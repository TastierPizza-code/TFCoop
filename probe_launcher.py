"""Portable Bautest entry point. Worker/self-check modes never open the UI."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import sys
import time
import traceback


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).resolve()


def portable_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else resource_root()


def _hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def _passive_native_check(path: Path) -> dict:
    class Status(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint32) for name in (
            "size", "abi", "initialized", "armed", "halted", "fault", "probe_required", "pending_state"
        )] + [(name, ctypes.c_uint64) for name in (
            "epoch", "completed_frame", "pending_frame", "outer_calls", "hold_calls", "advance_permits",
            "pause_permits", "completed_permits", "first_speed_reads", "second_speed_reads", "original_frame_time_us"
        )] + [(name, ctypes.c_uint32) for name in ("pending_dt_us", "reserved")]
        _fields_ += [(name, ctypes.c_uint64) for name in ("time_before_ms", "time_after_ms")]
    if os.name != "nt":
        raise RuntimeError("native portable self-check requires Windows")
    library = ctypes.CDLL(str(path))
    library.TF2StepProbe_GetStatus.argtypes = [ctypes.POINTER(Status), ctypes.c_uint32]
    library.TF2StepProbe_GetStatus.restype = ctypes.c_uint32
    library.TF2StepProbe_Initialize.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    library.TF2StepProbe_Initialize.restype = ctypes.c_uint32
    before, after = Status(), Status()
    if library.TF2StepProbe_GetStatus(ctypes.byref(before), ctypes.sizeof(before)) != 0:
        raise RuntimeError("native status ABI mismatch")
    if ctypes.sizeof(before) != 144 or before.abi != 3 or before.size != 144:
        raise RuntimeError("native probe requires ABI 3 with unchanged 144-byte status layout")
    if (before.initialized, before.armed, before.outer_calls, before.probe_required) != (0, 0, 0, 1):
        raise RuntimeError("native DLL was not passive on load")
    refused = library.TF2StepProbe_Initialize(3, 0x51554945)
    if refused != 4:  # TF2_PROBE_WRONG_BUILD; this executable is deliberately not TF2.
        raise RuntimeError("native DLL did not refuse this non-game process")
    if library.TF2StepProbe_GetStatus(ctypes.byref(after), ctypes.sizeof(after)) != 0:
        raise RuntimeError("native status failed after refusal")
    if (after.initialized, after.armed, after.outer_calls) != (0, 0, 0):
        raise RuntimeError("native wrong-host check changed engine state")
    return {"passed": True, "abi": 3, "native_step_us": 200000,
            "wrong_host_result": refused, "initialized": 0, "armed": 0}


def _model_workers(directory: Path) -> dict:
    """Run three copies of this exact packaged executable, exclusively on loopback."""
    directory.mkdir(parents=True, exist_ok=False)
    key = directory / "session.key"
    key.write_text(secrets.token_hex(32), encoding="ascii")
    epoch = secrets.token_hex(16)
    base = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    common = ["--epoch", epoch, "--key-file", str(key), "--timeout", "10"]
    processes = []
    def start(name, arguments):
        command = [*base, "--worker-log", str(directory / f"{name}.log"), "--worker", "model",
                   *arguments, *common]
        process = subprocess.Popen(command, cwd=portable_root(), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        processes.append(process)
        return process
    try:
        ready = directory / "ready.json"
        coordinator = start("host", ["host", "--report", str(directory / "host.json"), "--ready", str(ready)])
        deadline = time.monotonic() + 20
        port = None
        while time.monotonic() < deadline and coordinator.poll() is None:
            try:
                port = json.loads(ready.read_text("utf-8"))["port"]
                break
            except (OSError, json.JSONDecodeError):
                time.sleep(.02)
        if type(port) is not int or not 1 <= port <= 65535:
            raise RuntimeError("packaged model host did not become ready; inspect worker logs")
        for name in ("a", "b"):
            start(name, ["peer", "--peer", name, "--host", "127.0.0.1", "--port", str(port),
                         "--report", str(directory / f"{name}.json")])
        deadline = time.monotonic() + 40
        for process in processes:
            process.wait(timeout=max(.1, deadline - time.monotonic()))
        reports = {name: json.loads((directory / f"{name}.json").read_text("utf-8"))
                   for name in ("host", "a", "b")}
        host, a, b = (reports[name] for name in ("host", "a", "b"))
        if (any(process.returncode != 0 for process in processes) or host["halted"]
                or not a["finished"] or not b["finished"]
                or (host["round"], a["round"], b["round"]) != (14, 14, 14)
                or host["state_digest"] != a["state_digest"] or a["state_digest"] != b["state_digest"]
                or a["world"] != b["world"] or a["physical_ids"] == b["physical_ids"]
                or a["world"]["time_us"] != 800000):
            raise RuntimeError("packaged model workers failed to converge; inspect reports")
        return {"passed": True, "backend": "contract_model_only", "rounds": 14,
                "sim_time_us": 800000, "state_digest": host["state_digest"],
                "independent_physical_ids": True, "reports": str(directory)}
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        key.unlink(missing_ok=True)


def self_check(report_path: Path) -> int:
    """Headless physical-resource validation plus packaged model IPC, never TF2."""
    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "frozen": bool(getattr(sys, "frozen", False)),
              "game_started": False, "game_installed": False, "ui_opened": False,
              "actual_tf2_runtime_verified": False}
    with report_path.open("x", encoding="utf-8") as output:
        try:
            from coop import native
            from prototype.strict_sync import stage_probe
            from prototype.strict_sync import probe_install, game_runner
            from prototype.strict_sync.game_runner import read_inputs
            from prototype.strict_sync import launcher_session
            from prototype import diagnostic_session
            from prototype.strict_sync.build_profile import BUILD_PROFILE, BUILD_ROUNDS, build_inputs
            from prototype.strict_sync.timing_probe import SEGMENTS, STEP_US, WINDOW_STEPS, TIMING_CAPABILITY
            from prototype.strict_sync.game_runner import measurement_capabilities
            from prototype.strict_sync.engine_mailbox import EngineAdapter
            from prototype.strict_sync.stream_probe import STREAM_CAPABILITY, CHUNK_STEPS, CHECKPOINT_STEPS, TOTAL_STEPS
            from prototype.strict_sync.stream_engine import StreamEngine
            from prototype.strict_sync.live_probe import LIVE_CAPABILITY, LiveCoordinator, LiveReplica
            from prototype.strict_sync.paced_live_probe import (PACED_LIVE_CAPABILITY,
                PacedLiveCoordinator, PacedLiveReplica, schedule as paced_schedule)
            from prototype.strict_sync.short_build_profile import SHORT_BUILD_ROUNDS, SHORT_BUILD_CONTRACT
            from prototype.strict_sync.coalesced_progress import CoalescedProgress
            from prototype.strict_sync.live_input import InputReader, InputWriter, MAX_REQUESTS, MAX_BATCH
            from prototype.strict_sync.manual_depot_probe import (ManualDepotCoordinator, ManualDepotReplica,
                MANUAL_DEPOT_CAPABILITY, schedule as depot_schedule)
            from prototype.strict_sync.manual_depot_engine import ManualDepotEngineAdapter, ManualDepotStreamEngine
            from prototype.strict_sync.manual_depot_input import validate_command as depot_command
            from prototype.strict_sync import test_pairing
            resources, portable = resource_root(), portable_root()
            physical = resources / "prototype/strict_sync"
            required = set(stage_probe.REQUIRED_PYTHON) | {"model.py", "__init__.py"}
            for name in required:
                if not (physical / name).is_file():
                    raise RuntimeError("missing physical Python source: " + name)
            if stage_probe.ROOT.resolve() != resources:
                raise RuntimeError("frozen staging root does not match physical resources")
            for relative in stage_probe.REQUIRED_MOD_FILES | stage_probe.REQUIRED_BUILD_FILES:
                if not (resources / "prototype/mod/tf2_strict_probe_1" / relative).is_file():
                    raise RuntimeError("missing mod resource: " + relative)
            audit_files = ("mod.lua", "res/config/game_script/tf2_api_audit.lua",
                           "res/scripts/tf2_api_audit/config.lua", "res/scripts/tf2_api_audit/probe.lua",
                           "res/scripts/tf2_api_audit/json.lua")
            for relative in audit_files:
                if not (resources / "prototype/mod/tf2_api_audit_1" / relative).is_file():
                    raise RuntimeError("missing diagnostic mod resource: " + relative)
            result["shared_api_audit_sha256"] = stage_probe.verify_api_audit_copy(resources)
            if not callable(diagnostic_session.prepare_diagnostic) or not callable(diagnostic_session.read_diagnostic_report):
                raise RuntimeError("packaged solo diagnostic workflow is missing")
            examples = resources / "prototype/examples"
            checked_inputs = []
            for path in sorted(examples.glob("*.json")):
                document = json.loads(path.read_text("utf-8"))
                if set(document) == {"rounds"}:
                    read_inputs(path)
                    checked_inputs.append(path.name)
            if not {"time-a.json", "time-b.json"}.issubset(checked_inputs):
                raise RuntimeError("time input profiles are missing")
            if (launcher_session.PROFILE != BUILD_PROFILE or launcher_session.ROUNDS != BUILD_ROUNDS
                    or BUILD_ROUNDS != 240):
                raise RuntimeError("packaged launcher build profile mismatch")
            from types import SimpleNamespace
            if (launcher_session.TIMING_WINDOWS != len(SEGMENTS) or len(SEGMENTS) != 12
                    or launcher_session.PROGRESS_TOTAL != BUILD_ROUNDS + len(SEGMENTS)
                    or STEP_US != 200000 or WINDOW_STEPS != 25
                    or TIMING_CAPABILITY not in measurement_capabilities(SimpleNamespace(timing_probe=True))
                    or not callable(EngineAdapter.advance_window) or not callable(EngineAdapter.check_idle_wait)):
                raise RuntimeError("packaged timing experiment is incomplete")
            if (CHUNK_STEPS != 2 or CHECKPOINT_STEPS != 50 or TOTAL_STEPS != 600
                    or launcher_session.STREAM_STEPS != TOTAL_STEPS
                    or launcher_session.STREAM_CHECKPOINTS != TOTAL_STEPS // CHECKPOINT_STEPS
                    or STREAM_CAPABILITY not in measurement_capabilities(SimpleNamespace(stream_probe=True))
                    or not callable(StreamEngine.advance) or not callable(StreamEngine.checkpoint)
                    or launcher_session.TIMING_MODE not in launcher_session.TEST_MODES):
                raise RuntimeError("packaged stream experiment or comparison mode is incomplete")
            if (LIVE_CAPABILITY not in measurement_capabilities(SimpleNamespace(live_probe=True))
                    or launcher_session.LIVE_MODE not in launcher_session.TEST_MODES
                    or launcher_session.STREAM_MODE not in launcher_session.TEST_MODES
                    or not callable(LiveCoordinator.live_report) or not callable(LiveReplica.live_report)
                    or not callable(InputReader.take) or not callable(InputWriter.submit)
                    or MAX_REQUESTS != 128 or MAX_BATCH != 8):
                raise RuntimeError("packaged live input experiment is incomplete")
            if (PACED_LIVE_CAPABILITY not in measurement_capabilities(SimpleNamespace(paced_live_probe=True))
                    or launcher_session.PACED_LIVE_MODE not in launcher_session.TEST_MODES
                    or launcher_session.preparation_rounds(launcher_session.PACED_LIVE_MODE) != SHORT_BUILD_ROUNDS
                    or SHORT_BUILD_ROUNDS != 10 or SHORT_BUILD_CONTRACT != "short_scene_v1"
                    or not callable(PacedLiveCoordinator.live_report) or not callable(PacedLiveReplica.live_report)
                    or not callable(CoalescedProgress.metrics)
                    or paced_schedule()["separate_input_poll"] is not False
                    or paced_schedule()["checkpoint_steps"] != CHECKPOINT_STEPS):
                raise RuntimeError("packaged short paced-input experiment is incomplete")
            short_config = stage_probe.configuration_semantics("build_v2", SHORT_BUILD_CONTRACT)
            if (probe_install.validate_configuration_semantics is not stage_probe.validate_configuration_semantics
                    or game_runner.validate_configuration_semantics is not stage_probe.validate_configuration_semantics
                    or probe_install.validate_configuration_semantics(short_config) != short_config):
                raise RuntimeError("packaged preparation/installation/startup contracts differ")
            depot_config = stage_probe.configuration_semantics("build_v2", SHORT_BUILD_CONTRACT, "manual_depot_v1")
            if (probe_install.validate_configuration_semantics(depot_config) != depot_config
                    or MANUAL_DEPOT_CAPABILITY not in measurement_capabilities(SimpleNamespace(manual_depot_probe=True))
                    or launcher_session.preparation_rounds(launcher_session.MANUAL_DEPOT_MODE) != SHORT_BUILD_ROUNDS
                    or not callable(ManualDepotCoordinator.live_report) or not callable(ManualDepotReplica.live_report)
                    or not callable(ManualDepotEngineAdapter) or not callable(ManualDepotStreamEngine)
                    or depot_schedule()["chunk_steps"] != CHUNK_STEPS
                    or depot_schedule()["checkpoint_steps"] != CHECKPOINT_STEPS
                    or depot_schedule()["separate_input_poll"] is not False
                    or depot_command({"op": "BUILD_DEPOT", "site": 1, "rotation": 90})["rotation"] != 90
                    or not callable(test_pairing.validate_connection) or not callable(test_pairing.load_profile)):
                raise RuntimeError("packaged manual depot or private pairing integration is incomplete")
            result["manual_depot_profile"] = {"resources_checked": True, "schedule": depot_schedule(),
                                               "private_pairing": True, "game_runtime_verified": False}
            scheduled = [command for number in range(BUILD_ROUNDS) for peer in ("a", "b")
                         for command in build_inputs(peer, number)]
            from collections import Counter
            expected_operations = {"SET_PAUSED": 4, "PROBE_ROAD": 1, "PROBE_DEPOT": 1,
                                   "PROBE_STOP": 2, "PROBE_CONNECT": 1, "PROBE_VEHICLE": 1,
                                   "PROBE_LINE": 1, "PROBE_ASSIGN": 1}
            if Counter(command["op"] for command in scheduled) != expected_operations:
                raise RuntimeError("packaged automatic scene recipe is incomplete")
            manifest = json.loads((portable / "package_manifest.json").read_text("utf-8"))
            result["package_manifest_sha256"] = _hash(portable / "package_manifest.json")
            for name, expected in manifest["files"].items():
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts or ":" in name:
                    raise RuntimeError("unsafe package manifest path")
                target = portable / relative
                if not target.is_file() or _hash(target) != expected:
                    raise RuntimeError("package file/hash mismatch: " + name)
            baseline = manifest.get("baseline", {})
            for name in ("sav_sha256", "sav_lua_sha256"):
                if not isinstance(baseline.get(name), str) or not re.fullmatch(r"[0-9a-f]{64}", baseline[name]):
                    raise RuntimeError("shared local baseline identity is missing")
            if manifest.get("distribution") == "public":
                if any(path.name.endswith((".sav", ".sav.lua", ".key")) for path in portable.rglob("*")):
                    raise RuntimeError("public package contains private state")
            else:
                for name in ("initial.sav", "initial.sav.lua"):
                    if not (portable / "Testspielstand" / name).is_file():
                        raise RuntimeError("private test save pair missing")
            from prototype.release_version import RELEASE_TAG
            from prototype.updater import REPOSITORY
            if manifest.get("release_tag") != RELEASE_TAG or REPOSITORY != "TastierPizza-code/TFCoop":
                raise RuntimeError("packaged release/update identity mismatch")
            if list(portable.rglob("alut_real.dll")) or list(portable.rglob("TransportFever2.exe")):
                raise RuntimeError("package must not contain original game executable/audio")
            for name in ("probe_alut.dll", "tf2_step_probe.dll"):
                if not native._pe(resources / "prototype/native/out" / name)["is_dll"]:
                    raise RuntimeError("invalid native payload DLL")
            result["resources"] = {"passed": True, "verified_files": len(manifest["files"]),
                                   "physical_python_files": sorted(required), "input_profiles": checked_inputs}
            result["build_profile"] = {"profile": BUILD_PROFILE, "rounds": BUILD_ROUNDS,
                                       "scheduled_commands": len(scheduled), "resources_checked": True,
                                       "actual_tf2_construction_verified": False}
            result["timing_profile"] = {"resources_checked": True, "windows": len(SEGMENTS),
                                        "simulated_us": len(SEGMENTS) * WINDOW_STEPS * STEP_US,
                                        "actual_tf2_runtime_verified": False, "visual_smoothness_verified": False}
            result["stream_profile"] = {"resources_checked": True, "chunk_steps": CHUNK_STEPS,
                                        "checkpoint_steps": CHECKPOINT_STEPS, "total_steps": TOTAL_STEPS,
                                        "comparison_mode_available": True,
                                        "actual_tf2_runtime_verified": False, "visual_smoothness_verified": False}
            result["paced_live_profile"] = {"resources_checked": True, "capability": PACED_LIVE_CAPABILITY,
                                            "preparation_contract": SHORT_BUILD_CONTRACT,
                                            "preparation_rounds": SHORT_BUILD_ROUNDS,
                                            "schedule": paced_schedule(),
                                            "full_build_proof": False,
                                            "actual_tf2_runtime_verified": False,
                                            "visual_smoothness_verified": False}
            result["solo_diagnostic"] = {"resources_checked": True, "actual_tf2_runtime_verified": False,
                                          "world_commands": False, "requires_peer": False}
            result["native"] = _passive_native_check(resources / "prototype/native/out/tf2_step_probe.dll")
            worker_dir = report_path.parent / (report_path.stem + "-workers-" + secrets.token_hex(4))
            result["model_workers"] = _model_workers(worker_dir)
            result["passed"] = True
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["traceback"] = traceback.format_exc()
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return 0 if result["passed"] else 2


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    stream = None
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        if arguments[:1] == ["--worker-log"]:
            if len(arguments) < 3:
                raise ValueError("--worker-log requires a log path and worker command")
            log = Path(arguments[1]).resolve()
            log.parent.mkdir(parents=True, exist_ok=True)
            stream = log.open("a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stderr = stream
            arguments = arguments[2:]
        if arguments[:1] == ["--self-check"]:
            if len(arguments) != 2:
                raise ValueError("--self-check requires exactly one JSON report path")
            return self_check(Path(arguments[1]))
        if arguments[:1] == ["--worker"]:
            if len(arguments) < 3 or arguments[1] not in ("game", "model", "lobby"):
                raise ValueError("worker mode requires game/model/lobby followed by worker arguments")
            if arguments[1] == "game":
                from prototype.strict_sync.game_runner import main as worker_main
            elif arguments[1] == "lobby":
                from prototype.strict_sync.lobby import main as worker_main
            else:
                from prototype.strict_sync.runner import main as worker_main
            old_argv = sys.argv
            try:
                sys.argv = [old_argv[0], *arguments[2:]]
                return int(worker_main() or 0)
            finally:
                sys.argv = old_argv
        updated_launch = arguments == ["--updated-launch"]
        if arguments and not updated_launch:
            raise ValueError("unknown launcher arguments")
        from prototype.launcher import main as launcher_main
        return int(launcher_main(skip_update=updated_launch) or 0)
    except BaseException as exc:
        if stream is not None and not isinstance(exc, SystemExit):
            traceback.print_exc(file=stream)
        raise
    finally:
        if stream is not None:
            sys.stdout, sys.stderr = original_stdout, original_stderr
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
