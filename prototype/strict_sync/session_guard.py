"""OS-owned lobby lifetime, independent from the later game-controller lease."""
from __future__ import annotations

import ctypes
import os

LOBBY_MUTEX = "Local\\TF2StrictProbeLobby"
CONTROLLER_MUTEX = "Local\\TF2StrictProbeController"


def _kernel():
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel


def named_mutex_active(name):
    if os.name != "nt":
        return False
    kernel = _kernel()
    handle = kernel.OpenMutexW(0x00100000, False, name)
    if handle:
        kernel.CloseHandle(handle)
        return True
    # Only NAME_NOT_FOUND proves absence; access denied remains occupied.
    return ctypes.get_last_error() != 2


def lobby_active():
    return named_mutex_active(LOBBY_MUTEX)


class LobbyGuard:
    """Presence mutex, automatically removed when its sole owner process dies.

    The installer first creates the controller mutex and then checks the lobby;
    the lobby does the reverse. Either ordering rejects an overlapping start.
    Once admitted, the lobby permits its later game worker to own the separate
    controller mutex throughout measurement.
    """
    def __init__(self, *, name=LOBBY_MUTEX, controller_name=CONTROLLER_MUTEX):
        self.handle = None
        self.kernel = None
        if os.name != "nt":
            return
        self.kernel = _kernel()
        self.handle = self.kernel.CreateMutexW(None, False, name)
        existed = ctypes.get_last_error() == 183
        try:
            if not self.handle or existed:
                raise ValueError("Ein Test wartet bereits auf die Verbindung. Alten Test zuerst beenden.")
            if named_mutex_active(controller_name):
                raise ValueError("Ein Messcontroller oder eine Installation ist noch aktiv. Zuerst beenden.")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
