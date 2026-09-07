"""Headless protocol model tests; these do not execute or emulate TF2 internals."""
import copy
import unittest
from unittest.mock import patch

from prototype.strict_sync.core import CAPABILITIES, ProtocolError, digest
from prototype.strict_sync.timing_probe import (
    ID, SEGMENTS, STEP_US, TIMING_CAPABILITY, WINDOW_STEPS,
    TimingCoordinator, TimingReplica, _metrics,
)

EPOCH = "timing-test-epoch"
MANIFEST = "a" * 64
CAPS = tuple(sorted((*CAPABILITIES, TIMING_CAPABILITY)))


class ModelTimingEngine:
    """Explicit verified-build-boundary fixture, not a replacement game adapter."""
    def __init__(self):
        self.frame, self.time_us, self.paused = 240, 55600000, False
        self.waits, self.windows = [], []
        self.changed_wait = False
        self.bad_metrics = False
        self.salt = ""

    @property
    def state_digest(self):
        return digest({"frame": self.frame, "time": self.time_us, "salt": self.salt})

    def receipt(self, metrics):
        return {"frame": self.frame, "sim_time_us": self.time_us,
                "state_digest": self.state_digest, "metrics": metrics}

    def check_idle_wait(self, delay, *, stop_requested=None):
        stop = stop_requested
        if stop and stop():
            raise ProtocolError("fixture stopped")
        self.waits.append(delay)
        if self.changed_wait:
            self.salt = "unexpected idle change"
        metrics = {"kind": "idle_wait", "requested_delay_ms": delay,
                   "actual_delay_ms": delay, "duration_ms": delay + 1,
                   "boundary_unchanged": True, "maintenance_observed": delay > 0,
                   "native_before": None, "native_after": None,
                   "counter_deltas": {"hold_calls": int(delay > 0), "outer_calls": int(delay > 0),
                                      "updated_ms": delay}}
        if self.bad_metrics:
            metrics.pop("actual_delay_ms")
        return self.receipt(metrics)

    def advance_window(self, count, step_us=STEP_US, stop_requested=None):
        stop = stop_requested
        if stop and stop():
            raise ProtocolError("fixture stopped")
        self.windows.append(count)
        steps = []
        for index in range(count):
            before = self.time_us
            self.frame += 1
            self.time_us += STEP_US
            steps.append({"frame": self.frame, "sim_time_us": self.time_us,
                          "scheduled_offset_us": (index + 1) * STEP_US,
                          "admitted_offset_us": (index + 1) * STEP_US,
                          "ack_observed_offset_us": (index + 1) * STEP_US + 1000,
                          "permit_duration_us": 1000, "lateness_us": 0,
                          "native_time_before_ms": before // 1000,
                          "native_time_after_ms": self.time_us // 1000})
        return self.receipt({"kind": "advance_window", "steps_requested": count,
            "step_us": STEP_US, "simulated_us": count * STEP_US, "duration_ms": 5001,
            "rate_ppm": 999800, "steps": steps, "world_observation": "start_and_end_only",
            "native_clock_each_step": True})


class TimingTests(unittest.TestCase):
    def setup_pair(self):
        coordinator = TimingCoordinator(EPOCH, MANIFEST, CAPS, step_us=STEP_US)
        engines = {peer: ModelTimingEngine() for peer in ("a", "b")}
        replicas = {peer: TimingReplica(peer, EPOCH, MANIFEST, CAPS, engines[peer], lambda _: [],
                                       frame=240, step_us=STEP_US) for peer in engines}
        # Skip the independently tested build using an explicit fixture boundary.
        coordinator.round = 240
        coordinator.frame = 240
        coordinator.sim_time_us = engines["a"].time_us
        coordinator.state_digest = engines["a"].state_digest
        coordinator.paused = False
        for replica in replicas.values():
            replica.round = 240
        return coordinator, replicas, engines

    def run_pair(self, coordinator, replicas, actions):
        queue = list(actions)
        while queue and not coordinator.halted:
            peer, message = queue.pop(0)
            reply = replicas[peer].receive(message)
            if reply:
                queue.extend(coordinator.receive(peer, reply))

    def test_full_schedule_compares_boundaries_but_keeps_distinct_timing(self):
        coordinator, replicas, engines = self.setup_pair()
        self.run_pair(coordinator, replicas, coordinator._request_inputs())
        self.assertFalse(coordinator.halted, coordinator.halt_reason)
        self.assertEqual(coordinator.phase, "inputs")
        self.assertEqual(coordinator.round, 240)
        self.assertEqual(coordinator.frame, 540)
        self.assertEqual(coordinator.sim_time_us, 115600000)
        report = coordinator.timing_report()
        self.assertTrue(report["completed"])
        self.assertEqual(report["segments_completed"], 12)
        self.assertEqual(report["additional_simulated_us"], 60000000)
        self.assertFalse(report["visual_smoothness_verified"])
        self.assertFalse(report["complete_world_verified"])
        self.assertTrue(report["paced_windows_1x_met"])
        self.assertEqual(report["peer_timing_summaries"]["a"]["actual_injected_wait_ms"], 4250)
        self.assertEqual(report["peer_timing_summaries"]["b"]["actual_injected_wait_ms"], 2750)
        self.assertEqual(report["peer_timing_summaries"]["a"]["acknowledgement_intervals"]["count"], 288)
        for peer in engines:
            self.assertEqual(engines[peer].windows, [25] * 12)
            self.assertEqual(engines[peer].waits,
                [segment.delay_ms if segment.delayed_peer == peer else 0 for segment in SEGMENTS])
            self.assertTrue(replicas[peer].timing_report()["completed"])
            self.assertIsNone(replicas[peer].receive({"kind": "complete", "epoch": EPOCH,
                "round": 240, "frame": 540, "sim_time_us": coordinator.sim_time_us,
                "state_digest": coordinator.state_digest}))
            self.assertTrue(replicas[peer].finished)

    def test_neither_run_nor_completion_before_both_barriers(self):
        coordinator, replicas, engines = self.setup_pair()
        prepares = coordinator._request_inputs()
        first = replicas["a"].receive(prepares[0][1])
        self.assertEqual(coordinator.receive("a", first), [])
        self.assertEqual(coordinator.phase, "timing_ready")
        self.assertFalse(coordinator.timing_report()["completed"])
        self.assertEqual(engines["a"].windows, [])
        runs = coordinator.receive("b", replicas["b"].receive(prepares[1][1]))
        self.assertEqual([message["kind"] for _, message in runs], ["timing_run"] * 2)
        done_a = replicas["a"].receive(runs[0][1])
        self.assertEqual(coordinator.receive("a", done_a), [])
        self.assertEqual(coordinator.phase, "timing_done")
        self.assertEqual(coordinator.frame, 240)
        self.assertFalse(coordinator.timing_report()["completed"])

    def test_duplicate_messages_are_cached_without_reexecution(self):
        coordinator, replicas, engines = self.setup_pair()
        prepares = coordinator._request_inputs()
        ready_a = replicas["a"].receive(prepares[0][1])
        self.assertEqual(replicas["a"].receive(prepares[0][1]), ready_a)
        self.assertEqual(engines["a"].waits, [0])
        coordinator.receive("a", ready_a)
        self.assertEqual(coordinator.receive("a", ready_a), [])
        runs = coordinator.receive("b", replicas["b"].receive(prepares[1][1]))
        done = replicas["a"].receive(runs[0][1])
        self.assertEqual(replicas["a"].receive(runs[0][1]), done)
        self.assertEqual(engines["a"].windows, [25])
        self.assertEqual(replicas["a"].receive(prepares[0][1]), ready_a)

    def test_conflicting_duplicate_halts(self):
        coordinator, replicas, _ = self.setup_pair()
        prepare = coordinator._request_inputs()[0][1]
        replicas["a"].receive(prepare)
        prepare = copy.deepcopy(prepare)
        prepare["plan_hash"] = "b" * 64
        with self.assertRaisesRegex(ProtocolError, "conflicting duplicate"):
            replicas["a"].receive(prepare)
        self.assertTrue(replicas["a"].halted)

    def test_wrong_epoch_plan_and_schedule_rejected_without_engine_work(self):
        for name, value in (("epoch", "other-epoch"), ("plan_hash", "b" * 64),
                            ("schedule_id", "other"), ("index", 1), ("steps", 24), ("paused", True)):
            coordinator, replicas, engines = self.setup_pair()
            prepare = coordinator._request_inputs()[0][1]
            prepare[name] = value
            with self.assertRaises(ProtocolError):
                replicas["a"].receive(prepare)
            self.assertEqual(engines["a"].waits, [])
            self.assertEqual(engines["a"].windows, [])

    def test_idle_mutation_or_missing_measurements_halts_before_window(self):
        for flag in ("changed_wait", "bad_metrics"):
            coordinator, replicas, engines = self.setup_pair()
            setattr(engines["a"], flag, True)
            with self.assertRaises(ProtocolError):
                replicas["a"].receive(coordinator._request_inputs()[0][1])
            self.assertEqual(engines["a"].windows, [])
            self.assertTrue(replicas["a"].halted)

    def test_missing_wait_proof_cannot_acknowledge_a_scheduled_delay(self):
        coordinator, replicas, engines = self.setup_pair()
        actions = coordinator._request_inputs()
        # Complete the three no-delay baseline windows.
        for _ in range(3):
            replies = [(peer, replicas[peer].receive(message)) for peer, message in actions]
            runs = []
            for peer, reply in replies:
                runs += coordinator.receive(peer, reply)
            done = [(peer, replicas[peer].receive(message)) for peer, message in runs]
            actions = []
            for peer, reply in done:
                actions += coordinator.receive(peer, reply)
        self.assertEqual(coordinator._timing_index, 3)
        reply = replicas["a"].receive(actions[0][1])
        reply["metrics"]["actual_delay_ms"] = 0
        self.assertEqual(coordinator.receive("a", reply)[0][1]["kind"], "halt")
        self.assertIn("wait was not measured", coordinator.halt_reason)
        self.assertEqual(len(engines["a"].windows), 3)

    def test_mismatched_window_end_prevents_next_window(self):
        coordinator, replicas, engines = self.setup_pair()
        runs = []
        for peer, message in coordinator._request_inputs():
            runs += coordinator.receive(peer, replicas[peer].receive(message))
        done = [(peer, replicas[peer].receive(message)) for peer, message in runs]
        done[1][1]["state_digest"] = "f" * 64
        coordinator.receive(*done[0])
        self.assertEqual(coordinator.receive(*done[1])[0][1]["kind"], "halt")
        self.assertIn("end world differs", coordinator.halt_reason)
        self.assertEqual(coordinator.frame, 240)
        self.assertEqual([len(engine.windows) for engine in engines.values()], [1, 1])

    def test_premature_normal_completion_rejected(self):
        coordinator, replicas, _ = self.setup_pair()
        with self.assertRaisesRegex(ProtocolError, "before the timing schedule"):
            replicas["a"].receive({"kind": "complete", "epoch": EPOCH, "round": 240,
                "frame": 240, "sim_time_us": coordinator.sim_time_us,
                "state_digest": coordinator.state_digest})

    def test_interior_native_step_clock_mismatch_cannot_be_reported_done(self):
        coordinator, replicas, engines = self.setup_pair()
        original = engines["a"].advance_window
        def broken(count, **kwargs):
            result = original(count, **kwargs)
            result["metrics"]["steps"][4]["native_time_after_ms"] += 1
            return result
        engines["a"].advance_window = broken
        runs = []
        for peer, message in coordinator._request_inputs():
            runs += coordinator.receive(peer, replicas[peer].receive(message))
        with self.assertRaisesRegex(ProtocolError, "native clock"):
            replicas["a"].receive(runs[0][1])
        self.assertTrue(replicas["a"].halted)

    def test_stop_callback_is_forwarded_and_terminal(self):
        coordinator, replicas, engines = self.setup_pair()
        replicas["a"]._stop_requested = lambda: True
        with self.assertRaisesRegex(ProtocolError, "stopped"):
            replicas["a"].receive(coordinator._request_inputs()[0][1])
        self.assertEqual(engines["a"].waits, [])

    def test_base_rounds_are_not_replaced(self):
        coordinator = TimingCoordinator(EPOCH, MANIFEST, CAPS, step_us=STEP_US)
        for number in (0, 1, 239):
            coordinator.round = number
            messages = coordinator._request_inputs()
            self.assertEqual(messages[0][1]["kind"], "request_inputs")
            self.assertEqual(coordinator.phase, "inputs")
            self.assertFalse(coordinator.timing_report()["started"])

    def test_metrics_noninteger_or_unbounded_values_are_refused(self):
        for bad in (float("nan"), 1.5, True, "0"):
            coordinator, replicas, _ = self.setup_pair()
            ready = replicas["a"].receive(coordinator._request_inputs()[0][1])
            ready["metrics"]["actual_delay_ms"] = bad
            result = coordinator.receive("a", ready)
            self.assertEqual(result[0][1]["kind"], "halt")

    def test_complete_slow_windows_are_not_misreported_as_one_times_speed(self):
        coordinator, replicas, engines = self.setup_pair()
        original = engines["b"].advance_window
        def slow(count, **kwargs):
            result = original(count, **kwargs)
            result["metrics"]["rate_ppm"] = 900000
            result["metrics"]["duration_ms"] = 5556
            return result
        engines["b"].advance_window = slow
        self.assertIsNone(coordinator.timing_report()["paced_windows_1x_met"])
        self.run_pair(coordinator, replicas, coordinator._request_inputs())
        report = coordinator.timing_report()
        self.assertTrue(report["completed"])
        self.assertFalse(report["paced_windows_1x_met"])
        self.assertTrue(replicas["a"].timing_report()["paced_windows_1x_met"])
        self.assertFalse(replicas["b"].timing_report()["paced_windows_1x_met"])

    def test_real_adapter_methods_match_protocol_contract_with_model_native_clock(self):
        # Exercises production methods, using the native/Lua stand-ins explicitly
        # named by the backend fixture. It is not actual TF2 evidence.
        from prototype.tests.test_engine_timing import AdapterFixture, Clock
        clock = Clock()
        coordinator, replicas, _ = self.setup_pair()
        for peer in replicas:
            engine = AdapterFixture(clock)
            engine.native.completed_frame = engine.native.request = 240
            engine.world["sim_time_us"] = coordinator.sim_time_us
            engine.native.before_ms = coordinator.sim_time_us // 1000
            engine._accept_snapshot(engine.observation())
            replicas[peer] = TimingReplica(peer, EPOCH, MANIFEST, CAPS, engine, lambda _: [],
                                           frame=240, step_us=STEP_US)
            replicas[peer].round = 240
        coordinator.state_digest = replicas["a"].engine.state_digest
        with patch("prototype.strict_sync.engine_mailbox.time.monotonic", clock.monotonic), \
             patch("prototype.strict_sync.engine_mailbox.time.sleep", clock.sleep):
            self.run_pair(coordinator, replicas, coordinator._request_inputs())
        self.assertFalse(coordinator.halted, coordinator.halt_reason)
        self.assertTrue(coordinator.timing_report()["completed"])
        self.assertTrue(coordinator.timing_report()["paced_windows_1x_met"])

    def window_metrics(self):
        engine = ModelTimingEngine()
        before = {"frame": engine.frame, "sim_time_us": engine.time_us}
        return before, engine.advance_window(WINDOW_STEPS)["metrics"]

    def test_inconsistent_rate_zero_duration_and_duration_before_last_ack_fail(self):
        for change in ({"rate_ppm": 900000}, {"duration_ms": 0},
                       {"duration_ms": 4000, "rate_ppm": 1250000}):
            before, metrics = self.window_metrics()
            metrics.update(change)
            with self.assertRaises(ProtocolError):
                _metrics(metrics, "done", before=before)

    def test_rate_rounding_at_both_ceil_millisecond_edges_is_accepted(self):
        for rate in (999800, 999801, 1000000, 1000001):
            before, metrics = self.window_metrics()
            metrics["rate_ppm"] = rate
            self.assertEqual(_metrics(metrics, "done", before=before)["rate_ppm"], rate)
        for rate in (999799, 1000002):
            before, metrics = self.window_metrics()
            metrics["rate_ppm"] = rate
            with self.assertRaisesRegex(ProtocolError, "rate is inconsistent"):
                _metrics(metrics, "done", before=before)

    def test_offset_derived_metrics_allow_only_one_microsecond_rounding(self):
        for field in ("permit_duration_us", "lateness_us"):
            before, metrics = self.window_metrics()
            metrics["steps"][0][field] += 1
            _metrics(metrics, "done", before=before)
            metrics["steps"][0][field] += 1
            with self.assertRaisesRegex(ProtocolError, "disagrees with measured offsets"):
                _metrics(metrics, "done", before=before)

    def test_period_quantization_does_not_permit_an_early_burst(self):
        before, metrics = self.window_metrics()
        step = metrics["steps"][1]
        step["admitted_offset_us"] -= 1
        _metrics(metrics, "done", before=before)
        step["admitted_offset_us"] -= 1
        with self.assertRaisesRegex(ProtocolError, "pacing admits steps faster"):
            _metrics(metrics, "done", before=before)


if __name__ == "__main__":
    unittest.main()
