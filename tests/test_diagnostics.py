from pathlib import Path
import tempfile
import unittest
from coop.diagnostics import read_status


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        (self.path / "tpf2_instance.txt").write_text("a\npid=123\nport=7771\n")

    def dashboard(self, extra="", wall=100):
        (self.path / "lockstep_dash_a.txt").write_text(f"wall={wall}\npeers=b:20:0:SYNC\ncomparison_wall=100\ncomparison_match=yes\n" + extra)

    def test_seed_identity_is_not_readiness(self):
        (self.path / "tpf2_instance.txt").write_text("a\n")
        self.assertFalse(read_status(self.path, "host", 123, 100)["ready"])

    def test_wrong_bound_port_is_actionable(self):
        (self.path / "tpf2_instance.txt").write_text("a\npid=123\nport=7781\n")
        self.assertEqual(read_status(self.path, "host", 123, 100)["level"], "error")

    def test_world_match_does_not_conceal_money_gap(self):
        self.dashboard("money_gap=b:100:0\nmoney_gap_wall=b:100\n")
        report = read_status(self.path, "host", 123, 100)
        self.assertEqual(report["level"], "error")
        self.assertIn("FIRMENKASSE", report["text"])

    def test_zero_gap_is_distinct_from_missing_account_data(self):
        self.dashboard("money_gap=b:0:0\nmoney_gap_wall=b:100\n")
        self.assertIn("Firmenkasse gleich", read_status(self.path, "host", 123, 100)["text"])
        self.dashboard()
        self.assertIn("noch nicht", read_status(self.path, "host", 123, 100)["text"])
        self.dashboard("money_gap=b:-:-\nmoney_gap_wall=b:-\n")
        self.assertIn("noch nicht", read_status(self.path, "host", 123, 100)["text"])

    def test_stale_dashboard_never_reports_sync(self):
        self.dashboard(wall=10)
        self.assertNotEqual(read_status(self.path, "host", 123, 100)["level"], "info")

    def test_stale_or_missing_comparison_never_reports_sync(self):
        self.dashboard("comparison_wall=-\n")
        self.assertNotEqual(read_status(self.path, "host", 123, 100)["level"], "info")

    def test_pause_does_not_erase_last_world_divergence(self):
        self.dashboard("comparison_match=no\n", wall=200)
        report = read_status(self.path, "host", 123, 200)
        self.assertEqual(report["level"], "error")
        self.assertIn("WELT ABGEWICHEN", report["text"])

    def test_old_money_mismatch_stays_unresolved_until_new_measurement(self):
        self.dashboard("money_gap=b:1890:0\nmoney_gap_wall=b:100\n", wall=200)
        self.assertEqual(read_status(self.path, "host", 123, 200)["level"], "error")
        self.dashboard("money_gap=b:0:0\nmoney_gap_wall=b:200\ncomparison_wall=200\n", wall=200)
        self.assertEqual(read_status(self.path, "host", 123, 200)["level"], "info")

    def test_matching_geometry_after_late_command_does_not_imply_good_sync(self):
        self.dashboard("applylate=59\n")
        report = read_status(self.path, "host", 123, 100)
        self.assertEqual(report["level"], "warning")
        self.assertIn("59", report["text"])
