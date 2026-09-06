"""Fail-closed two-replica protocol, independent of sockets and Transport Fever 2.

The coordinator never executes commands. A replica must execute only ``apply``
and ``step`` actions, exactly once, and report their actual outcomes. In
particular, collecting or sealing local input MUST NOT change the engine.

Wire messages use canonical, integer-only JSON. Digests are SHA-256 hex strings;
their meaning and coverage are the adapter's responsibility. Matching advertised
capabilities and matching digests do not establish that an engine is deterministic.

``frame`` is a protocol step token, incremented even for a paused, zero-time step.
It is not necessarily the game's native frame counter. ``sim_time_us`` must be
read from the adapter and must not advance during a paused step. SET_PAUSED uses
``{"op": "SET_PAUSED", "value": bool}`` and participates in normal command order.
No other speed or pause controls may bypass the adapter.

An immutable epoch and roster prohibit automatic rejoin. After a halt, create a
new coordinator/epoch only after both adapters have explicitly loaded and checked
the same starting state. There is no timeout recovery or speculative execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from typing import Callable


ROSTER = ("a", "b")
CAPABILITIES = ("command_barrier", "fixed_step", "sealed_inputs", "state_digest")
MAX_INT = (1 << 53) - 1
MAX_MESSAGE_BYTES = 65536
MAX_COMMAND_BYTES = 8192
MAX_RESULT_BYTES = 16384
MAX_COMMANDS_PER_PEER = 32
MAX_DEPTH = 12
MAX_NODES = 4096
RETAINED_ROUNDS = 4
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_EPOCH = re.compile(r"[A-Za-z0-9_-]{8,128}\Z")


class ProtocolError(ValueError):
    """Malformed, incompatible, out-of-order, or conflicting protocol input."""


def canonical_json(value: object, *, limit: int = MAX_MESSAGE_BYTES) -> bytes:
    """Return deterministic UTF-8 JSON, rejecting coercions and unbounded input.

    Only plain dict/list/str/int/bool/None values are accepted. Floats (including
    finite floats), non-string keys, lone UTF-16 surrogates, cycles, and integers
    outside the interoperable JSON integer range are rejected. Physical values
    should be supplied as explicitly scaled integer units by adapters.
    """
    remaining = MAX_NODES

    def check(item: object, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise ProtocolError("JSON complexity limit exceeded")
        kind = type(item)
        if item is None or kind is bool:
            return
        if kind is int:
            if not -MAX_INT <= item <= MAX_INT:
                raise ProtocolError("JSON integer outside supported range")
            return
        if kind is str:
            try:
                encoded = item.encode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise ProtocolError("invalid Unicode string") from exc
            if len(encoded) > MAX_MESSAGE_BYTES:
                raise ProtocolError("JSON string too large")
            return
        if kind is list:
            if len(item) > MAX_NODES:
                raise ProtocolError("JSON array too large")
            for child in item:
                check(child, depth + 1)
            return
        if kind is dict:
            if len(item) > MAX_NODES:
                raise ProtocolError("JSON object too large")
            for key, child in item.items():
                if type(key) is not str:
                    raise ProtocolError("JSON object keys must be strings")
                check(key, depth + 1)
                check(child, depth + 1)
            return
        raise ProtocolError("unsupported JSON value type")

    check(value, 0)
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > limit:
        raise ProtocolError("JSON byte limit exceeded")
    return encoded


def digest(value: object) -> str:
    """SHA-256 of this protocol's canonical JSON representation."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def decode_message(raw: bytes) -> dict:
    """Decode one bounded JSON message; reject duplicate keys and NaN/Infinity.

    Transport framing and authentication belong to the caller. A generic
    json.loads without duplicate-key rejection must not be used on wire data.
    """
    if type(raw) is not bytes or len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("invalid wire message size/type")

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ProtocolError("duplicate JSON object key")
            result[key] = value
        return result

    def reject_constant(_: str) -> None:
        raise ProtocolError("non-finite JSON number")

    try:
        message = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                             parse_constant=reject_constant)
        canonical_json(message)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProtocolError("invalid JSON message") from exc
    if type(message) is not dict:
        raise ProtocolError("wire message must be an object")
    return message


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_INT:
        raise ProtocolError(f"invalid {name}")
    return value


def _hash(value: object, name: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ProtocolError(f"invalid {name}")
    return value


def _keys(message: dict, names: set[str]) -> None:
    if set(message) != {"kind", "epoch"} | names:
        raise ProtocolError("missing or unexpected message fields")


class Coordinator:
    """Pure state machine with fixed peers ``a`` and ``b``.

    ``receive(peer, message)`` returns ``[(recipient, message), ...]``. The caller
    must deliver every returned action reliably and in order, call ``tick`` at
    bounded intervals, and call ``disconnect`` when either socket is lost.
    Identical duplicates yield no output; the transport must not depend on ack
    retransmission. A late duplicate older than the bounded retained history
    halts instead of being treated as a new acknowledgement.

    Initial input: hello(manifest_digest, capabilities, state_digest, frame,
    sim_time_us, paused). The manifest must describe actual loaded game/mod
    binaries; state_digest must describe the actual loaded world, not a selected
    save file. Both peers must supply the same complete values.

    Each round: request_inputs -> inputs(commands=[{seq,command}]) -> prepare ->
    prepared(plan_hash) -> apply -> applied(index,success,result,state_digest),
    repeated for each command -> step -> stepped(frame,sim_time_us,state_digest).
    Every message after hello includes round; all messages after inputs include
    plan_hash. All messages carry kind and epoch. Sequence numbers start at 1
    independently for each peer and remain contiguous across rounds.
    """

    def __init__(self, epoch: str, manifest_digest: str,
                 capabilities: tuple[str, ...] = CAPABILITIES,
                 step_us: int = 100000, timeout_s: float = 10.0,
                 clock: Callable[[], float] = time.monotonic):
        if type(epoch) is not str or _EPOCH.fullmatch(epoch) is None:
            raise ValueError("epoch must be 8-128 ASCII letters/digits/_/-")
        _hash(manifest_digest, "manifest_digest")
        _integer(step_us, "step_us", 1)
        if step_us > 10_000_000:
            raise ValueError("step_us exceeds 10 seconds")
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or timeout_s <= 0 or timeout_s > 3600):
            raise ValueError("invalid timeout_s")
        if (type(capabilities) not in (tuple, list) or not capabilities
                or len(capabilities) > 32
                or any(type(c) is not str or not 1 <= len(c) <= 64 for c in capabilities)
                or len(set(capabilities)) != len(capabilities)):
            raise ValueError("invalid capabilities")
        self._epoch = epoch
        self._manifest_digest = manifest_digest
        self._capabilities = tuple(sorted(capabilities))
        self._step_us = step_us
        self._timeout_s = float(timeout_s)
        self._clock = clock
        self._last_now = float(clock())
        if not math.isfinite(self._last_now):
            raise ValueError("invalid clock")
        self._deadline = self._last_now + self._timeout_s
        self.halted = False
        self.halt_reason = ""
        self.round = 0
        self.phase = "hello"
        self.frame = 0
        self.sim_time_us = 0
        self.state_digest = ""
        self.paused = False
        self.plan_hash = ""
        self._hello: dict[str, dict] = {}
        self._inputs: dict[str, list] = {}
        self._prepared: set[str] = set()
        self._applied: dict[str, dict] = {}
        self._stepped: dict[str, dict] = {}
        self._commands: list[dict] = []
        self._index = 0
        self._last_seq = {peer: 0 for peer in ROSTER}
        self._seen: dict[tuple, bytes] = {}
        self._step_frame = 0
        self._step_time = 0

    @property
    def epoch(self) -> str:
        return self._epoch

    @property
    def roster(self) -> tuple[str, str]:
        return ROSTER

    def _broadcast(self, kind: str, **fields: object) -> list[tuple[str, dict]]:
        # Fresh objects prevent one transport/replica mutating another's action.
        raw = canonical_json({"kind": kind, "epoch": self.epoch, **fields})
        return [(peer, json.loads(raw)) for peer in ROSTER]

    def _halt(self, reason: str) -> list[tuple[str, dict]]:
        if self.halted:
            return []
        self.halted = True
        self.halt_reason = reason[:512]
        self.phase = "halted"
        return self._broadcast("halt", round=self.round, reason=self.halt_reason)

    def halt(self, reason: str) -> list[tuple[str, dict]]:
        """Explicit adapter/transport fatal error. This can never resume."""
        return self._halt(str(reason))

    def disconnect(self, peer: str, reason: str = "disconnected") -> list[tuple[str, dict]]:
        return self._halt(f"peer {peer}: {reason}")

    def tick(self, now: float | None = None) -> list[tuple[str, dict]]:
        if self.halted:
            return []
        moment = self._clock() if now is None else now
        if (type(moment) not in (int, float) or not math.isfinite(moment)
                or moment < self._last_now):
            return self._halt("invalid or backwards coordinator clock")
        self._last_now = float(moment)
        if moment >= self._deadline:
            return self._halt(f"timeout waiting in {self.phase} round {self.round}")
        return []

    def _enter(self, phase: str) -> None:
        self.phase = phase
        self._deadline = self._last_now + self._timeout_s

    def receive(self, peer: str, message: dict) -> list[tuple[str, dict]]:
        """Validate one input atomically and return the next authorized actions."""
        expired = self.tick()
        if self.halted:
            return expired
        try:
            if type(peer) is not str or peer not in ROSTER:
                raise ProtocolError("unknown peer; roster is immutable")
            raw = canonical_json(message)
            if type(message) is not dict:
                raise ProtocolError("message must be an object")
            # Deep-copy caller-owned data before accepting any input.
            message = json.loads(raw)
            key = self._validate(message)
            cache_key = (peer, *key)
            previous = self._seen.get(cache_key)
            if previous is not None:
                if previous != raw:
                    raise ProtocolError("conflicting duplicate message")
                return []
            if message["kind"] != "hello" and message["round"] != self.round:
                raise ProtocolError("message is from a different round")
            handler = getattr(self, "_on_" + message["kind"])
            actions = handler(peer, message)
            self._seen[cache_key] = raw
            self._prune_seen()
            return actions
        except ProtocolError as exc:
            return self._halt(str(exc))

    def _validate(self, message: dict) -> tuple:
        if message.get("epoch") != self.epoch:
            raise ProtocolError("wrong epoch; reconnect/rejoin is forbidden")
        kind = message.get("kind")
        if kind == "hello":
            _keys(message, {"manifest_digest", "capabilities", "state_digest",
                            "frame", "sim_time_us", "paused"})
            _hash(message["manifest_digest"], "manifest_digest")
            _hash(message["state_digest"], "state_digest")
            _integer(message["frame"], "frame")
            _integer(message["sim_time_us"], "sim_time_us")
            if type(message["paused"]) is not bool:
                raise ProtocolError("paused must be a boolean")
            caps = message["capabilities"]
            if type(caps) is not list or caps != list(self._capabilities):
                raise ProtocolError("capability mismatch; canonical sorted list required")
            if message["manifest_digest"] != self._manifest_digest:
                raise ProtocolError("manifest mismatch")
            return (kind, -1, -1)
        if kind == "inputs":
            _keys(message, {"round", "commands"})
            commands = message["commands"]
            if type(commands) is not list or len(commands) > MAX_COMMANDS_PER_PEER:
                raise ProtocolError("invalid or oversized input batch")
            for item in commands:
                if type(item) is not dict or set(item) != {"seq", "command"}:
                    raise ProtocolError("invalid command envelope")
                _integer(item["seq"], "sequence", 1)
                command = item["command"]
                if (type(command) is not dict or type(command.get("op")) is not str
                        or not 1 <= len(command["op"]) <= 64):
                    raise ProtocolError("command requires a bounded string op")
                canonical_json(command, limit=MAX_COMMAND_BYTES)
                if command["op"] == "SET_PAUSED":
                    if set(command) != {"op", "value"} or type(command["value"]) is not bool:
                        raise ProtocolError("SET_PAUSED requires only boolean value")
        elif kind == "prepared":
            _keys(message, {"round", "plan_hash"})
        elif kind == "applied":
            _keys(message, {"round", "plan_hash", "index", "success", "result", "state_digest"})
            _integer(message["index"], "command index")
            if type(message["success"]) is not bool:
                raise ProtocolError("success must be a boolean")
            _hash(message["state_digest"], "state_digest")
            canonical_json(message["result"], limit=MAX_RESULT_BYTES)
        elif kind == "stepped":
            _keys(message, {"round", "plan_hash", "frame", "sim_time_us", "state_digest"})
            _integer(message["frame"], "frame")
            _integer(message["sim_time_us"], "sim_time_us")
            _hash(message["state_digest"], "state_digest")
        else:
            raise ProtocolError("unknown message kind")
        _integer(message["round"], "round")
        if kind != "inputs":
            _hash(message["plan_hash"], "plan_hash")
        return (kind, message["round"], message.get("index", -1))

    def _require(self, phase: str, message: dict | None = None) -> None:
        if self.phase != phase:
            raise ProtocolError(f"unexpected input during {self.phase}; expected {phase}")
        if message is not None and message["plan_hash"] != self.plan_hash:
            raise ProtocolError("plan hash mismatch")

    def _on_hello(self, peer: str, message: dict) -> list[tuple[str, dict]]:
        self._require("hello")
        self._hello[peer] = message
        if len(self._hello) != len(ROSTER):
            return []
        if self._hello["a"] != self._hello["b"]:
            raise ProtocolError("actual initial state/frame/time/pause mismatch")
        self.frame = message["frame"]
        self.sim_time_us = message["sim_time_us"]
        self.state_digest = message["state_digest"]
        self.paused = message["paused"]
        return self._request_inputs()

    def _request_inputs(self) -> list[tuple[str, dict]]:
        self._inputs.clear()
        self._prepared.clear()
        self._applied.clear()
        self._stepped.clear()
        self._commands = []
        self._index = 0
        self.plan_hash = ""
        self._enter("inputs")
        return self._broadcast("request_inputs", round=self.round, frame=self.frame,
                               sim_time_us=self.sim_time_us, state_digest=self.state_digest,
                               paused=self.paused, max_commands=MAX_COMMANDS_PER_PEER)

    def _on_inputs(self, peer: str, message: dict) -> list[tuple[str, dict]]:
        self._require("inputs")
        expected = self._last_seq[peer] + 1
        for item in message["commands"]:
            if item["seq"] != expected:
                raise ProtocolError("input sequence is not contiguous")
            expected += 1
        self._last_seq[peer] = expected - 1
        self._inputs[peer] = message["commands"]
        if len(self._inputs) != len(ROSTER):
            return []
        self._commands = [
            {"origin": origin, "seq": item["seq"], "command": item["command"]}
            for origin in ROSTER for item in self._inputs[origin]
        ]
        plan = {"round": self.round, "commands": self._commands, "frame": self.frame,
                "sim_time_us": self.sim_time_us, "pre_state_digest": self.state_digest,
                "paused": self.paused, "step_us": self._step_us,
                "manifest_digest": self._manifest_digest,
                "capabilities": list(self._capabilities), "roster": list(ROSTER)}
        self.plan_hash = digest({"epoch": self.epoch, **plan})
        self._enter("prepared")
        return self._broadcast("prepare", plan_hash=self.plan_hash, **plan)

    def _on_prepared(self, peer: str, message: dict) -> list[tuple[str, dict]]:
        self._require("prepared", message)
        self._prepared.add(peer)
        if len(self._prepared) != len(ROSTER):
            return []
        return self._next_action()

    def _next_action(self) -> list[tuple[str, dict]]:
        self._applied.clear()
        if self._index < len(self._commands):
            item = self._commands[self._index]
            self._enter("applied")
            return self._broadcast("apply", round=self.round, plan_hash=self.plan_hash,
                                   index=self._index, command_key=f"{item['origin']}:{item['seq']}",
                                   **item)
        dt_us = 0 if self.paused else self._step_us
        self._step_frame = _integer(self.frame + 1, "next frame")
        self._step_time = _integer(self.sim_time_us + dt_us, "next simulation time")
        self._enter("stepped")
        return self._broadcast("step", round=self.round, plan_hash=self.plan_hash,
                               frame=self._step_frame, dt_us=dt_us,
                               sim_time_us=self._step_time)

    def _on_applied(self, peer: str, message: dict) -> list[tuple[str, dict]]:
        self._require("applied", message)
        if message["index"] != self._index:
            raise ProtocolError("wrong command index")
        if message["success"] is not True:
            raise ProtocolError(f"command {self._index} failed at peer {peer}")
        self._applied[peer] = message
        if len(self._applied) != len(ROSTER):
            return []
        if canonical_json(self._applied["a"]) != canonical_json(self._applied["b"]):
            raise ProtocolError(f"command {self._index} result/state mismatch")
        self.state_digest = message["state_digest"]
        command = self._commands[self._index]["command"]
        if command["op"] == "SET_PAUSED":
            self.paused = command["value"]
        self._index += 1
        return self._next_action()

    def _on_stepped(self, peer: str, message: dict) -> list[tuple[str, dict]]:
        self._require("stepped", message)
        if message["frame"] != self._step_frame or message["sim_time_us"] != self._step_time:
            raise ProtocolError("step completed at wrong frame/simulation time")
        self._stepped[peer] = message
        if len(self._stepped) != len(ROSTER):
            return []
        if self._stepped["a"] != self._stepped["b"]:
            raise ProtocolError("post-step state mismatch")
        self.frame = self._step_frame
        self.sim_time_us = self._step_time
        self.state_digest = message["state_digest"]
        self.round = _integer(self.round + 1, "next round")
        return self._request_inputs()

    def _prune_seen(self) -> None:
        cutoff = self.round - RETAINED_ROUNDS
        for key in list(self._seen):
            if key[1] != "hello" and key[2] < cutoff:
                del self._seen[key]


def verify_plan(message: dict) -> bool:
    """Replica helper: verify a prepare digest without changing an engine.

    This checks the canonical envelope/hash, not the peer's own sealed inputs or
    actual engine state. A replica must also compare those before acknowledging.
    """
    try:
        canonical_json(message)
        if type(message) is not dict or message.get("kind") != "prepare":
            return False
        expected = {"kind", "epoch", "plan_hash", "round", "commands", "frame",
                    "sim_time_us", "pre_state_digest", "paused", "step_us",
                    "manifest_digest", "capabilities", "roster"}
        if set(message) != expected:
            return False
        payload = {key: value for key, value in message.items() if key not in ("kind", "plan_hash")}
        return _hash(message["plan_hash"], "plan_hash") == digest(payload)
    except ProtocolError:
        return False
