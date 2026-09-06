"""Launcher lifecycle tests: fake processes/files, never install or launch TF2."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from prototype.strict_sync import launcher_session as workflow


class FakeChild:
    def __init__(self):
        self.returncode = None
    def poll(self):
        return self.returncode


class LauncherSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_dir = self.root / "run"
        self.run_dir.mkdir()
        self.session = self.run_dir / "session"
        self.session.mkdir()
        self.run = workflow.PreparedRun(str(self.run_dir), str(self.root / "game"), str(self.session),
            str(self.run_dir / "payload"), str(self.root / "imported.sav"), str(self.root / "backup"),
            "a", "25.1.2.3", "f" * 32, "a" * 64)
        self.spawned = []
        self.spawn = Mock(side_effect=self.fake_spawn)
        self.running_patch = patch.object(workflow, "game_is_running", return_value=False)
        self.running_patch.start()
        self.addCleanup(self.running_patch.stop)

    def fake_spawn(self, command, **options):
        child = FakeChild()
        self.spawned.append((command, options, child))
        return child

    def controller(self, role="a"):
        return workflow.SessionController(replace(self.run, role=role), spawn=self.spawn)

    def lobby(self, **changes):
        data = {"protocol": 1, "state": "connected", "epoch": self.run.epoch,
                "manifest": self.run.manifest, "role": self.run.role}
        data.update(changes)
        workflow.write_json(self.run_dir / "lobby-progress.json", data)

    def host_ready(self, **changes):
        data = {"port": workflow.PORT, "epoch": self.run.epoch, "backend": "tf2_controlled_measurement"}
        data.update(changes)
        workflow.write_json(self.run_dir / "host-ready.json", data)

    def test_identity_is_canonical_and_key_is_not_code(self):
        code = "0123-4567-89AB-CDEF-0123-4567-89AB-CDEF"
        epoch, secret = workflow.connection_identity(code)
        self.assertEqual((epoch, secret), workflow.connection_identity("  " + code.lower().replace("-", " ") + "  "))
        self.assertEqual(len(epoch), 32)
        self.assertEqual(len(secret), 64)
        self.assertNotIn(code.replace("-", "").lower().encode(), secret)
        for invalid in ("", "abcd", code[:-1], code.replace("A", "Z")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                workflow.connection_identity(invalid)

    def test_host_validation_and_new_code(self):
        self.assertEqual(workflow.validate_host(" 25.1.2.3 "), "25.1.2.3")
        for invalid in ("0.0.0.0", "255.255.255.255", "224.0.0.1", "host.example", "::1", "1.2.3.999"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                workflow.validate_host(invalid)
        first, second = workflow.new_code(), workflow.new_code()
        self.assertNotEqual(first, second)
        self.assertEqual(len(first.split("-")), 8)
        workflow.connection_identity(first)

    def test_frozen_worker_command_dispatches_same_executable(self):
        with patch.object(workflow.sys, "frozen", True, create=True), \
             patch.object(workflow.sys, "executable", str(self.root / "TF2 Test.exe")):
            result = workflow.worker_command("game", ["peer", "--port", 34207], self.root / "peer log.txt")
        self.assertEqual(result, [str(self.root / "TF2 Test.exe"), "--worker-log", str(self.root / "peer log.txt"),
                                  "--worker", "game", "peer", "--port", "34207"])

    def test_host_peer_starts_once_only_after_lobby_and_valid_host_ready(self):
        controller = self.controller()
        controller.start()
        self.assertEqual(set(controller.children), {"host", "lobby"})
        controller.poll()
        self.lobby()
        controller.poll()
        self.assertNotIn("peer", controller.children)
        self.host_ready()
        controller.poll()
        controller.poll()
        self.assertEqual(set(controller.children), {"host", "lobby", "peer"})
        self.assertEqual(self.spawn.call_count, 3)
        command, options, _ = self.spawned[-1]
        self.assertEqual(command[command.index("--delay-ms") + 1], "0")
        self.assertEqual(command[command.index("--rounds") + 1], "240")
        self.assertEqual(command[command.index("--profile") + 1], "build_v1")
        self.assertIn("--worker", command)
        self.assertNotIn(str(self.root / "game/TransportFever2.exe"), command)
        self.assertEqual(options["stdin"], workflow.subprocess.DEVNULL)
        self.assertEqual(options["creationflags"], getattr(workflow.subprocess, "CREATE_NO_WINDOW", 0))

    def test_peer_uses_100ms_delay_and_host_address(self):
        controller = self.controller("b")
        controller.start()
        self.assertEqual(set(controller.children), {"lobby"})
        self.lobby()
        controller.poll()
        command = self.spawned[-1][0]
        self.assertEqual(command[command.index("--host") + 1], "25.1.2.3")
        self.assertEqual(command[command.index("--peer") + 1], "b")
        self.assertEqual(command[command.index("--delay-ms") + 1], "100")

    def test_invalid_or_other_epoch_host_ready_never_starts_peer(self):
        controller = self.controller()
        controller.start()
        self.lobby()
        for document in (None, {"epoch": "old"}, {"epoch": self.run.epoch, "port": 3,
                         "backend": "tf2_controlled_measurement"}):
            (self.run_dir / "host-ready.json").write_text("{" if document is None else json.dumps(document))
            controller.poll()
            self.assertFalse(controller.peer_started)

    def test_other_lobby_identity_never_starts_peer(self):
        controller = self.controller("b")
        controller.start()
        self.lobby(epoch="old-session")
        controller.poll()
        self.assertFalse(controller.peer_started)

    def test_partial_host_ready_waits_then_valid_publication_can_start(self):
        controller = self.controller()
        controller.start()
        self.lobby()
        (self.run_dir / "host-ready.json").write_text('{"port":')
        waiting = controller.poll()
        self.assertFalse(waiting["stopping"])
        self.assertFalse(controller.peer_started)
        self.host_ready()
        controller.poll()
        self.assertTrue(controller.peer_started)

    def test_stop_or_failure_prevents_deferred_peer_spawn(self):
        controller = self.controller()
        controller.start()
        self.lobby()
        self.host_ready()
        controller.stop()
        controller.poll()
        self.assertFalse(controller.peer_started)
        self.assertTrue(self.run.stop_path.is_file())
        with self.assertRaises(ValueError):
            controller.start()

    def test_controller_failure_stops_others_before_peer_spawn(self):
        controller = self.controller()
        controller.start()
        self.lobby()
        self.host_ready()
        controller.children["host"].returncode = 2
        result = controller.poll()
        self.assertTrue(result["failure"])
        self.assertTrue(controller.stopping)
        self.assertFalse(controller.peer_started)

    def test_unexpected_clean_controller_exit_never_starts_peer(self):
        controller = self.controller()
        controller.start()
        self.lobby()
        self.host_ready()
        controller.children["host"].returncode = 0
        result = controller.poll()
        self.assertTrue(result["failure"])
        self.assertTrue(controller.stopping)
        self.assertFalse(controller.peer_started)

    def test_peer_spawn_failure_is_terminal_and_not_retried(self):
        controller = self.controller()
        controller.start()
        self.lobby()
        self.host_ready()
        self.spawn.side_effect = OSError("fixture process creation failure")
        result = controller.poll()
        self.assertTrue(result["failure"])
        self.assertTrue(controller.stopping)
        attempted = self.spawn.call_count
        repeated = controller.poll()
        self.assertTrue(repeated["failure"], "the original failure remains visible after stop")
        self.assertEqual(attempted, self.spawn.call_count)

    def test_completion_does_not_claim_complete_world(self):
        controller = self.controller()
        controller.start()
        self.lobby()
        self.host_ready()
        controller.poll()
        workflow.write_json(self.run_dir / "peer-report.json", {"finished": True, "complete_world_verified": False})
        workflow.write_json(self.run_dir / "host-report.json", {"coordinated_completed": True})
        result = controller.poll()
        self.assertTrue(result["completed"])
        self.assertTrue(result["coordinated_completed"])
        self.assertIn("Bautest abgeschlossen", workflow.describe_status(result))

    def test_actual_peer_fault_and_last_round_survive_follow_on_disconnect(self):
        controller = self.controller()
        controller.start()
        workflow.write_json(self.run_dir / "host-progress.json", {
            "state": "halted", "reason": "peer a: IncompleteReadError", "round": 38})
        workflow.write_json(self.run_dir / "peer-progress.json", {
            "state": "halted", "reason": "ProtocolError: native IO error runtime_fault=102 win32_error=5"})
        workflow.write_json(self.run_dir / "peer-report.json", {"halted": True, "round": 38})
        result = controller.poll()
        self.assertIn("win32_error=5", result["failure"])
        self.assertEqual(result["round"], 38)
        self.assertFalse(result["completed"])
        self.assertTrue(controller.stopping)
        workflow.write_json(self.run_dir / "peer-progress.json", {
            "state": "halted", "reason": "controller requested halt"})
        self.assertIn("win32_error=5", controller.poll()["failure"])

    def test_report_arriving_after_disconnect_replaces_generic_reason(self):
        controller = self.controller()
        controller.start()
        workflow.write_json(self.run_dir / "host-progress.json", {
            "state": "halted", "reason": "peer a: IncompleteReadError", "round": 6})
        self.assertIn("IncompleteReadError", controller.poll()["failure"])
        workflow.write_json(self.run_dir / "peer-report.json", {
            "halted": True, "round": 6, "reason": "ProtocolError: native IO error win32_error=5"})
        result = controller.poll()
        self.assertIn("win32_error=5", result["failure"])
        self.assertEqual(result["round"], 6)

    def test_halt_without_final_peer_round_uses_report_not_startup_default(self):
        controller = self.controller("b")
        controller.start()
        workflow.write_json(self.run_dir / "peer-progress.json", {"state": "halted"})
        workflow.write_json(self.run_dir / "peer-report.json", {"halted": True, "round": 38})
        self.assertEqual(controller.poll()["round"], 38)

    def test_diagnostic_archive_allowlist_excludes_credentials_and_save(self):
        for name in ("session.key", "run.json", "code.txt", "initial.sav", "initial.sav.lua", "peer-report.json", "peer.log", "peer-journal.jsonl"):
            (self.run_dir / name).write_text("sensitive" if name in ("session.key", "code.txt") else name)
        for name in ("probe_manifest.json", "native_status.txt", "lua_status.json", "loader_status.txt", "probe_setup.json", "config.lua"):
            (self.session / name).write_text(name)
        destination = self.root / "diagnostics.zip"
        workflow.export_diagnostics(self.run, destination)
        with zipfile.ZipFile(destination) as archive:
            names = set(archive.namelist())
            self.assertIn("peer-report.json", names)
            self.assertIn("peer-journal.jsonl", names)
            self.assertIn("session/native_status.txt", names)
            self.assertIn("session/lua_status.json", names)
            self.assertNotIn("session.key", names)
            self.assertNotIn("run.json", names)
            self.assertNotIn("initial.sav", names)
            self.assertNotIn("session/config.lua", names)
            self.assertNotIn("session/probe_setup.json", names)
        with self.assertRaises(ValueError):
            workflow.export_diagnostics(self.run, destination)

    def test_prepare_stages_before_explicit_install_and_second_run_is_fresh(self):
        game, saves, source = (self.root / name for name in ("game", "saves", "source"))
        for path in (game, saves, source):
            path.mkdir()
        events = []
        def stage(**kwargs):
            events.append("stage")
            self.assertEqual(kwargs["profile"], "build_v1")
            return {"session": str(kwargs["session"]), "output": str(kwargs["output"]), "manifest_digest": "a" * 64}
        def install(_game, _payload, _save, **kwargs):
            events.append("install")
            return {"imported_save": str(saves / "test.sav"), "backup_path": str(game / "backup")}
        with patch.object(workflow, "installation_status", return_value={"installed": False}), \
             patch.object(workflow, "stage_probe", side_effect=stage), \
             patch.object(workflow, "install_probe", side_effect=install):
            first = workflow.prepare(game, saves, "a", "127.0.0.1", workflow.new_code(),
                                     source_root=source, save=self.root / "baseline.sav", runs_root=self.root / "runs")
            second = workflow.prepare(game, saves, "b", "25.1.2.3", workflow.new_code(),
                                      source_root=source, save=self.root / "baseline.sav", runs_root=self.root / "runs")
        self.assertEqual(events, ["stage", "install", "stage", "install"])
        self.assertNotEqual(first.run_dir, second.run_dir)
        self.assertEqual(len((first.directory / "session.key").read_bytes()), 64)
        self.assertNotIn("session.key", (first.directory / "run.json").read_text())

    def test_prepare_refuses_installed_test_without_staging(self):
        with patch.object(workflow, "installation_status", return_value={"installed": True}), \
             patch.object(workflow, "stage_probe") as stage:
            with self.assertRaisesRegex(ValueError, "wiederherstellen"):
                workflow.prepare(self.root, self.root, "a", "127.0.0.1", workflow.new_code())
        stage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
