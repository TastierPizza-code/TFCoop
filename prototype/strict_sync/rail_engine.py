"""Actual Lua/native adapter for the separately identified guided fixed suite.

The accepted StreamEngine pacing is inherited. Mutations hold one jointly
observed frontier through fresh preview, plan, actual callback and postcondition
readback. Read-only checks use the Lua bridge's explicit observation path.
"""
from __future__ import annotations

import copy
import time

from .core import canonical_json
from .engine_mailbox import ENGINE_STEP_US, EngineAdapter, MailboxError, _COMMAND_KEY
from .rail_catalog import CONTRACT, get_step
from .rail_input import validate_command, validate_preview, validate_action_receipt
from .stream_engine import StreamEngine


VEHICLE_NAME_CONTRACT = "observed_vehicle_name_v1"


def _need(condition, detail):
    if not condition:
        raise MailboxError("rail engine: " + detail)


def _world(engine):
    return {"frame": engine.frame, "sim_time_us": engine.time_us,
            "paused": engine.paused, "state_digest": engine.state_digest}



_REGISTRY_FIELDS = ("station_a", "station_b", "depot", "connectors", "signal_a", "signal_b", "waypoint", "train", "clone", "line")
_ACTION_TARGETS = {
    "BUILD_STATION_A": "station_a", "BUILD_STATION_B": "station_b", "BUILD_RAIL_DEPOT": "depot",
    "CONNECT_RAIL": "connectors", "VERIFY_RAIL_GRAPH": "connectors",
    "ADD_SIGNAL_A": "signal_a", "ADD_SIGNAL_B": "signal_b", "ADD_WAYPOINT": "waypoint",
    "BUY_TRAIN": "train", "RENAME_TRAIN": "train", "TRAIN_MAINTENANCE": "train", "ASSIGN_TRAIN": "train",
    "VERIFY_TRAIN_MOVEMENT": "train", "STOP_TRAIN": "train", "START_TRAIN": "train", "REVERSE_TRAIN": "train",
    "SEND_DEPOT": "train", "VERIFY_DEPOT": "train", "REPLACE_TRAIN": "train", "CLONE_TRAIN": "clone",
    "CREATE_LINE": "line", "ADD_STOP_A": "line", "ADD_STOP_B": "line", "SELL_CLONE": "clone",
    "SELL_TRAIN": "train", "DELETE_LINE": "line", "REMOVE_WAYPOINT": "waypoint", "REMOVE_SIGNAL_A": "signal_a",
    "REMOVE_SIGNAL_B": "signal_b", "REMOVE_CONNECTORS": "connectors", "REMOVE_RAIL_DEPOT": "depot",
    "REMOVE_STATION_B": "station_b", "REMOVE_STATION_A": "station_a"}
_CREATES = frozenset(("BUILD_STATION_A", "BUILD_STATION_B", "BUILD_RAIL_DEPOT", "CONNECT_RAIL",
    "ADD_SIGNAL_A", "ADD_SIGNAL_B", "ADD_WAYPOINT", "BUY_TRAIN", "CREATE_LINE", "CLONE_TRAIN"))
_REMOVES = frozenset(("SELL_CLONE", "SELL_TRAIN", "DELETE_LINE", "REMOVE_WAYPOINT", "REMOVE_SIGNAL_A",
    "REMOVE_SIGNAL_B", "REMOVE_CONNECTORS", "REMOVE_RAIL_DEPOT", "REMOVE_STATION_B", "REMOVE_STATION_A"))
_MARKER_ACTIONS = frozenset(("ADD_SIGNAL_A", "ADD_SIGNAL_B", "ADD_WAYPOINT", "REMOVE_SIGNAL_A", "REMOVE_SIGNAL_B", "REMOVE_WAYPOINT"))


def _clone_configuration(value):
    result = copy.deepcopy(value)
    for part in result["vehicles"]:
        part.pop("purchase_time", None)
        part.pop("maintenance", None)
    return result


class RailEngineAdapter(EngineAdapter):
    def __init__(self, *args, **kwargs):
        self._guided_applied = {}
        super().__init__(*args, **kwargs)
        try:
            self._registry(self.snapshot())
        except Exception as exc:
            self.halt(str(exc))
            self.native.close()
            raise

    @staticmethod
    def _registry(snapshot):
        value = snapshot.get("probe", {}).get("rail_suite")
        kinds = {"station_a": "rail_station", "station_b": "rail_station", "depot": "rail_depot",
                 "connectors": "rail_network", "signal_a": "rail_marker", "signal_b": "rail_marker",
                 "waypoint": "rail_marker", "train": "rail_train", "clone": "rail_train", "line": "rail_line"}
        _need(type(value) is dict and value.get("contract") == CONTRACT
              and value.get("vehicle_name_contract") == VEHICLE_NAME_CONTRACT,
              "loaded Lua lacks the railway identity and semantic-name contract")
        caps = value.get("capabilities")
        _need(type(caps) is dict and caps.get("ready") is True and caps.get("missing") == [],
              "railway capability preflight did not finish successfully")
        objects = snapshot.get("objects")
        _need(type(objects) is list, "railway tracked object observations are absent")
        by_key = {item["logical_id"]: item for item in objects}
        _need(len(by_key) == len(objects), "duplicate logical object observation")
        refs = []
        for field, kind in kinds.items():
            key = value.get(field)
            _need(type(key) is str, "railway registry field is not a logical identity: " + field)
            if key:
                _need(key in by_key and by_key[key]["kind"] == kind,
                      "railway identity is not backed by its observed object kind: " + field)
                refs.append(key)
        _need(len(refs) == len(set(refs)), "railway registry aliases two owned objects")
        for item in objects:
            if item.get("kind") not in ("vehicle", "rail_train"):
                continue
            name = item.get("state", {}).get("name")
            _need(type(name) is dict and
                  ((set(name) == {"mode"} and name["mode"] == "automatic")
                   or (set(name) == {"mode", "value"} and name["mode"] == "explicit"
                       and type(name["value"]) is str)),
                  "tracked vehicle lacks a typed semantic name: " + item["logical_id"])
        return value

    def _accept_snapshot(self, status):
        super()._accept_snapshot(status)
        # The preparation vehicle is created before the guided input phase.
        # Validate its contract on every observed boundary as well.
        self._registry(self._snapshot)

    def _key(self, command, key):
        validate_command(command)
        _need(command["op"] == "RAIL_ACTION", "guided path requires RAIL_ACTION")
        step = get_step(command["step"])
        _need(type(key) is str and _COMMAND_KEY.fullmatch(key) is not None, "invalid command identity")
        origin, text = key.split(":")
        _need(origin == step["actor"] and int(text) == self._last_seq[origin] + 1,
              "wrong actor or noncontiguous logical command")
        return origin, int(text)

    def _plain_preview(self, raw, command):
        _need(type(raw) is dict and set(raw) == {"contract", "step", "action", "allowed", "reason", "observation"}
              and raw["contract"] == CONTRACT, "Lua preview differs from the guided contract")
        value = {key: copy.deepcopy(val) for key, val in raw.items() if key != "contract"}
        value["state_digest"] = self.state_digest
        return validate_preview(value, command, _world(self))

    def _preview_locked(self, command, key):
        self._key(command, key)
        before = _world(self)
        status = self._request_lua("preview", command=command, command_key=key,
            expected_sim_time_us=self.time_us, boundary=str(self.frame))
        self._accept_snapshot(status)
        _need(_world(self) == before, "read-only preflight changed the observed world")
        self._registry(self.snapshot())
        return self._plain_preview(status.get("preview"), command)

    def preview_guided(self, command, command_key):
        self._enter()
        try:
            return self._preview_locked(command, command_key)
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def apply(self, command, command_key):
        if type(command) is dict and command.get("op") == "RAIL_ACTION":
            self.halt("guided action requires the separately approved preview path")
            raise MailboxError(self.reason)
        return super().apply(command, command_key)

    def apply_guided(self, command, command_key, preview):
        self._enter()
        try:
            command_raw, preview_raw = canonical_json(command), canonical_json(preview)
            previous = self._guided_applied.get(command_key)
            if previous is not None:
                _need(previous[:2] == (command_raw, preview_raw), "conflicting repeated guided apply")
                return copy.deepcopy(previous[2])
            origin, number = self._key(command, command_key)
            before, before_snapshot = _world(self), self.snapshot()
            validate_preview(preview, command, before)
            _need(preview["allowed"] is True, "rejected action cannot be applied")
            _need(self._preview_locked(command, command_key) == preview,
                  "fresh preflight differs from jointly approved observation")
            fields = {"command_key": command_key, "command": command,
                      "expected_sim_time_us": self.time_us, "boundary": str(self.frame)}
            planned = self._request_lua("plan", **fields)
            self._accept_snapshot(planned)
            _need(_world(self) == before and self._plain_preview(planned.get("preview"), command) == preview,
                  "plan changed the approved action or tracked world")
            applied = self._request_lua("apply", **fields)
            self._accept_snapshot(applied)
            receipt = applied.get("receipt")
            _need(type(receipt) is dict and receipt.get("command_key") == command_key
                  and receipt.get("boundary") == fields["boundary"] and receipt.get("success") is True,
                  "actual completion identity or success differs")
            result = {"success": True, "result": copy.deepcopy(receipt.get("result")),
                      "state_digest": self.state_digest}
            validate_action_receipt(result, command, command_key, preview, before, _world(self))
            self._check_observation(command, result["result"]["effect"], before_snapshot, self.snapshot(), preview)
            self._last_seq[origin] = number
            self._last_apply[command_key] = (command_raw, copy.deepcopy(result))
            self._guided_applied[command_key] = (command_raw, preview_raw, copy.deepcopy(result))
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def _check_observation(self, command, effect, before, after, preview):
        step = get_step(command["step"])
        prior, current = self._registry(before), self._registry(after)
        _need(before["company"] == {"balance": effect["balance_before"], "loan": effect["loan_before"]}
              and after["company"] == {"balance": effect["balance_after"], "loan": effect["loan_after"]},
              "railway receipt money differs from independently observed company")
        old, new = ({item["logical_id"]: item for item in snapshot["objects"]} for snapshot in (before, after))
        _need(set(new) - set(old) == set(effect["created"]) and set(old) - set(new) == set(effect["removed"]),
              "railway receipt membership differs from actual snapshot")
        action, target, observed = step["action"], effect["target"], effect["observed"]
        expected = preview["observation"].get("expected")
        _need(type(expected) is dict and expected.get("required_effect") == action,
              "railway preview lacks the exact expected action")
        field = _ACTION_TARGETS.get(action)
        creates, removes = action in _CREATES, action in _REMOVES
        if field:
            expected_target = current[field] if creates or action == "REPLACE_TRAIN" else prior[field]
            _need(target == expected_target and bool(target), "railway result targets another logical generation")
        for registry_field in _REGISTRY_FIELDS:
            if registry_field != field or not (creates or removes or action == "REPLACE_TRAIN"):
                _need(prior[registry_field] == current[registry_field], "unrelated railway registry identity changed")
        if action in ("PAUSE", "RESUME"):
            _need(observed == {"paused": after["paused"]} and old == new,
                  "pause receipt differs from actual pause or changed railway objects")
        elif removes:
            _need(current[field] == "" and target not in new and observed == {"entity_absent": True}
                  and target in effect["removed"] and not effect["created"],
                  "removed railway object or generation is still present")
            _need(all(key == target or key.startswith(target + ":") for key in effect["removed"]),
                  "removal affected an unrelated logical object")
        else:
            _need(target in new and new[target]["state"] == observed,
                  "railway postconditions differ from independent component observations")
        if creates:
            _need(prior[field] == "" and target in effect["created"] and not effect["removed"],
                  "railway creation did not introduce exactly its fresh logical root")
            _need(all(key == target or key.startswith(target + ":") for key in effect["created"]),
                  "creation introduced an unrelated logical object")
        elif not removes and action != "REPLACE_TRAIN":
            _need(not effect["created"] and not effect["removed"], "property action changed object membership")
        if step["read_only"]:
            _need(before == after, "railway readiness observation changed the held world")
        self._check_changed_fields(action, prior, current, old, new)
        self._check_expected(action, prior, current, old, new, observed, expected, effect)

    @staticmethod
    def _check_expected(action, prior, current, old, new, observed, expected, effect):
        if action in ("BUY_TRAIN", "REPLACE_TRAIN", "CLONE_TRAIN"):
            cfg = observed.get("config", {})
            parts = cfg.get("vehicles")
            models = expected.get("models")
            _need(type(parts) is list and type(models) is list
                  and [part.get("model") for part in parts] == models
                  and len(parts) == (2 if action == "BUY_TRAIN" else 3)
                  and observed.get("carrier") == 1 and observed.get("position") == "in_depot"
                  and observed.get("depot") == current["depot"] + ":depot",
                  "actual train composition, carrier or depot differs from approved recipe")
            _need(type(cfg.get("groups")) is list and sum(cfg["groups"]) == len(parts),
                  "train vehicle groups do not account for every actual part")
            if action in ("BUY_TRAIN", "CLONE_TRAIN"):
                _need(observed.get("name") == {"mode": "automatic"} and observed.get("line") == "",
                      "new train lacks its semantic automatic name or is unexpectedly assigned")
            if action == "CLONE_TRAIN":
                source_cfg = old[prior["train"]]["state"]["config"]
                _need(_clone_configuration(source_cfg) == _clone_configuration(cfg),
                      "cloned train differs from the actual approved source configuration")
            if action == "REPLACE_TRAIN":
                previous = prior["train"]
                _need(observed.get("name") == old[previous]["state"].get("name")
                      and observed.get("line") == old[previous]["state"].get("line"),
                      "replacement changed the train name or assigned line")
                if current["train"] == previous:
                    _need(not effect["created"] and not effect["removed"], "same-entity replacement changed unrelated identities")
                else:
                    _need(effect["removed"] == [previous] and effect["created"] == [current["train"]],
                          "replacement did not bind the actual new train generation")
        elif action == "CREATE_LINE":
            _need(observed.get("stops") == [] and observed.get("vehicles") == [], "new railway line is not empty")
        elif action in ("ADD_STOP_A", "ADD_STOP_B"):
            stops = observed.get("stops")
            desired = [prior["station_a"]] if action == "ADD_STOP_A" else [prior["station_a"], prior["station_b"]]
            _need(type(stops) is list and [stop.get("stop") for stop in stops] == desired,
                  "railway stop order differs from requested station identities")
        elif action == "RENAME_TRAIN":
            _need(type(expected.get("name")) is str
                  and observed.get("name") == {"mode": "explicit", "value": expected["name"]},
                  "explicit train name differs from the jointly approved name")
        elif action == "TRAIN_MAINTENANCE":
            _need(all(part["target_maintenance"] == "1" for part in observed["config"]["vehicles"]),
                  "train maintenance target did not change on every part")
        elif action == "ASSIGN_TRAIN":
            _need(observed.get("line") == prior["line"]
                  and observed.get("stop_index") == {"available": True, "value": 0}
                  and prior["train"] in new[prior["line"]]["state"]["vehicles"],
                  "actual train assignment or ordered first stop differs")
        elif action in ("STOP_TRAIN", "START_TRAIN"):
            _need(observed.get("user_stopped") is (action == "STOP_TRAIN"), "actual train stop state differs")
        elif action == "REVERSE_TRAIN":
            previous = old[prior["train"]]["state"]
            _need(any(observed.get(key) != previous.get(key) for key in ("state", "stop_index", "movement")),
                  "train reverse has no actual observed route or state change")
        elif action == "SEND_DEPOT":
            previous = old[prior["train"]]["state"]
            _need(observed.get("state") != previous.get("state") or observed.get("line") == "",
                  "train depot request has no observed operation change")
        elif action == "VERIFY_DEPOT":
            _need(observed.get("position") == "in_depot" and observed.get("depot") == prior["depot"] + ":depot",
                  "train is not in its actual target depot")
        elif action == "VERIFY_TRAIN_MOVEMENT":
            motion = observed.get("guided_motion", {})
            _need(observed.get("position") != "in_depot" and observed.get("no_path") is False
                  and observed.get("world_position_present") is True
                  and motion.get("displacement_observed") is True
                  and type(motion.get("first_time_us")) is int and type(motion.get("observed_time_us")) is int
                  and motion["observed_time_us"] > motion["first_time_us"]
                  and motion.get("first_position_mm") != motion.get("observed_position_mm"),
                  "train motion lacks independently observed time and position displacement")
        elif action == "VERIFY_RAIL_GRAPH":
            _need(observed.get("connected") is True and len(observed.get("arms", [])) == 3
                  and all(prior[field] for field in ("signal_a", "signal_b", "waypoint", "station_a", "station_b", "depot")),
                  "actual railway graph or marker membership is incomplete")
            found = {entry["logical_id"] for arm in observed["arms"] for entry in arm["objects"]}
            _need(all(prior[field] in found for field in ("signal_a", "signal_b", "waypoint")),
                  "railway markers are not attached to the actual observed connector graph")

    @staticmethod
    def _check_changed_fields(action, prior, current, old, new):
        train, line, network = prior["train"], prior["line"], prior["connectors"]
        allowed = {}
        route = {"line", "depot", "state", "no_path", "stop_index", "position", "world_position_present",
                 "move_path_present", "movement", "guided_motion"}
        if action == "RENAME_TRAIN": allowed[train] = {"name"}
        elif action == "TRAIN_MAINTENANCE": allowed[train] = {"config"}
        elif action in ("ADD_STOP_A", "ADD_STOP_B"): allowed[line] = {"stops"}
        elif action in ("STOP_TRAIN", "START_TRAIN"): allowed[train] = {"user_stopped", "movement"}
        elif action == "REVERSE_TRAIN": allowed[train] = route - {"line", "depot"}
        elif action in ("ASSIGN_TRAIN", "SEND_DEPOT"):
            allowed[train] = route; allowed[line] = {"vehicles"}
        elif action == "REPLACE_TRAIN":
            allowed[train] = {"config"} | route; allowed[line] = {"vehicles"}
        elif action in ("SELL_TRAIN", "SELL_CLONE"): allowed[line] = {"vehicles"}
        if action in _MARKER_ACTIONS: allowed[network] = {"arms"}
        for key in set(old) & set(new):
            _need(old[key]["kind"] == new[key]["kind"], "existing railway object changed kind")
            fields = allowed.get(key, set())
            _need({name: value for name, value in old[key]["state"].items() if name not in fields}
                  == {name: value for name, value in new[key]["state"].items() if name not in fields},
                  "railway action changed an unrelated object or property: " + key)
        if action == "TRAIN_MAINTENANCE":
            previous, actual = (copy.deepcopy(objects[train]["state"]["config"]) for objects in (old, new))
            for cfg in (previous, actual):
                _need(len(cfg["vehicles"]) == 2, "maintenance changed the pre-replacement train part count")
                for part in cfg["vehicles"]: part.pop("target_maintenance")
            _need(previous == actual, "maintenance changed another actual train configuration field")
        if line and line in old and line in new and action in ("ASSIGN_TRAIN", "SEND_DEPOT", "REPLACE_TRAIN", "SELL_TRAIN", "SELL_CLONE"):
            previous = old[line]["state"]["vehicles"]
            actual = new[line]["state"]["vehicles"]
            if action == "ASSIGN_TRAIN":
                expected = sorted(set(previous) | {train})
            elif action == "REPLACE_TRAIN":
                expected = sorted(current["train"] if item == train else item for item in previous)
            elif action in ("SELL_TRAIN", "SELL_CLONE"):
                removed = prior["train" if action == "SELL_TRAIN" else "clone"]
                expected = sorted(item for item in previous if item != removed)
            else:
                _need(sorted(actual) in (sorted(previous), sorted(item for item in previous if item != train)),
                      "depot command changed unrelated line membership")
                expected = sorted(actual)
            _need(sorted(actual) == expected and len(actual) == len(set(actual)),
                  "railway action changed unrelated line membership")
        if action in _MARKER_ACTIONS:
            before_arms, after_arms = old[network]["state"]["arms"], new[network]["state"]["arms"]
            _need(len(before_arms) == len(after_arms) == 3, "marker operation changed network arm count")
            changed = []
            for before_arm, after_arm in zip(before_arms, after_arms):
                _need({key: value for key, value in before_arm.items() if key not in ("edge", "objects")}
                      == {key: value for key, value in after_arm.items() if key not in ("edge", "objects")},
                      "marker operation changed actual rail geometry or endpoints")
                if before_arm != after_arm: changed.append((before_arm, after_arm))
            _need(len(changed) == 1, "marker operation must rebuild exactly its single owned arm")
            before_arm, after_arm = changed[0]
            _need(before_arm["edge"] != after_arm["edge"], "rebuilt marker edge lacks a fresh logical generation")
            field = _ACTION_TARGETS[action]
            root = current[field] if action in _CREATES else prior[field]
            before_objects = {item["logical_id"]: item for item in before_arm["objects"]}
            after_objects = {item["logical_id"]: item for item in after_arm["objects"]}
            if action in _CREATES:
                _need(set(after_objects) - set(before_objects) == {root} and set(before_objects) <= set(after_objects),
                      "marker insertion changed another edge object")
            else:
                _need(set(before_objects) - set(after_objects) == {root} and set(after_objects) <= set(before_objects),
                      "marker removal changed another edge object")
            _need(all(before_objects[key] == after_objects[key] for key in before_objects.keys() & after_objects.keys()),
                  "marker operation changed another marker membership")


class RailStreamEngine(StreamEngine):
    def __init__(self, engine, *args, **kwargs):
        _need(isinstance(engine, RailEngineAdapter), "guided stream requires actual guided adapter")
        super().__init__(engine, *args, **kwargs)

    def preview_guided(self, command, command_key):
        self._enter()
        try:
            self._stop()
            _need(self.observations_fresh, "guided preview requires fresh jointly held world")
            before = self._boundary()
            result = self.engine.preview_guided(command, command_key)
            _need(_world(self.engine) == before, "guided preview changed native time/pause/world")
            self._remember_observation()
            self._fresh = True
            self._stop()
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def apply_guided(self, command, command_key, preview):
        self._enter()
        try:
            self._stop()
            _need(self.observations_fresh, "guided apply requires fresh jointly held world")
            before = self._boundary()
            result = self.engine.apply_guided(command, command_key, preview)
            _need(self.engine.frame == before["frame"] and self.engine.time_us == before["sim_time_us"],
                  "guided action changed native frontier")
            self.paused = self.engine.paused
            self._remember_observation()
            self._fresh = True
            validate_action_receipt(result, command, command_key, preview, before, self._boundary())
            if before["paused"] and not self.paused:
                self._next_call_deadline = time.perf_counter() + ENGINE_STEP_US / 1_000_000
            self._stop()
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()
