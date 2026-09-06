"""Observed-snapshot proof fixtures only; these never run TF2 or price its assets."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from prototype.strict_sync.build_profile import (BUILD_ROUNDS, BuildProof, EXPECTED_SCENE,
                                                SnapshotJournal, build_inputs)
from prototype.strict_sync.core import ProtocolError


def connector_objects(key="a:4"):
    """Declared road-edge observations, not a simulated TF2 construction."""
    return [{"logical_id": f"{key}:link:{index}", "kind": "connector", "state": {
        "node0": f"a:2:edge:{index}:node:0", "node1": f"{owner}:edge:1:node:0",
        "position0": ["0", "0", "0"], "position1": ["20", "0", "0"],
        "tangent0": ["20", "0", "0"], "tangent1": ["20", "0", "0"],
        "street": "fixture-street", "type": 0, "type_index": -1,
        "has_bus": False, "tram_track": 0}}
        for index, owner in enumerate(("b:1", "a:3", "b:2"), 1)]


def observed_snapshot(time_us=700000, money=10000, *, built=False, position=0):
    probe = {"profile": "build_v2", "site": {"x_mm": 1000, "y_mm": 2000, "z_mm": 3000,
             "recipe_id": "fixture-only", "assets": {"road": "fixture-road"}}, "scene": {},
             "connectivity": {"connected": False}}
    objects = []
    if built:
        probe.update(scene=copy.deepcopy(EXPECTED_SCENE), connectivity={"connected": True},
            vehicle={"logical_id": "b:3", "line": "a:5", "in_depot": False, "state": 1,
                     "no_path": False, "position_mm": [position, 0, 0]},
            line={"logical_id": "a:5", "vehicles": ["b:3"], "stops": ["a:3", "b:2"]})
        objects = [{"logical_id": key, "kind": kind, "state": {"fixture": True}}
                   for key, kind in (("a:2", "construction"), ("a:3", "construction"), ("a:5", "line"),
                                     ("b:1", "depot"), ("b:2", "construction"), ("b:3", "vehicle"))]
        objects.extend(connector_objects())
        objects.sort(key=lambda item: item["logical_id"])
    return {"sim_time_us": time_us, "paused": False, "company": {"balance": money, "loan": 0},
            "objects": objects, "probe": probe,
            "coverage": {"complete_world": False, "tracked_objects": True, "missing": []}}


class BuildProofTests(unittest.TestCase):
    def observed_proof(self, *, charge=True):
        proof = BuildProof()
        proof.observe(observed_snapshot(), frame=0)
        money = 9000 if charge else 10000
        proof.observe(observed_snapshot(money=money, built=True), frame=6,
                      command={"op": "PROBE_VEHICLE"}, command_key="b:3")
        proof.observe(observed_snapshot(900000, money, built=True, position=200), frame=10)
        final = observed_snapshot(42900000, money, built=True, position=42200)
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
        self.assertEqual(sequence, {"a": 7, "b": 5})
        self.assertEqual(advances, 211)
        self.assertEqual(identities, {"PROBE_ROAD": "a:2", "PROBE_DEPOT": "b:1", "PROBE_STOP0": "a:3",
            "PROBE_STOP1": "b:2", "PROBE_CONNECT": "a:4", "PROBE_VEHICLE": "b:3",
            "PROBE_LINE": "a:5", "PROBE_ASSIGN": "b:4"})
        modified = build_inputs("a", 1)
        modified[0]["op"] = "tampered"
        self.assertEqual(build_inputs("a", 1), [{"op": "PROBE_ROAD"}])

    def test_only_actual_scene_membership_departure_movement_and_debit_pass(self):
        result = self.observed_proof().finish(frame=240, step_us=200000)
        self.assertTrue(result["passed"])
        self.assertFalse(result["complete_world_verified"])
        self.assertEqual(result["elapsed_sim_time_us"], 42200000)
        self.assertEqual(result["finances"]["balance_delta"], -1000)
        self.assertEqual(result["command_finance_deltas"][0]["balance_delta"], -1000)

    def test_round_count_alone_is_not_build_proof(self):
        proof = BuildProof()
        proof.observe(observed_snapshot(), frame=0)
        proof.observe(observed_snapshot(42900000), frame=240)
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

    def test_connected_flag_cannot_replace_any_missing_connector_observation(self):
        for index in range(1, 4):
            with self.subTest(link=index):
                proof = self.observed_proof()
                proof.last_snapshot["objects"] = [obj for obj in proof.last_snapshot["objects"]
                    if obj["logical_id"] != f"a:4:link:{index}"]
                self.assertTrue(proof.last_snapshot["probe"]["connectivity"]["connected"])
                with self.assertRaisesRegex(ProtocolError, "tracked object states"):
                    proof.finish(frame=240, step_us=200000)

    def test_each_connector_must_have_the_observed_edge_kind_and_available_state(self):
        for index in range(1, 4):
            for change in ({"kind": "construction"}, {"state": None}, {"state": {"unavailable": True}}):
                with self.subTest(link=index, change=change):
                    proof = self.observed_proof()
                    obj = next(item for item in proof.last_snapshot["objects"]
                               if item["logical_id"] == f"a:4:link:{index}")
                    obj.update(change)
                    with self.assertRaises(ProtocolError):
                        proof.finish(frame=240, step_us=200000)

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
