"""Worker dispatch and logging checks; default Tk launcher is never opened."""
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import probe_launcher


class ProbeEntryTests(unittest.TestCase):
    def test_model_worker_uses_args_without_opening_launcher(self):
        original = list(sys.argv)
        observed = []
        def model():
            observed.append(list(sys.argv[1:]))
            print("headless model worker")
            return 7
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "worker.log"
            with patch("prototype.strict_sync.runner.main", model), patch.dict(sys.modules, {"prototype.launcher": None}):
                result = probe_launcher.main(["--worker-log", str(log), "--worker", "model", "peer", "--peer", "a"])
            self.assertEqual(result, 7)
            self.assertEqual(observed, [["peer", "--peer", "a"]])
            self.assertIn("headless model worker", log.read_text("utf-8"))
        self.assertEqual(sys.argv, original)

    def test_windowed_worker_exception_reaches_log_before_streams_restore(self):
        def fail():
            raise RuntimeError("intentional preflight failure")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "worker.log"
            with patch("prototype.strict_sync.game_runner.main", fail):
                with self.assertRaisesRegex(RuntimeError, "intentional"):
                    probe_launcher.main(["--worker-log", str(log), "--worker", "game", "peer"])
            self.assertIn("RuntimeError: intentional preflight failure", log.read_text("utf-8"))

    def test_lobby_worker_is_explicitly_dispatched(self):
        with patch("prototype.strict_sync.lobby.main", return_value=0) as worker:
            self.assertEqual(probe_launcher.main(["--worker", "lobby", "--role", "b"]), 0)
        worker.assert_called_once_with()

    def test_all_worker_modes_bypass_updater_and_gui_imports(self):
        for mode, module in (("game", "game_runner"), ("model", "runner"), ("lobby", "lobby")):
            with self.subTest(mode=mode):
                with patch("prototype.strict_sync." + module + ".main", return_value=0) as worker, \
                        patch.dict(sys.modules, {"prototype.launcher": None,
                                                 "prototype.updater": None,
                                                 "prototype.update_startup": None}):
                    self.assertEqual(probe_launcher.main(["--worker", mode, "fixture-worker-arg"]), 0)
                worker.assert_called_once_with()

    def test_self_check_dispatch_bypasses_updater_and_gui_imports(self):
        with patch.object(probe_launcher, "self_check", return_value=2) as check, \
                patch.dict(sys.modules, {"prototype.launcher": None,
                                         "prototype.updater": None,
                                         "prototype.update_startup": None}):
            self.assertEqual(probe_launcher.main(["--self-check", "fixture-report.json"]), 2)
        check.assert_called_once_with(Path("fixture-report.json"))

    def test_updated_launcher_flag_breaks_update_loop_only_for_exact_gui_dispatch(self):
        for arguments, skip in (([], False), (["--updated-launch"], True)):
            with self.subTest(arguments=arguments):
                launch = Mock(return_value=0)
                with patch.dict(sys.modules, {"prototype.launcher": SimpleNamespace(main=launch)}):
                    self.assertEqual(probe_launcher.main(arguments), 0)
                launch.assert_called_once_with(skip_update=skip)
        launch = Mock()
        with patch.dict(sys.modules, {"prototype.launcher": SimpleNamespace(main=launch)}):
            with self.assertRaisesRegex(ValueError, "unknown launcher arguments"):
                probe_launcher.main(["--updated-launch", "unexpected"])
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
