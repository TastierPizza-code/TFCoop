"""Complete solo file handoff on a temporary fake game with real Lua execution."""
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from prototype import diagnostic_session as session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/lua/.deps"))
from lupa.lua54 import LuaRuntime


class LiteralDiagnosticHandoff(unittest.TestCase):
    def test_prepared_lua_config_report_export_and_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            game, saves, local = (root / name for name in ("game", "saves", "local"))
            for directory in (game, saves, local, game / "res"):
                directory.mkdir()
            (game / "TransportFever2.exe").write_bytes(b"inert fixture, never executed")
            (game / "alut.dll").write_bytes(b"inert prior audio fixture")
            original = root / "initial.sav"
            original.write_bytes(b"inert private save fixture")
            Path(str(original) + ".lua").write_text("return {}", encoding="utf-8")
            with patch.object(session.workflow, "local_root", return_value=local), \
                    patch.object(session.workflow, "resources", return_value=ROOT), \
                    patch.object(session.workflow, "baseline_save", return_value=original), \
                    patch.object(session.workflow, "restore_probe") as native_restore, \
                    patch.object(session.recovery, "_require_closed"), \
                    patch.object(session.recovery, "_guard", side_effect=lambda: nullcontext()):
                run = session.prepare_diagnostic(game, saves)
                native_restore.assert_called_once_with(game)
                self.assertIsNone(session.read_diagnostic_report(run))
                lua = LuaRuntime(unpack_returned_tuples=True)
                lua.execute((ROOT / "prototype/mod/tf2_api_audit_1/tests/fake_api.lua").read_text("utf-8"))
                scripts = Path(run.mod_dir) / "res/scripts/tf2_api_audit"
                modules = {"tf2_api_audit/" + name: lua.execute((scripts / (name + ".lua")).read_text("utf-8"))
                           for name in ("config", "json", "probe")}
                lua.globals().require = lambda name: modules[name]
                lua.execute((Path(run.mod_dir) / "res/config/game_script/tf2_api_audit.lua").read_text("utf-8"))
                script = lua.globals().data()
                script.update()
                report = session.read_diagnostic_report(session.load_diagnostic(run.directory))
                self.assertEqual(report["request_id"], run.request_id)
                self.assertEqual(report["status"], "completed")
                self.assertFalse(report["valid_snapshot"])
                self.assertGreater(len(report["records"]), 100)
                self.assertEqual(lua.globals().sent, 0)
                archive = session.export_diagnostic(run, root / "diagnose.zip")
                with zipfile.ZipFile(archive) as exported:
                    self.assertEqual(set(exported.namelist()), {"api-audit.json", "diagnostic-info.json"})
                    self.assertEqual(json.loads(exported.read("api-audit.json")), report)
                session.restore_diagnostic(game)
                self.assertFalse(session.diagnostic_status(game)["installed"])
                self.assertTrue(Path(run.imported_save).is_file())
                self.assertTrue(Path(run.report_path).is_file())
                self.assertEqual((game / "alut.dll").read_bytes(), b"inert prior audio fixture")
                self.assertEqual(original.read_bytes(), b"inert private save fixture")


if __name__ == "__main__":
    unittest.main()
