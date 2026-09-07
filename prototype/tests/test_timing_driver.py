"""Production TCP/build/timing integration with explicit engine models, never TF2.

The fixture supplies invented timing measurements immediately. These tests check
protocol/report plumbing and rejection paths, not game speed or determinism.
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from prototype.strict_sync import game_runner as driver
from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.timing_probe import (
    SEGMENTS, STEP_US, TIMING_CAPABILITY, WINDOW_STEPS, TimingCoordinator,
)
from prototype.tests.test_build_driver import BuildEngineFixture
from prototype.tests.test_engine_mailbox import native_bytes


class BuildTimingEngineFixture(BuildEngineFixture):
    """Build model plus explicit invented native-clock/cadence observations."""

    def __init__(self, peer, *, fault="", final_waiting=None, release_final=None):
        super().__init__()
        self.peer, self.fault, self.frame = peer, fault, 0
        self.waits, self.windows = [], []
        self.final_waiting, self.release_final = final_waiting, release_final

    def step(self, dt_us):
        result = super().step(dt_us)
        self.frame += 1
        return result

    def receipt(self, metrics):
        return {"frame": self.frame, "sim_time_us": self.time_us,
                "state_digest": self.state_digest, "metrics": metrics}

    def check_idle_wait(self, delay, *, stop_requested=None):
        if stop_requested and stop_requested():
            raise ProtocolError("timing model stopped")
        self.waits.append(delay)
        if self.fault == "changed_idle":
            self.world["company"]["balance"] += 1
        return self.receipt({
            "kind": "idle_wait", "requested_delay_ms": delay,
            "actual_delay_ms": 0 if self.fault == "missing_wait" else delay,
            "duration_ms": delay + 1, "boundary_unchanged": True,
            "maintenance_observed": delay > 0,
            "native_before": None, "native_after": None,
            "counter_deltas": {"hold_calls": int(delay > 0),
                               "outer_calls": int(delay > 0), "updated_ms": delay},
        })

    def advance_window(self, count, step_us=STEP_US, stop_requested=None):
        if stop_requested and stop_requested():
            raise ProtocolError("timing model stopped")
        if count != WINDOW_STEPS or step_us != STEP_US:
            raise ProtocolError("unexpected fixture window")
        self.windows.append(count)
        interval_us = 300000 if self.fault == "slow" else STEP_US
        steps = []
        for index in range(count):
            before = self.time_us
            self.step(step_us)
            scheduled = (index + 1) * STEP_US
            admitted = (index + 1) * interval_us
            steps.append({"frame": self.frame, "sim_time_us": self.time_us,
                "scheduled_offset_us": scheduled, "admitted_offset_us": admitted,
                "ack_observed_offset_us": admitted + 1000,
                "permit_duration_us": 1000, "lateness_us": admitted - scheduled,
                "native_time_before_ms": before // 1000,
                "native_time_after_ms": self.time_us // 1000})
        if self.fault == "shifted_endpoint":
            self.world["company"]["balance"] += 1
        duration_ms = (count * interval_us) // 1000 + 1
        result = self.receipt({
            "kind": "advance_window", "steps_requested": count, "step_us": STEP_US,
            "simulated_us": count * STEP_US, "duration_ms": duration_ms,
            "rate_ppm": count * STEP_US * 1000 // duration_ms, "steps": steps,
            "world_observation": "start_and_end_only", "native_clock_each_step": True,
        })
        if len(self.windows) == len(SEGMENTS) and self.release_final is not None:
            self.final_waiting.set()
            if not self.release_final.wait(10):
                raise ProtocolError("test did not release its final model receipt")
        return result


class TimingDriverTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, *, fault="", hold_final=False):
        asyncio.get_running_loop().set_debug(False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs, sessions = {}, {}
            for peer in ("a", "b"):
                runs[peer] = root / peer
                sessions[peer] = runs[peer] / "session"
                sessions[peer].mkdir(parents=True)
                for name in driver.PREPARED_FILES:
                    (sessions[peer] / name).write_text("explicit fixture preparation")
            base_args = dict(epoch="timing-driver-model", timeout=15, rounds=240,
                             timing_probe=True, profile="build_v2", delay_ms=0)
            host_args = argparse.Namespace(**base_args, bind="127.0.0.1", port=0,
                ready=runs["a"] / "host-ready.json", report=runs["a"] / "host-report.json")
            secret = b"timing-driver-fixture-key-32-bytes"
            progress, engines = [], {}
            stop_host = threading.Event()
            final_waiting, release_final = threading.Event(), threading.Event()
            tasks = []
            host = asyncio.create_task(driver.host(host_args, secret, expected_manifest="a" * 64,
                capabilities=driver.measurement_capabilities(host_args),
                backend="explicit_model_only", startup_timeout=10,
                progress=lambda state, **fields: progress.append({"state": state, **fields}),
                stop_requested=stop_host.is_set, step_us=STEP_US,
                coordinator_factory=TimingCoordinator))

            def make_engine(directory, *_args, **_kwargs):
                peer = Path(directory).parent.name
                engine = BuildTimingEngineFixture(peer, fault=fault if peer == "b" else "",
                    final_waiting=final_waiting,
                    release_final=release_final if peer == "b" and hold_final else None)
                engines[peer] = engine
                return engine

            def lease_start(_exe, directory, **_kwargs):
                (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=1))
                (directory / "lua_status.json").write_text(json.dumps({"protocol": 1, "epoch": "7",
                    "request": 0, "revision": 1, "status": "ready", "complete": True, "snapshot": {}}))
                return Mock()

            async def wait_until(predicate, message):
                deadline = asyncio.get_running_loop().time() + 45
                while not predicate():
                    if host.done():
                        await host
                        self.fail(message + ": host ended early")
                    if asyncio.get_running_loop().time() >= deadline:
                        self.fail(message + ": fixture deadline")
                    await asyncio.sleep(.005)

            try:
                await wait_until(host_args.ready.exists, "host readiness")
                port = json.loads(host_args.ready.read_text())["port"]
                with patch.object(driver, "ControllerGuard"), \
                     patch.object(driver, "game_is_running", return_value=False), \
                     patch.object(driver, "verify_payload"), \
                     patch.object(driver.LaunchLease, "create", side_effect=lease_start), \
                     patch.object(driver, "EngineAdapter", side_effect=make_engine), \
                     patch.object(driver.os, "fsync"):
                    # Journal durability has separate tests; no game/native timer is patched.
                    for peer in ("a", "b"):
                        args = argparse.Namespace(**base_args, peer=peer, inputs=None,
                            host="127.0.0.1", port=port, startup_timeout=10,
                            report=runs[peer] / "peer-report.json",
                            progress=runs[peer] / "peer-progress.json", stop_file=runs[peer] / "stop")
                        setup = {"game_exe": str(root / "fixture-game.exe"), "native_epoch": 7,
                                 "manifest_digest": "a" * 64, "measurement_profile": "build_v2"}
                        tasks.append(asyncio.create_task(driver.game_peer(args, secret, sessions[peer], setup)))
                    if hold_final:
                        def first_peer_finished_window():
                            path = runs["a"] / "peer-progress.json"
                            if not path.is_file():
                                return False
                            try:
                                value = json.loads(path.read_text())
                            except (OSError, ValueError):
                                return False
                            return bool((value.get("timing") or {}).get("completed"))
                        await wait_until(lambda: final_waiting.is_set() and first_peer_finished_window(),
                                         "one final timing receipt remains withheld")
                        self.assertEqual(engines["a"].frame, 540)
                        self.assertEqual(engines["b"].frame, 540)
                        self.assertFalse(host.done())
                        self.assertFalse(any(item["state"] == "completed" for item in progress))
                        self.assertFalse(host_args.report.exists())
                        self.assertFalse(any((run / "peer-report.json").exists() for run in runs.values()))
                        self.assertEqual(progress[-1]["frame"], 515)
                        self.assertEqual(progress[-1]["timing"]["stage"], "timing_done")
                        release_final.set()
                    codes = await asyncio.wait_for(asyncio.gather(*tasks), 60)
                    host_code = await asyncio.wait_for(host, 10)
            finally:
                release_final.set()
                stop_host.set()
                for run in runs.values():
                    (run / "stop").write_text("fixture cleanup")
                outstanding = [task for task in [*tasks, host] if not task.done()]
                if outstanding:
                    done, pending = await asyncio.wait(outstanding, timeout=10)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*outstanding, return_exceptions=True)

            host_report = json.loads(host_args.report.read_text())
            reports, journals, exports = {}, {}, {}
            for peer in ("a", "b"):
                reports[peer] = json.loads((runs[peer] / "peer-report.json").read_text())
                journals[peer] = [json.loads(line) for line in
                    (runs[peer] / "peer-journal.jsonl").read_text(encoding="utf-8").splitlines()]
                prepared = workflow.PreparedRun(str(runs[peer]), str(root / "fixture-game"),
                    str(sessions[peer]), str(runs[peer] / "payload"), str(root / "save/imported.sav"),
                    str(root / "backup"), peer, "127.0.0.1", base_args["epoch"], "a" * 64)
                archive_path = workflow.export_diagnostics(prepared, root / (peer + "-diagnostics.zip"))
                with zipfile.ZipFile(archive_path) as archive:
                    exports[peer] = {name: archive.read(name) for name in archive.namelist()}
            return codes, host_code, host_report, reports, journals, exports, engines

    async def test_full_build_then_twelve_windows_waits_for_both_final_receipts_and_exports_evidence(self):
        codes, host_code, host, reports, journals, exports, engines = await self.run_fixture(hold_final=True)
        self.assertEqual(codes, [0, 0], [report["reason"] for report in reports.values()])
        self.assertEqual(host_code, 0, host["reason"])
        self.assertTrue(host["coordinated_completed"])
        self.assertEqual((host["round"], host["frame"]), (240, 540))
        timing = host["timing"]
        self.assertTrue(timing["completed"])
        self.assertEqual(timing["segments_completed"], 12)
        self.assertEqual(timing["additional_simulated_us"], 60000000)
        self.assertTrue(timing["paced_windows_1x_met"])
        self.assertFalse(timing["visual_smoothness_verified"])
        self.assertFalse(timing["complete_world_verified"])
        self.assertEqual(timing["delay_scope"], "synthetic_local_hold_not_network_rtt")
        self.assertEqual([action["kind"] for action in host["actions"][-2:]], ["complete", "complete"])
        for kind in ("timing_prepare", "timing_run"):
            self.assertEqual(len([item for item in host["actions"] if item["kind"] == kind]), 24)
        for peer in ("a", "b"):
            report, journal, engine = reports[peer], journals[peer], engines[peer]
            self.assertTrue(report["finished"])
            self.assertTrue(report["build_proof"]["passed"])
            self.assertEqual(report["build_proof"]["elapsed_sim_time_us"], 42200000)
            self.assertEqual(report["frame"], 540)
            self.assertTrue(report["timing"]["completed"])
            self.assertEqual(report["timing"]["additional_simulated_us"], 60000000)
            self.assertEqual(report["snapshot"]["sim_time_us"] - engine.initial_time, 102200000)
            self.assertEqual(engine.waits,
                [item.delay_ms if item.delayed_peer == peer else 0 for item in SEGMENTS])
            self.assertEqual(engine.windows, [WINDOW_STEPS] * len(SEGMENTS))
            for event, count in (("stepped", 240), ("applied", 12), ("timing_ready", 12), ("timing_done", 12)):
                self.assertEqual(len([record for record in journal if record["event"] == event]), count)
            self.assertEqual((journal[-1]["event"], journal[-1]["frame"]), ("completed", 540))
            self.assertEqual(json.loads(exports[peer]["peer-report.json"]), report)
            exported_journal = [json.loads(line) for line in exports[peer]["peer-journal.jsonl"].splitlines()]
            self.assertEqual(exported_journal, journal)
            self.assertTrue(engine.closed)
        self.assertEqual(json.loads(exports["a"]["host-report.json"]), host)

    async def test_changed_idle_boundary_stops_both_before_any_window(self):
        result = await self.run_fixture(fault="changed_idle")
        codes, host_code, host, reports, journals, _, engines = result
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertFalse(host["coordinated_completed"])
        self.assertEqual(host["frame"], 240)
        self.assertTrue(any("world changed" in report["reason"] for report in reports.values()))
        self.assertTrue(all(not engine.windows and engine.closed for engine in engines.values()))
        self.assertTrue(all(journal[-1]["event"] == "failed" for journal in journals.values()))
        self.assertFalse(any(action["kind"] == "complete" for action in host["actions"]))

    async def test_scheduled_delay_without_full_measurement_is_terminal(self):
        codes, host_code, host, reports, journals, _, engines = await self.run_fixture(fault="missing_wait")
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertFalse(host["coordinated_completed"])
        self.assertEqual(host["frame"], 340)  # b's first injected delay is window five.
        self.assertEqual(host["timing"]["segments_completed"], 4)
        self.assertTrue(any("wait was not measured in full" in report["reason"] for report in reports.values()))
        self.assertTrue(all(len(engine.windows) == 4 and engine.closed for engine in engines.values()))
        self.assertTrue(all(journal[-1]["event"] == "failed" for journal in journals.values()))

    async def test_shifted_endpoint_stops_before_next_window(self):
        codes, host_code, host, reports, journals, _, engines = await self.run_fixture(fault="shifted_endpoint")
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertIn("end world differs", host["reason"])
        self.assertEqual(host["frame"], 240)
        self.assertEqual(host["timing"]["segments_completed"], 0)
        self.assertFalse(host["coordinated_completed"])
        self.assertTrue(all(len(engine.windows) == 1 and engine.closed for engine in engines.values()))
        self.assertTrue(all(not report["finished"] for report in reports.values()))
        self.assertTrue(all(journal[-1]["event"] == "failed" for journal in journals.values()))

    async def test_slow_matching_windows_complete_sync_without_claiming_one_times_target(self):
        codes, host_code, host, reports, _, exports, engines = await self.run_fixture(fault="slow")
        self.assertEqual((codes, host_code), ([0, 0], 0))
        self.assertTrue(host["coordinated_completed"])
        self.assertTrue(host["timing"]["completed"])
        self.assertFalse(host["timing"]["paced_windows_1x_met"])
        self.assertTrue(reports["a"]["timing"]["paced_windows_1x_met"])
        self.assertFalse(reports["b"]["timing"]["paced_windows_1x_met"])
        self.assertEqual(host["timing"]["peer_timing_summaries"]["b"]["admission_intervals"]["p95_us"], 300000)
        self.assertEqual(reports["a"]["snapshot"], reports["b"]["snapshot"])
        self.assertFalse(json.loads(exports["b"]["peer-report.json"])["timing"]["paced_windows_1x_met"])
        self.assertTrue(all(engine.frame == 540 and engine.closed for engine in engines.values()))


class TimingSelectionTests(unittest.TestCase):
    def test_timing_selection_requires_build_profile_no_legacy_delay_and_sufficient_phase_timeout(self):
        args = argparse.Namespace(profile="build_v2", rounds=240, timing_probe=True, timeout=15, delay_ms=0)
        setup = {"measurement_profile": "build_v2"}
        self.assertEqual(driver.selected_profile(args, setup), "build_v2")
        self.assertIn(TIMING_CAPABILITY, driver.measurement_capabilities(args))
        for field, value in (("timeout", 14), ("delay_ms", 1), ("rounds", 239)):
            invalid = argparse.Namespace(**{**vars(args), field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                driver.selected_profile(invalid, setup)


if __name__ == "__main__":
    unittest.main()
