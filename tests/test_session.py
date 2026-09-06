import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from coop.session import export_save, hash_file, save_manifest


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("mod", "native/out", "upstream/tpf2-multiplayer/mod/mp_lockstep_1"):
            (self.root / folder).mkdir(parents=True)
        (self.root / "mod/mod.lua").write_text("return {}")
        self.save = self.root / "gemeinsam.sav"
        self.save.write_bytes(b"game world")
        Path(str(self.save) + ".lua").write_text("return {}")

    def test_fingerprint_tracks_both_save_components_and_our_payload(self):
        before = save_manifest(self.save, self.root)
        self.save.write_bytes(b"changed world")
        world = save_manifest(self.save, self.root)
        self.assertNotEqual(before["map_fingerprint"], world["map_fingerprint"])
        Path(str(self.save) + ".lua").write_text("return {state=1}")
        self.assertNotEqual(world["map_fingerprint"], save_manifest(self.save, self.root)["map_fingerprint"])
        (self.root / "mod/mod.lua").write_text("return {modified=true}")
        self.assertNotEqual(before["mod_fingerprint"], save_manifest(self.save, self.root)["mod_fingerprint"])

    def test_machine_local_config_is_not_a_compatibility_mismatch(self):
        before = save_manifest(self.save, self.root)
        (self.root / "mod/config.lua").write_text("return {mailbox_dir='local'}")
        self.assertEqual(before, save_manifest(self.save, self.root))

    def test_export_only_selected_save_and_companions_no_overwrite(self):
        (self.root / "unrelated.sav").write_bytes(b"private")
        destination = self.root / "share.zip"
        export_save(self.save, destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(set(archive.namelist()), {"gemeinsam.sav", "gemeinsam.sav.lua", "SHA256.json", "LESEN.txt"})
            self.assertEqual(json.loads(archive.read("SHA256.json"))[self.save.name], hash_file(self.save))
        original = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            export_save(self.save, destination)
        self.assertEqual(original, destination.read_bytes())

    def test_missing_lua_sidecar_is_actionable(self):
        Path(str(self.save) + ".lua").unlink()
        with self.assertRaisesRegex(ValueError, "sav.lua"):
            save_manifest(self.save, self.root)

    def test_export_creation_race_preserves_other_file(self):
        destination = self.root / "race.zip"
        original_open = Path.open

        def raced_open(path, *args, **kwargs):
            if path == destination and args and args[0] == "xb":
                with original_open(destination, "wb") as stream:
                    stream.write(b"someone else's file")
                raise FileExistsError("concurrent creation")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", raced_open):
            with self.assertRaises(FileExistsError):
                export_save(self.save, destination)
        self.assertEqual(destination.read_bytes(), b"someone else's file")
