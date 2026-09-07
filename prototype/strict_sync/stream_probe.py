"""Fixed continuous-step experiment, with world hashes only at fresh checkpoints.

This adds no player-input capture. Empty tick ranges and two scheduled commands
are committed before execution; native-only receipts never carry a world hash.
"""
from __future__ import annotations

import copy
import json
import time

from .build_profile import BUILD_ROUNDS
from .core import Coordinator, ProtocolError, ROSTER, canonical_json, digest, _hash, _integer
from .replica import Replica
from .timing_probe import PACE_THRESHOLDS, _metrics as _wait_metrics, _stats

ID = "paced-stream-v1"
STREAM_CAPABILITY = CAPABILITY = "paced_stream_v1"
STEP_US = 200000
CHUNK_STEPS = 2
CHECKPOINT_STEPS = 50
TOTAL_STEPS = 600
CHECKPOINTS = TOTAL_STEPS // CHECKPOINT_STEPS
PAUSE_AT = 300
HOLD_MS = 2000
STREAM_WORLD_RECEIPTS = frozenset(("stream_ready", "stream_checkpointed", "stream_applied", "stream_held"))
_WORLD = {"frame", "sim_time_us", "paused", "state_digest"}
_FRONTIER = {"frame", "sim_time_us"}
_COMMON = {"kind", "epoch", "round", "index", "plan_hash"}
_COMMANDS = (("a:8", True), ("b:6", False))


def schedule():
    return {"id": ID, "step_us": STEP_US, "chunk_steps": CHUNK_STEPS,
            "checkpoint_steps": CHECKPOINT_STEPS, "total_steps": TOTAL_STEPS,
            "empty_ranges": [[0, PAUSE_AT], [PAUSE_AT, TOTAL_STEPS]],
            "changes": [{"after_steps": PAUSE_AT, "command_key": key,
                         "command": {"op": "SET_PAUSED", "value": value}}
                        for key, value in _COMMANDS], "hold_ms": HOLD_MS}


def _need(condition, reason):
    if not condition:
        raise ProtocolError("stream probe: " + reason)


def _world(value):
    _need(type(value) is dict and set(value) == _WORLD, "invalid fresh world boundary")
    _integer(value["frame"], "world frame")
    _integer(value["sim_time_us"], "world time")
    _hash(value["state_digest"], "fresh world digest")
    _need(type(value["paused"]) is bool, "invalid world pause")
    return copy.deepcopy(value)


def _take_world(value):
    return _world({name: value[name] for name in _WORLD})


def _check_advance(value, before, previous=None):
    canonical_json(value, limit=12000)
    fields = {"kind", "steps_requested", "step_us", "simulated_us", "duration_ms", "steps",
              "world_observation", "clock_origin", "native_clock_each_step"}
    _need(type(value) is dict and set(value) == fields and value["kind"] == "stream_advance",
          "invalid native-only metrics schema")
    for field in ("steps_requested", "step_us", "simulated_us", "duration_ms"):
        _integer(value[field], field)
    _need(value["steps_requested"] == CHUNK_STEPS and value["step_us"] == STEP_US
          and value["simulated_us"] == CHUNK_STEPS * STEP_US,
          "chunk differs from the committed step range")
    _need(value["world_observation"] == "none" and value["native_clock_each_step"] is True
          and value["clock_origin"] == "stream_local_monotonic", "invalid native-only observation scope")
    steps = value["steps"]
    _need(type(steps) is list and len(steps) == CHUNK_STEPS, "missing native step measurements")
    call, ack = previous or (0, 0)
    step_fields = {"frame", "sim_time_us", "scheduled_offset_us", "call_started_offset_us",
                   "ack_observed_offset_us", "permit_duration_us", "lateness_us",
                   "native_time_before_ms", "native_time_after_ms"}
    for index, item in enumerate(steps):
        _need(type(item) is dict and set(item) == step_fields, "invalid native step metrics")
        for name, number in item.items():
            _integer(number, name)
        target = before["sim_time_us"] + (index + 1) * STEP_US
        _need(item["frame"] == before["frame"] + index + 1 and item["sim_time_us"] == target,
              "missing or reordered native step")
        _need(item["native_time_after_ms"] * 1000 == target
              and item["native_time_before_ms"] * 1000 in (target - STEP_US, target),
              "native step clock differs from granted time")
        started, observed = item["call_started_offset_us"], item["ack_observed_offset_us"]
        _need(observed >= started >= ack and started + 1 >= call + STEP_US
              and started + 1 >= item["scheduled_offset_us"],
              "step timings moved backwards or permit a catch-up burst")
        _need(abs(item["permit_duration_us"] - (observed - started)) <= 1
              and abs(item["lateness_us"] - max(0, started - item["scheduled_offset_us"])) <= 1,
              "native step durations disagree with timestamp offsets")
        call, ack = started, observed
    _need(value["duration_ms"] * 1000 + 1 >= ack - steps[0]["call_started_offset_us"],
          "chunk duration is shorter than its permit observations")
    return copy.deepcopy(value), (call, ack)


def _check_hold(metrics):
    _need(type(metrics) is dict and metrics.get("kind") == "stream_hold", "invalid pause hold metrics")
    converted = copy.deepcopy(metrics)
    converted["kind"] = "idle_wait"
    _wait_metrics(converted, "ready", delay=HOLD_MS)
    return copy.deepcopy(metrics)


def _start_plan(epoch, manifest, boundary):
    return {"epoch": epoch, "round": BUILD_ROUNDS, "index": 0,
            "manifest_digest": manifest, "schedule": schedule(), **boundary}


def _pace(chunks):
    steps = [step for chunk in chunks for step in chunk["steps"]]
    halves, checks = [], []
    for offset in (0, PAUSE_AT):
        part = steps[offset:offset + PAUSE_AT]
        if len(part) != PAUSE_AT:
            return None, {"steps_measured": len(steps), "halves": halves}
        span = part[-1]["ack_observed_offset_us"] - part[0]["call_started_offset_us"] + STEP_US
        rate = round(len(part) * STEP_US * 1000000 / max(1, span))
        call_intervals = [right["call_started_offset_us"] - left["call_started_offset_us"]
                          for left, right in zip(part, part[1:])]
        ack_intervals = [right["ack_observed_offset_us"] - left["ack_observed_offset_us"]
                         for left, right in zip(part, part[1:])]
        call, ack = _stats(call_intervals), _stats(ack_intervals)
        passed = (PACE_THRESHOLDS["rate_ppm_min"] <= rate <= PACE_THRESHOLDS["rate_ppm_max"]
                  and all(item["count"] == PAUSE_AT - 1
                          and item["p95_us"] <= PACE_THRESHOLDS["interval_p95_us_max"]
                          and item["max_us"] <= PACE_THRESHOLDS["interval_max_us_max"] for item in (call, ack)))
        checks.append(passed)
        halves.append({"first_step": offset + 1, "steps": len(part), "span_us": span,
                       "rate_ppm": rate, "call_intervals": call, "ack_intervals": ack, "target_met": passed})
    return all(checks), {"steps_measured": len(steps), "halves": halves,
                         "chunk_method_duration_ms": sum(chunk["duration_ms"] for chunk in chunks)}


class _StreamReport:
    def _init_stream(self):
        self._stream_started = self._stream_complete = False
        self._stream_start = None
        self._stream_plan = None
        self._stream_steps = 0
        self._stream_chunks = []
        self._stream_checkpoints = []
        self._stream_commands = []
        self._stream_hold = None
        self._stream_started_ns = self._stream_finished_ns = None

    def stream_progress(self):
        backend = getattr(self, "stream_engine", None)
        return {"started": self._stream_started, "completed": self._stream_complete,
                "stage": self.phase, "advanced_steps": self._stream_steps, "total_steps": TOTAL_STEPS,
                "checkpoint_index": len(self._stream_checkpoints), "checkpoint_total": CHECKPOINTS,
                "frame": backend.frame if backend else self.frame, "last_observed_frame": (backend.last_observed_frame if backend else
                    self._stream_checkpoints[-1]["boundary"]["frame"] if self._stream_checkpoints else
                    self._stream_start["frame"] if self._stream_start else None),
                "last_observed_time_us": (backend.last_observed_time_us if backend else
                    self._stream_checkpoints[-1]["boundary"]["sim_time_us"] if self._stream_checkpoints else
                    self._stream_start["sim_time_us"] if self._stream_start else None)}

    def stream_report(self):
        completed = self._stream_complete and not self.halted
        progress = self.stream_progress()
        backend = getattr(self, "stream_engine", None)
        confirmed_time = (backend.time_us if backend else self.sim_time_us
                          if isinstance(self, Coordinator) else self.engine.time_us)
        peers = {}
        for item in self._stream_chunks:
            for peer, metrics in (item["peers"].items() if "peers" in item else [(self.peer, item["metrics"])]):
                peers.setdefault(peer, []).append(metrics)
        summaries, checks = {}, []
        for peer, chunks in peers.items():
            check, summary = _pace(chunks)
            checks.append(check)
            summaries[peer] = summary
        elapsed = (None if self._stream_started_ns is None else max(0,
            ((self._stream_finished_ns or time.monotonic_ns()) - self._stream_started_ns) // 1000000))
        return {"id": ID, "completed": completed,
                "completion_scope": "both_peer_checkpoint_boundaries" if isinstance(self, Coordinator) else "local_checkpoint_boundaries",
                "advanced_steps": self._stream_steps, "total_steps": TOTAL_STEPS,
                "last_confirmed_native_frame": progress["frame"],
                "last_confirmed_native_sim_time_us": confirmed_time,
                "native_frontier_scope": ("both_peers_acknowledged_native_frontier"
                                          if isinstance(self, Coordinator) else "local_acknowledged_native_frontier"),
                "last_observed_frame": progress["last_observed_frame"],
                "last_observed_sim_time_us": progress["last_observed_time_us"],
                "advanced_steps_scope": "completed_two_step_chunks_only",
                "checkpoints_completed": len(self._stream_checkpoints), "checkpoints_expected": CHECKPOINTS,
                "chunk_steps": CHUNK_STEPS, "step_us": STEP_US, "schedule": schedule(),
                "start": copy.deepcopy(self._stream_start), "chunk_records": copy.deepcopy(self._stream_chunks),
                "checkpoint_records": copy.deepcopy(self._stream_checkpoints),
                "pause_proof": {"completed": len(self._stream_commands) == 2 and self._stream_hold is not None,
                                "commands": copy.deepcopy(self._stream_commands), "hold": copy.deepcopy(self._stream_hold)},
                "paced_stream_1x_met": all(check is True for check in checks) if completed and checks else None,
                "peer_timing_summaries": summaries, "pace_thresholds": dict(PACE_THRESHOLDS),
                "end_to_end_duration_ms": elapsed,
                "target_scope": "two_300_step_spans_including_ordinary_checkpoints_excluding_midpoint_pause_gap",
                "span_definition": "last_ACK_minus_first_permit_call_plus_one_step_period",
                "timestamp_scope": "local_Python_permit_call_starts_and_observed_native_ACKs_not_native_arrival_or_render_frames",
                "world_observation": "start_checkpoints_and_scheduled_commands_only",
                "native_clock_each_step": True, "full_world_verified": False, "visual_smoothness_verified": False}


class StreamCoordinator(_StreamReport, Coordinator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _need(self._step_us == STEP_US and STREAM_CAPABILITY in self._capabilities,
              "explicit stream capability and quantum required")
        self._init_stream()
        self._stream_replies = {}
        self._stream_offsets = {peer: (0, 0) for peer in ROSTER}

    def _request_inputs(self):
        if self.round < BUILD_ROUNDS:
            return super()._request_inputs()
        _need(self.round == BUILD_ROUNDS and not self._stream_started and self.paused is False,
              "stream cannot skip or repeat the completed unpaused build boundary")
        self._stream_started = True
        self._stream_started_ns = time.monotonic_ns()
        self._stream_start = _world({"frame": self.frame, "sim_time_us": self.sim_time_us,
                                    "state_digest": self.state_digest, "paused": self.paused})
        self._stream_plan = _start_plan(self.epoch, self._manifest_digest, self._stream_start)
        self.plan_hash = digest(self._stream_plan)
        self._enter("stream_ready")
        return self._broadcast("stream_start", plan_hash=self.plan_hash,
            **{key: value for key, value in self._stream_plan.items() if key != "epoch"})

    def _validate(self, message):
        kind = message.get("kind")
        if kind not in STREAM_WORLD_RECEIPTS and kind != "stream_advanced":
            return super()._validate(message)
        extra = (_FRONTIER | {"metrics"} if kind == "stream_advanced" else
                 _WORLD | ({"metrics"} if kind == "stream_held" else {"receipt"} if kind == "stream_applied" else set()))
        _need(set(message) == _COMMON | extra, "invalid stream reply envelope")
        _need(message["epoch"] == self.epoch and message["round"] == BUILD_ROUNDS, "wrong stream epoch or round")
        _integer(message["index"], "stream reply index")
        _need(message["index"] <= TOTAL_STEPS // CHUNK_STEPS, "stream reply index exceeds fixed bounds")
        _hash(message["plan_hash"], "stream plan")
        if kind == "stream_advanced":
            for field in _FRONTIER:
                _integer(message[field], field)
            canonical_json(message["metrics"], limit=12000)
        else:
            _take_world(message)
        return kind, message["round"], message["index"]

    def _collect(self, peer, message, phase, index):
        self._require(phase, message)
        _need(message["index"] == index, "reply is for the wrong scheduled operation")
        self._stream_replies[peer] = message
        return len(self._stream_replies) == len(ROSTER)

    def _matching_worlds(self):
        world = _take_world(self._stream_replies["a"])
        _need(world == _take_world(self._stream_replies["b"]), "fresh checkpoint worlds differ between peers")
        return world

    def _send(self, kind, phase, index, **fields):
        self._stream_replies = {}
        self._enter(phase)
        return self._broadcast(kind, round=BUILD_ROUNDS, index=index, plan_hash=self.plan_hash, **fields)

    def _grant_chunk(self):
        _need(self._stream_steps < TOTAL_STEPS and self.paused is False, "no advancing grant at this boundary")
        return self._send("stream_advance", "stream_advanced", self._stream_steps // CHUNK_STEPS,
                          frame=self.frame, sim_time_us=self.sim_time_us, steps=CHUNK_STEPS)

    def _on_stream_ready(self, peer, message):
        _need(_take_world(message) == self._stream_start, "fresh stream start differs from the build result")
        if not self._collect(peer, message, "stream_ready", 0):
            return []
        self._matching_worlds()
        return self._grant_chunk()

    def _on_stream_advanced(self, peer, message):
        _need(message["frame"] == self.frame + CHUNK_STEPS
              and message["sim_time_us"] == self.sim_time_us + CHUNK_STEPS * STEP_US,
              "native frontier differs from granted range")
        metrics, offsets = _check_advance(message["metrics"],
            {"frame": self.frame, "sim_time_us": self.sim_time_us}, self._stream_offsets[peer])
        if not self._collect(peer, message, "stream_advanced", self._stream_steps // CHUNK_STEPS):
            return []
        # Store both measured clocks independently; their wall timings need not match.
        for origin in ROSTER:
            item = self._stream_replies[origin]
            _, self._stream_offsets[origin] = _check_advance(item["metrics"],
                {"frame": self.frame, "sim_time_us": self.sim_time_us}, self._stream_offsets[origin])
        self.frame, self.sim_time_us = message["frame"], message["sim_time_us"]
        self._stream_steps += CHUNK_STEPS
        self._stream_chunks.append({"index": self._stream_steps // CHUNK_STEPS - 1,
            "frontier": {"frame": self.frame, "sim_time_us": self.sim_time_us},
            "peers": {origin: self._stream_replies[origin]["metrics"] for origin in ROSTER}})
        if self._stream_steps % CHECKPOINT_STEPS == 0:
            return self._send("stream_checkpoint", "stream_checkpointed", self._stream_steps // CHECKPOINT_STEPS,
                              frame=self.frame, sim_time_us=self.sim_time_us)
        return self._grant_chunk()

    def _on_stream_checkpointed(self, peer, message):
        _need(message["frame"] == self.frame and message["sim_time_us"] == self.sim_time_us
              and message["paused"] is False, "checkpoint is not at the granted frontier")
        if not self._collect(peer, message, "stream_checkpointed", self._stream_steps // CHECKPOINT_STEPS):
            return []
        world = self._matching_worlds()
        self.state_digest = world["state_digest"]
        self._stream_checkpoints.append({"index": len(self._stream_checkpoints) + 1, "boundary": world})
        if self._stream_steps == TOTAL_STEPS:
            _need(len(self._stream_commands) == 2 and self._stream_hold is not None,
                  "final checkpoint lacks the scheduled pause proof")
            self._stream_complete = True
            self._stream_finished_ns = time.monotonic_ns()
            self._enter("inputs")
            return []
        if self._stream_steps == PAUSE_AT:
            return self._command(0)
        return self._grant_chunk()

    def _command(self, index):
        key, paused = _COMMANDS[index]
        return self._send("stream_apply", "stream_applied", index, frame=self.frame,
            sim_time_us=self.sim_time_us, state_digest=self.state_digest, paused=self.paused,
            command_key=key, command={"op": "SET_PAUSED", "value": paused})

    def _on_stream_applied(self, peer, message):
        index = len(self._stream_commands)
        _need(index < len(_COMMANDS) and message["frame"] == self.frame
              and message["sim_time_us"] == self.sim_time_us and message["paused"] is _COMMANDS[index][1],
              "scheduled command changed an unauthorized boundary")
        receipt = message["receipt"]
        _need(type(receipt) is dict and set(receipt) == {"success", "result", "state_digest"}
              and receipt["success"] is True and receipt["state_digest"] == message["state_digest"],
              "invalid scheduled command completion")
        canonical_json(receipt, limit=16384)
        if not self._collect(peer, message, "stream_applied", index):
            return []
        world = self._matching_worlds()
        _need(canonical_json(self._stream_replies["a"]["receipt"]) == canonical_json(self._stream_replies["b"]["receipt"]),
              "scheduled command results differ")
        self.state_digest, self.paused = world["state_digest"], world["paused"]
        self._stream_commands.append({"command_key": _COMMANDS[index][0], "boundary": world, "receipt": receipt})
        if index == 0:
            return self._send("stream_hold", "stream_held", 0, duration_ms=HOLD_MS, **world)
        return self._grant_chunk()

    def _on_stream_held(self, peer, message):
        _need(message["frame"] == self.frame and message["sim_time_us"] == self.sim_time_us
              and message["state_digest"] == self.state_digest and message["paused"] is True,
              "shared paused boundary changed during hold")
        _check_hold(message["metrics"])
        if not self._collect(peer, message, "stream_held", 0):
            return []
        self._matching_worlds()
        self._stream_hold = {"boundary": _take_world(message),
            "peers": {origin: self._stream_replies[origin]["metrics"] for origin in ROSTER}}
        return self._command(1)


class StreamReplica(_StreamReport, Replica):
    def __init__(self, *args, stop_requested=None, stream_engine_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        _need(self.step_us == STEP_US and STREAM_CAPABILITY in self.capabilities,
              "explicit stream capability and quantum required")
        self._init_stream()
        self.stream_engine = None
        self._stream_factory = stream_engine_factory
        self._stop_requested = stop_requested
        self._stream_cache = {}
        self._stream_offsets = (0, 0)
        self._stream_frontier = None

    def _fresh(self, receipt=None):
        wrapper = self.stream_engine
        _need(wrapper is not None and wrapper.observations_fresh is True,
              "world observation is historical, not a fresh checkpoint")
        actual = _world({"frame": wrapper.frame, "sim_time_us": wrapper.time_us,
                        "paused": wrapper.paused, "state_digest": self.engine.state_digest})
        if receipt is not None:
            _need(_world(receipt) == actual, "fresh receipt disagrees with the observed engine")
        self.frame = actual["frame"]
        self._expected_boundary = self._boundary()
        self._stream_frontier = {name: actual[name] for name in _FRONTIER}
        return actual

    def _reply(self, kind, message, **fields):
        return self._message(kind, round=BUILD_ROUNDS, index=message["index"],
                             plan_hash=message["plan_hash"], **fields)

    def _receive(self, message):
        kind = message.get("kind") if type(message) is dict else None
        kinds = {"stream_start", "stream_advance", "stream_checkpoint", "stream_apply", "stream_hold"}
        if kind not in kinds:
            if self._stream_started and not self._stream_complete and kind != "halt":
                raise ProtocolError("stream probe: normal protocol input inside a committed stream")
            if kind == "complete" and self.round >= BUILD_ROUNDS:
                _need(self._stream_complete, "completion arrived before all stream checkpoints")
            return super()._receive(message)
        raw = canonical_json(message)
        message = json.loads(raw)
        _need(self.round == BUILD_ROUNDS and message.get("round") == BUILD_ROUNDS
              and message.get("epoch") == self.epoch, "wrong stream epoch or build boundary")
        _integer(message.get("index"), "stream action index")
        _need(message["index"] <= TOTAL_STEPS // CHUNK_STEPS, "stream action index exceeds bounds")
        _hash(message.get("plan_hash"), "stream plan")
        extras = {"stream_start": _WORLD | {"manifest_digest", "schedule"},
                  "stream_advance": _FRONTIER | {"steps"}, "stream_checkpoint": _FRONTIER,
                  "stream_apply": _WORLD | {"command_key", "command"}, "stream_hold": _WORLD | {"duration_ms"}}
        _need(set(message) == _COMMON | extras[kind], "invalid stream action envelope")
        key = kind, message["index"]
        cached = self._stream_cache.get(key)
        if cached:
            _need(raw == cached[0], "conflicting duplicate stream action")
            return copy.deepcopy(cached[1])
        if kind == "stream_start":
            reply = self._start(message)
        else:
            _need(self._stream_started and message["plan_hash"] == digest(self._stream_plan), "uncommitted stream plan")
            if kind == "stream_advance":
                reply = self._advance(message)
            elif kind == "stream_checkpoint":
                reply = self._checkpoint(message)
            elif kind == "stream_apply":
                reply = self._apply_scheduled(message)
            else:
                reply = self._hold(message)
        self._stream_cache[key] = raw, copy.deepcopy(reply)
        return reply

    def _start(self, message):
        _need(not self._stream_started and self.phase == "inputs" and message["index"] == 0,
              "stream cannot restart")
        self._verify_boundary()
        before = _world({"frame": self.frame, "sim_time_us": self.engine.time_us,
                         "paused": self.engine.paused, "state_digest": self.engine.state_digest})
        _need(before["paused"] is False, "stream requires the unpaused build result")
        plan = _start_plan(self.epoch, self.manifest, before)
        received = {name: value for name, value in message.items() if name not in ("kind", "plan_hash")}
        _need(canonical_json(received) == canonical_json(plan) and message["plan_hash"] == digest(plan),
              "stream schedule differs from the fixed changes, empty ranges or build result")
        factory = self._stream_factory
        if factory is None:
            from .stream_engine import StreamEngine
            factory = StreamEngine
        self.stream_engine = factory(self.engine, stop_requested=self._stop_requested)
        actual = self._fresh(self.stream_engine.checkpoint())
        _need(actual == before, "world changed before the fresh stream start")
        self._stream_started, self._stream_started_ns = True, time.monotonic_ns()
        self._stream_start, self._stream_plan = actual, plan
        self.phase = "stream_advance"
        return self._reply("stream_ready", message, **actual)

    def _advance(self, message):
        _need(self.phase == "stream_advance" and self._stream_steps < TOTAL_STEPS
              and message["index"] == self._stream_steps // CHUNK_STEPS
              and message["steps"] == CHUNK_STEPS
              and all(message[name] == self._stream_frontier[name] for name in _FRONTIER),
              "advance differs from the next committed empty range")
        before = dict(self._stream_frontier)
        _need(self.stream_engine.frame == before["frame"] and self.stream_engine.time_us == before["sim_time_us"]
              and self.stream_engine.paused is False, "native frontier moved outside the stream")
        result = self.stream_engine.advance(CHUNK_STEPS)
        canonical_json(result, limit=14000)
        _need(type(result) is dict and set(result) == _FRONTIER | {"metrics"},
              "native-only receipt must not carry a historical world hash")
        _need(result["frame"] == before["frame"] + CHUNK_STEPS == self.stream_engine.frame
              and result["sim_time_us"] == before["sim_time_us"] + CHUNK_STEPS * STEP_US == self.stream_engine.time_us
              and self.stream_engine.observations_fresh is False, "invalid native frontier or stale observation flag")
        metrics, self._stream_offsets = _check_advance(result["metrics"], before, self._stream_offsets)
        self.frame = result["frame"]
        self._stream_frontier = {name: result[name] for name in _FRONTIER}
        self._stream_steps += CHUNK_STEPS
        self._stream_chunks.append({"index": message["index"], "frontier": dict(self._stream_frontier), "metrics": metrics})
        if self._stream_steps % CHECKPOINT_STEPS == 0:
            self.phase = "stream_checkpoint"
        return self._reply("stream_advanced", message, **self._stream_frontier, metrics=metrics)

    def _checkpoint(self, message):
        _need(self.phase == "stream_checkpoint" and self._stream_steps % CHECKPOINT_STEPS == 0
              and message["index"] == self._stream_steps // CHECKPOINT_STEPS
              and all(message[name] == self._stream_frontier[name] for name in _FRONTIER),
              "checkpoint is missing, reordered or for another frontier")
        actual = self._fresh(self.stream_engine.checkpoint())
        _need(actual["paused"] is False and all(actual[name] == message[name] for name in _FRONTIER),
              "fresh checkpoint differs from the native frontier")
        self._stream_checkpoints.append({"index": message["index"], "boundary": actual})
        if self._stream_steps == TOTAL_STEPS:
            _need(len(self._stream_commands) == 2 and self._stream_hold is not None, "missing scheduled pause proof")
            self._stream_complete = True
            self._stream_finished_ns = time.monotonic_ns()
            self.phase = "inputs"
        else:
            self.phase = "stream_pause" if self._stream_steps == PAUSE_AT else "stream_advance"
        return self._reply("stream_checkpointed", message, **actual)

    def _apply_scheduled(self, message):
        index = len(self._stream_commands)
        _need(index < 2 and self.phase == ("stream_pause" if index == 0 else "stream_resume")
              and message["index"] == index and self._stream_steps == PAUSE_AT,
              "command is not at its precommitted checkpoint")
        before = self._fresh()
        key, paused = _COMMANDS[index]
        _need(_take_world(message) == before and message["command_key"] == key
              and canonical_json(message["command"]) == canonical_json({"op": "SET_PAUSED", "value": paused}),
              "command differs from the immutable schedule")
        receipt = self.stream_engine.apply(message["command"], key)
        canonical_json(receipt, limit=16384)
        after = self._fresh()
        _need(type(receipt) is dict and set(receipt) == {"success", "result", "state_digest"}
              and receipt["success"] is True and receipt["state_digest"] == after["state_digest"]
              and after["paused"] is paused and all(after[name] == before[name] for name in _FRONTIER),
              "scheduled command did not complete at the held boundary")
        self._stream_commands.append({"command_key": key, "boundary": after, "receipt": copy.deepcopy(receipt)})
        self.phase = "stream_hold" if index == 0 else "stream_advance"
        return self._reply("stream_applied", message, **after, receipt=receipt)

    def _hold(self, message):
        _need(self.phase == "stream_hold" and message["index"] == 0 and message["duration_ms"] == HOLD_MS,
              "unexpected shared pause hold")
        before = self._fresh()
        _need(before["paused"] is True and _take_world(message) == before, "pause hold is for another world")
        receipt = self.stream_engine.hold(HOLD_MS)
        canonical_json(receipt, limit=14000)
        _need(type(receipt) is dict and set(receipt) == _WORLD | {"metrics"}, "invalid held world receipt")
        after = self._fresh(_take_world(receipt))
        _need(after == before, "shared paused world changed during hold")
        metrics = _check_hold(receipt["metrics"])
        self._stream_hold = {"boundary": after, "metrics": metrics}
        self.phase = "stream_resume"
        return self._reply("stream_held", message, **after, metrics=metrics)
