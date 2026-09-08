"""Lobby owns its lifetime before game startup; installers/updates observe it."""
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from prototype.strict_sync import session_guard as guard, probe_install as install
from prototype import update_startup as startup


class LobbyGuardTests(unittest.TestCase):
    def test_duplicate_guard_closes_only_new_handle_and_never_allows_entry(self):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 10
        with patch.object(guard.os, "name", "nt"), patch.object(guard, "_kernel", return_value=kernel), \
             patch.object(guard.ctypes, "get_last_error", return_value=183, create=True), \
             patch.object(guard, "named_mutex_active") as active:
            with self.assertRaisesRegex(ValueError, "wartet bereits"):
                guard.LobbyGuard()
        active.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(10)

    def test_existing_game_or_installer_rejects_lobby_and_releases_presence(self):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 10
        with patch.object(guard.os, "name", "nt"), patch.object(guard, "_kernel", return_value=kernel), \
             patch.object(guard.ctypes, "get_last_error", return_value=0, create=True), \
             patch.object(guard, "named_mutex_active", return_value=True) as active:
            with self.assertRaisesRegex(ValueError, "Installation"):
                guard.LobbyGuard()
        active.assert_called_once_with(guard.CONTROLLER_MUTEX)
        kernel.CloseHandle.assert_called_once_with(10)

    def test_lobby_presence_does_not_use_game_mutex_and_context_releases_on_failure(self):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 10
        with patch.object(guard.os, "name", "nt"), patch.object(guard, "_kernel", return_value=kernel), \
             patch.object(guard.ctypes, "get_last_error", return_value=0, create=True), \
             patch.object(guard, "named_mutex_active", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "fixture disconnect"):
                with guard.LobbyGuard():
                    raise RuntimeError("fixture disconnect")
        kernel.CreateMutexW.assert_called_once_with(None, False, guard.LOBBY_MUTEX)
        kernel.CloseHandle.assert_called_once_with(10)

    def test_presence_query_is_fail_closed_and_closes_found_handles(self):
        kernel = Mock()
        with patch.object(guard.os, "name", "nt"), patch.object(guard, "_kernel", return_value=kernel):
            kernel.OpenMutexW.return_value = 12
            self.assertTrue(guard.named_mutex_active("fixture"))
            kernel.CloseHandle.assert_called_once_with(12)
            kernel.OpenMutexW.return_value = None
            for error, active in ((2, False), (5, True), (6, True), (0, True)):
                with patch.object(guard.ctypes, "get_last_error", return_value=error, create=True):
                    self.assertEqual(guard.named_mutex_active("fixture"), active)

    def test_installer_holds_controller_before_reading_lobby_and_releases_after_rejection(self):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 10
        def occupied():
            kernel.CreateMutexW.assert_called_once_with(None, False, guard.CONTROLLER_MUTEX)
            return True
        with patch.object(install, "os", SimpleNamespace(name="nt")), \
             patch.object(install.ctypes, "WinDLL", return_value=kernel, create=True), \
             patch.object(install.ctypes, "get_last_error", return_value=0, create=True), \
             patch.object(install, "lobby_active", side_effect=occupied), \
             patch.object(install, "_require_closed") as closed:
            with self.assertRaisesRegex(install.ProbeInstallError, "Mitspieler"):
                with install._guard():
                    self.fail("installer must not enter while lobby is waiting")
        closed.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(10)
        self.assertTrue(install._LOCAL_LOCK.acquire(blocking=False))
        install._LOCAL_LOCK.release()

    def test_waiting_lobby_blocks_update_even_without_game_controller(self):
        kernel = Mock()
        kernel.OpenMutexW.return_value = None
        with patch.object(startup, "game_is_running", return_value=False), \
             patch.object(startup, "os", SimpleNamespace(name="nt")), \
             patch.object(startup.ctypes, "WinDLL", return_value=kernel, create=True), \
             patch.object(startup.ctypes, "get_last_error", return_value=2, create=True), \
             patch.object(startup, "lobby_active", return_value=True) as active:
            self.assertTrue(startup.session_active())
            with tempfile.TemporaryDirectory() as temporary:
                executable = Path(temporary) / "TF2-Coop.exe"
                executable.write_bytes(b"fixture only")
                with patch.object(startup.subprocess, "Popen") as spawn:
                    with self.assertRaisesRegex(ValueError, "laufenden Test"):
                        startup.handoff(executable)
                spawn.assert_not_called()
        self.assertEqual(active.call_count, 2)

    @unittest.skipUnless(os.name == "nt", "actual Windows named mutex semantics")
    def test_real_os_presence_is_exclusive_and_disappears_after_last_owner_closes(self):
        # Dedicated names cannot affect an actual launcher or another test suite.
        suffix = uuid.uuid4().hex
        name = "Local\\TFCoopHeadlessLobbyTest-" + suffix
        controller = "Local\\TFCoopHeadlessControllerTest-" + suffix
        self.assertFalse(guard.named_mutex_active(name))
        with guard.LobbyGuard(name=name, controller_name=controller):
            self.assertTrue(guard.named_mutex_active(name))
            self.assertFalse(guard.named_mutex_active(controller))
            with self.assertRaises(ValueError):
                guard.LobbyGuard(name=name, controller_name=controller)
            self.assertTrue(guard.named_mutex_active(name))
        self.assertFalse(guard.named_mutex_active(name))
        with guard.LobbyGuard(name=name, controller_name=controller):
            self.assertTrue(guard.named_mutex_active(name))
        self.assertFalse(guard.named_mutex_active(name))


if __name__ == "__main__":
    unittest.main()
