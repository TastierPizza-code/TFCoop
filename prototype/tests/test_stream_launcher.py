"""Stream selection and honest progress scopes, with files/fake workers only."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from prototype.strict_sync import game_runner as driver
from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync.stream_probe import STREAM_CAPABILITY
from prototype.strict_sync.timing_probe import TIMING_CAPABILITY
from prototype.tests import test_launcher_session as fixtures


class StreamLauncherTests(unittest.TestCase):
    setUp = fixtures.LauncherSessionTests.setUp
    fake_spawn = fixtures.LauncherSessionTests.fake_spawn
    controller = fixtures.LauncherSessionTests.controller
    lobby = fixtures.LauncherSessionTests.lobby
    host_ready = fixtures.LauncherSessionTests.host_ready

    def test_old_prepared_records_keep_comparison_and_new_prepare_defaults_to_stream(self):
        self.assertEqual(self.run.test_mode, workflow.TIMING_MODE)
        saves = self.root / "saves"
        saves.mkdir()
        def stage(**kwargs):
            return {"session": str(kwargs["session"]), "output": str(kwargs["output"]),
                    "manifest_digest": "b" * 64}
        with patch.object(workflow, "installation_status", return_value={"installed": False}), \
             patch.object(workflow, "stage_probe", side_effect=stage), \
             patch.object(workflow, "install_probe", return_value={
                 "imported_save": str(saves / "fresh.sav"), "backup_path": str(self.root / "backup")}):
            prepared = workflow.prepare(self.root, saves, "a", "127.0.0.1", workflow.new_code(),
                source_root=self.root, save=self.root / "base.sav", runs_root=self.root / "runs",
                test_mode=workflow.STREAM_MODE)
        self.assertEqual(prepared.test_mode, workflow.STREAM_MODE)
        self.assertEqual(prepared.manifest, workflow.lobby_manifest("b" * 64, workflow.STREAM_MODE))
        self.assertEqual(json.loads((prepared.directory / "run.json").read_text())["test_mode"],
                         workflow.STREAM_MODE)

    def test_both_worker_roles_get_selected_flag_and_never_both(self):
        for mode, flag, absent in ((workflow.STREAM_MODE, "--stream-probe", "--timing-probe"),
                                  (workflow.TIMING_MODE, "--timing-probe", "--stream-probe")):
            for role in ("a", "b"):
                with self.subTest(mode=mode, role=role):
                    self.run = replace(self.run, test_mode=mode, role=role)
                    controller = self.controller(role)
                    controller.start()
                    self.lobby()
                    self.host_ready()
                    controller.poll()
                    game_commands = [command for command, _, _ in self.spawned
                                     if command[command.index("--worker") + 1] == "game"]
                    self.assertEqual(len(game_commands), 2 if role == "a" else 1)
                    for command in game_commands:
                        self.assertIn(flag, command)
                        self.assertNotIn(absent, command)
                        self.assertNotIn("TransportFever2.exe", " ".join(map(str, command)))
                    self.spawned.clear()

    def test_different_modes_bind_different_lobby_identity_and_cannot_start_game_peer(self):
        file_hash = "f" * 64
        stream = workflow.lobby_manifest(file_hash, workflow.STREAM_MODE)
        timing = workflow.lobby_manifest(file_hash, workflow.TIMING_MODE)
        self.assertNotEqual(stream, timing)
        self.assertEqual(stream, workflow.lobby_manifest(file_hash, workflow.STREAM_MODE))
        self.run = replace(self.run, manifest=stream, test_mode=workflow.STREAM_MODE)
        controller = self.controller()
        controller.start()
        self.host_ready()
        self.lobby(manifest=timing)
        status = controller.poll()
        self.assertFalse(controller.peer_started)
        self.assertTrue(status["failure"])
        self.assertTrue(status["stopping"])

    def test_invalid_mode_is_rejected_before_preparation_writes(self):
        with patch.object(workflow, "stage_probe") as stage, self.assertRaises(ValueError):
            workflow.prepare(self.root, self.root, "a", "127.0.0.1", workflow.new_code(), test_mode="bad")
        stage.assert_not_called()
        with self.assertRaises(ValueError):
            replace(self.run, test_mode="bad")

    def test_host_uses_joint_outcome_and_client_labels_local_tempo(self):
        self.run = replace(self.run, test_mode=workflow.STREAM_MODE)
        local = {"completed": True, "paced_stream_1x_met": True,
                 "completion_scope": "local_checkpoint_boundaries"}
        joint = {**local, "paced_stream_1x_met": False,
                 "completion_scope": "both_peer_checkpoint_boundaries"}
        workflow.write_json(self.run_dir / "peer-report.json", {"finished": True, "stream": local})
        controller = self.controller("b")
        status = controller.poll()
        self.assertIn("Tempo auf deinem PC: 1x-Ziel erreicht", workflow.describe_status(status))
        self.assertNotIn("Beide PCs", workflow.describe_status(status))
        workflow.write_json(self.run_dir / "host-report.json", {"coordinated_completed": True, "stream": joint})
        status = self.controller().poll()
        self.assertEqual(status["stream_result"], joint)
        self.assertIn("Beide PCs: 1x-Ziel noch nicht erreicht", workflow.describe_status(status))
        self.assertIn("Darstellung separat beurteilen", workflow.describe_status(status))

    def test_native_progress_does_not_claim_completion_or_fresh_world(self):
        self.run = replace(self.run, test_mode=workflow.STREAM_MODE)
        controller = self.controller("b")
        workflow.write_json(self.run_dir / "peer-progress.json", {"state": "running", "round": 240,
            "stream": {"started": True, "advanced_steps": 52, "checkpoint_index": 1,
                       "frame": 292, "last_observed_frame": 290}})
        status = controller.poll()
        self.assertFalse(status["completed"])
        self.assertEqual(status["stream"]["last_observed_frame"], 290)
        description = workflow.describe_status(status)
        self.assertIn("10 / 120 Sekunden Spielzeit", description)
        self.assertIn("Kontrollpunkt 1 / 12", description)
        self.assertNotIn("abgeschlossen", description)

    def test_stream_profile_requires_matching_build_and_safe_phase_timeout(self):
        args = SimpleNamespace(profile="build_v2", rounds=240, stream_probe=True,
                               timing_probe=False, delay_ms=0, timeout=30)
        self.assertEqual(driver.selected_profile(args, {"measurement_profile": "build_v2"}), "build_v2")
        caps = driver.measurement_capabilities(args)
        self.assertIn(STREAM_CAPABILITY, caps)
        self.assertNotIn(TIMING_CAPABILITY, caps)
        for changes in ({"timing_probe": True}, {"delay_ms": 5}, {"timeout": 14}, {"rounds": 239}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                driver.selected_profile(SimpleNamespace(**(vars(args) | changes)), {"measurement_profile": "build_v2"})
        with self.assertRaises(ValueError):
            driver.selected_profile(args, {"measurement_profile": "time_v1"})


if __name__ == "__main__":
    unittest.main()
