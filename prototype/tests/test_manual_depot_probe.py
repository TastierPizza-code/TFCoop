"""Deterministic transport models, not TF2 gameplay or pacing evidence."""
import copy
import tempfile
import unittest
from pathlib import Path

from prototype.strict_sync.core import CAPABILITIES, ProtocolError, digest
from prototype.strict_sync.live_input import InputReader, InputWriter, InputError, create
from prototype.strict_sync.manual_depot_input import validate_command
from prototype.strict_sync.manual_depot_probe import (
    ManualDepotCoordinator, ManualDepotReplica, MANUAL_DEPOT_CAPABILITY,
    _requests, schedule, STEP_US,
)
from prototype.tests import test_paced_live_probe as paced_tests
from prototype.tests.test_paced_live_probe import ScriptedInputs, EPOCH, MANIFEST, pause, END
from prototype.tests.test_stream_probe import BaseWorldModel, StreamWorldModel


def depot(site, rotation=0):
    return {"op": "BUILD_DEPOT", "site": site, "rotation": rotation}


class DepotStreamModel(StreamWorldModel):
    """Explicit independently evolving replicas; preview consults current state."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.previews = []
        self.bad_cost = self.fail_apply = self.mutate_preview = False

    def preview(self, command, key):
        self._stop()
        self.engine._fresh()
        if self.mutate_preview:
            self.engine.world["balance"] -= 1
            self.engine.observed = copy.deepcopy(self.engine.world)
        allowed = str(command["site"]) not in self.engine.world["depots"]
        cost = 1000 + command["site"] if allowed else None
        result = {"allowed": allowed, "reason": "" if allowed else "site_occupied", "cost": cost,
                  "position_mm": [command["site"] * 100000, 100000, 12000], "rotation": command["rotation"],
                  "proposal_digest": digest(command), "state_digest": self.engine.state_digest}
        self.previews.append({"command": copy.deepcopy(command), "key": key, "result": copy.deepcopy(result)})
        return result

    def apply_manual(self, command, key, preview):
        if self.fail_apply:
            raise ProtocolError("model callback failed")
        if self.preview(command, key) != preview or not preview["allowed"]:
            raise ProtocolError("model preflight changed")
        before = self.engine.world["balance"]
        self.engine.world["balance"] -= preview["cost"]
        self.engine.world["depots"] = {**self.engine.world["depots"], str(command["site"]): key}
        self.engine.commands.append((key, copy.deepcopy(command)))
        self.engine.observed = copy.deepcopy(self.engine.world)
        return {"success": True, "state_digest": self.engine.state_digest,
                "result": {**command, "logical_id": key, "cost": preview["cost"] + int(self.bad_cost),
                           "position_mm": preview["position_mm"], "balance_before": before,
                           "balance_after": self.engine.world["balance"], "loan_before": 5000000,
                           "loan_after": 5000000}}


class ManualDepotTests(unittest.TestCase):
    exchange = paced_tests.PacedLiveTests.exchange
    until = paced_tests.PacedLiveTests.until
    complete = paced_tests.PacedLiveTests.complete

    def pair(self, inputs=None):
        inputs = inputs or {}
        caps = tuple(sorted((*CAPABILITIES, MANUAL_DEPOT_CAPABILITY)))
        c = ManualDepotCoordinator(EPOCH, MANIFEST, caps, step_us=STEP_US)
        engines = {peer: BaseWorldModel() for peer in ("a", "b")}
        for engine in engines.values():
            engine.world.update(frame=10, time=200000, depots={}, balance=5000000)
            engine.observed = copy.deepcopy(engine.world)
        sources = {peer: ScriptedInputs(inputs.get(peer, {})) for peer in engines}
        r = {peer: ManualDepotReplica(peer, EPOCH, MANIFEST, caps, engines[peer], lambda _: [],
                frame=10, step_us=STEP_US, stream_engine_factory=DepotStreamModel,
                live_input_source=sources[peer]) for peer in engines}
        c.round = c.frame = 10
        c.sim_time_us = engines["a"].time_us
        c.state_digest = engines["a"].state_digest
        for replica in r.values():
            replica.round = 10
            replica._pause_clock = lambda replica=replica: replica.stream_engine.clock_us / 1000000
        c._pause_clock = lambda: min(engine.stream.clock_us for engine in engines.values()) / 1000000
        return c, r, engines, sources

    def test_complete_running_paused_and_same_batch_collision(self):
        c, r, engines, _ = self.pair({"a": {0: [depot(1)], 1: [pause(True)], 3: [depot(3)], 4: [END]},
                                     "b": {2: [depot(2, 90)], 3: [depot(3, 180)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        report = c.live_report()
        self.assertTrue(report["required_depot_interactions_met"])
        self.assertEqual(report["depot_coverage"]["successful_depots"], 3)
        self.assertEqual(report["depot_coverage"]["occupied_site_rejections"], 1)
        self.assertEqual(len(report["depot_coverage"]["same_batch_shared_sites"]), 1)
        self.assertEqual(len(report["depot_coverage"]["same_batch_conflicts_verified"]), 1)
        self.assertEqual(report["depot_records"], r["a"].live_report()["depot_records"])
        self.assertEqual(report["depot_records"], r["b"].live_report()["depot_records"])
        self.assertEqual(engines["a"].world, engines["b"].world)
        self.assertEqual(engines["a"].world["balance"], 5000000 - 3006)
        self.assertEqual(engines["a"].world["depots"], {"1": "a:7", "2": "b:5", "3": "a:9"})
        rejected = next(outcome for outcome in report["outcomes"] if outcome["status"] == "rejected")
        self.assertEqual(rejected["cost"], 0)
        self.assertEqual(rejected["peer"], "b")

    def test_conflicting_batch_replans_each_command_after_prior_mutation(self):
        c, r, engines, _ = self.pair({"a": {0: [depot(1), depot(1)], 1: [END]},
                                     "b": {0: [depot(1), depot(2)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        outcomes = c.live_report()["outcomes"][:-1]
        self.assertEqual([item["status"] for item in outcomes], ["applied", "rejected", "rejected", "applied"])
        self.assertEqual([key for key, _ in engines["a"].commands], ["a:7", "b:5"])
        self.assertEqual(len(engines["a"].stream.previews), 6)  # Four previews and two apply rechecks.
        previews = c.live_report()["depot_preview_records"]
        self.assertNotEqual(previews[0]["boundary"], previews[1]["boundary"])
        self.assertEqual(previews[1]["boundary"], previews[2]["boundary"])

    def test_empty_input_pacing_has_identical_grants_as_accepted_mode(self):
        runs = []
        for fixture in (paced_tests.PacedLiveTests(), self):
            c, r, _, _ = fixture.pair({"a": {26: [END]}})
            actions = c._request_inputs()
            kinds = []
            while actions:
                kinds.append(actions[0][1]["kind"])
                actions = fixture.exchange(c, r, actions)
            fixture.complete(c, r)
            runs.append(kinds)
        self.assertEqual(*runs)
        self.assertNotIn("live_preview", runs[1])
        self.assertEqual(schedule()["step_us"], 200000)
        self.assertEqual(schedule()["chunk_steps"], 2)
        self.assertEqual(schedule()["checkpoint_steps"], 50)

    def test_preview_requires_both_replies_and_never_authorizes_on_difference(self):
        for field, value in (("cost", 1234), ("proposal_digest", "d" * 64)):
            with self.subTest(field=field):
                c, r, engines, _ = self.pair({"a": {0: [depot(1)]}})
                actions = self.until(c, r, c._request_inputs(), "live_preview")
                a = r["a"].receive(actions[0][1])
                b = r["b"].receive(actions[1][1])
                self.assertEqual(c.receive("a", a), [])
                self.assertFalse(engines["a"].commands)
                b["preview"][field] = value
                self.assertTrue(all(message["kind"] == "halt" for _, message in c.receive("b", b)))
                self.assertTrue(c.halted)
                self.assertEqual(c.frame, 10)
                self.assertFalse(engines["a"].commands)

    def test_apply_cannot_bypass_preview(self):
        c, r, engines, _ = self.pair({"a": {0: [depot(1)]}})
        actions = self.until(c, r, c._request_inputs(), "live_preview")
        message = copy.deepcopy(actions[0][1])
        message["kind"] = "live_apply"
        with self.assertRaisesRegex(ProtocolError, "reordered"):
            r["a"].receive(message)
        self.assertFalse(engines["a"].commands)

    def test_duplicates_never_rebuild_or_reconsume_input(self):
        c, r, engines, sources = self.pair({"a": {0: [depot(1)], 1: [END]}})
        actions = self.until(c, r, c._request_inputs(), "live_preview")
        reply = r["a"].receive(actions[0][1])
        self.assertEqual(reply, r["a"].receive(actions[0][1]))
        self.assertEqual(len(engines["a"].stream.previews), 1)
        c.receive("a", reply)
        actions = c.receive("b", r["b"].receive(actions[1][1]))
        reply = r["a"].receive(actions[0][1])
        self.assertEqual(reply, r["a"].receive(actions[0][1]))
        self.assertEqual(len(engines["a"].commands), 1)
        c.receive("a", reply)
        actions = c.receive("b", r["b"].receive(actions[1][1]))
        self.until(c, r, actions)
        self.complete(c, r)
        self.assertEqual(sources["a"].calls, 2)

    def test_cost_error_or_failed_callback_stops_before_next_advance(self):
        for option in ("bad_cost", "fail_apply"):
            with self.subTest(option=option):
                c, r, engines, _ = self.pair({"a": {0: [depot(1)]}})
                actions = self.until(c, r, c._request_inputs(), "live_apply")
                setattr(engines["b"].stream, option, True)
                with self.assertRaises(ProtocolError):
                    self.exchange(c, r, actions)
                self.assertEqual(c.frame, 10)
                self.assertEqual(engines["a"].stream.advances, [])
                self.assertTrue(r["b"].halted)

    def test_no_next_depot_before_both_callbacks(self):
        c, r, engines, _ = self.pair({"a": {0: [depot(1), depot(2)], 1: [END]}})
        actions = self.until(c, r, c._request_inputs(), "live_apply")
        a = r["a"].receive(actions[0][1])
        self.assertEqual(c.receive("a", a), [])
        self.assertEqual(len(engines["a"].commands), 1)
        self.assertFalse(engines["b"].commands)
        self.assertEqual(c.frame, 10)
        actions = c.receive("b", r["b"].receive(actions[1][1]))
        self.assertEqual(actions[0][1]["kind"], "live_preview")
        self.until(c, r, actions)
        self.complete(c, r)

    def test_rejected_command_duplicate_is_read_only_and_cannot_be_forged_as_apply(self):
        c, r, engines, _ = self.pair({"a": {0: [depot(1), depot(1)], 1: [END]}})
        actions = self.until(c, r, c._request_inputs(), "live_reject")
        before = copy.deepcopy(engines["a"].world)
        reply = r["a"].receive(actions[0][1])
        calls = len(engines["a"].stream.checkpoints)
        self.assertEqual(reply, r["a"].receive(actions[0][1]))
        self.assertEqual(calls, len(engines["a"].stream.checkpoints))
        self.assertEqual(before, engines["a"].world)
        altered = copy.deepcopy(actions[1][1])
        altered["kind"] = "live_apply"
        altered.pop("preview_digest")
        altered["command_key"] = "a:8"
        with self.assertRaisesRegex(ProtocolError, "reordered"):
            r["b"].receive(altered)
        self.assertEqual(len(engines["b"].commands), 1)

    def test_rejection_digest_or_world_mismatch_halts_without_settlement(self):
        for part in ("preview_digest", "state_digest"):
            with self.subTest(part=part):
                c, r, engines, _ = self.pair({"a": {0: [depot(1), depot(1)]}})
                actions = self.until(c, r, c._request_inputs(), "live_reject")
                a, b = r["a"].receive(actions[0][1]), r["b"].receive(actions[1][1])
                self.assertEqual(c.receive("a", a), [])
                b[part] = "f" * 64
                c.receive("b", b)
                self.assertTrue(c.halted)
                self.assertEqual(c.live_progress()["acknowledged_seq"], {"a": 0, "b": 0})
                self.assertEqual(c.frame, 10)

    def test_pause_commands_keep_existing_conflict_rule_then_depots_run_held(self):
        c, r, engines, _ = self.pair({"a": {0: [depot(1), pause(True)], 1: [END]},
                                     "b": {0: [pause(False), depot(2)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        self.assertEqual([command for _, command in engines["a"].commands],
                         [pause(False), pause(True), depot(1), depot(2)])
        self.assertTrue(all(record["before"]["paused"] for record in c.live_report()["depot_records"]))
        self.assertEqual(c.live_report()["coverage"]["conflict_batches"], 1)

    def test_shared_site_already_occupied_has_no_false_winner_conflict_proof(self):
        c, r, _, _ = self.pair({"a": {0: [depot(1)], 1: [depot(1)], 2: [END]}, "b": {1: [depot(1)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        coverage = c.live_report()["depot_coverage"]
        self.assertEqual(len(coverage["same_batch_shared_sites"]), 1)
        self.assertEqual(coverage["same_batch_conflicts_verified"], [])

    def test_readonly_preview_mutation_halts(self):
        c, r, engines, _ = self.pair({"a": {0: [depot(1)]}})
        actions = self.until(c, r, c._request_inputs(), "live_preview")
        engines["a"].stream.mutate_preview = True
        with self.assertRaisesRegex(ProtocolError, "preview changed"):
            r["a"].receive(actions[0][1])
        self.assertFalse(engines["a"].commands)

    def test_later_duplicate_has_no_false_same_batch_claim(self):
        c, r, _, _ = self.pair({"a": {0: [depot(1)], 3: [END]}, "b": {2: [depot(1)]}})
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        coverage = c.live_report()["depot_coverage"]
        self.assertEqual(coverage["occupied_site_rejections"], 1)
        self.assertEqual(coverage["same_batch_shared_sites"], [])
        self.assertFalse(c.live_report()["required_depot_interactions_met"])

    def test_invalid_commands_fail_before_queue_and_network(self):
        cases = [depot(True), depot(0), depot(5), depot(1, True), depot(1, 45),
                 {**depot(1), "x": 10}, {"op": "BUILD_DEPOT"}, {"op": "BUILD_ROAD"}]
        for command in cases:
            with self.subTest(command=command), self.assertRaises(ProtocolError):
                _requests([{"seq": 1, "command": command}], 0)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            create(path, EPOCH, "a")
            old = InputWriter(path, EPOCH, "a")
            with self.assertRaises(InputError):
                old.submit(depot(1))
            writer = InputWriter(path, EPOCH, "a", command_validator=validate_command)
            reader = InputReader(path, EPOCH, "a", command_validator=validate_command)
            writer.submit(depot(2, 270))
            self.assertEqual(reader.take(), [{"seq": 1, "command": depot(2, 270)}])
            self.assertEqual(reader.take(), [])
            with self.assertRaises(InputError):
                InputReader(path, EPOCH, "a")


if __name__ == "__main__":
    unittest.main()
