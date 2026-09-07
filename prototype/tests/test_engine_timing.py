"""Bounded timing-controller tests. No Transport Fever 2 process is launched."""

import copy
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from prototype.strict_sync.engine_mailbox import EngineAdapter, MailboxError, NativeMailbox
from prototype.tests.test_engine_mailbox import EPOCH, native_state, snapshot
from prototype.tests.test_engine_mailbox_lua import ActualLuaWorker, RUNTIMES


class Clock:
    def __init__(self):
        self.now = 100.0
        self.oversleep = 0
        self.on_sleep = None

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds + self.oversleep
        self.oversleep = 0
        if self.on_sleep:
            self.on_sleep()


class NativeFixture:
    """Only native admission and clock are fixtures; snapshot checks are real."""
    def __init__(self, clock, world):
        self.clock, self.world = clock, world
        self.completed_frame = self.request = 0
        self.halted = False
        self.timeout_s = 30
        self._operation_deadline = None
        self.before_ms = self.world["sim_time_us"] // 1000
        self.permits = []
        self.permit_delays = []
        self.observed_timeouts = []
        self.change_result = None
        self.status_changes = {}

    def read_status(self):
        return native_state(completed_frame=self.completed_frame,
                            completed_dt_us=200000 if self.completed_frame else 0,
                            request_received=self.request, request_acknowledged=self.request,
                            request_completed=self.request, outer_calls=1,
                            time_before_ms=self.before_ms,
                            time_after_ms=self.world["sim_time_us"] // 1000,
                            updated_ms=round(self.clock.now * 1000),
                            hold_calls=round(self.clock.now * 100), **self.status_changes)

    def _wait(self, function):
        NativeMailbox._check_operation_deadline(self)
        result = function()
        NativeMailbox._check_operation_deadline(self)
        if result is None:
            raise MailboxError("fixture status unavailable")
        return result

    def permit(self, frame, dt_us):
        self.permits.append((frame, dt_us, self.clock.now))
        self.observed_timeouts.append(self.timeout_s)
        self.before_ms = self.world["sim_time_us"] // 1000
        delay = self.permit_delays.pop(0) if self.permit_delays else .01
        self.clock.now += min(delay, self.timeout_s)
        NativeMailbox._check_operation_deadline(self)
        if delay > self.timeout_s:
            raise MailboxError("fixture native acknowledgement timeout")
        self.completed_frame = frame
        self.request += 1
        self.world["sim_time_us"] += dt_us
        result = self.read_status()
        if self.change_result:
            self.change_result(result)
        return result

    def _write(self, *_, **__):
        pass

    def halt(self, reason):
        self.halted = True


class AdapterFixture(EngineAdapter):
    def __init__(self, clock, *, paused=False):
        self.world = snapshot()
        self.world["paused"] = paused
        self.native = NativeFixture(clock, self.world)
        self.epoch = EPOCH
        self.request = 0
        self._mutex = threading.Lock()
        self.halted = False
        self.reason = ""
        self.lua_requests = []
        self.on_lua_request = None
        self._accept_snapshot(self.observation())

    def observation(self):
        return {"snapshot": copy.deepcopy(self.world),
                "canonical_state_json": json.dumps(self.world)}

    def _request_lua(self, action, **fields):
        self._check_gate(fields["expected_sim_time_us"])
        self.lua_requests.append((action, fields, len(self.native.permits)))
        if self.on_lua_request:
            self.on_lua_request(self, action, fields)
        return self.observation()


class EngineTimingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.patches = [patch("prototype.strict_sync.engine_mailbox.time.monotonic", self.clock.monotonic),
                        patch("prototype.strict_sync.engine_mailbox.time.sleep", self.clock.sleep)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def assert_released_halted(self, engine):
        self.assertTrue(engine.halted)
        self.assertTrue(engine.native.halted)
        self.assertTrue(engine._mutex.acquire(blocking=False))
        engine._mutex.release()

    def test_window_full_bound_native_each_step_world_at_endpoints_only(self):
        engine = AdapterFixture(self.clock)
        result = engine.advance_window()
        self.assertEqual(result["frame"], 25)
        self.assertEqual(result["sim_time_us"], 5_000_000)
        self.assertEqual(result["state_digest"], engine.state_digest)
        self.assertEqual(len(engine.native.permits), 25)
        self.assertEqual([item[2] for item in engine.lua_requests], [0, 25])
        metrics = result["metrics"]
        self.assertEqual(metrics["steps_requested"], 25)
        self.assertEqual(metrics["simulated_us"], 5_000_000)
        self.assertEqual(metrics["world_observation"], "start_and_end_only")
        self.assertTrue(metrics["native_clock_each_step"])
        self.assertEqual(metrics["steps"][0]["scheduled_offset_us"], 200000)
        for index, record in enumerate(metrics["steps"]):
            self.assertEqual(record["frame"], index + 1)
            self.assertEqual(record["native_time_before_ms"], index * 200)
            self.assertEqual(record["native_time_after_ms"], (index + 1) * 200)
            self.assertEqual(record["permit_duration_us"], 10000)
        self.assertTrue(5000 <= metrics["duration_ms"] <= 5011)
        self.assertFalse(engine.halted)
        self.assertEqual(engine.native.timeout_s, 30)
        self.assertIsNone(engine.native._operation_deadline)
        self.assertTrue(engine._mutex.acquire(blocking=False))
        engine._mutex.release()

    def test_invalid_window_arguments_halt_without_any_permit(self):
        cases = [{"steps": n} for n in (True, 0, -1, 26, 1.0, "2")]
        cases += [{"step_us": n} for n in (True, 0, 100000, 200000.0)]
        cases += [{"stop_requested": False}, {"stop_requested": lambda: None}]
        for values in cases:
            with self.subTest(values=values):
                engine = AdapterFixture(self.clock)
                with self.assertRaises(MailboxError):
                    engine.advance_window(**values)
                self.assertFalse(engine.native.permits)
                self.assert_released_halted(engine)

    def test_paused_window_rejected_after_fresh_observation(self):
        engine = AdapterFixture(self.clock, paused=True)
        with self.assertRaisesRegex(MailboxError, "pause"):
            engine.advance_window()
        self.assertEqual(len(engine.lua_requests), 1)
        self.assertFalse(engine.native.permits)
        self.assert_released_halted(engine)

    def test_changed_start_snapshot_stops_before_first_permit(self):
        engine = AdapterFixture(self.clock)
        engine.world["company"]["balance"] += 1
        with self.assertRaisesRegex(MailboxError, "world changed"):
            engine.advance_window()
        self.assertFalse(engine.native.permits)
        self.assert_released_halted(engine)

    def test_native_clock_and_boundary_faults_halt_after_first_permit(self):
        changes = ({"time_before_ms": 1}, {"time_after_ms": 201},
                   {"completed_frame": 2}, {"completed_dt_us": 0}, {"pending_state": 1})
        for change in changes:
            with self.subTest(change=change):
                engine = AdapterFixture(self.clock)
                engine.native.change_result = lambda status: status.update(change)
                with self.assertRaisesRegex(MailboxError, "native clock/frame"):
                    engine.advance_window()
                self.assertEqual(len(engine.native.permits), 1)
                self.assert_released_halted(engine)

    def test_subsequent_hold_may_update_sampled_before_clock_to_target(self):
        engine = AdapterFixture(self.clock)
        engine.native.change_result = lambda status: status.update(time_before_ms=status["time_after_ms"])
        result = engine.advance_window(steps=2)
        self.assertEqual(result["frame"], 2)
        self.assertEqual(result["metrics"]["steps"][0]["native_time_before_ms"], 200)
        self.assertEqual(result["metrics"]["steps"][1]["native_time_before_ms"], 400)

    def test_endpoint_snapshot_clock_pause_and_coverage_failures_halt(self):
        def wrong_time(engine):
            engine.world["sim_time_us"] -= 200000
        def wrong_pause(engine):
            engine.world["paused"] = True
        def wrong_coverage(engine):
            engine.world["coverage"]["missing"] = ["vehicle"]
        for mutate in (wrong_time, wrong_pause, wrong_coverage):
            with self.subTest(mutate=mutate):
                engine = AdapterFixture(self.clock)
                engine.on_lua_request = lambda obj, *_: mutate(obj) if obj.native.permits else None
                with self.assertRaises(MailboxError):
                    engine.advance_window(steps=3)
                self.assertEqual(len(engine.native.permits), 3)
                self.assert_released_halted(engine)

    def test_cancel_before_start_during_pacing_and_between_permits(self):
        for after in (0, 2):
            engine = AdapterFixture(self.clock)
            with self.assertRaisesRegex(MailboxError, "cancelled"):
                engine.advance_window(stop_requested=lambda: len(engine.native.permits) >= after)
            self.assertEqual(len(engine.native.permits), after)
            self.assert_released_halted(engine)
        engine = AdapterFixture(self.clock)
        cancelled = [False]
        self.clock.on_sleep = lambda: cancelled.__setitem__(0, True)
        with self.assertRaisesRegex(MailboxError, "cancelled"):
            engine.advance_window(stop_requested=lambda: cancelled[0])
        self.assertFalse(engine.native.permits)
        self.assert_released_halted(engine)

    def test_late_wakeup_rebases_next_admission_without_catchup(self):
        engine = AdapterFixture(self.clock)
        self.clock.oversleep = .5
        records = engine.advance_window(steps=3)["metrics"]["steps"]
        self.assertGreater(records[0]["lateness_us"], 0)
        self.assertGreaterEqual(records[1]["admitted_offset_us"] - records[0]["admitted_offset_us"], 200000)
        self.assertGreaterEqual(records[2]["admitted_offset_us"] - records[1]["admitted_offset_us"], 200000)

    def test_slow_ack_neither_catches_up_nor_adds_an_extra_period(self):
        engine = AdapterFixture(self.clock)
        engine.native.permit_delays = [.35, .01, .01]
        records = engine.advance_window(steps=3)["metrics"]["steps"]
        self.assertEqual([r["admitted_offset_us"] for r in records], [200000, 550000, 750000])
        self.assertEqual(records[0]["ack_observed_offset_us"], records[1]["admitted_offset_us"])
        self.assertEqual(records[1]["lateness_us"], 150000)

    def test_multiple_slow_acks_exhaust_total_budget_and_restore_timeout(self):
        engine = AdapterFixture(self.clock)
        # Each ACK fits the original 30s mailbox timeout; together they must
        # still terminate the 12s window before all 25 permits are admitted.
        engine.native.permit_delays = [3] * 25
        with self.assertRaisesRegex(MailboxError, "wall-clock budget"):
            engine.advance_window()
        self.assertEqual(len(engine.native.permits), 4)
        self.assertLessEqual(self.clock.now, 112)
        self.assertTrue(all(timeout <= 12 for timeout in engine.native.observed_timeouts))
        self.assertEqual(engine.native.timeout_s, 30)
        self.assertIsNone(engine.native._operation_deadline)
        self.assert_released_halted(engine)

    def test_endpoint_work_counts_against_absolute_window_budget(self):
        engine = AdapterFixture(self.clock)
        engine.on_lua_request = lambda *_: setattr(self.clock, "now", self.clock.now + 4)
        with self.assertRaisesRegex(MailboxError, "wall-clock budget"):
            engine.advance_window(steps=1)
        self.assertFalse(engine.native.permits)
        self.assertEqual(engine.native.timeout_s, 30)
        self.assertIsNone(engine.native._operation_deadline)
        self.assert_released_halted(engine)

    def test_native_nested_waits_share_absolute_deadline(self):
        native = NativeMailbox.__new__(NativeMailbox)
        native.timeout_s, native.poll_s = 30, .01
        native._operation_deadline = self.clock.now + .05
        first_deadline = native._wait_deadline()
        self.clock.now += .02
        self.assertEqual(native._wait_deadline(), first_deadline)
        with self.assertRaisesRegex(MailboxError, "wall-clock budget"):
            native._wait(lambda: None)
        self.assertLessEqual(self.clock.now, first_deadline + .011)
        self.assertGreater(native._wait_deadline(emergency=True), first_deadline)

    def test_idle_preserves_paused_and_unpaused_world_without_permits(self):
        for paused in (True, False):
            with self.subTest(paused=paused):
                engine = AdapterFixture(self.clock, paused=paused)
                before = engine.snapshot()
                result = engine.check_idle_wait(100)
                self.assertEqual(engine.snapshot(), before)
                self.assertEqual(result["frame"], 0)
                self.assertEqual(len(engine.lua_requests), 2)
                self.assertFalse(engine.native.permits)
                self.assertTrue(result["metrics"]["boundary_unchanged"])
                self.assertTrue(result["metrics"]["maintenance_observed"])
                self.assertGreaterEqual(result["metrics"]["actual_delay_ms"], 100)

    def test_idle_absent_and_stale_maintenance_evidence_is_not_zero_or_success(self):
        for remove, stale in ((True, False), (False, True)):
            engine = AdapterFixture(self.clock)
            original = engine.native.read_status
            def status():
                value = original()
                if remove:
                    value.pop("hold_calls")
                    value.pop("updated_ms")
                if stale:
                    value["updated_ms"] = 1234
                return value
            engine.native.read_status = status
            metrics = engine.check_idle_wait(100)["metrics"]
            self.assertFalse(metrics["maintenance_observed"])
            if remove:
                self.assertIsNone(metrics["native_before"]["hold_calls"])
                self.assertIsNone(metrics["counter_deltas"]["hold_calls"])
            else:
                self.assertEqual(metrics["counter_deltas"]["updated_ms"], 0)
                self.assertGreater(metrics["counter_deltas"]["hold_calls"], 0)

    def test_idle_world_or_native_boundary_change_halts(self):
        for fault in ("world", "pending", "time", "frame"):
            with self.subTest(fault=fault):
                engine = AdapterFixture(self.clock)
                def mutate():
                    if fault == "world":
                        engine.world["company"]["balance"] += 1
                    elif fault == "pending":
                        engine.native.status_changes["pending_state"] = 1
                    elif fault == "time":
                        engine.world["sim_time_us"] += 200000
                    else:
                        engine.native.completed_frame += 1
                self.clock.on_sleep = mutate
                with self.assertRaises(MailboxError):
                    engine.check_idle_wait(100)
                self.assertFalse(engine.native.permits)
                self.assert_released_halted(engine)
                self.clock.on_sleep = None

    def test_idle_invalid_or_cancelled_wait_is_terminal(self):
        for duration in (True, -1, 30001, 1.0):
            engine = AdapterFixture(self.clock)
            with self.assertRaises(MailboxError):
                engine.check_idle_wait(duration)
            self.assert_released_halted(engine)
        engine = AdapterFixture(self.clock)
        cancelled = [False]
        self.clock.on_sleep = lambda: cancelled.__setitem__(0, True)
        with self.assertRaisesRegex(MailboxError, "cancelled"):
            engine.check_idle_wait(30000, stop_requested=lambda: cancelled[0])
        self.assertFalse(engine.native.permits)
        self.assertLess(self.clock.now - 100, .03)
        self.assert_released_halted(engine)


@unittest.skipUnless(RUNTIMES, "Lupa test runtime unavailable")
class TimingLuaMailboxIntegrationTests(unittest.TestCase):
    def test_production_lua_endpoints_and_idle_use_actual_file_ipc_on_all_runtimes(self):
        for runtime in RUNTIMES:
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as directory:
                worker = ActualLuaWorker(directory, runtime)
                engine = None
                try:
                    engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=2, poll_s=.002)
                    engine.apply({"op": "SET_PAUSED", "value": False}, "a:1")
                    request_before = engine.request
                    result = engine.advance_window(steps=2)
                    self.assertEqual(engine.request - request_before, 2)
                    self.assertEqual(result["frame"], 2)
                    self.assertEqual(result["sim_time_us"], 400000)
                    self.assertEqual(worker.clock_us, 400000)
                    before_hash = engine.state_digest
                    idle = engine.check_idle_wait(20)
                    self.assertTrue(idle["metrics"]["boundary_unchanged"])
                    self.assertEqual(before_hash, engine.state_digest)
                    self.assertFalse(idle["metrics"]["maintenance_observed"])
                    self.assertEqual(idle["metrics"]["counter_deltas"]["updated_ms"], 0)
                    engine.apply({"op": "SET_PAUSED", "value": True}, "a:2")
                    engine.check_idle_wait(20)
                    self.assertEqual(engine.frame, 2)
                    self.assertEqual(worker.clock_us, 400000)
                finally:
                    if engine is not None:
                        engine.close()
                    worker.close()


if __name__ == "__main__":
    unittest.main()
