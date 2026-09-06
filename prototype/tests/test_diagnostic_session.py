"""All diagnostic workflow fixtures live in a temp directory; no game is used."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from prototype import diagnostic_session as diagnostic


class DiagnosticSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.game, self.saves = self.root / "game", self.root / "save"
        self.local, self.source = self.root / "local", self.root / "source"
        for folder in (self.game, self.saves, self.local, self.source):
            folder.mkdir()
        (self.game / "res").mkdir()
        (self.game / "TransportFever2.exe").write_bytes(b"fixture executable; never run")
        (self.game / "alut.dll").write_bytes(b"previous audio bytes")
        (self.game / "other.dll").write_bytes(b"unrelated native bytes")
        self.baseline = self.root / "private/initial.sav"
        self.baseline.parent.mkdir()
        self.baseline.write_bytes(b"private same baseline")
        Path(str(self.baseline) + ".lua").write_bytes(b"return {name='private fixture'}\n")
        self.mod_source = self.source / "prototype/mod" / diagnostic.MOD
        for relative in diagnostic.REQUIRED_FILES:
            path = self.mod_source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("-- fixture " + relative + "\nreturn {}\n", encoding="utf-8")
        proxy = self.source / "prototype/native/out/probe_alut.dll"
        proxy.parent.mkdir(parents=True)
        proxy.write_bytes(b"strict proxy fixture")
        self.last_run_bytes = b'{"last_run":"keep existing normal test", "untouched": true}\n'
        (self.local / "launcher.json").write_bytes(self.last_run_bytes)
        self.patches = []
        for obj, name, value in (
            (diagnostic.workflow, "resources", self.source),
            (diagnostic.workflow, "local_root", self.local),
            (diagnostic.workflow, "baseline_save", self.baseline),
            (diagnostic.recovery.native, "game_is_running", False),
        ):
            mocked = patch.object(obj, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)

        @contextmanager
        def fake_guard():
            diagnostic.recovery._require_closed()
            yield

        guard = patch.object(diagnostic.recovery, "_guard", fake_guard)
        guard.start()
        self.addCleanup(guard.stop)

    def prepare(self, **kwargs):
        return diagnostic.prepare_diagnostic(self.game, self.saves, **kwargs)

    def mod_files(self):
        target = self.game / "mods" / diagnostic.MOD
        return {p.relative_to(target).as_posix(): p.read_bytes()
                for p in target.rglob("*") if p.is_file()} if target.exists() else {}

    def report(self, run, **changes):
        value = {"format": 1, "mode": diagnostic.MODE, "request_id": run.request_id,
                 "status": "completed", "valid_snapshot": False, "records": [],
                 "limits": {"max_bytes": diagnostic.MAX_REPORT_BYTES}, "truncated": False}
        value.update(changes)
        Path(run.report_path).write_text(json.dumps(value), encoding="utf-8")
        return value

    def native_install(self):
        request = "a" * 32
        state = self.game / diagnostic.recovery.STATE_DIR
        backup = state / "runs" / request
        original = backup / "original/alut.dll"
        original.parent.mkdir(parents=True)
        original.write_bytes((self.game / "alut.dll").read_bytes())
        deployed = (self.source / "prototype/native/out/probe_alut.dll").read_bytes()
        (self.game / "alut.dll").write_bytes(deployed)
        journal = {"owner": diagnostic.recovery.OWNER, "format": 1, "run_id": request,
                   "game_dir": str(self.game), "state": "installed", "created_dirs": [],
                   "files": [{"path": "alut.dll", "original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                              "deployed_sha256": hashlib.sha256(deployed).hexdigest()}]}
        (backup / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
        (state / "current.json").write_text(json.dumps({"owner": diagnostic.recovery.OWNER, "run_id": request}), encoding="utf-8")
        return backup

    def test_prepare_creates_only_lua_mod_fresh_pair_and_separate_run(self):
        messages = []
        run = self.prepare(on_progress=messages.append)
        self.assertRegex(run.request_id, r"^[0-9a-f]{32}$")
        self.assertEqual(run.directory, self.local / "diagnostics" / run.request_id)
        self.assertEqual(Path(run.imported_save).read_bytes(), self.baseline.read_bytes())
        self.assertEqual(Path(run.imported_save + ".lua").read_bytes(), Path(str(self.baseline) + ".lua").read_bytes())
        self.assertEqual(Path(run.imported_save).name, "TF2-API-Diagnose-" + run.request_id + ".sav")
        self.assertEqual(set(self.mod_files()), diagnostic.REQUIRED_FILES)
        config = self.mod_files()[diagnostic.CONFIG].decode("utf-8")
        self.assertIn("enabled = true", config)
        self.assertIn(run.request_id, config)
        self.assertIn(Path(run.report_path).as_posix(), config)
        self.assertNotIn("native", config.lower())
        self.assertEqual((self.game / "alut.dll").read_bytes(), b"previous audio bytes")
        self.assertEqual((self.game / "other.dll").read_bytes(), b"unrelated native bytes")
        self.assertEqual((self.local / "launcher.json").read_bytes(), self.last_run_bytes)
        self.assertFalse(Path(run.report_path).exists())
        self.assertFalse(list(self.local.rglob("launch.cfg")))
        self.assertFalse(list(self.local.rglob("session.key")))
        self.assertTrue(messages)

    def test_native_restore_uses_existing_recovery_and_preserves_old_alpha_proxy(self):
        native_backup = self.native_install()
        with patch.object(diagnostic.workflow, "restore_probe", wraps=diagnostic.recovery.restore_probe) as restore:
            self.prepare()
        restore.assert_called_once_with(self.game)
        self.assertEqual((self.game / "alut.dll").read_bytes(), b"previous audio bytes")
        self.assertEqual(json.loads((native_backup / "journal.json").read_text("utf-8"))["state"], "restored")
        self.assertTrue(native_backup.exists())

    def test_native_restore_conflict_prevents_diagnostic_install(self):
        self.native_install()
        (self.game / "alut.dll").write_bytes(b"later native user modification")
        with self.assertRaises(diagnostic.DiagnosticError):
            self.prepare()
        self.assertFalse((self.local / "diagnostics").exists())
        self.assertFalse((self.game / "mods" / diagnostic.MOD).exists())
        self.assertEqual((self.game / "alut.dll").read_bytes(), b"later native user modification")

    def test_orphaned_known_strict_proxy_is_rejected_without_native_replacement(self):
        proxy = (self.source / "prototype/native/out/probe_alut.dll").read_bytes()
        (self.game / "alut.dll").write_bytes(proxy)
        with self.assertRaisesRegex(diagnostic.DiagnosticError, "Strict-Test-Proxy"):
            self.prepare()
        self.assertEqual((self.game / "alut.dll").read_bytes(), proxy)
        self.assertFalse((self.local / "diagnostics").exists())

    def test_game_running_prevents_all_preparation_writes(self):
        with patch.object(diagnostic.recovery.native, "game_is_running", return_value=True):
            with self.assertRaises(diagnostic.DiagnosticError):
                self.prepare()
        self.assertEqual(list(self.saves.iterdir()), [])
        self.assertFalse((self.game / diagnostic.STATE_DIR).exists())
        self.assertFalse((self.local / "diagnostics").exists())

    def test_controller_guard_refusal_prevents_preparation(self):
        with patch.object(diagnostic.recovery, "_guard", side_effect=diagnostic.recovery.ProbeInstallError("Messcontroller aktiv")):
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "Messcontroller"):
                self.prepare()
        self.assertFalse((self.game / diagnostic.STATE_DIR).exists())

    def test_missing_source_or_baseline_sidecar_prevents_native_restore(self):
        (self.mod_source / "mod.lua").unlink()
        with patch.object(diagnostic.workflow, "restore_probe") as restore:
            with self.assertRaises(diagnostic.DiagnosticError):
                self.prepare()
            restore.assert_not_called()
        (self.mod_source / "mod.lua").write_text("return {}", encoding="utf-8")
        Path(str(self.baseline) + ".lua").unlink()
        with patch.object(diagnostic.workflow, "restore_probe") as restore:
            with self.assertRaises(diagnostic.DiagnosticError):
                self.prepare()
            restore.assert_not_called()

    def test_saves_cannot_be_inside_game(self):
        inside = self.game / "save"
        inside.mkdir()
        with self.assertRaisesRegex(diagnostic.DiagnosticError, "getrennt"):
            diagnostic.prepare_diagnostic(self.game, inside)

    def test_known_existing_mod_files_are_backed_up_and_restored_including_empty_files(self):
        old = self.game / "mods" / diagnostic.MOD
        old.mkdir(parents=True)
        (old / "mod.lua").write_bytes(b"original existing mod bytes")
        config = old / diagnostic.CONFIG
        config.parent.mkdir(parents=True)
        config.write_bytes(b"")
        before = self.mod_files()
        run = self.prepare()
        status = diagnostic.diagnostic_status(self.game)
        self.assertTrue(status["installed"])
        self.assertTrue(status["restorable"])
        self.assertEqual(status["request_id"], run.request_id)
        self.assertEqual((Path(run.backup_path) / "original/mods" / diagnostic.MOD / "mod.lua").read_bytes(), before["mod.lua"])
        self.assertTrue(diagnostic.restore_diagnostic(self.game)["restored"])
        self.assertEqual(self.mod_files(), before)
        self.assertFalse(diagnostic.diagnostic_status(self.game)["installed"])
        self.assertTrue(Path(run.imported_save).exists())
        self.assertTrue(Path(run.backup_path).exists())

    def test_unknown_extra_mod_files_are_preserved_and_preparation_refused(self):
        old = self.game / "mods" / diagnostic.MOD
        old.mkdir(parents=True)
        (old / "notes.txt").write_bytes(b"personal note")
        with self.assertRaisesRegex(diagnostic.DiagnosticError, "fremde Dateien"):
            self.prepare()
        self.assertEqual((old / "notes.txt").read_bytes(), b"personal note")

    def test_active_diagnostic_must_be_restored_before_next_prepare(self):
        run = self.prepare()
        with self.assertRaisesRegex(diagnostic.DiagnosticError, "bereits installiert"):
            self.prepare()
        diagnostic.restore_diagnostic(self.game)
        newer = self.prepare()
        self.assertNotEqual(run.request_id, newer.request_id)
        self.assertNotEqual(run.imported_save, newer.imported_save)
        self.assertTrue(Path(run.imported_save).exists())

    def test_restore_is_idempotent_and_absent_is_noop(self):
        self.assertEqual(diagnostic.restore_diagnostic(self.game), {"restored": False, "state": "absent"})
        run = self.prepare()
        diagnostic.restore_diagnostic(self.game)
        self.assertTrue(diagnostic.restore_diagnostic(self.game)["restored"])
        self.assertEqual(self.mod_files(), {})
        self.assertTrue(Path(run.imported_save).exists())

    def test_restore_refuses_user_edit_and_preserves_added_files(self):
        run = self.prepare()
        mod = Path(run.mod_dir)
        changed = mod / "mod.lua"
        installed = changed.read_bytes()
        changed.write_bytes(b"user modification")
        self.assertFalse(diagnostic.diagnostic_status(self.game)["restorable"])
        with self.assertRaisesRegex(diagnostic.DiagnosticError, "nachträglich verändert"):
            diagnostic.restore_diagnostic(self.game)
        self.assertEqual(changed.read_bytes(), b"user modification")
        changed.write_bytes(installed)
        (mod / "added.txt").write_bytes(b"keep new note")
        diagnostic.restore_diagnostic(self.game)
        self.assertEqual(self.mod_files(), {"added.txt": b"keep new note"})

    def test_restore_refuses_damaged_backup_before_overwriting_anything(self):
        old = self.game / "mods" / diagnostic.MOD
        old.mkdir(parents=True)
        (old / "mod.lua").write_bytes(b"original")
        run = self.prepare()
        before = self.mod_files()
        (Path(run.backup_path) / "original/mods" / diagnostic.MOD / "mod.lua").write_bytes(b"damaged")
        with self.assertRaisesRegex(diagnostic.DiagnosticError, "Backup beschädigt"):
            diagnostic.restore_diagnostic(self.game)
        self.assertEqual(self.mod_files(), before)

    def test_failed_replacement_rolls_back_only_owned_mod_files(self):
        old = self.game / "mods" / diagnostic.MOD
        old.mkdir(parents=True)
        (old / "mod.lua").write_bytes(b"original")
        original_replace = diagnostic.recovery._replace
        calls = 0

        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected replacement failure")
            return original_replace(*args)

        with patch.object(diagnostic.recovery, "_replace", side_effect=fail_second):
            with self.assertRaisesRegex(diagnostic.DiagnosticError, "wiederhergestellt"):
                self.prepare()
        self.assertEqual(self.mod_files(), {"mod.lua": b"original"})
        self.assertEqual((self.game / "alut.dll").read_bytes(), b"previous audio bytes")
        self.assertEqual(diagnostic.diagnostic_status(self.game)["state"], "restored")

    def test_recovery_journal_cannot_redirect_to_native_files(self):
        run = self.prepare()
        path = Path(run.backup_path) / "journal.json"
        value = json.loads(path.read_text("utf-8"))
        value["files"][0]["path"] = "alut.dll"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.restore_diagnostic(self.game)
        self.assertEqual((self.game / "alut.dll").read_bytes(), b"previous audio bytes")

    def test_linked_mod_parent_is_refused_before_writes(self):
        mods = self.game / "mods"
        mods.mkdir()
        original_lstat = Path.lstat

        def linked(path):
            info = original_lstat(path)
            if path == mods:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info

        with patch.object(Path, "lstat", linked):
            with self.assertRaises(diagnostic.DiagnosticError):
                self.prepare()
        self.assertEqual(list(mods.iterdir()), [])

    def test_load_roundtrip_and_reject_redirected_report_path(self):
        run = self.prepare()
        self.assertEqual(diagnostic.load_diagnostic(run.directory), run)
        self.assertEqual(diagnostic.load_diagnostic(run.directory / "run.json"), run)
        path = run.directory / "run.json"
        value = json.loads(path.read_text("utf-8"))
        value["run"]["report_path"] = str(self.root / "secret.json")
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.load_diagnostic(path)
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.read_diagnostic_report(replace(run, report_path=str(self.root / "secret.json")))

    def test_report_missing_then_valid_completed_and_error(self):
        run = self.prepare()
        self.assertIsNone(diagnostic.read_diagnostic_report(run))
        expected = self.report(run)
        self.assertEqual(diagnostic.read_diagnostic_report(run), expected)
        expected = self.report(run, status="error", error="field access unavailable")
        self.assertEqual(diagnostic.read_diagnostic_report(run), expected)

    def test_missing_entities_are_kept_as_observations_not_snapshot_success(self):
        run = self.prepare()
        records = [{"component": "TRANSPORT_VEHICLE", "status": "no_entities"}]
        self.report(run, records=records)
        value = diagnostic.read_diagnostic_report(run)
        self.assertEqual(value["records"], records)
        self.assertIs(value["valid_snapshot"], False)

    def test_report_rejects_wrong_request_mode_format_and_invalid_schema(self):
        run = self.prepare()
        cases = ({"request_id": "b" * 32}, {"mode": "multiplayer"}, {"format": True},
                 {"valid_snapshot": True}, {"status": []}, {"records": {}}, {"limits": []},
                 {"truncated": 1}, {"records": ["string row"]}, {"records": [{}] * 1025})
        for changes in cases:
            with self.subTest(changes=changes):
                self.report(run, **changes)
                with self.assertRaises(diagnostic.DiagnosticError):
                    diagnostic.read_diagnostic_report(run)

    def test_report_rejects_oversize_duplicates_and_nonfinite_numbers(self):
        run = self.prepare()
        path = Path(run.report_path)
        for data in (b" " * (diagnostic.MAX_REPORT_BYTES + 1), b'{"format":1,"format":1}',
                     b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e309}'):
            with self.subTest(data=data[:40]):
                path.write_bytes(data)
                with self.assertRaises(diagnostic.DiagnosticError):
                    diagnostic.read_diagnostic_report(run)

    def test_complete_stable_part_can_be_read_and_exported_without_renaming_or_installing(self):
        run = self.prepare()
        expected = self.report(run, records=[{"component": "CONSTRUCTION", "status": "observed"}])
        final = Path(run.report_path)
        part = Path(run.report_path + ".part")
        final.rename(part)
        before_part = part.read_bytes()
        journal = Path(run.backup_path) / "journal.json"
        before_journal = journal.read_bytes(), journal.stat().st_mtime_ns
        before_mod = self.mod_files()
        before_save = Path(run.imported_save).read_bytes()
        with patch.object(diagnostic.workflow, "restore_probe") as restore, \
                patch.object(diagnostic.recovery, "_replace") as mutate:
            self.assertEqual(diagnostic.read_diagnostic_report(run), expected)
            archive = diagnostic.export_diagnostic(run, self.root / "recovered.zip")
            restore.assert_not_called()
            mutate.assert_not_called()
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(json.loads(package.read("api-audit.json")), expected)
        self.assertFalse(final.exists())
        self.assertEqual(part.read_bytes(), before_part)
        self.assertEqual((journal.read_bytes(), journal.stat().st_mtime_ns), before_journal)
        self.assertEqual(self.mod_files(), before_mod)
        self.assertEqual(Path(run.imported_save).read_bytes(), before_save)

    def test_complete_final_is_preferred_without_reading_invalid_part(self):
        run = self.prepare()
        expected = self.report(run)
        Path(run.report_path + ".part").write_bytes(b"invalid leftover data")
        with patch.object(diagnostic, "_shared_read", wraps=diagnostic._shared_read) as reads:
            self.assertEqual(diagnostic.read_diagnostic_report(run), expected)
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(reads.call_args.args[0], Path(run.report_path))

    def test_partial_final_can_fall_back_to_complete_stable_part(self):
        run = self.prepare()
        expected = self.report(run)
        final = Path(run.report_path)
        Path(run.report_path + ".part").write_bytes(final.read_bytes())
        final.write_bytes(b'{"format":1,')
        self.assertEqual(diagnostic.read_diagnostic_report(run), expected)
        self.assertEqual(final.read_bytes(), b'{"format":1,')

    def test_partial_or_empty_json_in_both_files_waits_for_completion(self):
        run = self.prepare()
        final, part = Path(run.report_path), Path(run.report_path + ".part")
        prefixes = (b"", b" \r\n", b"{", b'{"format":', b'{"format":1,',
                    b'{"value":"unfinished', b'{"value":"escape\\',
                    b'{"value":"\\u1', b'{"value":tru', b'{"value":fal', b'{"value":nu',
                    b'{"value":-', b'{"value":1.', b'{"value":1e', b'{"value":1e+',
                    b'{"value":-1.2e-', b'{"value":"\xc3')
        for raw in prefixes:
            with self.subTest(raw=raw):
                final.write_bytes(raw)
                part.write_bytes(raw)
                self.assertIsNone(diagnostic.read_diagnostic_report(run))

    def test_stable_complete_part_rejects_wrong_request_schema_and_malformed_json(self):
        run = self.prepare()
        final, part = Path(run.report_path), Path(run.report_path + ".part")
        for changes in ({"request_id": "c" * 32}, {"mode": "different"},
                        {"valid_snapshot": True}, {"records": ["bad row"]}):
            with self.subTest(changes=changes):
                self.report(run, **changes)
                part.write_bytes(final.read_bytes())
                final.unlink()
                with self.assertRaises(diagnostic.DiagnosticError):
                    diagnostic.read_diagnostic_report(run)
        for raw in (b'{"value":nope}', b'{"value":NaN}', b'{"value":1e309}',
                    b'{"format":1,"format":1}', b'{"value":01}', b'{"value":1.e}',
                    b'{"value":"\\uX"}', b" " * (diagnostic.MAX_REPORT_BYTES + 1)):
            with self.subTest(raw=raw[:40]):
                part.write_bytes(raw)
                with self.assertRaises(diagnostic.DiagnosticError):
                    diagnostic.read_diagnostic_report(run)

    def test_complete_invalid_final_does_not_fall_back_to_valid_part(self):
        run = self.prepare()
        self.report(run)
        final = Path(run.report_path)
        Path(run.report_path + ".part").write_bytes(final.read_bytes())
        self.report(run, request_id="f" * 32)
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.read_diagnostic_report(run)
        final.write_bytes(b'{"value":wrong}')
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.read_diagnostic_report(run)

    def test_part_changed_between_shared_reads_waits_and_next_stable_read_succeeds(self):
        run = self.prepare()
        first = self.report(run)
        final, part = Path(run.report_path), Path(run.report_path + ".part")
        first_bytes = final.read_bytes()
        second = self.report(run, records=[{"status": "observed"}])
        second_bytes = final.read_bytes()
        final.rename(part)
        with patch.object(diagnostic, "_shared_read", side_effect=[first_bytes, second_bytes]) as reads:
            self.assertIsNone(diagnostic.read_diagnostic_report(run))
            self.assertEqual(reads.call_count, 2)
            self.assertTrue(all(call.args == (part, diagnostic.MAX_REPORT_BYTES) for call in reads.call_args_list))
        self.assertEqual(diagnostic.read_diagnostic_report(run), second)
        self.assertNotEqual(first, second)

    def test_part_disappearing_between_shared_reads_waits(self):
        run = self.prepare()
        self.report(run)
        final, part = Path(run.report_path), Path(run.report_path + ".part")
        raw = final.read_bytes()
        final.rename(part)
        with patch.object(diagnostic, "_shared_read", side_effect=[raw, FileNotFoundError()]):
            self.assertIsNone(diagnostic.read_diagnostic_report(run))

    def test_export_contains_only_validated_report_and_public_metadata(self):
        run = self.prepare()
        expected = self.report(run)
        (run.directory / "session.key").write_text("never export this key", encoding="utf-8")
        (run.directory / "secret.log").write_text("never export this log", encoding="utf-8")
        archive = diagnostic.export_diagnostic(run, self.root / "API-Diagnose.zip")
        with zipfile.ZipFile(archive) as package:
            self.assertEqual(set(package.namelist()), {"api-audit.json", "diagnostic-info.json"})
            self.assertEqual(json.loads(package.read("api-audit.json")), expected)
            info = json.loads(package.read("diagnostic-info.json"))
            self.assertIs(info["valid_snapshot"], False)
            self.assertNotIn(str(self.root), json.dumps(info))
            self.assertIsNone(package.testzip())
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.export_diagnostic(run, archive)

    def test_export_requires_report_and_zip_destination(self):
        run = self.prepare()
        with self.assertRaisesRegex(diagnostic.DiagnosticError, "Noch kein"):
            diagnostic.export_diagnostic(run, self.root / "empty.zip")
        self.report(run)
        with self.assertRaises(diagnostic.DiagnosticError):
            diagnostic.export_diagnostic(run, self.root / "wrong.txt")


if __name__ == "__main__":
    unittest.main()
