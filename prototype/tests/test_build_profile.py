"""Observed-snapshot proof fixtures only; these never run TF2 or price its assets."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from prototype.strict_sync.build_profile import (BUILD_ROUNDS, BuildProof, EXPECTED_SCENE,
                                                SnapshotJournal, build_inputs)
from prototype.strict_sync.core import ProtocolError


def observed_snapshot(time_us=700000, money=10000, *, built=False, position=0):
    probe = {"profile": "build_v1", "site": {"x_mm": 1000, "y_mm": 2000, "z_mm": 3000,
             "recipe_id": "fixture-only", "assets": {"road": "fixture-road"}}, "scene": {}}
    objects = []
    if built:
        probe.update(scene=copy.deepcopy(EXPECTED_SCENE), connectivity={"connected": True},
            vehicle={"logical_id": "b:3", "line": "a:4", "in_depot": False, "state": 1,
                     "no_path": False, "position_mm": [position, 0, 0]},
            line={"logical_id": "a:4", "vehicles": ["b:3"], "stops": ["a:3", "b:2"]})
        objects = [{"logical_id": key, "kind": kind, "state": {"fixture": True}}
                   for key, kind in (("a:2", "construction"), ("a:3", "construction"), ("a:4", "line"),
                                     ("b:1", "depot"), ("b:2", "construction"), ("b:3", "vehicle"))]
    return {"sim_time_us": time_us, "paused": False, "company": {"balance": money, "loan": 0},
            "objects": objects, "probe": probe,
            "coverage": {"complete_world": False, "tracked_objects": True, "missing": []}}


class BuildProofTests(unittest.TestCase):
    def observed_proof(self, *, charge=True):
        proof = BuildProof()
        proof.observe(observed_snapshot(), frame=0)
        money = 9000 if charge else 10000
        proof.observe(observed_snapshot(money=money, built=True), frame=5,
                      command={"op": "PROBE_VEHICLE"}, command_key="b:3")
        proof.observe(observed_snapshot(900000, money, built=True, position=200), frame=9)
        final = observed_snapshot(43100000, money, built=True, position=42400)
        proof.observe(final, frame=BUILD_ROUNDS)
        return proof

    def test_fixed_recipe_exercises_both_origins_and_expected_pause_duration(self):
        paused, advances = True, 0
        identities, sequence = {}, {"a": 0, "b": 0}
        for number in range(BUILD_ROUNDS):
            for peer in ("a", "b"):
                for command in build_inputs(peer, number):
                    sequence[peer] += 1
                    if command["op"] == "SET_PAUSED":
                        paused = command["value"]
                    else:
                        identity = command["op"] + str(command.get("index", ""))
                        identities[identity] = f"{peer}:{sequence[peer]}"
            advances += not paused
        self.assertEqual(sequence, {"a": 6, "b": 5})
        self.assertEqual(advances, 212)
        self.assertEqual(identities, {"PROBE_ROAD": "a:2", "PROBE_DEPOT": "b:1", "PROBE_STOP0": "a:3",
            "PROBE_STOP1": "b:2", "PROBE_VEHICLE": "b:3", "PROBE_LINE": "a:4", "PROBE_ASSIGN": "b:4"})
        modified = build_inputs("a", 1)
        modified[0]["op"] = "tampered"
        self.assertEqual(build_inputs("a", 1), [{"op": "PROBE_ROAD"}])

    def test_only_actual_scene_membership_departure_movement_and_debit_pass(self):
        result = self.observed_proof().finish(frame=240, step_us=200000)
        self.assertTrue(result["passed"])
        self.assertFalse(result["complete_world_verified"])
        self.assertEqual(result["elapsed_sim_time_us"], 42400000)
        self.assertEqual(result["finances"]["balance_delta"], -1000)
        self.assertEqual(result["command_finance_deltas"][0]["balance_delta"], -1000)

    def test_round_count_alone_is_not_build_proof(self):
        proof = BuildProof()
        proof.observe(observed_snapshot(), frame=0)
        proof.observe(observed_snapshot(43100000), frame=240)
        with self.assertRaisesRegex(ProtocolError, "scene objects"):
            proof.finish(frame=240, step_us=200000)

    def test_unreadable_missing_objects_assignment_and_disconnected_graph_fail(self):
        mutations = [
            lambda s: s["probe"]["scene"].pop("depot"),
            lambda s: s["objects"].pop(),
            lambda s: s["probe"]["vehicle"].update(line="wrong"),
            lambda s: s["probe"]["line"].update(vehicles=[]),
            lambda s: s["probe"]["line"].update(stops=["b:2", "a:3"]),
            lambda s: s["probe"]["vehicle"].update(in_depot=True),
            lambda s: s["probe"]["vehicle"].update(no_path=True),
            lambda s: s["probe"]["connectivity"].update(connected=False),
        ]
        for mutation in mutations:
            proof = self.observed_proof()
            mutation(proof.last_snapshot)
            with self.subTest(mutation=mutation), self.assertRaises(ProtocolError):
                proof.finish(frame=240, step_us=200000)

    def test_purchase_without_observed_debit_cannot_pass(self):
        with self.assertRaisesRegex(ProtocolError, "actual debit"):
            self.observed_proof(charge=False).finish(frame=240, step_us=200000)

    def test_unmoving_vehicle_and_multiple_reads_of_one_time_are_not_motion(self):
        proof = self.observed_proof()
        for sample in proof.samples:
            sample["position_mm"] = [100, 0, 0]
        with self.assertRaisesRegex(ProtocolError, "metre"):
            proof.finish(frame=240, step_us=200000)
        fresh = BuildProof()
        fresh.observe(observed_snapshot(built=True), frame=0)
        fresh.observe(observed_snapshot(built=True, position=10000), frame=0)
        self.assertEqual(len(fresh.samples), 1)

    def test_chosen_site_and_exact_observed_duration_cannot_change(self):
        proof = self.observed_proof()
        with self.assertRaisesRegex(ProtocolError, "simulation time"):
            proof.finish(frame=240, step_us=100000)
        modified = copy.deepcopy(proof.last_snapshot)
        modified["probe"]["site"]["x_mm"] += 1
        with self.assertRaisesRegex(ProtocolError, "site"):
            proof.observe(modified, frame=240)

    def test_journal_keeps_failed_phase_and_last_observation_without_replacing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "peer-journal.jsonl"
            journal = SnapshotJournal(path)
            journal.append("applied", frame=2, number=2, snapshot=observed_snapshot(), command={"op": "PROBE_DEPOT"})
            journal.append("failed", frame=2, number=2, snapshot=observed_snapshot(), reason="actual proposal collision")
            journal.close()
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["phase"], "Depot bauen")
            self.assertEqual(records[1]["reason"], "actual proposal collision")
            self.assertEqual(records[1]["snapshot_scope"], "last_observed")
            with self.assertRaises(FileExistsError):
                SnapshotJournal(path)


if __name__ == "__main__":
    unittest.main()
