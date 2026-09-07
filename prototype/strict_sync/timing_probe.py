"""Bounded post-build hold/cadence experiment; backend timing is not rendered FPS.

The existing 240-round build protocol is unchanged. Twelve prepared windows then
advance the already constructed scene for sixty further simulated seconds. World
digests are compared at window boundaries, not at every interior native permit.
"""
from __future__ import annotations

import copy
import json
import time
from typing import NamedTuple

from .build_profile import BUILD_ROUNDS
from .core import (Coordinator, ProtocolError, ROSTER, _hash, _integer,
                   canonical_json, digest)
from .replica import Replica

ID = "hold-and-pace-v1"
TIMING_CAPABILITY = "bounded_timing_windows_v1"
WINDOW_STEPS = 25
STEP_US = 200000


class Segment(NamedTuple):
    label: str
    delayed_peer: str
    delay_ms: int


SEGMENTS = (
    Segment("baseline-1", "", 0), Segment("baseline-2", "", 0),
    Segment("baseline-3", "", 0), Segment("wait-a-1000", "a", 1000),
    Segment("wait-b-1500", "b", 1500), Segment("wait-a-250", "a", 250),
    Segment("wait-b-750", "b", 750), Segment("wait-a-3000", "a", 3000),
    Segment("wait-b-500", "b", 500), Segment("recovery-1", "", 0),
    Segment("recovery-2", "", 0), Segment("recovery-3", "", 0),
)
SCHEDULE_HASH = digest([segment._asdict() for segment in SEGMENTS])
PACE_THRESHOLDS = {"rate_ppm_min": 950000, "rate_ppm_max": 1050000,
                   "interval_p95_us_max": 250000, "interval_max_us_max": 400000,
                   "minimum_intervals_per_window": WINDOW_STEPS - 1}
_BOUNDARY = {"frame", "sim_time_us", "state_digest", "paused"}
_REPLY = {"kind", "epoch", "round", "index", "schedule_id", "plan_hash", "metrics"} | _BOUNDARY
_PLAN = {"epoch", "round", "index", "schedule_id", "schedule_hash", "segment",
         "steps", "step_us", "manifest_digest"} | _BOUNDARY


def _require(condition, message):
    if not condition:
        raise ProtocolError("timing probe: " + message)


def _boundary(frame, sim_time_us, state_digest, paused):
    _integer(frame, "timing frame")
    _integer(sim_time_us, "timing simulation time")
    _hash(state_digest, "timing state digest")
    _require(paused is False, "window requires an unpaused verified world")
    return {"frame": frame, "sim_time_us": sim_time_us,
            "state_digest": state_digest, "paused": paused}


def _plan(epoch, manifest, index, boundary):
    _require(type(index) is int and 0 <= index < len(SEGMENTS), "invalid segment index")
    return {"epoch": epoch, "round": BUILD_ROUNDS, "index": index,
            "schedule_id": ID, "schedule_hash": SCHEDULE_HASH,
            "segment": dict(SEGMENTS[index]._asdict()), "steps": WINDOW_STEPS,
            "step_us": STEP_US, "manifest_digest": manifest, **boundary}


def _native_metrics(value):
    if value is None:
        return
    _require(type(value) is dict and len(value) <= 40, "invalid native timing sample")
    for key, item in value.items():
        _require(type(key) is str and 1 <= len(key) <= 64, "invalid native metric name")
        if item is not None:
            _integer(item, "native timing metric")


def _metrics(value, action, *, delay=0, before=None):
    canonical_json(value, limit=16384)
    _require(type(value) is dict, "missing timing metrics")
    if action == "ready":
        fields = {"kind", "requested_delay_ms", "actual_delay_ms", "duration_ms",
                  "boundary_unchanged", "maintenance_observed", "native_before",
                  "native_after", "counter_deltas"}
        _require(set(value) == fields and value["kind"] == "idle_wait", "invalid idle metrics schema")
        for name in ("requested_delay_ms", "actual_delay_ms", "duration_ms"):
            _integer(value[name], name)
        _require(value["requested_delay_ms"] == delay and value["actual_delay_ms"] >= delay,
                 "scheduled idle wait was not measured in full")
        _require(value["duration_ms"] >= value["actual_delay_ms"], "invalid idle wall duration")
        _require(value["boundary_unchanged"] is True and type(value["maintenance_observed"]) is bool,
                 "idle boundary was not verified")
        for name in ("native_before", "native_after"):
            _native_metrics(value[name])
        deltas = value["counter_deltas"]
        _require(type(deltas) is dict and set(deltas) == {"hold_calls", "outer_calls", "updated_ms"},
                 "invalid idle counter deltas")
        for item in deltas.values():
            if item is not None:
                _integer(item, "idle counter delta", -(1 << 53) + 1)
        if value["maintenance_observed"]:
            _require(type(deltas["hold_calls"]) is int and deltas["hold_calls"] > 0
                     and type(deltas["updated_ms"]) is int and deltas["updated_ms"] > 0,
                     "maintenance claim lacks fresh native evidence")
    else:
        fields = {"kind", "steps_requested", "step_us", "simulated_us", "duration_ms",
                  "rate_ppm", "steps", "world_observation", "native_clock_each_step"}
        _require(set(value) == fields and value["kind"] == "advance_window", "invalid window metrics schema")
        for name in ("steps_requested", "step_us", "simulated_us", "duration_ms", "rate_ppm"):
            _integer(value[name], name)
        _require(value["steps_requested"] == WINDOW_STEPS and value["step_us"] == STEP_US
                 and value["simulated_us"] == WINDOW_STEPS * STEP_US,
                 "window metrics disagree with the fixed schedule")
        _require(value["duration_ms"] > 0, "window duration must be positive")
        # The adapter rounds microseconds for rate calculation, but ceilings the
        # separately reported milliseconds. Preserve that unknown sub-ms range
        # and one ppm of rate rounding instead of demanding artificial equality.
        numerator = value["simulated_us"] * 1000000
        lower_duration_us = max(1, (value["duration_ms"] - 1) * 1000)
        upper_duration_us = value["duration_ms"] * 1000
        lower_rate = (numerator + upper_duration_us - 1) // upper_duration_us - 1
        upper_rate = numerator // lower_duration_us + 1
        _require(lower_rate <= value["rate_ppm"] <= upper_rate,
                 "window rate is inconsistent with measured duration")
        _require(value["world_observation"] == "start_and_end_only"
                 and value["native_clock_each_step"] is True, "invalid window observation scope")
        steps = value["steps"]
        _require(type(steps) is list and len(steps) == WINDOW_STEPS, "missing native step measurements")
        previous_ack, previous_admitted = 0, 0
        step_fields = {"frame", "sim_time_us", "scheduled_offset_us", "admitted_offset_us",
                       "ack_observed_offset_us", "permit_duration_us", "lateness_us",
                       "native_time_before_ms", "native_time_after_ms"}
        for index, item in enumerate(steps):
            _require(type(item) is dict and set(item) == step_fields, "invalid native step timing schema")
            for name, number in item.items():
                _integer(number, name)
            target = before["sim_time_us"] + (index + 1) * STEP_US
            _require(item["frame"] == before["frame"] + index + 1 and item["sim_time_us"] == target,
                     "window has a missing or reordered native step")
            # Native status describes its latest traversal: an intervening HOLD
            # may already have replaced the advancing traversal's before time.
            _require(item["native_time_before_ms"] * 1000 in (target - STEP_US, target)
                     and item["native_time_after_ms"] * 1000 == target,
                     "native clock measurement differs from the permitted step")
            _require(item["ack_observed_offset_us"] >= item["admitted_offset_us"] >= previous_ack,
                     "native timing observations moved backwards")
            # Offsets and elapsed intervals are rounded independently to integer
            # microseconds. A one-us discrepancy is quantization, not permission
            # for an early/catch-up burst or a materially shorter engine period.
            _require(item["scheduled_offset_us"] + 1 >= (index + 1) * STEP_US
                     and item["admitted_offset_us"] + 1 >= item["scheduled_offset_us"]
                     and item["admitted_offset_us"] + 1 >= previous_admitted + STEP_US,
                     "window pacing admits steps faster than one-times speed")
            _require(abs(item["permit_duration_us"] -
                         (item["ack_observed_offset_us"] - item["admitted_offset_us"])) <= 1,
                     "permit duration disagrees with measured offsets")
            _require(abs(item["lateness_us"] -
                         max(0, item["admitted_offset_us"] - item["scheduled_offset_us"])) <= 1,
                     "permit lateness disagrees with measured offsets")
            previous_ack = item["ack_observed_offset_us"]
            previous_admitted = item["admitted_offset_us"]
        _require(upper_duration_us + 1 >= previous_ack,
                 "window duration is shorter than its final acknowledgement")
    return copy.deepcopy(value)


def _stats(values):
    ordered = sorted(values)
    return {"count": len(ordered), "min_us": ordered[0] if ordered else None,
            "p95_us": ordered[(95 * len(ordered) + 99) // 100 - 1] if ordered else None,
            "max_us": ordered[-1] if ordered else None}


def _summarize_peer(entries):
    admissions, acknowledgements, rates, window_results = [], [], [], []
    for item in entries:
        window = item["window"]
        steps = window["steps"]
        admit = [right["admitted_offset_us"] - left["admitted_offset_us"]
                 for left, right in zip(steps, steps[1:])]
        ack = [right["ack_observed_offset_us"] - left["ack_observed_offset_us"]
               for left, right in zip(steps, steps[1:])]
        rates.append(window["rate_ppm"])
        admission, acknowledgement = _stats(admit), _stats(ack)
        window_results.append(PACE_THRESHOLDS["rate_ppm_min"] <= window["rate_ppm"] <= PACE_THRESHOLDS["rate_ppm_max"]
            and all(stats["count"] >= PACE_THRESHOLDS["minimum_intervals_per_window"]
                    and stats["p95_us"] <= PACE_THRESHOLDS["interval_p95_us_max"]
                    and stats["max_us"] <= PACE_THRESHOLDS["interval_max_us_max"]
                    for stats in (admission, acknowledgement)))
        admissions.extend(admit)
        acknowledgements.extend(ack)
    return {"windows_measured": len(entries), "window_target_checks_passed": all(window_results),
            "active_window_duration_ms": sum(item["window"]["duration_ms"] for item in entries),
            "requested_injected_wait_ms": sum(item["idle"]["requested_delay_ms"] for item in entries),
            "actual_injected_wait_ms": sum(item["idle"]["actual_delay_ms"] for item in entries),
            "idle_check_duration_ms": sum(item["idle"]["duration_ms"] for item in entries),
            "maintenance_observed_windows": sum(item["idle"]["maintenance_observed"] for item in entries),
            "rate_ppm_min": min(rates) if rates else None, "rate_ppm_max": max(rates) if rates else None,
            "admission_intervals": _stats(admissions), "acknowledgement_intervals": _stats(acknowledgements)}


def _report(records, *, completed, started, scope, elapsed_ms):
    peers = {}
    for item in records:
        for peer, evidence in (item["peers"].items() if "peers" in item else [(item["peer"], item)]):
            peers.setdefault(peer, []).append(evidence)
    summaries = {peer: _summarize_peer(entries) for peer, entries in peers.items()}
    paced = (all(summary["windows_measured"] == len(SEGMENTS) and summary["window_target_checks_passed"]
                 for summary in summaries.values()) if completed and summaries else None)
    return {"schedule_id": ID, "schedule_hash": SCHEDULE_HASH,
            "segments_expected": len(SEGMENTS), "segments_completed": len(records),
            "started": started, "completed": completed, "completion_scope": scope,
            "window_steps": WINDOW_STEPS, "step_us": STEP_US,
            "additional_simulated_us": len(records) * WINDOW_STEPS * STEP_US,
            "world_comparison": "window_boundaries_only", "native_clock_each_step": True,
            "visual_smoothness_verified": False, "complete_world_verified": False,
            "delay_scope": "synthetic_local_hold_not_network_rtt", "segments": copy.deepcopy(records),
            "paced_windows_1x_met": paced, "pace_thresholds": dict(PACE_THRESHOLDS),
            "peer_timing_summaries": summaries, "end_to_end_duration_ms": elapsed_ms,
            "end_to_end_scope": "local_monotonic_timing_phase_including_waits_and_barriers",
            "interval_scope": "consecutive_permit_call_starts_and_native_ack_observations_within_each_window",
            "window_duration_scope": "complete_method_including_initial_and_final_world_observations",
            "step_offset_origin": "after_initial_world_observation_and_gate_check",
            "interval_exclusions": ["first_admission_from_window_start", "inter_window_waits", "render_frames"]}


class TimingCoordinator(Coordinator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _require(self._step_us == STEP_US and TIMING_CAPABILITY in self._capabilities,
                 "timing coordinator requires its explicit capability and step quantum")
        self._timing_started = False
        self._timing_complete = False
        self._timing_index = 0
        self._timing_plan = None
        self._timing_ready = {}
        self._timing_done = {}
        self._timing_records = []
        self._timing_started_ns = None
        self._timing_finished_ns = None

    def _request_inputs(self):
        if self.round < BUILD_ROUNDS:
            return super()._request_inputs()
        _require(self.round == BUILD_ROUNDS and not self._timing_started,
                 "timing phase cannot restart or skip the build boundary")
        self._timing_started = True
        self._timing_started_ns = time.monotonic_ns()
        return self._prepare_timing()

    def _prepare_timing(self):
        boundary = _boundary(self.frame, self.sim_time_us, self.state_digest, self.paused)
        self._timing_plan = _plan(self.epoch, self._manifest_digest, self._timing_index, boundary)
        self.plan_hash = digest(self._timing_plan)
        self._timing_ready, self._timing_done = {}, {}
        self._enter("timing_ready")
        return self._broadcast("timing_prepare", plan_hash=self.plan_hash,
                               **{key: value for key, value in self._timing_plan.items() if key != "epoch"})

    def _validate(self, message):
        if message.get("kind") not in ("timing_ready", "timing_done"):
            return super()._validate(message)
        _require(set(message) == _REPLY, "invalid timing reply envelope")
        _require(message["epoch"] == self.epoch and message["schedule_id"] == ID
                 and message["round"] == BUILD_ROUNDS, "wrong timing epoch, schedule or round")
        _integer(message["index"], "timing index")
        _require(message["index"] < len(SEGMENTS), "timing index is outside the schedule")
        _hash(message["plan_hash"], "timing plan hash")
        _boundary(*(message[name] for name in ("frame", "sim_time_us", "state_digest", "paused")))
        canonical_json(message["metrics"], limit=16384)
        return message["kind"], message["round"], message["index"]

    def _on_timing_ready(self, peer, message):
        self._require("timing_ready", message)
        _require(message["index"] == self._timing_index, "wrong ready segment")
        _require(all(message[key] == self._timing_plan[key] for key in _BOUNDARY),
                 "world changed while a peer waited at the shared boundary")
        segment = SEGMENTS[self._timing_index]
        delay = segment.delay_ms if segment.delayed_peer == peer else 0
        _metrics(message["metrics"], "ready", delay=delay)
        self._timing_ready[peer] = message
        if len(self._timing_ready) < len(ROSTER):
            return []
        self._enter("timing_done")
        return self._broadcast("timing_run", round=BUILD_ROUNDS, index=self._timing_index,
                               schedule_id=ID, plan_hash=self.plan_hash)

    def _on_timing_done(self, peer, message):
        self._require("timing_done", message)
        _require(message["index"] == self._timing_index, "wrong completed segment")
        start = self._timing_plan
        _require(message["frame"] == start["frame"] + WINDOW_STEPS
                 and message["sim_time_us"] == start["sim_time_us"] + WINDOW_STEPS * STEP_US,
                 "window finished at the wrong boundary")
        _metrics(message["metrics"], "done", before=start)
        self._timing_done[peer] = message
        if len(self._timing_done) < len(ROSTER):
            return []
        _require(all(self._timing_done["a"][key] == self._timing_done["b"][key] for key in _BOUNDARY),
                 "window end world differs between peers")
        self._timing_records.append({"index": self._timing_index, "segment": start["segment"],
            "start": {key: start[key] for key in _BOUNDARY},
            "end": {key: message[key] for key in _BOUNDARY},
            "peers": {peer: {"idle": self._timing_ready[peer]["metrics"],
                             "window": self._timing_done[peer]["metrics"]} for peer in ROSTER}})
        self.frame, self.sim_time_us, self.state_digest = (message[key] for key in ("frame", "sim_time_us", "state_digest"))
        self._timing_index += 1
        if self._timing_index == len(SEGMENTS):
            self._timing_complete = True
            self._timing_finished_ns = time.monotonic_ns()
            self._enter("inputs")  # The runner may now send its normal terminal completion.
            return []
        return self._prepare_timing()

    def timing_progress(self):
        index = min(self._timing_index, len(SEGMENTS) - 1)
        return {"segment_index": self._timing_index, "segment_total": len(SEGMENTS),
                "label": SEGMENTS[index].label, "stage": self.phase,
                "started": self._timing_started, "completed": self._timing_complete, "frame": self.frame}

    def timing_report(self):
        return _report(self._timing_records, completed=self._timing_complete and not self.halted,
                       started=self._timing_started, scope="both_peer_window_boundaries",
                       elapsed_ms=self._elapsed_ms())

    def _elapsed_ms(self):
        if self._timing_started_ns is None:
            return None
        return max(0, ((self._timing_finished_ns or time.monotonic_ns()) - self._timing_started_ns) // 1000000)


class TimingReplica(Replica):
    def __init__(self, *args, stop_requested=None, **kwargs):
        super().__init__(*args, **kwargs)
        _require(self.step_us == STEP_US and TIMING_CAPABILITY in self.capabilities,
                 "timing replica requires its explicit capability and step quantum")
        self._stop_requested = stop_requested
        self._timing_index = 0
        self._timing_started = False
        self._timing_complete = False
        self._timing_plan = None
        self._timing_cache = {}
        self._timing_records = []
        self._timing_idle = None
        self._timing_started_ns = None
        self._timing_finished_ns = None

    def _engine_boundary(self):
        return _boundary(self.engine.frame, self.engine.time_us, self.engine.state_digest, self.engine.paused)

    def _receipt(self, value, before, action, delay=0):
        canonical_json(value, limit=20000)
        _require(type(value) is dict and set(value) == {"frame", "sim_time_us", "state_digest", "metrics"},
                 "invalid actual engine timing receipt")
        observed = self._engine_boundary()
        _require(all(value[key] == observed[key] for key in ("frame", "sim_time_us", "state_digest")),
                 "engine timing receipt disagrees with its verified state")
        metrics = _metrics(value["metrics"], action, before=before, delay=delay)
        if action == "ready":
            _require(observed == before, "world changed during the local idle wait")
        else:
            _require(observed["frame"] == before["frame"] + WINDOW_STEPS
                     and observed["sim_time_us"] == before["sim_time_us"] + WINDOW_STEPS * STEP_US,
                     "engine advanced a different window than permitted")
        return observed, metrics

    def _receive(self, message):
        kind = message.get("kind") if type(message) is dict else None
        if kind not in ("timing_prepare", "timing_run"):
            if kind == "complete" and self.round >= BUILD_ROUNDS:
                _require(self._timing_complete, "completion arrived before the timing schedule finished")
            return super()._receive(message)
        raw = canonical_json(message)
        message = json.loads(raw)
        _require(message.get("epoch") == self.epoch and message.get("round") == BUILD_ROUNDS
                 and self.round == BUILD_ROUNDS and message.get("schedule_id") == ID,
                 "timing message is for a different epoch, round or schedule")
        index = message.get("index")
        _require(type(index) is int and 0 <= index < len(SEGMENTS), "invalid timing message index")
        _hash(message.get("plan_hash"), "timing plan hash")
        expected_keys = (_PLAN | {"kind", "plan_hash"} if kind == "timing_prepare" else
                         {"kind", "epoch", "round", "index", "schedule_id", "plan_hash"})
        _require(set(message) == expected_keys, "invalid timing message schema")
        key = kind, index
        cached = self._timing_cache.get(key)
        if cached:
            _require(cached[0] == raw, "conflicting duplicate timing command")
            return copy.deepcopy(cached[1])
        _require(index == self._timing_index, "timing segment skipped or replayed")
        self._verify_boundary()
        before = self._engine_boundary()
        _require(before["frame"] == self.frame, "native frame changed outside the replica")
        if kind == "timing_prepare":
            _require(self.phase in ("inputs", "timing_next") and not self._timing_complete,
                     "prepare arrived outside a fresh timing boundary")
            plan = _plan(self.epoch, self.manifest, index, before)
            _require(canonical_json({key: message[key] for key in _PLAN}) == canonical_json(plan)
                     and message["plan_hash"] == digest(plan),
                     "timing plan differs from the fixed schedule or actual world")
            self._timing_started = True
            if self._timing_started_ns is None:
                self._timing_started_ns = time.monotonic_ns()
            segment = SEGMENTS[index]
            delay = segment.delay_ms if segment.delayed_peer == self.peer else 0
            result = self.engine.check_idle_wait(delay, stop_requested=self._stop_requested)
            observed, metrics = self._receipt(result, before, "ready", delay)
            self._timing_plan = copy.deepcopy(message)
            self._timing_idle = metrics
            self.phase = "timing_run"
            reply = self._message("timing_ready", round=BUILD_ROUNDS, index=index,
                                  schedule_id=ID, plan_hash=message["plan_hash"], metrics=metrics, **observed)
        else:
            _require(self.phase == "timing_run" and self._timing_plan is not None
                     and message["plan_hash"] == self._timing_plan["plan_hash"],
                     "window has no matching prepared barrier")
            _require(all(before[key] == self._timing_plan[key] for key in _BOUNDARY),
                     "world changed after readiness but before window execution")
            result = self.engine.advance_window(WINDOW_STEPS, step_us=STEP_US, stop_requested=self._stop_requested)
            observed, metrics = self._receipt(result, before, "done")
            self.frame = observed["frame"]
            self._expected_boundary = self._boundary()
            self._timing_records.append({"index": index, "segment": dict(SEGMENTS[index]._asdict()),
                "start": before, "end": observed, "peer": self.peer,
                "idle": self._timing_idle, "window": metrics})
            self._timing_index += 1
            self._timing_complete = self._timing_index == len(SEGMENTS)
            if self._timing_complete:
                self._timing_finished_ns = time.monotonic_ns()
            self.phase = "inputs" if self._timing_complete else "timing_next"
            reply = self._message("timing_done", round=BUILD_ROUNDS, index=index,
                                  schedule_id=ID, plan_hash=message["plan_hash"], metrics=metrics, **observed)
        self._timing_cache[key] = raw, copy.deepcopy(reply)
        return reply

    def timing_progress(self):
        index = min(self._timing_index, len(SEGMENTS) - 1)
        return {"segment_index": self._timing_index, "segment_total": len(SEGMENTS),
                "label": SEGMENTS[index].label, "stage": self.phase,
                "started": self._timing_started, "completed": self._timing_complete, "frame": self.frame}

    def timing_report(self):
        return _report(self._timing_records, completed=self._timing_complete and not self.halted,
                       started=self._timing_started, scope="local_window_boundaries",
                       elapsed_ms=self._elapsed_ms())

    def _elapsed_ms(self):
        if self._timing_started_ns is None:
            return None
        return max(0, ((self._timing_finished_ns or time.monotonic_ns()) - self._timing_started_ns) // 1000000)
