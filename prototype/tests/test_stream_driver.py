"""Production stream/TCP integration with explicit game and clock models.

No game starts or real-time pacing occurs here. Invented native measurements
exercise ordering, failure handling, snapshots and report transport only.
"""
import argparse
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from prototype.strict_sync import game_runner as driver
from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync import stream_probe
from prototype.strict_sync import stream_engine as stream_backend
from prototype.strict_sync.core import ProtocolError, digest
from prototype.tests.test_build_driver import BuildEngineFixture
from prototype.tests.test_engine_mailbox import native_bytes


STEP_US = 200000
BUILD_FRAMES = 240
STREAM_STEPS = 600
FINAL_FRAME = BUILD_FRAMES + STREAM_STEPS


class CachedBuildEngineFixture(BuildEngineFixture):
    """The base adapter's observation remains stale between stream checkpoints."""

    def __init__(self, peer):
        self.stream_started = False
        super().__init__()
        self.peer, self.frame = peer, 0
        self.observed = copy.deepcopy(self.world)
        self.observed_frame = 0
        self.command_calls = []

    @property
    def time_us(self):
        return (self.observed if self.stream_started else self.world)["sim_time_us"]

    @property
    def paused(self):
        return (self.observed if self.stream_started else self.world)["paused"]

    @property
    def state_digest(self):
        return digest(self.observed if self.stream_started else self.world)

    def snapshot(self):
        return copy.deepcopy(self.observed if self.stream_started else self.world)

    def observe(self):
        self.observed = copy.deepcopy(self.world)
        self.observed_frame = self.frame

    def step(self, dt_us):
        if self.stream_started:
            raise ProtocolError("ordinary fixture step must not be used in stream mode")
        result = super().step(dt_us)
        self.frame += 1
        self.observe()
        return result

    def apply(self, command, key):
        self.command_calls.append((self.frame, key, copy.deepcopy(command)))
        stream_started = self.stream_started
        self.stream_started = False
        try:
            result = super().apply(command, key)
            self.observe()
            return result
        finally:
            self.stream_started = stream_started


class StreamEngineFixture:
    """Explicit wrapper stand-in. Measurements are invented, never wall timing."""

    def __init__(self, engine, stop_requested=None, *, fault="", final_waiting=None, release_final=None):
        self.engine, self.stop_requested = engine, stop_requested
        self.fault = fault
        self.final_waiting, self.release_final = final_waiting, release_final
        self.advances, self.checkpoint_frames, self.holds = [], [], []
        self.offset_us = 0
        self._fresh = True
        engine.observe()
        engine.stream_started = True

    @property
    def frame(self):
        return self.engine.frame

    @property
    def time_us(self):
        return self.engine.world["sim_time_us"]

    @property
    def paused(self):
        return self.engine.world["paused"]

    @property
    def last_observed_frame(self):
        return self.engine.observed_frame

    @property
    def last_observed_time_us(self):
        return self.engine.observed["sim_time_us"]

    @property
    def last_observed_snapshot(self):
        return copy.deepcopy(self.engine.observed)

    @property
    def observations_fresh(self):
        return self._fresh

    def snapshot(self):
        if not self._fresh:
            raise ProtocolError("fixture snapshot requires a fresh checkpoint")
        return self.engine.snapshot()

    def check_stop(self):
        if self.engine.closed or self.stop_requested and self.stop_requested():
            raise ProtocolError("stream fixture stopped")

    def boundary(self):
        return {"frame": self.frame, "sim_time_us": self.time_us,
                "paused": self.paused, "state_digest": self.engine.state_digest}

    def checkpoint(self):
        self.check_stop()
        if self.fault == "divergent_checkpoint" and self.frame == BUILD_FRAMES + 50:
            self.engine.world["company"]["balance"] += 1
        self.engine.observe()
        self._fresh = True
        self.checkpoint_frames.append(self.frame)
        if self.frame == FINAL_FRAME and self.release_final is not None:
            self.final_waiting.set()
            if not self.release_final.wait(10):
                raise ProtocolError("test did not release final stream checkpoint receipt")
        return self.boundary()

    def advance(self, count):
        self.check_stop()
        if count != 2 or self.paused:
            raise ProtocolError("unexpected fixture stream permit")
        self.advances.append((self.frame, count))
        steps = []
        for _ in range(count):
            before = self.time_us
            self.engine.frame += 1
            self.engine.world["sim_time_us"] += STEP_US
            vehicle = self.engine.world["probe"]["vehicle"]
            vehicle.update(in_depot=False, state=1,
                           position_mm=[(self.time_us - self.engine.initial_time) // 1000, 0, 0])
            self.offset_us += STEP_US
            steps.append({"frame": self.frame, "sim_time_us": self.time_us,
                "scheduled_offset_us": self.offset_us, "call_started_offset_us": self.offset_us,
                "ack_observed_offset_us": self.offset_us + 1000,
                "permit_duration_us": 1000, "lateness_us": 0,
                "native_time_before_ms": before // 1000,
                "native_time_after_ms": self.time_us // 1000})
        self._fresh = False
        if self.fault == "missing_native_step":
            steps.pop()
        elif self.fault == "stale_native_step":
            steps[0]["native_time_after_ms"] -= 200
        return {"frame": self.frame, "sim_time_us": self.time_us, "metrics": {
            "kind": "stream_advance", "steps_requested": count, "step_us": STEP_US,
            "simulated_us": count * STEP_US, "duration_ms": 401,
            "steps": steps, "world_observation": "none",
            "clock_origin": "stream_local_monotonic", "native_clock_each_step": True}}

    def apply(self, command, key):
        self.check_stop()
        if not self._fresh:
            raise ProtocolError("fixture command attempted at an unobserved boundary")
        return self.engine.apply(command, key)

    def hold(self, delay_ms):
        self.check_stop()
        if not self.paused or not self._fresh or delay_ms != 2000:
            raise ProtocolError("unexpected fixture pause hold")
        self.holds.append((self.frame, self.time_us, delay_ms))
        self.offset_us += delay_ms * 1000
        self.engine.observe()
        return {**self.boundary(), "metrics": {
            "kind": "stream_hold", "requested_delay_ms": delay_ms,
            "actual_delay_ms": delay_ms, "duration_ms": delay_ms + 1,
            "boundary_unchanged": True, "maintenance_observed": True,
            "native_before": None, "native_after": None,
            "counter_deltas": {"hold_calls": 200, "outer_calls": 200, "updated_ms": delay_ms}}}


class StreamDriverTests(unittest.IsolatedAsyncioTestCase):
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
                    (sessions[peer] / name).write_text("explicit stream fixture preparation")
            base_args = dict(epoch="stream-driver-model", timeout=15, rounds=240,
                             timing_probe=False, stream_probe=True, profile="build_v2", delay_ms=0)
            host_args = argparse.Namespace(**base_args, bind="127.0.0.1", port=0,
                ready=runs["a"] / "host-ready.json", report=runs["a"] / "host-report.json")
            secret = b"stream-driver-fixture-key-32-byte"
            progress, engines, wrappers = [], {}, {}
            stop_host = threading.Event()
            final_waiting, release_final = threading.Event(), threading.Event()
            tasks = []
            host = asyncio.create_task(driver.host(host_args, secret, expected_manifest="a" * 64,
                capabilities=driver.measurement_capabilities(host_args),
                backend="explicit_model_only", startup_timeout=10,
                progress=lambda state, **fields: progress.append({"state": state, **fields}),
                stop_requested=stop_host.is_set, step_us=STEP_US,
                coordinator_factory=stream_probe.StreamCoordinator))

            def make_engine(directory, *_args, **_kwargs):
                peer = Path(directory).parent.name
                value = CachedBuildEngineFixture(peer)
                engines[peer] = value
                return value

            def make_stream(engine, stop_requested=None):
                peer = engine.peer
                value = StreamEngineFixture(engine, stop_requested,
                    fault=fault if peer == "b" else "", final_waiting=final_waiting,
                    release_final=release_final if peer == "b" and hold_final else None)
                wrappers[peer] = value
                return value

            def lease_start(_exe, directory, **_kwargs):
                (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=1))
                (directory / "lua_status.json").write_text(json.dumps({"protocol": 1, "epoch": "7",
                    "request": 0, "revision": 1, "status": "ready", "complete": True, "snapshot": {}}))
                return Mock()

            async def wait_until(predicate, message):
                deadline = asyncio.get_running_loop().time() + 60
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
                     patch.object(stream_backend, "StreamEngine", side_effect=make_stream), \
                     patch.object(driver.os, "fsync"):
                    for peer in ("a", "b"):
                        args = argparse.Namespace(**base_args, peer=peer, inputs=None,
                            host="127.0.0.1", port=port, startup_timeout=10,
                            report=runs[peer] / "peer-report.json",
                            progress=runs[peer] / "peer-progress.json", stop_file=runs[peer] / "stop")
                        setup = {"game_exe": str(root / "fixture-game.exe"), "native_epoch": 7,
                                 "manifest_digest": "a" * 64, "measurement_profile": "build_v2"}
                        tasks.append(asyncio.create_task(driver.game_peer(args, secret, sessions[peer], setup)))
                    if hold_final:
                        def a_final_checkpoint_recorded():
                            path = runs["a"] / "peer-journal.jsonl"
                            if not path.is_file():
                                return False
                            records = path.read_text(encoding="utf-8").splitlines()
                            for raw in reversed(records[-3:]):
                                try:
                                    record = json.loads(raw)
                                except ValueError:
                                    continue
                                if record.get("frame") == FINAL_FRAME and record.get("snapshot") is not None:
                                    return True
                            return False
                        await wait_until(lambda: final_waiting.is_set() and a_final_checkpoint_recorded(),
                                         "final peer stream checkpoint remains withheld")
                        self.assertFalse(host.done())
                        self.assertFalse(any(item["state"] == "completed" for item in progress))
                        self.assertFalse(host_args.report.exists())
                        self.assertFalse(any((run / "peer-report.json").exists() for run in runs.values()))
                        release_final.set()
                    codes = await asyncio.wait_for(asyncio.gather(*tasks), 90)
                    host_code = await asyncio.wait_for(host, 10)
            finally:
                release_final.set()
                stop_host.set()
                for run in runs.values():
                    (run / "stop").write_text("fixture cleanup")
                outstanding = [task for task in [*tasks, host] if not task.done()]
                if outstanding:
                    _, pending = await asyncio.wait(outstanding, timeout=10)
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
            return codes, host_code, host_report, reports, journals, exports, engines, wrappers

    async def test_full_stream_waits_for_both_final_checkpoints_and_exports_current_snapshots_only(self):
        codes, host_code, host, reports, journals, exports, engines, wrappers = await self.run_fixture(hold_final=True)
        self.assertEqual(codes, [0, 0], [report["reason"] for report in reports.values()])
        self.assertEqual(host_code, 0, host["reason"])
        self.assertTrue(host["coordinated_completed"])
        self.assertEqual(host["frame"], FINAL_FRAME)
        self.assertEqual(host["state_digest_scope"], "last_matching_world_boundary")
        self.assertEqual(host["state_digest_frame"], FINAL_FRAME)
        self.assertEqual(host["state_digest_sim_time_us"], host["sim_time_us"])
        self.assertEqual(host["round"], BUILD_FRAMES)
        self.assertTrue(host["stream"]["completed"])
        self.assertEqual(host["stream"]["completion_scope"], "both_peer_checkpoint_boundaries")
        self.assertEqual(host["stream"]["advanced_steps"], 600)
        self.assertEqual(host["stream"]["checkpoints_completed"], 12)
        self.assertTrue(host["stream"]["pause_proof"]["completed"])
        self.assertTrue(host["stream"]["paced_stream_1x_met"])
        self.assertFalse(host["stream"]["visual_smoothness_verified"])
        self.assertFalse(host["stream"]["full_world_verified"])
        self.assertEqual([action["kind"] for action in host["actions"][-2:]], ["complete", "complete"])
        self.assertEqual(reports["a"]["snapshot"], reports["b"]["snapshot"])
        self.assertEqual(json.loads(exports["a"]["host-report.json"]), host)
        # Real combined stream reports exceed the old generic JSON read cap.
        # Poll the actual produced bytes: the host must retain both peers' pace
        # result instead of silently falling back to its local peer report.
        host_bytes = exports["a"]["host-report.json"]
        self.assertGreater(len(host_bytes), 1024 * 1024)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "host-report.json").write_bytes(host_bytes)
            (folder / "peer-report.json").write_bytes(exports["a"]["peer-report.json"])
            prepared = workflow.PreparedRun(str(folder), str(folder / "game"),
                str(folder / "session"), str(folder / "payload"), str(folder / "save/imported.sav"),
                str(folder / "backup"), "a", "127.0.0.1", "report-size-fixture", "a" * 64)
            self.assertIsNone(workflow.read_json(folder / "host-report.json"))
            status = workflow.SessionController(prepared).poll()
            self.assertFalse(status["failure"])
            self.assertTrue(status["completed"])
            self.assertTrue(status["coordinated_completed"])
            self.assertEqual(status["stream_result"], host["stream"])
            self.assertIn("Beide PCs", workflow.describe_status(status))
        for peer in ("a", "b"):
            engine, wrapper = engines[peer], wrappers[peer]
            report, journal = reports[peer], journals[peer]
            self.assertTrue(engine.closed)
            self.assertEqual(engine.frame, FINAL_FRAME)
            self.assertEqual(len(wrapper.advances), STREAM_STEPS // 2)
            self.assertTrue(all(count == 2 for _, count in wrapper.advances))
            self.assertEqual(wrapper.checkpoint_frames,
                             list(range(BUILD_FRAMES, FINAL_FRAME + 1, 50)))
            self.assertEqual(wrapper.holds,
                             [(540, engine.initial_time + 42200000 + 60000000, 2000)])
            self.assertEqual(engine.command_calls[-2:], [
                (540, "a:8", {"op": "SET_PAUSED", "value": True}),
                (540, "b:6", {"op": "SET_PAUSED", "value": False})])
            self.assertTrue(report["finished"])
            self.assertTrue(report["stream"]["completed"])
            self.assertEqual(report["stream"]["completion_scope"], "local_checkpoint_boundaries")
            self.assertEqual(report["stream"]["peer_timing_summaries"][peer]["steps_measured"], 600)
            self.assertTrue(report["build_proof"]["passed"])
            self.assertEqual(report["build_proof"]["elapsed_sim_time_us"], 42200000)
            self.assertEqual(report["snapshot"]["sim_time_us"] - engine.initial_time,
                             42200000 + 120000000)
            self.assertEqual(len([row for row in journal if row["event"] == "stepped"]), 240)
            self.assertEqual(len([row for row in journal if row["event"] == "applied"]), 12)
            stream_rows = [row for row in journal if row["event"].startswith("stream_")]
            self.assertTrue(stream_rows)
            self.assertTrue(all(row["event"] in driver.STREAM_WORLD_RECEIPTS for row in stream_rows))
            self.assertEqual(len(report["stream"]["chunk_records"]), 300)
            for chunk in report["stream"]["chunk_records"]:
                self.assertEqual(set(chunk["frontier"]), {"frame", "sim_time_us"})
                self.assertEqual(chunk["metrics"]["world_observation"], "none")
                self.assertNotIn("snapshot", chunk)
                self.assertNotIn("state_digest", chunk)
            # The base adapter intentionally keeps its previous checkpoint
            # cached during native advances. No row may call that old cache a
            # verified observation of the newer simulation frame.
            for row in journal:
                if row["frame"] is not None and row["frame"] >= 240 and row["snapshot"] is not None:
                    self.assertEqual(row["snapshot"]["sim_time_us"],
                                     engine.initial_time + 42200000 + (row["frame"] - 240) * STEP_US)
            self.assertEqual((journal[-1]["event"], journal[-1]["frame"]), ("completed", FINAL_FRAME))
            self.assertEqual(json.loads(exports[peer]["peer-report.json"]), report)
            self.assertEqual([json.loads(line) for line in exports[peer]["peer-journal.jsonl"].splitlines()], journal)

    async def test_divergent_checkpoint_stops_before_another_chunk_is_granted(self):
        codes, host_code, host, reports, journals, _, engines, wrappers = await self.run_fixture(
            fault="divergent_checkpoint")
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertEqual(host["state_digest_scope"], "last_matching_world_boundary")
        self.assertEqual(host["state_digest_frame"], 240)
        self.assertLessEqual(host["state_digest_frame"], host["frame"])
        self.assertFalse(host["coordinated_completed"])
        self.assertIn("checkpoint worlds differ", host["reason"])
        self.assertFalse(host["stream"]["completed"])
        self.assertFalse(any(action["kind"] == "complete" for action in host["actions"]))
        self.assertTrue(all(engine.closed and engine.frame == 290 for engine in engines.values()))
        self.assertTrue(all(len(wrapper.advances) == 25 for wrapper in wrappers.values()))
        self.assertTrue(all(wrapper.checkpoint_frames == [240, 290] for wrapper in wrappers.values()))
        self.assertTrue(all(not report["finished"] for report in reports.values()))
        self.assertTrue(all(journal[-1]["event"] == "failed" for journal in journals.values()))

    async def test_missing_native_step_measurement_is_terminal_without_next_chunk(self):
        await self.assert_native_failure("missing_native_step")

    async def test_stale_native_clock_is_terminal_without_next_chunk(self):
        await self.assert_native_failure("stale_native_step")

    async def assert_native_failure(self, fault):
        codes, host_code, host, reports, journals, _, engines, wrappers = await self.run_fixture(fault=fault)
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertEqual(host["state_digest_scope"], "last_matching_world_boundary")
        self.assertEqual(host["state_digest_frame"], 240)
        self.assertLessEqual(host["state_digest_frame"], host["frame"])
        self.assertFalse(host["coordinated_completed"])
        self.assertFalse(any(action["kind"] == "complete" for action in host["actions"]))
        self.assertTrue(all(engine.closed and engine.frame == 242 for engine in engines.values()))
        self.assertTrue(all(len(wrapper.advances) == 1 for wrapper in wrappers.values()))
        self.assertTrue(all(wrapper.checkpoint_frames == [240] for wrapper in wrappers.values()))
        for peer in ("a", "b"):
            report, journal, engine = reports[peer], journals[peer], engines[peer]
            self.assertFalse(report["finished"])
            self.assertIsNone(report["snapshot"])
            self.assertEqual(report["last_observed_snapshot"]["sim_time_us"], engine.initial_time + 42200000)
            self.assertEqual(report["last_observed_frame"], 240)
            self.assertEqual(report["last_observed_sim_time_us"], engine.initial_time + 42200000)
            self.assertEqual(journal[-1]["event"], "failed")
            self.assertEqual(journal[-1]["frame"], 240)
            self.assertEqual(journal[-1]["snapshot_scope"], "last_observed")


if __name__ == "__main__":
    unittest.main()
