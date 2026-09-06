"""A stale on-disk permit must never become eligible at game bootstrap."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prototype.strict_sync import game_runner as runner
from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.engine_mailbox import MailboxError
from prototype.strict_sync.model import ModelEngine
from prototype.tests.test_engine_mailbox import native_bytes


class EntryPointTests(unittest.TestCase):
    def test_packaged_host_entrypoint_selects_actual_engine_quantum(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / "key"
            key.write_bytes(b"x" * 32)
            received = {}
            async def fake_host(args, secret, **kwargs):
                received.update(kwargs)
                return 0
            with patch.object(runner, "read_setup", return_value=(root, {"manifest_digest": "a" * 64})), \
                 patch.object(runner, "host", side_effect=fake_host):
                result = runner.main(["host", "--session", str(root), "--epoch", "fixture-epoch",
                    "--key-file", str(key), "--report", str(root / "report.json"),
                    "--ready", str(root / "ready.json")])
            self.assertEqual(result, 0)
            self.assertEqual(received["step_us"], 200000)
            self.assertEqual(received["backend"], "tf2_controlled_measurement")


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs.json"
        self.inputs.write_text('{"rounds":{}}')
        self.args = argparse.Namespace(inputs=self.inputs, report=self.root / "report.json")
        self.setup = {"game_exe": str(self.root / "TransportFever2.exe")}

    def fresh(self, name="session"):
        directory = self.root / name
        directory.mkdir()
        for filename in runner.PREPARED_FILES:
            (directory / filename).write_text("prepared")
        return directory

    async def invoke(self, directory):
        with patch.object(runner, "ControllerGuard") as guard, \
             patch.object(runner, "game_is_running", return_value=False), \
             patch.object(runner, "verify_payload"), \
             patch.object(runner.LaunchLease, "create", side_effect=OSError("fixture bootstrap stops here")) as lease, \
             patch.object(runner, "EngineAdapter") as engine:
            code = await runner.game_peer(self.args, b"unused", directory, self.setup)
        self.assertEqual(code, 2)
        guard.return_value.close.assert_called_once()
        engine.assert_not_called()
        report = json.loads(self.args.report.read_text())
        self.assertTrue(report["halted"])
        self.assertFalse(report["complete_world_verified"])
        return lease, report

    async def test_stale_mailboxes_never_create_launch_lease(self):
        for index, stale in enumerate(("native_control.txt", "lua_control.json", "native_status.txt",
                                       "lua_status.json", "loader_status.txt", ".engine_mailbox.lock",
                                       "controller_started.json")):
            with self.subTest(stale=stale):
                directory = self.fresh(str(index))
                (directory / stale).write_text("old state or permit")
                self.args.report = self.root / f"report-{index}.json"
                lease, report = await self.invoke(directory)
                lease.assert_not_called()
                self.assertIn("not fresh", report["reason"])
                self.assertEqual((directory / stale).read_text(), "old state or permit")

    async def test_epoch_is_consumed_before_lease_even_if_bootstrap_fails(self):
        directory = self.fresh()
        lease, report = await self.invoke(directory)
        lease.assert_called_once()
        self.assertTrue(json.loads((directory / "controller_started.json").read_text())["consumed"])
        self.assertIn("fixture bootstrap", report["reason"])
        self.args.report = self.root / "second-report.json"
        lease, report = await self.invoke(directory)
        lease.assert_not_called()

    async def test_incomplete_preparation_never_creates_lease(self):
        directory = self.fresh()
        (directory / "probe_epoch.txt").unlink()
        lease, _ = await self.invoke(directory)
        lease.assert_not_called()


class PackagedDriverTests(unittest.IsolatedAsyncioTestCase):
    """The game, lease and engine are fixtures; TCP and file handling are real."""
    fresh = StartupTests.fresh
    def setUp(self):
        StartupTests.setUp(self)
        self.setup.update(native_epoch=7, manifest_digest="a" * 64)
        self.args = argparse.Namespace(inputs=self.inputs, report=self.root / "report.json",
                                       progress=self.root / "progress.json", stop_file=self.root / "stop",
                                       peer="a", epoch="fixture-epoch", host="127.0.0.1", port=34207,
                                       startup_timeout=.3, timeout=.2, delay_ms=0)

    def world_files(self, directory, **native):
        (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=1, **native))
        (directory / "lua_status.json").write_text(json.dumps({"protocol": 1, "epoch": "7",
            "request": 0, "revision": 1, "status": "ready", "complete": True, "snapshot": {}}))

    def test_zero_native_outer_calls_is_not_loaded_world(self):
        directory = self.fresh()
        self.world_files(directory)
        (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=0))
        ready, facts = runner.startup_facts(directory, 7)
        self.assertFalse(ready)
        self.assertEqual(facts["native"]["outer_calls"], 0)

    def test_partial_lua_write_is_not_loaded_world(self):
        directory = self.fresh()
        self.world_files(directory)
        (directory / "lua_status.json").write_text('{"protocol":1,"epoch":')
        self.assertFalse(runner.startup_facts(directory, 7)[0])

    def test_native_fault_and_lua_fault_surface_immediately(self):
        for index, kind in enumerate(("loader", "native", "lua")):
            with self.subTest(kind=kind):
                directory = self.fresh(str(index))
                self.world_files(directory)
                if kind == "loader":
                    (directory / "loader_status.txt").write_text("protocol=1\npid=22\nresult=4\n")
                elif kind == "native":
                    (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, fault=14))
                else:
                    (directory / "lua_status.json").write_text(json.dumps({"epoch": "7", "status": "halted", "error": "missing game API"}))
                with self.assertRaisesRegex(ProtocolError, "failed|halted"):
                    runner.startup_facts(directory, 7)

    def test_launcher_files_cannot_contaminate_session(self):
        directory = self.fresh()
        for name in ("progress.json", "stop"):
            with self.assertRaisesRegex(ValueError, "outside"):
                runner.external_path(directory / name, directory)

    def test_progress_replacement_is_valid_machine_json(self):
        directory = self.fresh()
        progress = runner.Progress(self.args.progress, peer="a")
        progress("waiting_game", reason="Spiel lädt")
        progress("running", frame=2)
        value = json.loads(self.args.progress.read_text(encoding="utf-8"))
        self.assertEqual(value["state"], "running")
        self.assertFalse(value["complete_world_verified"])
        self.assertEqual(set(path.name for path in directory.iterdir()), runner.PREPARED_FILES)

    async def test_stop_during_bootstrap_writes_halt_and_revokes_lease(self):
        directory = self.fresh()
        def lease_start(*_args, **_kwargs):
            self.args.stop_file.write_text("stop")
            return lease_fixture
        from unittest.mock import Mock
        lease_fixture = Mock()
        with patch.object(runner, "ControllerGuard") as guard, \
             patch.object(runner, "game_is_running", return_value=False), \
             patch.object(runner, "verify_payload"), \
             patch.object(runner.LaunchLease, "create", side_effect=lease_start), \
             patch.object(runner, "EngineAdapter") as engine:
            code = await runner.game_peer(self.args, b"x" * 32, directory, self.setup)
        self.assertEqual(code, 2)
        self.assertIn("action=halt", (directory / "native_control.txt").read_text())
        self.assertIn("epoch=7", (directory / "native_control.txt").read_text())
        engine.assert_not_called()
        lease_fixture.revoke.assert_called_once()
        guard.return_value.close.assert_called_once()
        value = json.loads(self.args.progress.read_text())
        self.assertEqual(value["state"], "halted")
        self.assertIn("stopped", value["reason"])

    async def test_startup_timeout_does_not_construct_engine(self):
        directory = self.fresh()
        self.args.startup_timeout = .01
        with patch.object(runner, "ControllerGuard"), \
             patch.object(runner, "game_is_running", return_value=False), \
             patch.object(runner, "verify_payload"), \
             patch.object(runner.LaunchLease, "create") as lease, \
             patch.object(runner, "EngineAdapter") as engine:
            code = await runner.game_peer(self.args, b"x" * 32, directory, self.setup)
        self.assertEqual(code, 2)
        self.assertIn("startup timed out", json.loads(self.args.report.read_text())["reason"])
        engine.assert_not_called()
        lease.return_value.revoke.assert_called_once()

    async def test_network_wait_stop_cancels_wait(self):
        event = asyncio.Event()
        stopped = False
        async def set_stop():
            nonlocal stopped
            await asyncio.sleep(.02)
            stopped = True
        trigger = asyncio.create_task(set_stop())
        with self.assertRaises(runner.StopRequested):
            await runner.stoppable(event.wait(), lambda: stopped, 10)
        await trigger

    async def test_host_waits_startup_duration_then_stops_without_world_permits(self):
        args = argparse.Namespace(epoch="fixture-epoch", timeout=.05, rounds=2, bind="127.0.0.1", port=0,
                                  ready=self.root / "ready.json", report=self.root / "host.json")
        progress = []
        stop = False
        task = asyncio.create_task(runner.host(args, b"x" * 32, expected_manifest="a" * 64,
            capabilities=runner.CAPABILITIES, startup_timeout=3,
            progress=lambda state, **facts: progress.append((state, facts)), stop_requested=lambda: stop))
        await asyncio.sleep(.12)
        self.assertFalse(task.done(), "round timeout must not expire manual loading")
        stop = True
        self.assertEqual(await asyncio.wait_for(task, 1), 2)
        report = json.loads(args.report.read_text())
        self.assertEqual(report["frame"], 0)
        self.assertFalse(report["coordinated_completed"])
        self.assertNotIn("step", [value["kind"] for value in report["actions"]])
        self.assertEqual(progress[-1][0], "halted")

    async def test_real_tcp_engine_quantum_pause_and_terminal_completion(self):
        await self.tcp_engine_run()

    async def test_real_tcp_local_fault_reaches_host_and_other_peer_before_eof(self):
        await self.tcp_engine_run(fail=True)

    async def tcp_engine_run(self, fail=False):
        secret = b"x" * 32
        host_args = argparse.Namespace(epoch="fixture-epoch", timeout=1, rounds=3, bind="127.0.0.1", port=0,
                                       ready=self.root / "ready.json", report=self.root / "host.json")
        host_task = asyncio.create_task(runner.host(host_args, secret, expected_manifest="a" * 64,
                                                  capabilities=runner.CAPABILITIES, startup_timeout=3,
                                                  step_us=runner.ENGINE_STEP_US))
        while not host_args.ready.exists():
            if host_task.done():
                await host_task
            await asyncio.sleep(.005)
        port = json.loads(host_args.ready.read_text())["port"]
        engines = []
        closed_when_error_sent = []
        real_send = runner.send
        async def observed_send(writer, message):
            if message.get("kind") == "peer_error":
                closed_when_error_sent.append(next(engine.closed for engine in engines if engine.should_fail))
            await real_send(writer, message)
        outer = self
        class EngineFixture(ModelEngine):
            capabilities = runner.CAPABILITIES
            frame = 0
            def __init__(self, *_args, **_kwargs):
                super().__init__()
                self.closed = False
                self.steps = []
                self.should_fail = fail and Path(_args[0]).name == "a"
                engines.append(self)
            def step(self, dt_us):
                if self.closed or dt_us not in (0, 200000):
                    raise ValueError("fixture refuses advances after close or unsafe engine quantum")
                if self.should_fail and len(self.steps) == 2:
                    raise MailboxError("native gate halted: fault=0, runtime_fault=102, win32_error=5")
                self.steps.append(dt_us)
                return super().step(dt_us)
            def close(self):
                self.closed = True
        def lease_start(_exe, directory, **_kwargs):
            outer.world_files(directory)
            from unittest.mock import Mock
            return Mock()
        peers = []
        with patch.object(runner, "ControllerGuard"), \
             patch.object(runner, "game_is_running", return_value=False), \
             patch.object(runner, "verify_payload"), \
             patch.object(runner.LaunchLease, "create", side_effect=lease_start), \
             patch.object(runner, "EngineAdapter", EngineFixture), \
             patch.object(runner, "send", side_effect=observed_send):
            for peer in ("a", "b"):
                args = argparse.Namespace(**vars(self.args))
                args.peer, args.port, args.timeout = peer, port, 1
                args.delay_ms = 15 if peer == "b" else 0
                args.report = self.root / f"{peer}.report.json"
                args.progress = self.root / f"{peer}.progress.json"
                if peer == "a":
                    args.inputs = self.root / "engine-quantum-inputs.json"
                    args.inputs.write_text(json.dumps({"rounds": {
                        "0": [{"op": "SET_PAUSED", "value": False}],
                        "1": [{"op": "SET_PAUSED", "value": True}],
                        "2": [{"op": "SET_PAUSED", "value": False}]}}))
                peers.append(asyncio.create_task(runner.game_peer(args, secret, self.fresh(peer), self.setup)))
            self.assertEqual(await asyncio.gather(*peers), [2, 2] if fail else [0, 0])
        self.assertEqual(await host_task, 2 if fail else 0)
        if fail:
            host_report = json.loads(host_args.report.read_text())
            self.assertEqual(host_report["round"], 2)
            self.assertEqual(host_report["frame"], 2)
            self.assertEqual(host_report["peer_error"]["peer"], "a")
            self.assertEqual(host_report["peer_error"]["round"], 2)
            self.assertIn("runtime_fault=102, win32_error=5", host_report["reason"])
            self.assertNotIn("IncompleteReadError", host_report["reason"])
            for peer in ("a", "b"):
                report = json.loads((self.root / f"{peer}.report.json").read_text())
                progress = json.loads((self.root / f"{peer}.progress.json").read_text())
                self.assertIn("runtime_fault=102, win32_error=5", report["reason"])
                self.assertIsNone(report["snapshot"])
                self.assertIsNone(report["snapshot_scope"])
                self.assertIsNotNone(report["last_observed_snapshot"])
                self.assertEqual(progress["round"], report["round"])
                self.assertNotIn("native", progress)
            self.assertTrue(json.loads((self.root / "a.report.json").read_text())["peer_error_sent"])
            self.assertEqual(closed_when_error_sent, [True])
            self.assertTrue(all(engine.closed for engine in engines))
            self.assertTrue(all(len(engine.steps) <= 3 for engine in engines))
            return
        self.assertTrue(json.loads(host_args.report.read_text())["coordinated_completed"])
        for peer in ("a", "b"):
            report = json.loads((self.root / f"{peer}.report.json").read_text())
            self.assertTrue(report["local_completed"])
            self.assertFalse(report["coordinated_completed"])
            self.assertFalse(report["complete_world_verified"])
        self.assertTrue(all(engine.closed for engine in engines))
        self.assertEqual([engine.steps for engine in engines], [[200000, 0, 200000]] * 2)
        self.assertEqual([engine.time_us for engine in engines], [400000, 400000])
        self.assertEqual(json.loads(host_args.report.read_text())["sim_time_us"], 400000)


if __name__ == "__main__":
    unittest.main()
