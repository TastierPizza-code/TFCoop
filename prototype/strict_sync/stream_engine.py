"""Bounded paced native frontier with explicit, separate world checkpoints.

The wrapped EngineAdapter's cached world is historical between checkpoints.
Native frame/time receipts never contain a world hash or fabricated snapshot.
No game process, UI input, installation or network transport is created here.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import math
import threading
import time

from .core import MAX_INT, _hash
from .engine_mailbox import ENGINE_STEP_US, EngineAdapter, MailboxBusy, MailboxError, _uint


MAX_CHUNK_STEPS = 2
MAX_HOLD_MS = 2000
CHUNK_BUDGET_S = 3.0
CHECKPOINT_BUDGET_S = 3.0


class StreamEngine:
    """One exclusive stream owner around an already initialized probe adapter."""
    def __init__(self, engine, stop_requested=None):
        if not isinstance(engine, EngineAdapter):
            raise MailboxError("stream requires an actual EngineAdapter")
        if engine.halted or engine.native.halted:
            raise MailboxError("cannot start a stream on a halted adapter")
        if stop_requested is not None and not callable(stop_requested):
            raise MailboxError("stream stop_requested must be callable")
        self.engine = engine
        self.native = engine.native
        self._stop_requested = stop_requested
        self._mutex = threading.Lock()
        self.halted = False
        self.reason = ""
        self.frame = _uint(engine.frame, "stream initial frame", MAX_INT)
        self.time_us = _uint(engine.time_us, "stream initial simulation time", MAX_INT)
        self.paused = engine.paused
        if type(self.paused) is not bool:
            raise MailboxError("stream initial pause must be boolean")
        _hash(engine.state_digest, "stream initial observed digest")
        self._remember_observation()
        self._fresh = False
        self._started = False
        self._clock_origin = None
        self._next_call_deadline = None

    def _remember_observation(self):
        # Replace the complete record at once. A rejected later observation may
        # mutate the underlying adapter cache, but cannot relabel this snapshot
        # with another frame or simulation time during failure reporting.
        self._last_observation = {"frame": self.frame, "sim_time_us": self.time_us,
                                  "state_digest": self.engine.state_digest,
                                  "snapshot": self.engine.snapshot()}

    @property
    def last_observed_frame(self):
        return self._last_observation["frame"]

    @property
    def last_observed_time_us(self):
        return self._last_observation["sim_time_us"]

    @property
    def _last_digest(self):
        return self._last_observation["state_digest"]

    @property
    def last_observed_snapshot(self):
        """Defensive copy of the last accepted world, even after terminal HALT."""
        return copy.deepcopy(self._last_observation["snapshot"])

    @property
    def observations_fresh(self):
        """True means the cached observation belongs to this native frontier."""
        return (self._fresh and not self.halted and not self.engine.halted and not self.native.halted
                and self.last_observed_frame == self.frame == self.native.completed_frame
                and self.last_observed_time_us == self.time_us == self.engine.time_us
                and self._last_digest == self.engine.state_digest and self.paused is self.engine.paused)

    def snapshot(self):
        if not self.observations_fresh:
            raise MailboxError("stream world observation is historical; checkpoint required")
        return self.engine.snapshot()

    def _stop(self):
        self.engine._timing_stop(self._stop_requested)

    def _enter(self):
        if not self._mutex.acquire(blocking=False):
            raise MailboxBusy("stream operation still pending")
        if self.halted or self.engine.halted or self.native.halted:
            self._mutex.release()
            raise MailboxError("stream permanently halted")

    @contextmanager
    def _operation(self, duration_s):
        self._enter()
        engine_locked = False
        original_timeout = self.native.timeout_s
        original_deadline = self.native._operation_deadline
        try:
            self.engine._enter()
            engine_locked = True
            deadline = time.monotonic() + duration_s
            if original_deadline is not None:
                deadline = min(deadline, original_deadline)
            self.native._operation_deadline = deadline
            def budget():
                self._stop()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MailboxError("stream operation wall-clock budget exhausted")
                self.native.timeout_s = min(original_timeout, remaining)
            budget()
            yield budget
            budget()
        except Exception as exc:
            self.native.timeout_s = original_timeout
            self.native._operation_deadline = original_deadline
            self.halt(str(exc))
            raise
        finally:
            self.native.timeout_s = original_timeout
            self.native._operation_deadline = original_deadline
            if engine_locked:
                self.engine._mutex.release()
            self._mutex.release()

    def _gate(self, budget):
        budget()
        if self.native.completed_frame != self.frame:
            raise MailboxError("stream native frame changed outside its frontier")
        return self.engine._check_gate(self.time_us)

    def _boundary(self):
        return {"frame": self.frame, "sim_time_us": self.time_us,
                "paused": self.paused, "state_digest": self._last_digest}

    def _checkpoint(self, budget):
        self._gate(budget)
        budget()
        status = self.engine._request_lua("snapshot", expected_sim_time_us=self.time_us,
                                          boundary=str(self.frame))
        self.engine._accept_snapshot(status)
        if self.engine.time_us != self.time_us or self.engine.paused is not self.paused:
            raise MailboxError("stream world checkpoint disagrees with native time/shared pause")
        if (self.frame == self.last_observed_frame
                and self.engine.state_digest != self._last_digest):
            raise MailboxError("stream world changed without an authorized advance or command")
        self._gate(budget)
        self._remember_observation()
        self._fresh = self._started = True
        return self._boundary()

    def checkpoint(self):
        """Request exactly one fresh Lua observation at the native frontier."""
        with self._operation(CHECKPOINT_BUDGET_S) as budget:
            return self._checkpoint(budget)

    def advance(self, steps):
        """Advance one or two native steps; do not read or rewrite cached Lua state."""
        with self._operation(CHUNK_BUDGET_S) as budget:
            started = time.perf_counter()
            _uint(steps, "stream chunk steps", MAX_CHUNK_STEPS, 1)
            if not self._started:
                raise MailboxError("stream requires a first fresh checkpoint")
            if self.paused:
                raise MailboxError("stream cannot advance while shared pause is on")
            _uint(self.frame + steps, "stream target frame", MAX_INT)
            _uint(self.time_us + steps * ENGINE_STEP_US, "stream target time", MAX_INT)
            self._gate(budget)
            period = ENGINE_STEP_US / 1_000_000
            if self._clock_origin is None:
                self._clock_origin = time.perf_counter()
                self._next_call_deadline = self._clock_origin + period
            records = []
            for _ in range(steps):
                deadline = self._next_call_deadline
                while True:
                    budget()
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        break
                    time.sleep(min(remaining, 0.01, self.native.timeout_s))
                budget()
                called = time.perf_counter()
                expected_frame = self.frame + 1
                before_time = self.time_us
                expected_time = before_time + ENGINE_STEP_US
                # Even an unacknowledged permit attempt makes the old world an
                # historical observation until another checkpoint verifies it.
                self._fresh = False
                native = self.native.permit(expected_frame, ENGINE_STEP_US)
                acknowledged = time.perf_counter()
                if (native["completed_frame"] != expected_frame
                        or self.native.completed_frame != expected_frame
                        or native["completed_dt_us"] != ENGINE_STEP_US or native["pending_state"] != 0
                        or native["time_before_ms"] * 1000 not in (before_time, expected_time)
                        or native["time_after_ms"] * 1000 != expected_time):
                    raise MailboxError("stream native clock/frame differs from its permitted step")
                self.frame, self.time_us = expected_frame, expected_time
                records.append({"frame": self.frame, "sim_time_us": self.time_us,
                    "scheduled_offset_us": round((deadline - self._clock_origin) * 1_000_000),
                    "call_started_offset_us": round((called - self._clock_origin) * 1_000_000),
                    "ack_observed_offset_us": round((acknowledged - self._clock_origin) * 1_000_000),
                    "permit_duration_us": round((acknowledged - called) * 1_000_000),
                    "lateness_us": max(0, round((called - deadline) * 1_000_000)),
                    "native_time_before_ms": native["time_before_ms"],
                    "native_time_after_ms": native["time_after_ms"]})
                self._next_call_deadline = called + period
                # Preserve each verified native frontier before processing a
                # stop that arrived during this already authorized permit.
                budget()
            budget()
            metrics = {"kind": "stream_advance", "steps_requested": steps,
                       "step_us": ENGINE_STEP_US, "simulated_us": steps * ENGINE_STEP_US,
                       "duration_ms": math.ceil((time.perf_counter() - started) * 1000),
                       "steps": records, "world_observation": "none",
                       "clock_origin": "stream_local_monotonic", "native_clock_each_step": True}
            return {"frame": self.frame, "sim_time_us": self.time_us, "metrics": metrics}

    def apply(self, command, command_key):
        """Use the existing command path only at a freshly observed frontier."""
        self._enter()
        try:
            self._stop()
            if not self.observations_fresh:
                raise MailboxError("stream command requires a fresh checkpoint")
            before_frame, before_time, before_pause = self.frame, self.time_us, self.paused
            result = self.engine.apply(command, command_key)
            if self.engine.frame != before_frame or self.engine.time_us != before_time:
                raise MailboxError("stream command moved the native frontier")
            if (type(result) is not dict or type(result.get("success")) is not bool
                    or result.get("state_digest") != self.engine.state_digest):
                raise MailboxError("stream command receipt does not describe the fresh observed world")
            if (result["success"] and command.get("op") == "SET_PAUSED"
                    and self.engine.paused is not command.get("value")):
                raise MailboxError("stream pause receipt disagrees with the fresh observed pause")
            if not result["success"]:
                self.halt("stream command failed")
                return result
            self.paused = self.engine.paused
            self._remember_observation()
            self._fresh = True
            if before_pause and not self.paused:
                # A deliberate shared pause does not count as scheduling
                # lateness. Keep the common local origin but rebase the pacer.
                self._next_call_deadline = time.perf_counter() + ENGINE_STEP_US / 1_000_000
            self._stop()
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def hold(self, duration_ms):
        """Measure an explicit bounded hold with fresh observations at both ends."""
        # Invalid arguments still enter the same terminal error path, without
        # allowing an invalid duration to choose the operation deadline.
        bounded = duration_ms if type(duration_ms) is int and 0 <= duration_ms <= MAX_HOLD_MS else 0
        with self._operation(bounded / 1000 + CHECKPOINT_BUDGET_S) as budget:
            started = time.perf_counter()
            _uint(duration_ms, "stream hold duration_ms", MAX_HOLD_MS)
            before = self._checkpoint(budget)
            native_before = self.engine._timing_sample(self._gate(budget))
            wait_started = time.perf_counter()
            deadline = wait_started + duration_ms / 1000
            while True:
                budget()
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, .01, self.native.timeout_s))
            wait_ended = time.perf_counter()
            after = self._checkpoint(budget)
            native_after = self.engine._timing_sample(self._gate(budget))
            if after != before:
                raise MailboxError("stream hold changed its observed world boundary")
            deltas = {name: (native_after[name] - native_before[name]
                            if native_after[name] is not None and native_before[name] is not None else None)
                      for name in ("hold_calls", "outer_calls", "updated_ms")}
            maintenance = (deltas["updated_ms"] is not None and deltas["updated_ms"] > 0
                           and deltas["hold_calls"] is not None and deltas["hold_calls"] > 0)
            metrics = {"kind": "stream_hold", "requested_delay_ms": duration_ms,
                       "actual_delay_ms": math.ceil((wait_ended - wait_started) * 1000),
                       "duration_ms": math.ceil((time.perf_counter() - started) * 1000),
                       "boundary_unchanged": True, "native_before": native_before,
                       "native_after": native_after, "counter_deltas": deltas,
                       "maintenance_observed": maintenance}
            return {**after, "metrics": metrics}

    def halt(self, reason="stream explicitly halted"):
        if not self.halted:
            self.halted = True
            self.reason = str(reason)
            self._fresh = False
            self.engine.halt(self.reason)

    def close(self):
        self.halt("stream closed")
