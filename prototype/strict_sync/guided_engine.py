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
from .guided_catalog import CONTRACT, get_step
from .guided_input import validate_command, validate_preview, validate_action_receipt
from .stream_engine import StreamEngine


def _need(condition, detail):
    if not condition:
        raise MailboxError("guided engine: " + detail)


def _world(engine):
    return {"frame": engine.frame, "sim_time_us": engine.time_us,
            "paused": engine.paused, "state_digest": engine.state_digest}


class GuidedEngineAdapter(EngineAdapter):
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
        value = snapshot.get("probe", {}).get("guided_suite")
        _need(type(value) is dict and value.get("contract") == CONTRACT
              and type(value.get("vehicle")) is str and type(value.get("line")) is str,
              "loaded Lua lacks the guided suite identity contract")
        caps = value.get("capabilities")
        _need(type(caps) is dict and caps.get("ready") is True and caps.get("missing") == [],
              "guided capability preflight did not finish successfully")
        return value

    def _key(self, command, key):
        validate_command(command)
        _need(command["op"] == "GUIDED_ACTION", "guided path requires GUIDED_ACTION")
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
        if type(command) is dict and command.get("op") == "GUIDED_ACTION":
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
            self._check_observation(command, result["result"]["effect"], before_snapshot, self.snapshot())
            self._last_seq[origin] = number
            self._last_apply[command_key] = (command_raw, copy.deepcopy(result))
            self._guided_applied[command_key] = (command_raw, preview_raw, copy.deepcopy(result))
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def _check_observation(self, command, effect, before, after):
        step = get_step(command["step"])
        old_registry, registry = self._registry(before), self._registry(after)
        _need(before["company"] == {"balance": effect["balance_before"], "loan": effect["loan_before"]}
              and after["company"] == {"balance": effect["balance_after"], "loan": effect["loan_after"]},
              "receipt money differs from independently observed company")
        old, new = ({item["logical_id"]: item for item in snapshot["objects"]} for snapshot in (before, after))
        _need(set(new) - set(old) == set(effect["created"]) and set(old) - set(new) == set(effect["removed"]),
              "receipt object membership differs from actual snapshot")
        action, target, observed = step["action"], effect["target"], effect["observed"]
        self._check_changed_fields(action, old_registry, registry, old, new)
        if action in ("PAUSE", "RESUME"):
            _need(observed == {"paused": after["paused"]} and old == new,
                  "pause receipt differs from actual observed pause or changed objects")
        elif action in ("SELL_BUS", "DELETE_LINE"):
            expected = old_registry["vehicle" if action == "SELL_BUS" else "line"]
            _need(effect["removed"] == [expected] and target == expected and observed == {"entity_absent": True},
                  "removed object identity differs from current generation")
        else:
            _need(target in new and new[target]["state"] == observed,
                  "receipt postconditions differ from independent component observation")
        if step["read_only"]:
            _need(before == after, "read-only readiness completion changed tracked world")
        if action == "BUY_BUS":
            _need(effect["created"] == [registry["vehicle"]] and new[target]["kind"] == "vehicle"
                  and after["company"]["balance"] < before["company"]["balance"],
                  "purchase lacks a new actual vehicle and debit")
        elif action == "CREATE_LINE":
            _need(effect["created"] == [registry["line"]] and new[target]["kind"] == "line"
                  and observed["stops"] == [] and observed["vehicles"] == [], "new empty line differs")
        elif action not in ("SELL_BUS",):
            _need(before["company"] == after["company"], "no-cost action changed company")

    @staticmethod
    def _check_changed_fields(action, old_registry, registry, old, new):
        """Allow only the selected property and observed dependent route state.

        Two guided objects do not form a blanket mutation exemption. Even a
        successful rename callback must fail-stop if it also edits the line.
        """
        vehicle, line = old_registry['vehicle'], old_registry['line']
        allowed = {}
        route_fields = {'line', 'depot', 'state', 'no_path', 'stop_index', 'position',
                        'world_position_present', 'move_path_present', 'movement', 'guided_motion'}
        if action == 'RENAME_BUS':
            allowed[vehicle] = {'name'}
        elif action == 'MAINTENANCE':
            allowed[vehicle] = {'config'}
        elif action in ('STOP_BUS', 'START_BUS'):
            allowed[vehicle] = {'user_stopped', 'movement'}
        elif action == 'RENAME_LINE':
            allowed[line] = {'name'}
        elif action == 'COLOR_LINE':
            allowed[line] = {'color'}
        elif action in ('ADD_STOP_A', 'ADD_STOP_B', 'REMOVE_STOP_B', 'RESTORE_STOP_B'):
            allowed[line] = {'stops'}
        elif action in ('REVERSE_STOPS', 'RESTORE_STOPS', 'LINE_RULES'):
            allowed[line] = {'stops'}
            allowed[vehicle] = route_fields - {'line', 'depot'}
        elif action in ('ASSIGN_BUS', 'SEND_DEPOT'):
            allowed[vehicle] = route_fields
            allowed[line] = {'vehicles'}
        elif action == 'REVERSE_BUS':
            allowed[vehicle] = route_fields - {'line', 'depot'}
        elif action == 'SELL_BUS':
            allowed[line] = {'vehicles'}
        for key in set(old) & set(new):
            _need(old[key]['kind'] == new[key]['kind'], 'existing logical object changed kind')
            fields = allowed.get(key, set())
            prior, current = old[key]['state'], new[key]['state']
            _need({k: v for k, v in prior.items() if k not in fields}
                  == {k: v for k, v in current.items() if k not in fields},
                  'guided action changed an unrelated tracked object or property: ' + key)
        if action == 'MAINTENANCE':
            prior, current = (copy.deepcopy(objects[vehicle]['state']['config']) for objects in (old, new))
            for cfg in (prior, current):
                _need(len(cfg['vehicles']) == 1, 'maintenance vehicle part count changed')
                cfg['vehicles'][0].pop('target_maintenance')
            _need(prior == current, 'maintenance changed another vehicle configuration property')


class GuidedStreamEngine(StreamEngine):
    def __init__(self, engine, *args, **kwargs):
        _need(isinstance(engine, GuidedEngineAdapter), "guided stream requires actual guided adapter")
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
