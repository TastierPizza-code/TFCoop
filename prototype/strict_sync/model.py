"""Deterministic contract fixture, NOT a Transport Fever simulation.

Real adapters must obtain their digest from the loaded world and successful engine
callbacks. This fixture lets independent processes exercise the entire protocol with
different physical entity IDs. No game paths, hooks, guessed TF2 costs or IO occur here.
"""
from __future__ import annotations

import copy
import hashlib
import json


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class ModelError(ValueError):
    pass


class ModelEngine:
    """A small transport-world fixture with explicit logical identities and receipts."""

    def __init__(self, physical_id_base: int = 100, *, fault: str = "") -> None:
        self.time_us = 0
        self.money = 5_000_000
        self.paused = True
        self.roads: dict = {}
        self.depots: dict = {"seed:depot": {"position_mm": [0, 0]}}
        self.lines: dict = {}
        self.vehicles: dict = {"seed:vehicle": self._vehicle("seed:depot", "seed-model")}
        self.physical_ids = {"seed:depot": physical_id_base,
                             "seed:vehicle": physical_id_base + 1}
        self._next_id = physical_id_base + 2
        self._receipts: dict = {}
        self.fault = fault
        self.operations: list = []

    @staticmethod
    def _vehicle(depot: str, model: str) -> dict:
        return {"depot": depot, "model": model, "line": None, "stopped": True,
                "cargo": 0, "distance_mm": 0, "flipped": False,
                "logo": "", "maintenance": 100}

    def snapshot(self) -> dict:
        return copy.deepcopy({"schema": "contract-fixture-v1", "time_us": self.time_us,
                              "money": self.money, "paused": self.paused,
                              "roads": self.roads, "depots": self.depots,
                              "lines": self.lines, "vehicles": self.vehicles})

    @property
    def state_digest(self) -> str:
        return digest(self.snapshot())

    @staticmethod
    def _integer(value: object, lo: int, hi: int) -> int:
        if type(value) is not int or not lo <= value <= hi:
            raise ModelError("integer out of bounds")
        return value

    @staticmethod
    def _string(value: object) -> str:
        if not isinstance(value, str) or not value or len(value) > 128:
            raise ModelError("invalid name or logical reference")
        return value

    def _position(self, value: object) -> list:
        if not isinstance(value, list) or len(value) != 2:
            raise ModelError("position requires two integer millimetre coordinates")
        return [self._integer(v, -1_000_000_000, 1_000_000_000) for v in value]

    def _spend(self, amount: int) -> None:
        if self.money < amount:
            raise ModelError("insufficient funds")
        self.money -= amount

    def _reserve(self, key: str) -> None:
        if key in self.physical_ids:
            raise ModelError("logical identity already exists")
        self.physical_ids[key] = self._next_id
        self._next_id += 1

    def _stops(self, values: object) -> list:
        if not isinstance(values, list) or len(values) > 128:
            raise ModelError("invalid stops")
        result = []
        for value in values:
            ref = self._string(value)
            if ref not in self.depots:
                raise ModelError("unknown fixture stop")
            result.append(ref)
        return result

    def apply(self, command: dict, command_key: str) -> dict:
        """Apply once, atomically, after common authorization; return semantic result."""
        request_digest = digest(command)
        previous = self._receipts.get(command_key)
        if previous:
            if previous[0] != request_digest:
                raise ModelError("conflicting duplicate command")
            return copy.deepcopy(previous[1])
        before = copy.deepcopy(self.__dict__)
        try:
            result = self._apply(command, self._string(command_key))
            if self.fault == "money" and command.get("op") == "VEHICLE_BUY":
                self.money -= 1
            if self.fault == "route" and command.get("op") == "VEHICLE_ASSIGN":
                self.vehicles[command["vehicle"]]["stopped"] = True
            receipt = {"success": True, "result": result, "state_digest": self.state_digest}
        except (ModelError, KeyError, TypeError, ValueError) as exc:
            self.__dict__.clear()
            self.__dict__.update(before)
            receipt = {"success": False, "result": {"error": str(exc)},
                       "state_digest": self.state_digest}
        self._receipts[command_key] = (request_digest, copy.deepcopy(receipt))
        self.operations.append({"key": command_key, "command": copy.deepcopy(command),
                                "receipt": copy.deepcopy(receipt), "time_us": self.time_us})
        return receipt

    def _apply(self, command: dict, key: str) -> dict:
        if not isinstance(command, dict):
            raise ModelError("command must be an object")
        op = command.get("op")
        if op == "SET_PAUSED":
            if type(command.get("value")) is not bool:
                raise ModelError("pause must be boolean")
            self.paused = command["value"]
            return {"paused": self.paused}
        if op == "ROAD":
            points = command.get("points_mm")
            if not isinstance(points, list) or not 2 <= len(points) <= 128:
                raise ModelError("road needs 2..128 points")
            geometry = [self._position(p) for p in points]
            kind = self._string(command.get("kind"))
            self._reserve(key)
            self._spend(500)
            self.roads[key] = {"points_mm": geometry, "kind": kind}
        elif op == "DEPOT":
            position = self._position(command.get("position_mm"))
            self._reserve(key)
            self._spend(2000)
            self.depots[key] = {"position_mm": position}
        elif op == "LINE_CREATE":
            line = {"name": self._string(command.get("name")),
                    "stops": self._stops(command.get("stops", []))}
            self._reserve(key)
            self.lines[key] = line
        elif op == "LINE_UPDATE":
            ref = self._string(command.get("line"))
            if ref not in self.lines:
                raise ModelError("unknown line")
            self.lines[ref]["stops"] = self._stops(command.get("stops"))
            return {"line": ref, "stops": self.lines[ref]["stops"]}
        elif op == "VEHICLE_BUY":
            depot = self._string(command.get("depot"))
            if depot not in self.depots:
                raise ModelError("unknown depot")
            vehicle = self._vehicle(depot, self._string(command.get("model")))
            for name in ("flipped", "logo", "maintenance"):
                if name in command:
                    vehicle[name] = command[name]
            if type(vehicle["flipped"]) is not bool or not isinstance(vehicle["logo"], str):
                raise ModelError("invalid vehicle configuration")
            self._integer(vehicle["maintenance"], 0, 100)
            self._reserve(key)
            self._spend(10_000)
            self.vehicles[key] = vehicle
        elif op == "VEHICLE_ASSIGN":
            vehicle = self._string(command.get("vehicle"))
            line = self._string(command.get("line"))
            if vehicle not in self.vehicles or line not in self.lines or not self.lines[line]["stops"]:
                raise ModelError("vehicle and nonempty line required")
            self.vehicles[vehicle]["line"] = line
            self.vehicles[vehicle]["stopped"] = False
            return {"vehicle": vehicle, "line": line}
        else:
            raise ModelError("unsupported fixture command")
        return {"created": key}

    def step(self, dt_us: int) -> dict:
        self._integer(dt_us, 0, 1_000_000)
        if (self.paused and dt_us != 0) or (not self.paused and dt_us == 0):
            raise ModelError("permit disagrees with shared pause state")
        self.time_us += dt_us
        # Integer fixture arithmetic is intentionally transparent; these are NOT TF2 rules.
        for vehicle in self.vehicles.values():
            if vehicle["line"] and not vehicle["stopped"]:
                vehicle["distance_mm"] += dt_us // 100
                self.money += dt_us // 10_000
        return {"state_digest": self.state_digest, "sim_time_us": self.time_us}


def scenario(peer: str) -> dict[int, list[dict]]:
    """Includes creation dependencies, competing edits and builds during pause."""
    if peer == "a":
        return {
            0: [{"op": "ROAD", "points_mm": [[0, 0], [100_000, 0]], "kind": "street"},
                {"op": "DEPOT", "position_mm": [100_000, 0]},
                {"op": "LINE_CREATE", "name": "Gemeinsame Linie", "stops": []}],
            1: [{"op": "LINE_UPDATE", "line": "a:3", "stops": ["seed:depot", "a:2"]}],
            2: [{"op": "VEHICLE_BUY", "depot": "a:2", "model": "fixture-bus",
                 "flipped": True, "logo": "shared", "maintenance": 75}],
            3: [{"op": "VEHICLE_ASSIGN", "vehicle": "a:5", "line": "a:3"}],
            4: [{"op": "SET_PAUSED", "value": False}],
            9: [{"op": "SET_PAUSED", "value": True}],
            10: [{"op": "ROAD", "points_mm": [[0, 0], [0, 200_000]], "kind": "rail"}],
            11: [{"op": "SET_PAUSED", "value": False}],
        }
    if peer == "b":
        return {0: [{"op": "LINE_CREATE", "name": "Zweite leere Linie", "stops": []}],
                1: [{"op": "LINE_UPDATE", "line": "a:3", "stops": ["a:2", "seed:depot", "a:2"]}]}
    raise ValueError("unknown peer")
