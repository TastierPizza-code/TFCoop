"""A short-lived launch ticket and tracking across Steam's legitimate restart."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import time

FILETIME_EPOCH = 116444736000000000


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    created: int
    executable: str


def process_info(pid: int) -> ProcessInfo | None:
    """Read identity and liveness without touching windows or other processes."""
    if os.name != "nt" or pid <= 0:
        return None
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                      ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                                      ctypes.POINTER(wintypes.FILETIME))
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if (not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259
                or not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                               ctypes.byref(system), ctypes.byref(user))
                or not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length))):
            return None
        stamp = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return ProcessInfo(pid, stamp, path.value)
    finally:
        kernel.CloseHandle(handle)


class LaunchLease:
    def __init__(self, path: Path, nonce: str):
        self.path, self.nonce = path, nonce

    @classmethod
    def create(cls, game_exe: Path, directory: Path, *, lease_root: Path | None = None):
        owner = process_info(os.getpid())
        if owner is None:
            raise RuntimeError("Die Identität des Launchers konnte nicht geprüft werden.")
        root = lease_root or Path(os.environ["LOCALAPPDATA"]) / "TF2Coop"
        path, nonce = root / "launch.cfg", secrets.token_hex(16)
        fields = {"format": "1", "launcher_pid": str(owner.pid), "launcher_created": str(owner.created),
                  "expires": str(int(time.time()) + 120), "game_exe": str(game_exe.resolve()),
                  "data_dir": str(directory.resolve()), "nonce": nonce}
        if any("\n" in value or "\r" in value for value in fields.values()):
            raise ValueError("Ungültiger Sitzungspfad.")
        content = "".join(f"{key}={value}\n" for key, value in fields.items())
        if len(content.encode("utf-8")) > 4096:
            raise ValueError("Sitzungspfad ist zu lang.")
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / f"launch-{nonce}.tmp"
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return cls(path, nonce)

    def revoke(self):
        try:
            # Do not remove a newer launcher's ticket.
            with self.path.open(encoding="utf-8") as stream:
                content = stream.read(4097)
            if f"nonce={self.nonce}" in content.splitlines():
                self.path.unlink(missing_ok=True)
        except (OSError, UnicodeError):
            pass  # Expiry and owner liveness also invalidate an abandoned ticket.


class TrackedGame:
    """Keep the relay alive while Steam replaces the initially launched process."""
    def __init__(self, bootstrap, directory: Path, game_exe: Path, lease: LaunchLease,
                 started_filetime: int, *, inspect=process_info, clock=time.monotonic):
        self.bootstrap, self.directory, self.game_exe, self.lease = bootstrap, directory, game_exe.resolve(), lease
        self.started_filetime, self.inspect, self.clock = started_filetime, inspect, clock
        self.deadline = clock() + 120
        self.actual: ProcessInfo | None = None
        self.pid = bootstrap.pid
        self.exit_code = None
        self.startup_failed = False

    def _candidate(self):
        try:
            with (self.directory / "tpf2_instance.txt").open(encoding="ascii") as stream:
                lines = stream.read(1024).splitlines()
            fields = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
            pid = int(fields.get("pid", "0"))
            info = self.inspect(pid)
            if (info and info.created >= self.started_filetime
                    and os.path.normcase(info.executable) == os.path.normcase(str(self.game_exe))):
                return info
        except (OSError, UnicodeError, ValueError):
            pass
        return None

    def poll(self):
        if self.exit_code is not None:
            return self.exit_code
        if self.actual is not None:
            current = self.inspect(self.actual.pid)
            if current is None or current.created != self.actual.created:
                self.exit_code = 0
                self.lease.revoke()
            return self.exit_code
        candidate = self._candidate()
        if candidate is not None:
            self.pid = candidate.pid
            # The replacement is the real Steam game. The original remains a
            # bootstrap candidate until it has loaded Lua or the grace expires.
            dashboard = any(self.directory.glob("lockstep_dash_*.txt"))
            if candidate.pid != self.bootstrap.pid or dashboard or self.clock() >= self.deadline:
                self.actual = candidate
                self.lease.revoke()
        if self.actual is not None:
            current = self.inspect(self.actual.pid)
            if current is None or current.created != self.actual.created:
                self.exit_code = 0
        elif self.bootstrap.poll() is not None and self.clock() >= self.deadline:
            self.startup_failed = True
            self.exit_code = 1
        if self.exit_code is not None:
            self.lease.revoke()
        return self.exit_code


def filetime_now() -> int:
    return time.time_ns() // 100 + FILETIME_EPOCH
