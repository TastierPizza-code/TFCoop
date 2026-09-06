"""Fixed two-player engine experiment and proof from observed game snapshots.

This module creates no models, entity IDs, game commands or assumed prices.
Logical command identities select the objects created by verified Lua callbacks.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from .core import ProtocolError, canonical_json

BUILD_PROFILE = "build_v2"
TIME_PROFILE = "time_v1"
BUILD_ROUNDS = 240
BUILD_ADVANCE_STEPS = 211
EXPECTED_SCENE = {"road": "a:2", "depot": "b:1", "stops": ["a:3", "b:2"],
                  "connectors": "a:4", "vehicle": "b:3", "line": "a:5"}
_INPUTS = {
    "a": {0: {"op": "SET_PAUSED", "value": True}, 1: {"op": "PROBE_ROAD"},
          3: {"op": "PROBE_STOP", "index": 0}, 5: {"op": "PROBE_CONNECT"},
          7: {"op": "PROBE_LINE"}, 9: {"op": "SET_PAUSED", "value": False},
          80: {"op": "SET_PAUSED", "value": True}},
    "b": {2: {"op": "PROBE_DEPOT"}, 4: {"op": "PROBE_STOP", "index": 1},
          6: {"op": "PROBE_VEHICLE"}, 8: {"op": "PROBE_ASSIGN"},
          100: {"op": "SET_PAUSED", "value": False}},
}


def build_inputs(peer, number):
    if peer not in _INPUTS or type(number) is not int or not 0 <= number < BUILD_ROUNDS:
        raise ProtocolError("invalid fixed build profile player or round")
    command = _INPUTS[peer].get(number)
    return [copy.deepcopy(command)] if command else []


def phase_label(number, command=None):
    op = command.get("op") if isinstance(command, dict) else None
    labels = {"PROBE_ROAD": "Teststraße bauen", "PROBE_DEPOT": "Depot bauen",
              "PROBE_CONNECT": "Depot und Haltestellen mit der Straße verbinden",
              "PROBE_STOP": "Haltestellen bauen", "PROBE_VEHICLE": "Fahrzeug kaufen",
              "PROBE_LINE": "Linie mit beiden Haltestellen anlegen",
              "PROBE_ASSIGN": "Fahrzeug der Linie zuweisen"}
    if op in labels:
        return labels[op]
    if number is None or number == 0:
        return "Ausgangswelt und Baustelle prüfen"
    if number < 9:
        fixed = next((_INPUTS[peer][number] for peer in ("a", "b") if number in _INPUTS[peer]), {})
        return labels.get(fixed.get("op"), "Bauabschluss bestätigen")
    if 80 <= number < 100:
        return "Gemeinsame Pause und unveränderte Welt prüfen"
    if number >= BUILD_ROUNDS:
        return "Bau, Linienzuweisung und gefahrene Strecke bestätigt"
    return "Abfahrt, Bewegung und gemeinsame Firmenwerte prüfen"


def _require(condition, detail):
    if not condition:
        raise ProtocolError("build proof: " + detail)


class BuildProof:
    """Proof is collected at verified action boundaries and checked before ACK."""
    def __init__(self):
        self.site = None
        self.initial_time = None
        self.initial_finances = None
        self.last_snapshot = None
        self.samples = []
        self.finance_deltas = []

    def observe(self, snapshot, *, frame, command=None, command_key=None):
        _require(type(snapshot) is dict, "actual snapshot missing")
        probe = snapshot.get("probe")
        _require(type(probe) is dict and probe.get("profile") == BUILD_PROFILE,
                 "loaded Lua profile is not " + BUILD_PROFILE)
        site = probe.get("site")
        _require(type(site) is dict and all(type(site.get(k)) is int for k in ("x_mm", "y_mm", "z_mm"))
                 and type(site.get("recipe_id")) is str and bool(site["recipe_id"])
                 and type(site.get("assets")) is dict and bool(site["assets"]),
                 "observed recipe/site/assets are unavailable")
        current_time = snapshot.get("sim_time_us")
        company = snapshot.get("company")
        _require(type(current_time) is int and current_time >= 0 and type(company) is dict
                 and all(type(company.get(k)) is int for k in ("balance", "loan")),
                 "actual simulation time or company finances are unavailable")
        if self.site is None:
            self.site = copy.deepcopy(site)
            self.initial_time = current_time
            self.initial_finances = copy.deepcopy(company)
        else:
            _require(canonical_json(site) == canonical_json(self.site), "selected site or asset recipe changed")
            _require(current_time >= self.last_snapshot["sim_time_us"], "observed time moved backwards")
        if command is not None and self.last_snapshot is not None:
            self.finance_deltas.append({"command_key": command_key, "op": command.get("op"),
                "sim_time_us": current_time,
                "balance_delta": company["balance"] - self.last_snapshot["company"]["balance"],
                "loan_delta": company["loan"] - self.last_snapshot["company"]["loan"]})
        vehicle = probe.get("vehicle")
        if isinstance(vehicle, dict) and vehicle.get("position_mm") is not None:
            position = vehicle["position_mm"]
            _require(type(position) is list and len(position) == 3 and all(type(v) is int for v in position),
                     "vehicle position is not an observed integer millimetre vector")
            if not self.samples or current_time > self.samples[-1]["sim_time_us"]:
                self.samples.append({"sim_time_us": current_time, "frame": frame,
                    "position_mm": position[:], "in_depot": vehicle.get("in_depot"),
                    "state": vehicle.get("state"), "no_path": vehicle.get("no_path"),
                    "line": vehicle.get("line")})
        self.last_snapshot = copy.deepcopy(snapshot)

    def finish(self, *, frame, step_us):
        snapshot = self.last_snapshot
        _require(snapshot is not None and frame == BUILD_ROUNDS, "final verified boundary was not reached")
        _require(snapshot["sim_time_us"] - self.initial_time == BUILD_ADVANCE_STEPS * step_us,
                 "actual simulation time does not match the complete build/pause recipe")
        probe = snapshot["probe"]
        _require(probe.get("scene") == EXPECTED_SCENE, "not all actual scene objects were created")
        connectivity = probe.get("connectivity")
        _require(type(connectivity) is dict and connectivity.get("connected") is True,
                 "actual road/depot/stop graph connectivity was not verified")
        objects = snapshot.get("objects")
        _require(type(objects) is list, "tracked objects are unavailable")
        by_key = {obj.get("logical_id"): obj for obj in objects if type(obj) is dict}
        required = ("a:2", "b:1", "a:3", "b:2", "b:3", "a:5",
                    "a:4:link:1", "a:4:link:2", "a:4:link:3")
        _require(all(key in by_key and type(by_key[key].get("state")) is dict
                     and not by_key[key]["state"].get("unavailable") for key in required),
                 "scene references are not backed by actual tracked object states")
        _require(all(by_key[f"a:4:link:{index}"].get("kind") == "connector" for index in range(1, 4)),
                 "three observed connection edges are required")
        _require(by_key["b:3"].get("kind") == "vehicle" and by_key["a:5"].get("kind") == "line",
                 "tracked vehicle/line types are incorrect")
        vehicle, line = probe.get("vehicle"), probe.get("line")
        _require(type(vehicle) is dict and vehicle.get("logical_id") == "b:3"
                 and vehicle.get("line") == "a:5", "vehicle does not report its assigned line")
        _require(type(line) is dict and line.get("logical_id") == "a:5"
                 and line.get("vehicles") == ["b:3"] and line.get("stops") == ["a:3", "b:2"],
                 "actual line membership or ordered stop list is incorrect")
        _require(vehicle.get("in_depot") is False and type(vehicle.get("state")) is int
                 and vehicle["state"] == 1 and vehicle.get("no_path") is False,
                 "vehicle has not departed on a valid route")
        final_position = vehicle.get("position_mm")
        _require(type(final_position) is list and len(final_position) == 3
                 and all(type(value) is int for value in final_position),
                 "final actual vehicle position is unavailable")
        moving = [s for s in self.samples if s["in_depot"] is False and s["state"] == 1
                  and s["no_path"] is False and s["line"] == "a:5"]
        _require(len(moving) >= 2, "fewer than two observed movement samples at distinct simulation times")
        maximum_squared = max(sum((a - b) ** 2 for a, b in zip(left["position_mm"], right["position_mm"]))
                              for i, left in enumerate(moving) for right in moving[i + 1:])
        _require(maximum_squared >= 1000 ** 2, "vehicle did not move at least one observed metre")
        purchases = [event for event in self.finance_deltas if event["op"] == "PROBE_VEHICLE"]
        _require(len(purchases) == 1 and purchases[0]["command_key"] == "b:3"
                 and purchases[0]["balance_delta"] < 0,
                 "vehicle purchase did not show an actual debit from shared company money")
        return {"passed": True, "profile": BUILD_PROFILE, "complete_world_verified": False,
                "observed_scope": "constructed_scene_assignment_and_vehicle_movement",
                "frame": frame, "elapsed_sim_time_us": snapshot["sim_time_us"] - self.initial_time,
                "scene": copy.deepcopy(probe["scene"]), "site": copy.deepcopy(self.site),
                "connectivity": copy.deepcopy(connectivity),
                "movement_samples": copy.deepcopy(moving), "maximum_displacement_squared_mm": maximum_squared,
                "finances": {"initial": self.initial_finances, "final": copy.deepcopy(snapshot["company"]),
                    "balance_delta": snapshot["company"]["balance"] - self.initial_finances["balance"],
                    "loan_delta": snapshot["company"]["loan"] - self.initial_finances["loan"]},
                "command_finance_deltas": copy.deepcopy(self.finance_deltas)}


class SnapshotJournal:
    """Exclusive, bounded append-only local diagnostics; contains no connection key."""
    def __init__(self, path):
        self.path = Path(path)
        self.handle = self.path.open("x", encoding="utf-8", newline="\n")
        self.bytes = 0

    def append(self, event, *, frame=None, number=None, snapshot=None, command=None, command_key=None, reason=""):
        record = {"schema": 1, "profile": BUILD_PROFILE, "event": event, "frame": frame, "round": number,
                  "phase": phase_label(number, command), "command": command, "command_key": command_key,
                  "reason": str(reason)[:2048],
                  "snapshot_scope": "last_observed" if event == "failed" else "verified_boundary",
                  "snapshot": snapshot}
        raw = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
        self.bytes += len(raw.encode("utf-8"))
        if self.bytes > 64 * 1024 * 1024:
            raise ProtocolError("build snapshot journal exceeds 64 MiB")
        self.handle.write(raw)
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def close(self):
        self.handle.close()
