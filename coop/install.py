"""Steam discovery and conservative, recoverable installation of our own mod."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any

APP_ID = "1066780"
MOD_NAME = "tf2coop_1"
MARKER = ".tf2coop-install.json"
_OWNER = "transport-fever-coop-companion"


class InstallError(RuntimeError):
    """A mod installation is invalid, conflicts with local files, or failed."""


def _vdf(text: str) -> dict[str, Any]:
    tokens = re.finditer(r'"((?:\\.|[^"\\])*)"|([{}])|//[^\n]*', text)
    stream = iter([(re.sub(r'\\([\\"])', r'\1', match.group(1)) if match.group(1) is not None else match.group(2))
                   for match in tokens if match.group(1) is not None or match.group(2)])

    def object_value(nested: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in stream:
            if key == "}":
                if not nested:
                    raise ValueError("unexpected VDF closing brace")
                return result
            value = next(stream)
            result[key] = object_value(True) if value == "{" else value
        if nested:
            raise ValueError("unclosed VDF object")
        return result

    try:
        return object_value()
    except StopIteration as exc:
        raise ValueError("incomplete VDF pair") from exc


def _steam_roots() -> list[Path]:
    paths: list[Path] = []
    if os.name == "nt":
        try:
            import winreg
            keys = [(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")]
            for hive, key, value in keys:
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        path, _ = winreg.QueryValueEx(handle, value)
                    paths.append(Path(path))
                except OSError:
                    pass
        except ImportError:
            pass
        for variable in ("ProgramFiles(x86)", "ProgramFiles"):
            if os.environ.get(variable):
                paths.append(Path(os.environ[variable]) / "Steam")
        # Also find common alternate libraries even if Steam's registry or VDF
        # is incomplete (e.g. a moved library on X:).
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for index in range(26):
            if mask & (1 << index):
                drive = Path(f"{chr(ord('A') + index)}:/")
                paths.extend((drive / "SteamLibrary", drive / "Steam"))
    else:
        paths.extend((Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"))
    return paths


def _is_game(directory: Path) -> bool:
    return directory.is_dir() and (directory / "res").is_dir() and any(
        (directory / name).is_file() for name in ("TransportFever2.exe", "TransportFever2"))


def discover_game() -> Path | None:
    """Discover installed game data through registered and common Steam libraries."""
    roots = _steam_roots()
    libraries = list(roots)
    for root in roots:
        for vdf_path in (root / "steamapps/libraryfolders.vdf", root / "config/libraryfolders.vdf"):
            try:
                folders = _vdf(vdf_path.read_text(encoding="utf-8-sig"))
                folders = folders.get("libraryfolders", folders.get("LibraryFolders", {}))
                if isinstance(folders, dict):
                    for key, entry in folders.items():
                        path = entry.get("path") if isinstance(entry, dict) else entry
                        if key.isdigit() and isinstance(path, str) and path:
                            libraries.append(Path(path))
            except (OSError, ValueError, UnicodeError):
                continue
    seen: set[str] = set()
    for library in libraries:
        key = str(library.absolute()).casefold()
        if key in seen:
            continue
        seen.add(key)
        steamapps = library / "steamapps"
        try:
            manifest = _vdf((steamapps / f"appmanifest_{APP_ID}.acf").read_text(encoding="utf-8-sig"))
            install_dir = manifest.get("AppState", {}).get("installdir")
            if isinstance(install_dir, str) and install_dir and "/" not in install_dir and "\\" not in install_dir and install_dir not in (".", ".."):
                candidate = steamapps / "common" / install_dir
                if _is_game(candidate):
                    return candidate.resolve()
        except (OSError, ValueError, UnicodeError, AttributeError):
            pass
        fallback = steamapps / "common/Transport Fever 2"
        if _is_game(fallback):
            return fallback.resolve()
    return None


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _files(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in directory.rglob("*"):
        # resolve() also detects Windows directory junctions, which older
        # Python versions do not classify as symlinks.
        if path.is_symlink() or path.resolve() != path.absolute():
            raise InstallError(f"Linked paths are not supported in a mod installation: {path}")
        if path.is_file() and path != directory / MARKER:
            result[path.relative_to(directory).as_posix()] = _hash(path)
        elif not path.is_dir() and path != directory / MARKER:
            raise InstallError(f"Unsupported mod file: {path}")
    return result


def _verify_owned(target: Path) -> dict[str, str]:
    marker = target / MARKER
    try:
        if marker.stat().st_size > 1024 * 1024:
            raise ValueError("ownership manifest is too large")
        value = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("owner") != _OWNER or value.get("format") != 1:
            raise ValueError("ownership marker is invalid")
        files = value.get("files")
        if not isinstance(files, dict) or not files or len(files) > 10000:
            raise ValueError("ownership file list is invalid")
        for name, digest in files.items():
            if (not isinstance(name, str) or not name or "\\" in name
                    or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                    or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                raise ValueError("ownership file entry is invalid")
        if files != _files(target):
            raise InstallError(f"Local edits or extra files exist in {target}. Preserve or move that folder before reinstalling.")
        return files
    except (OSError, ValueError, TypeError) as exc:
        raise InstallError(f"Refusing to overwrite an unrecognized mod folder: {target} ({exc})") from exc


def _lua_string(value: str) -> str:
    pieces = ['"']
    for char in value:
        if char in ('"', "\\"):
            pieces.append("\\" + char)
        elif ord(char) < 32 or ord(char) == 127:
            pieces.append(f"\\{ord(char):03d}")
        else:
            pieces.append(char)
    return "".join(pieces) + '"'


def _remove_workdir(path: Path, mods: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != mods.resolve() or not path.name.startswith(".tf2coop-") or path.is_symlink():
        raise InstallError(f"Refusing to clean up an unexpected path: {path}")
    shutil.rmtree(path)


def install_mod(game_dir: str | os.PathLike[str], source_dir: str | os.PathLike[str],
                mailbox_dir: str | os.PathLike[str]) -> Path:
    """Install/update a pristine owned copy; refuse unknown folders and user edits.

    Validation occurs before staging. Updates move the previous owned copy to a
    temporary backup and restore it if the replacement cannot be placed.
    """
    game, source = Path(game_dir).resolve(), Path(source_dir).resolve()
    mailbox = Path(mailbox_dir).expanduser().resolve()
    if not _is_game(game):
        raise InstallError(f"Transport Fever 2 was not found in {game}")
    if not source.is_dir() or not (source / "mod.lua").is_file():
        raise InstallError(f"Mod source is incomplete: {source}")
    mods = game / "mods"
    if mods.exists() and (not mods.is_dir() or mods.resolve() != game / "mods"):
        raise InstallError(f"The game's mods path is linked or invalid: {mods}")
    target = mods / MOD_NAME
    if target.is_symlink() or target.resolve() != mods / MOD_NAME:
        raise InstallError(f"Refusing to install over a linked mod folder: {target}")
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise InstallError("The source must be separate from the installed mod")
    try:
        _files(source)
        previous = _verify_owned(target) if target.exists() else None
        mods.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".tf2coop-stage-", dir=mods))
        backup: Path | None = None
        try:
            shutil.copytree(source, stage, dirs_exist_ok=True)
            config = stage / "res/scripts/tf2coop/config.lua"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text("-- Generated locally by the companion installer.\nreturn { mailbox_dir = "
                              + _lua_string(mailbox.as_posix()) + " }\n", encoding="utf-8")
            current = _files(stage)
            (stage / MARKER).write_text(json.dumps({"owner": _OWNER, "format": 1, "files": current},
                                                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if previous == current:
                return target
            if target.exists():
                if previous is None or _verify_owned(target) != previous:
                    raise InstallError("The installed mod changed while the update was staged")
                backup = Path(tempfile.mkdtemp(prefix=".tf2coop-backup-", dir=mods))
                backup.rmdir()
                os.replace(target, backup)
            try:
                os.replace(stage, target)
            except OSError:
                if backup is not None and backup.exists() and not target.exists():
                    os.replace(backup, target)
                raise
            if backup is not None and backup.exists():
                _remove_workdir(backup, mods)
            return target
        finally:
            if stage.exists():
                _remove_workdir(stage, mods)
    except OSError as exc:
        raise InstallError(f"Could not install the mod: {exc}") from exc
