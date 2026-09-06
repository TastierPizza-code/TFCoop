"""Startup handoff helpers. Importing this module starts nothing."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess

from coop.native import game_is_running


def session_active() -> bool:
    if game_is_running():
        return True
    if os.name != "nt":
        return False
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenMutexW(0x00100000, False, "Local\\TF2StrictProbeController")
    if handle:
        kernel.CloseHandle(handle)
        return True
    error = ctypes.get_last_error()
    if error == 2:
        return False
    # Access denied also means an existing controller may own the name.
    return True


def handoff(executable: Path) -> None:
    executable = Path(executable).resolve(strict=True)
    if executable.name != "TF2-Coop.exe" or not executable.is_file():
        raise ValueError("Ungültiges Updateprogramm.")
    if session_active():
        raise ValueError("Update vorbereitet. TF2 und den laufenden Test zuerst schließen; Launcher dann neu starten.")
    subprocess.Popen([str(executable), "--updated-launch"], cwd=executable.parent,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
