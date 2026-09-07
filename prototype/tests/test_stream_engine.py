"""Native frontier/checkpoint separation without starting Transport Fever 2."""
import tempfile
import unittest
from unittest.mock import patch

from prototype.strict_sync.engine_mailbox import EngineAdapter, MailboxError
from prototype.strict_sync.stream_engine import StreamEngine
from prototype.tests.test_engine_mailbox import EPOCH
from prototype.tests.test_engine_mailbox_lua import ActualLuaWorker, RUNTIMES
from prototype.tests.test_engine_timing import AdapterFixture, Clock


class CommandAdapter(AdapterFixture):
    def __init__(self, clock, **kwargs):
        super().__init__(clock, **kwargs)
        self._last_apply = {}
        self._last_seq = {"a": 0, "b": 0}

    def _request_lua(self, action, **fields):
        result = super()._request_lua(action, **fields)
        if action == "apply":
            command = fields["command"]
            if command["op"] != "SET_PAUSED":
                raise MailboxError("fixture supports pause commands only")
            self.world["paused"] = command["value"]
            result = self.observation()
            result["receipt"] = {"command_key": fields["command_key"], "boundary": fields["boundary"],
                                 "success": True, "result": {"paused": self.world["paused"]}}
        return result


class StreamEngineTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        for target, replacement in (
            ("prototype.strict_sync.stream_engine.time.perf_counter", self.clock.monotonic),
            ("prototype.strict_sync.stream_engine.time.monotonic", self.clock.monotonic),
            ("prototype.strict_sync.stream_engine.time.sleep", self.clock.sleep),
        ):
            item = patch(target, replacement)
            item.start()
            self.addCleanup(item.stop)

    def stream(self, *, paused=False, **kwargs):
        base = CommandAdapter(self.clock, paused=paused)
        stream = StreamEngine(base, **kwargs)
        return base, stream

    def assert_terminal_released(self, stream):
        self.assertTrue(stream.halted)
        self.assertTrue(stream.engine.halted)
        self.assertTrue(stream.native.halted)
        self.assertFalse(stream.observations_fresh)
        for mutex in (stream._mutex, stream.engine._mutex):
            self.assertTrue(mutex.acquire(blocking=False))
            mutex.release()
        self.assertEqual(stream.native.timeout_s, 30)
        self.assertIsNone(stream.native._operation_deadline)

    def test_native_frontier_never_relabels_historical_world_as_current(self):
        base, stream = self.stream()
        self.assertFalse(stream.observations_fresh)
        with self.assertRaisesRegex(MailboxError, "historical"):
            stream.snapshot()
        start = stream.checkpoint()
        original = base.snapshot()
        lua_count = len(base.lua_requests)
        result = stream.advance(2)
        self.assertEqual(set(result), {"frame", "sim_time_us", "metrics"})
        self.assertEqual(result["frame"], 2)
        self.assertEqual(result["sim_time_us"], 400000)
        self.assertEqual(result["metrics"]["world_observation"], "none")
        self.assertEqual(len(base.lua_requests), lua_count)
        self.assertEqual(base.snapshot(), original)
        self.assertEqual(base.state_digest, start["state_digest"])
        self.assertEqual(base.time_us, 0)
        self.assertEqual(stream.time_us, 400000)
        self.assertEqual(stream.last_observed_frame, 0)
        self.assertFalse(stream.observations_fresh)
        with self.assertRaisesRegex(MailboxError, "historical"):
            stream.snapshot()
        end = stream.checkpoint()
        self.assertEqual(len(base.lua_requests), lua_count + 1)
        self.assertEqual(end["frame"], 2)
        self.assertEqual(end["sim_time_us"], 400000)
        self.assertNotEqual(end["state_digest"], start["state_digest"])
        self.assertEqual(stream.last_observed_time_us, 400000)
        self.assertTrue(stream.observations_fresh)
        self.assertEqual(stream.snapshot(), base.snapshot())

    def test_fifty_steps_use_twentyfive_native_chunks_and_only_two_checkpoints(self):
        base, stream = self.stream()
        stream.checkpoint()
        samples = []
        for _ in range(25):
            samples.extend(stream.advance(2)["metrics"]["steps"])
        stream.checkpoint()
        self.assertEqual(len(base.lua_requests), 2)
        self.assertEqual(stream.frame, 50)
        self.assertEqual(stream.time_us, 10000000)
        self.assertEqual(samples[0]["call_started_offset_us"], 200000)
        self.assertEqual(samples[-1]["call_started_offset_us"], 10000000)
        for previous, current in zip(samples, samples[1:]):
            self.assertGreaterEqual(current["call_started_offset_us"] - previous["call_started_offset_us"], 200000)

    def test_pacer_survives_chunks_and_checkpoint_without_per_chunk_reset(self):
        base, stream = self.stream()
        stream.checkpoint()
        first = stream.advance(1)["metrics"]["steps"][0]
        self.clock.now += .05
        stream.checkpoint()
        second = stream.advance(1)["metrics"]["steps"][0]
        self.assertEqual(first["call_started_offset_us"], 200000)
        self.assertEqual(second["call_started_offset_us"], 400000)
        self.assertEqual(second["scheduled_offset_us"], 400000)

    def test_slow_checkpoint_or_ack_never_causes_catchup_burst(self):
        base, stream = self.stream()
        stream.checkpoint()
        first = stream.advance(1)["metrics"]["steps"][0]
        self.clock.now += .75
        stream.checkpoint()
        base.native.permit_delays = [.35, .01]
        later = stream.advance(2)["metrics"]["steps"]
        self.assertGreater(later[0]["lateness_us"], 0)
        self.assertEqual(later[1]["call_started_offset_us"] - later[0]["call_started_offset_us"], 350000)
        self.assertGreaterEqual(later[0]["call_started_offset_us"] - first["call_started_offset_us"], 200000)

    def test_invalid_or_paused_advance_halts_without_permits(self):
        for count in (True, 0, -1, 3, 2.0, "2"):
            with self.subTest(count=count):
                base, stream = self.stream()
                stream.checkpoint()
                with self.assertRaises(MailboxError):
                    stream.advance(count)
                self.assertFalse(base.native.permits)
                self.assert_terminal_released(stream)
        for paused, checkpoint in ((True, True), (False, False)):
            base, stream = self.stream(paused=paused)
            if checkpoint:
                stream.checkpoint()
            with self.assertRaises(MailboxError):
                stream.advance(1)
            self.assertFalse(base.native.permits)
            self.assert_terminal_released(stream)

    def test_same_frame_checkpoint_detects_idle_world_mutation(self):
        base, stream = self.stream()
        stream.checkpoint()
        base.world["company"]["balance"] += 1
        with self.assertRaisesRegex(MailboxError, "world changed"):
            stream.checkpoint()
        self.assert_terminal_released(stream)

    def test_checkpoint_after_advance_accepts_world_change_but_rejects_time_pause_coverage(self):
        for field in ("time", "pause", "coverage"):
            with self.subTest(field=field):
                base, stream = self.stream()
                stream.checkpoint()
                last_good = stream.last_observed_snapshot
                stream.advance(2)
                def mutate(*_):
                    if field == "time":
                        base.world["sim_time_us"] -= 200000
                    elif field == "pause":
                        base.world["paused"] = True
                    else:
                        base.world["coverage"]["missing"] = ["vehicle"]
                base.on_lua_request = mutate
                with self.assertRaises(MailboxError):
                    stream.checkpoint()
                self.assertEqual(stream.last_observed_snapshot, last_good)
                self.assertEqual(stream.last_observed_frame, 0)
                self.assertEqual(stream.last_observed_time_us, last_good["sim_time_us"])
                self.assert_terminal_released(stream)

    def test_rejected_same_frame_fingerprint_keeps_last_accepted_snapshot(self):
        base, stream = self.stream()
        stream.checkpoint()
        stream.advance(2)
        stream.checkpoint()
        last_good = stream.last_observed_snapshot
        base.world["company"]["balance"] += 1
        with self.assertRaisesRegex(MailboxError, "world changed"):
            stream.checkpoint()
        self.assertEqual(stream.last_observed_snapshot, last_good)
        self.assertEqual(stream.last_observed_frame, 2)
        self.assertEqual(stream.last_observed_time_us, 400000)
        self.assertNotEqual(base.snapshot(), last_good)
        # Consumers cannot overwrite the retained evidence through its accessor.
        returned = stream.last_observed_snapshot
        returned["company"]["balance"] = -999
        self.assertEqual(stream.last_observed_snapshot, last_good)
        self.assert_terminal_released(stream)

    def test_rejected_command_after_base_cache_mutation_keeps_last_accepted_snapshot(self):
        base, stream = self.stream()
        stream.checkpoint()
        last_good = stream.last_observed_snapshot
        original = base.apply
        def bad_receipt(command, key):
            result = original(command, key)
            result["state_digest"] = "0" * 64
            return result
        base.apply = bad_receipt
        with self.assertRaisesRegex(MailboxError, "receipt"):
            stream.apply({"op": "SET_PAUSED", "value": True}, "a:1")
        self.assertTrue(base.snapshot()["paused"])
        self.assertFalse(stream.last_observed_snapshot["paused"])
        self.assertEqual(stream.last_observed_snapshot, last_good)
        self.assertEqual(stream.last_observed_frame, 0)
        self.assert_terminal_released(stream)

    def test_native_fault_stops_second_permit_and_keeps_world_historical(self):
        for change in ({"time_after_ms": 201}, {"completed_frame": 2},
                       {"completed_dt_us": 0}, {"time_before_ms": 1}, {"pending_state": 1}):
            with self.subTest(change=change):
                base, stream = self.stream()
                stream.checkpoint()
                base.native.change_result = lambda status: status.update(change)
                with self.assertRaisesRegex(MailboxError, "clock/frame"):
                    stream.advance(2)
                self.assertEqual(len(base.native.permits), 1)
                self.assertEqual(base.time_us, 0)
                self.assert_terminal_released(stream)

    def test_hold_overwrite_of_native_before_time_is_valid_diagnostic(self):
        base, stream = self.stream()
        stream.checkpoint()
        base.native.change_result = lambda status: status.update(time_before_ms=status["time_after_ms"])
        self.assertEqual(stream.advance(2)["frame"], 2)

    def test_chunk_total_budget_includes_multiple_waits_and_restores_settings(self):
        base, stream = self.stream()
        stream.checkpoint()
        base.native.permit_delays = [2, 2]
        began = self.clock.now
        with self.assertRaisesRegex(MailboxError, "budget"):
            stream.advance(2)
        self.assertLessEqual(self.clock.now - began, 3)
        self.assertEqual(len(base.native.permits), 2)
        self.assertEqual(stream.frame, 1)
        self.assertEqual(stream.time_us, 200000)
        self.assertEqual(stream.last_observed_frame, 0)
        self.assertLessEqual(max(base.native.observed_timeouts), 3)
        self.assert_terminal_released(stream)

    def test_cancel_before_pacing_or_between_permits_stops_new_work(self):
        for permits in (0, 1):
            base, stream = self.stream()
            stream.checkpoint()
            stream._stop_requested = lambda: len(base.native.permits) >= permits
            with self.assertRaisesRegex(MailboxError, "cancelled"):
                stream.advance(2)
            self.assertEqual(len(base.native.permits), permits)
            self.assertEqual(stream.frame, permits)
            self.assertEqual(stream.time_us, permits * 200000)
            self.assertEqual(stream.last_observed_frame, 0)
            self.assert_terminal_released(stream)
        base, stream = self.stream()
        stream.checkpoint()
        stopped = [False]
        stream._stop_requested = lambda: stopped[0]
        self.clock.on_sleep = lambda: stopped.__setitem__(0, True)
        with self.assertRaisesRegex(MailboxError, "cancelled"):
            stream.advance(1)
        self.assertFalse(base.native.permits)
        self.assert_terminal_released(stream)

    def test_pause_hold_resume_same_frame_updates_fresh_state_and_rebases_pacer(self):
        base, stream = self.stream()
        stream.checkpoint()
        first = stream.advance(2)
        stream.checkpoint()
        paused = stream.apply({"op": "SET_PAUSED", "value": True}, "a:1")
        self.assertTrue(paused["success"])
        self.assertTrue(stream.paused)
        before = stream.snapshot()
        held = stream.hold(2000)
        self.assertEqual(held["frame"], 2)
        self.assertEqual(held["sim_time_us"], 400000)
        self.assertGreaterEqual(held["metrics"]["actual_delay_ms"], 2000)
        self.assertTrue(held["metrics"]["maintenance_observed"])
        self.assertEqual(stream.snapshot(), before)
        stream.apply({"op": "SET_PAUSED", "value": False}, "b:1")
        self.assertFalse(stream.paused)
        resumed_at = self.clock.now
        second = stream.advance(1)["metrics"]["steps"][0]
        self.assertAlmostEqual(base.native.permits[-1][2] - resumed_at, .2, places=6)
        self.assertEqual(second["lateness_us"], 0)
        self.assertGreater(second["call_started_offset_us"], first["metrics"]["steps"][-1]["call_started_offset_us"] + 2000000)

    def test_commands_require_fresh_checkpoint_and_preserve_existing_key_validation(self):
        base, stream = self.stream()
        stream.checkpoint()
        stream.advance(1)
        with self.assertRaisesRegex(MailboxError, "fresh checkpoint"):
            stream.apply({"op": "SET_PAUSED", "value": True}, "a:1")
        self.assert_terminal_released(stream)
        base, stream = self.stream()
        stream.checkpoint()
        with self.assertRaisesRegex(MailboxError, "sequence"):
            stream.apply({"op": "SET_PAUSED", "value": True}, "a:2")
        self.assert_terminal_released(stream)

    def test_hold_invalid_cancelled_and_changed_world_halt(self):
        for duration in (-1, 2001, True, 2.0):
            base, stream = self.stream(paused=True)
            with self.assertRaises(MailboxError):
                stream.hold(duration)
            self.assert_terminal_released(stream)
        base, stream = self.stream(paused=True)
        stream.checkpoint()
        self.clock.on_sleep = lambda: base.world["company"].__setitem__("balance", 123)
        with self.assertRaisesRegex(MailboxError, "world changed"):
            stream.hold(20)
        self.assertFalse(base.native.permits)
        self.assert_terminal_released(stream)

    def test_old_command_receipt_cannot_be_presented_as_a_current_pause(self):
        base, stream = self.stream()
        stream.checkpoint()
        first = stream.apply({"op": "SET_PAUSED", "value": True}, "a:1")
        self.assertEqual(first, stream.apply({"op": "SET_PAUSED", "value": True}, "a:1"))
        stream.apply({"op": "SET_PAUSED", "value": False}, "a:2")
        with self.assertRaisesRegex(MailboxError, "receipt"):
            stream.apply({"op": "SET_PAUSED", "value": True}, "a:1")
        self.assertFalse(base.native.permits)
        self.assert_terminal_released(stream)

    def test_checkpoint_and_hold_share_one_absolute_operation_budget(self):
        for method in ("checkpoint", "hold"):
            base, stream = self.stream(paused=True)
            base.on_lua_request = lambda *_: setattr(self.clock, "now", self.clock.now + 6)
            with self.assertRaisesRegex(MailboxError, "budget"):
                stream.checkpoint() if method == "checkpoint" else stream.hold(2000)
            self.assert_terminal_released(stream)


@unittest.skipUnless(RUNTIMES, "Lupa test runtime unavailable")
class StreamLuaMailboxIntegrationTests(unittest.TestCase):
    def test_production_lua_checkpoints_commands_and_historical_cache_on_all_runtimes(self):
        for runtime in RUNTIMES:
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as directory:
                worker = ActualLuaWorker(directory, runtime)
                base = stream = None
                try:
                    base = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=2, poll_s=.002)
                    stream = StreamEngine(base)
                    start = stream.checkpoint()
                    self.assertTrue(start["paused"])
                    stream.apply({"op": "SET_PAUSED", "value": False}, "a:1")
                    before = base.snapshot()
                    request = base.request
                    first = stream.advance(2)
                    second = stream.advance(1)
                    self.assertEqual(base.request, request)
                    self.assertEqual(base.snapshot(), before)
                    self.assertEqual(base.time_us, 0)
                    self.assertEqual(stream.time_us, 600000)
                    self.assertEqual(first["frame"], 2)
                    self.assertEqual(second["frame"], 3)
                    checkpoint = stream.checkpoint()
                    self.assertEqual(base.request, request + 1)
                    self.assertEqual(checkpoint["sim_time_us"], 600000)
                    self.assertTrue(stream.observations_fresh)
                    stream.apply({"op": "SET_PAUSED", "value": True}, "a:2")
                    held = stream.hold(20)
                    self.assertTrue(held["metrics"]["boundary_unchanged"])
                    self.assertFalse(held["metrics"]["maintenance_observed"])
                    self.assertEqual(worker.clock_us, 600000)
                    self.assertEqual(stream.frame, 3)
                    self.assertEqual(base.snapshot(), stream.snapshot())
                finally:
                    if stream is not None:
                        stream.close()
                    if base is not None:
                        base.close()
                    worker.close()


if __name__ == "__main__":
    unittest.main()
