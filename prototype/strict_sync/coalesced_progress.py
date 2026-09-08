"""Bounded informational launcher updates for the separate paced-live mode.

This wrapper never buffers protocol messages, engine receipts or world journals.
It only coalesces the replaceable launcher status document. A later call carries
the latest facts; lifecycle and shared-input confirmations publish immediately.
"""
from __future__ import annotations

import copy
import math
import time


class CoalescedProgress:
    def __init__(self, sink, *, interval_s=.25, clock=None):
        if not callable(sink):
            raise ValueError("progress sink must be callable")
        if (type(interval_s) not in (int, float) or not math.isfinite(interval_s)
                or not 0 < interval_s <= 1):
            raise ValueError("progress interval must be in (0, 1] seconds")
        self._sink, self._interval = sink, interval_s
        self._clock = clock or time.perf_counter
        self._last_published_at = None
        self._last_confirmations = None
        self._sink_calls = self._suppressed = self._failures = 0
        self._duration_us = self._max_duration_us = 0

    @staticmethod
    def _confirmations(state, facts):
        live = facts.get("live") or {}
        # An engine-local pause value can precede the shared confirmation.
        # Keep those existing semantics: only confirmed state/sequence changes
        # bypass the display throttle, alongside readiness and terminal facts.
        return copy.deepcopy((state, facts.get("peers"), facts.get("coordinated_completed"),
            tuple(live.get(key) for key in ("started", "completed", "confirmed_paused",
                "acknowledged_seq", "ending", "long_pause_met"))))

    def __call__(self, state, **facts):
        now = self._clock()
        confirmations = self._confirmations(state, facts)
        urgent = (state != "running" or confirmations != self._last_confirmations
                  or any(facts.get(key) for key in ("reason", "error", "failure")))
        if (not urgent and self._last_published_at is not None
                and now - self._last_published_at < self._interval):
            self._suppressed += 1
            return
        self._sink_calls += 1
        sink_started = self._clock()
        try:
            self._sink(state, **facts)
        except Exception:
            # The caller retains its existing fail-stop behavior. A failed
            # publication is never recorded as successful or silently retried.
            self._failures += 1
            raise
        finally:
            elapsed = max(0, round((self._clock() - sink_started) * 1_000_000))
            self._duration_us += elapsed
            self._max_duration_us = max(self._max_duration_us, elapsed)
        self._last_published_at = now
        self._last_confirmations = confirmations

    def metrics(self):
        return {"mode": "coalesced_launcher_status_v1",
                "interval_ms": round(self._interval * 1000),
                "sink_calls": self._sink_calls, "suppressed_calls": self._suppressed,
                "failed_sink_calls": self._failures,
                "sink_duration_us": self._duration_us,
                "max_sink_duration_us": self._max_duration_us,
                "scope": "local synchronous status sink calls; unchanged documents may skip disk writes"}
