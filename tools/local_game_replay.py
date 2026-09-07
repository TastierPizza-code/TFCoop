"""One explicitly requested real TF2 process, controlled without desktop input.

Private developer tool: stage, install, load one imported save, record OR replay,
quit that process, then restore. It never contacts a peer or publishes evidence.
Importing this module does not install or launch anything.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coop.install import _lua_string
from coop.launch import LaunchLease, filetime_now, process_info
from coop.session import hash_file
from prototype.strict_sync.engine_mailbox import _shared_read
from prototype.strict_sync.game_runner import (ControllerGuard, claim_fresh_session,
    halt_before_adapter, read_setup, startup_facts, verify_payload)
from prototype.strict_sync.local_replay import run_local_replay
from prototype.strict_sync.probe_install import (_require_closed, install_probe,
    installation_status, restore_probe)
from prototype.strict_sync.stage_probe import stage_probe, validate_lease_path


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
LOG_LIMIT = 64 * 1024 * 1024


def _ordinary(path):
    """Check every existing component before resolving away a link or junction."""
    path = Path(path).absolute()
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Linked or reparse path is unsupported: {item}")
    if path.resolve() != path:
        raise ValueError(f"Noncanonical path is unsupported: {path}")
    return path


def processes():
    """Read only the game's process IDs and command lines, never global logs."""
    code = ('[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); '
            '@(Get-CimInstance Win32_Process -Filter "Name=\'TransportFever2.exe\'" '
            '| Select-Object ProcessId,CommandLine) | ConvertTo-Json -Compress')
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", code],
                            capture_output=True, text=True, encoding="utf-8", check=True,
                            timeout=15, creationflags=CREATE_NO_WINDOW)
    value = json.loads(result.stdout) if result.stdout.strip() else []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list) or len(value) > 32:
        raise RuntimeError("Invalid or ambiguous TF2 process inventory")
    return value


def command_arguments(command_line):
    """Use Windows' argument parser, never substring matching or a shell."""
    if type(command_line) is not str or not command_line or len(command_line) > 32768:
        raise ValueError("Missing or oversized TF2 command line")
    if os.name != "nt":
        raise RuntimeError("Real game orchestration requires Windows")
    from ctypes import wintypes
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    count = ctypes.c_int()
    argv = shell.CommandLineToArgvW(command_line, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(argv)


def _same_path(left, right):
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def script_argument_matches(command_line, game, script):
    args = command_arguments(command_line)
    # The installed console runner consumes --script as its first game argument.
    return bool(len(args) >= 3 and _same_path(args[0], game) and args[1] == "--script"
                and args.count("--script") == 1 and Path(args[2]).is_absolute()
                and _same_path(args[2], script))


def discover_owned(game, script, started):
    """A fresh PID alone is insufficient; require the precise bootstrap script."""
    candidates = []
    for row in processes():
        if type(row) is not dict or type(row.get("ProcessId")) is not int:
            raise RuntimeError("Malformed process identity")
        info = process_info(row["ProcessId"])
        if info is None:
            continue
        if info.created < started or not _same_path(info.executable, game):
            raise RuntimeError("Unowned TF2 process appeared; refusing to operate it")
        candidates.append((info, row.get("CommandLine")))
    if len(candidates) > 1:
        raise RuntimeError("Multiple fresh TF2 processes; ownership is ambiguous")
    if not candidates:
        return None
    info, command_line = candidates[0]
    if not script_argument_matches(command_line, game, script):
        raise RuntimeError("Fresh TF2 process has a different script; refusing ownership")
    return info


class OwnedProcess:
    """Retained kernel handle: an emergency stop cannot target a reused PID."""
    def __init__(self, identity):
        from ctypes import wintypes
        self.identity, self.handle = identity, None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                         wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        handle = self.kernel.OpenProcess(0x1000 | 0x100000 | 0x1, False, identity.pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            executable = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(executable))
            if (not self.kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                               ctypes.byref(system), ctypes.byref(user))
                    or not self.kernel.QueryFullProcessImageNameW(handle, 0, executable, ctypes.byref(length))):
                raise ctypes.WinError(ctypes.get_last_error())
            stamp = (created.dwHighDateTime << 32) | created.dwLowDateTime
            if stamp != identity.created or not _same_path(executable.value, identity.executable):
                raise RuntimeError("TF2 identity changed while acquiring its process handle")
            self.handle = handle
        finally:
            if self.handle is None:
                self.kernel.CloseHandle(handle)

    def alive(self):
        value = self.kernel.WaitForSingleObject(self.handle, 0)
        if value not in (0, 258):
            raise RuntimeError("Cannot determine owned TF2 process state")
        return value == 258

    def terminate(self):
        if self.alive() and not self.kernel.TerminateProcess(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def boot_script(nonce, epoch, run, imported, *, manual_load=False):
    """Console-state API only. No input simulation, save edits or game commands."""
    imported, run = Path(imported), Path(run)
    if (not imported.is_absolute() or imported.suffix.lower() != ".sav"
            or "\n" in str(imported) or "\r" in str(imported)):
        raise ValueError("Invalid absolute imported save path")
    replacements = {"@NONCE@": _lua_string(f"{nonce}|{epoch}|"),
                    "@RUN@": _lua_string(run.as_posix()), "@SAVE_NAME@": _lua_string(imported.name),
                    "@SAVE_PATH@": _lua_string(imported.as_posix())}
    replacements["@MANUAL_BOOT@"] = (r'''
if started then
  issued=true
  marker('manual_load_requested','manual_load_requested|'..save_name)
end
''' if manual_load else "")
    replacements["@LOAD_ACTION@"] = ("-- Manual mode has no automatic loading action." if manual_load else r'''
    if not marker('load_issued','load_issued|'..save_name) then return end
    local loaded,result=pcall(function()return app.loadGame(save_path)end)
    marker('load_result','load_result|call_ok='..tostring(loaded)..'|type='..type(result)..'|value='..scalar(result))
    if not loaded then marker('error','load_failed|'..scalar(result))
    elseif result==false then marker('error','load_rejected|app.loadGame returned false')
    else marker('load_returned','load_returned|'..save_name)end
''')
    code = r'''-- Private, single-load console bootstrap; never a game-script command sender.
local prefix=@NONCE@
local directory=@RUN@
local save_name=@SAVE_NAME@
local save_path=@SAVE_PATH@
local issued,quitting=false,false
local function marker(name,value)
  local ok=pcall(function()
    local f=assert(io.open(directory..'/'..name..'.txt','wb'))
    assert(f:write(prefix..value..'\n'));assert(f:close())
  end)
  return ok
end
local function scalar(value)
  local kind=type(value)
  if kind=='string' then return string.sub(value,1,384):gsub('[%c|]','?')end
  if kind=='nil' or kind=='boolean' or kind=='number' then return tostring(value)end
  return '<not expanded>'
end
local started=marker('started','started')
@MANUAL_BOOT@
local function quit_requested()
  local ok,value=pcall(function()
    local f=io.open(directory..'/control.txt','rb');if not f then return nil end
    local value=f:read(256);f:close();return value
  end)
  return ok and value==prefix..'quit\n'
end
function data()
  return {update=function()
    if quitting then return end
    if quit_requested() then
      quitting=true;marker('quit_requested','quit_requested');app.quit();return
    end
    if not started or issued then return end
    local ok,visible=pcall(function()
      local menu=api.gui.util.getById('menuUI');return menu~=nil and menu:isVisible()
    end)
    if not ok or not visible then return end
    issued=true
@LOAD_ACTION@
  end,handleEvent=function()end}
end
'''
    # One pass: a token-like substring in an escaped path is data, not a second
    # template replacement that could break its Lua string literal.
    return re.sub(r"@(?:NONCE|RUN|SAVE_NAME|SAVE_PATH|LOAD_ACTION|MANUAL_BOOT)@", lambda match: replacements[match[0]], code)


def signal_quit(run, nonce, epoch):
    # Binary writing deliberately preserves LF for the exact Lua comparison.
    _ordinary(Path(run) / "control.txt").write_bytes(f"{nonce}|{epoch}|quit\n".encode("ascii"))


def _marker(run, name, expected):
    try:
        return _shared_read(Path(run) / f"{name}.txt", 1024) == expected.encode("utf-8")
    except (FileNotFoundError, PermissionError):
        return False


def copy_logs(save_dir, output, prefix):
    facts = {}
    for name in ("stdout.txt", "stderr.txt"):
        source = _ordinary(Path(save_dir).parent / "crash_dump" / name)
        if not source.exists():
            facts[name] = {"present": False}
            continue
        raw = _shared_read(source, LOG_LIMIT)
        if len(raw) > LOG_LIMIT:
            raise ValueError(f"Refusing oversized game log backup: {name}")
        target = Path(output) / f"{prefix}-{name}"
        with target.open("xb") as stream:
            stream.write(raw)
        facts[name] = {"present": True, "bytes": len(raw)}
    return facts


def _wait_exit(owned, seconds):
    deadline = time.monotonic() + seconds
    while owned.alive():
        if time.monotonic() >= deadline:
            return False
        time.sleep(.25)
    return True


def _write_report(output, report):
    temporary = output / "result.json.tmp"
    with temporary.open("xb") as stream:
        stream.write((json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii"))
    os.replace(temporary, output / "result.json")


def _hold_uncertain_process(owned, game, script, started, output, report, progress):
    """Exceptional recovery holds the controller alive until an exact exit.

    A startup timeout normally has an owned handle and the bounded quit/terminate
    path succeeds. If Windows cannot establish ownership or exit, returning would
    drop the lifetime guard. Keep evidence visible for the operator instead.
    """
    report["recovery_waiting"] = True
    def publish():
        # Reporting failures must never release a still-required process guard.
        try:
            _write_report(output, report)
        except Exception as exc:
            report["recovery_report_error"] = str(exc)[:512]
    publish()
    last_progress = -float("inf")
    while True:
        try:
            if owned is None:
                identity = discover_owned(game, script, started)
                if identity is not None:
                    owned = OwnedProcess(identity)
                    report.update(pid=identity.pid, process_created=identity.created,
                                  script_argument_verified=True, actual_process_verified=True)
            if owned is not None and not owned.alive():
                report.update(recovery_waiting=False, process_exit_verified=True)
                return owned
        except Exception as exc:
            report["recovery_last_error"] = str(exc)[:512]
        if time.monotonic() - last_progress >= 20:
            try:
                progress("Recovery waiting: exact TF2 exit is unverified; keeping controller and lease, no restore or foreign process stop.")
            except Exception as exc:
                report["recovery_progress_error"] = str(exc)[:512]
            publish()
            last_progress = time.monotonic()
        time.sleep(.5)


def _progress(message):
    print(message, flush=True)


def run_one(*, game_dir, save_dir, baseline, output, steam, replay=None,
            probe_load_only=False, manual_load=False, startup_timeout=600.0, exit_timeout=45.0,
            timeout_s=60.0, max_duration_s=900.0, progress=_progress):
    """Run once; every external operation is replaceable by headless test mocks."""
    for value, cap in ((startup_timeout, 600), (exit_timeout, 60), (timeout_s, 60), (max_duration_s, 3600)):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= cap:
            raise ValueError("Invalid bounded orchestration timeout")
    if probe_load_only and replay is not None:
        raise ValueError("Load-only cannot claim or execute replay")
    game_dir, save_dir, baseline, output, steam = map(_ordinary, (game_dir, save_dir, baseline, output, steam))
    game = game_dir / "TransportFever2.exe"
    if not game.is_file() or not steam.is_file() or steam.name.lower() != "steam.exe":
        raise ValueError("Expected game or Steam executable missing")
    if not save_dir.is_dir() or baseline.suffix.lower() != ".sav" or not baseline.is_file():
        raise ValueError("Missing selected save directory or baseline")
    if not _ordinary(Path(str(baseline) + ".lua")).is_file():
        raise ValueError("Selected baseline sidecar missing")
    if output.exists() or any(output == root or root in output.parents for root in (game_dir, save_dir)):
        raise ValueError("Output must be a fresh directory outside the game and save directories")
    if replay is not None:
        replay = _ordinary(replay)
        if replay.is_dir() and (replay / "measurement").is_dir():
            replay = _ordinary(replay / "measurement")
        if not replay.exists():
            raise ValueError("Replay evidence missing")
    output.mkdir(parents=True, exist_ok=False)
    report = {"scope": "real_tf2_sequential_replay", "mode": "load_only" if probe_load_only else
              "replay" if replay is not None else "record", "passed": False,
              "computer_use": False, "live_network_tested": False, "complete_world_verified": False,
              "manual_load": manual_load,
              "output": str(output), "cleanup_errors": []}
    guard = lease = owned = None
    installed = launched = False
    run = session = setup = None
    nonce = secrets.token_hex(16)
    failure = ""
    try:
        _require_closed()
        if processes():
            raise RuntimeError("Close TF2 before this fresh local run")
        old = installation_status(game_dir)
        if old["installed"]:
            if not old.get("restorable"):
                raise RuntimeError("Previous installation cannot be safely restored")
            report["previous_restore"] = restore_probe(game_dir)
        local = _ordinary(Path(os.environ["LOCALAPPDATA"]) / "TF2StrictProbe")
        run = _ordinary(local / "local" / nonce)
        validate_lease_path(run / "session")
        run.mkdir(parents=True, exist_ok=False)
        session, payload = run / "session", run / "payload"
        report["private_run"] = str(run)
        progress("Preparing a fresh private TF2 run.")
        stage_probe(game_dir=game_dir, save=baseline, session=session, output=payload, profile="build_v2")
        deployment = install_probe(game_dir, payload, save_dir, session_dir=session)
        installed = True
        report["installation"] = deployment
        imported = _ordinary(deployment["imported_save"])
        if imported.parent != save_dir or imported == baseline or not imported.name.startswith("TF2-Koop-Messtest-"):
            raise RuntimeError("Installer did not return a fresh scoped test save")
        session, setup = read_setup(session)
        if setup["measurement_profile"] != "build_v2" or not _same_path(setup["game_exe"], game):
            raise RuntimeError("Prepared run profile or game mismatch")
        manifest = json.loads((session / "probe_manifest.json").read_bytes())
        for suffix, key in (("", "sav_sha256"), (".lua", "sav_lua_sha256")):
            if hash_file(_ordinary(Path(str(imported) + suffix))) != manifest["save"][key]:
                raise RuntimeError("Imported test save differs from the staged baseline")
        script = run / "boot.lua"
        script.write_bytes(boot_script(nonce, setup["native_epoch"], run, imported,
                                       manual_load=manual_load).encode("utf-8"))
        report["script"] = str(script)
        report["logs_before"] = copy_logs(save_dir, output, "before")
        guard = ControllerGuard()
        _require_closed()
        if processes():
            raise RuntimeError("TF2 appeared before this controller's launch")
        verify_payload(session, setup)
        claim_fresh_session(session)
        lease = LaunchLease.create(game, session, lease_root=local)
        started = filetime_now()
        subprocess.Popen([str(steam), "-applaunch", "1066780", "--script", script.as_posix()],
                         creationflags=CREATE_NO_WINDOW)
        launched = True
        report["steam_request_sent"] = True
        if manual_load:
            progress(f"TF2 manuell laden: {imported.name}")
        progress("Steam requested; waiting for the exact process, save load and native/Lua startup.")
        deadline, lease_deadline = time.monotonic() + startup_timeout, time.monotonic() + 120
        prefix = f"{nonce}|{setup['native_epoch']}|"
        last_progress = time.monotonic()
        while True:
            if owned is None:
                identity = discover_owned(game, script, started)
                if identity is not None:
                    owned = OwnedProcess(identity)
                    report.update(pid=identity.pid, process_created=identity.created,
                                  script_argument_verified=True, actual_process_verified=True)
            if owned is not None and not owned.alive():
                raise RuntimeError("Owned TF2 process exited before world readiness")
            ready, facts = startup_facts(session, setup["native_epoch"])
            report["startup"] = facts
            loader = facts["loader"]
            if loader and (loader["protocol"] != 1 or loader["result"] != 0 or
                           (owned is not None and loader["pid"] != owned.identity.pid)):
                raise RuntimeError("Loader PID/result does not belong to this exact fresh process")
            started_marker = _marker(run, "started", prefix + "started\n")
            issued = _marker(run, "load_issued", prefix + "load_issued|" + imported.name + "\n")
            returned = _marker(run, "load_returned", prefix + "load_returned|" + imported.name + "\n")
            manual_requested = manual_load and _marker(run, "manual_load_requested",
                                                       prefix + "manual_load_requested|" + imported.name + "\n")
            report["bootstrap"] = {"started": started_marker, "load_issued": issued,
                                   "load_returned": returned, "manual_load_requested": manual_requested}
            if manual_load:
                report["bootstrap"]["loaded_filename_verified"] = False
            error_file = run / "error.txt"
            if error_file.exists():
                raise RuntimeError("Console save load failed: " + _shared_read(error_file, 1024).decode("utf-8", "replace"))
            load_observed = manual_requested if manual_load else issued and returned
            if ready and owned is not None and loader and started_marker and load_observed:
                report["native_and_lua_ready"] = True
                break
            if time.monotonic() >= lease_deadline and loader is None:
                raise TimeoutError("Native launch lease expired without a verified loader")
            if time.monotonic() >= deadline:
                raise TimeoutError("No verified console/save/native/Lua startup within the deadline")
            if time.monotonic() - last_progress >= 20:
                progress("Still waiting for verified game startup; no simulation permit was sent.")
                last_progress = time.monotonic()
            time.sleep(.25)
        verify_payload(session, setup)
        progress("Actual TF2 startup verified." if probe_load_only else "Actual TF2 startup verified; running bounded local measurement.")
        if not probe_load_only:
            measurement = run_local_replay(session, setup["native_epoch"], output / "measurement",
                baseline=imported, replay=replay, stop_requested=lambda: not owned.alive(),
                timeout_s=timeout_s, max_duration_s=max_duration_s)
            report["measurement"] = measurement
            if measurement.get("passed") is not True:
                raise RuntimeError(measurement.get("reason") or "Local measurement failed")
        report["operation_completed"] = True
    except (Exception, KeyboardInterrupt) as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        # HALT is terminal, never a step permit. Keep lease and guard until the
        # owned process is demonstrably gone, including when measurement failed.
        if lease is not None and setup is not None:
            try:
                halt_before_adapter(session, setup["native_epoch"])
            except Exception as exc:
                report["cleanup_errors"].append(f"Terminal halt: {exc}")
        if launched and run is not None and setup is not None:
            try:
                signal_quit(run, nonce, setup["native_epoch"])
            except Exception as exc:
                report["cleanup_errors"].append(f"Quit signal: {exc}")
        process_ended = not launched
        if owned is not None:
            try:
                process_ended = _wait_exit(owned, exit_timeout)
                report["graceful_exit_verified"] = process_ended
                if not process_ended:
                    report["cleanup_errors"].append("app.quit timeout; terminating only the retained owned TF2 handle")
                    owned.terminate()
                    report["owned_process_terminated"] = True
                    process_ended = _wait_exit(owned, 15)
                report["process_exit_verified"] = process_ended
            except Exception as exc:
                report["cleanup_errors"].append(f"Owned process shutdown: {exc}")
        if launched and not process_ended:
            report["cleanup_errors"].append("Exact process exit required exceptional recovery waiting")
            report["reason"] = failure or report["cleanup_errors"][0]
            owned = _hold_uncertain_process(owned, game, script, started, output, report, progress)
            process_ended = True
        for label, item, method in (("Lease", lease, "revoke"), ("Controller", guard, "close"),
                                    ("Owned handle", owned, "close")):
            if item is not None:
                try:
                    getattr(item, method)()
                except Exception as exc:
                    report["cleanup_errors"].append(f"{label} cleanup: {exc}")
        if installed:
            if process_ended:
                try:
                    report["restoration"] = restore_probe(game_dir)
                    if report["restoration"].get("restored") is not True:
                        raise RuntimeError("Installation restoration was not confirmed")
                except Exception as exc:
                    report["cleanup_errors"].append(f"Restore: {exc}")
            else:
                report["cleanup_errors"].append("Restore deferred: launched process exit or ownership remains unverified")
        try:
            report["logs_after"] = copy_logs(save_dir, output, "after")
        except Exception as exc:
            report["cleanup_errors"].append(f"Final game log copy: {exc}")
        report["reason"] = failure or (report["cleanup_errors"][0] if report["cleanup_errors"] else "")
        report["passed"] = bool(report.get("operation_completed") and not report["reason"])
        _write_report(output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game-dir", "save-dir", "baseline", "output", "steam"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--probe-load-only", action="store_true")
    parser.add_argument("--manual-load", action="store_true")
    parser.add_argument("--startup-timeout", type=float, default=600)
    parser.add_argument("--exit-timeout", type=float, default=45)
    args = parser.parse_args(argv)
    try:
        report = run_one(**vars(args))
    except Exception as exc:
        print(f"Local TF2 run refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
