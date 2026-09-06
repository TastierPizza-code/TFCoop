"""Windows CRT integration for the actual Lua activation guard; no game or UI.

A disposable native pipe models the wire transport in this Python test process.
Production server/PID-gate code is exercised separately by native/test_launch.cmd.
This checks the real Lua file functions, exact-length reads, same-PID acceptance,
and a different-process rejection. No game files, DLLs or sockets are accessed.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / ".deps"))
SOURCE = ROOT / "upstream/tpf2-multiplayer/mod/mp_lockstep_1/res/config/game_script/lockstep.lua"


def guard(pipe_suffix: str):
    from lupa.lua53 import LuaRuntime
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("os.getenv = nil; os.rename = nil; os.remove = nil")
    code = SOURCE.read_text(encoding="utf-8").split("-- MP Lockstep -- prototype.")[0]
    code = code.replace("TF2CoopActivation", "TF2CoopActivationTest-" + pipe_suffix)
    return lua.execute(code + "\nreturn K.ACTIVATION\n")


if os.name != "nt":
    print("SKIP: Windows named pipe integration requires Windows")
    raise SystemExit(0)

if len(sys.argv) == 3 and sys.argv[1] == "--foreign-client":
    assert guard(sys.argv[2]) is None
    print("PASS foreign Lua process remains passive")
    raise SystemExit(0)

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, wintypes.LPVOID]
k.CreateNamedPipeW.restype = wintypes.HANDLE
k.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
k.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
k.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                       ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
k.FlushFileBuffers.argtypes = [wintypes.HANDLE]
k.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
k.CloseHandle.argtypes = [wintypes.HANDLE]

payload = ("format=1\nactive=1\ndata_dir=C:/pipe-test-session\n"
           "game_exe=X:/test/TransportFever2.exe\n"
           f"game_pid={os.getpid()}\nnonce=0123456789abcdef0123456789abcdef\n").encode("utf-8")
wire = f"{len(payload):04d}".encode("ascii") + payload


def server(suffix: str):
    name = "\\\\.\\pipe\\TF2CoopActivationTest-" + suffix
    handle = k.CreateNamedPipeW(name, 2, 8, 1, 4096, 4096, 1000, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    outcome: list[object] = []

    def serve():
        try:
            connected = k.ConnectNamedPipe(handle, None)
            assert connected or ctypes.get_last_error() == 535
            client = wintypes.ULONG()
            assert k.GetNamedPipeClientProcessId(handle, ctypes.byref(client))
            if client.value == os.getpid():
                written = wintypes.DWORD()
                assert k.WriteFile(handle, wire, len(wire), ctypes.byref(written), None)
                assert written.value == len(wire)
                assert k.FlushFileBuffers(handle)
            outcome.append(client.value)
        except BaseException as error:
            outcome.append(error)
        finally:
            k.DisconnectNamedPipe(handle)
            k.CloseHandle(handle)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread, outcome


suffix = str(os.getpid()) + "-same"
thread, outcome = server(suffix)
activation = guard(suffix)
thread.join(2)
assert outcome == [os.getpid()], outcome
assert activation["source"] == "native process pipe"
assert activation["data_dir"] == "C:/pipe-test-session"
print("PASS actual Lua5.3 guard reads native Windows pipe without getenv/rename/remove")

suffix = str(os.getpid()) + "-foreign"
thread, outcome = server(suffix)
child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--foreign-client", suffix],
                       capture_output=True, text=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
thread.join(2)
assert child.returncode == 0, child.stdout + child.stderr
assert len(outcome) == 1 and isinstance(outcome[0], int) and outcome[0] != os.getpid(), outcome
print(child.stdout.strip())
assert guard(str(os.getpid()) + "-absent") is None
print("PASS absent native pipe keeps actual Lua guard passive")
