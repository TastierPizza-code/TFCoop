"""Explicit controlled TF2 measurement driver, separate from the playable Alpha.

Does not install files or start/control game windows. The user must have staged
the diagnostic proxy and mod, then manually start TF2 and load a separate test save.
Normal building tools are outside this experiment. The optional live test accepts
explicit pause/end requests through a bounded local queue after the fixed build.
Every run needs a fresh prepared directory/epoch on each PC.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from coop.launch import LaunchLease
from coop.native import game_is_running, EXPECTED_SHA256
from .core import ProtocolError, decode_message, digest
from .build_profile import (BUILD_PROFILE, BUILD_ROUNDS, TIME_PROFILE, BuildProof, SnapshotJournal,
                            build_inputs, phase_label)
from .engine_mailbox import (ENGINE_STEP_US, EngineAdapter, _decode_json, _shared_read,
                             native_fault_detail, parse_native_status)
from .replica import Replica
from .runner import host, peer_error_message, write_report
from .stage_probe import validate_lease_path
from .transport import authenticate_client, receive, send
from .timing_probe import TimingCoordinator, TimingReplica, TIMING_CAPABILITY
from .stream_probe import StreamCoordinator, StreamReplica, STREAM_CAPABILITY, STREAM_WORLD_RECEIPTS
from .live_probe import LiveCoordinator, LiveReplica, LIVE_CAPABILITY, LIVE_WORLD_RECEIPTS
from .paced_live_probe import (PacedLiveCoordinator, PacedLiveReplica,
                               PACED_LIVE_CAPABILITY, PACED_LIVE_WORLD_RECEIPTS)
from .short_build_profile import (SHORT_BUILD_CONTRACT, SHORT_BUILD_ROUNDS,
                                  ShortBuildProof, short_build_inputs)
from .live_input import InputReader
from .coalesced_progress import CoalescedProgress


CAPABILITIES = tuple(sorted(("experimental_file_mailbox", "lua_actual_snapshots",
                             "native_probe_required", "partial_world_digest")))
PREPARED_FILES = {"probe_setup.json", "probe_manifest.json", "probe_payload.json", "probe_epoch.txt"}


class StopRequested(ProtocolError):
    pass


def external_path(value, directory):
    if value is None:
        return None
    result = Path(value).resolve()
    if result == directory or directory in result.parents:
        raise ValueError("launcher progress/stop files must be outside the fresh session")
    return result


class Progress:
    def __init__(self, path, **identity):
        self.path, self.identity = path, identity
        self.last = None

    def __call__(self, state, **facts):
        if self.path is None:
            return
        value = {"protocol": 1, "backend": "tf2_controlled_measurement", "probe_only": True,
                 "complete_world_verified": False, **self.identity, "state": state,
                 **facts}
        if value == self.last:
            return
        unchanged = value.copy()
        value["updated_at"] = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            deadline = time.monotonic() + .5
            while True:
                try:
                    os.replace(temporary, self.path)
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
            self.last = unchanged
        finally:
            temporary.unlink(missing_ok=True)


def read_optional(path, limit):
    try:
        return _shared_read(path, limit)
    except (FileNotFoundError, PermissionError):
        return None


def startup_facts(directory, epoch):
    """Read real diagnostic files; mere file existence never means world ready."""
    facts = {"loader": None, "native": None, "lua": None}
    raw = read_optional(directory / "loader_status.txt", 4096)
    if raw and raw.endswith(b"\n"):
        try:
            loader = dict(line.split("=", 1) for line in raw.decode("ascii").splitlines())
            if set(loader) == {"protocol", "pid", "result"}:
                facts["loader"] = {key: int(value) for key, value in loader.items()}
        except (UnicodeError, ValueError):
            pass
        if facts["loader"] and facts["loader"]["result"] != 0:
            raise ProtocolError(f"native loader failed: result={facts['loader']['result']}")
    raw = read_optional(directory / "native_status.txt", 4096)
    native = parse_native_status(raw) if raw else None
    if native:
        facts["native"] = {key: native[key] for key in
                           ("abi", "epoch", "ready", "armed", "halted", "fault", "runtime_fault",
                            "outer_calls", "completed_frame", "pending_state", "time_after_ms", "native_step_us")}
        if native["epoch"] != epoch:
            raise ProtocolError("native startup epoch differs from this fresh session")
        if native["halted"] or native["fault"] or native["runtime_fault"]:
            raise ProtocolError(f"native startup halted: {native_fault_detail(native)}")
        if any(native[key] for key in ("completed_frame", "pending_state", "request_received",
                                       "request_acknowledged", "request_completed")):
            raise ProtocolError("native startup already processed work; prepare a fresh session")
        if native["result"] not in (0, 1):
            raise ProtocolError(f"native startup rejected: result={native['result']}")
    raw = read_optional(directory / "lua_status.json", 262144)
    lua = _decode_json(raw) if raw else None
    if lua:
        facts["lua"] = {key: lua.get(key) for key in ("protocol", "epoch", "status", "request", "revision", "error")}
        if lua.get("epoch") != str(epoch):
            raise ProtocolError("Lua startup epoch differs from this fresh session")
        if lua.get("status") == "halted":
            raise ProtocolError(f"Lua startup halted: {lua.get('error', 'no detail')}")
        if lua.get("request") != 0:
            raise ProtocolError("Lua startup already processed work; prepare a fresh session")
    ready = bool(native and native["ready"] and native["initialized"] and native["armed"]
                 and native["outer_calls"] > 0 and lua and lua.get("protocol") == 1
                 and lua.get("status") == "ready" and lua.get("complete") is True
                 and isinstance(lua.get("snapshot"), dict))
    return ready, facts


def halt_before_adapter(directory, epoch):
    """A stopped bootstrap must remain stopped even if its DLL starts late."""
    target = directory / "native_control.txt"
    if target.exists():
        return  # A failed constructor already owns/wrote its terminal control.
    temporary = directory / f".controller_halt.{uuid.uuid4().hex}.tmp"
    try:
        raw = f"protocol=1\nepoch={epoch}\nrequest=1\naction=halt\nframe=0\ndt_us=0\n"
        with temporary.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


async def stoppable(awaitable, stop_requested, timeout):
    """Only cancellable network/wait operations belong here, never engine threads."""
    task = asyncio.ensure_future(awaitable)
    deadline = time.monotonic() + timeout
    try:
        while not task.done():
            if stop_requested():
                raise StopRequested("measurement stopped by local user")
            if time.monotonic() >= deadline:
                raise asyncio.TimeoutError()
            await asyncio.wait({task}, timeout=min(0.1, max(0, deadline - time.monotonic())))
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def claim_fresh_session(directory):
    """Consume the epoch before any game bootstrap can read an old native permit.

    The marker deliberately survives controller failure. Removing controls is not
    a supported restart: the staging tool must produce a fresh directory/epoch.
    The separate OS controller guard serializes this check and lease creation.
    """
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != PREPARED_FILES or any(path.is_symlink() or not path.is_file()
                                            for path in entries.values()):
        raise ValueError("measurement session is not fresh; prepare a new directory and epoch")
    with (directory / "controller_started.json").open("xb") as handle:
        handle.write(b'{"protocol":1,"consumed":true}\n')
        handle.flush()
        os.fsync(handle.fileno())


def read_setup(directory):
    path = Path(directory).resolve()
    validate_lease_path(path)
    raw = (path / "probe_setup.json").read_bytes()
    value = decode_message(raw)
    if (set(value) != {"protocol", "native_epoch", "manifest_digest", "game_exe"}
            or type(value["protocol"]) is not int or value["protocol"] != 1):
        raise ValueError("invalid prepared prototype setup")
    if type(value["native_epoch"]) is not int or not 0 < value["native_epoch"] <= (1 << 53) - 1:
        raise ValueError("invalid native epoch")
    if not re.fullmatch(r"[0-9a-f]{64}", value["manifest_digest"]):
        raise ValueError("invalid prototype manifest")
    validate_lease_path(value["game_exe"])
    shared = decode_message((path / "probe_manifest.json").read_bytes())
    if digest(shared) != value["manifest_digest"]:
        raise ValueError("prepared manifest was changed")
    for name, expected in shared["prototype_files"].items():
        if name.startswith("python/"):
            relative = name.removeprefix("python/")
            if Path(relative).name != relative or not relative.endswith(".py"):
                raise ValueError("invalid Python manifest path")
            if hashlib.sha256((Path(__file__).parent / relative).read_bytes()).hexdigest() != expected:
                raise ValueError("prototype Python code changed after staging; prepare a fresh session")
    value["measurement_profile"] = shared.get("config_semantics", {}).get("profile", TIME_PROFILE)
    value["measurement_preparation"] = shared.get("config_semantics", {}).get("preparation")
    return path, value


def selected_profile(args, setup):
    profile = getattr(args, "profile", TIME_PROFILE)
    if profile not in (TIME_PROFILE, BUILD_PROFILE) or profile != setup.get("measurement_profile", TIME_PROFILE):
        raise ValueError("selected test profile does not match the prepared shared manifest")
    paced_live = getattr(args, "paced_live_probe", False)
    if paced_live:
        if (profile != BUILD_PROFILE or getattr(args, "rounds", None) != SHORT_BUILD_ROUNDS
                or setup.get("measurement_preparation") != SHORT_BUILD_CONTRACT):
            raise ValueError("paced live probe requires the identified ten-round short_scene_v1 preparation")
    elif setup.get("measurement_preparation") is not None:
        raise ValueError("short preparation belongs only to the paced live experiment")
    if not paced_live and profile == BUILD_PROFILE and getattr(args, "rounds", None) != BUILD_ROUNDS:
        raise ValueError("build_v2 requires the complete fixed 240-round recipe")
    if sum(bool(getattr(args, name, False)) for name in ("timing_probe", "stream_probe", "live_probe", "paced_live_probe")) > 1:
        raise ValueError("choose exactly one post-build experiment")
    if getattr(args, "live_probe", False) or paced_live:
        if profile != BUILD_PROFILE or getattr(args, "delay_ms", 0) != 0:
            raise ValueError("live probe requires build_v2 without legacy message delays")
        if getattr(args, "timeout", 30) < 15:
            raise ValueError("live probe requires at least 15 seconds per protocol phase")
    if getattr(args, "stream_probe", False):
        if profile != BUILD_PROFILE or getattr(args, "delay_ms", 0) != 0:
            raise ValueError("stream probe requires build_v2 without legacy message delays")
        if getattr(args, "timeout", 30) < 15:
            raise ValueError("stream probe requires at least 15 seconds per protocol phase")
    if getattr(args, "timing_probe", False):
        if profile != BUILD_PROFILE or getattr(args, "delay_ms", 0) != 0:
            raise ValueError("timing probe requires build_v2 without legacy message delays")
        if getattr(args, "timeout", 30) < 15:
            raise ValueError("timing probe requires at least 15 seconds per protocol phase")
    return profile


def measurement_capabilities(args):
    if getattr(args, "paced_live_probe", False):
        return tuple(sorted((*CAPABILITIES, PACED_LIVE_CAPABILITY)))
    if getattr(args, "live_probe", False):
        return tuple(sorted((*CAPABILITIES, LIVE_CAPABILITY)))
    if getattr(args, "stream_probe", False):
        return tuple(sorted((*CAPABILITIES, STREAM_CAPABILITY)))
    return tuple(sorted((*CAPABILITIES, TIMING_CAPABILITY))) if getattr(args, "timing_probe", False) else CAPABILITIES


def verify_payload(directory, setup):
    game_exe = Path(setup["game_exe"])
    if not game_exe.is_absolute() or hashlib.sha256(game_exe.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("unsupported or changed actual game executable")
    payload = decode_message((directory / "probe_payload.json").read_bytes())
    if set(payload) != {"files"} or not isinstance(payload["files"], dict):
        raise ValueError("missing installed prototype file manifest")
    for relative, expected in payload["files"].items():
        part = Path(relative)
        if part.is_absolute() or ".." in part.parts or ":" in relative:
            raise ValueError("invalid payload path")
        installed = game_exe.parent / part
        if hashlib.sha256(installed.read_bytes()).hexdigest() != expected:
            raise ValueError(f"installed prototype file mismatch: {relative}")
    if not {"alut.dll", "tf2_step_probe.dll"}.issubset(payload["files"]):
        raise ValueError("incomplete prototype manifest")


class ControllerGuard:
    """OS-owned lifetime prevents two leases; a crashed process leaves no stale lock."""
    def __init__(self):
        if os.name != "nt":
            raise ValueError("TF2 engine measurement requires Windows")
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateMutexW(None, False, "Local\\TF2StrictProbeController")
        existed = ctypes.get_last_error() == 183
        if not self.handle or existed:
            if self.handle:
                self.kernel.CloseHandle(self.handle)
            raise ValueError("another prototype controller is already active")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def read_inputs(path):
    document = decode_message(Path(path).read_bytes())
    if set(document) != {"rounds"} or type(document["rounds"]) is not dict:
        raise ValueError("input document must contain rounds object")
    result = {}
    for number, commands in document["rounds"].items():
        if not re.fullmatch(r"0|[1-9][0-9]*", number) or not isinstance(commands, list):
            raise ValueError("invalid round input")
        result[int(number)] = commands
    return result


async def game_peer(args, secret, directory, setup):
    engine = None
    writer = None
    lease = None
    replica = None
    guard = None
    failure = ""
    failure_error = None
    authenticated = False
    peer_error_sent = False
    finished = False
    build_proof = None
    proof_result = None
    journal = None
    stream_world_journaled = set()
    live_world_journaled = set()
    preparation_journaled = set()
    live_input_reader = None
    facts = {}
    paced_live = getattr(args, "paced_live_probe", False)
    preparation_rounds = SHORT_BUILD_ROUNDS if paced_live else BUILD_ROUNDS
    progress = Progress(external_path(getattr(args, "progress", None), directory),
                        peer=getattr(args, "peer", None))
    if paced_live:
        progress = CoalescedProgress(progress)
    stop_file = external_path(getattr(args, "stop_file", None), directory)
    stop_requested = lambda: bool(stop_file and stop_file.exists())
    def check_stop():
        if stop_requested():
            raise StopRequested("measurement stopped by local user")
    try:
        profile = selected_profile(args, setup)
        if getattr(args, "live_probe", False) or paced_live:
            input_path = external_path(getattr(args, "live_input_file", None), directory)
            if input_path is None:
                raise ValueError("live peer requires a prepared input queue outside the session")
            # Validate the exact queue identity and structure before consuming
            # a game session or creating a launch lease. The reader validates
            # again on every collection while the live test is running.
            live_input_reader = InputReader(input_path, args.epoch, args.peer)
        if profile == BUILD_PROFILE:
            build_proof = ShortBuildProof() if paced_live else BuildProof()
            journal_path = external_path(getattr(args, "journal", None) or
                                         Path(args.report).with_name("peer-journal.jsonl"), directory)
            journal = SnapshotJournal(journal_path)
            input_source = lambda number: (short_build_inputs(args.peer, number) if paced_live
                                           else build_inputs(args.peer, number))
        else:
            inputs = read_inputs(args.inputs)
            input_source = lambda number: inputs.get(number, [])
        check_stop()
        guard = ControllerGuard()
        if game_is_running():
            raise ValueError("a fresh game process is required; close TF2 before starting the measurement controller")
        verify_payload(directory, setup)
        claim_fresh_session(directory)
        # Different lease root from the Alpha: a normal Alpha proxy cannot consume it.
        lease = LaunchLease.create(Path(setup["game_exe"]), directory,
                                   lease_root=Path(os.environ["LOCALAPPDATA"]) / "TF2StrictProbe")
        print("Messmodus wartet auf TF2. Spiel selbst ueber Steam starten und den vorbereiteten Teststand laden.", flush=True)
        print("TF2 innerhalb von 2 Minuten starten. Fuer das Laden des Spielstands bleiben bis zu 10 Minuten.", flush=True)
        deadline = time.monotonic() + getattr(args, "startup_timeout", 600.0)
        lease_deadline = time.monotonic() + 120
        while True:
            check_stop()
            ready, facts = startup_facts(directory, setup["native_epoch"])
            progress("waiting_game", reason="waiting for actual native and Lua world contact",
                     phase_label=phase_label(0) if build_proof else "Spielkontakt herstellen", **facts)
            if ready:
                break
            if time.monotonic() >= lease_deadline and facts["native"] is None and facts["loader"] is None:
                raise ProtocolError("game startup lease expired after 2 minutes; prepare a fresh attempt")
            if time.monotonic() >= deadline:
                raise ProtocolError("game measurement startup timed out; no native/Lua world contact")
            await asyncio.sleep(0.1)
        check_stop()
        # Do not cancel an engine thread: it owns native/Lua mailboxes. A local
        # stop during this bounded operation is handled immediately afterward.
        engine = await asyncio.to_thread(EngineAdapter, directory, setup["native_epoch"],
                                         probe_only=True, timeout_s=min(args.timeout, 60))
        check_stop()
        if tuple(sorted(engine.capabilities)) != CAPABILITIES:
            raise ProtocolError("unexpected engine measurement capabilities")
        if build_proof:
            initial = engine.snapshot()
            journal.append("initial", frame=engine.frame, number=0, snapshot=initial)
            build_proof.observe(initial, frame=engine.frame)
        replica_class = (PacedLiveReplica if paced_live else
                         LiveReplica if getattr(args, "live_probe", False) else
                         StreamReplica if getattr(args, "stream_probe", False) else
                         TimingReplica if getattr(args, "timing_probe", False) else Replica)
        options = {"stop_requested": stop_requested} if replica_class in (TimingReplica, StreamReplica, LiveReplica, PacedLiveReplica) else {}
        if replica_class in (LiveReplica, PacedLiveReplica):
            options["live_input_source"] = live_input_reader.take
        replica = replica_class(args.peer, args.epoch, setup["manifest_digest"], measurement_capabilities(args),
                                engine, input_source, frame=engine.frame,
                                step_us=ENGINE_STEP_US, **options)
        progress("waiting_peer", reason="actual local world ready; waiting for both peers", **facts)
        reader, writer = await stoppable(asyncio.open_connection(args.host, args.port), stop_requested, args.timeout)
        await stoppable(authenticate_client(reader, writer, secret, args.epoch, args.peer), stop_requested, args.timeout)
        authenticated = True
        await stoppable(send(writer, replica.hello()), stop_requested, args.timeout)
        first_message = True
        while not replica.halted and not replica.finished:
            message = await stoppable(receive(reader), stop_requested,
                                     getattr(args, "startup_timeout", 600.0) if first_message else args.timeout)
            first_message = False
            check_stop()
            delay = getattr(args, "delay_ms", 0) / 1000
            if delay:
                await stoppable(asyncio.sleep(delay), stop_requested, delay + args.timeout)
            progress("running", round=replica.round, frame=replica.frame,
                     message=message.get("kind"), delay_ms=getattr(args, "delay_ms", 0),
                     timing=replica.timing_progress() if hasattr(replica, "timing_progress") else None,
                     stream=replica.stream_progress() if hasattr(replica, "stream_progress") else None,
                     live=replica.live_progress() if hasattr(replica, "live_progress") else None,
                     phase_label=("Frei ausgelöste Testpause gemeinsam verarbeiten" if str(message.get("kind", "")).startswith("live_") else
                                  "Fortlaufende Fahrt und gemeinsame Kontrollpunkte" if str(message.get("kind", "")).startswith("stream_") else
                                  "Fahrzeug beobachten: 1x-Zieltempo" if message.get("kind") == "timing_run" else
                                  "Warteprobe: Spielzeit bleibt gehalten" if message.get("kind") == "timing_prepare" else
                                  phase_label(message.get("round"), message.get("command")) if build_proof else "Gemeinsame Zeit und Pause prüfen"))
            response = await asyncio.to_thread(replica.receive, message)
            check_stop()
            preparation_key = ((response.get("kind"), response.get("round"), response.get("index"),
                                response.get("plan_hash")) if response else None)
            if (build_proof and response and response.get("kind") in ("applied", "stepped")
                    and (not paced_live or preparation_key not in preparation_journaled)):
                observed = engine.snapshot()
                command = message.get("command") if response["kind"] == "applied" else None
                journal.append(response["kind"], frame=replica.frame, number=message.get("round"),
                               snapshot=observed, command=command, command_key=message.get("command_key"))
                build_proof.observe(observed, frame=replica.frame, command=command,
                                    command_key=message.get("command_key"),
                                    **({"receipt": {key: response[key] for key in ("success", "result", "state_digest")}
                                       if command is not None else None} if paced_live else {}))
                if response["kind"] == "stepped" and message.get("round") == preparation_rounds - 1:
                    # The coordinator cannot send completion until both local
                    # postconditions pass and this last STEP receipt is sent.
                    proof_result = build_proof.finish(frame=replica.frame, step_us=ENGINE_STEP_US)
                preparation_journaled.add(preparation_key)
            if journal and response and response.get("kind") in ("timing_ready", "timing_done"):
                journal.append(response["kind"], frame=replica.frame, number=replica.round,
                               snapshot=engine.snapshot())
                progress("running", round=replica.round, frame=replica.frame,
                         timing=replica.timing_progress(), phase_label="Gemeinsame Rückmeldung zum Fahrtabschnitt abwarten")
            if response and str(response.get("kind", "")).startswith("stream_"):
                receipt_key = (response["kind"], response.get("index"), response.get("plan_hash"))
                if journal and response["kind"] in STREAM_WORLD_RECEIPTS and receipt_key not in stream_world_journaled:
                    # Native-only receipts never turn the cached old Lua world
                    # into a current observation. Only a fresh checkpoint may.
                    stream_engine = replica.stream_engine
                    if not stream_engine or not stream_engine.observations_fresh:
                        raise ProtocolError("stream world receipt lacks a fresh Lua observation")
                    observed = stream_engine.last_observed_snapshot
                    if (response["frame"] != stream_engine.last_observed_frame
                            or response["sim_time_us"] != observed["sim_time_us"]
                            or response["paused"] is not observed["paused"]
                            or response["state_digest"] != engine.state_digest):
                        raise ProtocolError("stream world receipt belongs to another observation")
                    journal.append(response["kind"], frame=stream_engine.last_observed_frame,
                                   number=replica.round, snapshot=observed)
                    # Identical cached protocol replies are sent again below,
                    # but never become a second or falsely current observation.
                    stream_world_journaled.add(receipt_key)
                progress("running", round=replica.round, frame=replica.frame,
                         stream=replica.stream_progress(), phase_label="Fortlaufende Fahrt und gemeinsame Kontrollpunkte")
            if response and str(response.get("kind", "")).startswith("live_"):
                receipt_key = (response["kind"], response.get("index"), response.get("plan_hash"))
                world_receipts = PACED_LIVE_WORLD_RECEIPTS if paced_live else LIVE_WORLD_RECEIPTS
                if journal and response["kind"] in world_receipts and receipt_key not in live_world_journaled:
                    stream_engine = replica.stream_engine
                    if not stream_engine or not stream_engine.observations_fresh:
                        raise ProtocolError("live world receipt lacks a fresh Lua observation")
                    observed = stream_engine.last_observed_snapshot
                    if (response["frame"] != stream_engine.last_observed_frame
                            or response["sim_time_us"] != observed["sim_time_us"]
                            or response["paused"] is not observed["paused"]
                            or response["state_digest"] != engine.state_digest):
                        raise ProtocolError("live world receipt belongs to another observation")
                    journal.append(response["kind"], frame=stream_engine.last_observed_frame,
                                   number=replica.round, snapshot=observed)
                    live_world_journaled.add(receipt_key)
                progress("running", round=replica.round, frame=replica.frame,
                         live=replica.live_progress(), phase_label="Gemeinsame Teststeuerung: Pause, Fortsetzen oder Abschließen")
            if response is not None:
                await stoppable(send(writer, response), stop_requested, args.timeout)
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ProtocolError, ValueError) as exc:
        failure = f"{type(exc).__name__}: {exc}"
        failure_error = exc
    finally:
        last_observed_snapshot = None
        last_observed_frame = None
        last_acknowledged_native_frame = None
        last_acknowledged_native_sim_time_us = None
        if engine:
            try:
                stream_engine = getattr(replica, "stream_engine", None) if replica else None
                # A rejected Lua checkpoint may already have mutated the base
                # adapter cache. Retain the stream's accepted observation and
                # its matching frame together, including on terminal errors.
                last_observed_snapshot = (stream_engine.last_observed_snapshot if stream_engine else
                                          engine.snapshot())
                last_observed_frame = (stream_engine.last_observed_frame if stream_engine else
                                       replica.frame if replica else engine.frame)
                last_acknowledged_native_frame = stream_engine.frame if stream_engine else engine.frame
                last_acknowledged_native_sim_time_us = stream_engine.time_us if stream_engine else engine.time_us
            except Exception as exc:
                failure = failure or f"snapshot during cleanup failed: {exc}"
            try:
                engine.close()  # terminal HALT; never resume normal simulation on exit
            except Exception as exc:
                failure = failure or f"engine halt during cleanup failed: {exc}"
        elif lease:
            try:
                halt_before_adapter(directory, setup["native_epoch"])
            except Exception as exc:
                failure = failure or f"bootstrap halt failed: {exc}"
        if lease:
            try:
                lease.revoke()
            except Exception as exc:
                failure = failure or f"lease cleanup failed: {exc}"
        if guard:
            try:
                guard.close()
            except Exception as exc:
                failure = failure or f"controller cleanup failed: {exc}"
        if writer:
            if authenticated and failure and replica:
                try:
                    # Local gates are already closed above. Report the original
                    # failure before EOF, with a strict bound even if the host
                    # has disappeared. The host can only halt on this message.
                    diagnostic = peer_error_message(args.epoch, replica.round, replica.frame,
                                                    failure_error or ProtocolError(failure))
                    await asyncio.wait_for(send(writer, diagnostic), min(args.timeout, 1.0))
                    peer_error_sent = True
                except (OSError, asyncio.TimeoutError, ProtocolError):
                    pass  # Preserve the original fault; EOF remains the fallback.
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        if build_proof and replica and replica.finished and not proof_result:
            failure = failure or "build proof: missing verified final postconditions"
        finished = bool(replica and replica.finished and not failure)
        reason = failure or (replica.reason if replica else "")
        if journal:
            try:
                journal.append("completed" if finished else "failed", frame=last_observed_frame,
                               number=replica.round if replica else None, snapshot=last_observed_snapshot,
                               reason=reason)
            except Exception as exc:
                failure = failure or f"build journal completion failed: {exc}"
                reason = failure or reason
                finished = False
            finally:
                try:
                    journal.close()
                except Exception as exc:
                    failure = failure or f"build journal close failed: {exc}"
                    reason = failure or reason
                    finished = False
        write_report(args.report, {"backend": "tf2_controlled_measurement", "probe_only": True,
                                   "complete_world_verified": False, "finished": finished,
                                   "local_completed": finished, "coordinated_completed": False,
                                   "completion_scope": "local_received_host_completion" if finished else None,
                                   "halted": not finished, "reason": reason,
                                   "peer_error_sent": peer_error_sent,
                                   "profile": getattr(args, "profile", TIME_PROFILE),
                                   "build_proof": proof_result if finished and not paced_live else None,
                                   **({"short_preparation": proof_result,
                                       "preparation_contract": SHORT_BUILD_CONTRACT,
                                       "launcher_status": progress.metrics()} if paced_live else {}),
                                   "timing": replica.timing_report() if replica and hasattr(replica, "timing_report") else None,
                                   "stream": replica.stream_report() if replica and hasattr(replica, "stream_report") else None,
                                   "live": replica.live_report() if replica and hasattr(replica, "live_report") else None,
                                   "journal": str(journal.path) if journal else None,
                                   "round": replica.round if replica else None,
                                   "frame": replica.frame if replica else None,
                                   "snapshot": last_observed_snapshot if finished else None,
                                   "snapshot_scope": "verified_completion" if finished else None,
                                   "last_observed_frame": last_observed_frame,
                                   "last_acknowledged_native_frame": last_acknowledged_native_frame,
                                   "last_acknowledged_native_sim_time_us": last_acknowledged_native_sim_time_us,
                                   "last_observed_sim_time_us": (last_observed_snapshot.get("sim_time_us")
                                                                  if last_observed_snapshot else None),
                                   "last_observed_snapshot": last_observed_snapshot if not finished else None})
        progress("completed" if finished else "halted", reason=reason, local_completed=finished,
                 coordinated_completed=False, round=replica.round if replica else None,
                 frame=replica.frame if replica else None,
                 phase_label=("Kurzer Aufbau und gemeinsame Eingaben abgeschlossen" if finished and paced_live else
                              phase_label(BUILD_ROUNDS) if finished and build_proof else reason),
                 timing=replica.timing_progress() if replica and hasattr(replica, "timing_progress") else None,
                 stream=replica.stream_progress() if replica and hasattr(replica, "stream_progress") else None,
                 live=replica.live_progress() if replica and hasattr(replica, "live_progress") else None,
                 last_observed_frame=last_observed_frame,
                 last_acknowledged_native_frame=last_acknowledged_native_frame,
                 last_acknowledged_native_sim_time_us=last_acknowledged_native_sim_time_us,
                 completion_scope="local_received_host_completion" if finished else None,
                 startup_facts=facts)
    return 0 if finished else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("host", "peer"))
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--epoch", required=True, help="same fresh network epoch on both PCs")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--port", type=int, default=34207)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ready")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0, help="per protocol phase/engine operation, seconds")
    parser.add_argument("--startup-timeout", type=float, default=600.0, help="manual game loading and initial peer join, seconds")
    parser.add_argument("--progress", type=Path, help="atomic launcher status JSON outside the session")
    parser.add_argument("--stop-file", type=Path, help="creating this external file requests terminal stop")
    parser.add_argument("--delay-ms", type=int, default=0, help="experimental delay before each peer response, 0..5000 ms")
    parser.add_argument("--peer", choices=("a", "b"))
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--profile", choices=(TIME_PROFILE, BUILD_PROFILE), default=TIME_PROFILE)
    parser.add_argument("--journal", type=Path, help="build snapshot journal outside the session")
    parser.add_argument("--timing-probe", action="store_true", help="after the build, compare bounded 1x windows and asymmetric controlled waits")
    parser.add_argument("--stream-probe", action="store_true", help="after the build, use paced small grants, ten-second world checkpoints and scheduled pause commands")
    parser.add_argument("--live-probe", action="store_true", help="after the build, accept explicit pause/resume/end requests from a bounded local input queue")
    parser.add_argument("--paced-live-probe", action="store_true", help="after ten verified preparation rounds, collect live inputs with native receipts")
    parser.add_argument("--live-input-file", type=Path, help="prepared live peer input queue outside the native/Lua session")
    args = parser.parse_args(argv)
    if (not 1 <= args.port <= 65535 or not 1 <= args.rounds <= 10000 or not 0 < args.timeout <= 60
            or not 0 < args.startup_timeout <= 3600 or not 0 <= args.delay_ms <= 5000):
        parser.error("invalid port/rounds/timeout")
    if args.mode == "host" and not args.ready:
        parser.error("host requires --ready")
    accepts_live = args.live_probe or args.paced_live_probe
    if args.mode == "peer" and (not args.peer or not args.inputs and not accepts_live):
        parser.error("peer requires --peer and --inputs")
    if args.live_input_file and (args.mode != "peer" or not accepts_live):
        parser.error("--live-input-file belongs only to a live probe peer")
    if args.mode == "peer" and accepts_live and not args.live_input_file:
        parser.error("live peer requires --live-input-file")
    directory, setup = read_setup(args.session)
    selected_profile(args, setup)
    secret = args.key_file.read_bytes().strip()
    if not 32 <= len(secret) <= 128:
        parser.error("key file must contain 32..128 bytes")
    if args.mode == "host":
        progress = Progress(external_path(args.progress, directory), role="host")
        if args.paced_live_probe:
            progress = CoalescedProgress(progress)
        stop_file = external_path(args.stop_file, directory)
        return asyncio.run(host(args, secret, expected_manifest=setup["manifest_digest"],
                                capabilities=measurement_capabilities(args), backend="tf2_controlled_measurement",
                                startup_timeout=args.startup_timeout, progress=progress,
                                stop_requested=lambda: bool(stop_file and stop_file.exists()),
                                step_us=ENGINE_STEP_US,
                                coordinator_factory=(PacedLiveCoordinator if args.paced_live_probe else
                                                     LiveCoordinator if args.live_probe else
                                                     StreamCoordinator if args.stream_probe else
                                                     TimingCoordinator if args.timing_probe else None)))
    return asyncio.run(game_peer(args, secret, directory, setup))


if __name__ == "__main__":
    raise SystemExit(main())
