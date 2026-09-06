import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from coop.bridge import Mailbox, MAX_BYTES, MAX_PREVIEW_POINTS


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.mailbox = Mailbox(self.directory)

    def game(self, value):
        (self.directory / "game.json").write_text(json.dumps(value), encoding="utf-8")

    def peers(self):
        return {"connected": True, "local_peer_id": "host", "peers": [
            {"id": "friend", "name": "Jörg", "color": "#1aBCef", "presence": {
                "cursor": [1, 2.5, 3], "preview": {"kind": "street", "points": [[1, 2, 3], [4, 5, 6]]}}}]}

    def test_reads_fresh_snapshot_and_telemetry(self):
        value = {"protocol": 1, "cursor": [1, 2, 3], "preview": None,
                 "capabilities": {"cursor": True}, "status": "Ready", "telemetry": {"money": 300}}
        self.game(value)
        self.assertEqual(self.mailbox.read_game(), value)
        self.assertIsNone(self.mailbox.last_error)

    def test_missing_and_stale_snapshots_are_diagnostic(self):
        self.assertIsNone(self.mailbox.read_game())
        self.assertIn("Cannot read", self.mailbox.last_error)
        self.game({"protocol": 1, "cursor": None, "preview": None})
        old = time.time() - 4
        os.utime(self.directory / "game.json", (old, old))
        self.assertIsNone(self.mailbox.read_game())
        self.assertIn("stale", self.mailbox.last_error)

    def test_rejects_corrupt_duplicate_nonfinite_and_oversized_json(self):
        for raw in ('{', '{"protocol":1,"protocol":1}', '{"protocol":true}',
                    '{"protocol":1,"cursor":[NaN,0,0]}',
                    '{"protocol":1,"telemetry":{"money":1e400}}',
                    '{"protocol":1,"cursor":[true,0,0]}',
                    '{"protocol":1,"padding":"' + 'a' * MAX_BYTES + '"}'):
            with self.subTest(raw=raw[:70]):
                (self.directory / "game.json").write_text(raw, encoding="utf-8")
                self.assertIsNone(self.mailbox.read_game())
                self.assertIsNotNone(self.mailbox.last_error)

    def test_rejects_bad_previews(self):
        for preview in ({"kind": "execute", "points": []}, {"kind": "street", "points": [[1, 2]]},
                        {"kind": "street", "points": [[1, 2, 3]] * (MAX_PREVIEW_POINTS + 1)}):
            self.game({"protocol": 1, "preview": preview})
            self.assertIsNone(self.mailbox.read_game())

    def test_writes_utf8_stamped_snapshot(self):
        self.assertTrue(self.mailbox.write_peers(self.peers()))
        value = json.loads((self.directory / "peers.json").read_text(encoding="utf-8"))
        self.assertEqual(value["protocol"], 1)
        self.assertEqual(value["peers"][0]["name"], "Jörg")
        self.assertAlmostEqual(value["written_at"], time.time(), delta=2)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_retries_windows_sharing_failure(self):
        actual_replace = os.replace
        attempts = []
        def replace(src, dst):
            attempts.append(1)
            if len(attempts) < 3:
                raise PermissionError("temporarily open")
            actual_replace(src, dst)
        with patch("coop.bridge.os.replace", side_effect=replace), patch("coop.bridge.time.sleep"):
            self.assertTrue(self.mailbox.write_peers(self.peers()))
        self.assertEqual(len(attempts), 3)

    def test_write_failure_preserves_previous_snapshot_and_cleans_stage(self):
        self.assertTrue(self.mailbox.write_peers(self.peers()))
        before = (self.directory / "peers.json").read_bytes()
        with patch("coop.bridge.os.replace", side_effect=PermissionError("locked")), patch("coop.bridge.time.sleep"):
            self.assertFalse(self.mailbox.write_peers(self.peers()))
        self.assertIn("locked", self.mailbox.last_error)
        self.assertEqual((self.directory / "peers.json").read_bytes(), before)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_invalid_peer_cannot_replace_existing_data(self):
        snapshot = self.peers()
        self.assertTrue(self.mailbox.write_peers(snapshot))
        before = (self.directory / "peers.json").read_bytes()
        snapshot["peers"][0]["color"] = "red; dofile('x')"
        self.assertFalse(self.mailbox.write_peers(snapshot))
        self.assertEqual((self.directory / "peers.json").read_bytes(), before)

    def test_oversized_write_is_rejected(self):
        snapshot = self.peers()
        snapshot["extra"] = "a" * MAX_BYTES
        self.assertFalse(self.mailbox.write_peers(snapshot))
        self.assertIn("64 KiB", self.mailbox.last_error)


if __name__ == "__main__":
    unittest.main()
