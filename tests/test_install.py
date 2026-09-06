import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coop.install import discover_game, install_mod, InstallError, MARKER, _vdf


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.game = self.make_game(self.root / "SteamLibrary/steamapps/common/Transport Fever 2")
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "mod.lua").write_text("function data() return {} end\n", encoding="utf-8")
        self.mailbox = self.root / 'mailbox with space'

    def make_game(self, path):
        (path / "res").mkdir(parents=True)
        (path / "TransportFever2.exe").write_bytes(b"fake")
        return path

    def test_vdf_handles_nested_escaped_paths_empty_values_and_comments(self):
        parsed = _vdf('// hi\n"libraryfolders" { "0" { "path" "X:\\\\SteamLibrary" "empty" "" } }')
        self.assertEqual(parsed["libraryfolders"]["0"]["path"], "X:\\SteamLibrary")
        self.assertEqual(parsed["libraryfolders"]["0"]["empty"], "")

    def test_discovery_uses_fallback_without_manifest(self):
        with patch("coop.install._steam_roots", return_value=[self.root / "SteamLibrary"]):
            self.assertEqual(discover_game(), self.game.resolve())

    def test_discovery_follows_modern_library_and_manifest(self):
        steam = self.root / "Steam"
        (steam / "steamapps").mkdir(parents=True)
        library = self.root / "other library"
        expected = self.make_game(library / "steamapps/common/Custom Game Folder")
        path = library.as_posix()
        (steam / "steamapps/libraryfolders.vdf").write_text(f'"libraryfolders" {{ "1" {{ "path" "{path}" }} }}')
        (library / "steamapps/appmanifest_1066780.acf").write_text('"AppState" { "installdir" "Custom Game Folder" }')
        with patch("coop.install._steam_roots", return_value=[steam]):
            self.assertEqual(discover_game(), expected.resolve())

    def test_discovery_ignores_corrupt_manifests(self):
        (self.game.parent.parent / "appmanifest_1066780.acf").write_text('"AppState" {')
        with patch("coop.install._steam_roots", return_value=[self.root / "SteamLibrary"]):
            self.assertEqual(discover_game(), self.game.resolve())

    def test_install_is_idempotent_and_records_generated_config(self):
        target = install_mod(self.game, self.source, self.mailbox)
        self.assertEqual(target.name, "tf2coop_1")
        config = (target / "res/scripts/tf2coop/config.lua").read_text(encoding="utf-8")
        self.assertIn(self.mailbox.resolve().as_posix(), config)
        marker = json.loads((target / MARKER).read_text())
        self.assertIn("res/scripts/tf2coop/config.lua", marker["files"])
        before = (target / "mod.lua").stat().st_mtime_ns
        self.assertEqual(install_mod(self.game, self.source, self.mailbox), target)
        self.assertEqual((target / "mod.lua").stat().st_mtime_ns, before)
        self.assertEqual(list((self.game / "mods").glob(".tf2coop-*")), [])

    def test_pristine_install_can_update(self):
        target = install_mod(self.game, self.source, self.mailbox)
        (self.source / "mod.lua").write_text("new source")
        install_mod(self.game, self.source, self.mailbox)
        self.assertEqual((target / "mod.lua").read_text(), "new source")

    def test_unknown_folder_is_preserved(self):
        target = self.game / "mods/tf2coop_1"
        target.mkdir(parents=True)
        (target / "mine.lua").write_text("user content")
        with self.assertRaises(InstallError):
            install_mod(self.game, self.source, self.mailbox)
        self.assertEqual((target / "mine.lua").read_text(), "user content")
        self.assertFalse((target / MARKER).exists())

    def test_local_edits_and_extra_files_are_preserved(self):
        target = install_mod(self.game, self.source, self.mailbox)
        for file in ("mod.lua", "extra.lua"):
            with self.subTest(file=file):
                path = target / file
                previous = path.read_bytes() if path.exists() else None
                path.write_text("local edit")
                with self.assertRaises(InstallError):
                    install_mod(self.game, self.source, self.mailbox)
                self.assertEqual(path.read_text(), "local edit")
                if previous is None:
                    path.unlink()
                else:
                    path.write_bytes(previous)

    def test_failed_replacement_rolls_back_owned_install(self):
        target = install_mod(self.game, self.source, self.mailbox)
        before = (target / "mod.lua").read_bytes()
        (self.source / "mod.lua").write_text("new source")
        actual_replace = os.replace
        def replace(src, dst):
            if Path(src).name.startswith(".tf2coop-stage-"):
                raise PermissionError("locked")
            actual_replace(src, dst)
        with patch("coop.install.os.replace", side_effect=replace):
            with self.assertRaises(InstallError):
                install_mod(self.game, self.source, self.mailbox)
        self.assertEqual((target / "mod.lua").read_bytes(), before)
        self.assertEqual(list((self.game / "mods").glob(".tf2coop-*")), [])

    def test_invalid_source_makes_no_game_changes(self):
        with self.assertRaises(InstallError):
            install_mod(self.game, self.root / "missing", self.mailbox)
        self.assertFalse((self.game / "mods").exists())


if __name__ == "__main__":
    unittest.main()
