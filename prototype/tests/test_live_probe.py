"""Headless dynamic-input models; no native TF2, desktop or real-time claims."""
import copy
import json
import unittest
from unittest.mock import patch

from prototype.strict_sync.core import CAPABILITIES, ProtocolError, digest
from prototype.strict_sync.live_probe import (
    LiveCoordinator, LiveReplica, LIVE_CAPABILITY, LIVE_WORLD_RECEIPTS,
    STEP_US, POLL_MS, LONG_PAUSE_MS, MAX_BATCH_REQUESTS, _requests,
    _hold_metrics, _NATIVE_FIELDS, MAX_PAUSE_RECEIPT_BYTES, MAX_CYCLES, MAX_REQUESTS,
)
from prototype.tests.test_stream_probe import BaseWorldModel, StreamWorldModel

EPOCH = "live-model-epoch"
MANIFEST = "c" * 64
CAPS = tuple(sorted((*CAPABILITIES, LIVE_CAPABILITY)))


def pause(value):
    return {"op": "SET_PAUSED", "value": value}


END = {"op": "END_TEST"}


class ScriptedInputs:
    def __init__(self, cycles):
        self.cycles = cycles
        self.calls = 0
        self.seq = 0

    def __call__(self):
        result = []
        for command in self.cycles.get(self.calls, []):
            self.seq += 1
            result.append({"seq": self.seq, "command": copy.deepcopy(command)})
        self.calls += 1
        return result


class LiveTests(unittest.TestCase):
    def pair(self, inputs=None, **coordinator_options):
        inputs = inputs or {}
        coordinator = LiveCoordinator(EPOCH, MANIFEST, CAPS, step_us=STEP_US, **coordinator_options)
        engines = {peer: BaseWorldModel() for peer in ("a", "b")}
        sources = {peer: ScriptedInputs(inputs.get(peer, {})) for peer in engines}
        replicas = {peer: LiveReplica(peer, EPOCH, MANIFEST, CAPS, engines[peer], lambda _: [],
                    frame=240, step_us=STEP_US, stream_engine_factory=StreamWorldModel,
                    live_input_source=sources[peer]) for peer in engines}
        # Explicit post-build model fixture; actual build and Lua are covered separately.
        coordinator.round = coordinator.frame = 240
        coordinator.sim_time_us = engines["a"].time_us
        coordinator.state_digest = engines["a"].state_digest
        for replica in replicas.values():
            replica.round = 240
        # Deterministic monotonic model time, advanced by the wrapper. No real
        # sleeping or elapsed TF2 runtime is claimed by these protocol fixtures.
        coordinator._pause_clock = lambda: min(engine.stream.clock_us for engine in engines.values()) / 1000000
        for replica in replicas.values():
            replica._pause_clock = lambda replica=replica: replica.stream_engine.clock_us / 1000000
        return coordinator, replicas, engines, sources

    def exchange(self, coordinator, replicas, actions):
        replies = [(peer, replicas[peer].receive(message)) for peer, message in actions]
        result = []
        for peer, reply in replies:
            result.extend(coordinator.receive(peer, reply))
        return result

    def until(self, coordinator, replicas, actions, kind=None):
        for _ in range(11000):
            if not actions or coordinator.halted or kind and actions[0][1]["kind"] == kind:
                return actions
            actions = self.exchange(coordinator, replicas, actions)
        self.fail("model exceeded bounded operation schedule")

    def complete(self, coordinator, replicas):
        self.assertFalse(coordinator.halted, coordinator.halt_reason)
        self.assertEqual(coordinator.phase, "inputs")
        self.assertTrue(coordinator.live_report()["completed"])
        for replica in replicas.values():
            self.assertTrue(replica.live_report()["completed"])
            self.assertIsNone(replica.receive({"kind": "complete", "epoch": EPOCH, "round": 240,
                "frame": coordinator.frame, "sim_time_us": coordinator.sim_time_us,
                "state_digest": coordinator.state_digest}))
            self.assertTrue(replica.finished)

    def test_real_request_flow_long_pause_conflict_both_players_and_end(self):
        c, r, engines, sources = self.pair({
            "a": {0: [pause(True)], 177: [pause(False)], 178: [pause(False)], 179: [pause(False)]},
            "b": {175: [pause(False)], 176: [pause(True)], 178: [pause(True)], 185: [END]},
        })
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        report = c.live_report()
        self.assertTrue(report["required_interactions_met"])
        self.assertEqual(report["coverage"]["conflict_batches"], 1)
        self.assertEqual(report["coverage"]["longest_measured_pause_ms"], {"a": 35000, "b": 35000})
        self.assertEqual(c.live_progress()["acknowledged_seq"], {"a": 4, "b": 4})
        self.assertEqual(engines["a"].commands, engines["b"].commands)
        self.assertEqual(len(engines["a"].commands), 7)
        self.assertEqual(sources["a"].calls, 186)
        self.assertTrue(all(record["boundary"]["paused"] for record in report["hold_records"]))
        self.assertFalse(report["native_ui_input_capture"])
        self.assertFalse(report["full_world_verified"])

    def test_early_end_is_completed_but_missing_coverage_is_not_green(self):
        c, r, _, _ = self.pair({"b": {0: [END]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        self.assertEqual(c.frame, 240)
        self.assertFalse(c.live_report()["required_interactions_met"])
        self.assertEqual(len(c.live_report()["command_records"]), 0)

    def test_optional_conflict_is_not_required_for_successful_pause_coverage(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)], 177: [pause(False)], 180: [END]},
                               "b": {175: [pause(False)], 176: [pause(True)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        self.assertTrue(c.live_report()["required_interactions_met"])
        self.assertEqual(c.live_report()["coverage"]["conflict_batches"], 0)

    def test_after_end_all_earlier_commands_in_same_batch_are_applied(self):
        c, r, engines, _ = self.pair({"a": {0: [pause(True), END]}, "b": {0: [pause(False)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        self.assertEqual([command for _, command in engines["a"].commands], [pause(False), pause(True)])
        self.assertTrue(c.paused)
        self.assertEqual(len(c.live_report()["outcomes"]), 3)

    def test_single_player_rapid_opposites_pause_wins_but_not_cross_peer_coverage(self):
        c, r, engines, _ = self.pair({"a": {0: [pause(True), pause(False)], 2: [END]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        self.assertTrue(c.paused)
        self.assertEqual([command for _, command in engines["a"].commands], [pause(False), pause(True)])
        self.assertEqual(c.live_report()["coverage"]["conflict_batches"], 0)

    def test_no_requests_advances_only_until_explicit_limit_halt(self):
        with patch("prototype.strict_sync.live_probe.MAX_STEPS", 4):
            c, r, _, _ = self.pair()
            self.until(c, r, c._request_inputs())
        self.assertTrue(c.halted)
        self.assertIn("step limit", c.halt_reason)
        self.assertEqual(c.frame, 244)
        self.assertFalse(c.live_report()["completed"])

    def test_cycle_limit_is_terminal_not_auto_success(self):
        with patch("prototype.strict_sync.live_probe.MAX_CYCLES", 2):
            c, r, _, _ = self.pair({"a": {0: [pause(True)]}})
            self.until(c, r, c._request_inputs())
        self.assertTrue(c.halted)
        self.assertIn("cycle limit", c.halt_reason)
        self.assertFalse(c.live_report()["completed"])

    def test_source_is_sealed_once_duplicate_poll_and_command_never_reexecutes(self):
        c, r, engines, sources = self.pair({"a": {0: [pause(True)], 1: [END]}})
        poll = self.exchange(c, r, c._request_inputs())
        response = r["a"].receive(poll[0][1])
        self.assertEqual(r["a"].receive(poll[0][1]), response)
        self.assertEqual(sources["a"].calls, 1)
        self.assertEqual(c.receive("a", response), [])
        self.assertEqual(c.receive("a", response), [])
        actions = c.receive("b", r["b"].receive(poll[1][1]))
        apply = self.until(c, r, actions, "live_apply")
        reply = r["a"].receive(apply[0][1])
        self.assertEqual(r["a"].receive(apply[0][1]), reply)
        self.assertEqual(len(engines["a"].commands), 1)
        self.assertEqual(r["a"].receive(poll[0][1]), response)
        c.receive("a", reply)
        actions = c.receive("b", r["b"].receive(apply[1][1]))
        self.until(c, r, actions)
        self.complete(c, r)

    def test_identical_requests_are_not_toggle_and_each_real_callback_is_recorded(self):
        c, r, engines, _ = self.pair({"a": {0: [pause(True)], 2: [END]}, "b": {0: [pause(True)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        self.assertTrue(c.paused)
        self.assertEqual(len(engines["a"].commands), 2)
        self.assertEqual([item["changed_pause"] for item in c.live_report()["outcomes"][:2]], [True, False])

    def test_local_apply_is_not_joint_acknowledgement_or_common_pause(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)], 1: [END]}})
        apply = self.until(c, r, c._request_inputs(), "live_apply")
        reply = r["a"].receive(apply[0][1])
        self.assertTrue(r["a"].live_progress()["paused"])
        self.assertFalse(r["a"].live_progress()["confirmed_paused"])
        self.assertEqual(r["a"].live_progress()["acknowledged_seq"]["a"], 0)
        self.assertEqual(c.receive("a", reply), [])
        self.assertFalse(c.live_progress()["confirmed_paused"])
        settle = c.receive("b", r["b"].receive(apply[1][1]))
        self.assertEqual(settle[0][1]["kind"], "live_settle")
        self.assertTrue(c.live_progress()["confirmed_paused"])
        self.exchange(c, r, settle)
        self.assertTrue(r["a"].live_progress()["confirmed_paused"])
        self.assertEqual(r["a"].live_progress()["acknowledged_seq"]["a"], 1)

    def test_native_only_reply_and_partial_frontier_do_not_claim_fresh_world(self):
        c, r, _, _ = self.pair({"a": {1: [END]}})
        advance = self.until(c, r, c._request_inputs(), "live_advance")
        reply = r["a"].receive(advance[0][1])
        self.assertNotIn("state_digest", reply)
        self.assertNotIn(reply["kind"], LIVE_WORLD_RECEIPTS)
        self.assertEqual(r["a"].live_progress()["last_observed_frame"], 240)
        self.assertEqual(r["a"].live_report()["last_confirmed_native_frame"], 242)
        self.assertEqual(c.live_report()["last_confirmed_native_frame"], 240)
        self.assertEqual(c.receive("a", reply), [])
        self.assertEqual(c.frame, 240)

    def test_checkpoint_every_fifty_steps_and_before_each_input_batch(self):
        c, r, _, _ = self.pair({"b": {27: [END]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        checkpoints = c.live_report()["checkpoint_records"]
        self.assertEqual([(item["reason"], item["boundary"]["frame"]) for item in checkpoints],
                         [("periodic", 290), ("inputs", 294)])

    def test_peer_cannot_advance_before_pending_own_input_is_committed(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)]}})
        checkpoint = self.until(c, r, c._request_inputs(), "live_checkpoint")
        fake = {k: v for k, v in checkpoint[0][1].items() if k != "reason"}
        fake.update(kind="live_advance", steps=2)
        with self.assertRaisesRegex(ProtocolError, "reordered"):
            r["a"].receive(fake)
        self.assertEqual(r["a"].stream_engine.advances, [])

    def test_host_cannot_change_sealed_input_even_with_recomputed_batch_hash(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)]}})
        commit = self.until(c, r, c._request_inputs(), "live_commit")
        fake = copy.deepcopy(commit[0][1])
        fake["requests"]["a"][0]["command"]["value"] = False
        fake["batch_hash"] = digest({k: fake[k] for k in ("cycle", "requests", "frame", "sim_time_us", "paused", "state_digest")})
        with self.assertRaisesRegex(ProtocolError, "locally sealed"):
            r["a"].receive(fake)

    def test_fresh_checkpoint_difference_prevents_command(self):
        c, r, engines, _ = self.pair({"a": {1: [pause(True)]}})
        checkpoint = self.until(c, r, c._request_inputs(), "live_checkpoint")
        r["b"].stream_engine.mutate_checkpoint = True
        self.exchange(c, r, checkpoint)
        self.assertTrue(c.halted)
        self.assertIn("worlds differ", c.halt_reason)
        self.assertEqual(engines["a"].commands, [])

    def test_callback_difference_prevents_settlement_and_next_grant(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)]}})
        apply = self.until(c, r, c._request_inputs(), "live_apply")
        replies = [(peer, r[peer].receive(message)) for peer, message in apply]
        replies[1][1]["receipt"]["result"] = {"different": True}
        self.assertEqual(c.receive(*replies[0]), [])
        c.receive(*replies[1])
        self.assertTrue(c.halted)
        self.assertIn("callback results differ", c.halt_reason)
        self.assertEqual(c.live_progress()["acknowledged_seq"]["a"], 0)
        self.assertFalse(c.live_progress()["confirmed_paused"])

    def test_changed_world_during_paused_heartbeat_is_terminal(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)]}})
        hold = self.until(c, r, c._request_inputs(), "live_hold")
        r["a"].stream_engine.mutate_checkpoint = True
        with self.assertRaisesRegex(ProtocolError, "world changed"):
            r["a"].receive(hold[0][1])

    def test_missing_or_short_hold_measurement_cannot_prove_long_pause(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)]}})
        hold = self.until(c, r, c._request_inputs(), "live_hold")
        r["a"].stream_engine.bad_hold = True
        with self.assertRaises(ProtocolError):
            r["a"].receive(hold[0][1])
        self.assertFalse(c.live_report()["coverage"]["long_pause_met"])

    def test_continuous_pause_counts_between_heartbeat_network_and_ipc_waits(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)], 1: [END]}})
        clock = [0.0]
        c._pause_clock = lambda: clock[0]
        for replica in r.values():
            replica._pause_clock = lambda: clock[0]
        hold = self.until(c, r, c._request_inputs(), "live_hold")
        clock[0] = 45.0  # Modeled waiting around the same held native boundary.
        self.until(c, r, hold)
        self.complete(c, r)
        report = c.live_report()
        self.assertTrue(report["coverage"]["long_pause_met"])
        self.assertEqual(report["coverage"]["longest_measured_pause_ms"], {"a": 45000, "b": 45000})
        self.assertEqual(report["hold_records"][0]["peers"]["a"]["actual_delay_ms"], 200)

    def test_separate_short_pauses_are_not_added_into_long_pause_coverage(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)], 1: [pause(False)], 2: [pause(True)],
                                      3: [pause(False)], 4: [END]}})
        clock = [0.0]
        c._pause_clock = lambda: clock[0]
        for replica in r.values():
            replica._pause_clock = lambda: clock[0]
        actions = c._request_inputs()
        while actions:
            if actions[0][1]["kind"] == "live_hold":
                clock[0] += 20
            actions = self.exchange(c, r, actions)
        self.complete(c, r)
        self.assertFalse(c.live_report()["coverage"]["long_pause_met"])
        self.assertEqual(c.live_report()["coverage"]["longest_measured_pause_ms"], {"a": 20000, "b": 20000})

    def test_heartbeat_resets_phase_deadlines_but_missing_peer_times_out(self):
        now = [0.0]
        c, r, _, _ = self.pair({"a": {0: [pause(True)], 180: [END]}}, clock=lambda: now[0], timeout_s=1)
        actions = c._request_inputs()
        while actions:
            now[0] += .2
            actions = self.exchange(c, r, actions)
        self.complete(c, r)
        self.assertGreater(now[0], 35)
        c, r, _, _ = self.pair(clock=lambda: now[0], timeout_s=1)
        ready = c._request_inputs()
        c.receive("a", r["a"].receive(ready[0][1]))
        now[0] += 2
        c.tick()
        self.assertTrue(c.halted)

    def test_end_requires_both_final_fresh_receipts(self):
        c, r, _, _ = self.pair({"b": {0: [END]}})
        finish = self.until(c, r, c._request_inputs(), "live_finish")
        self.assertEqual(c.receive("a", r["a"].receive(finish[0][1])), [])
        self.assertFalse(c.live_report()["completed"])
        self.assertNotEqual(c.phase, "inputs")
        c.receive("b", r["b"].receive(finish[1][1]))
        self.complete(c, r)

    def test_wrong_plan_reordered_and_conflicting_duplicates_fail_closed(self):
        for change in (lambda m: m.update(plan_hash="d" * 64), lambda m: m.update(index=99)):
            with self.subTest(change=change):
                c, r, _, _ = self.pair()
                start = c._request_inputs()[0][1]
                change(start)
                with self.assertRaises(ProtocolError):
                    r["a"].receive(start)
        c, r, _, _ = self.pair()
        poll = self.exchange(c, r, c._request_inputs())[0][1]
        r["a"].receive(poll)
        changed = {**poll, "cycle": 1}
        with self.assertRaisesRegex(ProtocolError, "conflicting duplicate"):
            r["a"].receive(changed)

    def test_request_schema_bounds_bool_sequences_and_terminal_end(self):
        invalid = [None, [{"seq": True, "command": pause(True)}], [{"seq": 2, "command": pause(True)}],
                   [{"seq": 1, "command": {"op": "SET_PAUSED", "value": 1}}],
                   [{"seq": 1, "command": END}, {"seq": 2, "command": pause(False)}],
                   [{"seq": i + 1, "command": pause(True)} for i in range(MAX_BATCH_REQUESTS + 1)]]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                _requests(value, 0)
        with self.assertRaises(ProtocolError):
            _requests([{"seq": 129, "command": END}], 128)

    def test_maximum_retained_report_stays_below_live_reader_limit(self):
        # Conservative serialized upper bound, deliberately combining maxima that
        # cannot coexist in one run:2048 cycles of larger record type PLUS1500
        # chunks PLUS256 commands/batches. The actual cycle limit is stricter.
        c, r, _, _ = self.pair({"a": {1: [pause(True)], 2: [END]}})
        self.until(c, r, c._request_inputs())
        report = c.live_report()
        maximum = (1 << 53) - 1
        hold = copy.deepcopy(report["hold_records"][0])
        for metrics in hold["peers"].values():
            for name in ("native_before", "native_after"):
                metrics[name] = {key: maximum for key in _NATIVE_FIELDS}
            for name in ("actual_delay_ms", "duration_ms"):
                metrics[name] = maximum
            metrics["counter_deltas"] = {key: maximum for key in ("hold_calls", "outer_calls", "updated_ms")}
            _hold_metrics(metrics)
        report["hold_records"] = [hold] * MAX_CYCLES
        # Actual grant and hold records share a2048 cycle budget. We nevertheless
        # add all1500 chunks to leave room for final driver metadata and journals.
        report["chunk_records"] *= 1500
        command = copy.deepcopy(report["command_records"][0])
        command["receipt"]["result"] = {"padding": "x" * (MAX_PAUSE_RECEIPT_BYTES - 160)}
        report["command_records"] = [command] * (MAX_REQUESTS * 2)
        report["input_batches"] *= MAX_REQUESTS
        report["outcomes"] *= MAX_REQUESTS
        size = len(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
        self.assertLess(size, 16 * 1024 * 1024)

    def test_unknown_native_hold_fields_are_rejected(self):
        c, r, _, _ = self.pair({"a": {0: [pause(True)], 1: [END]}})
        hold = self.until(c, r, c._request_inputs(), "live_hold")
        reply = r["a"].receive(hold[0][1])
        reply["metrics"]["native_before"] = {"unexpected": 1}
        c.receive("a", reply)
        self.assertTrue(c.halted)
        self.assertIn("unknown native", c.halt_reason)

    def test_stop_during_native_chunk_keeps_partial_ack_frontier_separate(self):
        c, r, _, _ = self.pair()
        advance = self.until(c, r, c._request_inputs(), "live_advance")
        wrapper = r["a"].stream_engine
        original = wrapper.advance
        def partial(_):
            original(1)
            raise ProtocolError("model local stop after one acknowledged permit")
        wrapper.advance = partial
        with self.assertRaisesRegex(ProtocolError, "local stop"):
            r["a"].receive(advance[0][1])
        report = r["a"].live_report()
        self.assertEqual(report["last_confirmed_native_frame"], 241)
        self.assertEqual(report["last_observed_frame"], 240)
        self.assertEqual(report["progress"]["advanced_steps"], 0)
        self.assertFalse(report["completed"])


if __name__ == "__main__":
    unittest.main()
