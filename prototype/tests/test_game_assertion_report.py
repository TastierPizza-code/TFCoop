"""A fatal TF2 assertion can leave a live, unresponsive process behind."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

from prototype.strict_sync.launcher_session import PreparedRun, SessionController, current_game_assertion, export_diagnostics


class AssertionReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = self.root / "run/session"
        self.session.mkdir(parents=True)
        self.marker = self.session / "controller_started.json"
        self.marker.write_text('{"consumed":true}')
        os.utime(self.marker, (1000, 1000))
        self.log = self.root / "local/crash_dump/stdout.txt"
        self.log.parent.mkdir(parents=True)
        self.run = PreparedRun(str(self.root / "run"), str(self.root / "game"), str(self.session),
                               str(self.root / "payload"), str(self.root / "local/save/test.sav"),
                               str(self.root / "backup"), "a", "127.0.0.1", "epoch", "a" * 64)
        self.assertion = "EmissionMap.cpp:428: EmissionMap::Update: Assertion `dt >= .2f' failed."

    def test_current_fatal_assertion_stops_even_if_process_is_still_alive(self):
        self.log.write_text("normal loading\n" + self.assertion + "\n")
        controller = SessionController(self.run)
        controller.started = True
        controller.children["peer"] = Mock(poll=Mock(return_value=None))
        result = controller.poll()
        self.assertTrue(result["stopping"])
        self.assertTrue(result["alive"])
        self.assertIn("dt >= .2f", result["failure"])
        self.assertTrue(self.run.stop_path.exists())

    def test_previous_launch_assertion_is_not_used_for_new_attempt(self):
        self.log.write_text(self.assertion)
        os.utime(self.log, (999, 999))
        self.assertIsNone(current_game_assertion(self.run))
        os.utime(self.log, (1001, 1001))
        self.assertEqual(current_game_assertion(self.run), self.assertion)

    def test_loading_hang_warning_alone_is_not_a_fatal_assertion(self):
        self.log.write_text("Thread did not respond to ping. Possible hang detected!\n")
        self.assertIsNone(current_game_assertion(self.run))

    def test_export_contains_assertion_only_not_full_game_log(self):
        self.log.write_text("private unrelated line\n" + self.assertion + "\n")
        archive = self.root / "report.zip"
        export_diagnostics(self.run, archive)
        with zipfile.ZipFile(archive) as result:
            self.assertEqual(result.read("game-assertion.txt").decode(), self.assertion + "\n")
            self.assertNotIn("stdout.txt", result.namelist())
            self.assertNotIn("private unrelated", result.read("game-assertion.txt").decode())


if __name__ == "__main__":
    unittest.main()
