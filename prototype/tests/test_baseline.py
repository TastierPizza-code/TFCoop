"""Private baseline migration uses temporary files only, never a running game."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from prototype import baseline


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "public-package"
        self.package.mkdir()
        self.state = self.root / "local-state"
        self.save_data = b"private TF2 baseline bytes\x00\x01"
        self.lua_data = b"return {name = 'private baseline'}\n"
        self.meta = {
            "sav_sha256": hashlib.sha256(self.save_data).hexdigest(),
            "sav_lua_sha256": hashlib.sha256(self.lua_data).hexdigest(),
        }
        self.manifest()

    def manifest(self, **changes):
        document = {"package": "test-public", "baseline": dict(self.meta)}
        document.update(changes)
        (self.package / "package_manifest.json").write_text(json.dumps(document), encoding="utf-8")

    def pair(self, save, *, sav=None, lua=None):
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_bytes(self.save_data if sav is None else sav)
        Path(str(save) + ".lua").write_bytes(self.lua_data if lua is None else lua)
        return save

    def prior_run(self, *, output=None, run=None):
        run = run or self.state / "runs/known-run"
        output = output or run / "payload"
        self.state.mkdir(parents=True, exist_ok=True)
        run.mkdir(parents=True, exist_ok=True)
        (self.state / "launcher.json").write_text(json.dumps({"last_run": str(run)}), encoding="utf-8")
        (run / "run.json").write_text(json.dumps({"output": str(output)}), encoding="utf-8")
        return self.pair(output / "save/initial.sav")

    def resolve(self, selected=None):
        return baseline.resolve_baseline(self.package, self.state, selected)

    def test_public_package_without_local_pair_explains_private_migration(self):
        with self.assertRaisesRegex(baseline.BaselineError, "alten Paketordner.*Testspielstand/initial.sav"):
            self.resolve()
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.package.iterdir()), [self.package / "package_manifest.json"])

    def test_old_bundled_pair_is_copied_to_verified_cache(self):
        source = self.pair(self.package / "Testspielstand/initial.sav")
        cached = self.resolve()
        self.assertTrue(cached.is_relative_to(self.state / "baseline"))
        self.assertNotEqual(source, cached)
        self.assertEqual(cached.read_bytes(), self.save_data)
        self.assertEqual(Path(str(cached) + ".lua").read_bytes(), self.lua_data)
        self.assertEqual(source.read_bytes(), self.save_data)
        self.assertEqual(len(cached.parent.name), 64)

    def test_valid_cache_survives_package_move_and_original_removal(self):
        source = self.pair(self.package / "Testspielstand/initial.sav")
        cached = self.resolve()
        source.unlink()
        Path(str(source) + ".lua").unlink()
        moved = self.root / "next-public-package"
        self.package.rename(moved)
        self.package = moved
        self.assertEqual(self.resolve(), cached)

    def test_valid_cache_takes_priority_over_bad_user_selection(self):
        source = self.pair(self.root / "old-package/Testspielstand/initial.sav")
        cached = self.resolve(source)
        source.write_bytes(b"wrong user world")
        self.assertEqual(self.resolve(source), cached)

    def test_previous_recorded_payload_is_migrated_without_game_writes(self):
        source = self.prior_run()
        before = {p: p.read_bytes() for p in source.parent.iterdir()}
        cached = self.resolve()
        self.assertNotEqual(source, cached)
        self.assertEqual(before, {p: p.read_bytes() for p in source.parent.iterdir()})

    def test_bad_bundled_pair_falls_back_to_valid_previous_run(self):
        self.pair(self.package / "Testspielstand/initial.sav", sav=b"wrong bundle save")
        self.prior_run()
        self.assertEqual(self.resolve().read_bytes(), self.save_data)

    def test_unrecorded_runs_and_adjacent_old_packages_are_not_scanned(self):
        self.pair(self.state / "runs/unrecorded/payload/save/initial.sav")
        self.pair(self.root / "old-version/Testspielstand/initial.sav")
        with self.assertRaises(baseline.BaselineError):
            self.resolve()

    def test_prior_run_outside_local_state_is_not_followed(self):
        self.prior_run(run=self.root / "unrelated-run")
        with self.assertRaises(baseline.BaselineError):
            self.resolve()

    def test_prior_payload_cannot_escape_recorded_run(self):
        self.prior_run(output=self.state / "other-payload")
        with self.assertRaises(baseline.BaselineError):
            self.resolve()

    def test_manual_selection_imports_named_sav_with_sibling_lua(self):
        selected = self.pair(self.root / "private location/My baseline.sav")
        self.assertEqual(self.resolve(selected).read_bytes(), selected.read_bytes())

    def test_pair_requires_both_exact_hashes_and_no_missing_lua(self):
        selected = self.pair(self.root / "private/initial.sav")
        for sav, lua in ((b"other world", self.lua_data), (self.save_data, b"other metadata")):
            with self.subTest(sav=sav, lua=lua):
                self.pair(selected, sav=sav, lua=lua)
                with self.assertRaises(baseline.BaselineError):
                    self.resolve(selected)
        self.pair(selected)
        Path(str(selected) + ".lua").unlink()
        with self.assertRaises(baseline.BaselineError):
            self.resolve(selected)

    def test_expected_pair_sizes_are_optional_but_enforced_when_present(self):
        selected = self.pair(self.root / "private/initial.sav")
        meta = dict(self.meta, sav_bytes=len(self.save_data), sav_lua_bytes=len(self.lua_data))
        self.manifest(baseline=meta)
        self.assertEqual(self.resolve(selected).read_bytes(), self.save_data)
        self.manifest(baseline=dict(meta, sav_lua_bytes=len(self.lua_data) + 1))
        with self.assertRaises(baseline.BaselineError):
            self.resolve(selected)

    def test_changed_lua_identity_uses_different_cache_directory(self):
        selected = self.pair(self.root / "private/initial.sav")
        original = self.resolve(selected)
        changed_lua = self.lua_data + b"-- changed baseline version\n"
        Path(str(selected) + ".lua").write_bytes(changed_lua)
        self.manifest(baseline=dict(self.meta, sav_lua_sha256=hashlib.sha256(changed_lua).hexdigest()))
        changed = self.resolve(selected)
        self.assertNotEqual(original.parent, changed.parent)
        self.assertEqual(Path(str(original) + ".lua").read_bytes(), self.lua_data)

    def test_damaged_cache_is_preserved_before_new_atomic_pair_is_published(self):
        selected = self.pair(self.root / "private/initial.sav")
        cached = self.resolve(selected)
        cached.write_bytes(b"damaged old cache")
        (cached.parent / "unrelated-note.txt").write_text("keep this", encoding="utf-8")
        self.assertEqual(self.resolve(selected), cached)
        self.assertEqual(cached.read_bytes(), self.save_data)
        preserved = list(cached.parent.parent.glob("rejected-*"))
        self.assertEqual(len(preserved), 1)
        self.assertEqual((preserved[0] / "initial.sav").read_bytes(), b"damaged old cache")
        self.assertEqual((preserved[0] / "unrelated-note.txt").read_text("utf-8"), "keep this")
        self.assertEqual(list(cached.parent.parent.glob(".import-*")), [])

    def test_invalid_new_manifest_cannot_downgrade_to_unchecked_bundled_save(self):
        self.pair(self.package / "Testspielstand/initial.sav")
        cases = (None, [], {}, dict(self.meta, sav_sha256="x" * 64),
                 dict(self.meta, sav_bytes=True), dict(self.meta, sav_lua_bytes=-1))
        for meta in cases:
            with self.subTest(meta=meta):
                self.manifest(baseline=meta)
                with self.assertRaises(baseline.BaselineError):
                    self.resolve()
        self.assertFalse(self.state.exists())

    def test_manifest_is_bounded_and_malformed_json_is_not_legacy(self):
        path = self.package / "package_manifest.json"
        self.pair(self.package / "Testspielstand/initial.sav")
        path.write_text("{" + " " * baseline.MAX_JSON_BYTES, encoding="utf-8")
        with self.assertRaises(baseline.BaselineError):
            self.resolve()
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(baseline.BaselineError):
            self.resolve()

    def test_broken_prior_settings_do_not_block_explicit_selection(self):
        selected = self.pair(self.root / "private/initial.sav")
        self.state.mkdir()
        (self.state / "launcher.json").write_text("[invalid", encoding="utf-8")
        self.assertEqual(self.resolve(selected).read_bytes(), self.save_data)

    def test_linked_cache_parent_is_rejected_before_writes(self):
        self.state.mkdir()
        cache = self.state / "baseline"
        cache.mkdir()
        selected = self.pair(self.root / "private/initial.sav")
        original_lstat = Path.lstat

        def fake_lstat(path):
            info = original_lstat(path)
            if path == cache:
                return SimpleNamespace(st_mode=info.st_mode,
                                       st_file_attributes=baseline._REPARSE_POINT)
            return info

        with patch.object(Path, "lstat", fake_lstat):
            with self.assertRaisesRegex(baseline.BaselineError, "Junctions"):
                self.resolve(selected)
        self.assertEqual(list(cache.iterdir()), [])

    def test_linked_source_is_not_imported(self):
        selected = self.pair(self.root / "private/initial.sav")
        original_lstat = Path.lstat

        def fake_lstat(path):
            info = original_lstat(path)
            if path == selected:
                return SimpleNamespace(st_mode=info.st_mode,
                                       st_file_attributes=baseline._REPARSE_POINT)
            return info

        with patch.object(Path, "lstat", fake_lstat):
            with self.assertRaises(baseline.BaselineError):
                self.resolve(selected)
        self.assertFalse(self.state.exists())

    def test_source_change_during_copy_publishes_nothing(self):
        selected = self.pair(self.root / "private/initial.sav")
        original_copy = baseline._copy_file

        def changed_copy(source, *args):
            if source == selected:
                selected.write_bytes(b"modified source while importing")
            return original_copy(source, *args)

        with patch.object(baseline, "_copy_file", side_effect=changed_copy):
            with self.assertRaisesRegex(baseline.BaselineError, "während des Kopierens verändert"):
                self.resolve(selected)
        self.assertEqual(list((self.state / "baseline").iterdir()), [])

    def test_legacy_private_bundle_without_baseline_metadata_returns_original_pair(self):
        bundled = self.pair(self.package / "Testspielstand/initial.sav")
        self.manifest()
        (self.package / "package_manifest.json").write_text('{"package":"old-private"}', encoding="utf-8")
        self.assertEqual(self.resolve(), bundled)
        (self.package / "package_manifest.json").unlink()
        self.assertEqual(self.resolve(), bundled)
        self.assertFalse(self.state.exists())

    def test_empty_or_incomplete_legacy_pair_is_rejected(self):
        (self.package / "package_manifest.json").unlink()
        self.pair(self.package / "Testspielstand/initial.sav", lua=b"")
        with self.assertRaises(baseline.BaselineError):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
