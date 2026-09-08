"""New short mode binds the preparation and uses the existing guarded input UI."""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync.live_input import create, InputReader
from prototype.tests import test_launcher_session as fixtures


class PacedLiveLauncherTests(unittest.TestCase):
    setUp = fixtures.LauncherSessionTests.setUp
    fake_spawn = fixtures.LauncherSessionTests.fake_spawn
    controller = fixtures.LauncherSessionTests.controller
    lobby = fixtures.LauncherSessionTests.lobby
    host_ready = fixtures.LauncherSessionTests.host_ready

    def test_default_preparation_binds_short_contract_and_fresh_queue(self):
        saves = self.root / "saves"
        saves.mkdir()
        with patch.object(workflow, "installation_status", return_value={"installed": False}), \
             patch.object(workflow, "stage_probe", return_value={"output": str(self.root / "payload"),
                 "session": str(self.root / "session"), "manifest_digest": "b" * 64}) as staged, \
             patch.object(workflow, "install_probe", return_value={"imported_save": str(saves / "fresh.sav"),
                 "backup_path": str(self.root / "backup")}):
            prepared = workflow.prepare(self.root, saves, "b", "127.0.0.1", workflow.new_code(),
                source_root=self.root, save=self.root / "base.sav", runs_root=self.root / "runs")
        self.assertEqual(prepared.test_mode, workflow.PACED_LIVE_MODE)
        self.assertEqual(staged.call_args.kwargs["preparation"], "short_scene_v1")
        self.assertFalse(prepared.live_input_path.exists())
        self.assertFalse(prepared.epoch)
        self.assertTrue(prepared.local_run)
        self.assertEqual(json.loads((prepared.directory / "run.json").read_text())["test_mode"],
                         workflow.PACED_LIVE_MODE)

    def test_both_roles_pass_ten_rounds_and_distinct_capability(self):
        for role in ("a", "b"):
            run = replace(self.run, role=role, test_mode=workflow.PACED_LIVE_MODE)
            controller = workflow.SessionController(run)
            for mode in ("host", "peer"):
                args = controller._game_args(mode)
                self.assertEqual(args[args.index("--rounds") + 1], 10)
                self.assertIn("--paced-live-probe", args)
                self.assertNotIn("--live-probe", args)
                self.assertEqual("--live-input-file" in args, mode == "peer")
        for mode in (workflow.LIVE_MODE, workflow.STREAM_MODE, workflow.TIMING_MODE):
            controller = workflow.SessionController(replace(self.run, test_mode=mode))
            args = controller._game_args("peer")
            self.assertEqual(args[args.index("--rounds") + 1], 240)
            self.assertNotIn("--paced-live-probe", args)

    def test_short_ready_state_accepts_and_confirms_real_input(self):
        self.run = replace(self.run, test_mode=workflow.PACED_LIVE_MODE)
        create(self.run.live_input_path, self.run.epoch, self.run.role)
        controller = self.controller()
        controller.start()
        self.lobby()
        self.host_ready()
        controller.poll()
        with self.assertRaises(ValueError):
            controller.submit_live({"op": "SET_PAUSED", "value": True})
        workflow.write_json(self.run_dir / "peer-progress.json", {"state": "running", "round": 10,
            "live": {"started": True, "completed": False, "confirmed_paused": False,
                     "acknowledged_seq": {"a": 0, "b": 0}}})
        self.assertEqual(controller.submit_live({"op": "SET_PAUSED", "value": True}), 1)
        self.assertIn("Noch 1 zur Bestätigung offen", workflow.live_input_status(controller.poll()))
        controller.submit_live({"op": "END_TEST"})
        self.assertFalse(workflow.live_input_ready(controller.poll()))
        self.assertFalse(self.run.stop_path.exists())

    def test_preparation_progress_uses_selected_round_limit(self):
        status = {"failure": "", "completed": False, "stopping": False,
                  "test_mode": workflow.PACED_LIVE_MODE,
                  "peer": {"state": "running", "round": 3}}
        self.assertIn("von 10", workflow.describe_status(status))
        status["test_mode"] = workflow.LIVE_MODE
        self.assertIn("von 240", workflow.describe_status(status))


if __name__ == "__main__":
    unittest.main()
