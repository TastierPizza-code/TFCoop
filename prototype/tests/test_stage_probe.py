from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from prototype.strict_sync import stage_probe as stage
from prototype.strict_sync.core import digest
from coop.install import _files


def dll_bytes(tag=b""):
    data = bytearray(64 + 88)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0x8664)
    struct.pack_into("<H", data, 86, 0x2000)
    struct.pack_into("<H", data, 88, 0x20B)
    struct.pack_into("<I", data, 144, 0x10000)
    return bytes(data) + tag


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "source"
        self.game = self.base / "game"
        self.game.mkdir()
        (self.game / "res").mkdir()
        (self.game / "TransportFever2.exe").write_bytes(b"read-only fake game executable")
        self.stock = dll_bytes(b"stock-audio")
        (self.game / "alut.dll").write_bytes(self.stock)
        self.stock_patch = patch.object(stage.native, "STOCK_ALUT_SHA256", hashlib.sha256(self.stock).hexdigest())
        self.stock_patch.start()
        self.addCleanup(self.stock_patch.stop)
        self.build_patch = patch.object(stage.native, "check_game_build", return_value={
            "compatible": True, "sha256": stage.native.EXPECTED_SHA256})
        self.build_patch.start()
        self.addCleanup(self.build_patch.stop)
        self.save = self.base / "original.sav"
        self.save.write_bytes(b"saved world")
        Path(str(self.save) + ".lua").write_bytes(b"save metadata")
        for name in stage.REQUIRED_MOD_FILES:
            target = self.root / "prototype" / "mod" / stage.MOD / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("-- source " + name + "\nreturn {}\n", encoding="utf-8")
        for name in stage.REQUIRED_PYTHON:
            target = self.root / "prototype" / "strict_sync" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# source " + name + "\n", encoding="utf-8")
        native = self.root / "prototype" / "native" / "out"
        native.mkdir(parents=True)
        (native / "probe_alut.dll").write_bytes(dll_bytes(b"probe-proxy"))
        (native / "tf2_step_probe.dll").write_bytes(dll_bytes(b"probe-runtime"))

    def prepare(self, name="one", **kwargs):
        return stage.stage_probe(game_dir=self.game, save=self.save, session=self.base / (name + "-session"),
                                 output=self.base / (name + "-output"), repository_root=self.root,
                                 native_epoch=kwargs.pop("native_epoch", 1234567890123456), **kwargs)

    def template(self, bindings, name="templates.json"):
        path = self.base / name
        path.write_text(json.dumps({"initial_bindings": bindings}), encoding="utf-8")
        return path

    def test_stages_only_and_binds_local_payload(self):
        game_before = _files(self.game)
        with patch.object(stage.native, "game_is_running", return_value=True) as process_check:
            result = self.prepare()
        process_check.assert_not_called()  # Preparation neither operates nor requires a closed game.
        self.assertEqual(game_before, _files(self.game))
        self.assertTrue(result["staging_only"])
        self.assertTrue(result["read_only_time_probe"])
        directory, output = Path(result["session"]), Path(result["output"])
        setup = json.loads((directory / "probe_setup.json").read_text())
        self.assertEqual(set(setup), {"protocol", "native_epoch", "manifest_digest", "game_exe"})
        self.assertEqual(setup["game_exe"], str(self.game / "TransportFever2.exe"))
        self.assertEqual((directory / "probe_epoch.txt").read_text().strip(), str(setup["native_epoch"]))
        self.assertEqual(json.loads((directory / "probe_payload.json").read_text()), {"files": _files(output / "game")})
        self.assertEqual((output / "save/initial.sav").read_bytes(), self.save.read_bytes())
        self.assertEqual((output / "save/initial.sav.lua").read_bytes(), Path(str(self.save) + ".lua").read_bytes())
        config = (output / "game/mods" / stage.MOD / stage.CONFIG).read_text(encoding="utf-8")
        self.assertIn("enabled = true", config)
        self.assertIn("native_gate_required = true", config)
        self.assertIn(directory.as_posix(), config)
        manifest = json.loads((directory / "probe_manifest.json").read_text())
        self.assertEqual(digest(manifest), setup["manifest_digest"])
        self.assertNotIn(str(self.base), json.dumps(manifest))
        self.assertNotIn("native_epoch", manifest)

    def test_same_inputs_different_local_paths_epochs_same_shared_digest(self):
        a = self.prepare("a", native_epoch=1)
        b = self.prepare("b", native_epoch=2)
        self.assertEqual(a["manifest_digest"], b["manifest_digest"])
        payload_a = json.loads((Path(a["session"]) / "probe_payload.json").read_text())
        payload_b = json.loads((Path(b["session"]) / "probe_payload.json").read_text())
        self.assertNotEqual(payload_a, payload_b)  # Local config is still bound for installation checks.

    def test_build_profile_is_bound_and_legacy_time_config_is_unchanged(self):
        for name in stage.REQUIRED_BUILD_FILES:
            file = self.root / "prototype/mod" / stage.MOD / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("-- build fixture\nreturn {}\n")
        time = self.prepare("time")
        build = self.prepare("build", profile="build_v2")
        self.assertNotEqual(time["manifest_digest"], build["manifest_digest"])
        self.assertFalse(build["read_only_time_probe"])
        time_manifest = json.loads((Path(time["session"]) / "probe_manifest.json").read_text())
        build_manifest = json.loads((Path(build["session"]) / "probe_manifest.json").read_text())
        self.assertEqual(time_manifest["prototype_files"], build_manifest["prototype_files"])
        self.assertNotIn("profile", time_manifest["config_semantics"])
        self.assertEqual(build_manifest["config_semantics"]["profile"], "build_v2")
        config = (Path(build["output"]) / "game/mods" / stage.MOD / stage.CONFIG).read_text()
        self.assertIn('profile = "build_v2"', config)

    def test_build_profile_refuses_missing_assets_before_creating_session(self):
        with self.assertRaisesRegex(stage.StageError, "recipe"):
            self.prepare("build", profile="build_v2")
        self.assertFalse((self.base / "build-session").exists())
        with self.assertRaisesRegex(stage.StageError, "Unknown"):
            self.prepare("unknown", profile="invented")

    def test_short_preparation_is_shared_manifest_bound_and_opt_in(self):
        for name in stage.REQUIRED_BUILD_FILES:
            file = self.root / "prototype/mod" / stage.MOD / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("-- build fixture\nreturn {}\n")
        old = self.prepare("old", profile="build_v2")
        a = self.prepare("short-a", profile="build_v2", preparation="short_scene_v1", native_epoch=1)
        b = self.prepare("short-b", profile="build_v2", preparation="short_scene_v1", native_epoch=2)
        self.assertEqual(a["manifest_digest"], b["manifest_digest"])
        self.assertNotEqual(old["manifest_digest"], a["manifest_digest"])
        for result, expected in ((old, None), (a, "short_scene_v1")):
            manifest = json.loads((Path(result["session"]) / "probe_manifest.json").read_text())
            self.assertEqual(manifest["config_semantics"].get("preparation"), expected)
        for name, kwargs in (("bad", {"profile": "build_v2", "preparation": "unknown"}),
                             ("wrong-profile", {"profile": "time_v1", "preparation": "short_scene_v1"})):
            with self.assertRaisesRegex(stage.StageError, "preparation contract"):
                self.prepare(name, **kwargs)
            self.assertFalse((self.base / (name + "-session")).exists())

    def test_build_profile_cannot_mix_existing_template_bindings(self):
        template = self.template([{"logical_id": "seed:depot", "kind": "depot", "entity": 5}])
        with self.assertRaisesRegex(stage.StageError, "cannot be mixed"):
            self.prepare("mixed", profile="build_v2", templates=template)

    def test_template_order_canonical_and_actual_ids_bound(self):
        bindings = [{"logical_id": "seed:vehicle", "kind": "vehicle", "entity": 20},
                    {"logical_id": "seed:depot", "kind": "depot", "entity": 10}]
        a = self.prepare("a", templates=self.template(bindings, "a.json"))
        b = self.prepare("b", templates=self.template(list(reversed(bindings)), "b.json"))
        self.assertEqual(a["manifest_digest"], b["manifest_digest"])
        bindings[0]["entity"] = 21
        c = self.prepare("c", templates=self.template(bindings, "c.json"))
        self.assertNotEqual(a["manifest_digest"], c["manifest_digest"])
        self.assertFalse(a["read_only_time_probe"])

    def test_code_and_both_save_parts_change_manifest(self):
        a = self.prepare("a")
        Path(str(self.save) + ".lua").write_bytes(b"different metadata")
        b = self.prepare("b")
        self.assertNotEqual(a["manifest_digest"], b["manifest_digest"])
        self.save.write_bytes(b"different world")
        c = self.prepare("c")
        self.assertNotEqual(b["manifest_digest"], c["manifest_digest"])
        (self.root / "prototype/strict_sync/core.py").write_text("# changed source\n")
        d = self.prepare("d")
        self.assertNotEqual(c["manifest_digest"], d["manifest_digest"])

    def test_bad_build_missing_sidecar_or_sources_creates_nothing(self):
        with patch.object(stage.native, "check_game_build", return_value={"compatible": False}):
            with self.assertRaises(stage.StageError): self.prepare()
        self.assertFalse((self.base / "one-output").exists())
        Path(str(self.save) + ".lua").unlink()
        with self.assertRaises(stage.StageError): self.prepare()
        self.assertFalse((self.base / "one-output").exists())
        Path(str(self.save) + ".lua").write_bytes(b"metadata")
        (self.root / "prototype/native/out/probe_alut.dll").unlink()
        with self.assertRaises(stage.StageError): self.prepare()
        self.assertFalse((self.base / "one-output").exists())

    def test_existing_or_nested_paths_never_overwritten(self):
        existing = self.base / "one-session"
        existing.mkdir()
        (existing / "native_control.txt").write_bytes(b"old permit")
        with self.assertRaises(stage.StageError): self.prepare()
        self.assertEqual((existing / "native_control.txt").read_bytes(), b"old permit")
        self.assertFalse((self.base / "one-output").exists())
        for output, session in ((self.game / "new-stage", self.base / "unused"),
                                (self.base / "outside", self.game / "new-session"),
                                (self.base / "outer", self.base / "outer/inner")):
            with self.subTest(output=output), self.assertRaises(stage.StageError):
                stage.stage_probe(game_dir=self.game, save=self.save, session=session, output=output,
                                  repository_root=self.root)
        self.assertFalse((self.game / "new-stage").exists())

    def test_invalid_binding_metadata_rejected(self):
        good = {"logical_id": "seed:x", "kind": "vehicle", "entity": 1}
        cases = [[dict(good, entity=True)], [dict(good, entity=0)], [dict(good, kind="unknown")],
                 [dict(good, logical_id="bad\\key")], [good, dict(good)],
                 [good, dict(good, logical_id="seed:y")],
                 [{"logical_id": "seed:d", "kind": "depot", "entity": 1},
                  {"logical_id": "seed:d:depot:1", "kind": "vehicle", "entity": 2}]]
        for index, bindings in enumerate(cases):
            with self.subTest(bindings=bindings), self.assertRaises(stage.StageError):
                self.prepare(str(index), templates=self.template(bindings))

    def test_duplicate_json_keys_and_floats_rejected(self):
        path = self.base / "bad.json"
        for text in ('{"initial_bindings":[],"initial_bindings":[]}',
                     '{"initial_bindings":[{"logical_id":"x","kind":"vehicle","entity":1.5}]}',
                     '{"initial_bindings":[]}' + ' ' * 65536):
            path.write_text(text)
            with self.assertRaises(ValueError): self.prepare(templates=path)

    def test_only_verified_original_audio_is_staged(self):
        (self.game / "alut.dll").write_bytes(dll_bytes(b"unknown proxy"))
        with self.assertRaises(stage.StageError): self.prepare()
        backup = self.game / stage.native.STATE_DIR / "original/alut.dll"
        backup.parent.mkdir(parents=True)
        backup.write_bytes(self.stock)
        result = self.prepare("backup")
        self.assertEqual((Path(result["output"]) / "game/alut_real.dll").read_bytes(), self.stock)

    def test_copy_race_leaves_no_activatable_setup(self):
        original_copy = stage.shutil.copyfile
        def corrupt(source, target):
            result = original_copy(source, target)
            if Path(target).name == "initial.sav": Path(target).write_bytes(b"changed during copy")
            return result
        with patch.object(stage.shutil, "copyfile", side_effect=corrupt):
            with self.assertRaises(stage.StageError): self.prepare()
        self.assertFalse((self.base / "one-session/probe_setup.json").exists())

    def test_safe_integer_epoch_required(self):
        for epoch in (0, True, 1 << 53, -1):
            with self.subTest(epoch=epoch), self.assertRaises(stage.StageError):
                self.prepare(native_epoch=epoch)

    def test_loader_path_limit_counts_utf16_before_creating_directories(self):
        prefix = str(self.base) + "\\"
        units = len(prefix.encode("utf-16-le")) // 2
        valid = prefix + "x" * (219 - units)
        stage.validate_lease_path(valid)
        for text in (valid + "x", valid[:-1] + "\U0001f680"):
            with self.subTest(path=text), self.assertRaises(stage.StageError):
                stage.validate_lease_path(text)
        long_session = Path(prefix + "s" * (220 - units))
        with self.assertRaises(stage.StageError):
            stage.stage_probe(game_dir=self.game, save=self.save, session=long_session,
                              output=self.base / "long-output", repository_root=self.root)
        self.assertFalse((self.base / "long-output").exists())
        self.assertFalse(long_session.exists())
        long_game = Path(prefix + "g" * (220 - units))
        with self.assertRaises(stage.StageError):
            stage.stage_probe(game_dir=long_game, save=self.save, session=self.base / "fresh-session",
                              output=self.base / "fresh-output", repository_root=self.root)
        self.assertFalse((self.base / "fresh-output").exists())


if __name__ == "__main__":
    unittest.main()
