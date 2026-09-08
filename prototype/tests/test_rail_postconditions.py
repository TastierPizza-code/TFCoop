"""Adversarial T2 result readbacks. Fixtures do not establish TF2 rail support."""
import copy
import unittest

from prototype.strict_sync.core import digest, ProtocolError
from prototype.strict_sync.engine_mailbox import MailboxError
from prototype.strict_sync.rail_catalog import STEPS, get_step
from prototype.strict_sync.rail_engine import RailEngineAdapter, VEHICLE_NAME_CONTRACT
from prototype.strict_sync.rail_input import validate_action_receipt, validate_command
from prototype.strict_sync import guided_probe, rail_probe


def step_for(action):
    return next(step for step in STEPS if step["action"] == action)


def root_snapshot():
    registry = {key: "" for key in ("station_a", "station_b", "depot", "connectors", "signal_a", "signal_b",
                                       "waypoint", "train", "clone", "line")}
    registry.update(contract="guided_rail_v1", vehicle_name_contract=VEHICLE_NAME_CONTRACT,
                    capabilities={"ready": True, "missing": []})
    return {"company": {"balance": 1000000, "loan": 5000000}, "paused": True,
            "objects": [], "probe": {"rail_suite": registry}}


def bind(snapshot, field, key, kind, state):
    snapshot["probe"]["rail_suite"][field] = key
    snapshot["objects"].append({"kind": kind, "logical_id": key, "state": copy.deepcopy(state)})


def objects(snapshot):
    return {obj["logical_id"]: obj for obj in snapshot["objects"]}


def part(model="locomotive.mdl", *, age="1000", maintenance="1"):
    return {"model": model, "purchase_time": age, "maintenance": maintenance, "target_maintenance": "0",
            "color": ["-1", "-1", "-1"], "logo": "", "reversed": False,
            "load_config": [0], "auto_load_config": ["1"]}


def train_state(parts=2):
    return {"name": {"mode": "automatic"}, "carrier": 1, "position": "in_depot", "depot": "depot:depot",
            "config": {"groups": [parts], "vehicles": [part()] + [part("coach.mdl") for _ in range(parts - 1)]},
            "line": "", "state": 0, "user_stopped": False, "no_path": False,
            "stop_index": {"available": True, "value": 0}}


def train_snapshot(parts=2):
    snap = root_snapshot()
    bind(snap, "depot", "depot", "rail_depot", {"fixed": "unchanged"})
    bind(snap, "train", "train", "rail_train", train_state(parts))
    return snap


def observed_effect(before, after, target, *, kind="callback", absent=False):
    old, new = objects(before), objects(after)
    return {"balance_before": before["company"]["balance"], "balance_after": after["company"]["balance"],
            "loan_before": before["company"]["loan"], "loan_after": after["company"]["loan"],
            "target": target, "kind": kind, "created": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "observed": {"entity_absent": True} if absent else copy.deepcopy(new[target]["state"])}


def preview(step, before, **expected):
    return {"allowed": True, "reason": "", "step": step["step"], "action": step["action"],
            "state_digest": digest(before), "observation": {"company": copy.deepcopy(before["company"]),
                "expected": {"required_effect": step["action"], **expected}}}


class RailPostconditionTests(unittest.TestCase):
    def check(self, action, before, after, target, *, effect=None, absent=False, **expected):
        step = step_for(action)
        adapter = object.__new__(RailEngineAdapter)
        eff = effect or observed_effect(before, after, target, kind="observation" if step["read_only"] else "callback", absent=absent)
        adapter._check_observation(step["command"], eff, before, after, preview(step, before, **expected))

    def test_maintenance_only_changes_target_on_every_part(self):
        before = train_snapshot()
        after = copy.deepcopy(before)
        for item in objects(after)["train"]["state"]["config"]["vehicles"]:
            item["target_maintenance"] = "1"
        self.check("TRAIN_MAINTENANCE", before, after, "train")
        corrupt = copy.deepcopy(after)
        objects(corrupt)["train"]["state"]["config"]["vehicles"][1]["color"] = ["1", "0", "0"]
        with self.assertRaisesRegex(MailboxError, "another actual train configuration"):
            self.check("TRAIN_MAINTENANCE", before, corrupt, "train")
        missing = copy.deepcopy(after)
        objects(missing)["train"]["state"]["config"]["vehicles"][1]["target_maintenance"] = "0"
        with self.assertRaisesRegex(MailboxError, "every part"):
            self.check("TRAIN_MAINTENANCE", before, missing, "train")

    def test_clone_matches_actual_source_configuration_but_has_new_purchase_age(self):
        before = train_snapshot(3)
        after = copy.deepcopy(before)
        clone = train_state(3)
        for item in clone["config"]["vehicles"]:
            item["purchase_time"] = "2000"
        bind(after, "clone", "clone", "rail_train", clone)
        after["company"]["balance"] -= 5000
        models = ["locomotive.mdl", "coach.mdl", "coach.mdl"]
        self.check("CLONE_TRAIN", before, after, "clone", models=models)
        altered = copy.deepcopy(after)
        objects(altered)["clone"]["state"]["config"]["vehicles"][1]["load_config"] = [1]
        with self.assertRaisesRegex(MailboxError, "actual approved source configuration"):
            self.check("CLONE_TRAIN", before, altered, "clone", models=models)

    def test_replace_requires_exact_new_three_part_configuration_and_generation(self):
        before = train_snapshot(2)
        after = copy.deepcopy(before)
        after["objects"] = [obj for obj in after["objects"] if obj["logical_id"] != "train"]
        bind(after, "train", "replacement", "rail_train", train_state(3))
        models = ["locomotive.mdl", "coach.mdl", "coach.mdl"]
        self.check("REPLACE_TRAIN", before, after, "replacement", models=models)
        broken = copy.deepcopy(after)
        objects(broken)["replacement"]["state"]["config"]["vehicles"].pop()
        with self.assertRaisesRegex(MailboxError, "composition"):
            self.check("REPLACE_TRAIN", before, broken, "replacement", models=models)

    def network_snapshot(self):
        snap = root_snapshot()
        arms = [{"slot": slot, "edge": "generation-" + slot, "node0": "port-" + slot, "node1": "network",
                 "position0": ["0", "0", "0"], "position1": ["1", "0", "0"],
                 "tangent0": ["1", "0", "0"], "tangent1": ["1", "0", "0"],
                 "track": "standard.lua", "catenary": False, "objects": []} for slot in ("a", "b", "depot")]
        bind(snap, "connectors", "network", "rail_network", {"position": ["1", "0", "0"], "arms": arms, "connected": True})
        return snap

    def add_marker(self, snap):
        after = copy.deepcopy(snap)
        arm = objects(after)["network"]["state"]["arms"][0]
        arm["edge"] = "generation-a-next"
        arm["objects"] = [{"logical_id": "signal", "kind": "signal"}]
        bind(after, "signal_a", "signal", "rail_marker", {"edge": arm["edge"], "model": "signal.mdl",
            "signal_type": 0, "position": ["0.5", "0", "0"], "direction": False, "name": "Signal A"})
        return after

    def test_marker_rebuilds_only_owned_arm_and_never_moves_rail_geometry(self):
        before = self.network_snapshot()
        after = self.add_marker(before)
        self.check("ADD_SIGNAL_A", before, after, "signal")
        for changed_arm in (0, 1):
            broken = copy.deepcopy(after)
            objects(broken)["network"]["state"]["arms"][changed_arm]["position1"] = ["2", "0", "0"]
            with self.assertRaisesRegex(MailboxError, "geometry or endpoints"):
                self.check("ADD_SIGNAL_A", before, broken, "signal")
        broken = copy.deepcopy(after)
        objects(broken)["network"]["state"]["arms"][1]["edge"] = "unrelated-generation"
        with self.assertRaisesRegex(MailboxError, "exactly its single owned arm"):
            self.check("ADD_SIGNAL_A", before, broken, "signal")

    def test_successful_callback_cannot_hide_wrong_target_component_or_company(self):
        before = train_snapshot()
        after = copy.deepcopy(before)
        objects(after)["train"]["state"]["name"] = {"mode": "explicit", "value": "Expected"}
        eff = observed_effect(before, after, "train")
        eff["observed"]["name"]["value"] = "Invented"
        with self.assertRaisesRegex(MailboxError, "independent component"):
            self.check("RENAME_TRAIN", before, after, "train", effect=eff, name="Expected")
        eff = observed_effect(before, after, "train")
        eff["balance_after"] -= 1
        with self.assertRaisesRegex(MailboxError, "independently observed company"):
            self.check("RENAME_TRAIN", before, after, "train", effect=eff, name="Expected")

    def test_reverse_cannot_pass_on_successful_but_unchanged_readback(self):
        before = train_snapshot()
        with self.assertRaisesRegex(MailboxError, "no actual observed route"):
            self.check("REVERSE_TRAIN", before, copy.deepcopy(before), "train")

    def test_station_removal_cannot_silently_drop_a_retained_property_or_another_child(self):
        before = root_snapshot()
        bind(before, "station_a", "station-a", "rail_station", {"modules": {"1": "platform.module"}, "frozen_track": ["edge-a"]})
        bind(before, "station_b", "station-b", "rail_station", {"modules": {"1": "platform.module"}, "frozen_track": ["edge-b"]})
        before["objects"].append({"logical_id": "station-b:station", "kind": "rail_station_child", "state": {"terminal": 0}})
        after = copy.deepcopy(before)
        after["objects"] = [item for item in after["objects"] if not item["logical_id"].startswith("station-b")]
        after["probe"]["rail_suite"]["station_b"] = ""
        self.check("REMOVE_STATION_B", before, after, "station-b", absent=True)
        altered = copy.deepcopy(after)
        objects(altered)["station-a"]["state"].pop("frozen_track")
        with self.assertRaisesRegex(MailboxError, "unrelated object or property"):
            self.check("REMOVE_STATION_B", before, altered, "station-b", absent=True)

    def test_readonly_depot_check_never_may_mutate_tracked_world(self):
        before = train_snapshot()
        self.check("VERIFY_DEPOT", before, copy.deepcopy(before), "train")
        after = copy.deepcopy(before)
        after["company"]["balance"] -= 1
        with self.assertRaisesRegex(MailboxError, "readiness observation changed"):
            self.check("VERIFY_DEPOT", before, after, "train")

    def test_t1_and_t2_contracts_coexist_without_rewriting_each_other(self):
        first = guided_probe.schedule()
        second = rail_probe.schedule()
        self.assertEqual(first, guided_probe.schedule())
        self.assertEqual(first["input_ops"], ["GUIDED_ACTION"])
        self.assertEqual(len(first["catalogue"]["steps"]), 26)
        self.assertEqual(second["input_ops"], ["RAIL_ACTION"])
        self.assertEqual(len(second["catalogue"]["steps"]), 37)
        with self.assertRaises(ProtocolError):
            validate_command({"op": "GUIDED_ACTION", "step": 1})


if __name__ == "__main__":
    unittest.main()
