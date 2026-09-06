"""Solo launcher transitions without Tcl, game processes, or real installations."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from prototype import launcher
from prototype.tests.test_update_startup import headless_app, Value


class DiagnosticLauncherTests(unittest.TestCase):
    def app(self):
        app = headless_app()
        app.busy = False
        app.last_run = None
        app.diagnostic_save = Value()
        app._save_settings = Mock()
        app.game.set("game fixture")
        app.saves.set("save fixture")
        return app

    def test_preparation_uses_only_solo_workflow_without_connection(self):
        app = self.app()
        app._work = Mock()
        app.prepare_diagnostic()
        job, done = app._work.call_args.args
        with patch.object(launcher.diagnostics, "prepare_diagnostic", return_value="run") as prepare, \
                patch.object(launcher.workflow, "prepare") as build, \
                patch.object(launcher.workflow, "SessionController") as controller:
            self.assertEqual(job(), "run")
        prepare.assert_called_once_with("game fixture", "save fixture")
        build.assert_not_called()
        controller.assert_not_called()
        self.assertEqual(done, app._diagnostic_prepared)

    def test_active_build_or_busy_disallows_solo_preparation(self):
        for state in ("busy", "prepared", "controller"):
            app = self.app()
            app._work = Mock()
            if state == "busy":
                app.busy = True
            elif state == "prepared":
                app.prepared = object()
            else:
                app.controller = Mock()
                app.controller.alive.return_value = True
            app.prepare_diagnostic()
            app._work.assert_not_called()

    def test_prepared_solo_locks_build_and_retains_old_build_report(self):
        app = self.app()
        old = app.last_run = object()
        run = SimpleNamespace(imported_save="TF2-API-Diagnose-fixture.sav", run_dir="fixture")
        app._diagnostic_prepared(run)
        self.assertIs(app.last_run, old)
        self.assertIs(app.diagnostic, run)
        self.assertIs(app.last_diagnostic, run)
        self.assertIsNone(app.controller)
        app.prepare_button.configure.assert_called_with(state="disabled")
        app.connect_button.configure.assert_called_with(state="disabled")
        app.diagnostic_export_button.configure.assert_called_with(state="normal")

    def poll(self, app, result):
        app.diagnostic = object()
        app.diagnostic_ticks = 2
        with patch.object(launcher.diagnostics, "read_diagnostic_report", return_value=result):
            app._poll_diagnostic()

    def test_waiting_is_distinct_from_completed_with_missing_fields(self):
        app = self.app()
        self.poll(app, None)
        self.assertFalse(app.diagnostic_finished)
        self.poll(app, {"status": "completed", "records": [{"access": "nil"}], "truncated": True})
        self.assertTrue(app.diagnostic_finished)
        self.assertIn("kein bestandener Synchronitätstest", app.diagnostic_status.get())
        self.assertIn("gekürzt", app.diagnostic_status.get())

    def test_error_report_does_not_claim_success(self):
        app = self.app()
        self.poll(app, {"status": "error", "records": []})
        self.assertIn("meldet einen Fehler", app.diagnostic_status.get())
        self.assertNotIn("Diagnosebericht vorhanden", app.diagnostic_status.get())

    def test_missing_report_gets_a_hint_and_late_report_still_arrives(self):
        app = self.app()
        app.diagnostic_started = 10
        with patch.object(launcher.time, "monotonic", return_value=71):
            self.poll(app, None)
        self.assertIn("Noch kein Diagnosebericht", app.diagnostic_status.get())
        self.assertFalse(app.diagnostic_finished)
        self.poll(app, {"status": "completed", "records": [], "truncated": False})
        self.assertTrue(app.diagnostic_finished)
        self.assertIn("Diagnosebericht vorhanden", app.diagnostic_status.get())

    def test_tampered_report_stops_polling_with_visible_error(self):
        app = self.app()
        app.diagnostic = object()
        app.diagnostic_ticks = 2
        with patch.object(launcher.diagnostics, "read_diagnostic_report", side_effect=ValueError("wrong request")):
            app._poll_diagnostic()
        self.assertTrue(app.diagnostic_finished)
        self.assertIn("wrong request", app.diagnostic_status.get())

    def test_installed_solo_refuses_build_even_after_launcher_restart(self):
        app = self.app()
        app.role, app.host, app.code = Value("a"), Value("127.0.0.1"), Value("fixture")
        app._work = Mock()
        app.prepare()
        job = app._work.call_args.args[0]
        with patch.object(launcher.diagnostics, "diagnostic_status", return_value={"installed": True}), \
                patch.object(launcher.workflow, "prepare") as build:
            with self.assertRaisesRegex(ValueError, "Diagnoseinstallation"):
                job()
        build.assert_not_called()

    def test_restore_does_not_touch_native_if_diagnostic_restore_conflicts(self):
        app = self.app()
        app._work = Mock()
        app.restore()
        job = app._work.call_args.args[0]
        with patch.object(launcher.diagnostics, "restore_diagnostic", side_effect=ValueError("modified file")), \
                patch.object(launcher.workflow, "restore_probe") as restore:
            with self.assertRaisesRegex(ValueError, "modified file"):
                job()
        restore.assert_not_called()


if __name__ == "__main__":
    unittest.main()
