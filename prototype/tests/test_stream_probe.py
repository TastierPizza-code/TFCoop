"""Headless committed-stream models; no actual TF2 or desktop interaction."""
import copy
import math
import unittest
from unittest.mock import patch

from prototype.strict_sync.core import CAPABILITIES, ProtocolError, digest
from prototype.strict_sync.stream_probe import (
    CHECKPOINTS, CHECKPOINT_STEPS, CHUNK_STEPS, HOLD_MS, ID, PAUSE_AT, STEP_US,
    STREAM_CAPABILITY, STREAM_WORLD_RECEIPTS, TOTAL_STEPS, StreamCoordinator, StreamReplica,
)

EPOCH = "stream-model-epoch"
MANIFEST = "b" * 64
CAPS = tuple(sorted((*CAPABILITIES, STREAM_CAPABILITY)))


class BaseWorldModel:
    """Reading historical world properties deliberately fails in this fixture."""
    def __init__(self):
        self.world = {"frame": 240, "time": 55600000, "paused": False, "salt": ""}
        self.observed = dict(self.world)
        self.stream = None
        self.commands = []

    def _fresh(self):
        if self.stream and not self.stream.observations_fresh:
            raise AssertionError("attempted to read a historical world as current")

    @property
    def frame(self):
        return self.world["frame"]

    @property
    def state_digest(self):
        self._fresh()
        return digest(self.observed)

    @property
    def time_us(self):
        self._fresh()
        return self.observed["time"]

    @property
    def paused(self):
        self._fresh()
        return self.observed["paused"]


class StreamWorldModel:
    """Explicit native frontier and cached-world distinction for protocol tests."""
    def __init__(self, engine, stop_requested=None):
        self.engine, self.stop_requested = engine, stop_requested
        engine.stream = self
        self.observations_fresh = False
        self.last_observed_frame = engine.observed["frame"]
        self.last_observed_time_us = engine.observed["time"]
        self.clock_us, self.next_call_us = 0, STEP_US
        self.advances, self.checkpoints, self.holds = [], [], []
        self.bad_hash = self.bad_hold = self.mutate_checkpoint = False

    @property
    def frame(self):
        return self.engine.world["frame"]

    @property
    def time_us(self):
        return self.engine.world["time"]

    @property
    def paused(self):
        return self.engine.world["paused"]

    def _stop(self):
        if self.stop_requested and self.stop_requested():
            raise ProtocolError("model stopped")

    def checkpoint(self):
        self._stop()
        self.checkpoints.append(self.frame)
        if self.mutate_checkpoint:
            self.engine.world["salt"] = "checkpoint divergence"
        self.engine.observed = dict(self.engine.world)
        self.observations_fresh = True
        self.last_observed_frame, self.last_observed_time_us = self.frame, self.time_us
        return {"frame": self.frame, "sim_time_us": self.time_us, "paused": self.paused,
                "state_digest": self.engine.state_digest}

    def advance(self, steps):
        self._stop()
        self.advances.append(steps)
        before_wall = self.clock_us
        measurements = []
        for _ in range(steps):
            start = max(self.next_call_us, self.clock_us)
            before = self.time_us
            self.engine.world["frame"] += 1
            self.engine.world["time"] += STEP_US
            self.clock_us = start + 1000
            measurements.append({"frame": self.frame, "sim_time_us": self.time_us,
                "scheduled_offset_us": self.next_call_us, "call_started_offset_us": start,
                "ack_observed_offset_us": self.clock_us, "permit_duration_us": 1000,
                "lateness_us": start - self.next_call_us, "native_time_before_ms": before // 1000,
                "native_time_after_ms": self.time_us // 1000})
            self.next_call_us = start + STEP_US
        self.observations_fresh = False
        result = {"frame": self.frame, "sim_time_us": self.time_us, "metrics": {
            "kind": "stream_advance", "steps_requested": steps, "step_us": STEP_US,
            "simulated_us": steps * STEP_US, "duration_ms": math.ceil((self.clock_us - before_wall) / 1000),
            "steps": measurements, "world_observation": "none", "clock_origin": "stream_local_monotonic",
            "native_clock_each_step": True}}
        if self.bad_hash:
            result["state_digest"] = digest(self.engine.observed)
        return result

    def apply(self, command, key):
        self._stop()
        if not self.observations_fresh:
            raise AssertionError("model command before checkpoint")
        self.engine.commands.append((key, dict(command)))
        self.engine.world["paused"] = command["value"]
        if not command["value"]:
            self.next_call_us = self.clock_us + STEP_US
        self.engine.observed = dict(self.engine.world)
        return {"success": True, "result": {"paused": command["value"]}, "state_digest": self.engine.state_digest}

    def hold(self, milliseconds):
        self._stop()
        self.holds.append(milliseconds)
        self.clock_us += milliseconds * 1000
        boundary = self.checkpoint()
        return {**boundary, "metrics": {"kind": "stream_hold", "requested_delay_ms": milliseconds,
            "actual_delay_ms": milliseconds - int(self.bad_hold), "duration_ms": milliseconds + 1,
            "boundary_unchanged": True, "native_before": None, "native_after": None,
            "counter_deltas": {"hold_calls": 20, "outer_calls": 20, "updated_ms": milliseconds},
            "maintenance_observed": True}}


class StreamTests(unittest.TestCase):
    def pair(self):
        coordinator = StreamCoordinator(EPOCH, MANIFEST, CAPS, step_us=STEP_US)
        engines = {peer: BaseWorldModel() for peer in ("a", "b")}
        replicas = {peer: StreamReplica(peer, EPOCH, MANIFEST, CAPS, engines[peer], lambda _: [],
                    frame=240, step_us=STEP_US, stream_engine_factory=StreamWorldModel) for peer in engines}
        # The build is covered independently; this fixture starts at its exact boundary.
        coordinator.round = coordinator.frame = 240
        coordinator.sim_time_us = engines["a"].time_us
        coordinator.state_digest = engines["a"].state_digest
        coordinator.paused = False
        for replica in replicas.values():
            replica.round = 240
        return coordinator, replicas, engines

    def exchange(self, coordinator, replicas, actions):
        replies = [(peer, replicas[peer].receive(message)) for peer, message in actions]
        result = []
        for peer, reply in replies:
            result.extend(coordinator.receive(peer, reply))
        return result

    def run_until(self, coordinator, replicas, actions, kind=None):
        while actions and not coordinator.halted:
            if kind and actions[0][1]["kind"] == kind:
                return actions
            actions = self.exchange(coordinator, replicas, actions)
        return actions

    def test_full_stream_has_600_native_steps_12_checkpoints_and_scheduled_pause(self):
        coordinator, replicas, engines = self.pair()
        self.run_until(coordinator, replicas, coordinator._request_inputs())
        self.assertFalse(coordinator.halted, coordinator.halt_reason)
        self.assertEqual(coordinator.phase, "inputs")
        self.assertEqual(coordinator.round, 240)
        self.assertEqual(coordinator.frame, 840)
        self.assertEqual(coordinator.sim_time_us, 175600000)
        report = coordinator.stream_report()
        self.assertTrue(report["completed"])
        self.assertTrue(report["pause_proof"]["completed"])
        self.assertTrue(report["paced_stream_1x_met"])
        self.assertEqual(report["advanced_steps"], TOTAL_STEPS)
        self.assertEqual(report["checkpoints_completed"], CHECKPOINTS)
        self.assertFalse(report["visual_smoothness_verified"])
        for peer, replica in replicas.items():
            wrapper = replica.stream_engine
            self.assertEqual(wrapper.advances, [CHUNK_STEPS] * (TOTAL_STEPS // CHUNK_STEPS))
            self.assertEqual(wrapper.holds, [HOLD_MS])
            self.assertEqual([key for key, _ in engines[peer].commands], ["a:8", "b:6"])
            self.assertTrue(replica.stream_report()["completed"])
            self.assertEqual(replica.stream_progress()["last_observed_frame"], 840)
            self.assertIsNone(replica.receive({"kind": "complete", "epoch": EPOCH, "round": 240,
                "frame": 840, "sim_time_us": coordinator.sim_time_us, "state_digest": coordinator.state_digest}))
            self.assertTrue(replica.finished)

    def test_native_only_replies_never_read_or_claim_historical_world(self):
        coordinator, replicas, _ = self.pair()
        chunks = self.exchange(coordinator, replicas, coordinator._request_inputs())
        reply = replicas["a"].receive(chunks[0][1])
        self.assertNotIn("state_digest", reply)
        self.assertNotIn("snapshot", reply)
        self.assertNotIn(reply["kind"], STREAM_WORLD_RECEIPTS)
        self.assertFalse(replicas["a"].stream_engine.observations_fresh)
        self.assertEqual(replicas["a"].stream_progress()["frame"], 242)
        self.assertEqual(replicas["a"].stream_progress()["last_observed_frame"], 240)
        self.assertIsNone(replicas["a"].stream_report()["paced_stream_1x_met"])

    def test_native_reply_containing_old_hash_is_rejected(self):
        coordinator, replicas, _ = self.pair()
        chunks = self.exchange(coordinator, replicas, coordinator._request_inputs())
        replicas["a"].stream_engine.bad_hash = True
        with self.assertRaisesRegex(ProtocolError, "must not carry a historical world hash"):
            replicas["a"].receive(chunks[0][1])

    def test_coordinator_waits_for_both_native_frontiers(self):
        coordinator, replicas, _ = self.pair()
        starts = coordinator._request_inputs()
        self.assertEqual(coordinator.receive("a", replicas["a"].receive(starts[0][1])), [])
        self.assertEqual(coordinator.phase, "stream_ready")
        chunks = coordinator.receive("b", replicas["b"].receive(starts[1][1]))
        self.assertEqual(coordinator.receive("a", replicas["a"].receive(chunks[0][1])), [])
        self.assertEqual(coordinator.frame, 240)
        self.assertFalse(coordinator.stream_report()["completed"])
        next_chunks = coordinator.receive("b", replicas["b"].receive(chunks[1][1]))
        self.assertEqual(coordinator.frame, 242)
        self.assertEqual(next_chunks[0][1]["index"], 1)

    def test_identical_duplicate_grants_and_receipts_do_not_execute_twice(self):
        coordinator, replicas, _ = self.pair()
        starts = coordinator._request_inputs()
        ready = replicas["a"].receive(starts[0][1])
        self.assertEqual(replicas["a"].receive(starts[0][1]), ready)
        coordinator.receive("a", ready)
        self.assertEqual(coordinator.receive("a", ready), [])
        chunks = coordinator.receive("b", replicas["b"].receive(starts[1][1]))
        advanced = replicas["a"].receive(chunks[0][1])
        self.assertEqual(replicas["a"].receive(chunks[0][1]), advanced)
        self.assertEqual(replicas["a"].stream_engine.advances, [2])
        self.assertEqual(replicas["a"].receive(starts[0][1]), ready)

    def test_changed_duplicate_halts_and_cannot_execute_again(self):
        coordinator, replicas, _ = self.pair()
        chunks = self.exchange(coordinator, replicas, coordinator._request_inputs())
        replicas["a"].receive(chunks[0][1])
        bad = copy.deepcopy(chunks[0][1])
        bad["steps"] = 1
        with self.assertRaisesRegex(ProtocolError, "conflicting duplicate"):
            replicas["a"].receive(bad)
        self.assertEqual(replicas["a"].stream_engine.advances, [2])

    def test_checkpoint_cannot_be_skipped_or_passed_by_a_larger_grant(self):
        coordinator, replicas, _ = self.pair()
        checkpoints = self.run_until(coordinator, replicas, coordinator._request_inputs(), "stream_checkpoint")
        self.assertEqual(coordinator.frame, 290)
        bad = {"kind": "stream_advance", "epoch": EPOCH, "round": 240, "index": 25,
               "plan_hash": coordinator.plan_hash, "frame": 290, "sim_time_us": coordinator.sim_time_us, "steps": 2}
        with self.assertRaisesRegex(ProtocolError, "next committed empty range"):
            replicas["a"].receive(bad)
        self.assertEqual(len(replicas["a"].stream_engine.advances), 25)

    def test_checkpoint_mismatch_stops_before_next_range(self):
        coordinator, replicas, _ = self.pair()
        checkpoints = self.run_until(coordinator, replicas, coordinator._request_inputs(), "stream_checkpoint")
        replicas["b"].stream_engine.mutate_checkpoint = True
        result = self.exchange(coordinator, replicas, checkpoints)
        self.assertEqual(result[0][1]["kind"], "halt")
        self.assertIn("worlds differ", coordinator.halt_reason)
        self.assertEqual(coordinator.frame, 290)

    def test_pause_and_resume_are_same_checkpoint_with_measured_hold(self):
        coordinator, replicas, _ = self.pair()
        pause = self.run_until(coordinator, replicas, coordinator._request_inputs(), "stream_apply")
        self.assertEqual(pause[0][1]["command_key"], "a:8")
        self.assertEqual(pause[0][1]["frame"], 540)
        hold = self.exchange(coordinator, replicas, pause)
        self.assertEqual(hold[0][1]["kind"], "stream_hold")
        resume = self.exchange(coordinator, replicas, hold)
        self.assertEqual(resume[0][1]["command_key"], "b:6")
        self.assertEqual(resume[0][1]["frame"], 540)
        self.assertEqual(resume[0][1]["sim_time_us"], pause[0][1]["sim_time_us"])
        chunks = self.exchange(coordinator, replicas, resume)
        self.assertEqual(chunks[0][1]["index"], 150)

    def test_short_hold_cannot_release_resume(self):
        coordinator, replicas, _ = self.pair()
        hold = self.run_until(coordinator, replicas, coordinator._request_inputs(), "stream_hold")
        replicas["a"].stream_engine.bad_hold = True
        with self.assertRaisesRegex(ProtocolError, "wait was not measured"):
            replicas["a"].receive(hold[0][1])
        self.assertEqual(len(replicas["a"].engine.commands), 1)

    def test_changed_schedule_wrong_epoch_or_manifest_has_no_engine_effect(self):
        for name, value in (("epoch", "wrong-epoch"), ("plan_hash", "c" * 64),
                            ("manifest_digest", "d" * 64), ("index", 1)):
            coordinator, replicas, _ = self.pair()
            start = coordinator._request_inputs()[0][1]
            start[name] = value
            with self.assertRaises(ProtocolError):
                replicas["a"].receive(start)
            self.assertIsNone(replicas["a"].stream_engine)

    def test_injected_normal_input_is_rejected_while_world_is_historical(self):
        coordinator, replicas, _ = self.pair()
        chunks = self.exchange(coordinator, replicas, coordinator._request_inputs())
        replicas["a"].receive(chunks[0][1])
        with self.assertRaisesRegex(ProtocolError, "normal protocol input"):
            replicas["a"].receive({"kind": "prepare"})

    def test_final_success_requires_both_final_fresh_checkpoints(self):
        coordinator, replicas, _ = self.pair()
        actions = coordinator._request_inputs()
        while not (actions[0][1]["kind"] == "stream_checkpoint" and actions[0][1]["index"] == CHECKPOINTS):
            actions = self.exchange(coordinator, replicas, actions)
        self.assertEqual(coordinator.frame, 840)
        self.assertFalse(coordinator.stream_report()["completed"])
        self.assertEqual(coordinator.receive("a", replicas["a"].receive(actions[0][1])), [])
        self.assertEqual(coordinator.phase, "stream_checkpointed")
        self.assertFalse(coordinator.stream_report()["completed"])
        coordinator.receive("b", replicas["b"].receive(actions[1][1]))
        self.assertTrue(coordinator.stream_report()["completed"])

    def test_base_build_protocol_remains_before_round_240(self):
        coordinator = StreamCoordinator(EPOCH, MANIFEST, CAPS, step_us=STEP_US)
        for number in (0, 1, 239):
            coordinator.round = number
            self.assertEqual(coordinator._request_inputs()[0][1]["kind"], "request_inputs")
            self.assertFalse(coordinator.stream_report()["completed"])

    def test_production_stream_backend_contract_with_explicit_native_lua_fixtures(self):
        # Production StreamEngine and EngineAdapter methods; game/native calls
        # remain fixtures, and the shared artificial clock is not a speed proof.
        from prototype.strict_sync.stream_engine import StreamEngine
        from prototype.tests.test_stream_engine import CommandAdapter
        from prototype.tests.test_engine_timing import Clock
        clock = Clock()
        coordinator, replicas, _ = self.pair()
        for peer in replicas:
            base = CommandAdapter(clock)
            base.native.completed_frame = base.native.request = 240
            base.world["sim_time_us"] = coordinator.sim_time_us
            base.native.before_ms = coordinator.sim_time_us // 1000
            base._last_seq = {"a": 7, "b": 5}
            base._accept_snapshot(base.observation())
            replicas[peer] = StreamReplica(peer, EPOCH, MANIFEST, CAPS, base, lambda _: [],
                frame=240, step_us=STEP_US, stream_engine_factory=StreamEngine)
            replicas[peer].round = 240
        coordinator.state_digest = replicas["a"].engine.state_digest
        with patch("prototype.strict_sync.stream_engine.time.perf_counter", clock.monotonic), \
             patch("prototype.strict_sync.stream_engine.time.monotonic", clock.monotonic), \
             patch("prototype.strict_sync.stream_engine.time.sleep", clock.sleep):
            self.run_until(coordinator, replicas, coordinator._request_inputs())
        self.assertFalse(coordinator.halted, coordinator.halt_reason)
        self.assertTrue(coordinator.stream_report()["completed"])
        self.assertEqual(coordinator.frame, 840)
        for replica in replicas.values():
            self.assertEqual(len(replica.stream_engine.native.permits), 600)
            self.assertTrue(replica.stream_engine.observations_fresh)

    def test_wrong_pause_key_rejected_before_sending_to_engine(self):
        coordinator, replicas, engines = self.pair()
        pause = self.run_until(coordinator, replicas, coordinator._request_inputs(), "stream_apply")
        pause[0][1]["command_key"] = "a:9"
        with self.assertRaisesRegex(ProtocolError, "immutable schedule"):
            replicas["a"].receive(pause[0][1])
        self.assertEqual(engines["a"].commands, [])

    def test_checkpoint_requires_explicit_fresh_observation_flag(self):
        coordinator, replicas, _ = self.pair()
        actions = self.run_until(coordinator, replicas, coordinator._request_inputs(), "stream_checkpoint")
        wrapper = replicas["a"].stream_engine
        original = wrapper.checkpoint
        def stale():
            result = original()
            wrapper.observations_fresh = False
            return result
        wrapper.checkpoint = stale
        with self.assertRaisesRegex(ProtocolError, "historical"):
            replicas["a"].receive(actions[0][1])

    def test_cancellation_after_a_native_step_keeps_progress_frontier_separate(self):
        coordinator, replicas, _ = self.pair()
        chunks = self.exchange(coordinator, replicas, coordinator._request_inputs())
        wrapper = replicas["a"].stream_engine
        def partial(_count):
            wrapper.engine.world["frame"] += 1
            wrapper.engine.world["time"] += STEP_US
            wrapper.observations_fresh = False
            raise ProtocolError("model canceled after one acknowledged step")
        wrapper.advance = partial
        with self.assertRaises(ProtocolError):
            replicas["a"].receive(chunks[0][1])
        progress = replicas["a"].stream_progress()
        self.assertEqual(progress["frame"], 241)
        self.assertEqual(progress["last_observed_frame"], 240)
        self.assertEqual(progress["advanced_steps"], 0)
        report = replicas["a"].stream_report()
        self.assertEqual(report["last_confirmed_native_frame"], 241)
        self.assertEqual(report["last_confirmed_native_sim_time_us"], coordinator.sim_time_us + STEP_US)
        self.assertEqual(report["last_observed_frame"], 240)
        self.assertEqual(report["last_observed_sim_time_us"], coordinator.sim_time_us)
        self.assertEqual(report["native_frontier_scope"], "local_acknowledged_native_frontier")
        self.assertEqual(report["advanced_steps_scope"], "completed_two_step_chunks_only")
        self.assertEqual(report["advanced_steps"], 0)
        host_report = coordinator.stream_report()
        self.assertEqual(host_report["last_confirmed_native_frame"], 240)
        self.assertEqual(host_report["native_frontier_scope"], "both_peers_acknowledged_native_frontier")


if __name__ == "__main__":
    unittest.main()
