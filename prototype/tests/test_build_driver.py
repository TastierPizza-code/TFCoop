"""Production profile/controller/TCP with two explicit engine fixtures, no TF2."""
import argparse
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from prototype.strict_sync import game_runner as driver
from prototype.strict_sync.core import digest
from prototype.tests.test_build_profile import observed_snapshot
from prototype.tests.test_engine_mailbox import native_bytes


class BuildEngineFixture:
    capabilities = driver.CAPABILITIES
    frame = 0
    def __init__(self, *, missing_debit=False):
        self.world = observed_snapshot()
        self.world["paused"] = True
        self.initial_time = self.time_us
        self.missing_debit = missing_debit
        self.closed = False
    @property
    def time_us(self): return self.world["sim_time_us"]
    @property
    def paused(self): return self.world["paused"]
    @property
    def state_digest(self): return digest(self.world)
    def snapshot(self): return copy.deepcopy(self.world)
    def close(self): self.closed = True
    def apply(self, command, key):
        if self.closed:
            raise ValueError("fixture closed")
        op = command["op"]
        probe = self.world["probe"]
        scene = probe["scene"]
        kind = None
        if op == "SET_PAUSED":
            self.world["paused"] = command["value"]
        elif op == "PROBE_ROAD":
            scene["road"], kind = key, "construction"
        elif op == "PROBE_DEPOT":
            scene["depot"], kind = key, "depot"
        elif op == "PROBE_STOP":
            scene.setdefault("stops", []).append(key)
            kind = "construction"
        elif op == "PROBE_VEHICLE":
            scene["vehicle"], kind = key, "vehicle"
            probe["vehicle"] = {"logical_id": key, "line": "", "in_depot": True, "state": 0, "no_path": False}
            if not self.missing_debit:
                self.world["company"]["balance"] -= 1000  # Explicit fixture value, never a game price.
        elif op == "PROBE_LINE":
            scene["line"], kind = key, "line"
            probe["line"] = {"logical_id": key, "vehicles": [], "stops": scene["stops"][:]}
            probe["connectivity"] = {"connected": True}
        elif op == "PROBE_ASSIGN":
            probe["vehicle"]["line"] = scene["line"]
            probe["line"]["vehicles"] = [scene["vehicle"]]
        else:
            raise ValueError("unsupported fixture intent")
        if kind:
            self.world["objects"].append({"logical_id": key, "kind": kind, "state": {"fixture": True}})
            self.world["objects"].sort(key=lambda item: item["logical_id"])
        return {"success": True, "result": {"command_key": key}, "state_digest": self.state_digest}
    def step(self, dt_us):
        if self.closed or dt_us != (0 if self.paused else 200000):
            raise ValueError("invalid fixture permit")
        self.world["sim_time_us"] += dt_us
        probe = self.world["probe"]
        if dt_us and probe.get("vehicle", {}).get("line"):
            probe["vehicle"].update(in_depot=False, state=1,
                                    position_mm=[(self.time_us - self.initial_time) // 1000, 0, 0])
        return {"state_digest": self.state_digest, "sim_time_us": self.time_us}


class BuildDriverTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, *, missing_debit):
        asyncio.get_running_loop().set_debug(False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            host_args = argparse.Namespace(epoch="build-fixture", timeout=5, rounds=240, bind="127.0.0.1", port=0,
                ready=root / "ready.json", report=root / "host-report.json")
            secret = b"x" * 32
            host = asyncio.create_task(driver.host(host_args, secret, expected_manifest="a" * 64,
                capabilities=driver.CAPABILITIES, backend="tf2_controlled_measurement", startup_timeout=10,
                step_us=driver.ENGINE_STEP_US))
            while not host_args.ready.exists():
                if host.done(): await host
                await asyncio.sleep(.001)
            port = json.loads(host_args.ready.read_text())["port"]
            engines = []
            def make_engine(*_args, **_kwargs):
                value = BuildEngineFixture(missing_debit=missing_debit)
                engines.append(value)
                return value
            def lease_start(_exe, directory, **_kwargs):
                (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=1))
                (directory / "lua_status.json").write_text(json.dumps({"protocol": 1, "epoch": "7",
                    "request": 0, "revision": 1, "status": "ready", "complete": True, "snapshot": {}}))
                return Mock()
            tasks, reports, journals = [], [], []
            with patch.object(driver, "ControllerGuard"), patch.object(driver, "game_is_running", return_value=False), \
                 patch.object(driver, "verify_payload"), patch.object(driver.LaunchLease, "create", side_effect=lease_start), \
                 patch.object(driver, "EngineAdapter", side_effect=make_engine), patch.object(driver.os, "fsync"):
                # This checks the 240-round TCP/proof integration, not a disk
                # durability benchmark. Separate journal tests exercise fsync.
                for peer in ("a", "b"):
                    run = root / peer
                    run.mkdir()
                    session = run / "session"
                    session.mkdir()
                    for name in driver.PREPARED_FILES: (session / name).write_text("fixture preparation")
                    args = argparse.Namespace(peer=peer, inputs=None, profile="build_v1", rounds=240, epoch="build-fixture",
                        host="127.0.0.1", port=port, timeout=5, startup_timeout=10, delay_ms=0,
                        report=run / "peer-report.json", progress=run / "peer-progress.json", stop_file=run / "stop")
                    setup = {"game_exe": str(root / "fixture-game.exe"), "native_epoch": 7,
                             "manifest_digest": "a" * 64, "measurement_profile": "build_v1"}
                    tasks.append(asyncio.create_task(driver.game_peer(args, secret, session, setup)))
                together = asyncio.gather(*tasks)
                done, _ = await asyncio.wait({together}, timeout=60)
                if not done:
                    for peer in ("a", "b"):
                        (root / peer / "stop").write_text("fixture deadline; stop cooperatively")
                    await asyncio.wait_for(asyncio.shield(together), 10)
                    self.fail("fixture protocol did not complete within 60 seconds")
                codes = together.result()
            host_code = await asyncio.wait_for(host, 10)
            for peer in ("a", "b"):
                reports.append(json.loads((root / peer / "peer-report.json").read_text()))
                journals.append([json.loads(line) for line in
                                 (root / peer / "peer-journal.jsonl").read_text(encoding="utf-8").splitlines()])
            return codes, host_code, json.loads(host_args.report.read_text()), reports, journals, engines

    async def test_two_engine_profile_completes_with_evidence_for_every_build_and_step(self):
        codes, host_code, host, reports, journals, engines = await self.run_fixture(missing_debit=False)
        self.assertEqual(codes, [0, 0])
        self.assertEqual(host_code, 0)
        self.assertTrue(host["coordinated_completed"])
        for report, journal in zip(reports, journals):
            self.assertTrue(report["build_proof"]["passed"])
            self.assertEqual(report["build_proof"]["elapsed_sim_time_us"], 42400000)
            self.assertEqual(len([record for record in journal if record["event"] == "stepped"]), 240)
            self.assertEqual(len([record for record in journal if record["event"] == "applied"]), 11)
            self.assertEqual(journal[-1]["event"], "completed")
        self.assertTrue(all(engine.closed for engine in engines))

    async def test_matching_worlds_without_actual_purchase_debit_never_get_host_completion(self):
        codes, host_code, host, reports, journals, engines = await self.run_fixture(missing_debit=True)
        self.assertEqual(codes, [2, 2])
        self.assertEqual(host_code, 2)
        self.assertFalse(host["coordinated_completed"])
        self.assertFalse(any(action["kind"] == "complete" for action in host["actions"]))
        self.assertEqual(host["frame"], 239, {"host_reason": host["reason"],
                                          "peer_reasons": [report["reason"] for report in reports]})
        self.assertTrue(any("actual debit" in report["reason"] for report in reports))
        self.assertTrue(all(report["build_proof"] is None for report in reports))
        self.assertTrue(all(journal[-1]["event"] == "failed" for journal in journals))
        self.assertTrue(all(engine.closed for engine in engines))


if __name__ == "__main__":
    unittest.main()
