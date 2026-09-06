"""Private raw API diagnostics are copied as bytes, separate from sync snapshots."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from prototype.strict_sync import launcher_session as workflow


class BuildAuditExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.run_dir = self.root / "run"
        self.session = self.run_dir / "session"
        self.session.mkdir(parents=True)
        self.run = workflow.PreparedRun(
            str(self.run_dir), str(self.root / "game"), str(self.session),
            str(self.run_dir / "payload"), str(self.root / "imported.sav"),
            str(self.root / "backup"), "a", "127.0.0.1", "f" * 32, "a" * 64)
        assertion = patch.object(workflow, "current_game_assertion", return_value=None)
        assertion.start()
        self.addCleanup(assertion.stop)

    def export(self):
        destination = self.root / "report.zip"
        workflow.export_diagnostics(self.run, destination)
        return zipfile.ZipFile(destination)

    def test_raw_decimal_values_and_formatting_survive_unchanged(self):
        raw = (b'{\n  "completed": true, "valid_snapshot": false,\n'
               b'  "records": [{"path": "game.time.time", "value": 13.4},'
               b'{"path": "CONSTRUCTION.transf[13]", "value": -968.125}]\n}\n')
        (self.session / "lua_api_audit.json").write_bytes(raw)
        status = {"status": "halted", "diagnostics": {"failure": {
            "valid_snapshot": False, "api_audit": {"file": "lua_api_audit.json",
            "written": True, "valid_snapshot": False}}}}
        status_bytes = json.dumps(status).encode()
        (self.session / "lua_status.json").write_bytes(status_bytes)
        with self.export() as archive:
            self.assertEqual(archive.read("session/lua_api_audit.json"), raw)
            self.assertEqual(archive.read("session/lua_status.json"), status_bytes)
            exported_failure = json.loads(archive.read("session/lua_status.json"))["diagnostics"]["failure"]
            self.assertNotIn("records", exported_failure["api_audit"])
        self.assertEqual((self.session / "lua_api_audit.json").read_bytes(), raw)

    def test_only_fixed_session_filename_is_exported(self):
        (self.session / "lua_api_audit.json").write_bytes(b'{"records": []}')
        for directory in (self.run_dir, self.session):
            for name in ("lua_api_audit.json.part", "other_api_audit.json", "config.lua",
                         "session.key", "initial.sav", "initial.sav.lua"):
                (directory / name).write_bytes(b"excluded")
        (self.run_dir / "lua_api_audit.json").write_bytes(b"wrong location")
        with self.export() as archive:
            self.assertEqual(set(archive.namelist()), {"INFO.txt", "session/lua_api_audit.json"})
            self.assertEqual(archive.read("session/lua_api_audit.json"), b'{"records": []}')

    def test_absent_audit_does_not_block_ordinary_report(self):
        (self.run_dir / "peer-report.json").write_bytes(b'{"halted": true}')
        with self.export() as archive:
            self.assertEqual(set(archive.namelist()), {"INFO.txt", "peer-report.json"})

    def test_in_progress_audit_does_not_block_ordinary_report(self):
        audit = self.session / "lua_api_audit.json"
        audit.write_bytes(b"temporarily unavailable")
        (self.run_dir / "peer-report.json").write_bytes(b'{"halted": true}')
        shared_read = workflow._shared_read
        def read(path, limit):
            if path == audit:
                raise PermissionError("writer owns file")
            return shared_read(path, limit)
        with patch.object(workflow, "_shared_read", side_effect=read), self.export() as archive:
            self.assertEqual(set(archive.namelist()), {"INFO.txt", "peer-report.json"})


if __name__ == "__main__":
    unittest.main()
