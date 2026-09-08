"""Real preparation/install/driver boundaries, entirely in temporary game trees.

Only the supported Windows executable/audio identities and process-presence
checks are fixtures. Staging, installation, manifest checks, input queues and
journal-based restoration all run without replacement functions.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from coop.install import _files
from prototype.strict_sync import game_runner as driver
from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync import probe_install as install
from prototype.strict_sync import stage_probe as stage
from prototype.strict_sync.core import digest
from prototype.strict_sync.live_input import InputReader
from prototype.strict_sync.short_build_profile import SHORT_BUILD_CONTRACT
from prototype.strict_sync.test_pairing import connection_receipt, load_profile, save_profile
from prototype.tests.test_stage_probe import dll_bytes


class PreparationPipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "source"
        self.game = self.base / "game"
        self.saves = self.base / "save"
        self.game.mkdir()
        (self.game / "res").mkdir()
        self.saves.mkdir()
        executable = b"supported fixture executable"
        (self.game / "TransportFever2.exe").write_bytes(executable)
        stock = dll_bytes(b"fixture stock audio")
        (self.game / "alut.dll").write_bytes(b"preexisting alpha proxy")
        (self.game / "alut_real.dll").write_bytes(stock)
        (self.game / "other.dll").write_bytes(b"unrelated library")
        old_mod = self.game / "mods/tf2coop_1/mod.lua"
        old_mod.parent.mkdir(parents=True)
        old_mod.write_bytes(b"preexisting alpha mod")
        self.original = self.saves / "original.sav"
        self.original.write_bytes(b"original shared world")
        Path(str(self.original) + ".lua").write_bytes(
            b"return { name = 'Private original title' }\r\n")
        self.original_game = _files(self.game)
        self.original_saves = _files(self.saves)

        # The reader verifies executing Python bytes against the manifest. Use
        # the actual source files, rather than weakening that production check.
        python_source = self.root / "prototype/strict_sync"
        python_source.mkdir(parents=True)
        for source in Path(stage.__file__).parent.glob("*.py"):
            shutil.copyfile(source, python_source / source.name)
        for name in stage.REQUIRED_MOD_FILES | stage.REQUIRED_BUILD_FILES:
            target = self.root / "prototype/mod" / stage.MOD / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("-- fixture " + name + "\nreturn {}\n", encoding="utf-8")
        native_output = self.root / "prototype/native/out"
        native_output.mkdir(parents=True)
        (native_output / "probe_alut.dll").write_bytes(dll_bytes(b"fixture proxy"))
        (native_output / "tf2_step_probe.dll").write_bytes(dll_bytes(b"fixture runtime"))

        game_hash = hashlib.sha256(executable).hexdigest()
        patches = (
            patch.object(stage.native, "EXPECTED_SHA256", game_hash),
            patch.object(driver, "EXPECTED_SHA256", game_hash),
            patch.object(stage.native, "STOCK_ALUT_SHA256", hashlib.sha256(stock).hexdigest()),
            patch.object(stage.native, "check_game_build", return_value={
                "compatible": True, "sha256": game_hash}),
            patch.object(stage.native, "game_is_running", return_value=False),
            patch.object(workflow, "game_is_running", return_value=False),
            patch.dict(os.environ, {"LOCALAPPDATA": str(self.base / "local")}),
        )
        for context in patches:
            context.start()
            self.addCleanup(context.stop)

    def game_bytes(self):
        return {name: value for name, value in _files(self.game).items()
                if not name.startswith(install.STATE_DIR + "/")}

    def assert_original_saves(self):
        actual = _files(self.saves)
        self.assertEqual({name: actual[name] for name in self.original_saves}, self.original_saves)

    def prepare(self, mode, role="a"):
        return workflow.prepare(self.game, self.saves, role, "127.0.0.1", "1234-" * 7 + "1234",
                                source_root=self.root, save=self.original,
                                runs_root=self.base / "runs", test_mode=mode)

    def stage_short(self, name):
        output, session = self.base / (name + "-payload"), self.base / (name + "-session")
        stage.stage_probe(game_dir=self.game, save=self.original, session=session,
                          output=output, repository_root=self.root, native_epoch=55,
                          profile="build_v2", preparation=SHORT_BUILD_CONTRACT)
        return output, session

    def rebind_semantics(self, output, session, semantics):
        manifest = json.loads((session / "probe_manifest.json").read_text(encoding="utf-8"))
        manifest["config_semantics"] = semantics
        for path in (session / "probe_manifest.json", output / "probe_manifest.json"):
            path.write_text(json.dumps(manifest), encoding="utf-8")
        setup_path = session / "probe_setup.json"
        setup = json.loads(setup_path.read_text(encoding="utf-8"))
        setup["manifest_digest"] = digest(manifest)
        setup_path.write_text(json.dumps(setup), encoding="utf-8")

    def test_all_five_modes_reach_the_actual_driver_and_restore_exactly(self):
        file_manifests, lobby_manifests, imported_names = {}, {}, set()
        for mode in workflow.TEST_MODES:
            for role in ("a", "b"):
                with self.subTest(mode=mode, role=role):
                    private_profile = save_profile(workflow.local_root(), host="127.0.0.1",
                                                   code="1234-" * 7 + "1234", role=role)
                    prepared = self.prepare(mode, role)
                    self.assertTrue(install.installation_status(self.game)["installed"])
                    session, setup = driver.read_setup(prepared.session)
                    shared = json.loads((session / "probe_manifest.json").read_text(encoding="utf-8"))
                    short = mode in (workflow.PACED_LIVE_MODE, workflow.MANUAL_DEPOT_MODE)
                    expected_semantics = {"enabled": True, "native_gate_required": True, "profile": "build_v2"}
                    if short:
                        expected_semantics["preparation"] = SHORT_BUILD_CONTRACT
                    if mode == workflow.MANUAL_DEPOT_MODE:
                        expected_semantics["input_mode"] = "manual_depot_v1"
                    self.assertEqual(shared["config_semantics"], expected_semantics)
                    self.assertEqual(setup["measurement_preparation"], SHORT_BUILD_CONTRACT if short else None)
                    self.assertEqual(setup["measurement_input_mode"],
                                     "manual_depot_v1" if mode == workflow.MANUAL_DEPOT_MODE else None)
                    self.assertEqual(setup["manifest_digest"], digest(shared))
                    self.assertEqual(prepared.manifest, workflow.lobby_manifest(digest(shared), mode))
                    self.assertEqual(file_manifests.setdefault(mode, digest(shared)), digest(shared))
                    self.assertEqual(lobby_manifests.setdefault(mode, prepared.manifest), prepared.manifest)

                    # Consume actual launcher worker arguments through the driver
                    # boundary without starting a controller or native process.
                    controller = workflow.SessionController(prepared)
                    self.assertFalse(prepared.live_input_path.exists())
                    with self.assertRaisesRegex(ValueError, "noch nicht bestätigt"):
                        controller._game_args("peer")
                    # The loopback lobby tests exercise the signed exchange.
                    # Here carry its authenticated result across the actual
                    # prepare -> installer -> queue -> driver boundary.
                    epoch = "f" * 32
                    connected = {"protocol": 2, "state": "connected", "role": role,
                                 "local_run": prepared.local_run, "epoch": epoch, "manifest": prepared.manifest}
                    connected["run_proof"] = connection_receipt(
                        (prepared.directory / "pairing.key").read_bytes(), role=role,
                        local_run=prepared.local_run, epoch=epoch, manifest=prepared.manifest)
                    controller._activate_connection(connected)
                    for worker in ("host", "peer"):
                        command = controller._game_args(worker)
                        args = SimpleNamespace(
                            profile=command[command.index("--profile") + 1],
                            rounds=command[command.index("--rounds") + 1],
                            timeout=command[command.index("--timeout") + 1], delay_ms=0,
                            timing_probe="--timing-probe" in command,
                            stream_probe="--stream-probe" in command,
                            live_probe="--live-probe" in command,
                            paced_live_probe="--paced-live-probe" in command,
                            manual_depot_probe="--manual-depot-probe" in command)
                        self.assertEqual(args.rounds, 10 if short else 240)
                        self.assertEqual(driver.selected_profile(args, setup), "build_v2")
                        self.assertEqual("--live-input-file" in command,
                                         worker == "peer" and mode in workflow.LIVE_MODES)
                    driver.verify_payload(session, setup)

                    self.assertEqual(prepared.live_input_path.is_file(), mode in workflow.LIVE_MODES)
                    if mode in workflow.LIVE_MODES:
                        self.assertEqual(InputReader(prepared.live_input_path, prepared.epoch, role).take(), [])
                    imported = Path(prepared.imported_save)
                    self.assertNotIn(imported.name, imported_names)
                    imported_names.add(imported.name)
                    self.assertEqual(imported.read_bytes(), self.original.read_bytes())
                    self.assertEqual(Path(str(imported) + ".lua").read_bytes(),
                                     Path(str(self.original) + ".lua").read_bytes())
                    self.assert_original_saves()
                    restored = install.restore_probe(self.game)
                    self.assertTrue(restored["restored"])
                    self.assertEqual(self.game_bytes(), self.original_game)
                    self.assert_original_saves()
                    self.assertTrue(imported.is_file())
                    self.assertFalse(install.installation_status(self.game)["installed"])
                    self.assertEqual(load_profile(workflow.local_root()), private_profile)

        old = [file_manifests[mode] for mode in (workflow.LIVE_MODE, workflow.STREAM_MODE, workflow.TIMING_MODE)]
        self.assertEqual(len(set(old)), 1)  # Old full recipes retain their shared file identity.
        self.assertNotIn(file_manifests[workflow.PACED_LIVE_MODE], old)
        self.assertNotIn(file_manifests[workflow.MANUAL_DEPOT_MODE], [*old, file_manifests[workflow.PACED_LIVE_MODE]])
        self.assertEqual(len(set(lobby_manifests.values())), 5)

    def test_unknown_or_incompatible_semantics_fail_before_any_game_or_save_write(self):
        valid = {"enabled": True, "native_gate_required": True,
                 "profile": "build_v2", "preparation": SHORT_BUILD_CONTRACT}
        invalid = {
            "unknown_field": {**valid, "unchecked_behavior": True},
            "unknown_preparation": {**valid, "preparation": "short_scene_v2"},
            "wrong_profile": {**valid, "profile": "time_v1"},
            "unknown_profile": {**valid, "profile": "unverified"},
            "missing_profile": {key: value for key, value in valid.items() if key != "profile"},
            "disabled_gate": {**valid, "native_gate_required": False},
            "disabled_mod": {**valid, "enabled": False},
            "integer_gate": {**valid, "native_gate_required": 1},
            "integer_enabled": {**valid, "enabled": 1},
            "null_preparation": {**valid, "preparation": None},
            "unknown_input_mode": {**valid, "input_mode": "manual_depot_v2"},
            "boolean_input_mode": {**valid, "input_mode": True},
            "null_input_mode": {**valid, "input_mode": None},
            "missing_short_input_mode": {"enabled": True, "native_gate_required": True,
                                          "profile": "build_v2", "input_mode": "manual_depot_v1"},
        }
        for name, semantics in invalid.items():
            with self.subTest(semantics=name):
                output, session = self.stage_short(name)
                self.rebind_semantics(output, session, semantics)
                with self.assertRaises(install.ProbeInstallError):
                    install.install_probe(self.game, output, self.saves, session_dir=session)
                self.assertEqual(_files(self.game), self.original_game)
                self.assertEqual(_files(self.saves), self.original_saves)
                self.assertFalse((self.game / install.STATE_DIR).exists())

    def test_wrong_epoch_still_fails_before_game_writes_for_the_short_mode(self):
        output, session = self.stage_short("wrong-epoch")
        (session / "probe_epoch.txt").write_text("56\n", encoding="ascii")
        with self.assertRaisesRegex(install.ProbeInstallError, "epoch"):
            install.install_probe(self.game, output, self.saves, session_dir=session)
        self.assertEqual(_files(self.game), self.original_game)
        self.assertEqual(_files(self.saves), self.original_saves)

    def test_invalid_preparation_is_rejected_by_staging_before_outputs_exist(self):
        for index, (profile, preparation) in enumerate((
                ("build_v2", "unknown"), ("time_v1", SHORT_BUILD_CONTRACT),
                (None, SHORT_BUILD_CONTRACT))):
            with self.subTest(profile=profile, preparation=preparation):
                output, session = self.base / f"bad-{index}-payload", self.base / f"bad-{index}-session"
                with self.assertRaises(stage.StageError):
                    stage.stage_probe(game_dir=self.game, save=self.original, session=session,
                                      output=output, repository_root=self.root,
                                      profile=profile, preparation=preparation)
                self.assertFalse(output.exists())
                self.assertFalse(session.exists())
                self.assertEqual(_files(self.game), self.original_game)
                self.assertEqual(_files(self.saves), self.original_saves)


if __name__ == "__main__":
    unittest.main()
