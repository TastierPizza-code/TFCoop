"""Build observation boundaries only: no Lua, native controller, game or GUI.

These fixtures test transport of declared observations, not whether a TF2
getter exists. Literal Lua tests separately establish how those declarations
are produced from missing, present and invalid fields.
"""
import copy
import json
import unittest

from prototype.strict_sync.build_profile import BUILD_ADVANCE_STEPS, BUILD_ROUNDS, BuildProof
from prototype.strict_sync.engine_mailbox import ENGINE_STEP_US, EngineAdapter, MailboxError
from prototype.tests.test_build_profile import observed_snapshot
from prototype.tests.test_protocol import Harness, command


TIME_PATH = "a:2.CONSTRUCTION.timeBuild"
STOP_PATH = "b:3.TRANSPORT_VEHICLE.stopIndex"


def observation(field="time_build", value=None):
    world = observed_snapshot()
    is_time = field == "time_build"
    world["objects"] = [{"logical_id": "a:2" if is_time else "b:3",
                         "kind": "road" if is_time else "vehicle",
                         "state": {field: copy.deepcopy(value if value is not None else {"available": False})}}]
    # Keep coverage identical when isolating object-field digest changes.
    world["coverage"]["observed_unavailable"] = []
    return world


def accept(world, *, canonical=None):
    # Only exercise the decoder/digest boundary. __init__ would open mailboxes.
    adapter = EngineAdapter.__new__(EngineAdapter)
    adapter._accept_snapshot({"snapshot": world, "canonical_state_json":
                              json.dumps(world if canonical is None else canonical)})
    return adapter


class BuildObservationContractTests(unittest.TestCase):
    def test_time_build_absent_zero_and_decimal_are_preserved_and_distinct(self):
        values = ({"available": False}, {"available": True, "value": "0"},
                  {"available": True, "value": "13.4"})
        digests = []
        for value in values:
            with self.subTest(value=value):
                world = observation(value=value)
                adapter = accept(world)
                self.assertEqual(adapter.snapshot(), world)
                self.assertEqual(adapter.snapshot()["objects"][0]["state"]["time_build"], value)
                digests.append(adapter.state_digest)
        self.assertEqual(len(set(digests)), len(values))

    def test_stop_index_absent_zero_and_integer_are_preserved_and_distinct(self):
        values = ({"available": False}, {"available": True, "value": 0},
                  {"available": True, "value": 1})
        digests = []
        for value in values:
            with self.subTest(value=value):
                world = observation("stop_index", value)
                adapter = accept(world)
                stored = adapter.snapshot()["objects"][0]["state"]["stop_index"]
                self.assertEqual(adapter.snapshot(), world)
                self.assertEqual(stored, value)
                if value["available"]:
                    self.assertIs(type(stored["value"]), int)
                digests.append(adapter.state_digest)
        self.assertEqual(len(set(digests)), len(values))

    def test_observed_unavailable_paths_are_preserved_and_digest_bound(self):
        world = observation()
        digests = []
        for unavailable in ([], [TIME_PATH], [TIME_PATH, STOP_PATH]):
            with self.subTest(unavailable=unavailable):
                world["coverage"]["observed_unavailable"] = unavailable[:]
                adapter = accept(world)
                self.assertEqual(adapter.coverage["observed_unavailable"], unavailable)
                self.assertEqual(adapter.snapshot()["objects"], world["objects"])
                self.assertFalse(adapter.coverage["complete_world"])
                digests.append(adapter.state_digest)
        self.assertEqual(len(set(digests)), 3)

    def test_canonical_json_cannot_hide_presence_or_coverage_changes(self):
        original = observation()
        present = copy.deepcopy(original)
        present["objects"][0]["state"]["time_build"] = {"available": True, "value": "0"}
        changed_coverage = copy.deepcopy(original)
        changed_coverage["coverage"]["observed_unavailable"] = [TIME_PATH]
        for changed in (present, changed_coverage):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(MailboxError, "canonical state differs"):
                    accept(changed, canonical=original)

    def test_missing_mandatory_state_still_fails_with_optional_absence(self):
        world = observation()
        world["coverage"]["observed_unavailable"] = [TIME_PATH]
        for missing in ("b:1:VEHICLE_DEPOT.state unavailable",
                        "b:3:TRANSPORT_VEHICLE.stopIndex unavailable"):
            with self.subTest(missing=missing):
                world["coverage"]["missing"] = [missing]
                with self.assertRaises(MailboxError) as caught:
                    accept(world)
                self.assertIn("unreadable tracked world state", str(caught.exception))
                self.assertIn(missing, str(caught.exception))

    def test_required_coverage_declaration_cannot_be_replaced_by_unavailable_list(self):
        for removed in ("complete_world", "tracked_objects", "missing"):
            with self.subTest(removed=removed):
                world = observation()
                world["coverage"]["observed_unavailable"] = [TIME_PATH]
                del world["coverage"][removed]
                with self.assertRaisesRegex(MailboxError, "actual coverage"):
                    accept(world)
        world = observation()
        world["coverage"]["tracked_objects"] = False
        with self.assertRaisesRegex(MailboxError, "unreadable tracked world state"):
            accept(world)

    def test_peer_presence_or_coverage_mismatch_halts_after_command(self):
        missing = observation()
        present = observation(value={"available": True, "value": "0"})
        other_coverage = copy.deepcopy(missing)
        other_coverage["coverage"]["observed_unavailable"] = [TIME_PATH]
        for other in (present, other_coverage):
            with self.subTest(other=other):
                harness = Harness(paused=True)
                harness.start()
                harness.plan(a=[command(1, "PROBE_ROAD")])
                harness.prepare()
                common = {"round": harness.c.round, "plan_hash": harness.c.plan_hash,
                          "index": 0, "success": True, "result": {"logical_id": "a:1"}}
                self.assertEqual(harness.send("a", "applied", **common,
                                 state_digest=accept(missing).state_digest), [])
                actions = harness.send("b", "applied", **common,
                                       state_digest=accept(other).state_digest)
                self.assertTrue(harness.c.halted)
                self.assertEqual([message["kind"] for _, message in actions], ["halt", "halt"])

    def test_build_proof_with_missing_build_times_remains_explicitly_limited(self):
        proof = BuildProof()
        initial_time = 700000
        sequence = (
            (observed_snapshot(initial_time), 0, None),
            (observed_snapshot(initial_time, 9000, built=True), 5, {"op": "PROBE_VEHICLE"}),
            (observed_snapshot(initial_time + ENGINE_STEP_US, 9000, built=True, position=200), 9, None),
            (observed_snapshot(initial_time + BUILD_ADVANCE_STEPS * ENGINE_STEP_US,
                               9000, built=True, position=2000), BUILD_ROUNDS, None),
        )
        construction_kinds = {"a:2": "road", "a:3": "stop", "b:1": "depot", "b:2": "stop"}
        for world, frame, applied in sequence:
            unavailable = []
            for obj in world["objects"]:
                key = obj["logical_id"]
                if key in construction_kinds:
                    obj["kind"] = construction_kinds[key]
                    obj["state"]["time_build"] = {"available": False}
                    unavailable.append(key + ".CONSTRUCTION.timeBuild")
            world["coverage"]["observed_unavailable"] = sorted(unavailable)
            adapter = accept(world)
            proof.observe(adapter.snapshot(), frame=frame, command=applied,
                          command_key="b:3" if applied else None)
        result = proof.finish(frame=BUILD_ROUNDS, step_us=ENGINE_STEP_US)
        self.assertTrue(result["passed"])
        self.assertIs(result["complete_world_verified"], False)
        self.assertEqual(result["observed_scope"], "constructed_scene_assignment_and_vehicle_movement")
        self.assertIs(proof.last_snapshot["coverage"]["complete_world"], False)
        self.assertEqual(len(proof.last_snapshot["coverage"]["observed_unavailable"]), 4)
        for obj in proof.last_snapshot["objects"]:
            if obj["logical_id"] in construction_kinds:
                self.assertEqual(obj["state"]["time_build"], {"available": False})


if __name__ == "__main__":
    unittest.main()
