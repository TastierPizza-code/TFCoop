from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from coop.install import _files
from prototype.strict_sync import probe_install as install
from prototype.strict_sync import stage_probe as stage
from prototype.strict_sync.core import digest
from prototype.tests.test_stage_probe import dll_bytes


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "source"
        self.game = self.base / "game"
        self.game.mkdir()
        (self.game / "res").mkdir()
        (self.game / "TransportFever2.exe").write_bytes(b"supported fixture executable")
        self.stock = dll_bytes(b"stock audio")
        (self.game / "alut.dll").write_bytes(b"existing alpha proxy bytes")
        (self.game / "alut_real.dll").write_bytes(self.stock)
        (self.game / "other.dll").write_bytes(b"unrelated library")
        oldmod = self.game / "mods/tf2coop_1/mod.lua"
        oldmod.parent.mkdir(parents=True)
        oldmod.write_bytes(b"existing alpha mod")
        self.saves = self.base / "save"
        self.saves.mkdir()
        self.original = self.saves / "original.sav"
        self.original.write_bytes(b"original shared world")
        Path(str(self.original) + ".lua").write_bytes(b"return { name = 'Private save title' }\r\n")
        self.original_bytes = _files(self.saves)
        self.original_game = _files(self.game)
        for attr, value in (("STOCK_ALUT_SHA256", hashlib.sha256(self.stock).hexdigest()),
                            ("check_game_build", None), ("game_is_running", None)):
            if attr == "check_game_build":
                p = patch.object(stage.native, attr, return_value={"compatible": True, "sha256": stage.native.EXPECTED_SHA256})
            elif attr == "game_is_running":
                p = patch.object(stage.native, attr, return_value=False)
            else:
                p = patch.object(stage.native, attr, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict(os.environ, {"LOCALAPPDATA": str(self.base / "local")})
        p.start()
        self.addCleanup(p.stop)
        for name in stage.REQUIRED_MOD_FILES:
            file = self.root / "prototype/mod" / stage.MOD / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("-- source " + name + "\nreturn {}\n", encoding="utf-8")
        for name in stage.REQUIRED_PYTHON:
            file = self.root / "prototype/strict_sync" / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("# source " + name + "\n", encoding="utf-8")
        native_out = self.root / "prototype/native/out"
        native_out.mkdir(parents=True)
        (native_out / "probe_alut.dll").write_bytes(dll_bytes(b"test proxy"))
        (native_out / "tf2_step_probe.dll").write_bytes(dll_bytes(b"test runtime"))
        self.output = self.base / "output"
        self.session = self.base / "session"
        stage.stage_probe(game_dir=self.game, save=self.original, session=self.session,
                          output=self.output, repository_root=self.root, native_epoch=55)

    def execute(self):
        return install.install_probe(self.game, self.output, self.saves, session_dir=self.session)

    def game_bytes(self):
        return {name: sha for name, sha in _files(self.game).items() if not name.startswith(install.STATE_DIR + "/")}

    def mutate_json(self, path, callback):
        value = json.loads(path.read_text())
        callback(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_install_and_restore_preserve_alpha_exactly_and_save_metadata(self):
        result = self.execute()
        self.assertTrue(result["installed"])
        imported = Path(result["imported_save"])
        self.assertRegex(imported.name, r"^TF2-Koop-Messtest-[0-9a-f]{32}\.sav$")
        self.assertEqual(imported.read_bytes(), self.original.read_bytes())
        self.assertEqual(Path(str(imported) + ".lua").read_bytes(), Path(str(self.original) + ".lua").read_bytes())
        status = install.installation_status(self.game)
        self.assertEqual(status["state"], "installed")
        self.assertTrue(status["restorable"])
        self.assertEqual((Path(result["backup_path"]) / "original/alut.dll").read_bytes(), b"existing alpha proxy bytes")
        restored = install.restore_probe(self.game)
        self.assertTrue(restored["restored"])
        self.assertEqual(self.game_bytes(), self.original_game)
        self.assertTrue(imported.is_file())
        self.assertTrue(Path(result["backup_path"]).is_dir())
        self.assertFalse(install.installation_status(self.game)["installed"])
        self.assertTrue(install.restore_probe(self.game)["restored"])

    def test_repeat_install_requires_restore_then_imports_unique_save(self):
        first = self.execute()
        with self.assertRaisesRegex(install.ProbeInstallError, "bereits installiert"):
            self.execute()
        install.restore_probe(self.game)
        second = self.execute()
        self.assertNotEqual(first["imported_save"], second["imported_save"])
        self.assertTrue(Path(first["imported_save"]).is_file())
        self.assertTrue(Path(second["imported_save"]).is_file())
        self.assertTrue(Path(first["backup_path"]).is_dir())

    def test_changed_deployed_file_blocks_whole_restore_before_any_change(self):
        self.execute()
        (self.game / "tf2_step_probe.dll").write_bytes(b"user edit")
        before = self.game_bytes()
        status = install.installation_status(self.game)
        self.assertFalse(status["restorable"])
        self.assertIn("tf2_step_probe.dll", status["conflicts"][0])
        with self.assertRaises(install.ProbeInstallError):
            install.restore_probe(self.game)
        self.assertEqual(before, self.game_bytes())

    def test_missing_deployed_file_blocks_restore(self):
        self.execute()
        (self.game / "tf2_step_probe.dll").unlink()
        self.assertFalse(install.installation_status(self.game)["restorable"])
        with self.assertRaises(install.ProbeInstallError): install.restore_probe(self.game)

    def test_modified_backup_blocks_whole_restore(self):
        result = self.execute()
        (Path(result["backup_path"]) / "original/alut.dll").write_bytes(b"modified backup")
        before = self.game_bytes()
        with self.assertRaisesRegex(install.ProbeInstallError, "Backup beschädigt"):
            install.restore_probe(self.game)
        self.assertEqual(before, self.game_bytes())

    def test_added_user_file_in_owned_mod_is_preserved(self):
        self.execute()
        user = self.game / f"mods/{stage.MOD}/notes.txt"
        user.write_text("user data")
        install.restore_probe(self.game)
        self.assertEqual(user.read_text(), "user data")
        self.assertEqual({k: v for k, v in self.game_bytes().items() if not k.endswith("notes.txt")}, self.original_game)

    def test_copy_failure_rolls_back_game_and_cleans_completed_save_import(self):
        original = install._replace
        calls = 0
        def fail_second(source, target, expected, previous):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected replacement failure")
            return original(source, target, expected, previous)
        with patch.object(install, "_replace", side_effect=fail_second):
            with self.assertRaisesRegex(install.ProbeInstallError, "wiederhergestellt"):
                self.execute()
        self.assertEqual(self.game_bytes(), self.original_game)
        self.assertEqual(_files(self.saves), self.original_bytes)
        self.assertEqual(install.installation_status(self.game)["state"], "restored")

    def test_backup_failure_changes_no_game_files(self):
        with patch.object(install, "_copy_exclusive", side_effect=OSError("backup read error")):
            with self.assertRaises(OSError): self.execute()
        self.assertEqual(self.game_bytes(), self.original_game)
        self.assertEqual(_files(self.saves), self.original_bytes)
        self.assertEqual(install.installation_status(self.game)["state"], "absent")

    def test_restore_interruption_is_resumable(self):
        result = self.execute()
        original = install._replace
        count = 0
        def fail_restore(source, target, expected, previous):
            nonlocal count
            count += 1
            if count == 1:
                raise OSError("interrupted restore")
            return original(source, target, expected, previous)
        with patch.object(install, "_replace", side_effect=fail_restore):
            with self.assertRaises(OSError): install.restore_probe(self.game)
        self.assertEqual(install.installation_status(self.game)["state"], "restoring")
        self.assertTrue(install.installation_status(self.game)["restorable"])
        self.assertTrue(install.restore_probe(self.game)["restored"])
        self.assertEqual(self.game_bytes(), self.original_game)
        self.assertTrue(Path(result["imported_save"]).is_file())

    def test_wrong_build_or_running_game_refuses_without_writes(self):
        for function, value in (("game_is_running", True), ("check_game_build", {"compatible": False})):
            with self.subTest(function=function), patch.object(install.native, function, return_value=value):
                with self.assertRaises(install.ProbeInstallError): self.execute()
            self.assertEqual(self.game_bytes(), self.original_game)
            self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_changed_payload_or_save_refuses_without_game_writes(self):
        for relative in ("game/alut.dll", "game/mods/" + stage.MOD + "/mod.lua", "save/initial.sav.lua"):
            file = self.output / relative
            original = file.read_bytes()
            file.write_bytes(b"changed after preparation")
            with self.subTest(relative=relative), self.assertRaises(install.ProbeInstallError): self.execute()
            file.write_bytes(original)
        self.assertEqual(self.game_bytes(), self.original_game)
        self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_payload_path_escape_refuses_without_touching_outside_file(self):
        outside = self.base / "outside.txt"
        outside.write_bytes(b"outside")
        self.mutate_json(self.session / "probe_payload.json", lambda p: p["files"].update({"../outside.txt": hashlib.sha256(b"outside").hexdigest()}))
        with self.assertRaises(install.ProbeInstallError): self.execute()
        self.assertEqual(outside.read_bytes(), b"outside")
        self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_config_cannot_redirect_mailbox_even_when_local_payload_hash_updated(self):
        config = self.output / "game/mods" / stage.MOD / stage.CONFIG
        config.write_bytes(b"return { enabled = true, mailbox_dir = 'foreign' }")
        name = f"mods/{stage.MOD}/{stage.CONFIG}"
        self.mutate_json(self.session / "probe_payload.json", lambda p: p["files"].update({name: hashlib.sha256(config.read_bytes()).hexdigest()}))
        with self.assertRaisesRegex(install.ProbeInstallError, "local Lua configuration"):
            self.execute()
        self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_explicit_build_profile_installs_only_matching_generated_config(self):
        for name in stage.REQUIRED_BUILD_FILES:
            file = self.root / "prototype/mod" / stage.MOD / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("-- build fixture\nreturn {}\n")
        self.output = self.base / "build-output"
        self.session = self.base / "build-session"
        stage.stage_probe(game_dir=self.game, save=self.original, session=self.session,
                          output=self.output, repository_root=self.root, native_epoch=66, profile="build_v2")
        result = self.execute()
        self.assertTrue(result["installed"])
        actual = (self.game / "mods" / stage.MOD / stage.CONFIG).read_text()
        self.assertIn('profile = "build_v2"', actual)
        install.restore_probe(self.game)
        self.assertEqual(self.game_bytes(), self.original_game)

    def test_save_collision_is_never_overwritten(self):
        class FixedUUID:
            hex = "1" * 32
        target = self.saves / ("TF2-Koop-Messtest-" + FixedUUID.hex + ".sav")
        target.write_bytes(b"existing important save")
        with patch.object(install.uuid, "uuid4", return_value=FixedUUID()):
            with self.assertRaises(install.ProbeInstallError): self.execute()
        self.assertEqual(target.read_bytes(), b"existing important save")
        self.assertEqual(self.game_bytes(), self.original_game)

    def test_unchanged_preexisting_probe_file_restored_exactly(self):
        target = self.game / f"mods/{stage.MOD}/mod.lua"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"older test mod")
        before = self.game_bytes()
        self.execute()
        install.restore_probe(self.game)
        self.assertEqual(before, self.game_bytes())

    def test_foreign_ownership_journal_is_never_adopted(self):
        state = self.game / install.STATE_DIR
        state.mkdir()
        (state / "current.json").write_text(json.dumps({"owner": "foreign", "run_id": "1" * 32}))
        with self.assertRaises(install.ProbeInstallError): self.execute()
        with self.assertRaises(install.ProbeInstallError): install.restore_probe(self.game)
        self.assertEqual(self.game_bytes(), self.original_game)

    def test_active_launch_ticket_blocks_install_without_revoking_it(self):
        ticket = self.base / "local/TF2Coop/launch.cfg"
        ticket.parent.mkdir(parents=True)
        ticket.write_text(f"format=1\nlauncher_pid=123\nlauncher_created=456\nexpires={int(time.time()) + 120}\n")
        before = ticket.read_bytes()
        with patch.object(install, "process_info", return_value=SimpleNamespace(created=456)):
            with self.assertRaisesRegex(install.ProbeInstallError, "Koop-Start"):
                self.execute()
        self.assertEqual(ticket.read_bytes(), before)
        self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_already_consumed_session_is_rejected_before_installing(self):
        (self.session / "controller_started.json").write_text('{"consumed":true}')
        with self.assertRaisesRegex(install.ProbeInstallError, "bereits verwendet"):
            self.execute()
        self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_native_epoch_mismatch_is_rejected_before_installing(self):
        (self.session / "probe_epoch.txt").write_text("56\n")
        with self.assertRaisesRegex(install.ProbeInstallError, "epoch"):
            self.execute()
        self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_preexisting_empty_directories_remain_after_restore(self):
        empty = self.game / f"mods/{stage.MOD}/res/scripts"
        empty.mkdir(parents=True)
        self.execute()
        install.restore_probe(self.game)
        self.assertTrue(empty.is_dir())


if __name__ == "__main__":
    unittest.main()
