"""Actual TCP/queue/driver flow with explicit engine models, never a TF2 run."""
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

from prototype.strict_sync import game_runner as driver, live_input, paced_live_probe, runner
from prototype.strict_sync import stream_engine as stream_backend
from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.short_build_profile import SHORT_BUILD_CONTRACT
from prototype.strict_sync.coalesced_progress import CoalescedProgress
from prototype.tests.test_engine_mailbox import native_bytes
from prototype.tests.test_live_driver import LiveEngineFixture, ModelClock
from prototype.tests.test_stream_driver import CachedBuildEngineFixture


class PacedLiveDriverTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, choose_inputs, *, fault="", duplicate_checkpoint=False, hold_final=False):
        asyncio.get_running_loop().set_debug(False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            epoch = "paced-live-driver-model"
            runs, sessions, inputs, queues = {}, {}, {}, {}
            for peer in ("a", "b"):
                runs[peer] = root / peer
                sessions[peer] = runs[peer] / "session"
                sessions[peer].mkdir(parents=True)
                for name in driver.PREPARED_FILES:
                    (sessions[peer] / name).write_text("explicit short preparation fixture")
                inputs[peer] = runs[peer] / "live-input.json"
                live_input.create(inputs[peer], epoch, peer)
                queues[peer] = live_input.InputWriter(inputs[peer], epoch, peer)
            fields = dict(epoch=epoch, timeout=15, rounds=10, profile="build_v2", delay_ms=0,
                          paced_live_probe=True, live_probe=False, timing_probe=False, stream_probe=False)
            host_args = argparse.Namespace(**fields, bind="127.0.0.1", port=0,
                ready=runs["a"] / "host-ready.json", report=runs["a"] / "host-report.json")
            secret = b"paced-live-fixture-secret-32-bytes"
            stop = threading.Event()
            context = {"clock": ModelClock(), "queues": queues, "inputs": inputs,
                       "engines": {}, "wrappers": {}, "state": {}, "actions": [],
                       "final_waiting": threading.Event(), "release_final": threading.Event(),
                       "finish_armed": False}
            if not hold_final:
                context["release_final"].set()

            class ObservedCoordinator(paced_live_probe.PacedLiveCoordinator):
                def receive(self, peer, message):
                    actions = super().receive(peer, message)
                    context["actions"].extend(copy.deepcopy(actions))
                    choose_inputs(self, actions, context)
                    if any(message["kind"] == "live_finish" for _, message in actions):
                        context["finish_armed"] = True
                    return actions

            class ClockedReplica(paced_live_probe.PacedLiveReplica):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._pause_clock = lambda: 100.0 + context["clock"].pause_ms[self.peer] / 1000

            class Wrapper(LiveEngineFixture):
                def checkpoint(self):
                    if fault == "divergent_checkpoint" and self.engine.peer == "b" and self.frame == 60:
                        self.engine.world["company"]["balance"] += 1
                    return super().checkpoint()

            def coordinator_factory(*args, **kwargs):
                kwargs["clock"] = context["clock"].monotonic
                return ObservedCoordinator(*args, **kwargs)

            def make_engine(directory, *_args, **_kwargs):
                peer = Path(directory).parent.name
                value = CachedBuildEngineFixture(peer)
                value.missing_debit = fault == "missing_debit"
                context["engines"][peer] = value
                return value

            def make_stream(engine, stop_requested=None):
                value = Wrapper(engine, stop_requested, context=context,
                                fault=fault if engine.peer == "b" else "")
                context["wrappers"][engine.peer] = value
                return value

            def lease_start(_exe, directory, **_kwargs):
                (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=1))
                (directory / "lua_status.json").write_text(json.dumps({"protocol": 1, "epoch": "7",
                    "request": 0, "revision": 1, "status": "ready", "complete": True, "snapshot": {}}))
                return Mock()

            cached, duplicated = {}, set()
            real_send = runner.send
            async def observed_send(writer, message):
                if duplicate_checkpoint and message.get("kind") == "live_checkpoint":
                    cached.setdefault(id(writer), copy.deepcopy(message))
                await real_send(writer, message)
                if (duplicate_checkpoint and message.get("kind") == "live_advance"
                        and id(writer) in cached and id(writer) not in duplicated):
                    await real_send(writer, cached[id(writer)])
                    duplicated.add(id(writer))

            async def wait_for(predicate):
                deadline = asyncio.get_running_loop().time() + 30
                while not predicate():
                    if host.done():
                        result = json.loads(host_args.report.read_text())
                        self.fail("host ended before fixture condition: " + result.get("reason", ""))
                    if asyncio.get_running_loop().time() >= deadline:
                        self.fail("fixture condition timed out")
                    await asyncio.sleep(.005)

            host = asyncio.create_task(driver.host(host_args, secret, expected_manifest="a" * 64,
                capabilities=driver.measurement_capabilities(host_args), backend="explicit_model_only",
                startup_timeout=10, stop_requested=stop.is_set, step_us=200000,
                coordinator_factory=coordinator_factory))
            tasks = []
            try:
                await wait_for(host_args.ready.exists)
                port = json.loads(host_args.ready.read_text())["port"]
                with patch.object(driver, "ControllerGuard"), patch.object(driver, "game_is_running", return_value=False), \
                     patch.object(driver, "verify_payload"), patch.object(driver.LaunchLease, "create", side_effect=lease_start), \
                     patch.object(driver, "EngineAdapter", side_effect=make_engine), \
                     patch.object(driver, "PacedLiveReplica", ClockedReplica), \
                     patch.object(stream_backend, "StreamEngine", side_effect=make_stream), \
                     patch.object(runner, "send", side_effect=observed_send), patch.object(driver.os, "fsync"):
                    for peer in ("a", "b"):
                        args = argparse.Namespace(**fields, peer=peer, inputs=None, live_input_file=inputs[peer],
                            host="127.0.0.1", port=port, startup_timeout=10, report=runs[peer] / "peer-report.json",
                            progress=runs[peer] / "peer-progress.json", stop_file=runs[peer] / "stop")
                        setup = {"game_exe": str(root / "fixture-game.exe"), "native_epoch": 7,
                                 "manifest_digest": "a" * 64, "measurement_profile": "build_v2",
                                 "measurement_preparation": SHORT_BUILD_CONTRACT}
                        tasks.append(asyncio.create_task(driver.game_peer(args, secret, sessions[peer], setup)))
                    if hold_final:
                        await wait_for(context["final_waiting"].is_set)
                        self.assertFalse(host.done())
                        self.assertFalse(host_args.report.exists())
                        self.assertFalse(any((run / "peer-report.json").exists() for run in runs.values()))
                        context["release_final"].set()
                    codes = await asyncio.wait_for(asyncio.gather(*tasks), 45)
                    host_code = await asyncio.wait_for(host, 10)
            finally:
                context["release_final"].set()
                stop.set()
                for run in runs.values():
                    (run / "stop").write_text("fixture cleanup")
                pending = [task for task in [*tasks, host] if not task.done()]
                if pending:
                    _, unfinished = await asyncio.wait(pending, timeout=10)
                    for task in unfinished:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
            reports = {peer: json.loads((runs[peer] / "peer-report.json").read_text()) for peer in runs}
            journals = {peer: [json.loads(row) for row in (runs[peer] / "peer-journal.jsonl")
                              .read_text(encoding="utf-8").splitlines()] for peer in runs}
            context["duplicates"] = duplicated
            return codes, host_code, json.loads(host_args.report.read_text()), reports, journals, context

    @staticmethod
    def action(actions, kind):
        return next((item for _, item in actions if item["kind"] == kind), None)

    async def test_short_ready_is_separate_from_full_build_and_end_still_waits_for_both_worlds(self):
        def choose(_coordinator, actions, context):
            if self.action(actions, "live_start"):
                context["queues"]["a"].submit({"op": "END_TEST"})
        codes, host_code, host, reports, journals, context = await self.run_fixture(choose, hold_final=True)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertTrue(host["coordinated_completed"])
        self.assertEqual(host["frame"], 10)
        self.assertFalse(host["live"]["required_interactions_met"])
        self.assertEqual(journals["a"], journals["b"])
        for peer in reports:
            self.assertIsNone(reports[peer]["build_proof"])
            self.assertTrue(reports[peer]["short_preparation"]["passed"])
            self.assertFalse(reports[peer]["short_preparation"]["full_build_proof"])
            self.assertEqual(len([row for row in journals[peer] if row["event"] == "stepped"]), 10)
            self.assertEqual(len([row for row in journals[peer] if row["event"] == "applied"]), 10)
            self.assertEqual(context["wrappers"][peer].advances, [])
            self.assertGreater(reports[peer]["launcher_status"]["suppressed_calls"], 0)

    async def test_mutual_requests_are_carried_by_native_and_hold_receipts_without_poll_barriers(self):
        def choose(coordinator, actions, context):
            state, queues = context["state"], context["queues"]
            phase = state.get("phase", 0)
            advance, hold = self.action(actions, "live_advance"), self.action(actions, "live_hold")
            if phase == 0 and advance:
                queues["a"].submit({"op": "SET_PAUSED", "value": True})
                state["phase"] = 1
            elif phase == 1 and hold and context["clock"].pause_ms["a"] >= 36000:
                queues["b"].submit({"op": "SET_PAUSED", "value": False})
                state["phase"] = 2
            elif phase == 2 and advance:
                queues["b"].submit({"op": "SET_PAUSED", "value": True})
                state["phase"] = 3
            elif phase == 3 and hold:
                queues["a"].submit({"op": "SET_PAUSED", "value": False})
                state["phase"] = 4
            elif phase == 4 and advance and advance["frame"] >= 70:
                queues["a"].submit({"op": "END_TEST"})
                state["phase"] = 5
        codes, host_code, host, reports, journals, context = await self.run_fixture(choose, duplicate_checkpoint=True)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertTrue(host["live"]["required_interactions_met"])
        self.assertEqual(host["live"]["coverage"]["total_requests"], 5)
        self.assertEqual(host["live"]["separate_input_poll_barriers"], 0)
        self.assertFalse(any(message["kind"] == "live_poll" for _, message in context["actions"]))
        self.assertEqual(len(context["duplicates"]), 2)
        self.assertEqual(journals["a"], journals["b"])
        for peer in reports:
            engine = context["engines"][peer]
            self.assertTrue(engine.closed)
            self.assertEqual([key for _, key, _ in engine.command_calls[10:]], ["a:7", "b:5", "b:6", "a:8"])
            self.assertTrue(reports[peer]["short_preparation"]["passed"])
            self.assertTrue(reports[peer]["live"]["required_interactions_met"])
            self.assertTrue(all(row["event"] != "live_advanced" for row in journals[peer]))

    async def test_short_readiness_failure_never_enables_live_inputs_or_completes(self):
        codes, host_code, host, reports, journals, context = await self.run_fixture(lambda *_: None, fault="missing_debit")
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertFalse(host["coordinated_completed"])
        self.assertFalse(any(message["kind"] == "live_start" for _, message in context["actions"]))
        self.assertEqual(host["frame"], 9)
        self.assertTrue(all(report["short_preparation"] is None for report in reports.values()))
        self.assertTrue(any("actual company debit" in report["reason"] for report in reports.values()))

    async def test_invalid_native_receipt_keeps_completed_preparation_but_no_new_world_claim(self):
        for fault in ("missing_native_step", "stale_native_step"):
            with self.subTest(fault=fault):
                codes, host_code, host, reports, journals, context = await self.run_fixture(lambda *_: None, fault=fault)
                self.assertEqual((codes, host_code), ([2, 2], 2))
                self.assertEqual(host["state_digest_frame"], 10)
                for peer in reports:
                    self.assertTrue(reports[peer]["short_preparation"]["passed"])
                    self.assertEqual(reports[peer]["last_observed_frame"], 10)
                    self.assertEqual(reports[peer]["last_acknowledged_native_frame"], 12)
                    self.assertEqual(journals[peer][-1]["frame"], 10)
                    self.assertEqual(journals[peer][-1]["snapshot_scope"], "last_observed")
                    self.assertEqual(len(context["wrappers"][peer].advances), 1)

    async def test_divergent_periodic_world_stops_before_next_native_grant(self):
        codes, host_code, host, reports, journals, context = await self.run_fixture(lambda *_: None, fault="divergent_checkpoint")
        self.assertEqual((codes, host_code), ([2, 2], 2))
        self.assertIn("fresh peer worlds differ", host["reason"])
        self.assertEqual(host["frame"], 60)
        self.assertEqual(host["state_digest_frame"], 10)
        for peer in reports:
            self.assertTrue(reports[peer]["short_preparation"]["passed"])
            self.assertEqual(len(context["wrappers"][peer].advances), 25)
            self.assertEqual(reports[peer]["last_observed_frame"], 60)


class PacedLiveStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_queue_identity_or_structure_cannot_consume_session_or_create_lease(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case in ("absent", "malformed", "wrong_epoch", "wrong_peer", "inside"):
                with self.subTest(case=case):
                    run = root / case
                    session = run / "session"
                    session.mkdir(parents=True)
                    for name in driver.PREPARED_FILES:
                        (session / name).write_text("explicit untouched fixture preparation")
                    queue = session / "input.json" if case == "inside" else run / "input.json"
                    if case == "malformed":
                        queue.write_text("{")
                    elif case != "absent":
                        live_input.create(queue, "wrong-epoch" if case == "wrong_epoch" else "paced-startup",
                                          "b" if case == "wrong_peer" else "a")
                    args = argparse.Namespace(profile="build_v2", rounds=10, timeout=15,
                        paced_live_probe=True, delay_ms=0, live_input_file=queue, peer="a",
                        epoch="paced-startup", report=run / "peer-report.json")
                    setup = {"measurement_profile": "build_v2", "measurement_preparation": SHORT_BUILD_CONTRACT}
                    with patch.object(driver, "ControllerGuard") as guard, \
                         patch.object(driver.LaunchLease, "create") as lease, \
                         patch.object(driver, "EngineAdapter") as engine:
                        code = await driver.game_peer(args, b"unused", session, setup)
                    self.assertEqual(code, 2)
                    guard.assert_not_called()
                    lease.assert_not_called()
                    engine.assert_not_called()
                    self.assertFalse((session / "controller_started.json").exists())


class PacedLiveEntryTests(unittest.TestCase):
    def test_new_flag_selects_own_coordinator_capability_and_coalesced_status(self):
        self.assertNotIn(paced_live_probe.PACED_LIVE_CAPABILITY, driver.measurement_capabilities(argparse.Namespace()))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / "key"
            key.write_bytes(b"x" * 32)
            captured = {}
            async def host(_args, _secret, **kwargs):
                captured.update(kwargs)
                return 0
            with patch.object(driver, "read_setup", return_value=(root / "session", {
                    "measurement_profile": "build_v2", "measurement_preparation": SHORT_BUILD_CONTRACT,
                    "manifest_digest": "a" * 64})), patch.object(driver, "host", side_effect=host):
                code = driver.main(["host", "--session", str(root / "session"), "--epoch", "fixture",
                    "--key-file", str(key), "--report", str(root / "report.json"), "--ready", str(root / "ready"),
                    "--profile", "build_v2", "--rounds", "10", "--paced-live-probe"])
            self.assertEqual(code, 0)
            self.assertIs(captured["coordinator_factory"], paced_live_probe.PacedLiveCoordinator)
            self.assertIn(paced_live_probe.PACED_LIVE_CAPABILITY, captured["capabilities"])
            self.assertIsInstance(captured["progress"], CoalescedProgress)

    def test_queue_argument_validation_precedes_staging_and_game_contact(self):
        base = ["--session", "unused", "--epoch", "fixture", "--key-file", "unused",
                "--report", "unused", "--profile", "build_v2", "--rounds", "10"]
        for options in (["peer", "--peer", "a", "--paced-live-probe"],
                        ["host", "--ready", "unused", "--paced-live-probe", "--live-input-file", "unused"]):
            with self.subTest(options=options), patch.object(driver, "read_setup") as setup, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    driver.main([*options, *base])
                setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
