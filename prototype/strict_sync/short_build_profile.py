"""A separately identified scene preparation, not the 240-round BuildProof.

The original ten construction commands are reused with their actual callback,
shared-world and fixed-step checks. One advancing step must expose a connected,
assigned and departed vehicle before interactive controls are enabled. This does
not claim a metre of movement, a pause endurance result or complete world proof.
"""
from __future__ import annotations

import copy

from .build_profile import BUILD_PROFILE, EXPECTED_SCENE, BuildProof, build_inputs
from .core import ProtocolError, canonical_json, digest


SHORT_BUILD_CONTRACT = "short_scene_v1"
SHORT_BUILD_ROUNDS = 10
SHORT_ENGINE_SEQUENCES = {"a": 6, "b": 4}


def short_build_inputs(peer, number):
    if type(number) is not int or not 0 <= number < SHORT_BUILD_ROUNDS:
        raise ProtocolError("short preparation round outside its ten-command contract")
    return build_inputs(peer, number)


def _require(condition, detail):
    if not condition:
        raise ProtocolError("short preparation: " + detail)


class ShortBuildProof:
    """Collect local readiness before the last STEP acknowledgement is released."""
    def __init__(self):
        # Reuse only observation validation/collection, never BuildProof.finish.
        self.observed = BuildProof()
        self.frame = None
        self.commands = []
        self.sequences = {"a": 0, "b": 0}
        self.last_command_frame = None

    def observe(self, snapshot, *, frame, command=None, command_key=None, receipt=None):
        _require(type(frame) is int and 0 <= frame <= SHORT_BUILD_ROUNDS,
                 "observation outside the short preparation")
        if self.frame is None:
            _require(frame == 0 and command is None and receipt is None,
                     "initial observation must precede all work at frame zero")
        elif command is not None:
            _require(frame == self.frame and self.last_command_frame != frame,
                     "command observation repeated or outside the held round")
            expected = [(peer, item) for peer in ("a", "b")
                        for item in short_build_inputs(peer, frame)]
            _require(len(expected) == 1 and command == expected[0][1],
                     "command differs from the fixed short preparation")
            peer = expected[0][0]
            key = f"{peer}:{self.sequences[peer] + 1}"
            _require(command_key == key, "callback identity differs from the short recipe")
            _require(type(receipt) is dict and set(receipt) == {"success", "result", "state_digest"}
                     and receipt["success"] is True and receipt["state_digest"] == digest(snapshot),
                     "successful callback receipt matching the actual observation is missing")
            canonical_json(receipt)
            self.commands.append({"frame": frame, "command_key": key,
                                  "command": copy.deepcopy(command),
                                  "receipt": copy.deepcopy(receipt)})
            self.sequences[peer] += 1
            self.last_command_frame = frame
        else:
            _require(frame == self.frame + 1 and self.last_command_frame == self.frame
                     and receipt is None, "step lacks its verified command callback")
        self.observed.observe(snapshot, frame=frame, command=command, command_key=command_key)
        self.frame = frame

    def finish(self, *, frame, step_us):
        observed = self.observed
        snapshot = observed.last_snapshot
        _require(snapshot is not None and frame == self.frame == SHORT_BUILD_ROUNDS
                 and len(self.commands) == SHORT_BUILD_ROUNDS
                 and self.sequences == SHORT_ENGINE_SEQUENCES,
                 "all ten commands and their step boundaries must be verified")
        _require(type(step_us) is int and step_us > 0
                 and snapshot["sim_time_us"] - observed.initial_time == step_us,
                 "short recipe must contain exactly one advancing simulation step")
        _require(snapshot.get("paused") is False, "prepared scene is still paused")
        probe = snapshot["probe"]
        _require(probe.get("scene") == EXPECTED_SCENE, "actual scene objects are incomplete")
        connectivity = probe.get("connectivity")
        _require(type(connectivity) is dict and connectivity.get("connected") is True,
                 "actual road/depot/stop graph connectivity is unavailable")
        objects = snapshot.get("objects")
        _require(type(objects) is list, "tracked object observations are missing")
        by_key = {obj.get("logical_id"): obj for obj in objects if type(obj) is dict}
        required = ("a:2", "b:1", "a:3", "b:2", "b:3", "a:5",
                    "a:4:link:1", "a:4:link:2", "a:4:link:3")
        _require(all(key in by_key and type(by_key[key].get("state")) is dict
                     and not by_key[key]["state"].get("unavailable") for key in required),
                 "scene is not backed by actual tracked object states")
        _require(all(by_key[f"a:4:link:{index}"].get("kind") == "connector" for index in range(1, 4))
                 and by_key["b:3"].get("kind") == "vehicle" and by_key["a:5"].get("kind") == "line",
                 "connector, vehicle or line observation has the wrong type")
        vehicle, line = probe.get("vehicle"), probe.get("line")
        _require(type(vehicle) is dict and vehicle.get("logical_id") == "b:3"
                 and vehicle.get("line") == "a:5", "vehicle assignment is not observed")
        _require(type(line) is dict and line.get("logical_id") == "a:5"
                 and line.get("vehicles") == ["b:3"] and line.get("stops") == ["a:3", "b:2"],
                 "actual line membership or ordered stops differ")
        _require(vehicle.get("in_depot") is False and type(vehicle.get("state")) is int
                 and vehicle["state"] == 1 and vehicle.get("no_path") is False,
                 "vehicle has not departed on its connected assigned route")
        position = vehicle.get("position_mm")
        _require(type(position) is list and len(position) == 3 and all(type(v) is int for v in position),
                 "actual vehicle world position is not available")
        purchases = [row for row in observed.finance_deltas if row["op"] == "PROBE_VEHICLE"]
        _require(len(purchases) == 1 and purchases[0]["command_key"] == "b:3"
                 and purchases[0]["balance_delta"] < 0, "vehicle purchase lacks an actual company debit")
        return {"passed": True, "contract": SHORT_BUILD_CONTRACT, "lua_profile": BUILD_PROFILE,
                "observed_scope": "short_constructed_scene_callbacks_assignment_and_departure",
                "full_build_proof": False, "vehicle_displacement_verified": False,
                "pause_endurance_verified": False, "complete_world_verified": False,
                "frame": frame, "advancing_steps": 1, "paused_steps": SHORT_BUILD_ROUNDS - 1,
                "elapsed_sim_time_us": snapshot["sim_time_us"] - observed.initial_time,
                "engine_sequences": copy.deepcopy(self.sequences),
                "callback_outcomes": copy.deepcopy(self.commands),
                "scene": copy.deepcopy(probe["scene"]), "site": copy.deepcopy(observed.site),
                "connectivity": copy.deepcopy(connectivity), "vehicle": copy.deepcopy(vehicle),
                "line": copy.deepcopy(line), "command_finance_deltas": copy.deepcopy(observed.finance_deltas),
                "finances": {"initial": copy.deepcopy(observed.initial_finances),
                             "final": copy.deepcopy(snapshot["company"])}}
