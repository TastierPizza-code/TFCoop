"""Guarded model/engine boundary: only verified common actions may mutate it.

The synchronous adapter must finish commands without advancing simulation time.
Its state digest must cover the actual world. The replica checks that boundary
before every action; this does not provide native TF2 interception by itself.
"""
from __future__ import annotations

import copy
import json

from .core import (
    MAX_COMMAND_BYTES, MAX_COMMANDS_PER_PEER, MAX_RESULT_BYTES, ROSTER,
    ProtocolError, _EPOCH, _hash, _integer, canonical_json, verify_plan,
)


class Replica:
    def __init__(self, peer, epoch, manifest_digest, capabilities, engine, inputs,
                 *, step_us=100000, frame=0):
        if type(peer) is not str or peer not in ROSTER:
            raise ProtocolError("invalid replica peer")
        if type(epoch) is not str or _EPOCH.fullmatch(epoch) is None:
            raise ProtocolError("invalid replica epoch")
        _hash(manifest_digest, "manifest_digest")
        _integer(step_us, "step_us", 1)
        if step_us > 10_000_000:
            raise ProtocolError("step_us exceeds 10 seconds")
        _integer(frame, "frame")
        if (type(capabilities) not in (list, tuple) or not capabilities
                or len(capabilities) > 32
                or any(type(c) is not str or not 1 <= len(c) <= 64 for c in capabilities)
                or len(set(capabilities)) != len(capabilities)):
            raise ProtocolError("invalid replica capabilities")
        canonical_json(list(capabilities))
        self.peer, self._epoch = peer, epoch
        self.manifest = manifest_digest
        self.capabilities = sorted(capabilities)
        self.engine, self.inputs = engine, inputs
        self.round, self.frame, self.seq = 0, frame, 0
        self.step_us = step_us
        self.phase = "inputs"
        self.plan = None
        self.sealed = []
        self.next_index = 0
        self.cache = {}
        self.halted = False
        self.finished = False
        self.reason = ""
        self._terminal_raw = None
        self._last_seq = {origin: 0 for origin in ROSTER}
        self._expected_boundary = self._boundary()

    @property
    def epoch(self):
        return self._epoch

    def hello(self):
        self._require(not self.halted and not self.finished, "replica already stopped")
        self._verify_boundary()
        return self._message("hello", manifest_digest=self.manifest,
                             capabilities=self.capabilities,
                             state_digest=self.engine.state_digest, frame=self.frame,
                             sim_time_us=self.engine.time_us, paused=self.engine.paused)

    def _message(self, kind, **fields):
        return {"kind": kind, "epoch": self.epoch, **fields}

    def _require(self, predicate, message):
        if not predicate:
            raise ProtocolError(message)

    def _boundary(self):
        state = _hash(self.engine.state_digest, "actual state digest")
        actual_time = _integer(self.engine.time_us, "actual simulation time")
        self._require(type(self.engine.paused) is bool, "actual pause is not boolean")
        return state, actual_time, self.engine.paused

    def _verify_boundary(self):
        self._require(self._boundary() == self._expected_boundary,
                      "engine changed outside a permitted command/step")

    def receive(self, message):
        if self.halted or self.finished:
            if self._terminal_raw is not None and canonical_json(message) == self._terminal_raw:
                return None
            raise ProtocolError("replica already stopped")
        try:
            return self._receive(message)
        except Exception as exc:
            # Adapter exceptions must close the gate as well as protocol errors.
            self.halted, self.reason, self.phase = True, str(exc), "halted"
            raise ProtocolError(self.reason) from exc

    def _keys(self, message, names):
        self._require(set(message) == {"kind", "epoch", "round"} | set(names),
                      "missing or unexpected coordinator fields")

    def _validate_command(self, command):
        self._require(type(command) is dict and type(command.get("op")) is str
                      and 1 <= len(command["op"]) <= 64, "invalid command op")
        canonical_json(command, limit=MAX_COMMAND_BYTES)
        if command["op"] == "SET_PAUSED":
            self._require(set(command) == {"op", "value"} and type(command["value"]) is bool,
                          "SET_PAUSED requires only boolean value")

    def _validate_message(self, message):
        self._require(type(message) is dict, "coordinator message must be object")
        self._require(message.get("epoch") == self.epoch, "wrong replica epoch")
        kind = message.get("kind")
        self._require(type(kind) is str, "invalid coordinator kind")
        _integer(message.get("round"), "round")
        if kind == "halt":
            self._keys(message, {"reason"})
            self._require(type(message["reason"]) is str and len(message["reason"]) <= 512,
                          "invalid halt reason")
        elif kind == "complete":
            self._keys(message, {"frame", "sim_time_us", "state_digest"})
        elif kind == "request_inputs":
            self._keys(message, {"frame", "sim_time_us", "state_digest", "paused", "max_commands"})
            self._require(type(message["paused"]) is bool, "pause must be boolean")
            _integer(message["max_commands"], "input limit", 1)
            self._require(message["max_commands"] <= MAX_COMMANDS_PER_PEER, "input limit too large")
        elif kind == "prepare":
            self._require(verify_plan(message), "invalid common plan digest/envelope")
            _hash(message["pre_state_digest"], "pre_state_digest")
            _hash(message["manifest_digest"], "manifest_digest")
            self._require(type(message["paused"]) is bool, "plan pause must be boolean")
            _integer(message["step_us"], "fixed step", 1)
            self._require(message["step_us"] <= 10_000_000, "fixed step too large")
            self._require(type(message["capabilities"]) is list and type(message["roster"]) is list,
                          "invalid plan capabilities/roster")
            commands = message["commands"]
            self._require(type(commands) is list and len(commands) <= 2 * MAX_COMMANDS_PER_PEER,
                          "invalid plan commands")
            for item in commands:
                self._require(type(item) is dict and set(item) == {"origin", "seq", "command"},
                              "invalid plan command envelope")
                self._require(type(item["origin"]) is str and item["origin"] in ROSTER,
                              "invalid command origin")
                _integer(item["seq"], "command sequence", 1)
                self._validate_command(item["command"])
        elif kind == "apply":
            self._keys(message, {"plan_hash", "index", "command_key", "origin", "seq", "command"})
            _integer(message["index"], "command index")
            _integer(message["seq"], "command sequence", 1)
            self._require(type(message["origin"]) is str and message["origin"] in ROSTER,
                          "invalid command origin")
            self._require(type(message["command_key"]) is str and len(message["command_key"]) <= 64,
                          "invalid command key")
            self._validate_command(message["command"])
        elif kind == "step":
            self._keys(message, {"plan_hash", "frame", "dt_us", "sim_time_us"})
            _integer(message["dt_us"], "step delta")
            self._require(message["dt_us"] <= 10_000_000, "step delta too large")
        else:
            raise ProtocolError("unknown coordinator message")
        if kind in ("prepare", "apply", "step"):
            _hash(message["plan_hash"], "plan_hash")
        if kind in ("complete", "request_inputs", "prepare", "step"):
            _integer(message["frame"], "frame")
            _integer(message["sim_time_us"], "simulation time")
        if kind in ("complete", "request_inputs"):
            _hash(message["state_digest"], "state_digest")
        return kind

    def _receive(self, message):
        raw = canonical_json(message)
        message = json.loads(raw)
        kind = self._validate_message(message)
        if kind == "halt":
            self.halted, self.reason, self.phase = True, message["reason"], "halted"
            self._terminal_raw = raw
            return None
        self._verify_boundary()
        key = (kind, message["round"], message.get("index"))
        cached = self.cache.get(key)
        if cached:
            self._require(cached[0] == raw, "conflicting coordinator duplicate")
            return copy.deepcopy(cached[1])
        self._require(message["round"] == self.round, "wrong replica round")
        if kind == "complete":
            self._require(self.phase == "inputs" and message["frame"] == self.frame
                          and message["state_digest"] == self.engine.state_digest
                          and message["sim_time_us"] == self.engine.time_us,
                          "completion does not match actual world")
            self.finished, self.phase = True, "finished"
            self._terminal_raw = raw
            return None
        if kind == "request_inputs":
            self._require(self.phase == "inputs", "input request in wrong phase")
            self._require(message["frame"] == self.frame
                          and message["sim_time_us"] == self.engine.time_us
                          and message["state_digest"] == self.engine.state_digest
                          and message["paused"] == self.engine.paused,
                          "initial/current world mismatch")
            commands = self.inputs(self.round)
            self._verify_boundary()
            self._require(type(commands) is list and len(commands) <= message["max_commands"],
                          "invalid or oversized local input batch")
            canonical_json(commands)
            sealed, sequence = [], self.seq
            for command in commands:
                self._validate_command(command)
                sequence = _integer(sequence + 1, "next local sequence", 1)
                sealed.append({"seq": sequence, "command": copy.deepcopy(command)})
            self.seq, self.sealed = sequence, sealed
            reply = self._message("inputs", round=self.round, commands=self.sealed)
            self.phase = "prepare"
        elif kind == "prepare":
            self._require(self.phase == "prepare", "plan in wrong phase")
            self._require(message["manifest_digest"] == self.manifest
                          and canonical_json(message["capabilities"]) == canonical_json(self.capabilities)
                          and canonical_json(message["roster"]) == canonical_json(list(ROSTER))
                          and message["step_us"] == self.step_us
                          and message["frame"] == self.frame
                          and message["sim_time_us"] == self.engine.time_us
                          and message["pre_state_digest"] == self.engine.state_digest
                          and message["paused"] == self.engine.paused,
                          "plan is not for actual world/configuration")
            last = dict(self._last_seq)
            counts = {origin: 0 for origin in ROSTER}
            previous = None
            for item in message["commands"]:
                origin, seq = item["origin"], item["seq"]
                order = (ROSTER.index(origin), seq)
                self._require(previous is None or previous < order, "plan command order is not canonical")
                self._require(seq == last[origin] + 1, "plan remote/local sequence is not contiguous")
                last[origin], previous = seq, order
                counts[origin] += 1
                self._require(counts[origin] <= MAX_COMMANDS_PER_PEER, "peer input batch too large")
            own = [{"seq": c["seq"], "command": c["command"]}
                   for c in message["commands"] if c["origin"] == self.peer]
            self._require(canonical_json(own) == canonical_json(self.sealed),
                          "plan changed or omitted sealed local input")
            self._last_seq = last
            self.plan = copy.deepcopy(message)
            self.next_index = 0
            self.phase = "actions"
            reply = self._message("prepared", round=self.round, plan_hash=self.plan["plan_hash"])
        elif kind == "apply":
            self._check_action(message)
            self._require(message["index"] == self.next_index, "wrong command index")
            self._require(self.next_index < len(self.plan["commands"]), "extra command")
            expected = self.plan["commands"][self.next_index]
            actual = {name: message[name] for name in ("origin", "seq", "command")}
            self._require(canonical_json(actual) == canonical_json(expected)
                          and message["command_key"] == f'{expected["origin"]}:{expected["seq"]}',
                          "command differs from prepared plan")
            before_time, before_pause = self.engine.time_us, self.engine.paused
            receipt = self.engine.apply(copy.deepcopy(message["command"]), message["command_key"])
            canonical_json(receipt)
            self._require(type(receipt) is dict and set(receipt) == {"success", "result", "state_digest"}
                          and type(receipt["success"]) is bool, "invalid adapter command receipt")
            canonical_json(receipt["result"], limit=MAX_RESULT_BYTES)
            actual_state, actual_time, actual_pause = self._boundary()
            self._require(receipt["state_digest"] == actual_state,
                          "adapter receipt does not match actual world")
            self._require(actual_time == before_time, "command advanced simulation time")
            expected_pause = (message["command"]["value"]
                              if receipt["success"] and message["command"]["op"] == "SET_PAUSED"
                              else before_pause)
            self._require(actual_pause is expected_pause, "command changed pause without ordered authorization")
            self._expected_boundary = (actual_state, actual_time, actual_pause)
            reply = self._message("applied", round=self.round, plan_hash=self.plan["plan_hash"],
                                  index=self.next_index, **receipt)
            self.next_index += 1
            if receipt["success"] is False:
                # Return the failure for the coordinator, but close the local gate now.
                self.halted, self.reason, self.phase = True, "adapter command failed", "halted"
        elif kind == "step":
            self._check_action(message)
            self._require(self.next_index == len(self.plan["commands"]), "step before commands finished")
            next_round = _integer(self.round + 1, "next round")
            dt = 0 if self.engine.paused else self.step_us
            self._require(message["dt_us"] == dt and message["frame"] == self.frame + 1
                          and message["sim_time_us"] == self.engine.time_us + dt,
                          "incorrect simulation permit")
            before_state, _, before_pause = self._expected_boundary
            result = self.engine.step(dt)
            canonical_json(result)
            self._require(type(result) is dict and set(result) == {"state_digest", "sim_time_us"},
                          "invalid adapter step receipt")
            _integer(result["sim_time_us"], "adapter step time")
            actual_state, actual_time, actual_pause = self._boundary()
            self._require(result["state_digest"] == actual_state
                          and result["sim_time_us"] == actual_time == message["sim_time_us"]
                          and actual_pause is before_pause, "engine violated step permit")
            self._require(dt != 0 or actual_state == before_state, "paused step changed world")
            self._expected_boundary = (actual_state, actual_time, actual_pause)
            self.frame = message["frame"]
            reply = self._message("stepped", round=self.round, plan_hash=self.plan["plan_hash"],
                                  frame=self.frame, **result)
            self.round = next_round
            self.phase = "inputs"
        else:
            raise ProtocolError("unknown coordinator message")
        canonical_json(reply)
        self.cache[key] = (raw, copy.deepcopy(reply))
        self.cache = {k: v for k, v in self.cache.items() if k[1] >= self.round - 2}
        return copy.deepcopy(reply)

    def _check_action(self, message):
        self._require(self.phase == "actions" and self.plan
                      and message["plan_hash"] == self.plan["plan_hash"], "action without matching prepared plan")
