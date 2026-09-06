import hashlib
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from coop.native import (check_game_build, install_native, uninstall_native, prepare_session,
                         NativeError, EXPECTED_TIMESTAMP, EXPECTED_IMAGE_SIZE, DLL_NAMES)


def pe_bytes(dll=False, timestamp=EXPECTED_TIMESTAMP, image_size=EXPECTED_IMAGE_SIZE, suffix=b""):
    value = bytearray(256)
    value[:2] = b"MZ"
    struct.pack_into("<I", value, 0x3C, 64)
    value[64:68] = b"PE\0\0"
    struct.pack_into("<H", value, 68, 0x8664)
    struct.pack_into("<I", value, 72, timestamp)
    struct.pack_into("<H", value, 86, 0x2000 if dll else 2)
    struct.pack_into("<H", value, 88, 0x20B)
    struct.pack_into("<I", value, 144, image_size)
    return bytes(value) + suffix


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.game, self.runtime, self.mod = self.root / "game", self.root / "runtime", self.root / "source"
        (self.game / "res").mkdir(parents=True)
        self.runtime.mkdir()
        (self.mod / "res/config/game_script").mkdir(parents=True)
        self.original = pe_bytes(dll=True, suffix=b"stock audio")
        exe = pe_bytes(suffix=b"supported test exe")
        (self.game / "TransportFever2.exe").write_bytes(exe)
        (self.game / "alut.dll").write_bytes(self.original)
        for name in DLL_NAMES:
            (self.runtime / name).write_bytes(pe_bytes(dll=True, suffix=name.encode()))
        (self.mod / "mod.lua").write_text("function data() return {} end")
        (self.mod / "res/config/game_script/lockstep.lua").write_text("test lockstep")
        self.patches = [patch("coop.native.EXPECTED_SHA256", hashlib.sha256(exe).hexdigest()),
                        patch("coop.native.STOCK_ALUT_SHA256", hashlib.sha256(self.original).hexdigest()),
                        patch("coop.native.game_is_running", return_value=False)]
        for mocked in self.patches:
            mocked.start()
            self.addCleanup(mocked.stop)

    def install(self):
        return install_native(self.game, self.runtime, self.mod)

    def test_build_check_rejects_changed_binary_even_with_same_pe_metadata(self):
        self.assertTrue(check_game_build(self.game)["compatible"])
        with (self.game / "TransportFever2.exe").open("ab") as file:
            file.write(b"modified")
        self.assertFalse(check_game_build(self.game)["compatible"])
        with self.assertRaises(NativeError):
            self.install()
        self.assertEqual((self.game / "alut.dll").read_bytes(), self.original)

    def test_build_check_rejects_truncated_pe(self):
        (self.game / "TransportFever2.exe").write_bytes(b"MZ")
        self.assertFalse(check_game_build(self.game)["compatible"])

    def test_install_and_uninstall_restore_exact_original(self):
        result = self.install()
        self.assertTrue(result["installed"])
        self.assertTrue(check_game_build(self.game)["installed"])
        self.assertEqual((self.game / "alut_real.dll").read_bytes(), self.original)
        self.assertNotEqual((self.game / "alut.dll").read_bytes(), self.original)
        self.assertTrue((self.game / "mods/mp_lockstep_1/mod.lua").exists())
        self.assertTrue(uninstall_native(self.game)["restored_original_audio"])
        self.assertEqual((self.game / "alut.dll").read_bytes(), self.original)
        self.assertFalse((self.game / "alut_real.dll").exists())
        self.assertFalse((self.game / "tpf2_bridge_mp.dll").exists())
        self.assertFalse((self.game / "mods/mp_lockstep_1").exists())
        self.assertFalse((self.game / ".tf2coop-native").exists())

    def test_install_is_idempotent_and_allows_pristine_update(self):
        self.install()
        self.assertFalse(self.install()["changed"])
        (self.mod / "mod.lua").write_text("updated mod")
        self.assertTrue(self.install()["changed"])
        self.assertEqual((self.game / "mods/mp_lockstep_1/mod.lua").read_text(), "updated mod")
        uninstall_native(self.game)
        self.assertEqual((self.game / "alut.dll").read_bytes(), self.original)

    def test_unknown_audio_proxy_and_native_files_are_not_overwritten(self):
        (self.game / "tpf2_slice.dll").write_bytes(b"another tool")
        with self.assertRaises(NativeError):
            self.install()
        self.assertEqual((self.game / "tpf2_slice.dll").read_bytes(), b"another tool")
        (self.game / "tpf2_slice.dll").unlink()
        (self.game / "alut.dll").write_bytes(b"another audio proxy")
        with self.assertRaises(NativeError):
            self.install()
        self.assertEqual((self.game / "alut.dll").read_bytes(), b"another audio proxy")

    def test_unknown_existing_lockstep_mod_is_preserved(self):
        target = self.game / "mods/mp_lockstep_1"
        target.mkdir(parents=True)
        (target / "mod.lua").write_text("mine")
        with self.assertRaises(NativeError):
            self.install()
        self.assertEqual((target / "mod.lua").read_text(), "mine")

    def test_changed_installed_files_and_backup_prevent_uninstall(self):
        self.install()
        for relative in ("tpf2_slice.dll", "mods/mp_lockstep_1/mod.lua", ".tf2coop-native/original/alut.dll"):
            with self.subTest(relative=relative):
                file = self.game / relative
                prior = file.read_bytes()
                file.write_bytes(b"user edit")
                with self.assertRaises(NativeError):
                    uninstall_native(self.game)
                self.assertEqual(file.read_bytes(), b"user edit")
                file.write_bytes(prior)

    def test_extra_mod_file_prevents_update_and_uninstall(self):
        self.install()
        extra = self.game / "mods/mp_lockstep_1/user.lua"
        extra.write_text("user extension")
        with self.assertRaises(NativeError):
            self.install()
        with self.assertRaises(NativeError):
            uninstall_native(self.game)
        self.assertTrue(extra.exists())

    def test_install_failure_restores_previous_audio_and_removes_new_files(self):
        actual_replace = os.replace
        def replace(src, dst):
            if Path(dst).name == "tpf2_slice.dll":
                raise PermissionError("locked slice")
            actual_replace(src, dst)
        with patch("coop.native.os.replace", side_effect=replace):
            with self.assertRaises(NativeError):
                self.install()
        self.assertEqual((self.game / "alut.dll").read_bytes(), self.original)
        self.assertFalse((self.game / "tpf2_bridge_mp.dll").exists())
        self.assertFalse((self.game / ".tf2coop-native").exists())
        self.assertEqual(list(self.game.glob(".tf2coop-native-*")), [])

    def test_uninstall_failure_keeps_working_installed_version(self):
        self.install()
        actual_replace = os.replace
        fail_once = []
        def replace(src, dst):
            if Path(dst).name == "alut.dll" and not fail_once:
                fail_once.append(True)
                raise PermissionError("locked audio")
            actual_replace(src, dst)
        with patch("coop.native.os.replace", side_effect=replace):
            with self.assertRaises(NativeError):
                uninstall_native(self.game)
        self.assertTrue(check_game_build(self.game)["installed"])

    def test_missing_dll_build_does_not_modify_game(self):
        (self.runtime / "alut.dll").unlink()
        with self.assertRaises(NativeError):
            self.install()
        self.assertEqual((self.game / "alut.dll").read_bytes(), self.original)
        self.assertFalse((self.game / ".tf2coop-native").exists())

    def test_session_is_fresh_has_inverse_ports_and_no_save_server(self):
        self.install()
        host = prepare_session(self.game, self.root / "sessions", "host", "25.1.2.3")
        guest = prepare_session(self.game, self.root / "sessions", "guest", "25.4.5.6")
        next_host = prepare_session(self.game, self.root / "sessions", "host", "25.1.2.3")
        self.assertNotEqual(host["data_dir"], next_host["data_dir"])
        self.assertEqual(host["udp_port"], guest["peer_port"])
        self.assertEqual(host["peer_port"], guest["udp_port"])
        self.assertEqual(host["env"]["TF2COOP_SESSION"], "1")
        self.assertEqual(host["env"]["TPF2MP_DATADIR"], host["data_dir"])
        config = Path(host["config_path"]).read_text()
        self.assertIn("xfer_port=0\n", config)
        self.assertIn("buy_hook=0\n", config)
        self.assertEqual((Path(host["data_dir"]) / "tpf2_instance.txt").read_text(), "a\n")
        self.assertIn("expect_players=2", (Path(host["data_dir"]) / "tpf2_slice.cfg").read_text())

    def test_session_requires_install_and_valid_unicast_ip(self):
        with self.assertRaises(NativeError):
            prepare_session(self.game, self.root / "sessions", "host", "127.0.0.1")
        self.install()
        for peer in ("localhost", "1.2.3.4\nxfer_port=7871", "0.0.0.0", "224.0.0.1", "255.255.255.255"):
            with self.subTest(peer=peer), self.assertRaises(NativeError):
                prepare_session(self.game, self.root / "sessions", "host", peer)
        self.assertFalse((self.root / "sessions").exists())

    def test_running_game_prevents_install_removal_and_another_session(self):
        with patch("coop.native.game_is_running", return_value=True), self.assertRaises(NativeError):
            self.install()
        self.assertFalse((self.game / ".tf2coop-native").exists())
        self.install()
        with patch("coop.native.game_is_running", return_value=True):
            with self.assertRaises(NativeError):
                uninstall_native(self.game)
            with self.assertRaises(NativeError):
                prepare_session(self.game, self.root / "sessions", "host", "25.1.2.3")
        self.assertTrue(check_game_build(self.game)["installed"])
        self.assertFalse((self.root / "sessions").exists())


if __name__ == "__main__":
    unittest.main()
