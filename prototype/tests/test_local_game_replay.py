"""Headless orchestration checks: every install, process and game call is mocked."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from coop.launch import ProcessInfo
from tools import local_game_replay as runner


class LocalGameReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.game, self.saves = self.root / "game", self.root / "saves"
        self.game.mkdir()
        self.saves.mkdir()
        self.exe = self.game / "TransportFever2.exe"
        self.exe.write_bytes(b"fixture executable, never launched")
        self.steam = self.root / "steam.exe"
        self.steam.write_bytes(b"fixture Steam, never launched")
        self.baseline = self.saves / "original.sav"
        self.baseline.write_bytes(b"fixture baseline")
        Path(str(self.baseline) + ".lua").write_bytes(b"fixture sidecar")
        self.imported = self.saves / "TF2-Koop-Messtest-fixture.sav"
        self.output = self.root / "output"
        self.identity = ProcessInfo(12345, 999999, str(self.exe))
        self.events = []

    def fixture(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "local")}))
        mocks = {}
        for name in ("_require_closed", "processes", "installation_status", "restore_probe",
                     "stage_probe", "install_probe", "read_setup", "verify_payload", "claim_fresh_session",
                     "ControllerGuard", "LaunchLease", "discover_owned", "OwnedProcess", "startup_facts",
                     "_marker", "run_local_replay", "halt_before_adapter", "_wait_exit", "filetime_now"):
            mocks[name] = stack.enter_context(patch.object(runner, name))
        mocks["Popen"] = stack.enter_context(patch.object(runner.subprocess, "Popen"))
        mocks["processes"].return_value = []
        mocks["installation_status"].return_value = {"installed": False}
        mocks["restore_probe"].side_effect = lambda *_: self.events.append("restore") or {"restored": True}
        mocks["filetime_now"].return_value = self.identity.created - 1

        def stage(**kwargs):
            self.events.append("stage")
            session = kwargs["session"]
            session.mkdir()
            kwargs["output"].mkdir()
            (session / "probe_manifest.json").write_text(json.dumps({"save": {
                "sav_sha256": runner.hash_file(self.baseline),
                "sav_lua_sha256": runner.hash_file(Path(str(self.baseline) + ".lua"))}}))
            return {}

        def install(*args, **kwargs):
            self.events.append("install")
            self.imported.write_bytes(self.baseline.read_bytes())
            Path(str(self.imported) + ".lua").write_bytes(Path(str(self.baseline) + ".lua").read_bytes())
            return {"installed": True, "imported_save": str(self.imported)}

        mocks["stage_probe"].side_effect = stage
        mocks["install_probe"].side_effect = install
        mocks["read_setup"].side_effect = lambda directory: (directory, {"native_epoch": 42,
            "measurement_profile": "build_v2", "game_exe": str(self.exe)})
        mocks["ControllerGuard"].side_effect = lambda: self.events.append("guard") or guard
        guard = Mock()
        guard.close.side_effect = lambda: self.events.append("guard_close")
        lease = mocks["LaunchLease"].create.return_value
        lease.revoke.side_effect = lambda: self.events.append("lease_revoke")
        mocks["discover_owned"].return_value = self.identity
        owned = mocks["OwnedProcess"].return_value
        owned.identity = self.identity
        owned.alive.return_value = True
        owned.close.side_effect = lambda: self.events.append("handle_close")
        mocks["startup_facts"].return_value = (True, {"loader": {"protocol": 1, "pid": 12345, "result": 0},
                                                   "native": {"epoch": 42}, "lua": {"epoch": "42"}})
        mocks["_marker"].return_value = True
        mocks["run_local_replay"].side_effect = lambda *a, **k: self.events.append("measurement") or {"passed": True}
        mocks["halt_before_adapter"].side_effect = lambda *a: self.events.append("halt")
        mocks["_wait_exit"].side_effect = lambda *a: self.events.append("exit") or True
        return mocks

    def run_fixture(self, **kwargs):
        return runner.run_one(game_dir=self.game, save_dir=self.saves, baseline=self.baseline,
                              output=self.output, steam=self.steam, progress=lambda _: None, **kwargs)

    def test_load_only_waits_exact_exit_before_releasing_lease_and_restoring(self):
        mocks = self.fixture()
        report = self.run_fixture(probe_load_only=True, startup_timeout=180)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["live_network_tested"])
        self.assertFalse(report["complete_world_verified"])
        mocks["run_local_replay"].assert_not_called()
        self.assertLess(self.events.index("install"), self.events.index("guard"))
        self.assertLess(self.events.index("exit"), self.events.index("lease_revoke"))
        self.assertLess(self.events.index("guard_close"), self.events.index("restore"))
        args, kw = mocks["Popen"].call_args
        self.assertEqual(args[0][:4], [str(self.steam), "-applaunch", "1066780", "--script"])
        self.assertEqual(args[0][4], Path(report["script"]).as_posix())
        self.assertEqual(kw, {"creationflags": runner.CREATE_NO_WINDOW})
        mocks["Popen"].return_value.terminate.assert_not_called()
        signal = Path(report["private_run"]) / "control.txt"
        self.assertTrue(signal.read_bytes().endswith(b"|42|quit\n"))
        self.assertNotIn(b"\r", signal.read_bytes())

    def test_record_uses_only_imported_baseline_and_preserves_original_pair(self):
        mocks = self.fixture()
        original = (self.baseline.read_bytes(), Path(str(self.baseline) + ".lua").read_bytes())
        report = self.run_fixture()
        self.assertTrue(report["passed"])
        self.assertEqual(mocks["run_local_replay"].call_args.kwargs["baseline"], self.imported)
        self.assertEqual(mocks["run_local_replay"].call_args.args[2], self.output / "measurement")
        self.assertEqual(original, (self.baseline.read_bytes(), Path(str(self.baseline) + ".lua").read_bytes()))

    def test_manual_record_reports_requested_save_without_claiming_auto_load(self):
        mocks = self.fixture()
        mocks["_marker"].side_effect = lambda run, name, expected: name in ("started", "manual_load_requested")
        messages = []
        report = runner.run_one(game_dir=self.game, save_dir=self.saves, baseline=self.baseline,
            output=self.output, steam=self.steam, manual_load=True, progress=messages.append)
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["bootstrap"]["manual_load_requested"])
        self.assertFalse(report["bootstrap"]["load_issued"])
        self.assertFalse(report["bootstrap"]["load_returned"])
        self.assertFalse(report["bootstrap"]["loaded_filename_verified"])
        self.assertIn(f"TF2 manuell laden: {self.imported.name}", messages)
        self.assertNotIn("app.loadGame", Path(report["script"]).read_text(encoding="utf-8"))
        mocks["run_local_replay"].assert_called_once()

    def test_manual_marker_is_required_and_never_replaced_by_auto_markers(self):
        mocks = self.fixture()
        mocks["_marker"].side_effect = lambda run, name, expected: name != "manual_load_requested"
        with patch.object(runner.time, "monotonic", side_effect=range(1000)), patch.object(runner.time, "sleep"):
            report = self.run_fixture(manual_load=True, startup_timeout=.1)
        self.assertFalse(report["passed"])
        mocks["run_local_replay"].assert_not_called()

    def test_manual_request_without_real_world_ready_cannot_start_adapter(self):
        mocks = self.fixture()
        facts = mocks["startup_facts"].return_value[1]
        mocks["startup_facts"].return_value = (False, facts)
        with patch.object(runner.time, "monotonic", side_effect=range(1000)), patch.object(runner.time, "sleep"):
            report = self.run_fixture(manual_load=True, startup_timeout=.1)
        self.assertFalse(report["passed"])
        mocks["run_local_replay"].assert_not_called()

    def test_false_return_error_stops_immediately_without_startup_timeout_or_adapter(self):
        mocks = self.fixture()
        def launch(args, **kwargs):
            (Path(args[4]).parent / "error.txt").write_bytes(b"fixture|42|load_rejected|app.loadGame returned false\n")
        mocks["Popen"].side_effect = launch
        with patch.object(runner.time, "sleep") as sleep:
            report = self.run_fixture(startup_timeout=600)
        self.assertIn("load_rejected", report["reason"])
        mocks["run_local_replay"].assert_not_called()
        sleep.assert_not_called()

    def test_replay_accepts_outer_run_directory(self):
        mocks = self.fixture()
        recorded = self.root / "recorded" / "measurement"
        recorded.mkdir(parents=True)
        report = self.run_fixture(replay=recorded.parent)
        self.assertTrue(report["passed"])
        self.assertEqual(mocks["run_local_replay"].call_args.kwargs["replay"], recorded)

    def test_old_install_is_restored_before_staging(self):
        mocks = self.fixture()
        mocks["installation_status"].return_value = {"installed": True, "restorable": True}
        self.assertTrue(self.run_fixture(probe_load_only=True)["passed"])
        self.assertEqual(self.events[:3], ["restore", "stage", "install"])

    def test_existing_game_is_never_installed_started_or_killed(self):
        mocks = self.fixture()
        mocks["processes"].return_value = [{"ProcessId": 1}]
        self.assertFalse(self.run_fixture()["passed"])
        for name in ("install_probe", "stage_probe", "Popen", "OwnedProcess", "restore_probe"):
            mocks[name].assert_not_called()

    def test_existing_output_refused_before_any_mutation(self):
        mocks = self.fixture()
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh directory"):
            self.run_fixture()
        mocks["install_probe"].assert_not_called()
        mocks["Popen"].assert_not_called()

    def test_wrong_loader_pid_halts_without_measurement_then_restores(self):
        mocks = self.fixture()
        mocks["startup_facts"].return_value[1]["loader"]["pid"] = 98765
        report = self.run_fixture()
        self.assertFalse(report["passed"])
        self.assertIn("Loader PID", report["reason"])
        mocks["run_local_replay"].assert_not_called()
        mocks["halt_before_adapter"].assert_called_once()
        mocks["restore_probe"].assert_called_once()

    def test_missing_console_load_marker_times_out_without_adapter(self):
        mocks = self.fixture()
        mocks["_marker"].return_value = False
        with patch.object(runner.time, "monotonic", side_effect=range(1000)), patch.object(runner.time, "sleep"):
            report = self.run_fixture(startup_timeout=.1)
        self.assertIn("No verified console/save", report["reason"])
        mocks["run_local_replay"].assert_not_called()

    def test_measurement_first_error_survives_failed_restore(self):
        mocks = self.fixture()
        mocks["run_local_replay"].side_effect = RuntimeError("original actual API failure")
        mocks["restore_probe"].side_effect = RuntimeError("later restore failure")
        report = self.run_fixture()
        self.assertIn("original actual API failure", report["reason"])
        self.assertTrue(any("later restore failure" in x for x in report["cleanup_errors"]))
        self.assertFalse(report["passed"])
        self.assertEqual(json.loads((self.output / "result.json").read_bytes())["reason"], report["reason"])

    def test_terminate_targets_only_retained_handle_and_is_not_a_success(self):
        mocks = self.fixture()
        mocks["_wait_exit"].side_effect = [False, True]
        report = self.run_fixture(probe_load_only=True)
        self.assertFalse(report["passed"])
        self.assertTrue(report["owned_process_terminated"])
        mocks["OwnedProcess"].return_value.terminate.assert_called_once()
        mocks["Popen"].return_value.terminate.assert_not_called()
        mocks["restore_probe"].assert_called_once()

    def test_unknown_launch_keeps_guard_and_lease_through_recovery_wait(self):
        mocks = self.fixture()
        mocks["discover_owned"].return_value = None
        mocks["startup_facts"].side_effect = RuntimeError("early native failure")
        def recover(*args):
            self.assertNotIn("lease_revoke", self.events)
            self.assertNotIn("guard_close", self.events)
            mocks["restore_probe"].assert_not_called()
            self.events.append("recovered_exit")
            return mocks["OwnedProcess"].return_value
        with patch.object(runner, "_hold_uncertain_process", side_effect=recover) as recovery:
            report = self.run_fixture()
        recovery.assert_called_once()
        self.assertIn("early native failure", report["reason"])
        self.assertLess(self.events.index("recovered_exit"), self.events.index("guard_close"))

    def test_failed_termination_cannot_release_guard_before_recovery(self):
        mocks = self.fixture()
        mocks["_wait_exit"].return_value = False
        mocks["_wait_exit"].side_effect = None
        mocks["OwnedProcess"].return_value.terminate.side_effect = OSError("cannot terminate")
        def recover(*args):
            self.assertNotIn("guard_close", self.events)
            self.assertNotIn("lease_revoke", self.events)
            mocks["restore_probe"].assert_not_called()
            return mocks["OwnedProcess"].return_value
        with patch.object(runner, "_hold_uncertain_process", side_effect=recover) as recovery:
            report = self.run_fixture()
        recovery.assert_called_once()
        self.assertFalse(report["passed"])

    def test_cleanup_identity_read_error_requires_recovery_before_restore(self):
        mocks = self.fixture()
        mocks["_wait_exit"].side_effect = OSError("cannot inspect process")
        def recover(*args):
            self.assertNotIn("guard_close", self.events)
            mocks["restore_probe"].assert_not_called()
            return mocks["OwnedProcess"].return_value
        with patch.object(runner, "_hold_uncertain_process", side_effect=recover):
            report = self.run_fixture()
        self.assertFalse(report["passed"])

    def test_recovery_report_or_progress_failure_cannot_release_lifetime(self):
        owned, progress = Mock(), Mock(side_effect=BrokenPipeError("closed output"))
        owned.alive.side_effect = [True, False]
        report = {}
        with patch.object(runner, "_write_report", side_effect=PermissionError("locked result")), \
             patch.object(runner.time, "sleep"):
            actual = runner._hold_uncertain_process(owned, self.exe, "boot.lua", 1,
                                                   self.output, report, progress)
        self.assertIs(actual, owned)
        self.assertTrue(report["process_exit_verified"])
        self.assertIn("recovery_report_error", report)
        self.assertIn("recovery_progress_error", report)
        owned.close.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows argument semantics")
    def test_script_argument_is_exact_token_including_spaces(self):
        script = self.root / "folder with spaces" / "boot.lua"
        good = subprocess.list2cmdline([str(self.exe), "--script", script.as_posix()])
        self.assertTrue(runner.script_argument_matches(good, self.exe, script))
        for args in ([str(self.exe), "--script", script.as_posix() + ".other"],
                     [str(self.exe), "--wrong", script.as_posix()],
                     [str(self.exe), "--script", script.as_posix(), "--script", script.as_posix()]):
            self.assertFalse(runner.script_argument_matches(subprocess.list2cmdline(args), self.exe, script))

    def test_discovery_rejects_old_wrong_script_and_ambiguous_processes(self):
        rows = [{"ProcessId": 12345, "CommandLine": "mocked exact script"}]
        with patch.object(runner, "processes", return_value=rows), \
             patch.object(runner, "process_info", return_value=self.identity), \
             patch.object(runner, "script_argument_matches", return_value=True) as match:
            self.assertEqual(runner.discover_owned(self.exe, "boot.lua", 999998), self.identity)
            with self.assertRaisesRegex(RuntimeError, "Unowned"):
                runner.discover_owned(self.exe, "boot.lua", 1000000)
            match.return_value = False
            with self.assertRaisesRegex(RuntimeError, "different script"):
                runner.discover_owned(self.exe, "boot.lua", 999998)
            rows.append({"ProcessId": 23456, "CommandLine": "another"})
            with self.assertRaisesRegex(RuntimeError, "Multiple"):
                runner.discover_owned(self.exe, "boot.lua", 999998)

    def test_log_copy_preserves_original_and_uses_new_private_files(self):
        crash = self.saves.parent / "crash_dump"
        crash.mkdir()
        (crash / "stdout.txt").write_bytes(b"fixture private stdout\r\n")
        self.output.mkdir()
        facts = runner.copy_logs(self.saves, self.output, "before")
        self.assertEqual((self.output / "before-stdout.txt").read_bytes(), (crash / "stdout.txt").read_bytes())
        self.assertTrue(facts["stdout.txt"]["present"])


class LiteralBootTests(unittest.TestCase):
    def make_lua(self):
        deps = Path(__file__).resolve().parents[2] / "tests" / "lua" / ".deps"
        import sys
        if str(deps) not in sys.path:
            sys.path.insert(0, str(deps))
        try:
            from lupa.lua54 import LuaRuntime
        except ImportError:
            self.skipTest("Lupa fixture runtime unavailable")
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(r'''
          files={};loads={};quits=0
          io={open=function(path,mode)
            if mode=='rb' then
              if files[path]==nil then return nil end
              return {read=function()return files[path]end,close=function()return true end}
            end
            return {write=function(self,value)files[path]=value;return self end,
                    close=function()return true end}
          end}
          app={loadGame=function(name)loads[#loads+1]=name end,quit=function()quits=quits+1 end}
          api={gui={util={getById=function()return {isVisible=function()return true end}end}}}
        ''')
        return lua

    def test_console_script_loads_once_and_only_quits_for_exact_nonce_lf(self):
        lua = self.make_lua()
        imported = Path(tempfile.gettempdir()).resolve() / "private folder ö ' @SAVE_PATH@" / "selected.sav"
        script = runner.boot_script("abc", 42, Path("fixture"), imported)
        lua.execute(script)
        lua.execute("state=data();state.update();state.update();state=data();state.update()")
        self.assertEqual(lua.eval("#loads"), 1)
        self.assertEqual(lua.eval("loads[1]"), imported.as_posix())
        self.assertEqual(lua.eval("files['fixture/load_issued.txt']"), "abc|42|load_issued|selected.sav\n")
        self.assertEqual(lua.eval("files['fixture/load_result.txt']"),
                         "abc|42|load_result|call_ok=true|type=nil|value=nil\n")
        lua.execute(r"files['fixture/control.txt']='wrong|42|quit\n';state.update()")
        self.assertEqual(lua.eval("quits"), 0)
        lua.execute(r"files['fixture/control.txt']='abc|42|quit\r\n';state.update()")
        self.assertEqual(lua.eval("quits"), 0)
        lua.execute(r"files['fixture/control.txt']='abc|42|quit\n';state.update();state.update()")
        self.assertEqual(lua.eval("quits"), 1)

    def test_basename_or_newline_path_is_rejected(self):
        for imported in (Path("selected.sav"), Path(tempfile.gettempdir()).resolve() / "bad\nname.sav"):
            with self.assertRaisesRegex(ValueError, "absolute imported save"):
                runner.boot_script("abc", 42, Path("fixture"), imported)

    def test_manual_marker_precedes_updates_and_no_load_call_exists(self):
        lua = self.make_lua()
        imported = Path(tempfile.gettempdir()).resolve() / "chosen.sav"
        script = runner.boot_script("abc", 42, Path("fixture"), imported, manual_load=True)
        self.assertNotIn("app.loadGame", script)
        lua.execute(script)
        self.assertEqual(lua.eval("files['fixture/manual_load_requested.txt']"),
                         "abc|42|manual_load_requested|chosen.sav\n")
        lua.execute("state=data();for i=1,50 do state.update()end;state=data();state.update()")
        self.assertEqual(lua.eval("#loads"), 0)
        self.assertIsNone(lua.eval("files['fixture/load_issued.txt']"))
        self.assertIsNone(lua.eval("files['fixture/load_returned.txt']"))
        lua.execute(r"files['fixture/control.txt']='abc|42|quit\n';state.update();state.update()")
        self.assertEqual(lua.eval("quits"), 1)

    def test_false_return_is_explicit_rejection_and_never_retried(self):
        lua = self.make_lua()
        lua.execute("app.loadGame=function(name)loads[#loads+1]=name;return false end")
        lua.execute(runner.boot_script("abc", 42, Path("fixture"),
                                     Path(tempfile.gettempdir()).resolve() / "chosen.sav"))
        lua.execute("state=data();state.update();state.update()")
        self.assertEqual(lua.eval("#loads"), 1)
        self.assertIsNone(lua.eval("files['fixture/load_returned.txt']"))
        self.assertEqual(lua.eval("files['fixture/error.txt']"),
                         "abc|42|load_rejected|app.loadGame returned false\n")
        self.assertEqual(lua.eval("files['fixture/load_result.txt']"),
                         "abc|42|load_result|call_ok=true|type=boolean|value=false\n")


if __name__ == "__main__":
    unittest.main()
