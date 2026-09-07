"""Bounded launcher-input experiment; the accepted stream pacer is unchanged.

Both input queues are sealed at a held native frontier. A fresh shared world
precedes each nonempty batch, and every actual command result is compared before
another native grant. This does not capture native game UI or construction.
"""
from __future__ import annotations

import copy
import json
import time

from .build_profile import BUILD_ROUNDS
from .core import Coordinator, ProtocolError, ROSTER, canonical_json, digest, _hash, _integer
from .replica import Replica
from .stream_probe import STEP_US, CHUNK_STEPS, CHECKPOINT_STEPS, _world, _take_world, _check_advance
from .timing_probe import _metrics as _wait_metrics

ID = "live-input-v1"
LIVE_CAPABILITY = "live_input_v1"
MAX_CYCLES = 2048
MAX_REQUESTS = 128  # Per peer, including END_TEST.
MAX_BATCH_REQUESTS = 8
MAX_STEPS = 3000
MAX_ACTIONS = 10000
POLL_MS = 200
LONG_PAUSE_MS = 35000
MAX_PAUSE_RECEIPT_BYTES = 1024
_NATIVE_FIELDS = frozenset(("completed_frame", "pending_state", "pending_frame", "pending_dt_us",
    "completed_dt_us", "time_before_ms", "time_after_ms", "native_step_us", "request_received",
    "request_acknowledged", "request_completed", "ready", "initialized", "armed", "outer_calls", "hold_calls", "updated_ms"))
LIVE_WORLD_RECEIPTS = frozenset(("live_ready", "live_checkpointed", "live_applied", "live_held", "live_finished"))
_WORLD = {"frame", "sim_time_us", "paused", "state_digest"}
_FRONTIER = {"frame", "sim_time_us"}
_COMMON = {"kind", "epoch", "round", "index", "plan_hash"}
_REPLIES = {
    "live_ready": _WORLD, "live_sealed": _FRONTIER | {"cycle", "requests"},
    "live_advanced": _FRONTIER | {"metrics"}, "live_checkpointed": _WORLD,
    "live_committed": {"batch_hash"}, "live_applied": _WORLD | {"receipt"},
    "live_settled": {"batch_hash"}, "live_held": _WORLD | {"metrics"}, "live_finished": _WORLD,
}
_ACTIONS = {
    "live_start": _WORLD | {"manifest_digest", "schedule"},
    "live_poll": _FRONTIER | {"cycle"}, "live_advance": _FRONTIER | {"steps"},
    "live_checkpoint": _FRONTIER | {"reason"},
    "live_commit": _WORLD | {"cycle", "requests", "batch_hash"},
    "live_apply": _WORLD | {"request", "command_key", "batch_hash"},
    "live_settle": {"batch_hash", "outcomes"}, "live_hold": _WORLD | {"duration_ms"},
    "live_finish": _WORLD,
}


def _need(condition, reason):
    if not condition:
        raise ProtocolError("live probe: " + reason)


def schedule():
    return {"id": ID, "step_us": STEP_US, "chunk_steps": CHUNK_STEPS,
            "checkpoint_steps": CHECKPOINT_STEPS, "max_steps": MAX_STEPS,
            "max_cycles": MAX_CYCLES, "max_requests_per_peer": MAX_REQUESTS,
            "max_batch_requests_per_peer": MAX_BATCH_REQUESTS, "poll_ms": POLL_MS,
            "long_pause_ms": LONG_PAUSE_MS, "conflict_rule": "resume_before_pause_pause_wins",
            "input_ops": ["SET_PAUSED", "END_TEST"]}


def _requests(value, previous):
    _need(type(value) is list and len(value) <= MAX_BATCH_REQUESTS, "input batch exceeds bounds")
    canonical_json(value, limit=3000)
    for index, item in enumerate(value):
        _need(type(item) is dict and set(item) == {"seq", "command"}, "invalid input request")
        _integer(item["seq"], "request sequence", 1)
        _need(item["seq"] == previous + index + 1 <= MAX_REQUESTS, "request sequence is not contiguous or exceeds limit")
        command = item["command"]
        _need(type(command) is dict, "invalid input command")
        if command.get("op") == "SET_PAUSED":
            _need(set(command) == {"op", "value"} and type(command["value"]) is bool, "invalid pause request")
        else:
            _need(command == {"op": "END_TEST"} and index == len(value) - 1, "invalid or nonterminal END_TEST")
    return copy.deepcopy(value)


def _ordered(requests):
    items = [{"peer": peer, **item} for peer in ROSTER for item in requests[peer]]
    return sorted((item for item in items if item["command"]["op"] == "SET_PAUSED"),
                  key=lambda item: (item["command"]["value"], item["peer"], item["seq"]))


def _batch(cycle, requests, boundary):
    return {"cycle": cycle, "requests": requests, **boundary}


def _receipt(value, world):
    canonical_json(value, limit=MAX_PAUSE_RECEIPT_BYTES)
    _need(type(value) is dict and set(value) == {"success", "result", "state_digest"}
          and value["success"] is True and value["state_digest"] == world["state_digest"],
          "command lacks a successful fresh receipt")


def _hold_metrics(value):
    _need(type(value) is dict and value.get("kind") == "stream_hold", "invalid paused heartbeat metrics")
    converted = copy.deepcopy(value)
    converted["kind"] = "idle_wait"
    _wait_metrics(converted, "ready", delay=POLL_MS)
    for name in ("native_before", "native_after"):
        _need(value[name] is None or set(value[name]) <= _NATIVE_FIELDS,
              "heartbeat contains unknown native metrics")
    return copy.deepcopy(value)


class _LiveState:
    def _init_live(self):
        self._live_started = self._live_complete = self._ending = False
        self._live_start = self._live_plan = self._last_world = None
        self._confirmed_paused = None
        self._steps = self._cycle = self._checkpoint_steps = 0
        self._requests_seen = {peer: 0 for peer in ROSTER}
        self._acknowledged = {peer: 0 for peer in ROSTER}
        self._engine_seq = {"a": 7, "b": 5}
        self._counts = {peer: {"pause": 0, "resume": 0, "end": 0} for peer in ROSTER}
        self._transitions = {peer: {"pause": 0, "resume": 0} for peer in ROSTER}
        self._chunks, self._checkpoints, self._batches, self._outcomes, self._holds = [], [], [], [], []
        self._command_records = []
        self._conflicts = 0
        self._pause_ms = {peer: 0 for peer in ROSTER}
        self._longest_pause_ms = {peer: 0 for peer in ROSTER}
        self._pause_started = None
        self._pause_clock = self._clock if isinstance(self, Coordinator) else time.monotonic
        self._live_started_ns = self._live_finished_ns = None
        self._batch_requests = {peer: [] for peer in ROSTER}
        self._batch_hash = ""
        self._batch_order, self._batch_outcomes = [], []
        self._batch_cursor = 0

    def _accept_batch(self, requests, boundary):
        self._batch_requests = copy.deepcopy(requests)
        self._batch_order = _ordered(requests)
        self._batch_outcomes = []
        self._batch_cursor = 0
        values = {item["command"]["value"] for item in self._batch_order}
        cross_peer_conflict = any(a["command"]["value"] != b["command"]["value"]
            for a in self._batch_order if a["peer"] == "a"
            for b in self._batch_order if b["peer"] == "b")
        if cross_peer_conflict:
            self._conflicts += 1
        for peer in ROSTER:
            for item in requests[peer]:
                op = item["command"]
                name = "end" if op["op"] == "END_TEST" else "pause" if op["value"] else "resume"
                self._counts[peer][name] += 1
                self._requests_seen[peer] = item["seq"]
                self._ending |= name == "end"
        self._batches.append({"cycle": self._cycle, "batch_hash": self._batch_hash,
                              "requests": copy.deepcopy(requests), "boundary": copy.deepcopy(boundary),
                              "conflict": len(values) == 2, "cross_peer_conflict": cross_peer_conflict})

    def _applied_outcome(self, request, before, after, receipt):
        name = "pause" if request["command"]["value"] else "resume"
        changed = before["paused"] != after["paused"]
        if changed:
            self._transitions[request["peer"]][name] += 1
        if before["paused"]:
            self._measure_pause()
        if changed:
            self._pause_started = self._pause_clock() if after["paused"] else None
            self._pause_ms = {peer: 0 for peer in ROSTER}
        outcome = {**copy.deepcopy(request), "status": "applied", "changed_pause": changed,
                   "frame": after["frame"], "sim_time_us": after["sim_time_us"],
                   "receipt_digest": digest(receipt)}
        self._command_records.append({"request": copy.deepcopy(request), "before": copy.deepcopy(before),
                                      "after": copy.deepcopy(after), "receipt": copy.deepcopy(receipt)})
        self._batch_outcomes.append(outcome)
        self._batch_cursor += 1

    def _settled_outcomes(self):
        outcomes = copy.deepcopy(self._batch_outcomes)
        for peer in ROSTER:
            for item in self._batch_requests[peer]:
                if item["command"]["op"] == "END_TEST":
                    outcomes.append({"peer": peer, **copy.deepcopy(item), "status": "accepted_end",
                                     "frame": self._last_world["frame"], "sim_time_us": self._last_world["sim_time_us"]})
        return outcomes

    def _confirm_outcomes(self, outcomes):
        self._outcomes.extend(copy.deepcopy(outcomes))
        self._confirmed_paused = self._last_world["paused"]
        for peer in ROSTER:
            self._acknowledged[peer] = self._requests_seen[peer]

    def _measure_pause(self):
        _need(self._pause_started is not None, "paused measurement lacks its confirmed start")
        elapsed = int((self._pause_clock() - self._pause_started) * 1000)
        _integer(elapsed, "continuous measured pause")
        for peer in ROSTER if isinstance(self, Coordinator) else (self.peer,):
            _need(elapsed >= self._pause_ms[peer], "pause measurement clock moved backwards")
            self._pause_ms[peer] = elapsed
            self._longest_pause_ms[peer] = max(self._longest_pause_ms[peer], self._pause_ms[peer])

    def _record_hold(self, metrics):
        # Only called after a fresh, unchanged paused world was validated. The
        # host interval spans joint boundary confirmations; peers use independent
        # local monotonic clocks. Inter-heartbeat IPC and network waits count too.
        self._measure_pause()

    def live_progress(self):
        wrapper = getattr(self, "stream_engine", None)
        world = self._last_world or {}
        return {"started": self._live_started, "completed": self._live_complete and not self.halted,
                "stage": self.phase, "cycle": self._cycle, "advanced_steps": self._steps,
                "frame": wrapper.frame if wrapper else self.frame,
                "sim_time_us": wrapper.time_us if wrapper else getattr(self, "sim_time_us", world.get("sim_time_us")),
                "paused": wrapper.paused if wrapper else getattr(self, "paused", world.get("paused")),
                "confirmed_paused": self._confirmed_paused,
                "paused_duration_ms": min(self._pause_ms.values()) if isinstance(self, Coordinator) else self._pause_ms[self.peer],
                "long_pause_met": all(self._longest_pause_ms[peer] >= LONG_PAUSE_MS
                                      for peer in (ROSTER if isinstance(self, Coordinator) else (self.peer,))),
                "last_observed_frame": wrapper.last_observed_frame if wrapper else world.get("frame"),
                "last_observed_time_us": wrapper.last_observed_time_us if wrapper else world.get("sim_time_us"),
                "acknowledged_seq": dict(self._acknowledged), "requests": copy.deepcopy(self._counts),
                "ending": self._ending, "acknowledgements": copy.deepcopy(self._outcomes[-16:])}

    def live_report(self):
        progress = self.live_progress()
        joint = isinstance(self, Coordinator)
        peers = ROSTER if joint else (self.peer,)
        per_peer = {peer: all(self._transitions[peer][name] > 0 for name in ("pause", "resume")) for peer in ROSTER}
        long_pause = all(self._longest_pause_ms[peer] >= LONG_PAUSE_MS for peer in peers)
        coverage = {"per_peer_pause_resume": per_peer, "long_pause_met": long_pause,
                    "long_pause_scope": "both_peers" if joint else "local_peer_only",
                    "pause_duration_scope": "coordinator_monotonic_between_joint_fresh_paused_boundaries" if joint else
                        "local_monotonic_between_fresh_paused_boundaries",
                    "longest_measured_pause_ms": dict(self._longest_pause_ms),
                    "conflict_batches": self._conflicts, "total_requests": sum(self._requests_seen.values()),
                    "applied_pause_transitions": copy.deepcopy(self._transitions)}
        return {"id": ID, "completed": progress["completed"],
                "completion_scope": "both_peer_fresh_world_boundaries" if joint else "local_fresh_world_boundary",
                "required_interactions_met": (progress["completed"] and all(per_peer.values()) and long_pause),
                "coverage": coverage, "progress": progress, "schedule": schedule(),
                "last_confirmed_native_frame": progress["frame"], "last_confirmed_native_sim_time_us": progress["sim_time_us"],
                "native_frontier_scope": "both_peers_acknowledged_native_frontier" if joint else "local_acknowledged_native_frontier",
                "last_observed_frame": progress["last_observed_frame"], "last_observed_sim_time_us": progress["last_observed_time_us"],
                "start": copy.deepcopy(self._live_start), "chunk_records": copy.deepcopy(self._chunks),
                "checkpoint_records": copy.deepcopy(self._checkpoints), "input_batches": copy.deepcopy(self._batches),
                "outcomes": copy.deepcopy(self._outcomes), "hold_records": copy.deepcopy(self._holds),
                "command_records": copy.deepcopy(self._command_records),
                "end_to_end_duration_ms": None if self._live_started_ns is None else
                    ((self._live_finished_ns or time.monotonic_ns()) - self._live_started_ns) // 1000000,
                "world_observation": "fresh_start_input_batches_commands_periodic_checkpoints_paused_heartbeats_and_finish",
                "native_ui_input_capture": False, "full_world_verified": False, "visual_smoothness_verified": False}


class LiveCoordinator(_LiveState, Coordinator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _need(self._step_us == STEP_US and LIVE_CAPABILITY in self._capabilities, "live capability and quantum required")
        self._init_live()
        self._operation = -1
        self._replies = {}
        self._offsets = {peer: (0, 0) for peer in ROSTER}

    def _request_inputs(self):
        if self.round < BUILD_ROUNDS:
            return super()._request_inputs()
        _need(self.round == BUILD_ROUNDS and not self._live_started and self.paused is False,
              "live mode requires the completed unpaused build")
        self._live_started, self._live_started_ns = True, time.monotonic_ns()
        self._live_start = self._last_world = _world({"frame": self.frame, "sim_time_us": self.sim_time_us,
            "state_digest": self.state_digest, "paused": self.paused})
        self._live_plan = {"epoch": self.epoch, "round": BUILD_ROUNDS, "index": 0,
            "manifest_digest": self._manifest_digest, "schedule": schedule(), **self._live_start}
        self.plan_hash = digest(self._live_plan)
        return self._send("live_start", "live_ready", manifest_digest=self._manifest_digest, schedule=schedule(), **self._live_start)

    def _send(self, kind, expected, **fields):
        self._operation += 1
        _need(self._operation < MAX_ACTIONS, "operation limit reached; end the test earlier")
        self._replies = {}
        self._enter(expected)
        return self._broadcast(kind, round=BUILD_ROUNDS, index=self._operation, plan_hash=self.plan_hash, **fields)

    def _validate(self, message):
        kind = message.get("kind")
        if kind not in _REPLIES:
            return super()._validate(message)
        _need(set(message) == _COMMON | _REPLIES[kind] and message["epoch"] == self.epoch
              and message["round"] == BUILD_ROUNDS, "invalid live reply envelope")
        _integer(message["index"], "operation index")
        _need(message["index"] < MAX_ACTIONS, "reply exceeds operation limit")
        _hash(message["plan_hash"], "live plan")
        if kind in LIVE_WORLD_RECEIPTS:
            _take_world(message)
        if kind == "live_sealed":
            _integer(message["cycle"], "input cycle")
        return kind, message["round"], message["index"]

    def _collect(self, peer, message, phase):
        self._require(phase, message)
        _need(message["index"] == self._operation, "reply belongs to another operation")
        self._replies[peer] = message
        return len(self._replies) == 2

    def _worlds(self):
        world = _take_world(self._replies["a"])
        _need(world == _take_world(self._replies["b"]), "fresh peer worlds differ")
        self._last_world = world
        self.state_digest, self.paused = world["state_digest"], world["paused"]
        self._confirmed_paused = self.paused
        return world

    def _at_frontier(self, message, paused=None):
        _need(message["frame"] == self.frame and message["sim_time_us"] == self.sim_time_us,
              "reply is not at the granted native frontier")
        if paused is not None:
            _need(message["paused"] is paused, "unexpected pause state")

    def _poll(self):
        _need(self._cycle < MAX_CYCLES, "input cycle limit reached; end the test earlier")
        return self._send("live_poll", "live_sealed", cycle=self._cycle, frame=self.frame, sim_time_us=self.sim_time_us)

    def _continue(self):
        if self._ending:
            return self._send("live_finish", "live_finished", **self._last_world)
        if self.paused:
            return self._send("live_hold", "live_held", duration_ms=POLL_MS, **self._last_world)
        _need(self._steps + CHUNK_STEPS <= MAX_STEPS, "native step limit reached; end the test earlier")
        return self._send("live_advance", "live_advanced", frame=self.frame, sim_time_us=self.sim_time_us, steps=CHUNK_STEPS)

    def _on_live_ready(self, peer, message):
        _need(_take_world(message) == self._live_start, "live start differs from the completed build")
        if self._collect(peer, message, "live_ready"):
            self._worlds()
            return self._poll()
        return []

    def _on_live_sealed(self, peer, message):
        self._at_frontier(message)
        _need(message["cycle"] == self._cycle, "wrong sealed input cycle")
        _requests(message["requests"], self._requests_seen[peer])
        if not self._collect(peer, message, "live_sealed"):
            return []
        self._pending_requests = {origin: self._replies[origin]["requests"] for origin in ROSTER}
        nonempty = any(self._pending_requests.values())
        if nonempty or self._steps - self._checkpoint_steps >= CHECKPOINT_STEPS:
            self._checkpoint_reason = "inputs" if nonempty else "periodic"
            return self._send("live_checkpoint", "live_checkpointed", reason=self._checkpoint_reason,
                              frame=self.frame, sim_time_us=self.sim_time_us)
        self._cycle += 1
        return self._continue()

    def _on_live_checkpointed(self, peer, message):
        self._at_frontier(message, self.paused)
        if self.paused:
            _need(_take_world(message) == self._last_world, "paused world changed before input checkpoint")
        if not self._collect(peer, message, "live_checkpointed"):
            return []
        world = self._worlds()
        self._checkpoint_steps = self._steps
        self._checkpoints.append({"index": self._operation, "reason": self._checkpoint_reason, "boundary": world})
        if self._checkpoint_reason == "inputs":
            self._batch_hash = digest(_batch(self._cycle, self._pending_requests, world))
            self._accept_batch(self._pending_requests, world)
            return self._send("live_commit", "live_committed", cycle=self._cycle,
                requests=self._batch_requests, batch_hash=self._batch_hash, **world)
        self._cycle += 1
        return self._continue()

    def _on_live_committed(self, peer, message):
        _need(message["batch_hash"] == self._batch_hash, "wrong committed input batch")
        if self._collect(peer, message, "live_committed"):
            return self._next_command()
        return []

    def _next_command(self):
        if self._batch_cursor == len(self._batch_order):
            outcomes = self._settled_outcomes()
            self._confirm_outcomes(outcomes)
            return self._send("live_settle", "live_settled", batch_hash=self._batch_hash, outcomes=outcomes)
        request = self._batch_order[self._batch_cursor]
        key = request["peer"] + ":" + str(self._engine_seq[request["peer"]] + 1)
        return self._send("live_apply", "live_applied", request=request, command_key=key,
                          batch_hash=self._batch_hash, **self._last_world)

    def _on_live_applied(self, peer, message):
        request = self._batch_order[self._batch_cursor]
        self._at_frontier(message, request["command"]["value"])
        _receipt(message["receipt"], message)
        if not self._collect(peer, message, "live_applied"):
            return []
        before = self._last_world
        _need(self._replies["a"]["receipt"] == self._replies["b"]["receipt"], "command callback results differ")
        world = self._worlds()
        self._engine_seq[request["peer"]] += 1
        self._applied_outcome(request, before, world, message["receipt"])
        return self._next_command()

    def _on_live_settled(self, peer, message):
        _need(message["batch_hash"] == self._batch_hash, "wrong settlement batch")
        if self._collect(peer, message, "live_settled"):
            self._cycle += 1
            return self._continue()
        return []

    def _on_live_advanced(self, peer, message):
        before = {"frame": self.frame, "sim_time_us": self.sim_time_us}
        _need(message["frame"] == self.frame + CHUNK_STEPS and
              message["sim_time_us"] == self.sim_time_us + CHUNK_STEPS * STEP_US, "incorrect native range acknowledgement")
        _check_advance(message["metrics"], before, self._offsets[peer])
        if not self._collect(peer, message, "live_advanced"):
            return []
        metrics = {}
        for origin in ROSTER:
            metrics[origin], self._offsets[origin] = _check_advance(self._replies[origin]["metrics"], before, self._offsets[origin])
        self.frame, self.sim_time_us = message["frame"], message["sim_time_us"]
        self._steps += CHUNK_STEPS
        self._chunks.append({"index": self._operation, "frontier": {"frame": self.frame, "sim_time_us": self.sim_time_us}, "peers": metrics})
        return self._poll()

    def _on_live_held(self, peer, message):
        _need(_take_world(message) == self._last_world and message["paused"] is True, "paused world changed during heartbeat")
        _hold_metrics(message["metrics"])
        if not self._collect(peer, message, "live_held"):
            return []
        self._worlds()
        metrics = {origin: self._replies[origin]["metrics"] for origin in ROSTER}
        self._record_hold(metrics)
        self._holds.append({"index": self._operation, "boundary": self._last_world, "peers": metrics})
        return self._poll()

    def _on_live_finished(self, peer, message):
        _need(self._ending and _take_world(message) == self._last_world, "end checkpoint changed the held world")
        if self._collect(peer, message, "live_finished"):
            self._worlds()
            self._live_complete, self._live_finished_ns = True, time.monotonic_ns()
            self._enter("inputs")
        return []


class LiveReplica(_LiveState, Replica):
    def __init__(self, *args, live_input_source=None, stop_requested=None, stream_engine_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        _need(self.step_us == STEP_US and LIVE_CAPABILITY in self.capabilities, "live capability and quantum required")
        self._init_live()
        self.stream_engine = None
        self._live_source = live_input_source or (lambda: [])
        self._live_factory, self._live_stop = stream_engine_factory, stop_requested
        self._live_cache = {}
        self._operation = 0
        self._offsets = (0, 0)
        self._frontier = None
        self._sealed = []
        self._next = {"live_start"}

    def _fresh(self, receipt=None):
        wrapper = self.stream_engine
        _need(wrapper is not None and wrapper.observations_fresh is True, "world observation is historical")
        world = _world({"frame": wrapper.frame, "sim_time_us": wrapper.time_us,
                        "paused": wrapper.paused, "state_digest": self.engine.state_digest})
        if receipt is not None:
            _need(world == _world(receipt), "fresh receipt disagrees with observed engine")
        self.frame = world["frame"]
        self._expected_boundary = self._boundary()
        self._frontier = {key: world[key] for key in _FRONTIER}
        self._last_world = world
        return world

    def _reply(self, kind, message, **fields):
        return self._message(kind, round=BUILD_ROUNDS, index=message["index"], plan_hash=message["plan_hash"], **fields)

    def _receive(self, message):
        kind = message.get("kind") if type(message) is dict else None
        if kind not in _ACTIONS:
            if self._live_started and not self._live_complete and kind != "halt":
                raise ProtocolError("live probe: normal protocol inside live session")
            if kind == "complete" and self.round >= BUILD_ROUNDS:
                _need(self._live_complete, "completion before fresh joint end barrier")
            return super()._receive(message)
        raw = canonical_json(message)
        message = json.loads(raw)
        _need(set(message) == _COMMON | _ACTIONS[kind] and message["epoch"] == self.epoch
              and message["round"] == self.round == BUILD_ROUNDS, "invalid live action envelope")
        _integer(message["index"], "live operation index")
        _hash(message["plan_hash"], "live plan")
        _need(message["index"] < MAX_ACTIONS, "operation limit exceeded")
        key = kind, message["index"]
        if key in self._live_cache:
            cached = self._live_cache[key]
            _need(raw == cached[0], "conflicting duplicate live action")
            return copy.deepcopy(cached[1])
        _need(message["index"] == self._operation and kind in self._next, "missing or reordered live operation")
        if kind != "live_start":
            _need(self._live_started and message["plan_hash"] == digest(self._live_plan), "uncommitted live plan")
        result = getattr(self, "_do_" + kind[5:])(message)
        self._operation += 1
        self._live_cache[key] = raw, copy.deepcopy(result)
        if not self._live_complete:
            self.phase = next(iter(sorted(self._next)))
        return result

    def _do_start(self, message):
        _need(not self._live_started and self.phase == "inputs" and message["index"] == 0, "live mode cannot restart")
        self._verify_boundary()
        before = _world({"frame": self.frame, "sim_time_us": self.engine.time_us,
                         "paused": self.engine.paused, "state_digest": self.engine.state_digest})
        plan = {"epoch": self.epoch, "round": BUILD_ROUNDS, "index": 0,
                "manifest_digest": self.manifest, "schedule": schedule(), **before}
        _need(before["paused"] is False and {k: v for k, v in message.items() if k not in ("kind", "plan_hash")} == plan
              and message["plan_hash"] == digest(plan), "live start plan differs from approved schedule/build")
        factory = self._live_factory
        if factory is None:
            from .stream_engine import StreamEngine
            factory = StreamEngine
        self.stream_engine = factory(self.engine, stop_requested=self._live_stop)
        actual = self._fresh(self.stream_engine.checkpoint())
        _need(actual == before, "world changed before live start")
        self._live_started, self._live_started_ns = True, time.monotonic_ns()
        self._live_start, self._live_plan = actual, plan
        self._next = {"live_poll"}
        return self._reply("live_ready", message, **actual)

    def _same_frontier(self, message):
        _need(all(message[key] == self._frontier[key] for key in _FRONTIER)
              and self.stream_engine.frame == self._frontier["frame"]
              and self.stream_engine.time_us == self._frontier["sim_time_us"], "live operation has wrong native frontier")

    def _after_batch(self):
        self._next = {"live_finish"} if self._ending else {"live_hold"} if self.stream_engine.paused else {"live_advance"}

    def _do_poll(self, message):
        self._same_frontier(message)
        _integer(message["cycle"], "input cycle")
        _need(message["cycle"] == self._cycle < MAX_CYCLES and not self._ending, "wrong or exhausted input cycle")
        if self._confirmed_paused is None:
            self._confirmed_paused = self._live_start["paused"]
        self._sealed = _requests(self._live_source(), self._requests_seen[self.peer])
        self._next = {"live_checkpoint"}
        if not self._sealed and self._steps - self._checkpoint_steps < CHECKPOINT_STEPS:
            self._next.add("live_hold" if self.stream_engine.paused else "live_advance")
        return self._reply("live_sealed", message, cycle=self._cycle, requests=self._sealed, **self._frontier)

    def _do_checkpoint(self, message):
        self._same_frontier(message)
        reason = message["reason"]
        _need(reason in ("inputs", "periodic") and
              (reason != "periodic" or not self._sealed and self._steps - self._checkpoint_steps >= CHECKPOINT_STEPS),
              "checkpoint reason does not match input cycle")
        paused = self.stream_engine.paused
        before = self._last_world
        world = self._fresh(self.stream_engine.checkpoint())
        _need(world["paused"] is paused and all(world[key] == message[key] for key in _FRONTIER), "checkpoint moved native boundary")
        _need(not paused or world == before, "paused world changed before input checkpoint")
        self._checkpoint_steps = self._steps
        self._checkpoints.append({"index": message["index"], "reason": reason, "boundary": world})
        if reason == "inputs":
            self._next = {"live_commit"}
        else:
            self._cycle += 1
            self._after_batch()
        return self._reply("live_checkpointed", message, **world)

    def _do_commit(self, message):
        world = self._fresh()
        _integer(message["cycle"], "input cycle")
        _need(_take_world(message) == world and message["cycle"] == self._cycle, "batch targets another checkpoint")
        requests = message["requests"]
        _need(type(requests) is dict and set(requests) == set(ROSTER), "batch lacks both sealed queues")
        for peer in ROSTER:
            _requests(requests[peer], self._requests_seen[peer])
        _need(any(requests.values()) and requests[self.peer] == self._sealed,
              "host altered or omitted the locally sealed queue")
        _need(message["batch_hash"] == digest(_batch(self._cycle, requests, world)), "wrong input batch hash")
        self._batch_hash = message["batch_hash"]
        self._accept_batch(requests, world)
        self._next = {"live_apply"} if self._batch_order else {"live_settle"}
        return self._reply("live_committed", message, batch_hash=self._batch_hash)

    def _do_apply(self, message):
        before = self._fresh()
        request = self._batch_order[self._batch_cursor]
        expected_key = request["peer"] + ":" + str(self._engine_seq[request["peer"]] + 1)
        _need(_take_world(message) == before and message["batch_hash"] == self._batch_hash
              and message["request"] == request and message["command_key"] == expected_key,
              "command differs from committed deterministic input order")
        receipt = self.stream_engine.apply(request["command"], expected_key)
        after = self._fresh()
        _receipt(receipt, after)
        _need(after["paused"] is request["command"]["value"] and
              all(after[key] == before[key] for key in _FRONTIER), "live command changed native time or failed to set pause")
        self._engine_seq[request["peer"]] += 1
        self._applied_outcome(request, before, after, receipt)
        self._next = {"live_apply"} if self._batch_cursor < len(self._batch_order) else {"live_settle"}
        return self._reply("live_applied", message, **after, receipt=receipt)

    def _do_settle(self, message):
        _need(message["batch_hash"] == self._batch_hash and message["outcomes"] == self._settled_outcomes(),
              "joint settlement differs from actual command outcomes")
        self._confirm_outcomes(message["outcomes"])
        self._cycle += 1
        self._after_batch()
        return self._reply("live_settled", message, batch_hash=self._batch_hash)

    def _do_advance(self, message):
        self._same_frontier(message)
        _need(not self.stream_engine.paused and not self._ending and message["steps"] == CHUNK_STEPS
              and self._steps + CHUNK_STEPS <= MAX_STEPS, "invalid live advancing grant")
        # An empty seal uses no separate settlement message.
        if "live_checkpoint" in self._next:
            self._cycle += 1
        before = dict(self._frontier)
        result = self.stream_engine.advance(CHUNK_STEPS)
        _need(type(result) is dict and set(result) == _FRONTIER | {"metrics"}, "native receipt carries historical world data")
        _need(result["frame"] == before["frame"] + CHUNK_STEPS == self.stream_engine.frame and
              result["sim_time_us"] == before["sim_time_us"] + CHUNK_STEPS * STEP_US == self.stream_engine.time_us
              and self.stream_engine.observations_fresh is False, "native advance receipt is not current")
        metrics, self._offsets = _check_advance(result["metrics"], before, self._offsets)
        self.frame = result["frame"]
        self._frontier = {key: result[key] for key in _FRONTIER}
        self._steps += CHUNK_STEPS
        self._chunks.append({"index": message["index"], "frontier": dict(self._frontier), "metrics": metrics})
        self._next = {"live_poll"}
        return self._reply("live_advanced", message, **self._frontier, metrics=metrics)

    def _do_hold(self, message):
        before = self._fresh()
        _need(before["paused"] is True and _take_world(message) == before and message["duration_ms"] == POLL_MS,
              "invalid paused heartbeat")
        if "live_checkpoint" in self._next:
            self._cycle += 1
        receipt = self.stream_engine.hold(POLL_MS)
        _need(type(receipt) is dict and set(receipt) == _WORLD | {"metrics"}, "invalid heartbeat receipt")
        after = self._fresh(_take_world(receipt))
        _need(after == before, "world changed during paused heartbeat")
        metrics = _hold_metrics(receipt["metrics"])
        self._record_hold({self.peer: metrics})
        self._holds.append({"index": message["index"], "boundary": after, "metrics": metrics})
        self._next = {"live_poll"}
        return self._reply("live_held", message, **after, metrics=metrics)

    def _do_finish(self, message):
        _need(self._ending and _take_world(message) == self._fresh(), "uncommitted end request")
        world = self._fresh(self.stream_engine.checkpoint())
        _need(world == _take_world(message), "end checkpoint changed the held world")
        self._live_complete, self._live_finished_ns = True, time.monotonic_ns()
        self.phase, self._next = "inputs", set()
        return self._reply("live_finished", message, **world)
