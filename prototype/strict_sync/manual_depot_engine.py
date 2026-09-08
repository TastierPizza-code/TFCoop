"""Actual observed-engine adapter for the separate bounded depot input test.

The accepted StreamEngine pacer is inherited unchanged. A depot needs a fresh
read-only Lua preview, an identical freshly regenerated plan, the real engine
callback and observed object/company changes at the same native frontier.
"""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from .core import canonical_json, digest
from .engine_mailbox import EngineAdapter, MailboxError, _COMMAND_KEY
from .manual_depot_input import validate_command, validate_preview, validate_build_receipt
from .stream_engine import StreamEngine


CONTRACT = "manual_depot_v1"
DEPOT_FILE = "depot/road_depot_era_a.con"


def _need(condition, detail):
    if not condition:
        raise MailboxError("manual depot engine: " + detail)


def _world(engine):
    return {"frame": engine.frame, "sim_time_us": engine.time_us,
            "paused": engine.paused, "state_digest": engine.state_digest}


class ManualDepotEngineAdapter(EngineAdapter):
    def __init__(self, *args, **kwargs):
        self._manual_applied = {}
        super().__init__(*args, **kwargs)
        try:
            self._registry(self.snapshot())
        except Exception as exc:
            self.halt(str(exc))
            self.native.close()
            raise

    @staticmethod
    def _registry(snapshot):
        registry = snapshot.get("probe", {}).get("manual_depot")
        _need(type(registry) is dict and registry.get("contract") == CONTRACT
              and type(registry.get("placements")) is list,
              "loaded Lua configuration lacks the manual depot contract")
        return registry

    def _key(self, command, command_key):
        validate_command(command)
        _need(command["op"] == "BUILD_DEPOT", "preview/apply_manual requires BUILD_DEPOT")
        _need(type(command_key) is str and _COMMAND_KEY.fullmatch(command_key) is not None,
              "invalid logical command key")
        origin, number = command_key.split(":")
        _need(int(number) == self._last_seq[origin] + 1, "logical command sequence is not contiguous")
        return origin, int(number)

    def _plain_preview(self, raw, command):
        _need(type(raw) is dict and set(raw) == {"contract", "site", "rotation", "allowed", "reason",
                                               "cost", "position_mm", "proposal"}
              and raw["contract"] == CONTRACT and type(raw["site"]) is int
              and raw["site"] == command["site"] and type(raw["proposal"]) is dict,
              "Lua preview differs from the bounded contract")
        canonical_json(raw, limit=32768)
        value = {key: copy.deepcopy(raw[key]) for key in ("allowed", "reason", "cost", "position_mm", "rotation")}
        value.update(proposal_digest=digest(raw), state_digest=self.state_digest)
        return validate_preview(value, command, _world(self))

    def _preview_locked(self, command, command_key):
        self._key(command, command_key)
        before = _world(self)
        status = self._request_lua("preview", command=command, command_key=command_key,
            expected_sim_time_us=self.time_us, boundary=str(self.native.completed_frame))
        self._accept_snapshot(status)
        _need(_world(self) == before, "read-only preview changed the observed world")
        self._registry(self.snapshot())
        return self._plain_preview(status.get("preview"), command)

    def preview(self, command, command_key):
        self._enter()
        try:
            return self._preview_locked(command, command_key)
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def apply(self, command, command_key):
        if type(command) is dict and command.get("op") == "BUILD_DEPOT":
            self.halt("manual depot requires the separately approved preview path")
            raise MailboxError(self.reason)
        return super().apply(command, command_key)

    def apply_manual(self, command, command_key, preview):
        self._enter()
        try:
            raw_command, raw_preview = canonical_json(command), canonical_json(preview)
            previous = self._manual_applied.get(command_key)
            if previous is not None:
                _need(previous[:2] == (raw_command, raw_preview), "conflicting repeated manual apply")
                return copy.deepcopy(previous[2])
            origin, number = self._key(command, command_key)
            before, before_snapshot = _world(self), self.snapshot()
            validate_preview(preview, command, before)
            _need(preview["allowed"] is True, "rejected depot cannot be applied")
            _need(self._preview_locked(command, command_key) == preview,
                  "fresh preflight differs from the jointly approved preview")
            fields = {"command_key": command_key, "command": command,
                      "expected_sim_time_us": self.time_us, "boundary": str(self.frame)}
            planned = self._request_lua("plan", **fields)
            self._accept_snapshot(planned)
            _need(_world(self) == before and self._plain_preview(planned.get("preview"), command) == preview,
                  "Lua plan changed the approved placement or tracked world")
            applied = self._request_lua("apply", **fields)
            self._accept_snapshot(applied)
            receipt = applied.get("receipt")
            _need(type(receipt) is dict and receipt.get("command_key") == command_key
                  and receipt.get("boundary") == fields["boundary"] and receipt.get("success") is True,
                  "actual callback identity or success differs from the command")
            result = {"success": True, "result": copy.deepcopy(receipt.get("result")),
                      "state_digest": self.state_digest}
            validate_build_receipt(result, command, command_key, preview, before, _world(self))
            self._check_built_observation(command_key, result["result"], before_snapshot, self.snapshot())
            self._last_seq[origin] = number
            self._last_apply[command_key] = (raw_command, copy.deepcopy(result))
            self._manual_applied[command_key] = (raw_command, raw_preview, copy.deepcopy(result))
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def _check_built_observation(self, key, result, before, after):
        prior, current = {o["logical_id"]: o for o in before["objects"]}, {o["logical_id"]: o for o in after["objects"]}
        _need(set(current) - set(prior) == {key, key + ":depot"} and set(prior) <= set(current),
              "actual callback did not add exactly one depot and its bound child")
        _need(all(current[name] == obj for name, obj in prior.items()),
              "depot placement unexpectedly changed an earlier tracked object")
        main, child = current[key], current[key + ":depot"]
        _need(main["kind"] == "manual_depot" and child["kind"] == "manual_depot_child"
              and main["state"].get("file") == DEPOT_FILE and child["state"].get("carrier") == 0,
              "actual depot component/file/carrier differs")
        transform = main["state"].get("transform")
        _need(type(transform) is list and len(transform) == 16 and all(type(v) is str for v in transform),
              "actual depot transform is unavailable")
        try:
            values = [Decimal(v) for v in transform]
        except InvalidOperation as exc:
            raise MailboxError("manual depot transform is not numeric") from exc
        _need(all(v.is_finite() for v in values), "actual depot transform is not finite")
        position = [int((v * 1000 + Decimal(".5")).to_integral_value(rounding=ROUND_FLOOR)) for v in values[12:15]]
        rotations = {0: [1, 0, 0, 1], 90: [0, 1, -1, 0], 180: [-1, 0, 0, -1], 270: [0, -1, 1, 0]}
        rotation = [values[0], values[1], values[4], values[5]]
        _need(position == result["position_mm"] and rotation == rotations[result["rotation"]]
              and [values[i] for i in (2, 3, 6, 7, 8, 9, 11)] == [0] * 7
              and values[10] == values[15] == 1, "observed depot pose differs from the approved placement")
        _need(before["company"] == {"balance": result["balance_before"], "loan": result["loan_before"]}
              and after["company"] == {"balance": result["balance_after"], "loan": result["loan_after"]},
              "callback debit differs from independently observed company values")
        old_places, new_places = self._registry(before)["placements"], self._registry(after)["placements"]
        expected = sorted([*old_places, result], key=lambda value: value["logical_id"])
        _need(new_places == expected, "actual placement registry differs from the callback identities")


class ManualDepotStreamEngine(StreamEngine):
    def __init__(self, engine, *args, **kwargs):
        _need(isinstance(engine, ManualDepotEngineAdapter), "manual stream requires the actual manual adapter")
        super().__init__(engine, *args, **kwargs)

    def preview(self, command, command_key):
        self._enter()
        try:
            self._stop()
            _need(self.observations_fresh, "preview requires a fresh jointly held world")
            before = self._boundary()
            result = self.engine.preview(command, command_key)
            _need(_world(self.engine) == before, "preview changed native time/pause/world")
            self._remember_observation()
            self._fresh = True
            self._stop()
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def apply_manual(self, command, command_key, preview):
        self._enter()
        try:
            self._stop()
            _need(self.observations_fresh, "manual apply requires a fresh jointly held world")
            before = self._boundary()
            result = self.engine.apply_manual(command, command_key, preview)
            _need(all(_world(self.engine)[key] == before[key] for key in ("frame", "sim_time_us", "paused")),
                  "manual apply changed native time or pause")
            self._remember_observation()
            self._fresh = True
            validate_build_receipt(result, command, command_key, preview, before, self._boundary())
            self._stop()
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()
