"""Display coalescing must never delay actual input confirmations or failures."""
import copy
import unittest

from prototype.strict_sync.coalesced_progress import CoalescedProgress


class CoalescedProgressTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.records = []
        self.live = {"started": True, "completed": False, "confirmed_paused": False,
                     "acknowledged_seq": {"a": 0, "b": 0}, "ending": False,
                     "long_pause_met": False}
        self.progress = CoalescedProgress(self.sink, clock=lambda: self.now)

    def sink(self, state, **facts):
        self.records.append((state, copy.deepcopy(facts)))

    def publish(self, **facts):
        self.progress("running", live=self.live, **facts)

    def test_rapid_frames_and_phases_coalesce_to_latest_available_update(self):
        self.publish(frame=10, message="paced_start")
        self.now += .1
        self.publish(frame=11, message="paced_advance")
        self.now += .1
        self.publish(frame=12, message="paced_advanced")
        self.assertEqual(len(self.records), 1)
        self.now += .1
        self.publish(frame=14, message="paced_advance")
        self.assertEqual([r[1]["frame"] for r in self.records], [10, 14])
        self.assertEqual(self.progress.metrics()["suppressed_calls"], 2)

    def test_shared_confirmation_sequence_is_immediate_even_when_pause_is_same(self):
        self.publish()
        self.live["acknowledged_seq"]["a"] = 1
        self.publish()
        self.assertEqual(len(self.records), 2)
        self.assertEqual(self.records[-1][1]["live"]["acknowledged_seq"]["a"], 1)

    def test_local_pause_is_not_promoted_to_a_shared_confirmation(self):
        self.publish()
        self.live["paused"] = True
        self.publish()
        self.assertEqual(len(self.records), 1)
        self.live["confirmed_paused"] = True
        self.publish()
        self.assertEqual(len(self.records), 2)

    def test_readiness_end_and_long_pause_coverage_are_immediate(self):
        self.live["started"] = False
        self.publish()
        for key in ("started", "ending", "long_pause_met", "completed"):
            self.live[key] = True
            self.publish()
        self.assertEqual(len(self.records), 5)

    def test_peer_membership_and_terminal_failure_are_immediate(self):
        self.publish(peers=["a"])
        self.publish(peers=["a", "b"])
        self.progress("halted", reason="peer disconnected", live=self.live)
        self.assertEqual(len(self.records), 3)
        self.assertEqual(self.records[-1][0], "halted")

    def test_nonempty_diagnostic_is_never_suppressed(self):
        self.publish()
        for key in ("reason", "error", "failure"):
            self.publish(**{key: "unavailable"})
        self.assertEqual(len(self.records), 4)

    def test_sink_failure_propagates_and_does_not_consume_confirmation(self):
        def failed_sink(state, **facts):
            raise OSError("status unavailable")
        self.progress._sink = failed_sink
        with self.assertRaises(OSError):
            self.publish()
        self.progress._sink = self.sink
        self.publish()
        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.progress.metrics()["failed_sink_calls"], 1)

    def test_timing_is_local_sink_cost_and_defensive_metrics(self):
        def slow_sink(state, **facts):
            self.now += .035
            self.sink(state, **facts)
        self.progress._sink = slow_sink
        self.publish()
        metrics = self.progress.metrics()
        self.assertEqual(metrics["sink_duration_us"], 35000)
        self.assertEqual(metrics["max_sink_duration_us"], 35000)
        metrics["sink_calls"] = 100
        self.assertEqual(self.progress.metrics()["sink_calls"], 1)

    def test_invalid_interval_or_sink_rejected(self):
        for value in (0, -1, 2, True, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                CoalescedProgress(self.sink, interval_s=value)
        with self.assertRaises(ValueError):
            CoalescedProgress(None)


if __name__ == "__main__":
    unittest.main()
