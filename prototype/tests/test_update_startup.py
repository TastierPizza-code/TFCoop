"""Headless startup/update integration. All process and GUI entry points are mocked."""
from pathlib import Path
import queue
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from coop.native import NativeError
from prototype import launcher
from prototype import update_startup as startup
from prototype.updater import UpdateResult


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def headless_app():
    """Exercise actual event handlers without constructing Tcl, Tk or a thread."""
    app = launcher.App.__new__(launcher.App)
    app.events = queue.Queue()
    app.root = Mock()
    app.busy = True
    app.prepared = app.controller = None
    app.diagnostic = app.last_diagnostic = None
    app.diagnostic_finished = False
    app.diagnostic_ticks = 0
    app.diagnostic_started = 0
    app.skip_update = app.closing_for_update = False
    app.baseline_ready = True
    for name in ("status", "update_status", "baseline_status", "game", "saves", "host", "diagnostic_status"):
        setattr(app, name, Value())
    for name in ("prepare_button", "connect_button", "restore_button", "stop_button", "addresses", "diagnostic_button", "diagnostic_export_button"):
        setattr(app, name, Mock())
    app.inputs = [Mock(), Mock()]
    app.last_live_status = {}
    app.live_buttons = [Mock(), Mock(), Mock()]
    app.live_status = Value()
    return app


class StartupGuardTests(unittest.TestCase):
    def test_game_running_short_circuits_mutex_probe(self):
        with patch.object(startup, "game_is_running", return_value=True), \
                patch.object(startup.ctypes, "WinDLL", create=True) as load:
            self.assertTrue(startup.session_active())
        load.assert_not_called()

    def test_named_controller_mutex_is_closed_and_blocks_handoff(self):
        kernel = Mock()
        kernel.OpenMutexW.return_value = 1234
        with patch.object(startup, "game_is_running", return_value=False), \
                patch.object(startup, "os", SimpleNamespace(name="nt")), \
                patch.object(startup.ctypes, "WinDLL", return_value=kernel, create=True):
            self.assertTrue(startup.session_active())
        kernel.OpenMutexW.assert_called_once_with(0x00100000, False, "Local\\TF2StrictProbeController")
        kernel.CloseHandle.assert_called_once_with(1234)

    def test_only_absent_mutex_allows_startup_on_windows(self):
        for error, expected in ((2, False), (5, True), (6, True), (0, True)):
            with self.subTest(error=error):
                kernel = Mock()
                kernel.OpenMutexW.return_value = None
                with patch.object(startup, "game_is_running", return_value=False), \
                        patch.object(startup, "os", SimpleNamespace(name="nt")), \
                        patch.object(startup.ctypes, "WinDLL", return_value=kernel, create=True), \
                        patch.object(startup.ctypes, "get_last_error", return_value=error, create=True):
                    self.assertIs(startup.session_active(), expected)
                kernel.CloseHandle.assert_not_called()

    def test_non_windows_inactive_game_needs_no_windows_api(self):
        with patch.object(startup, "game_is_running", return_value=False), \
                patch.object(startup, "os", SimpleNamespace(name="posix")), \
                patch.object(startup.ctypes, "WinDLL", create=True) as load:
            self.assertFalse(startup.session_active())
        load.assert_not_called()

    def test_verified_update_handoff_uses_exact_program_and_loop_break_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "TF2-Coop.exe"
            executable.write_bytes(b"fixture only, never executed")
            with patch.object(startup, "session_active", return_value=False) as active, \
                    patch.object(startup.subprocess, "Popen") as spawn:
                startup.handoff(executable)
            active.assert_called_once_with()
            args, options = spawn.call_args
            self.assertEqual(args, ([str(executable.resolve()), "--updated-launch"],))
            self.assertEqual(options["cwd"], executable.parent.resolve())
            for stream in ("stdin", "stdout", "stderr"):
                self.assertEqual(options[stream], startup.subprocess.DEVNULL)
            self.assertEqual(options["creationflags"],
                             startup.subprocess.CREATE_NO_WINDOW if startup.os.name == "nt" else 0)

    def test_handoff_rechecks_newly_active_session_before_spawning(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "TF2-Coop.exe"
            executable.write_bytes(b"fixture only")
            with patch.object(startup, "session_active", return_value=True), \
                    patch.object(startup.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "laufenden Test"):
                    startup.handoff(executable)
            spawn.assert_not_called()

    def test_handoff_rejects_wrong_name_directory_and_missing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            wrong = directory / "another.exe"
            wrong.write_bytes(b"fixture only")
            fake_executable = directory / "TF2-Coop.exe"
            fake_executable.mkdir()
            for path in (wrong, fake_executable, directory / "missing" / "TF2-Coop.exe"):
                with self.subTest(path=path), patch.object(startup, "session_active") as active, \
                        patch.object(startup.subprocess, "Popen") as spawn:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        startup.handoff(path)
                    active.assert_not_called()
                    spawn.assert_not_called()


class LauncherUpdateIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Any accidental UI construction during these tests is a hard failure.
        guard = patch.object(launcher.tk, "Tk", side_effect=AssertionError("Tk must not be created"))
        guard.start()
        self.addCleanup(guard.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.baseline = self.directory / "initial.sav"
        self.baseline.write_bytes(b"local baseline fixture")
        Path(str(self.baseline) + ".lua").write_text("fixture", encoding="utf-8")

    def discover(self, app, *, frozen, updater):
        with patch.object(launcher.sys, "frozen", frozen, create=True), \
                patch("prototype.updater.check_for_update", updater), \
                patch.object(launcher.workflow, "package_directory", return_value=self.directory / "package"), \
                patch.object(launcher.workflow, "local_root", return_value=self.directory / "local"), \
                patch.object(launcher.workflow, "baseline_save", return_value=self.baseline), \
                patch.object(launcher.workflow, "save_directories", return_value=["save-fixture"]), \
                patch.object(launcher.workflow, "suggested_addresses", return_value=["127.0.0.1"]), \
                patch.object(launcher, "discover_game", return_value="game-fixture"):
            return app._discover()

    def test_frozen_startup_passes_active_guard_and_delivers_progress_via_queue(self):
        app = headless_app()
        update = UpdateResult(None, "fixture current", "v5.2.0")
        def check(package, cache, *, progress, active_check):
            self.assertEqual(package, self.directory / "package")
            self.assertEqual(cache, self.directory / "local" / "updates")
            self.assertIs(active_check, startup.session_active)
            progress("fixture download")
            return update
        updater = Mock(side_effect=check)
        result = self.discover(app, frozen=True, updater=updater)
        updater.assert_called_once()
        self.assertEqual(result, ("game-fixture", ["save-fixture"], ["127.0.0.1"], update, ""))
        self.assertEqual(app.update_status.get(), "")  # Worker did not touch a Tk variable.
        callback, value, error = app.events.get_nowait()
        self.assertEqual(callback, app._update_progress)
        self.assertEqual((value, error), ("fixture download", None))

    def test_development_and_updated_launch_bypass_network_check(self):
        for frozen, skip in ((False, False), (False, True), (True, True)):
            with self.subTest(frozen=frozen, skip=skip):
                app = headless_app()
                app.skip_update = skip
                updater = Mock(side_effect=AssertionError("unexpected network update"))
                result = self.discover(app, frozen=frozen, updater=updater)
                updater.assert_not_called()
                self.assertIsNone(result[3])

    def test_progress_event_keeps_prepare_locked_until_discovery_finishes(self):
        app = headless_app()
        app._buttons()
        app.events.put((app._update_progress, "Downloading fixture…", None))
        app.events.put((app._update_progress, "Checking fixture…", None))
        app.tick()
        self.assertTrue(app.busy)
        self.assertEqual(app.update_status.get(), "Checking fixture…")
        app.prepare_button.configure.assert_called_once_with(state="disabled")
        for widget in app.inputs:
            widget.configure.assert_called_once_with(state="disabled")
        app.root.after.assert_called_once_with(400, app.tick)
        app.events.put((app._discovered, (None, [], [], None, ""), None))
        app.tick()
        self.assertFalse(app.busy)
        app.prepare_button.configure.assert_called_with(state="normal")

    def test_successful_handoff_closes_old_launcher_without_rescheduling_tick(self):
        app = headless_app()
        update = UpdateResult(self.directory / "TF2-Coop.exe", "fixture ready", "v5.2.0")
        app.events.put((app._discovered, (None, [], [], update, ""), None))
        with patch.object(startup, "handoff") as handoff:
            app.tick()
        handoff.assert_called_once_with(update.executable)
        self.assertTrue(app.closing_for_update)
        app.root.destroy.assert_called_once_with()
        app.root.after.assert_not_called()
        app.prepare_button.configure.assert_not_called()

    def test_handoff_failure_retains_old_launcher_and_restores_controls(self):
        for failure in (ValueError("fixture active test"), OSError("fixture spawn failed"),
                        NativeError("fixture process inspection failed")):
            with self.subTest(failure=failure):
                app = headless_app()
                update = UpdateResult(self.directory / "TF2-Coop.exe", "fixture ready", "v5.2.0")
                app.events.put((app._discovered, (None, [], [], update, ""), None))
                with patch.object(startup, "handoff", side_effect=failure):
                    app.tick()
                self.assertFalse(app.closing_for_update)
                self.assertFalse(app.busy)
                app.root.destroy.assert_not_called()
                app.root.after.assert_called_once_with(400, app.tick)
                self.assertIn("bisherige Version bleibt geöffnet", app.update_status.get())
                self.assertIn(str(failure), app.update_status.get())
                app.prepare_button.configure.assert_called_with(state="normal")

    def test_missing_baseline_remains_locked_when_no_update_is_available(self):
        app = headless_app()
        app.events.put((app._discovered,
                        (None, [], [], UpdateResult(None, "fixture current"), "fixture missing save"), None))
        app.tick()
        self.assertFalse(app.baseline_ready)
        app.prepare_button.configure.assert_called_with(state="disabled")
        self.assertEqual(app.baseline_status.get(), "fixture missing save")


if __name__ == "__main__":
    unittest.main()
