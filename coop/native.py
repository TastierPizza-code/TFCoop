"""Version-gated native runtime installation and isolated two-player sessions.

The audio proxy enables hooks for explicit co-op launches, including Steam's
replacement process with a validated launch ticket. This module never starts the game.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import tempfile
import uuid

from .install import InstallError, _files, _hash, _is_game

EXPECTED_TIMESTAMP = 0x675ABCC6
EXPECTED_IMAGE_SIZE = 0x046CE000
EXPECTED_SHA256 = "782b904a8f7bbdac1f7a18528f1a5c778691e5aa3087c37c351bf6912585175c"
STOCK_ALUT_SHA256 = "3df103ae3d94a6b90c4d2a6d75dcb388cd835f5e3af9962b22c20d4473cfc035"
STATE_DIR = ".tf2coop-native"
MOD_DIR = "mods/mp_lockstep_1"
VERSION = "7e8e49e-coop3"
DLL_NAMES = ("alut.dll", "tpf2_bridge_mp.dll", "tpf2_slice.dll")


class NativeError(InstallError):
    """Native files are incompatible, conflicting, or cannot be changed safely."""


def game_is_running() -> bool:
    """Inspect process names without interacting with windows or starting a shell."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise NativeError(f"Could not inspect running game processes (Windows error {ctypes.get_last_error()})")
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        success = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        if not success:
            raise NativeError("Could not read the Windows process list")
        while success:
            if entry.szExeFile.casefold() == "transportfever2.exe":
                return True
            success = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return False
    finally:
        kernel.CloseHandle(snapshot)


def _require_game_closed() -> None:
    if game_is_running():
        raise NativeError("Transport Fever 2 is already running. Close it before installing, removing, or starting a co-op session.")


def _pe(path: Path) -> dict:
    with path.open("rb") as file:
        dos = file.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError("not a Windows PE executable")
        offset = struct.unpack_from("<I", dos, 0x3C)[0]
        if offset < 64 or offset > 16 * 1024 * 1024:
            raise ValueError("invalid PE header location")
        file.seek(offset)
        header = file.read(88)
        if len(header) != 88 or header[:4] != b"PE\0\0":
            raise ValueError("invalid or truncated PE header")
        machine, timestamp = struct.unpack_from("<H", header, 4)[0], struct.unpack_from("<I", header, 8)[0]
        if struct.unpack_from("<H", header, 24)[0] != 0x20B or machine != 0x8664:
            raise ValueError("native multiplayer requires the Windows x64 build")
        return {"timestamp": timestamp, "size_of_image": struct.unpack_from("<I", header, 80)[0],
                "machine": machine, "is_dll": bool(struct.unpack_from("<H", header, 22)[0] & 0x2000)}


def check_game_build(game_dir: str | os.PathLike[str]) -> dict:
    """Read PE metadata and the complete executable hash; never modify the game."""
    game = Path(game_dir).resolve()
    status = {"compatible": False, "installed": False, "game_dir": str(game), "reason": ""}
    try:
        if not _is_game(game):
            raise ValueError("Transport Fever 2 executable and res directory were not found")
        status.update(_pe(game / "TransportFever2.exe"))
        status["sha256"] = _hash(game / "TransportFever2.exe")
        status["compatible"] = (status["timestamp"] == EXPECTED_TIMESTAMP
                                and status["size_of_image"] == EXPECTED_IMAGE_SIZE
                                and status["sha256"] == EXPECTED_SHA256)
        if not status["compatible"]:
            status["reason"] = "This executable is not the supported Transport Fever 2 Windows build."
        if (game / STATE_DIR).exists():
            manifest = _read_manifest(game)
            _verify_installed(game, manifest)
            status["installed"] = True
            status["active_version"] = manifest["version"]
    except (OSError, ValueError, NativeError, InstallError) as exc:
        status["reason"] = str(exc)
    return status


def _path(game: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if not relative or name.is_absolute() or ".." in name.parts or "\\" in relative or ":" in relative:
        raise NativeError("Invalid native installation manifest path")
    path = game.joinpath(*name.parts)
    if path.resolve() != path.absolute():
        raise NativeError(f"Refusing linked native installation path: {path}")
    return path


def _read_manifest(game: Path) -> dict:
    path = _path(game, STATE_DIR + "/manifest.json")
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("manifest too large")
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("owner") != "tf2coop-native"
                or value.get("format") != 1 or not isinstance(value.get("version"), str)
                or not isinstance(value.get("files"), dict) or not value["files"]
                or value.get("original_alut_sha256") != STOCK_ALUT_SHA256):
            raise ValueError("invalid ownership manifest")
        for relative, digest in value["files"].items():
            _path(game, relative)
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("invalid ownership hash")
            if relative not in (*DLL_NAMES, "alut_real.dll") and not relative.startswith(MOD_DIR + "/"):
                raise ValueError("unexpected owned native file")
        if not all(name in value["files"] for name in (*DLL_NAMES, "alut_real.dll", MOD_DIR + "/mod.lua")):
            raise ValueError("incomplete ownership manifest")
        return value
    except (OSError, ValueError, TypeError) as exc:
        raise NativeError(f"Unrecognized or incomplete native installation: {exc}") from exc


def _verify_installed(game: Path, manifest: dict) -> None:
    for relative, digest in manifest["files"].items():
        path = _path(game, relative)
        if not path.is_file() or _hash(path) != digest:
            raise NativeError(f"Native installation has changed: {path}. Preserve local edits before updating or uninstalling.")
    actual = {f"{MOD_DIR}/{name}": digest for name, digest in _files(_path(game, MOD_DIR)).items()}
    expected = {name: digest for name, digest in manifest["files"].items() if name.startswith(MOD_DIR + "/")}
    if actual != expected:
        raise NativeError("The installed lockstep mod contains extra or modified files")
    original = _path(game, STATE_DIR + "/original/alut.dll")
    if not original.is_file() or _hash(original) != manifest["original_alut_sha256"]:
        raise NativeError("The original audio DLL backup is missing or has changed")


def _cleanup_work(path: Path, game: Path) -> None:
    if path.resolve().parent != game.resolve() or not path.name.startswith(".tf2coop-native-") or path.is_symlink():
        raise NativeError(f"Refusing unexpected cleanup path: {path}")
    shutil.rmtree(path)


def _empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


def _apply_transaction(game: Path, replacements: dict[str, Path | None], work: Path) -> None:
    """Keep previous bytes for every touched file until all replacements succeed."""
    for relative in replacements:
        _path(game, relative)
    journal: list[tuple[Path, Path | None]] = []
    try:
        for index, (relative, incoming) in enumerate(replacements.items()):
            target = _path(game, relative)
            old = work / f"rollback-{index}"
            existed = target.exists()
            if existed:
                shutil.copy2(target, old)
            target.parent.mkdir(parents=True, exist_ok=True)
            if incoming is None:
                target.unlink()
            else:
                pending = work / f"pending-{index}"
                shutil.copy2(incoming, pending)
                os.replace(pending, target)
            journal.append((target, old if existed else None))
    except OSError as failure:
        rollback_errors = []
        for target, old in reversed(journal):
            try:
                if old is None:
                    target.unlink(missing_ok=True)
                else:
                    os.replace(old, target)
            except OSError as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            # Keep work/rollback files when recovery itself is prevented by a
            # file lock. The caller deliberately leaves this directory intact.
            raise NativeError(f"Installation failed ({failure}); recovery files remain at {work}: {'; '.join(rollback_errors)}") from failure
        raise NativeError(f"Native file update failed and previous files were restored: {failure}") from failure


def install_native(game_dir: str | os.PathLike[str], runtime_dir: str | os.PathLike[str],
                   mod_source: str | os.PathLike[str]) -> dict:
    game, runtime, source = Path(game_dir).resolve(), Path(runtime_dir).resolve(), Path(mod_source).resolve()
    status = check_game_build(game)
    if not status["compatible"]:
        raise NativeError(status["reason"] or "Unsupported executable")
    _require_game_closed()
    try:
        for name in DLL_NAMES:
            path = runtime / name
            if not path.is_file() or not _pe(path)["is_dll"]:
                raise NativeError(f"Native runtime build is missing or invalid: {path}")
        if not source.is_dir() or not (source / "mod.lua").is_file():
            raise NativeError("The lockstep mod source is missing")
        source_files = _files(source)
        if _path(game, MOD_DIR).is_relative_to(source) or source.is_relative_to(game):
            raise NativeError("Native mod source must be outside the game installation")
        state = _path(game, STATE_DIR)
        previous = _read_manifest(game) if state.exists() else None
        if previous is not None:
            _verify_installed(game, previous)
        else:
            if not (game / "alut.dll").is_file() or _hash(game / "alut.dll") != STOCK_ALUT_SHA256:
                raise NativeError("The game's alut.dll is not the recognized original audio library; refusing to replace it")
            for relative in ("alut_real.dll", "tpf2_bridge_mp.dll", "tpf2_slice.dll", MOD_DIR):
                if _path(game, relative).exists():
                    raise NativeError(f"An unrelated file or mod already exists: {game / relative}")
        work = Path(tempfile.mkdtemp(prefix=".tf2coop-native-stage-", dir=game))
        preserve_work = False
        try:
            payload: dict[str, Path] = {name: runtime / name for name in DLL_NAMES}
            payload.update({f"{MOD_DIR}/{name}": source / name for name in source_files})
            original = game / (STATE_DIR + "/original/alut.dll") if previous else game / "alut.dll"
            stock = work / "original-alut.dll"
            shutil.copy2(original, stock)
            payload["alut_real.dll"] = stock
            staged_payload = {}
            for index, (name, path) in enumerate(payload.items()):
                staged_file = work / f"payload-{index}"
                shutil.copy2(path, staged_file)
                staged_payload[name] = staged_file
            payload = staged_payload
            hashes = {name: _hash(path) for name, path in payload.items()}
            if previous is not None and previous["files"] == hashes:
                return {"installed": True, "changed": False, "game_dir": str(game), "version": VERSION}
            replacements: dict[str, Path | None] = {}
            if previous is None:
                replacements[STATE_DIR + "/original/alut.dll"] = stock
            replacements.update(payload)
            if previous:
                replacements.update({name: None for name in previous["files"] if name not in payload})
            manifest = {"owner": "tf2coop-native", "format": 1, "version": VERSION,
                        "original_alut_sha256": STOCK_ALUT_SHA256, "game_sha256": status["sha256"], "files": hashes}
            manifest_path = work / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            replacements[STATE_DIR + "/manifest.json"] = manifest_path
            try:
                _apply_transaction(game, replacements, work)
            except NativeError as exc:
                preserve_work = "recovery files remain" in str(exc)
                if previous is None and not preserve_work:
                    _empty_dirs(state)
                    _empty_dirs(game / MOD_DIR)
                raise
            return {"installed": True, "changed": True, "game_dir": str(game), "version": VERSION,
                    "backup_path": str(game / STATE_DIR / "original/alut.dll")}
        finally:
            if not preserve_work:
                _cleanup_work(work, game)
    except (OSError, ValueError) as exc:
        raise NativeError(f"Native installation failed: {exc}") from exc


def uninstall_native(game_dir: str | os.PathLike[str]) -> dict:
    """Restore the exact original DLL and remove only unchanged owned files."""
    game = Path(game_dir).resolve()
    if not (game / STATE_DIR).exists():
        return {"installed": False, "changed": False, "game_dir": str(game)}
    _require_game_closed()
    manifest = _read_manifest(game)
    _verify_installed(game, manifest)
    work = Path(tempfile.mkdtemp(prefix=".tf2coop-native-remove-", dir=game))
    preserve_work = False
    try:
        original = work / "original-alut.dll"
        shutil.copy2(_path(game, STATE_DIR + "/original/alut.dll"), original)
        replacements = {name: None for name in manifest["files"] if name != "alut.dll"}
        replacements["alut.dll"] = original
        replacements[STATE_DIR + "/manifest.json"] = None
        replacements[STATE_DIR + "/original/alut.dll"] = None
        try:
            _apply_transaction(game, replacements, work)
        except NativeError as exc:
            preserve_work = "recovery files remain" in str(exc)
            raise
        _empty_dirs(game / MOD_DIR)
        _empty_dirs(game / STATE_DIR)
        return {"installed": False, "changed": True, "game_dir": str(game), "restored_original_audio": True}
    except OSError as exc:
        raise NativeError(f"Native uninstall failed: {exc}") from exc
    finally:
        if not preserve_work:
            _cleanup_work(work, game)


def prepare_session(game_dir: str | os.PathLike[str], data_dir: str | os.PathLike[str],
                    role: str, peer_ip: str) -> dict:
    """Create fresh command/log files and return child-process environment values."""
    status = check_game_build(game_dir)
    if not status["compatible"] or not status["installed"]:
        raise NativeError(status["reason"] or "Install the compatible native runtime before starting a session")
    _require_game_closed()
    if role not in ("host", "guest"):
        raise NativeError("Session role must be host or guest")
    try:
        address = ipaddress.IPv4Address(peer_ip)
        if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
            raise ValueError("not a unicast peer address")
    except ipaddress.AddressValueError as exc:
        raise NativeError("Native sessions require the friend's LAN or Hamachi IPv4 address") from exc
    except ValueError as exc:
        raise NativeError(str(exc)) from exc
    directory = Path(data_dir).expanduser().resolve() / f"session-{role}-{uuid.uuid4().hex[:12]}"
    if len(str(directory)) > 200:
        raise NativeError("The native session directory path must be shorter than 200 characters")
    instance, local_port, peer_port = ("a", 7771, 7772) if role == "host" else ("b", 7772, 7771)
    bridge_config = (f"local_port={local_port}\npeer_ip={address}\npeer_port={peer_port}\ninstance={instance}\n"
                     "xfer_port=0\nauto_pull=0\nsim_hook=1\nbuy_hook=0\n")
    slice_config = ("enabled=1\nsuppress=1\nmerge=1\ncancel_vehicle=1\ncancel_line=1\n"
                    "dumpprop=0\nconx_strict=1\nroad_demolish=1\nstrict_buy=0\n"
                    "strict_barrier=0\nload_gate=1\nexpect_players=2\n")
    try:
        directory.mkdir(parents=True, exist_ok=False)
        config_path = directory / "tpf2_bridge_mp.cfg"
        config_path.write_text(bridge_config, encoding="ascii")
        (directory / "tpf2_slice.cfg").write_text(slice_config, encoding="ascii")
        (directory / "tpf2_instance.txt").write_text(f"{instance}\n", encoding="ascii")
    except OSError as exc:
        raise NativeError(f"Could not prepare native session: {exc}") from exc
    return {"role": role, "instance": instance, "udp_port": local_port, "peer_port": peer_port,
            "peer_ip": str(address), "data_dir": str(directory), "config_path": str(config_path),
            "env": {"TF2COOP_SESSION": "1", "TPF2MP_DATADIR": str(directory)}}
