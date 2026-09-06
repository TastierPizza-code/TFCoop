import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from coop.launch import LaunchLease, ProcessInfo, TrackedGame, process_info


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.exe = self.root / "TransportFever2.exe"
        self.bootstrap = Mock(pid=100)
        self.bootstrap.poll.return_value = None
        self.lease = Mock()
        self.now = 0
        self.processes = {100: ProcessInfo(100, 1000, str(self.exe))}
        self.tracker = TrackedGame(self.bootstrap, self.root, self.exe, self.lease, 999,
                                   inspect=self.processes.get, clock=lambda: self.now)

    def identity(self, pid):
        (self.root / "tpf2_instance.txt").write_text(f"a\npid={pid}\nport=7771\n")

    def test_steam_restart_keeps_connection_alive_and_tracks_replacement(self):
        self.identity(100)
        self.assertIsNone(self.tracker.poll())
        self.bootstrap.poll.return_value = 0
        del self.processes[100]
        self.now = 4
        self.assertIsNone(self.tracker.poll())
        self.processes[200] = ProcessInfo(200, 1100, str(self.exe))
        self.identity(200)
        self.assertIsNone(self.tracker.poll())
        self.assertEqual(self.tracker.pid, 200)
        self.lease.revoke.assert_called()
        self.now = 121
        self.assertIsNone(self.tracker.poll())
        del self.processes[200]
        self.assertEqual(self.tracker.poll(), 0)

    def test_wrong_executable_and_old_identity_cannot_adopt_process(self):
        self.bootstrap.poll.return_value = 0
        self.processes[200] = ProcessInfo(200, 1100, str(self.root / "different.exe"))
        self.identity(200)
        self.assertIsNone(self.tracker.poll())
        self.processes[200] = ProcessInfo(200, 500, str(self.exe))
        self.assertIsNone(self.tracker.poll())
        self.now = 121
        self.assertEqual(self.tracker.poll(), 1)
        self.assertTrue(self.tracker.startup_failed)

    def test_pid_reuse_after_real_game_exit_is_not_followed(self):
        self.processes[200] = ProcessInfo(200, 1100, str(self.exe))
        self.identity(200)
        self.tracker.poll()
        self.processes[200] = ProcessInfo(200, 1200, str(self.exe))
        self.assertEqual(self.tracker.poll(), 0)

    def test_direct_launch_is_confirmed_when_game_lua_reports(self):
        self.identity(100)
        (self.root / "lockstep_dash_a.txt").write_text("wall=1\n")
        self.assertIsNone(self.tracker.poll())
        self.assertEqual(self.tracker.actual.pid, 100)
        del self.processes[100]
        self.assertEqual(self.tracker.poll(), 0)

    def test_slow_loading_original_process_remains_running(self):
        self.identity(100)
        self.now = 300
        self.assertIsNone(self.tracker.poll())
        self.assertFalse(self.tracker.startup_failed)

    def test_ticket_is_atomic_bounded_and_revoke_preserves_newer_ticket(self):
        owner = ProcessInfo(123, 987654321, "launcher.exe")
        with patch("coop.launch.process_info", return_value=owner), patch("coop.launch.time.time", return_value=1000):
            first = LaunchLease.create(self.exe, self.root, lease_root=self.root)
            self.assertEqual(list(self.root.glob("*.tmp")), [])
            content = first.path.read_text()
            self.assertIn("expires=1120\n", content)
            self.assertIn("launcher_created=987654321\n", content)
            second = LaunchLease.create(self.exe, self.root, lease_root=self.root)
        first.revoke()
        self.assertTrue(second.path.exists())
        second.revoke()
        self.assertFalse(second.path.exists())

    def test_closing_launcher_during_start_cannot_orphan_game(self):
        from coop.app import App
        app = App.__new__(App)
        app.busy, app.process = True, None
        app.window, app.connection, app.pool = Mock(), Mock(), Mock()
        with patch("coop.app.messagebox.showinfo") as notice:
            app.close()
        notice.assert_called_once()
        app.window.destroy.assert_not_called()
        app.connection.disconnect.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows process identity API")
    def test_real_current_process_identity(self):
        info = process_info(os.getpid())
        self.assertIsNotNone(info)
        self.assertEqual(info.pid, os.getpid())
        self.assertGreater(info.created, 0)
        self.assertTrue(Path(info.executable).is_file())
        self.assertIsNone(process_info(0))


if __name__ == "__main__":
    unittest.main()
