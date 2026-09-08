"""Guided fixed-action launcher experiment with input seals on existing replies.

This separate experiment adds bounded launcher guided action requests to the accepted
paced schedule. Every guided action gets a fresh read-only engine preview after all
preceding commands settled locally. Both peers must agree before application;
expected collisions reject without cost, unexpected callback failures halt.

Both input queues are sealed in ready, advancing and paused HOLD receipts, while
the engine is held at that receipt's frontier. The host needs both receipts and
seals before its next grant. Nonempty batches still require a fresh shared world,
compared callbacks and settlement. The accepted stream pacer is unchanged. This
does not capture native game UI or arbitrary construction.
"""
from __future__ import annotations

import copy
import json
import time

from .short_build_profile import SHORT_BUILD_ROUNDS, SHORT_ENGINE_SEQUENCES, SHORT_BUILD_CONTRACT
from .core import Coordinator, ProtocolError, ROSTER, canonical_json, digest, _hash, _integer
from .replica import Replica
from .guided_input import validate_command, validate_preview, validate_action_receipt
from .guided_catalog import STEPS, get_step, catalogue
from .stream_probe import STEP_US, CHUNK_STEPS, CHECKPOINT_STEPS, _world, _take_world, _check_advance
from .timing_probe import _metrics as _wait_metrics

ID = "guided-fixed-lifecycle-v1"
GUIDED_CAPABILITY = "guided_suite_v1"
MAX_CYCLES = 24000
MAX_REQUESTS = 128  # Matches the persistent live-input queue, per peer.
MAX_BATCH_REQUESTS = 8
MAX_STEPS = 12000
MAX_ACTIONS = 80000
POLL_MS = 200
LONG_PAUSE_MS = 35000
MAX_PAUSE_RECEIPT_BYTES = 1024
_NATIVE_FIELDS = frozenset(("completed_frame", "pending_state", "pending_frame", "pending_dt_us",
    "completed_dt_us", "time_before_ms", "time_after_ms", "native_step_us", "request_received",
    "request_acknowledged", "request_completed", "ready", "initialized", "armed", "outer_calls", "hold_calls", "updated_ms"))
GUIDED_WORLD_RECEIPTS = frozenset(("live_ready", "live_checkpointed", "live_applied", "live_held", "live_finished", "live_previewed", "live_rejected"))
_WORLD = {"frame", "sim_time_us", "paused", "state_digest"}
_FRONTIER = {"frame", "sim_time_us"}
_COMMON = {"kind", "epoch", "round", "index", "plan_hash"}
_SEAL = {"cycle", "requests"}
_REPLIES = {
    "live_ready": _WORLD | _SEAL,
    "live_advanced": _FRONTIER | {"metrics"} | _SEAL, "live_checkpointed": _WORLD,
    "live_committed": {"batch_hash"}, "live_applied": _WORLD | {"receipt"},
    "live_previewed": _WORLD | {"preview"}, "live_rejected": _WORLD | {"preview_digest"},
    "live_settled": {"batch_hash"}, "live_held": _WORLD | {"metrics"} | _SEAL, "live_finished": _WORLD,
}
_ACTIONS = {
    "live_start": _WORLD | {"manifest_digest", "schedule"},
    "live_advance": _FRONTIER | {"steps"},
    "live_checkpoint": _FRONTIER | {"reason"},
    "live_commit": _WORLD | {"cycle", "requests", "batch_hash"},
    "live_apply": _WORLD | {"request", "command_key", "batch_hash"},
    "live_preview": _WORLD | {"request", "command_key", "batch_hash"},
    "live_reject": _WORLD | {"request", "preview_digest", "batch_hash"},
    "live_settle": {"batch_hash", "outcomes"}, "live_hold": _WORLD | {"duration_ms"},
    "live_finish": _WORLD,
}


def _need(condition, reason):
    if not condition:
        raise ProtocolError("guided probe: " + reason)


def schedule():
    return {"id": ID, "step_us": STEP_US, "chunk_steps": CHUNK_STEPS,
            "checkpoint_steps": CHECKPOINT_STEPS, "max_steps": MAX_STEPS,
            "max_cycles": MAX_CYCLES, "max_requests_per_peer": MAX_REQUESTS,
            "max_batch_requests_per_peer": MAX_BATCH_REQUESTS, "poll_ms": POLL_MS,
            "input_seal_transport": "ready_advance_hold_receipts", "separate_input_poll": False,
            "preparation_rounds": SHORT_BUILD_ROUNDS, "preparation_contract": SHORT_BUILD_CONTRACT,
            "input_ops": ["GUIDED_ACTION"], "catalogue": catalogue(),
            "guide_authority": "ordered_role_checked_steps_after_joint_receipts_and_settlement",
            "validation": "fresh_read_only_preview_before_each_apply"}


def _requests(value, previous):
    _need(type(value) is list and len(value) <= MAX_BATCH_REQUESTS, "input batch exceeds bounds")
    canonical_json(value, limit=3000)
    for index, item in enumerate(value):
        _need(type(item) is dict and set(item) == {"seq", "command"}, "invalid input request")
        _integer(item["seq"], "request sequence", 1)
        _need(item["seq"] == previous + index + 1 <= MAX_REQUESTS, "request sequence is not contiguous or exceeds limit")
        command = validate_command(item["command"])
        _need(command["op"] != "END_TEST" or index == len(value) - 1, "nonterminal END_TEST")
    return copy.deepcopy(value)


def _ordered(requests):
    return [{"peer": peer, **item} for peer in ROSTER for item in requests[peer]]



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
        self._engine_seq = dict(SHORT_ENGINE_SEQUENCES)
        self._counts = {peer: {"pause": 0, "resume": 0, "action": 0} for peer in ROSTER}
        self._guided_completed = self._guided_revision = 0
        self._guided_last_attempt = None
        self._pending_guided_settlement = None
        self._transitions = {peer: {"pause": 0, "resume": 0} for peer in ROSTER}
        self._chunks, self._checkpoints, self._batches, self._outcomes, self._holds = [], [], [], [], []
        self._command_records = []
        self._seals = 0
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
        self._guided_preview = None
        self._guided_previews, self._guided_records = [], []

    def _accept_batch(self, requests, boundary):
        self._batch_requests = copy.deepcopy(requests)
        self._batch_order, self._batch_outcomes, self._batch_cursor = [], [], 0
        current = get_step(self._guided_completed + 1) if self._guided_completed < len(STEPS) else None
        for request in _ordered(requests):
            peer, command = request["peer"], request["command"]
            self._requests_seen[peer] = request["seq"]
            self._counts[peer]["action"] += 1
            reason = ("suite_complete" if current is None else
                      "end_before_suite_complete" if command["op"] == "END_TEST" else
                      "stale_step" if command["step"] < current["step"] else
                      "future_step" if command["step"] > current["step"] else
                      "wrong_actor" if peer != current["actor"] else
                      "duplicate_step" if self._batch_order else "")
            if reason:
                self._batch_outcomes.append({**copy.deepcopy(request), "status": "input_rejected",
                    "reason": reason, "cost": 0, "frame": boundary["frame"], "sim_time_us": boundary["sim_time_us"]})
            else:
                self._batch_order.append(copy.deepcopy(request))
        self._batches.append({"cycle": self._cycle, "batch_hash": self._batch_hash,
            "requests": copy.deepcopy(requests), "boundary": copy.deepcopy(boundary),
            "guided_step": current["step"] if current else None})

    def _applied_outcome(self, request, before, after, receipt):
        step = get_step(request["command"]["step"])
        changed = before["paused"] != after["paused"]
        if "pause" in step:
            name = "pause" if step["pause"] else "resume"
            self._counts[request["peer"]][name] += 1
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
        record = {"request": copy.deepcopy(request), "before": copy.deepcopy(before),
                  "after": copy.deepcopy(after), "receipt": copy.deepcopy(receipt),
                  "preview": copy.deepcopy(self._guided_preview), "batch_hash": self._batch_hash}
        self._command_records.append(record)
        self._guided_records.append(copy.deepcopy(record))
        self._batch_outcomes.append(outcome)
        self._batch_cursor += 1
        self._guided_preview = None

    def _record_preview(self, request):
        self._guided_previews.append({"request": copy.deepcopy(request),
            "boundary": copy.deepcopy(self._last_world), "preview": copy.deepcopy(self._guided_preview),
            "batch_hash": self._batch_hash})

    def _rejected_outcome(self, request):
        _need(self._guided_preview is not None and self._guided_preview["allowed"] is False,
              "rejection lacks its agreed negative preview")
        _need(self._guided_preview["reason"] == "not_ready", "required guided action is unavailable")
        outcome = {**copy.deepcopy(request), "status": "not_ready", "reason": "not_ready", "cost": 0,
                   "frame": self._last_world["frame"], "sim_time_us": self._last_world["sim_time_us"],
                   "preview_digest": digest(self._guided_preview)}
        self._guided_records.append({"request": copy.deepcopy(request), "before": copy.deepcopy(self._last_world),
            "after": copy.deepcopy(self._last_world), "preview": copy.deepcopy(self._guided_preview),
            "receipt": None, "batch_hash": self._batch_hash})
        self._batch_outcomes.append(outcome)
        self._batch_cursor += 1
        self._guided_preview = None

    def _settled_outcomes(self):
        return copy.deepcopy(self._batch_outcomes)

    def _confirm_outcomes(self, outcomes):
        for outcome in outcomes:
            if outcome["status"] == "applied":
                _need(outcome["command"]["step"] == self._guided_completed + 1,
                      "confirmed step is not contiguous")
                self._guided_completed += 1
            self._guided_last_attempt = {"step": outcome["command"].get("step"),
                "seq": outcome["seq"], "peer": outcome["peer"], "status": outcome["status"],
                "reason": outcome.get("reason", "")}
        self._guided_revision += 1
        self._outcomes.extend(copy.deepcopy(outcomes))
        self._confirmed_paused = self._last_world["paused"]
        for peer in ROSTER:
            self._acknowledged[peer] = self._requests_seen[peer]
        self._ending = self._guided_completed == len(STEPS)

    def guide_status(self):
        current = get_step(self._guided_completed + 1) if self._guided_completed < len(STEPS) else None
        pending = any(self._acknowledged[peer] != self._requests_seen[peer] for peer in ROSTER)
        pending |= bool(getattr(self, "_pending_guided_settlement", None))
        pending |= bool(getattr(self, "_sealed", [])) and any(
            item["seq"] > self._acknowledged.get(getattr(self, "peer", ""), 0)
            for item in getattr(self, "_sealed", []))
        joint_started = self._live_started and type(self._confirmed_paused) is bool
        phase = ("halted" if self.halted else "completed" if self._live_complete else
                 "waiting" if not joint_started else
                 "pending" if pending or current is None else "ready")
        return {"index": self._guided_completed, "step": current["step"] if current else None,
                "current_step": current["step"] if current else None,
                "step_id": current["id"] if current else None,
                "actor": current["actor"] if current else None,
                "phase": phase, "ready": phase == "ready" and joint_started,
                "completed_step_ids": [step["id"] for step in STEPS[:self._guided_completed]],
                "completed_steps": self._guided_completed, "total_steps": len(STEPS),
                "pending": bool(pending), "settled_revision": self._guided_revision,
                "last_attempt": copy.deepcopy(self._guided_last_attempt),
                "error": str(getattr(self, "halt_reason", "")) if self.halted else "",
                "scope": "fixed_launcher_actions", "native_ui_input_capture": False}

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
                "ending": self._ending, "acknowledgements": copy.deepcopy(self._outcomes[-16:]), "guided": self.guide_status()}

    def live_report(self):
        progress = self.live_progress()
        joint = isinstance(self, Coordinator)
        passed = progress["completed"] and self._guided_completed == len(STEPS)
        return {"id": ID, "completed": progress["completed"],
                "completion_scope": "both_peer_fresh_world_boundaries" if joint else "local_fresh_world_boundary",
                "required_interactions_met": passed, "required_guided_interactions_met": passed,
                "guided": self.guide_status(), "catalogue": catalogue(),
                "coverage": {"completed_step_ids": self.guide_status()["completed_step_ids"],
                    "per_peer_pause_resume": copy.deepcopy(self._transitions),
                    "observed_scope": "fixed_launcher_road_vehicle_line_lifecycle",
                    "fresh_preview_records": len(self._guided_previews),
                    "unavailable_scope": catalogue()["not_covered"]},
                "guided_preview_records": copy.deepcopy(self._guided_previews),
                "guided_records": copy.deepcopy(self._guided_records),
                "progress": progress, "schedule": schedule(),
                "last_confirmed_native_frame": progress["frame"], "last_confirmed_native_sim_time_us": progress["sim_time_us"],
                "native_frontier_scope": "both_peers_acknowledged_native_frontier" if joint else "local_acknowledged_native_frontier",
                "last_observed_frame": progress["last_observed_frame"], "last_observed_sim_time_us": progress["last_observed_time_us"],
                "start": copy.deepcopy(self._live_start), "chunk_records": copy.deepcopy(self._chunks),
                "checkpoint_records": copy.deepcopy(self._checkpoints), "input_batches": copy.deepcopy(self._batches),
                "outcomes": copy.deepcopy(self._outcomes), "hold_records": copy.deepcopy(self._holds),
                "command_records": copy.deepcopy(self._command_records),
                "input_seal_cycles": self._seals, "separate_input_poll_barriers": 0,
                "end_to_end_duration_ms": None if self._live_started_ns is None else
                    ((self._live_finished_ns or time.monotonic_ns()) - self._live_started_ns) // 1000000,
                "world_observation": "fresh_start_input_batches_commands_periodic_checkpoints_paused_heartbeats_and_finish",
                "native_ui_input_capture": False, "full_world_verified": False, "visual_smoothness_verified": False}


class GuidedCoordinator(_LiveState, Coordinator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _need(self._step_us == STEP_US and GUIDED_CAPABILITY in self._capabilities, "live capability and quantum required")
        self._init_live()
        self._operation = -1
        self._replies = {}
        self._offsets = {peer: (0, 0) for peer in ROSTER}

    def _request_inputs(self):
        if self.round < SHORT_BUILD_ROUNDS:
            return super()._request_inputs()
        _need(self.round == SHORT_BUILD_ROUNDS and not self._live_started and self.paused is False,
              "live mode requires the completed unpaused build")
        self._live_started, self._live_started_ns = True, time.monotonic_ns()
        self._live_start = self._last_world = _world({"frame": self.frame, "sim_time_us": self.sim_time_us,
            "state_digest": self.state_digest, "paused": self.paused})
        self._live_plan = {"epoch": self.epoch, "round": SHORT_BUILD_ROUNDS, "index": 0,
            "manifest_digest": self._manifest_digest, "schedule": schedule(), **self._live_start}
        self.plan_hash = digest(self._live_plan)
        return self._send("live_start", "live_ready", manifest_digest=self._manifest_digest, schedule=schedule(), **self._live_start)

    def _send(self, kind, expected, **fields):
        self._operation += 1
        _need(self._operation < MAX_ACTIONS, "operation limit reached; end the test earlier")
        self._replies = {}
        self._enter(expected)
        return self._broadcast(kind, round=SHORT_BUILD_ROUNDS, index=self._operation, plan_hash=self.plan_hash, **fields)

    def _validate(self, message):
        kind = message.get("kind")
        if kind not in _REPLIES:
            return super()._validate(message)
        _need(set(message) == _COMMON | _REPLIES[kind] and message["epoch"] == self.epoch
              and message["round"] == SHORT_BUILD_ROUNDS, "invalid live reply envelope")
        _integer(message["index"], "operation index")
        _need(message["index"] < MAX_ACTIONS, "reply exceeds operation limit")
        _hash(message["plan_hash"], "live plan")
        if kind in GUIDED_WORLD_RECEIPTS:
            _take_world(message)
        if kind in ("live_ready", "live_advanced", "live_held"):
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

    def _validate_seal(self, peer, message):
        _need(message["cycle"] == self._cycle < MAX_CYCLES, "wrong or exhausted sealed input cycle")
        _requests(message["requests"], self._requests_seen[peer])

    def _joint_seals(self):
        # Called only after both receipts have been validated at the same held
        # frontier. A queue read or one peer ACK alone never authorizes a grant.
        self._seals += 1
        self._pending_requests = {origin: self._replies[origin]["requests"] for origin in ROSTER}
        nonempty = any(self._pending_requests.values())
        if nonempty or self._steps - self._checkpoint_steps >= CHECKPOINT_STEPS:
            self._checkpoint_reason = "inputs" if nonempty else "periodic"
            return self._send("live_checkpoint", "live_checkpointed", reason=self._checkpoint_reason,
                              frame=self.frame, sim_time_us=self.sim_time_us)
        self._cycle += 1
        return self._continue()

    def _continue(self):
        if self._ending:
            return self._send("live_finish", "live_finished", **self._last_world)
        _need(self._cycle < MAX_CYCLES, "input cycle limit reached; end the test earlier")
        if self.paused:
            return self._send("live_hold", "live_held", duration_ms=POLL_MS, **self._last_world)
        _need(self._steps + CHUNK_STEPS <= MAX_STEPS, "native step limit reached; end the test earlier")
        return self._send("live_advance", "live_advanced", frame=self.frame, sim_time_us=self.sim_time_us, steps=CHUNK_STEPS)

    def _on_live_ready(self, peer, message):
        _need(_take_world(message) == self._live_start, "live start differs from the completed build")
        self._validate_seal(peer, message)
        if self._collect(peer, message, "live_ready"):
            self._worlds()
            return self._joint_seals()
        return []

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
            return self._send("live_settle", "live_settled", batch_hash=self._batch_hash, outcomes=outcomes)
        request = self._batch_order[self._batch_cursor]
        key = request["peer"] + ":" + str(self._engine_seq[request["peer"]] + 1)
        self._guided_preview = None
        return self._send("live_preview", "live_previewed", request=request, command_key=key,
                          batch_hash=self._batch_hash, **self._last_world)

    def _on_live_previewed(self, peer, message):
        request = self._batch_order[self._batch_cursor]
        _need(request["command"]["op"] == "GUIDED_ACTION" and _take_world(message) == self._last_world,
              "preview changed the held world or targets a non-guided action command")
        validate_preview(message["preview"], request["command"], self._last_world)
        if not self._collect(peer, message, "live_previewed"):
            return []
        _need(self._replies["a"]["preview"] == self._replies["b"]["preview"], "guided action preview results differ")
        self._guided_preview = copy.deepcopy(message["preview"])
        self._record_preview(request)
        if not self._guided_preview["allowed"]:
            _need(self._guided_preview["reason"] == "not_ready", "required guided capability unavailable: " + self._guided_preview["reason"])
            return self._send("live_reject", "live_rejected", request=request,
                preview_digest=digest(self._guided_preview), batch_hash=self._batch_hash, **self._last_world)
        key = request["peer"] + ":" + str(self._engine_seq[request["peer"]] + 1)
        return self._send("live_apply", "live_applied", request=request, command_key=key,
                          batch_hash=self._batch_hash, **self._last_world)

    def _on_live_rejected(self, peer, message):
        _need(_take_world(message) == self._last_world and self._guided_preview is not None
              and self._guided_preview["allowed"] is False
              and message["preview_digest"] == digest(self._guided_preview),
              "guided action rejection changed the held world or its agreed preview")
        if not self._collect(peer, message, "live_rejected"):
            return []
        self._rejected_outcome(self._batch_order[self._batch_cursor])
        return self._next_command()

    def _on_live_applied(self, peer, message):
        request = self._batch_order[self._batch_cursor]
        step = get_step(request["command"]["step"])
        self._at_frontier(message, step.get("pause", self.paused))
        key = request["peer"] + ":" + str(self._engine_seq[request["peer"]] + 1)
        validate_action_receipt(message["receipt"], request["command"], key,
                               self._guided_preview, self._last_world, _take_world(message))
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
            self._confirm_outcomes(self._settled_outcomes())
            self._cycle += 1
            return self._continue()
        return []

    def _on_live_advanced(self, peer, message):
        before = {"frame": self.frame, "sim_time_us": self.sim_time_us}
        _need(message["frame"] == self.frame + CHUNK_STEPS and
              message["sim_time_us"] == self.sim_time_us + CHUNK_STEPS * STEP_US, "incorrect native range acknowledgement")
        _check_advance(message["metrics"], before, self._offsets[peer])
        self._validate_seal(peer, message)
        if not self._collect(peer, message, "live_advanced"):
            return []
        metrics = {}
        for origin in ROSTER:
            metrics[origin], self._offsets[origin] = _check_advance(self._replies[origin]["metrics"], before, self._offsets[origin])
        self.frame, self.sim_time_us = message["frame"], message["sim_time_us"]
        self._steps += CHUNK_STEPS
        self._chunks.append({"index": self._operation, "frontier": {"frame": self.frame, "sim_time_us": self.sim_time_us}, "peers": metrics})
        return self._joint_seals()

    def _on_live_held(self, peer, message):
        _need(_take_world(message) == self._last_world and message["paused"] is True, "paused world changed during heartbeat")
        _hold_metrics(message["metrics"])
        self._validate_seal(peer, message)
        if not self._collect(peer, message, "live_held"):
            return []
        self._worlds()
        metrics = {origin: self._replies[origin]["metrics"] for origin in ROSTER}
        self._record_hold(metrics)
        self._holds.append({"index": self._operation, "boundary": self._last_world, "peers": metrics})
        return self._joint_seals()

    def _on_live_finished(self, peer, message):
        _need(self._ending and _take_world(message) == self._last_world, "end checkpoint changed the held world")
        if self._collect(peer, message, "live_finished"):
            self._worlds()
            self._live_complete, self._live_finished_ns = True, time.monotonic_ns()
            self._enter("inputs")
        return []


class GuidedReplica(_LiveState, Replica):
    def __init__(self, *args, live_input_source=None, stop_requested=None, stream_engine_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        _need(self.step_us == STEP_US and GUIDED_CAPABILITY in self.capabilities, "live capability and quantum required")
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
        return self._message(kind, round=SHORT_BUILD_ROUNDS, index=message["index"], plan_hash=message["plan_hash"], **fields)

    def _receive(self, message):
        kind = message.get("kind") if type(message) is dict else None
        if kind not in _ACTIONS:
            if self._live_started and not self._live_complete and kind != "halt":
                raise ProtocolError("live probe: normal protocol inside live session")
            if kind == "complete" and self.round >= SHORT_BUILD_ROUNDS:
                _need(self._live_complete, "completion before fresh joint end barrier")
            return super()._receive(message)
        raw = canonical_json(message)
        message = json.loads(raw)
        _need(set(message) == _COMMON | _ACTIONS[kind] and message["epoch"] == self.epoch
              and message["round"] == self.round == SHORT_BUILD_ROUNDS, "invalid live action envelope")
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
        if self._pending_guided_settlement is not None:
            self._confirm_outcomes(self._pending_guided_settlement)
            self._pending_guided_settlement = None
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
        plan = {"epoch": self.epoch, "round": SHORT_BUILD_ROUNDS, "index": 0,
                "manifest_digest": self.manifest, "schedule": schedule(), **before}
        _need(before["paused"] is False and {k: v for k, v in message.items() if k not in ("kind", "plan_hash")} == plan
              and message["plan_hash"] == digest(plan), "live start plan differs from approved schedule/build")
        factory = self._live_factory
        if factory is None:
            from .guided_engine import GuidedStreamEngine
            factory = GuidedStreamEngine
        self.stream_engine = factory(self.engine, stop_requested=self._live_stop)
        actual = self._fresh(self.stream_engine.checkpoint())
        _need(actual == before, "world changed before live start")
        self._live_started, self._live_started_ns = True, time.monotonic_ns()
        self._live_start, self._live_plan = actual, plan
        return self._reply("live_ready", message, **actual, **self._seal_inputs())

    def _same_frontier(self, message):
        _need(all(message[key] == self._frontier[key] for key in _FRONTIER)
              and self.stream_engine.frame == self._frontier["frame"]
              and self.stream_engine.time_us == self._frontier["sim_time_us"], "live operation has wrong native frontier")
        # The first subsequent host action confirms that both start receipts
        # were received. Local readiness alone is not a joint pause indication.
        if self._confirmed_paused is None:
            self._confirmed_paused = self._live_start["paused"]

    def _after_batch(self):
        self._next = {"live_finish"} if self._ending else {"live_hold"} if self.stream_engine.paused else {"live_advance"}

    def _seal_inputs(self):
        _need(self._cycle < MAX_CYCLES and not self._ending, "wrong or exhausted input cycle")
        self._sealed = _requests(self._live_source(), self._requests_seen[self.peer])
        self._seals += 1
        self._next = {"live_checkpoint"}
        if not self._sealed and self._steps - self._checkpoint_steps < CHECKPOINT_STEPS:
            self._next.add("live_hold" if self.stream_engine.paused else "live_advance")
        return {"cycle": self._cycle, "requests": copy.deepcopy(self._sealed)}

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
        self._next_command()
        return self._reply("live_committed", message, batch_hash=self._batch_hash)

    def _do_apply(self, message):
        before = self._fresh()
        request = self._batch_order[self._batch_cursor]
        expected_key = request["peer"] + ":" + str(self._engine_seq[request["peer"]] + 1)
        _need(_take_world(message) == before and message["batch_hash"] == self._batch_hash
              and message["request"] == request and message["command_key"] == expected_key,
              "command differs from committed deterministic input order")
        _need(self._guided_preview is not None and self._guided_preview["allowed"] is True,
              "guided command lacks its agreed successful preview")
        receipt = self.stream_engine.apply_guided(request["command"], expected_key, self._guided_preview)
        after = self._fresh()
        validate_action_receipt(receipt, request["command"], expected_key, self._guided_preview, before, after)
        self._engine_seq[request["peer"]] += 1
        self._applied_outcome(request, before, after, receipt)
        self._next_command()
        return self._reply("live_applied", message, **after, receipt=receipt)

    def _next_command(self):
        self._next = {"live_settle"} if self._batch_cursor == len(self._batch_order) else {"live_preview"}

    def _do_preview(self, message):
        before = self._fresh()
        request = self._batch_order[self._batch_cursor]
        key = request["peer"] + ":" + str(self._engine_seq[request["peer"]] + 1)
        _need(request["command"]["op"] == "GUIDED_ACTION" and _take_world(message) == before
              and message["batch_hash"] == self._batch_hash and message["request"] == request
              and message["command_key"] == key, "preview differs from committed deterministic input order")
        preview = self.stream_engine.preview_guided(request["command"], key)
        after = self._fresh()
        _need(after == before, "preview changed the held world")
        self._guided_preview = validate_preview(preview, request["command"], before)
        _need(preview["allowed"] or preview["reason"] == "not_ready", "required guided capability unavailable: " + preview["reason"])
        self._record_preview(request)
        self._next = {"live_apply"} if preview["allowed"] else {"live_reject"}
        return self._reply("live_previewed", message, **after, preview=copy.deepcopy(preview))

    def _do_reject(self, message):
        before = self._fresh()
        request = self._batch_order[self._batch_cursor]
        _need(request["command"]["op"] == "GUIDED_ACTION" and _take_world(message) == before
              and message["batch_hash"] == self._batch_hash and message["request"] == request
              and self._guided_preview is not None and self._guided_preview["allowed"] is False
              and message["preview_digest"] == digest(self._guided_preview),
              "rejection differs from the agreed negative preview")
        # Read the world again before confirming that rejection spent nothing.
        after = self._fresh(self.stream_engine.checkpoint())
        _need(after == before, "rejected guided action changed the observed world")
        preview_hash = digest(self._guided_preview)
        self._rejected_outcome(request)
        self._next_command()
        return self._reply("live_rejected", message, **after, preview_digest=preview_hash)

    def _do_settle(self, message):
        _need(message["batch_hash"] == self._batch_hash and message["outcomes"] == self._settled_outcomes(),
              "joint settlement differs from actual command outcomes")
        # The next authenticated host operation establishes that both settlement
        # ACKs arrived. Until then no next step is exposed to the launcher.
        self._pending_guided_settlement = copy.deepcopy(message["outcomes"])
        self._cycle += 1
        last_step = self._guided_completed + sum(item["status"] == "applied" for item in message["outcomes"])
        self._next = {"live_finish"} if last_step == len(STEPS) else {"live_hold"} if self.stream_engine.paused else {"live_advance"}
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
        return self._reply("live_advanced", message, **self._frontier, metrics=metrics, **self._seal_inputs())

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
        return self._reply("live_held", message, **after, metrics=metrics, **self._seal_inputs())

    def _do_finish(self, message):
        _need(self._ending and _take_world(message) == self._fresh(), "uncommitted end request")
        world = self._fresh(self.stream_engine.checkpoint())
        _need(world == _take_world(message), "end checkpoint changed the held world")
        self._live_complete, self._live_finished_ns = True, time.monotonic_ns()
        self.phase, self._next = "inputs", set()
        return self._reply("live_finished", message, **world)
