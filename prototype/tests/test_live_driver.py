"""Live TCP driver tests with real input queues and explicit engine/clock models.

Test code chooses when to write user requests. Production code has no scripted
pause sequence in live mode. No TF2, native timer or desktop interaction occurs.
"""
import argparse
import asyncio
import copy
import json
import io
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from prototype.strict_sync import game_runner as driver
from prototype.strict_sync import runner
from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync import live_probe
from prototype.strict_sync import live_input
from prototype.strict_sync import stream_engine as stream_backend
from prototype.strict_sync.core import ProtocolError
from prototype.tests.test_engine_mailbox import native_bytes
from prototype.tests.test_stream_driver import CachedBuildEngineFixture, StreamEngineFixture


class ModelClock:
    """An explicit coordinator clock fixture; real network deadlines stay real."""
    def __init__(self):
        self.now = 100.0
        self.pause_ms = {"a": 0, "b": 0}
        self.lock = threading.Lock()

    def monotonic(self):
        with self.lock:
            return self.now

    def hold(self, peer, duration_ms):
        with self.lock:
            self.pause_ms[peer] += duration_ms
            self.now = 100.0 + max(self.pause_ms.values()) / 1000


class LiveEngineFixture(StreamEngineFixture):
    def __init__(self, engine, stop_requested=None, *, context, fault=""):
        super().__init__(engine, stop_requested, fault=fault)
        self.context = context

    def checkpoint(self):
        result = super().checkpoint()
        if self.engine.peer == "b" and self.context.get("finish_armed"):
            self.context["final_waiting"].set()
            if not self.context["release_final"].wait(10):
                raise ProtocolError("test did not release final live checkpoint")
        return result

    def hold(self, delay_ms):
        self.check_stop()
        if not self.paused or not self._fresh or delay_ms != 200:
            raise ProtocolError("unexpected explicit model pause poll")
        self.holds.append((self.frame, self.time_us, delay_ms))
        self.context["clock"].hold(self.engine.peer, delay_ms)
        self.offset_us += delay_ms * 1000
        self.engine.observe()
        return {**self.boundary(), "metrics": {
            "kind": "stream_hold", "requested_delay_ms": delay_ms,
            "actual_delay_ms": delay_ms, "duration_ms": delay_ms + 1,
            "boundary_unchanged": True, "maintenance_observed": True,
            "native_before": None, "native_after": None,
            "counter_deltas": {"hold_calls": 20, "outer_calls": 20, "updated_ms": delay_ms}}}


class LiveDriverTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, action_hook, *, fault="", hold_final=False, duplicate=False,
                          completion_timeout=90):
        asyncio.get_running_loop().set_debug(False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            epoch = "live-driver-model"
            runs, sessions, inputs, queues = {}, {}, {}, {}
            for peer in ("a", "b"):
                runs[peer] = root / peer
                sessions[peer] = runs[peer] / "session"
                sessions[peer].mkdir(parents=True)
                for name in driver.PREPARED_FILES:
                    (sessions[peer] / name).write_text("explicit live fixture preparation")
                inputs[peer] = runs[peer] / "live-input.json"
                live_input.create(inputs[peer], epoch, peer)
                queues[peer] = live_input.InputWriter(inputs[peer], epoch, peer)
            base_args = dict(epoch=epoch, timeout=15, rounds=240, live_probe=True,
                             timing_probe=False, stream_probe=False, profile="build_v2", delay_ms=0)
            host_args = argparse.Namespace(**base_args, bind="127.0.0.1", port=0,
                ready=runs["a"] / "host-ready.json", report=runs["a"] / "host-report.json")
            secret = b"live-driver-fixture-key-32-bytes!"
            stop_host = threading.Event()
            context = {"clock": ModelClock(), "queues": queues, "inputs": inputs,
                       "engines": {}, "wrappers": {}, "actions": [], "progress": [],
                       "final_waiting": threading.Event(), "release_final": threading.Event(),
                       "finish_armed": False, "test_state": {}}
            if not hold_final:
                context["release_final"].set()

            class ObservedCoordinator(live_probe.LiveCoordinator):
                # The production decision is unchanged. An external test hook
                # writes actual input files before newly emitted actions travel
                # over TCP, representing arbitrary user actions at that moment.
                def receive(self, peer, message):
                    actions = super().receive(peer, message)
                    context["actions"].extend(copy.deepcopy(actions))
                    action_hook(self, actions, context)
                    return actions

            class ClockedReplica(live_probe.LiveReplica):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    # Explicit per-peer elapsed-time fixture. Network timeouts
                    # and native production timers are never replaced.
                    self._pause_clock = lambda: 100.0 + context["clock"].pause_ms[self.peer] / 1000

            def coordinator_factory(*args, **kwargs):
                kwargs["clock"] = context["clock"].monotonic
                value = ObservedCoordinator(*args, **kwargs)
                context["coordinator"] = value
                return value

            def make_engine(directory, *_args, **_kwargs):
                peer = Path(directory).parent.name
                value = CachedBuildEngineFixture(peer)
                context["engines"][peer] = value
                return value

            def make_stream(engine, stop_requested=None):
                value = LiveEngineFixture(engine, stop_requested, context=context,
                                          fault=fault if engine.peer == "b" else "")
                context["wrappers"][engine.peer] = value
                return value

            def lease_start(_exe, directory, **_kwargs):
                (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=1))
                (directory / "lua_status.json").write_text(json.dumps({"protocol": 1, "epoch": "7",
                    "request": 0, "revision": 1, "status": "ready", "complete": True, "snapshot": {}}))
                return Mock()

            progress_path = runs["a"] / "host-progress.json"
            production_progress = driver.Progress(progress_path)
            def progress(state, **fields):
                context["progress"].append({"state": state, **copy.deepcopy(fields)})
                production_progress(state, **fields)

            host = asyncio.create_task(driver.host(host_args, secret, expected_manifest="a" * 64,
                capabilities=driver.measurement_capabilities(host_args), backend="explicit_model_only",
                startup_timeout=10, progress=progress, stop_requested=stop_host.is_set,
                step_us=200000, coordinator_factory=coordinator_factory))
            tasks = []
            real_send = runner.send
            cached_checkpoint = {}
            duplicate_sent = set()

            async def observed_send(writer, message):
                # Deliver an old checkpoint action only after the next native
                # advance was sent. It must be answered from cache without
                # creating a new observation of the now historical world.
                duplicate_kind = "live_poll" if duplicate == "poll" else "live_checkpoint"
                if duplicate and message.get("kind") == duplicate_kind:
                    cached_checkpoint.setdefault(id(writer), copy.deepcopy(message))
                await real_send(writer, message)
                if (duplicate and message.get("kind") == "live_advance"
                        and id(writer) in cached_checkpoint and id(writer) not in duplicate_sent):
                    await real_send(writer, cached_checkpoint[id(writer)])
                    duplicate_sent.add(id(writer))

            async def wait_until(predicate, reason):
                deadline = asyncio.get_running_loop().time() + 75
                while not predicate():
                    if host.done():
                        await host
                        report = json.loads(host_args.report.read_text()) if host_args.report.exists() else {}
                        self.fail(reason + ": host ended early: " + report.get("reason", ""))
                    if asyncio.get_running_loop().time() >= deadline:
                        self.fail(reason + ": fixture deadline")
                    await asyncio.sleep(.005)

            try:
                await wait_until(host_args.ready.exists, "host readiness")
                port = json.loads(host_args.ready.read_text())["port"]
                with patch.object(driver, "ControllerGuard"), \
                     patch.object(driver, "game_is_running", return_value=False), \
                     patch.object(driver, "verify_payload"), \
                     patch.object(driver.LaunchLease, "create", side_effect=lease_start), \
                     patch.object(driver, "EngineAdapter", side_effect=make_engine), \
                     patch.object(driver, "LiveReplica", ClockedReplica), \
                     patch.object(stream_backend, "StreamEngine", side_effect=make_stream), \
                     patch.object(runner, "send", side_effect=observed_send), \
                     patch.object(driver.os, "fsync"):
                    for peer in ("a", "b"):
                        args = argparse.Namespace(**base_args, peer=peer, inputs=None,
                            live_input_file=inputs[peer], host="127.0.0.1", port=port, startup_timeout=10,
                            report=runs[peer] / "peer-report.json", progress=runs[peer] / "peer-progress.json",
                            stop_file=runs[peer] / "stop")
                        setup = {"game_exe": str(root / "fixture-game.exe"), "native_epoch": 7,
                                 "manifest_digest": "a" * 64, "measurement_profile": "build_v2"}
                        tasks.append(asyncio.create_task(driver.game_peer(args, secret, sessions[peer], setup)))
                    if hold_final:
                        def a_final_recorded():
                            path = runs["a"] / "peer-journal.jsonl"
                            if not path.exists():
                                return False
                            for raw in reversed(path.read_text(encoding="utf-8").splitlines()[-3:]):
                                try:
                                    if json.loads(raw).get("event") == "live_finished":
                                        return True
                                except ValueError:
                                    pass
                            return False
                        await wait_until(lambda: context["final_waiting"].is_set() and a_final_recorded(),
                                         "one final live checkpoint is withheld")
                        self.assertFalse(host.done())
                        self.assertFalse(host_args.report.exists())
                        self.assertFalse(any(item["state"] == "completed" for item in context["progress"]))
                        self.assertFalse(any((run / "peer-report.json").exists() for run in runs.values()))
                        context["release_final"].set()
                    codes = await asyncio.wait_for(asyncio.gather(*tasks), completion_timeout)
                    host_code = await asyncio.wait_for(host, 10)
            finally:
                context["release_final"].set()
                stop_host.set()
                for run in runs.values():
                    (run / "stop").write_text("fixture cleanup")
                pending = [task for task in [*tasks, host] if not task.done()]
                if pending:
                    _, still_pending = await asyncio.wait(pending, timeout=10)
                    for task in still_pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

            reports, journals, exported = {}, {}, {}
            host_report = json.loads(host_args.report.read_text())
            for peer in ("a", "b"):
                reports[peer] = json.loads((runs[peer] / "peer-report.json").read_text())
                journals[peer] = [json.loads(row) for row in
                    (runs[peer] / "peer-journal.jsonl").read_text(encoding="utf-8").splitlines()]
                prepared = workflow.PreparedRun(str(runs[peer]), str(root / "fixture-game"),
                    str(sessions[peer]), str(runs[peer] / "payload"), str(root / "save/imported.sav"),
                    str(root / "backup"), peer, "127.0.0.1", epoch, "a" * 64, test_mode=workflow.LIVE_MODE)
                archive_path = workflow.export_diagnostics(prepared, root / (peer + "-diagnostics.zip"))
                with zipfile.ZipFile(archive_path) as archive:
                    exported[peer] = {name: archive.read(name) for name in archive.namelist()}
                controller = workflow.SessionController(prepared, spawn=Mock())
                status = controller.poll()
                self.assertEqual(status.get("live_result"),
                                 host_report["live"] if peer == "a" else reports[peer]["live"])
            context["duplicate_sent"] = duplicate_sent
            return codes, host_code, host_report, reports, journals, exported, context

    @staticmethod
    def first_action(actions, kind):
        return next((message for _, message in actions if message.get("kind") == kind), None)

    async def test_early_explicit_end_requires_both_fresh_final_receipts_without_claiming_coverage(self):
        def choose_inputs(coordinator, actions, context):
            if self.first_action(actions, "live_poll") and not context["test_state"]:
                context["queues"]["a"].submit({"op": "END_TEST"})
                context["test_state"]["submitted"] = True
            if self.first_action(actions, "live_finish"):
                context["finish_armed"] = True

        codes, host_code, host, reports, journals, exports, context = await self.run_fixture(
            choose_inputs, hold_final=True)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertTrue(host["coordinated_completed"])
        self.assertTrue(host["live"]["completed"])
        self.assertFalse(host["live"]["required_interactions_met"])
        self.assertEqual(host["live"]["completion_scope"], "both_peer_fresh_world_boundaries")
        self.assertEqual(host["frame"], 240)
        for peer in ("a", "b"):
            self.assertTrue(reports[peer]["finished"])
            self.assertTrue(reports[peer]["build_proof"]["passed"])
            self.assertFalse(reports[peer]["live"]["required_interactions_met"])
            self.assertEqual(reports[peer]["live"]["completion_scope"], "local_fresh_world_boundary")
            self.assertEqual(context["wrappers"][peer].advances, [])
            self.assertEqual(journals[peer][-1]["event"], "completed")
            self.assertEqual(json.loads(exports[peer]["peer-report.json"]), reports[peer])

    async def test_arbitrary_queue_inputs_both_origins_long_pause_conflict_and_joint_finish(self):
        def choose_inputs(coordinator, actions, context):
            poll = self.first_action(actions, "live_poll")
            if not poll:
                return
            state = context["test_state"]
            phase = state.get("phase", "begin")
            queue = context["queues"]
            if phase == "begin" and poll["frame"] >= 244:
                queue["a"].submit({"op": "SET_PAUSED", "value": True})
                state.update(phase="long_pause", pause_frame=poll["frame"])
            elif phase == "long_pause" and context["clock"].pause_ms["a"] >= 200000:
                self.assertTrue(coordinator.paused)
                self.assertEqual(poll["frame"], state["pause_frame"])
                queue["b"].submit({"op": "SET_PAUSED", "value": False})
                state["phase"] = "client_pause"
            elif phase == "client_pause" and poll["frame"] > state["pause_frame"]:
                queue["b"].submit({"op": "SET_PAUSED", "value": True})
                state["phase"] = "host_resume"
            elif phase == "host_resume" and coordinator.paused:
                queue["a"].submit({"op": "SET_PAUSED", "value": False})
                state["phase"] = "conflict"
            elif phase == "conflict" and not coordinator.paused:
                queue["a"].submit({"op": "SET_PAUSED", "value": False})
                queue["b"].submit({"op": "SET_PAUSED", "value": True})
                state.update(phase="after_conflict", conflict_frame=poll["frame"])
            elif phase == "after_conflict":
                self.assertTrue(coordinator.paused, "the collected pause must win over resume")
                self.assertEqual(poll["frame"], state["conflict_frame"])
                queue["a"].submit({"op": "SET_PAUSED", "value": False})
                state["phase"] = "end"
            elif phase == "end" and not coordinator.paused and poll["frame"] >= 2100:
                queue["b"].submit({"op": "END_TEST"})
                state["phase"] = "sent_end"

        # This size-boundary scenario deliberately generates a >4 MiB report:
        # 1,000 paused heartbeats plus over 1,800 advancing steps. Its fixture
        # budget includes file IPC and serialization, independently of native
        # pacing. Every production phase deadline and assertion stays intact.
        codes, host_code, host, reports, journals, exports, context = await self.run_fixture(
            choose_inputs, completion_timeout=300)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        result = host["live"]
        self.assertTrue(result["completed"])
        self.assertTrue(result["required_interactions_met"])
        self.assertEqual(result["coverage"]["per_peer_pause_resume"], {"a": True, "b": True})
        self.assertEqual(result["coverage"]["conflict_batches"], 1)
        self.assertGreaterEqual(min(result["coverage"]["longest_measured_pause_ms"].values()), 200000)
        self.assertGreater(context["clock"].monotonic() - 100, 15)
        self.assertFalse(result["native_ui_input_capture"])
        self.assertFalse(result["full_world_verified"])
        self.assertEqual(journals["a"], journals["b"])
        for peer in ("a", "b"):
            engine, wrapper = context["engines"][peer], context["wrappers"][peer]
            report, journal = reports[peer], journals[peer]
            self.assertTrue(engine.closed)
            self.assertTrue(report["finished"])
            self.assertTrue(report["live"]["required_interactions_met"])
            self.assertEqual(report["live"]["outcomes"], result["outcomes"])
            self.assertEqual(len([row for row in journal if row["event"] == "stepped"]), 240)
            live_rows = [row for row in journal if row["event"].startswith("live_")]
            self.assertTrue(all(row["event"] in driver.LIVE_WORLD_RECEIPTS for row in live_rows))
            for row in journal:
                if row["frame"] is not None and row["frame"] >= 240 and row["snapshot"] is not None:
                    self.assertEqual(row["snapshot"]["sim_time_us"],
                                     engine.initial_time + 42200000 + (row["frame"] - 240) * 200000)
            self.assertEqual(report["last_acknowledged_native_frame"], engine.frame)
            self.assertEqual(report["last_observed_frame"], engine.frame)
            self.assertEqual(json.loads(exports[peer]["peer-report.json"]), report)
            self.assertTrue(all(count == 2 for _, count in wrapper.advances))
            self.assertTrue(all(delay == 200 for _, _, delay in wrapper.holds))
        # This is the actual production host report, including both metric
        # streams, read by SessionController.poll inside run_fixture.
        self.assertGreater(len(exports["a"]["host-report.json"]), 4 * 1024 * 1024)
        self.assertLess(len(exports["a"]["host-report.json"]), 16 * 1024 * 1024)

    async def test_delayed_duplicate_checkpoint_reuses_receipt_without_journaling_stale_world(self):
        def choose_inputs(coordinator, actions, context):
            poll = self.first_action(actions, "live_poll")
            if poll and poll["frame"] >= 300 and not context["test_state"]:
                context["queues"]["a"].submit({"op": "END_TEST"})
                context["test_state"]["end"] = True

        codes, host_code, host, reports, journals, _, context = await self.run_fixture(choose_inputs, duplicate=True)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertEqual(len(context["duplicate_sent"]), 2)
        self.assertEqual(journals["a"], journals["b"])
        for peer in ("a", "b"):
            wrapper = context["wrappers"][peer]
            self.assertEqual(len(wrapper.advances), 30)
            self.assertEqual(wrapper.checkpoint_frames, [240, 290, 300, 300])
            self.assertEqual([row["frame"] for row in journals[peer] if row["event"] == "live_checkpointed"], [290, 300])
            self.assertEqual(reports[peer]["live"]["coverage"]["total_requests"], 1)

    async def test_native_clock_and_missing_measurement_are_terminal_at_historical_world(self):
        for fault in ("stale_native_step", "missing_native_step"):
            with self.subTest(fault=fault):
                codes, host_code, host, reports, journals, _, context = await self.run_fixture(
                    lambda *_: None, fault=fault)
                self.assertEqual((codes, host_code), ([2, 2], 2))
                self.assertFalse(host["coordinated_completed"])
                self.assertEqual(host["state_digest_frame"], 240)
                self.assertFalse(any(action["kind"] == "complete" for action in host["actions"]))
                for peer in ("a", "b"):
                    self.assertEqual(len(context["wrappers"][peer].advances), 1)
                    self.assertEqual(context["engines"][peer].frame, 242)
                    self.assertEqual(reports[peer]["last_observed_frame"], 240)
                    self.assertEqual(reports[peer]["last_acknowledged_native_frame"], 242)
                    self.assertEqual(journals[peer][-1]["frame"], 240)
                    self.assertEqual(journals[peer][-1]["snapshot_scope"], "last_observed")

    async def test_delayed_duplicate_input_poll_does_not_consume_or_apply_new_request_twice(self):
        def choose_inputs(coordinator, actions, context):
            poll = self.first_action(actions, "live_poll")
            if not poll:
                return
            stage = context["test_state"].get("stage", 0)
            if stage == 0 and poll["frame"] >= 242:
                context["queues"]["a"].submit({"op": "SET_PAUSED", "value": True})
                context["test_state"]["stage"] = 1
            elif stage == 1 and coordinator.paused:
                context["queues"]["b"].submit({"op": "SET_PAUSED", "value": False})
                context["test_state"]["stage"] = 2
            elif stage == 2 and not coordinator.paused:
                context["queues"]["a"].submit({"op": "END_TEST"})
                context["test_state"]["stage"] = 3

        codes, host_code, host, reports, journals, _, context = await self.run_fixture(choose_inputs, duplicate="poll")
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertEqual(len(context["duplicate_sent"]), 2)
        self.assertEqual(host["live"]["coverage"]["total_requests"], 3)
        self.assertEqual(len(host["live"]["outcomes"]), 3)
        self.assertEqual(journals["a"], journals["b"])
        for engine in context["engines"].values():
            self.assertEqual([key for _, key, _ in engine.command_calls[-2:]], ["a:8", "b:6"])

    async def test_divergent_fresh_world_stops_before_another_native_grant(self):
        codes, host_code, host, reports, journals, _, context = await self.run_fixture(
            lambda *_: None, fault="divergent_checkpoint")
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertIn("fresh peer worlds differ", host["reason"])
        self.assertEqual(host["state_digest_frame"], 240)
        self.assertEqual(host["frame"], 290)
        self.assertFalse(host["coordinated_completed"])
        for peer in ("a", "b"):
            self.assertEqual(len(context["wrappers"][peer].advances), 25)
            self.assertEqual(context["engines"][peer].frame, 290)
            self.assertEqual(reports[peer]["last_observed_frame"], 290)
            self.assertEqual(journals[peer][-1]["frame"], 290)

    async def test_removed_or_corrupted_queue_stops_at_next_collection_without_another_grant(self):
        for fault in ("removed", "corrupted"):
            with self.subTest(fault=fault):
                def choose_inputs(coordinator, actions, context):
                    poll = self.first_action(actions, "live_poll")
                    if poll and poll["frame"] == 242:
                        path = context["inputs"]["b"]
                        if fault == "removed":
                            path.unlink()
                        else:
                            path.write_text('{"requests": []}')
                codes, host_code, host, reports, journals, _, context = await self.run_fixture(choose_inputs)
                self.assertEqual((codes, host_code), ([2, 2], 2))
                self.assertFalse(host["coordinated_completed"])
                self.assertIn("live input" if fault == "corrupted" else "mailbox file not found", host["reason"])
                self.assertTrue(all(len(wrapper.advances) == 1 for wrapper in context["wrappers"].values()))
                self.assertTrue(all(report["last_observed_frame"] == 240 for report in reports.values()))


class LiveInputStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_malformed_stale_or_inside_session_queue_never_reaches_a_game_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case in ("missing", "malformed", "stale_epoch", "inside"):
                with self.subTest(case=case):
                    run = root / case
                    session = run / "session"
                    session.mkdir(parents=True)
                    for name in driver.PREPARED_FILES:
                        (session / name).write_text("explicit fixture preparation")
                    queue = session / "input.json" if case == "inside" else run / "input.json"
                    if case == "malformed":
                        queue.write_text("{")
                    elif case != "missing":
                        live_input.create(queue, "stale-epoch" if case == "stale_epoch" else "live-test", "a")
                    args = argparse.Namespace(profile="build_v2", rounds=240, timeout=15, live_probe=True,
                        timing_probe=False, stream_probe=False, delay_ms=0, live_input_file=queue,
                        peer="a", epoch="live-test", report=run / "peer-report.json")
                    with patch.object(driver, "ControllerGuard") as guard, \
                         patch.object(driver.LaunchLease, "create") as lease, \
                         patch.object(driver, "EngineAdapter") as engine:
                        code = await driver.game_peer(args, b"unused", session, {"measurement_profile": "build_v2"})
                    self.assertEqual(code, 2)
                    guard.assert_not_called()
                    lease.assert_not_called()
                    engine.assert_not_called()
                    self.assertFalse((session / "controller_started.json").exists())
                    self.assertFalse(json.loads(args.report.read_text())["finished"])


class LiveEntryTests(unittest.TestCase):
    def test_profile_requires_full_build_zero_delay_adequate_timeout_and_exclusive_mode(self):
        valid = dict(profile="build_v2", rounds=240, timeout=15, delay_ms=0,
                     live_probe=True, stream_probe=False, timing_probe=False)
        self.assertEqual(driver.selected_profile(argparse.Namespace(**valid),
                                                {"measurement_profile": "build_v2"}), "build_v2")
        for changed in ({"profile": "time_v1"}, {"rounds": 239}, {"delay_ms": 1},
                        {"timeout": 14.9}, {"stream_probe": True}, {"timing_probe": True}):
            with self.subTest(changed=changed):
                values = {**valid, **changed}
                with self.assertRaises(ValueError):
                    driver.selected_profile(argparse.Namespace(**values),
                                            {"measurement_profile": values["profile"]})

    def test_live_capability_only_opt_in_and_host_uses_live_coordinator(self):
        self.assertNotIn(live_probe.LIVE_CAPABILITY, driver.measurement_capabilities(argparse.Namespace()))
        self.assertIn(live_probe.LIVE_CAPABILITY,
                      driver.measurement_capabilities(argparse.Namespace(live_probe=True)))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            key = folder / "key"
            key.write_bytes(b"x" * 32)
            seen = {}
            async def capture_host(args, secret, **kwargs):
                seen.update(kwargs)
                return 0
            with patch.object(driver, "read_setup", return_value=(folder / "session", {
                    "measurement_profile": "build_v2", "manifest_digest": "a" * 64})), \
                 patch.object(driver, "host", side_effect=capture_host):
                code = driver.main(["host", "--session", str(folder / "session"), "--epoch", "fixture",
                    "--key-file", str(key), "--report", str(folder / "report"),
                    "--ready", str(folder / "ready"), "--profile", "build_v2", "--rounds", "240",
                    "--live-probe", "--delay-ms", "0"])
            self.assertEqual(code, 0)
            self.assertIs(seen["coordinator_factory"], live_probe.LiveCoordinator)
            self.assertIn(live_probe.LIVE_CAPABILITY, seen["capabilities"])
            self.assertNotIn(driver.STREAM_CAPABILITY, seen["capabilities"])
            self.assertNotIn(driver.TIMING_CAPABILITY, seen["capabilities"])

    def test_input_queue_argument_is_required_for_live_peer_and_rejected_elsewhere_before_setup(self):
        common = ["--session", "unused", "--epoch", "fixture", "--key-file", "unused",
                  "--report", "unused", "--profile", "build_v2", "--rounds", "240"]
        cases = [
            ["peer", "--peer", "a", "--live-probe"],
            ["host", "--ready", "unused", "--live-probe", "--live-input-file", "unused"],
            ["peer", "--peer", "a", "--inputs", "unused", "--live-input-file", "unused"],
        ]
        for argv in cases:
            with self.subTest(argv=argv), patch.object(driver, "read_setup") as setup, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    driver.main(argv + common)
                self.assertEqual(failure.exception.code, 2)
                setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
