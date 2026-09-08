"""Explicit experimental TF2 file IPC. Never launches, installs, or simulates a game.

Native permits acknowledge control boundaries only. EngineAdapter waits for a new
Lua observation of the actual world before returning a state receipt. The Lua
snapshot currently covers tracked objects and the native gate still reports
probe_required=1: this adapter therefore requires explicit probe_only=True and
never advertises the production protocol's complete capabilities.

Session directories must already exist. One exclusive owner lock and atomic
replacement protect control files; old sessions cannot be silently rejoined.
Timeouts permanently close the local gate and attempt terminal native/Lua HALT.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid

from .core import MAX_INT, ProtocolError, canonical_json


NATIVE_LIMIT = 4096
LUA_LIMIT = 262144
NATIVE_ABI = 3
ENGINE_STEP_US = 200000
MAX_TIMING_WINDOW_STEPS = 25
MAX_TIMING_IDLE_MS = 30000
UINT64_MAX = (1 << 64) - 1
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_KEY = re.compile(r"[a-z][a-z0-9_]*\Z")
_COMMAND_KEY = re.compile(r"[ab]:[1-9][0-9]*\Z")
NATIVE_REQUIRED = {
    "protocol", "abi", "epoch", "ready", "request_received", "request_acknowledged",
    "request_completed", "result", "initialized", "armed", "halted", "fault",
    "runtime_fault", "probe_required", "completed_frame", "outer_calls", "pending_state",
    "pending_frame", "pending_dt_us", "completed_dt_us", "time_before_ms", "time_after_ms", "native_step_us",
}


class MailboxError(ProtocolError):
    pass


class MailboxBusy(MailboxError):
    pass


def lua_error_detail(value):
    """Keep the first useful Lua failure readable without terminal controls."""
    if type(value) is list:
        value = "; ".join(str(item) for item in value[:8])
    clean = "".join(character if character.isprintable() else " " for character in str(value))
    return " ".join(clean.split())[:1024]


def _shared_read(path, limit):
    """Windows readers must permit deletion so native atomic replacement works."""
    if os.name != "nt":
        with path.open("rb") as handle:
            return handle.read(limit + 1)
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        error = ctypes.get_last_error()
        if error in (2, 3):
            raise FileNotFoundError(error, "mailbox file not found", str(path))
        raise ctypes.WinError(error)
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close(handle)
        raise
    with os.fdopen(fd, "rb") as stream:
        return stream.read(limit + 1)


def _uint(value, name, maximum=UINT64_MAX, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise MailboxError(f"invalid {name}")
    return value


def _epoch(value):
    if type(value) is int:
        return str(_uint(value, "epoch", minimum=1))
    if type(value) is str and _DECIMAL.fullmatch(value) and 0 < int(value) <= UINT64_MAX:
        return value
    raise MailboxError("epoch must be a positive uint64 or its canonical decimal string")


def _json_bytes(value, limit=LUA_LIMIT):
    """Integer-only canonical JSON with a larger, still bounded snapshot budget."""
    left = 24000
    def check(item, depth):
        nonlocal left
        left -= 1
        if left < 0 or depth > 24:
            raise MailboxError("Lua JSON complexity limit exceeded")
        kind = type(item)
        if item is None or kind is bool:
            return
        if kind is int:
            if not -MAX_INT <= item <= MAX_INT:
                raise MailboxError("Lua integer out of supported range")
            return
        if kind is str:
            try:
                size = len(item.encode("utf-8"))
            except UnicodeError as exc:
                raise MailboxError("invalid Lua Unicode") from exc
            if size > limit:
                raise MailboxError("Lua string too large")
            return
        if kind is list:
            if len(item) > 24000:
                raise MailboxError("Lua array too large")
            for child in item:
                check(child, depth + 1)
            return
        if kind is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise MailboxError("Lua JSON keys must be strings")
                check(key, depth + 1)
                check(child, depth + 1)
            return
        raise MailboxError("Lua JSON requires integer or decimal-string numbers")
    check(value, 0)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    if len(raw) > limit:
        raise MailboxError("Lua JSON byte limit exceeded")
    return raw


def _decode_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise MailboxError("duplicate Lua JSON key")
            result[key] = value
        return result
    def bad_number(_):
        raise MailboxError("non-finite Lua JSON number")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=bad_number)
    except (UnicodeError, json.JSONDecodeError):
        return None  # TF2's sandbox may expose a partially written status file.
    except RecursionError as exc:
        raise MailboxError("Lua JSON recursion limit") from exc
    _json_bytes(result)
    if type(result) is not dict:
        raise MailboxError("Lua status must be an object")
    return result


def parse_native_status(raw):
    """Missing/incomplete writes return None; a complete invalid status raises."""
    if type(raw) is not bytes or len(raw) > NATIVE_LIMIT:
        raise MailboxError("native status exceeds 4096 bytes")
    if not raw or not raw.endswith(b"\n"):
        return None
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError:
        return None
    values = {}
    for line in lines:
        if "=" not in line:
            return None
        key, value = line.split("=", 1)
        if not _KEY.fullmatch(key) or key in values:
            raise MailboxError("invalid/duplicate native status key")
        if not _DECIMAL.fullmatch(value) or len(value) > 20:
            raise MailboxError("invalid native status integer")
        values[key] = _uint(int(value), key)
    if ("protocol" in values and "abi" in values
            and (values["protocol"] != 1 or values["abi"] != NATIVE_ABI)):
        raise MailboxError("unsupported native mailbox protocol/ABI")
    if not NATIVE_REQUIRED.issubset(values):
        return None
    if values["native_step_us"] != ENGINE_STEP_US:
        raise MailboxError("native mailbox step quantum must be 200000 microseconds")
    for name in ("ready", "initialized", "armed", "halted", "probe_required"):
        _uint(values[name], name, 1)
    _uint(values["pending_state"], "pending_state", 3)
    for name in ("pending_dt_us", "completed_dt_us"):
        if values[name] not in (0, ENGINE_STEP_US):
            raise MailboxError("invalid native step delta")
    return values


def native_fault_detail(status):
    """Keep numeric native diagnostics intact instead of hiding them as EOF."""
    names = ("halted", "fault", "runtime_fault", "win32_error", "io_operation", "result",
             "request_received", "request_completed", "completed_frame")
    return ", ".join(f"{name}={status.get(name, 0)}" for name in names
                     if name in status or name == "io_operation")


class NativeMailbox:
    """Serialized owner of native control. Constructing it does not send a permit."""
    def __init__(self, session_dir, epoch, *, timeout_s=5.0, poll_s=0.01):
        self.epoch = _epoch(epoch)
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 60):
            raise MailboxError("timeout_s must be in (0, 60]")
        if (type(poll_s) not in (int, float) or not math.isfinite(poll_s)
                or not 0 < poll_s <= 0.1):
            raise MailboxError("poll_s must be in (0, 0.1]")
        supplied = Path(session_dir)
        self.directory = supplied.resolve(strict=True)
        if not self.directory.is_dir():
            raise MailboxError("session directory must already exist")
        self.timeout_s, self.poll_s = timeout_s, poll_s
        self._operation_deadline = None
        self.request = 0
        self.completed_frame = 0
        self.halted = False
        self.reason = ""
        self.last_status = None
        self._last_permit = None
        self._pending = False
        self._mutex = threading.Lock()
        self._written = {}
        self._closed = False
        self._epoch_confirmed = False
        self._lock_path = self.directory / ".engine_mailbox.lock"
        self._owner = f"{os.getpid()}:{uuid.uuid4().hex}\n".encode("ascii")
        try:
            fd = os.open(self._lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise MailboxBusy("session already has an owner; implicit rejoin is forbidden") from exc
        with os.fdopen(fd, "wb") as handle:
            handle.write(self._owner)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            for name in ("native_control.txt", "lua_control.json"):
                if (self.directory / name).exists():
                    raise MailboxError("session already contains controls; use a fresh epoch/directory")
            self._wait(self._initial_status)
        except Exception as exc:
            self.halt(str(exc))
            self._release_lock()
            raise

    def _path(self, name):
        path = self.directory / name
        if path.is_symlink() or path.parent.resolve(strict=True) != self.directory:
            raise MailboxError("mailbox path was redirected")
        return path

    def _read(self, name, limit):
        path = self._path(name)
        try:
            raw = _shared_read(path, limit)
        except FileNotFoundError:
            return None
        except PermissionError:
            if name in ("native_status.txt", "lua_status.json"):
                return None  # A replacement/delete-sharing race is never an ACK.
            raise
        if len(raw) > limit:
            raise MailboxError(f"{name} exceeds size limit")
        return raw

    def _write(self, name, raw, *, emergency=False):
        if type(raw) is not bytes:
            raise MailboxError("mailbox payload must be bytes")
        self._check_operation_deadline(emergency=emergency)
        path = self._path(name)
        current = self._read(name, max(NATIVE_LIMIT, LUA_LIMIT))
        if current is not None and current != self._written.get(name):
            raise MailboxError("another writer changed the pending control file")
        temp = self.directory / f".{name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            deadline = self._wait_deadline(emergency=emergency)
            while True:
                self._check_operation_deadline(emergency=emergency)
                try:
                    os.replace(temp, path)
                    break
                except PermissionError:
                    # Lua's fopen can briefly deny delete sharing on Windows.
                    # Retry atomic replacement, never fall back to truncation.
                    if time.monotonic() >= deadline:
                        raise
                    current = self._read(name, LUA_LIMIT)
                    if current is not None and current != self._written.get(name):
                        raise MailboxError("another writer changed the pending control file")
                    time.sleep(min(self.poll_s, max(0, deadline - time.monotonic())))
            self._written[name] = raw
            self._check_operation_deadline(emergency=emergency)
        finally:
            if temp.exists():
                temp.unlink()

    def _check_operation_deadline(self, *, emergency=False):
        if (not emergency and self._operation_deadline is not None
                and time.monotonic() >= self._operation_deadline):
            raise MailboxError("timing window wall-clock budget exhausted")

    def _wait_deadline(self, *, emergency=False):
        deadline = time.monotonic() + self.timeout_s
        if not emergency and self._operation_deadline is not None:
            deadline = min(deadline, self._operation_deadline)
        return deadline

    def _wait(self, predicate):
        deadline = self._wait_deadline()
        while True:
            self._check_operation_deadline()
            answer = predicate()
            self._check_operation_deadline()
            if answer is not None:
                return answer
            if time.monotonic() >= deadline:
                raise MailboxError("engine mailbox timeout; no permit may continue")
            time.sleep(min(self.poll_s, max(0, deadline - time.monotonic())))

    def read_status(self):
        raw = self._read("native_status.txt", NATIVE_LIMIT)
        if raw is None:
            return None
        status = parse_native_status(raw)
        if status is None:
            return None
        if str(status["epoch"]) != self.epoch:
            raise MailboxError("native status epoch mismatch")
        self._epoch_confirmed = True
        if status["halted"] or status["fault"] or status["runtime_fault"]:
            raise MailboxError(f"native gate halted: {native_fault_detail(status)}")
        self.last_status = status
        return copy.deepcopy(status)

    def _initial_status(self):
        status = self.read_status()
        if status is None:
            return None
        if any(status[k] for k in ("request_received", "request_acknowledged", "request_completed",
                                   "completed_frame", "pending_state")):
            raise MailboxError("native session already processed work; rejoin is forbidden")
        if status["result"] not in (0, 1):
            raise MailboxError("native initialization failed")
        return status if status["ready"] and status["initialized"] and status["armed"] else None

    def _control(self, action, request, frame, dt_us):
        fields = {"protocol": 1, "epoch": self.epoch, "request": request,
                  "action": action, "frame": frame, "dt_us": dt_us}
        return "".join(f"{key}={value}\n" for key, value in fields.items()).encode("ascii")

    def permit(self, frame, dt_us):
        if not self._mutex.acquire(blocking=False):
            raise MailboxBusy("native request still pending")
        try:
            if self.halted or self._closed:
                raise MailboxError("native mailbox permanently halted")
            _uint(frame, "frame", minimum=1)
            if type(dt_us) is not int or dt_us not in (0, ENGINE_STEP_US):
                raise MailboxError("native dt_us must be exactly 0 or 200000")
            if self._last_permit == (frame, dt_us):
                return copy.deepcopy(self.last_status)
            if frame != self.completed_frame + 1:
                raise MailboxError("native frame is not contiguous")
            self.request = _uint(self.request + 1, "next native request", minimum=1)
            self._pending = True
            self._write("native_control.txt", self._control("permit", self.request, frame, dt_us))
            def completed():
                status = self.read_status()
                if status is None:
                    return None
                if any(status[k] > self.request for k in ("request_received", "request_acknowledged", "request_completed")):
                    raise MailboxError("native status acknowledges a future request")
                if status["completed_frame"] > frame:
                    raise MailboxError("native gate advanced beyond the permitted frame")
                if status["completed_frame"] < self.completed_frame:
                    raise MailboxError("native completed frame moved backwards")
                if status["request_received"] != self.request:
                    return None
                if status["result"] not in (0, 1, 9):
                    raise MailboxError("native permit rejected")
                if (status["request_acknowledged"] != self.request
                        or status["request_completed"] != self.request
                        or status["completed_frame"] != frame or status["pending_state"] != 0):
                    return None
                if (status["result"] not in (0, 1) or not status["ready"]
                        or not status["initialized"] or not status["armed"]
                        or status["completed_dt_us"] != dt_us):
                    raise MailboxError("native completion does not match the permit")
                return status
            status = self._wait(completed)
            self.completed_frame = frame
            self._last_permit = (frame, dt_us)
            self._pending = False
            return status
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def halt(self, reason="explicit engine halt"):
        if self.halted:
            return
        self.halted, self.reason = True, str(reason)
        if self._epoch_confirmed:
            try:
                self.request = _uint(self.request + 1, "halt request", minimum=1)
                self._write("native_control.txt", self._control("halt", self.request,
                            0, 0), emergency=True)
            except Exception:
                pass  # Local halt is permanent even when the filesystem is unavailable.

    def _release_lock(self):
        try:
            if self._lock_path.read_bytes() == self._owner:
                self._lock_path.unlink()
        except OSError:
            pass

    def close(self):
        if not self._closed:
            self.halt("engine mailbox closed")
            self._closed = True
            self._release_lock()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class EngineAdapter:
    """Replica-compatible real-observation adapter, restricted to explicit probes.

    Properties describe the last verified actual Lua observation. Every apply
    and step first requests a fresh snapshot and refuses autonomous changes.
    No guessed prices, positions, model-world fallback, or automatic local input
    capture are supplied. Unsupported Lua commands fail and halt the session.
    """
    def __init__(self, session_dir, epoch, *, probe_only=False, timeout_s=5.0, poll_s=0.01):
        if probe_only is not True:
            raise MailboxError("TF2 mailbox is an incomplete experimental adapter; explicit probe_only=True required")
        self.native = NativeMailbox(session_dir, epoch, timeout_s=timeout_s, poll_s=poll_s)
        self.epoch = self.native.epoch
        self.request = 0
        self.revision = -1
        self._last_lua_signature = None
        self.halted = False
        self.reason = ""
        self._mutex = threading.Lock()
        self._snapshot = None
        self._digest = None
        self._last_apply = {}
        self._last_seq = {"a": 0, "b": 0}
        self.capabilities = ("experimental_file_mailbox", "lua_actual_snapshots",
                             "native_probe_required", "partial_world_digest")
        try:
            bootstrap = self.native._wait(self._bootstrap)
            self._accept_snapshot(bootstrap)
            self._refresh()
        except Exception as exc:
            self.halt(str(exc))
            self.native.close()
            raise

    @property
    def state_digest(self):
        return self._digest

    @property
    def time_us(self):
        return self._snapshot["sim_time_us"]

    @property
    def paused(self):
        return self._snapshot["paused"]

    @property
    def coverage(self):
        return copy.deepcopy(self._snapshot["coverage"])

    @property
    def frame(self):
        return self.native.completed_frame

    def snapshot(self):
        return copy.deepcopy(self._snapshot)

    def _read_lua(self):
        raw = self.native._read("lua_status.json", LUA_LIMIT)
        if raw is None:
            return None
        status = _decode_json(raw)
        if status is None:
            return None
        required = {"protocol", "epoch", "request", "revision", "status", "complete"}
        if not required.issubset(status):
            return None
        if type(status["protocol"]) is not int or status["protocol"] != 1 or status["epoch"] != self.epoch:
            raise MailboxError("Lua protocol/epoch mismatch")
        _uint(status["request"], "Lua request", MAX_INT)
        _uint(status["revision"], "Lua revision", MAX_INT)
        if type(status["complete"]) is not bool or type(status["status"]) is not str:
            raise MailboxError("invalid Lua completion/status fields")
        if status["request"] > self.request:
            raise MailboxError("Lua status acknowledges a future request")
        if status["request"] < self.request:
            return None
        if status["revision"] < self.revision:
            return None
        signature = (status["request"], status["revision"], _json_bytes(status))
        if (self._last_lua_signature is not None
                and signature[:2] == self._last_lua_signature[:2]
                and signature[2] != self._last_lua_signature[2]):
            raise MailboxError("conflicting Lua status revision")
        self._last_lua_signature = signature
        self.revision = status["revision"]
        if status["status"] in ("error", "halted"):
            raise MailboxError("Lua adapter reported error/halt: " +
                               lua_error_detail(status.get("error", "no Lua error detail")))
        if not status["complete"]:
            return None
        return status

    def _bootstrap(self):
        status = self._read_lua()
        if status is not None and status["status"] != "ready":
            raise MailboxError("Lua session already active; no implicit rejoin")
        return status

    def _accept_snapshot(self, status):
        snapshot = status.get("snapshot")
        if type(snapshot) is not dict or not {"sim_time_us", "paused", "company", "objects", "coverage"}.issubset(snapshot):
            raise MailboxError("Lua status lacks an actual world snapshot")
        _uint(snapshot["sim_time_us"], "snapshot time", MAX_INT)
        if type(snapshot["paused"]) is not bool:
            raise MailboxError("snapshot pause is not boolean")
        company = snapshot["company"]
        if type(company) is not dict or not {"balance", "loan"}.issubset(company):
            raise MailboxError("snapshot lacks actual company finances")
        if type(company["balance"]) is not int or not -MAX_INT <= company["balance"] <= MAX_INT:
            raise MailboxError("invalid observed company balance")
        _uint(company["loan"], "company loan", MAX_INT)
        coverage = snapshot["coverage"]
        if (type(coverage) is not dict or type(coverage.get("complete_world")) is not bool
                or type(coverage.get("tracked_objects")) is not bool
                or type(coverage.get("missing")) is not list
                or any(type(x) is not str for x in coverage["missing"])):
            raise MailboxError("snapshot does not declare its actual coverage")
        if not coverage["tracked_objects"] or coverage["missing"]:
            raise MailboxError("snapshot has unreadable tracked world state: " + lua_error_detail(coverage["missing"]))
        objects = snapshot["objects"]
        if type(objects) is not list:
            raise MailboxError("invalid snapshot objects")
        keys = []
        for item in objects:
            if (type(item) is not dict or type(item.get("logical_id")) is not str or not item["logical_id"]
                    or type(item.get("kind")) is not str or not item["kind"] or type(item.get("state")) is not dict):
                raise MailboxError("snapshot contains an unbound/nonlogical object")
            keys.append(item["logical_id"])
        if keys != sorted(set(keys)):
            raise MailboxError("snapshot logical objects are not unique and sorted")
        raw = _json_bytes(snapshot)
        supplied = status.get("canonical_state_json")
        if type(supplied) is not str:
            raise MailboxError("Lua canonical state observation missing")
        decoded = _decode_json(supplied.encode("utf-8"))
        if decoded is None or _json_bytes(decoded) != raw:
            raise MailboxError("Lua canonical state differs from snapshot")
        self._snapshot = copy.deepcopy(snapshot)
        self._digest = hashlib.sha256(raw).hexdigest()

    def _request_lua(self, action, **fields):
        self._check_gate(fields["expected_sim_time_us"])
        self.request = _uint(self.request + 1, "next Lua request", MAX_INT, 1)
        message = {"protocol": 1, "epoch": self.epoch, "request": self.request,
                   "action": action, **fields}
        self.native._write("lua_control.json", _json_bytes(message))
        status = self.native._wait(self._read_lua)
        expected = {"snapshot": "ready", "plan": "planned", "apply": "applied", "preview": "previewed"}[action]
        if status["status"] != expected:
            raise MailboxError("Lua acknowledgement is for the wrong action")
        return status

    def _check_gate(self, expected_time):
        def ready():
            status = self.native.read_status()
            if status is None:
                return None
            if status["completed_frame"] != self.native.completed_frame or status["pending_state"] != 0:
                raise MailboxError("native gate is not at the expected idle boundary")
            if any(status[k] != self.native.request for k in
                   ("request_received", "request_acknowledged", "request_completed")):
                raise MailboxError("native gate request differs from the owned boundary")
            if not status["ready"] or not status["initialized"] or not status["armed"]:
                raise MailboxError("native gate is not armed and ready")
            if status["outer_calls"] == 0:
                return None  # No actual engine-clock observation exists yet.
            if status["time_after_ms"] * 1000 != expected_time:
                raise MailboxError("native actual time differs from expected Lua boundary")
            return status
        return self.native._wait(ready)

    def _refresh(self):
        before = self._digest
        observed = self._request_lua("snapshot", expected_sim_time_us=self.time_us,
                                     boundary=str(self.native.completed_frame))
        self._accept_snapshot(observed)
        if before != self._digest:
            raise MailboxError("actual world changed without a permitted engine action")

    def _enter(self):
        if not self._mutex.acquire(blocking=False):
            raise MailboxBusy("engine operation still pending")
        if self.halted:
            self._mutex.release()
            raise MailboxError("engine adapter permanently halted")

    def apply(self, command, command_key):
        self._enter()
        try:
            canonical_json(command)
            if type(command) is not dict or type(command.get("op")) is not str:
                raise MailboxError("invalid engine command")
            if type(command_key) is not str or _COMMAND_KEY.fullmatch(command_key) is None:
                raise MailboxError("invalid logical command key")
            previous = self._last_apply.get(command_key)
            if previous:
                if previous[0] != canonical_json(command):
                    raise MailboxError("conflicting duplicate engine command")
                return copy.deepcopy(previous[1])
            origin, sequence_text = command_key.split(":")
            sequence = _uint(int(sequence_text), "logical command sequence", MAX_INT, 1)
            if sequence != self._last_seq[origin] + 1:
                raise MailboxError("logical command sequence is not contiguous; old commands cannot replay")
            self._refresh()
            before_time, before_digest, before_pause = self.time_us, self._digest, self.paused
            fields = {"command_key": command_key, "command": command,
                      "expected_sim_time_us": before_time, "boundary": str(self.native.completed_frame)}
            planned = self._request_lua("plan", **fields)
            self._accept_snapshot(planned)
            if self._digest != before_digest:
                raise MailboxError("planning a command changed the actual world")
            applied = self._request_lua("apply", **fields)
            self._accept_snapshot(applied)
            receipt = applied.get("receipt")
            if (type(receipt) is not dict or receipt.get("command_key") != command_key
                    or receipt.get("boundary") != fields["boundary"]
                    or type(receipt.get("success")) is not bool or type(receipt.get("result")) is not dict):
                raise MailboxError("Lua receipt does not match the commanded logical action")
            if self.time_us != before_time:
                raise MailboxError("Lua command advanced actual simulation time")
            pause = command.get("value") if command["op"] == "SET_PAUSED" and receipt["success"] else before_pause
            if self.paused is not pause:
                raise MailboxError("Lua command changed pause without authorization")
            result = {"success": receipt["success"], "result": copy.deepcopy(receipt["result"]),
                      "state_digest": self._digest}
            canonical_json(result)
            self._last_apply[command_key] = (canonical_json(command), copy.deepcopy(result))
            self._last_seq[origin] = sequence
            # Bound diagnostics; a pruned key is not a license to replay it.
            if len(self._last_apply) > 256:
                self._last_apply.pop(next(iter(self._last_apply)))
            if not result["success"]:
                self.halt("Lua command failed")
            return result
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def step(self, dt_us):
        self._enter()
        try:
            if type(dt_us) is not int or dt_us not in (0, ENGINE_STEP_US):
                raise MailboxError("engine step requires dt_us 0 or 200000")
            self._refresh()
            if dt_us != (0 if self.paused else ENGINE_STEP_US):
                raise MailboxError("engine permit disagrees with shared pause")
            before_time, before_digest = self.time_us, self._digest
            target_time = _uint(before_time + dt_us, "target simulation time", MAX_INT)
            native = self.native.permit(self.native.completed_frame + 1, dt_us)
            observed = self._request_lua("snapshot", expected_sim_time_us=target_time,
                                         boundary=str(self.native.completed_frame))
            self._accept_snapshot(observed)
            if self.time_us != target_time or native["time_after_ms"] * 1000 != self.time_us:
                raise MailboxError("actual native/Lua world time does not match the permitted step")
            if dt_us == 0 and self._digest != before_digest:
                raise MailboxError("paused engine boundary changed the observed world")
            return {"state_digest": self._digest, "sim_time_us": self.time_us}
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    @staticmethod
    def _timing_sample(status):
        # Each native counter is an individual atomic observation. Do not infer
        # an aggregate invariant between counters sampled by the native writer.
        names = ("completed_frame", "pending_state", "pending_frame", "pending_dt_us",
                 "completed_dt_us", "time_before_ms", "time_after_ms", "native_step_us",
                 "request_received", "request_acknowledged", "request_completed",
                 "ready", "initialized", "armed", "outer_calls", "hold_calls", "updated_ms")
        return {name: status.get(name) for name in names}

    @staticmethod
    def _timing_stop(stop_requested):
        if stop_requested is None:
            return
        if not callable(stop_requested):
            raise MailboxError("timing stop_requested must be callable")
        stopped = stop_requested()
        if type(stopped) is not bool:
            raise MailboxError("timing stop_requested must return a boolean")
        if stopped:
            raise MailboxError("timing experiment cancelled; no further permits")

    def _timing_wait(self, deadline, stop_requested):
        while True:
            self._timing_stop(stop_requested)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.02))

    def check_idle_wait(self, duration_ms, stop_requested=None):
        """Observe one closed boundary around a bounded wall-clock wait.

        A new Lua snapshot is requested on both sides. Optional native counters
        supply diagnostic evidence of maintenance only, not full-world coverage.
        No permit is emitted, even when the shared pause state is unpaused.
        """
        self._enter()
        try:
            started = time.monotonic()
            _uint(duration_ms, "timing idle duration_ms", MAX_TIMING_IDLE_MS)
            self._timing_stop(stop_requested)
            self._refresh()
            before_time, before_frame = self.time_us, self.frame
            before_digest, before_pause = self.state_digest, self.paused
            before = self._timing_sample(self._check_gate(before_time))
            wait_started = time.monotonic()
            self._timing_wait(wait_started + duration_ms / 1000, stop_requested)
            wait_ended = time.monotonic()
            self._refresh()
            after = self._timing_sample(self._check_gate(before_time))
            if (self.frame != before_frame or self.time_us != before_time
                    or self.state_digest != before_digest or self.paused is not before_pause):
                raise MailboxError("idle wait changed the observed boundary")
            self._timing_stop(stop_requested)
            deltas = {name: (after[name] - before[name]
                            if after[name] is not None and before[name] is not None else None)
                      for name in ("hold_calls", "outer_calls", "updated_ms")}
            maintenance = (deltas["updated_ms"] is not None and deltas["updated_ms"] > 0
                           and deltas["hold_calls"] is not None and deltas["hold_calls"] > 0)
            metrics = {"kind": "idle_wait", "requested_delay_ms": duration_ms,
                       "actual_delay_ms": math.ceil((wait_ended - wait_started) * 1000),
                       "duration_ms": math.ceil((time.monotonic() - started) * 1000),
                       "boundary_unchanged": True, "maintenance_observed": maintenance,
                       "native_before": before, "native_after": after,
                       "counter_deltas": deltas}
            return {"state_digest": self.state_digest, "sim_time_us": self.time_us,
                    "frame": self.frame, "metrics": metrics}
        except Exception as exc:
            self.halt(str(exc))
            raise
        finally:
            self._mutex.release()

    def advance_window(self, steps=25, step_us=ENGINE_STEP_US, stop_requested=None):
        """Admit at most five simulated seconds at a paced 1x target.

        Native completion/clock checks remain per permit. Actual Lua world
        observations cover the start and end only: there is deliberately no Lua
        snapshot round trip between permits. Timing records refer to backend
        admission and observed acknowledgement, never to rendered frames.
        """
        self._enter()
        original_timeout = self.native.timeout_s
        original_deadline = self.native._operation_deadline
        try:
            started = time.monotonic()
            _uint(steps, "timing window steps", MAX_TIMING_WINDOW_STEPS, 1)
            if type(step_us) is not int or step_us != ENGINE_STEP_US:
                raise MailboxError("timing window step_us must be exactly 200000")
            # Endpoint requests share the same absolute deadline with every
            # permit. A slow mailbox cannot multiply its timeout by 25 steps.
            window_deadline = started + min(12.0, 2 * steps * step_us / 1_000_000 + 2)
            self.native._operation_deadline = window_deadline
            def budget():
                remaining = window_deadline - time.monotonic()
                if remaining <= 0:
                    raise MailboxError("timing window wall-clock budget exhausted")
                self.native.timeout_s = min(original_timeout, remaining)
            budget()
            self._timing_stop(stop_requested)
            self._refresh()
            if self.paused:
                raise MailboxError("timing window requires shared pause to be off")
            before_frame, before_time = self.frame, self.time_us
            target_frame = _uint(before_frame + steps, "timing target frame")
            target_time = _uint(before_time + steps * step_us, "timing target time", MAX_INT)
            budget()
            self._check_gate(before_time)
            paced_start = time.monotonic()
            period = step_us / 1_000_000
            deadline = paced_start + period
            records = []
            for index in range(steps):
                budget()
                self._timing_wait(min(deadline, window_deadline), stop_requested)
                budget()
                self._timing_stop(stop_requested)
                admitted = time.monotonic()
                frame = before_frame + index + 1
                step_before = before_time + index * step_us
                expected_time = step_before + step_us
                native = self.native.permit(frame, step_us)
                acknowledged = time.monotonic()
                budget()
                if (native["completed_frame"] != frame or self.native.completed_frame != frame
                        or native["completed_dt_us"] != step_us or native["pending_state"] != 0
                        # HOLD traversals continue after acknowledgement and
                        # overwrite this diagnostic with the completed time.
                        # The previous verified boundary + exact after time
                        # establish the permit delta, not this sampled counter.
                        or native["time_before_ms"] * 1000 not in (step_before, expected_time)
                        or native["time_after_ms"] * 1000 != expected_time):
                    raise MailboxError("timing window native clock/frame differs from permitted step")
                records.append({"frame": frame, "sim_time_us": expected_time,
                                "scheduled_offset_us": round((deadline - paced_start) * 1_000_000),
                                "admitted_offset_us": round((admitted - paced_start) * 1_000_000),
                                "ack_observed_offset_us": round((acknowledged - paced_start) * 1_000_000),
                                "permit_duration_us": round((acknowledged - admitted) * 1_000_000),
                                "lateness_us": max(0, round((admitted - deadline) * 1_000_000)),
                                "native_time_before_ms": native["time_before_ms"],
                                "native_time_after_ms": native["time_after_ms"]})
                self._timing_stop(stop_requested)
                # Rebase on actual admission rather than catching up to the old
                # schedule. A slow ACK may consume the interval; it does not earn
                # multiple closely spaced permits or a new extra 200ms delay.
                deadline = admitted + period
            budget()
            observed = self._request_lua("snapshot", expected_sim_time_us=target_time,
                                         boundary=str(target_frame))
            self._accept_snapshot(observed)
            if self.frame != target_frame or self.time_us != target_time or self.paused:
                raise MailboxError("timing window final Lua clock/frame/pause differs from permitted window")
            budget()
            self._check_gate(target_time)
            budget()
            self._timing_stop(stop_requested)
            duration_us = max(1, round((time.monotonic() - started) * 1_000_000))
            simulated_us = steps * step_us
            metrics = {"kind": "advance_window", "steps_requested": steps, "step_us": step_us,
                       "simulated_us": simulated_us, "duration_ms": math.ceil(duration_us / 1000),
                       "rate_ppm": round(simulated_us * 1_000_000 / duration_us),
                       "steps": records, "world_observation": "start_and_end_only",
                       "native_clock_each_step": True}
            return {"state_digest": self.state_digest, "sim_time_us": self.time_us,
                    "frame": self.frame, "metrics": metrics}
        except Exception as exc:
            self.native.timeout_s = original_timeout
            self.native._operation_deadline = original_deadline
            self.halt(str(exc))
            raise
        finally:
            self.native.timeout_s = original_timeout
            self.native._operation_deadline = original_deadline
            self._mutex.release()

    def halt(self, reason="explicit engine halt"):
        if self.halted:
            return
        self.halted, self.reason = True, str(reason)
        self.native.halt(self.reason)
        try:
            self.request = _uint(self.request + 1, "Lua halt request", MAX_INT, 1)
            self.native._write("lua_control.json", _json_bytes({"protocol": 1, "epoch": self.epoch,
                               "request": self.request, "action": "halt"}), emergency=True)
        except Exception:
            pass

    def close(self):
        self.halt("engine adapter closed")
        self.native.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
