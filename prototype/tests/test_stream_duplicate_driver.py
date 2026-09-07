"""Duplicate server grants over real TCP, with explicitly modeled game execution."""
import copy
import unittest
from unittest.mock import patch

from prototype.strict_sync import runner
from prototype.tests import test_stream_driver as stream_driver_fixture


class StreamDuplicateDriverTests(unittest.IsolatedAsyncioTestCase):
    run_fixture = stream_driver_fixture.StreamDriverTests.run_fixture

    async def test_old_start_duplicates_neither_reexecute_nor_relabel_journal_snapshots(self):
        real_send = runner.send
        starts, injections = {}, []

        async def duplicate_start(writer, message, *args, **kwargs):
            kind = message.get("kind")
            if kind == "stream_start":
                starts[writer] = copy.deepcopy(message)
            await real_send(writer, message, *args, **kwargs)
            trigger = ((kind == "stream_advance" and message.get("index") == 1)
                       or (kind == "stream_checkpoint" and message.get("index") == 2))
            if trigger:
                # First duplicate arrives after a native-only chunk, when the
                # cached world is historical. The second arrives after a later
                # fresh checkpoint; its world still does not belong to start.
                self.assertIn(writer, starts)
                injections.append((writer, kind, message["index"]))
                await real_send(writer, copy.deepcopy(starts[writer]), *args, **kwargs)

        with patch.object(runner, "send", side_effect=duplicate_start):
            codes, host_code, host, reports, journals, _, engines, wrappers = await self.run_fixture()

        self.assertEqual((codes, host_code), ([0, 0], 0), [report["reason"] for report in reports.values()])
        self.assertEqual(len(starts), 2)
        self.assertEqual(len(injections), 4)
        self.assertEqual(host["frame"], 840)
        self.assertTrue(host["coordinated_completed"])
        self.assertTrue(host["stream"]["completed"])
        for peer in ("a", "b"):
            self.assertTrue(reports[peer]["finished"])
            self.assertEqual(len(wrappers[peer].advances), 300)
            self.assertEqual(wrappers[peer].checkpoint_frames, list(range(240, 841, 50)))
            rows = [row for row in journals[peer] if row["event"].startswith("stream_")]
            self.assertEqual(len(rows), 16)
            self.assertEqual([row["frame"] for row in rows if row["event"] == "stream_ready"], [240])
            self.assertEqual([row["frame"] for row in rows if row["event"] == "stream_checkpointed"],
                             list(range(290, 841, 50)))
            self.assertEqual([row["frame"] for row in rows if row["event"] == "stream_applied"], [540, 540])
            self.assertEqual([row["frame"] for row in rows if row["event"] == "stream_held"], [540])
            for row in rows:
                expected = engines[peer].initial_time + 42200000 + (row["frame"] - 240) * stream_driver_fixture.STEP_US
                self.assertEqual(row["snapshot"]["sim_time_us"], expected)
            self.assertEqual(journals[peer][-1]["frame"], 840)


if __name__ == "__main__":
    unittest.main()
