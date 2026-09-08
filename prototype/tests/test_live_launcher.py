"""File-backed launcher lifecycle checks; never open Tk or launch TF2."""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync.live_input import create, InputReader, InputError
from prototype.strict_sync.test_pairing import connection_receipt
from prototype.tests import test_launcher_session as fixtures


class LiveLauncherTests(unittest.TestCase):
    setUp = fixtures.LauncherSessionTests.setUp
    fake_spawn = fixtures.LauncherSessionTests.fake_spawn
    controller = fixtures.LauncherSessionTests.controller
    lobby = fixtures.LauncherSessionTests.lobby
    host_ready = fixtures.LauncherSessionTests.host_ready

    def live_run(self, role="a"):
        self.run = replace(self.run, role=role, test_mode=workflow.LIVE_MODE)
        create(self.run.live_input_path, self.run.epoch, role)
        return self.controller(role)

    def running(self, controller):
        controller.start()
        self.lobby()
        self.host_ready()
        controller.poll()
        self.progress()

    def progress(self, **changes):
        live = {"started": True, "completed": False, "paused": False,
                "confirmed_paused": False, "acknowledged_seq": {"a": 0, "b": 0}}
        live.update(changes)
        workflow.write_json(self.run_dir / "peer-progress.json", {"state": "running", "round": 240, "live": live})

    def test_reference_preparation_defers_queue_until_authenticated_connection(self):
        saves = self.root / "saves"
        saves.mkdir()
        with patch.object(workflow, "installation_status", return_value={"installed": False}), \
             patch.object(workflow, "stage_probe", return_value={"output": str(self.root / "payload"),
                 "session": str(self.root / "session"), "manifest_digest": "b" * 64}), \
             patch.object(workflow, "install_probe", return_value={"imported_save": str(saves / "fresh.sav"),
                 "backup_path": str(self.root / "backup")}):
            prepared = workflow.prepare(self.root, saves, "b", "127.0.0.1", workflow.new_code(),
                source_root=self.root, save=self.root / "base.sav", runs_root=self.root / "runs",
                test_mode=workflow.LIVE_MODE)
        self.assertEqual(prepared.test_mode, workflow.LIVE_MODE)
        self.assertFalse(prepared.epoch)
        self.assertFalse(prepared.live_input_path.exists())
        self.assertFalse((prepared.directory / "session.key").exists())
        controller = workflow.SessionController(prepared, spawn=self.spawn)
        controller.start()
        self.assertEqual(set(controller.children), {"lobby"})
        self.assertFalse(prepared.live_input_path.exists())
        epoch = "e" * 32
        connected = {"protocol": 2, "state": "connected", "role": "b",
                     "local_run": prepared.local_run, "epoch": epoch, "manifest": prepared.manifest}
        connected["run_proof"] = connection_receipt(
            (prepared.directory / "pairing.key").read_bytes(), role="b",
            local_run=prepared.local_run, epoch=epoch, manifest=prepared.manifest)
        workflow.write_json(prepared.directory / "lobby-progress.json", connected)
        status = controller.poll()
        self.assertFalse(status["failure"])
        self.assertTrue(status["peer_started"])
        self.assertEqual(prepared.epoch, epoch)
        self.assertNotEqual(prepared.epoch, prepared.pairing_epoch)
        self.assertEqual(InputReader(prepared.live_input_path, prepared.epoch, "b").take(), [])
        self.assertEqual(json.loads((prepared.directory / "run.json").read_text())["test_mode"], workflow.LIVE_MODE)

    def test_missing_or_wrong_identity_queue_prevents_all_processes(self):
        self.run = replace(self.run, test_mode=workflow.LIVE_MODE)
        controller = self.controller()
        with self.assertRaises(OSError):
            controller.start()
        self.assertFalse(controller.started)
        create(self.run.live_input_path, "1" * 32, "a")
        with self.assertRaises(InputError):
            controller.start()
        self.spawn.assert_not_called()

    def test_real_request_written_only_after_interactive_phase_and_never_game_launch(self):
        controller = self.live_run()
        with self.assertRaises(ValueError):
            controller.submit_live({"op": "SET_PAUSED", "value": True})
        self.running(controller)
        self.assertEqual(controller.submit_live({"op": "SET_PAUSED", "value": True}), 1)
        self.assertEqual(InputReader(self.run.live_input_path, self.run.epoch, "a").take(),
                         [{"seq": 1, "command": {"op": "SET_PAUSED", "value": True}}])
        for command, _, _ in self.spawned:
            if "game" in command:
                self.assertIn("--live-probe", command)
                self.assertNotIn("--stream-probe", command)
                self.assertNotIn("--timing-probe", command)
                self.assertEqual("--live-input-file" in command, "peer" in command)
            self.assertNotIn("TransportFever2.exe", " ".join(map(str, command)))

    def test_client_gets_own_queue_and_same_live_capability(self):
        controller = self.live_run("b")
        self.running(controller)
        command = self.spawned[-1][0]
        self.assertIn("--live-probe", command)
        self.assertEqual(command[command.index("--peer") + 1], "b")
        self.assertEqual(command[command.index("--live-input-file") + 1], str(self.run.live_input_path))

    def test_local_apply_is_not_joint_confirmation(self):
        controller = self.live_run()
        self.running(controller)
        controller.submit_live({"op": "SET_PAUSED", "value": True})
        self.progress(paused=True)
        status = controller.poll()
        self.assertIn("Gemeinsamer Zustand: läuft", workflow.live_input_status(status))
        self.assertIn("Noch 1 zur Bestätigung offen", workflow.live_input_status(status))
        self.progress(paused=True, confirmed_paused=True, acknowledged_seq={"a": 1, "b": 0})
        self.assertIn("Kein eigener Wunsch offen", workflow.live_input_status(controller.poll()))

    def test_end_request_is_not_completion_and_closes_local_buttons(self):
        controller = self.live_run()
        self.running(controller)
        controller.submit_live({"op": "END_TEST"})
        status = controller.poll()
        self.assertTrue(status["finish_requested"])
        self.assertFalse(status["completed"])
        self.assertFalse(workflow.live_input_ready(status))
        with self.assertRaises(ValueError):
            controller.submit_live({"op": "SET_PAUSED", "value": False})
        self.assertFalse(self.run.stop_path.exists())

    def test_failed_queue_write_does_not_claim_pending_request(self):
        controller = self.live_run()
        self.running(controller)
        with patch.object(controller._input_writer, "submit", side_effect=OSError("busy")):
            with self.assertRaises(OSError):
                controller.submit_live({"op": "END_TEST"})
        self.assertEqual(controller.last_submitted_seq, 0)
        self.assertFalse(controller.finish_requested)

    def test_stop_disconnect_and_completion_block_new_inputs(self):
        controller = self.live_run()
        self.running(controller)
        controller.stop()
        with self.assertRaises(ValueError):
            controller.submit_live({"op": "SET_PAUSED", "value": True})
        base = {"test_mode": workflow.LIVE_MODE, "peer_started": True, "alive": True, "live": {"started": True}}
        self.assertTrue(workflow.live_input_ready(base))
        for change in ({"completed": True}, {"failure": "disconnect"}, {"live": {"started": True, "ending": True}},
                       {"alive": False}, {"test_mode": workflow.STREAM_MODE}):
            self.assertFalse(workflow.live_input_ready(base | change))

    def test_early_clean_finish_does_not_claim_interactions_passed(self):
        controller = self.live_run()
        workflow.write_json(self.run_dir / "peer-report.json", {"finished": True,
            "live": {"required_interactions_met": False}})
        text = workflow.describe_status(controller.poll())
        self.assertIn("Nicht alle vorgesehenen Bedienproben", text)
        self.assertNotIn("1x-Ziel", text)

    def test_larger_live_report_is_read_with_separate_progress_limit(self):
        controller = self.live_run()
        workflow.write_json(self.run_dir / "peer-report.json", {"finished": True,
            "padding": "x" * (4 * 1024 * 1024), "live": {"required_interactions_met": True}})
        self.assertTrue(controller.poll()["completed"])

    def test_mode_identity_preserves_old_paths_and_separates_guided_suite(self):
        previous = {workflow.STREAM_MODE, workflow.TIMING_MODE, workflow.LIVE_MODE,
                    workflow.PACED_LIVE_MODE, workflow.MANUAL_DEPOT_MODE}
        self.assertEqual(set(workflow.TEST_MODES), previous | {workflow.GUIDED_MODE})
        previous_manifests = {workflow.lobby_manifest("e" * 64, mode) for mode in previous}
        self.assertEqual(len(previous_manifests), 5)
        self.assertNotIn(workflow.lobby_manifest("e" * 64, workflow.GUIDED_MODE), previous_manifests)

    def test_real_headless_button_handler_sends_request_and_disables_after_end(self):
        from prototype.tests.test_update_startup import headless_app
        from prototype import launcher
        controller = self.live_run()
        self.running(controller)
        app = headless_app()
        app.busy = False
        app.controller = controller
        app.last_live_status = controller.poll()
        with patch.object(launcher.tk, "Tk", side_effect=AssertionError("No UI")), \
             patch.object(launcher.messagebox, "showerror", side_effect=AssertionError("Unexpected error dialog")):
            app._buttons()
            for button in app.live_buttons:
                button.configure.assert_called_with(state="normal")
            app.submit_live({"op": "END_TEST"})
            for button in app.live_buttons:
                button.configure.assert_called_with(state="disabled")
        self.assertEqual(controller.last_submitted_seq, 1)
        self.assertIn("lokal angenommen", app.live_status.get())
        self.assertFalse(self.run.stop_path.exists())

    def test_terminal_pending_request_remains_unconfirmed_and_pause_metric_is_visible(self):
        controller = self.live_run()
        self.running(controller)
        controller.submit_live({"op": "SET_PAUSED", "value": True})
        self.progress(paused=True, confirmed_paused=True, paused_duration_ms=35000, long_pause_met=True)
        status = controller.poll()
        status["completed"] = True
        text = workflow.live_input_status(status)
        self.assertIn("Lange Pause erfasst", text)
        self.assertIn("Ohne gemeinsame Bestätigung beendet: 1", text)
        self.assertNotIn("zur Bestätigung offen", text)


if __name__ == "__main__":
    unittest.main()
