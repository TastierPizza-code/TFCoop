"""Reversible installation of a locally staged, explicitly selected TF2 probe.

The public functions never start the game. Existing Alpha DLL bytes are backed
up exactly; existing mods and save metadata are not edited. Restore preserves
imported test saves and refuses to overwrite subsequent user changes.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import threading
import time
import uuid

from coop import native
from coop.launch import process_info
from coop.session import hash_file
from .core import decode_message, digest
from .session_guard import lobby_active
from .stage_probe import (CONFIG, MOD, REQUIRED_MOD_FILES, _config, StageError,
                          validate_configuration_semantics)


STATE_DIR = ".tf2-strict-probe-install"
OWNER = "tf2-strict-probe-installer"
SHA = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"[0-9a-f]{32}\Z")
_LOCAL_LOCK = threading.Lock()


class ProbeInstallError(RuntimeError):
    """The selected package cannot be installed or restored safely."""


def _root(value: str | Path) -> Path:
    path = Path(value).absolute()
    if path.resolve() != path or path.is_symlink() or not path.is_dir():
        raise ProbeInstallError(f"Missing, linked or noncanonical directory: {path}")
    return path


def _path(root: Path, relative: str) -> Path:
    if type(relative) is not str:
        raise ProbeInstallError("Invalid scoped installation path")
    parts = PurePosixPath(relative)
    if (type(relative) is not str or not relative or parts.is_absolute()
            or str(parts) != relative or any(p in (".", "..") or p.rstrip(" .") != p for p in parts.parts)
            or "\\" in relative or ":" in relative or "\0" in relative):
        raise ProbeInstallError("Invalid scoped installation path")
    path = root.joinpath(*parts.parts)
    if path.resolve() != path.absolute() or path.is_symlink():
        raise ProbeInstallError(f"Refusing linked installation path: {path}")
    return path


def _allowed(relative: str) -> bool:
    return relative in {"alut.dll", "alut_real.dll", "tf2_step_probe.dll"} or relative.startswith(f"mods/{MOD}/")


def _read_json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ProbeInstallError(f"Missing or oversized installation descriptor: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ProbeInstallError(f"Invalid installation descriptor: {path}") from exc
    if type(value) is not dict:
        raise ProbeInstallError("Installation descriptor must be an object")
    return value


def _write_json(path: Path, value: dict) -> None:
    data = (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode("ascii")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _current_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ProbeInstallError(f"Expected an ordinary file: {path}")
    return hash_file(path)


def _copy_exclusive(source: Path, target: Path, expected: str) -> None:
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    if hash_file(target) != expected:
        raise ProbeInstallError(f"Source changed during copying: {source}")


def _replace(source: Path, target: Path, expected: str, previous: str | None) -> None:
    temporary = target.with_name(".tf2-probe-" + uuid.uuid4().hex + ".tmp")
    try:
        _copy_exclusive(source, temporary, expected)
        if _current_hash(target) != previous:
            raise ProbeInstallError(f"File changed during installation: {target}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _require_closed() -> None:
    if native.game_is_running():
        raise ProbeInstallError("Transport Fever 2 muss vor Installation oder Wiederherstellung geschlossen sein.")
    # An explicit Alpha launch ticket can still be waiting for Steam's process.
    # Read only: do not revoke another launcher's session or operate its process.
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for folder in ("TF2Coop", "TF2StrictProbe"):
            path = Path(local) / folder / "launch.cfg"
            try:
                with path.open(encoding="utf-8") as stream:
                    raw = stream.read(4097)
                fields = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
                if len(raw) > 4096 or int(fields.get("expires", "0")) < time.time():
                    continue
                owner = process_info(int(fields.get("launcher_pid", "0")))
                if owner and owner.created == int(fields.get("launcher_created", "0")):
                    raise ProbeInstallError("Ein Koop-Start ist noch aktiv. Test bzw. alten Launcher zuerst beenden.")
            except (OSError, UnicodeError, ValueError):
                continue


@contextmanager
def _guard():
    """Share the runner's lifetime mutex; never create a stale on-disk lock."""
    if not _LOCAL_LOCK.acquire(blocking=False):
        raise ProbeInstallError("Another prototype installation is active")
    handle = None
    kernel = None
    try:
        if os.name == "nt":
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.CreateMutexW(None, False, "Local\\TF2StrictProbeController")
            existed = ctypes.get_last_error() == 183
            if not handle or existed:
                raise ProbeInstallError("Ein Messcontroller ist noch aktiv. Test zuerst beenden.")
        if lobby_active():
            raise ProbeInstallError("Ein Test wartet auf den Mitspieler oder ist noch verbunden. Test zuerst beenden.")
        _require_closed()
        yield
    finally:
        if handle:
            kernel.CloseHandle(handle)
        _LOCAL_LOCK.release()


def _load_journal(game: Path) -> tuple[Path, dict] | None:
    state = _path(game, STATE_DIR)
    pointer = _path(state, "current.json")
    if not pointer.exists():
        return None
    current = _read_json(pointer)
    if set(current) != {"owner", "run_id"} or current["owner"] != OWNER or not RUN.fullmatch(str(current["run_id"])):
        raise ProbeInstallError("Unrecognized prototype installation ownership")
    run = _path(state, "runs/" + current["run_id"])
    journal = _read_json(_path(run, "journal.json"))
    if (journal.get("owner") != OWNER or journal.get("format") != 1
            or journal.get("run_id") != current["run_id"] or journal.get("game_dir") != str(game)
            or journal.get("state") not in {"backed_up", "installing", "installed", "restoring", "restored", "install_failed"}
            or type(journal.get("files")) is not list or not 1 <= len(journal["files"]) <= 128
            or type(journal.get("created_dirs")) is not list):
        raise ProbeInstallError("Invalid recovery journal")
    seen = set()
    for entry in journal["files"]:
        if type(entry) is not dict or set(entry) != {"path", "original_sha256", "deployed_sha256"}:
            raise ProbeInstallError("Invalid recovery file record")
        relative = entry["path"]
        _path(game, relative)
        if relative in seen or not _allowed(relative) or not SHA.fullmatch(str(entry["deployed_sha256"])):
            raise ProbeInstallError("Invalid recovery file scope")
        seen.add(relative)
        if entry["original_sha256"] is not None and not SHA.fullmatch(str(entry["original_sha256"])):
            raise ProbeInstallError("Invalid backup hash")
    for relative in journal["created_dirs"]:
        _path(game, relative)
        if relative != "mods" and relative != f"mods/{MOD}" and not relative.startswith(f"mods/{MOD}/"):
            raise ProbeInstallError("Invalid created-directory scope")
    return run, journal


def _conflicts(game: Path, run: Path, journal: dict) -> list[str]:
    conflicts = []
    for entry in journal["files"]:
        target = _path(game, entry["path"])
        if entry["original_sha256"] is not None:
            backup = _path(run, "original/" + entry["path"])
            if _current_hash(backup) != entry["original_sha256"]:
                conflicts.append("Backup beschädigt: " + entry["path"])
        acceptable = {entry["deployed_sha256"]}
        if journal["state"] != "installed":
            acceptable.add(entry["original_sha256"])
        if _current_hash(target) not in acceptable:
            conflicts.append("Datei nachträglich verändert: " + entry["path"])
    return conflicts


def installation_status(game_dir: str | Path) -> dict:
    """Read-only status. A restored journal remains as recoverable history."""
    game = _root(game_dir)
    found = _load_journal(game)
    if found is None:
        return {"installed": False, "state": "absent", "restorable": False, "conflicts": []}
    run, journal = found
    restored = journal["state"] == "restored"
    conflicts = [] if restored else _conflicts(game, run, journal)
    return {"installed": not restored, "state": journal["state"], "restorable": not restored and not conflicts,
            "conflicts": conflicts, "run_id": journal["run_id"], "backup_path": str(run),
            "imported_save": journal.get("imported_save", "")}


def _verify_stage(game: Path, output: Path, session: Path) -> tuple[dict, dict]:
    build = native.check_game_build(game)
    if not build.get("compatible") or build.get("sha256") != native.EXPECTED_SHA256:
        raise ProbeInstallError("Nur der exakt geprüfte Windows-Spielbuild 35924 wird unterstützt.")
    if {path.name for path in session.iterdir()} != {"probe_setup.json", "probe_manifest.json", "probe_payload.json", "probe_epoch.txt"}:
        raise ProbeInstallError("Diese Messsitzung wurde bereits verwendet. Eine neue Sitzung vorbereiten.")
    setup = decode_message(_path(session, "probe_setup.json").read_bytes())
    manifest = decode_message(_path(session, "probe_manifest.json").read_bytes())
    other = decode_message(_path(output, "probe_manifest.json").read_bytes())
    if (setup.get("game_exe") != str(game / "TransportFever2.exe") or setup.get("protocol") != 1
            or digest(manifest) != setup.get("manifest_digest") or manifest != other
            or manifest.get("game_sha256") != native.EXPECTED_SHA256
            or manifest.get("backend") != "tf2_controlled_measurement"
            or manifest.get("complete_world_verified") is not False):
        raise ProbeInstallError("The staged package does not belong to this prepared game/session")
    payload = decode_message(_path(session, "probe_payload.json").read_bytes())
    if set(payload) != {"files"} or type(payload["files"]) is not dict or not 1 <= len(payload["files"]) <= 128:
        raise ProbeInstallError("Invalid local payload manifest")
    files = payload["files"]
    required = {"alut.dll", "alut_real.dll", "tf2_step_probe.dll"} | {f"mods/{MOD}/{name}" for name in REQUIRED_MOD_FILES}
    if not required <= files.keys():
        raise ProbeInstallError("Incomplete measurement package")
    payload_root = _root(output / "game")
    actual = set()
    for source in payload_root.rglob("*"):
        relative = source.relative_to(payload_root).as_posix()
        checked = _path(payload_root, relative)
        if checked.is_file():
            actual.add(relative)
        elif not checked.is_dir():
            raise ProbeInstallError("Unsupported payload filesystem object")
    if actual != files.keys():
        raise ProbeInstallError("Unexpected or missing staged files")
    for relative, expected in files.items():
        if not _allowed(relative) or not SHA.fullmatch(str(expected)):
            raise ProbeInstallError("Payload file is outside the measurement package scope")
        if _current_hash(_path(payload_root, relative)) != expected:
            raise ProbeInstallError("Staged file changed: " + relative)
        _path(game, relative)
        if relative in {"alut.dll", "alut_real.dll", "tf2_step_probe.dll"}:
            if manifest.get("prototype_files", {}).get("game/" + relative) != expected:
                raise ProbeInstallError("Native payload is not bound to the shared manifest")
        else:
            mod_relative = relative.removeprefix(f"mods/{MOD}/")
            if mod_relative != CONFIG and manifest.get("prototype_files", {}).get("mod/" + mod_relative) != expected:
                raise ProbeInstallError("Lua payload is not bound to the shared manifest")
    try:
        semantics = validate_configuration_semantics(manifest.get("config_semantics"))
    except StageError as exc:
        raise ProbeInstallError(str(exc)) from exc
    profile = semantics.get("profile")
    if type(setup.get("native_epoch")) is not int or not 0 < setup["native_epoch"] <= (1 << 53) - 1:
        raise ProbeInstallError("Invalid prepared native epoch")
    if _path(session, "probe_epoch.txt").read_text(encoding="ascii").strip() != str(setup["native_epoch"]):
        raise ProbeInstallError("Native loader epoch does not match the prepared session")
    expected_config = _config(session, setup["native_epoch"], {"initial_bindings": manifest["template_bindings"]},
                              profile, semantics.get("input_mode"))
    if _path(payload_root, f"mods/{MOD}/{CONFIG}").read_bytes() != expected_config.encode("utf-8"):
        raise ProbeInstallError("The local Lua configuration is not bound to this session and epoch")
    if files["alut_real.dll"] != native.STOCK_ALUT_SHA256:
        raise ProbeInstallError("The verified original audio library is required")
    save = manifest.get("save", {})
    for relative, key in (("save/initial.sav", "sav_sha256"), ("save/initial.sav.lua", "sav_lua_sha256")):
        if _current_hash(_path(output, relative)) != save.get(key) or not SHA.fullmatch(str(save.get(key))):
            raise ProbeInstallError("The shared save or its sidecar changed after preparation")
    return files, save


def _restore(game: Path, run: Path, journal: dict) -> dict:
    conflicts = _conflicts(game, run, journal)
    if conflicts:
        raise ProbeInstallError("Wiederherstellung blockiert; Änderungen zuerst sichern: " + "; ".join(conflicts))
    journal["state"] = "restoring"
    _write_json(run / "journal.json", journal)
    for entry in reversed(journal["files"]):
        target = _path(game, entry["path"])
        current = _current_hash(target)
        if current == entry["original_sha256"]:
            continue  # A previously interrupted restore already completed this file.
        if current != entry["deployed_sha256"]:
            raise ProbeInstallError("File changed during restoration: " + entry["path"])
        if entry["original_sha256"] is None:
            target.unlink()  # Exactly one verified file inside the journal scope.
        else:
            _replace(_path(run, "original/" + entry["path"]), target, entry["original_sha256"], current)
    for relative in sorted(journal["created_dirs"], key=lambda p: len(PurePosixPath(p).parts), reverse=True):
        directory = _path(game, relative)
        try:
            directory.rmdir()  # Never recursive; retain added user files and preexisting directories.
        except (FileNotFoundError, OSError):
            pass
    journal["state"] = "restored"
    _write_json(run / "journal.json", journal)
    return {"restored": True, "backup_path": str(run), "imported_save": journal.get("imported_save", "")}


def restore_probe(game_dir: str | Path) -> dict:
    """Restore exact pre-test files, preserving test saves and backup history."""
    with _guard():
        game = _root(game_dir)
        found = _load_journal(game)
        if found is None:
            return {"restored": False, "state": "absent"}
        run, journal = found
        if journal["state"] == "restored":
            return {"restored": True, "backup_path": str(run), "imported_save": journal.get("imported_save", "")}
        return _restore(game, run, journal)


def install_probe(game_dir: str | Path, staged_output: str | Path, save_dir: str | Path,
                  *, session_dir: str | Path) -> dict:
    """Install a verified local stage and import its save under a fresh name.

    All overwritten game files are backed up and the complete recovery journal
    is flushed before the first replacement. On failure, automatic restoration
    is attempted; conflicts retain the journal for explicit recovery.
    """
    with _guard():
        game, output, session, saves = map(_root, (game_dir, staged_output, session_dir, save_dir))
        if game == saves or game in saves.parents or saves == output or output in saves.parents:
            raise ProbeInstallError("The save directory must be separate from game and staging payload")
        state = installation_status(game)
        if state["installed"]:
            raise ProbeInstallError("Messdateien sind bereits installiert. Zuerst vorherige Installation wiederherstellen.")
        files, save_hashes = _verify_stage(game, output, session)
        run_id = uuid.uuid4().hex
        state_root = _path(game, STATE_DIR)
        run = _path(state_root, "runs/" + run_id)
        run.mkdir(parents=True, exist_ok=False)
        imported = _path(saves, "TF2-Koop-Messtest-" + run_id + ".sav")
        journal = {"owner": OWNER, "format": 1, "run_id": run_id, "game_dir": str(game),
                   "state": "backed_up", "imported_save": str(imported), "files": [], "created_dirs": []}
        # Backup preparation cannot alter the previous game, even if it fails.
        for relative, expected in sorted(files.items()):
            target = _path(game, relative)
            original = _current_hash(target)
            if original is not None:
                backup = _path(run, "original/" + relative)
                backup.parent.mkdir(parents=True, exist_ok=True)
                _copy_exclusive(target, backup, original)
            journal["files"].append({"path": relative, "original_sha256": original, "deployed_sha256": expected})
            directory = target.parent
            while directory != game and not directory.exists():
                name = directory.relative_to(game).as_posix()
                if name not in journal["created_dirs"]:
                    journal["created_dirs"].append(name)
                directory = directory.parent
        _write_json(run / "journal.json", journal)
        _write_json(state_root / "current.json", {"owner": OWNER, "run_id": run_id})
        imported_files = []
        try:
            _require_closed()  # Recheck after potentially large file hashing and backups.
            for source_name, target, key in (("initial.sav", imported, "sav_sha256"),
                                             ("initial.sav.lua", Path(str(imported) + ".lua"), "sav_lua_sha256")):
                _copy_exclusive(output / "save" / source_name, target, save_hashes[key])
                imported_files.append((target, save_hashes[key]))
            journal["state"] = "installing"
            _write_json(run / "journal.json", journal)
            for entry in journal["files"]:
                target = _path(game, entry["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                _replace(_path(output / "game", entry["path"]), target,
                         entry["deployed_sha256"], entry["original_sha256"])
            journal["state"] = "installed"
            _write_json(run / "journal.json", journal)
        except Exception as exc:
            journal["state"] = "install_failed"
            try:
                _write_json(run / "journal.json", journal)
                _restore(game, run, journal)
            except Exception as recovery:
                raise ProbeInstallError(f"Installation fehlgeschlagen: {exc}. Wiederherstellung benötigt Hilfe: {recovery}. Backup: {run}") from exc
            for target, expected in imported_files:
                if _current_hash(target) == expected:
                    target.unlink()
            raise ProbeInstallError(f"Installation fehlgeschlagen; Spieldateien wurden wiederhergestellt: {exc}") from exc
        return {"installed": True, "run_id": run_id, "imported_save": str(imported), "backup_path": str(run)}
