"""The manual-loading clock transition must remain monotonic at a repeated tick."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from prototype.strict_sync import runner


class ClockHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_tick_cannot_round_running_clock_below_startup_clock(self):
        # At transition the old expression is .3 + .6 - .6 < .3. Replace only
        # runner's time binding; asyncio retains the real monotonic clock.
        reads = iter((.3,))
        coarse_time = SimpleNamespace(monotonic=lambda: next(reads, .6))
        with tempfile.TemporaryDirectory() as temporary, patch.object(runner, "time", coarse_time):
            root = Path(temporary)
            secret = b"x" * 32
            host_args = argparse.Namespace(epoch="clock-regression", timeout=1, rounds=1, bind="127.0.0.1",
                port=0, ready=root / "ready.json", report=root / "host.json")
            host = asyncio.create_task(runner.host(host_args, secret, startup_timeout=10))
            while not host_args.ready.exists():
                if host.done(): await host
                await asyncio.sleep(.001)
            port = json.loads(host_args.ready.read_text())["port"]
            peers = []
            for peer in ("a", "b"):
                args = argparse.Namespace(epoch=host_args.epoch, timeout=1, host="127.0.0.1", port=port,
                    peer=peer, fault="", stop_round=3, delay_ms=0, fragment=0, duplicate=False,
                    report=root / (peer + ".json"))
                peers.append(asyncio.create_task(runner.peer(args, secret)))
            results = await asyncio.wait_for(asyncio.gather(*peers), 5)
            host_code = await asyncio.wait_for(host, 5)
            report = json.loads(host_args.report.read_text())
            self.assertEqual(results, [0, 0], report["reason"])
            self.assertEqual(host_code, 0, report["reason"])
            self.assertEqual(report["frame"], 1)
            self.assertTrue(report["coordinated_completed"])


if __name__ == "__main__":
    unittest.main()
