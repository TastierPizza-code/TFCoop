"""Keep the private test save locally when public packages contain only its hashes.

Only the current package, one recorded previous run and an explicit user choice
are candidate sources. This module never downloads a save or writes into TF2.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid


MAX_JSON_BYTES = 1024 * 1024
MAX_SAVE_BYTES = 8 * 1024 * 1024 * 1024
MAX_LUA_BYTES = 16 * 1024 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_GUIDANCE = ("Bitte im alten Paketordner die Datei Testspielstand/initial.sav auswählen. "
             "Die zugehörige initial.sav.lua muss daneben liegen. "
             "Der private Spielstand wird nicht von GitHub heruntergeladen.")


class BaselineError(ValueError):
    """The required private save pair cannot be safely resolved."""


@dataclass(frozen=True)
class _Identity:
    sav_sha256: str
    sav_lua_sha256: str
    sav_bytes: int | None = None
    sav_lua_bytes: int | None = None

    @property
    def cache_key(self):
        value = self.sav_sha256 + ":" + self.sav_lua_sha256
        return hashlib.sha256(value.encode("ascii")).hexdigest()


def _absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def _plain_path(path):
    """Reject links/junctions in every existing component before reading/writing."""
    path = _absolute(path)
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise BaselineError("Verknüpfungen oder Junctions sind für den Testspielstand nicht erlaubt: "
                                + str(component))
    return path


def _inside(path, parent):
    path, parent = _absolute(path), _absolute(parent)
    return path != parent and path.is_relative_to(parent)


def _open_regular(path, limit):
    path = _plain_path(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
                or info.st_size > limit):
            raise BaselineError("Ungültige oder zu große Testspielstand-Datei: " + str(path))
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _json(path):
    with _open_regular(path, MAX_JSON_BYTES) as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise BaselineError("Die Metadaten für den Testspielstand sind zu groß.")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise BaselineError("Die Metadaten für den Testspielstand sind ungültig.")
    return value


def _identity(package_dir):
    manifest = package_dir / "package_manifest.json"
    try:
        value = _json(manifest)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeError) as exc:
        raise BaselineError("Paketmanifest für den Testspielstand nicht lesbar: " + str(exc)) from exc
    if "baseline" not in value:
        return None  # Compatibility with the older private, complete bundles.
    meta = value["baseline"]
    if not isinstance(meta, dict):
        raise BaselineError("Das Paketmanifest enthält keine gültige Testspielstand-Identität.")
    fields = {}
    for key in ("sav_sha256", "sav_lua_sha256"):
        digest = meta.get(key)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise BaselineError("Ungültige SHA-256-Prüfsumme im Paketmanifest: " + key)
        fields[key] = digest.lower()
    for key, limit in (("sav_bytes", MAX_SAVE_BYTES), ("sav_lua_bytes", MAX_LUA_BYTES)):
        size = meta.get(key)
        if size is not None and (type(size) is not int or not 0 < size <= limit):
            raise BaselineError("Ungültige Dateigröße im Paketmanifest: " + key)
        fields[key] = size
    return _Identity(**fields)


def _digest(path, limit):
    digest, count = hashlib.sha256(), 0
    with _open_regular(path, limit) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            count += len(chunk)
            if count > limit:
                raise BaselineError("Testspielstand-Datei ist während des Lesens zu groß geworden.")
            digest.update(chunk)
    if count == 0:
        raise BaselineError("Leere Testspielstand-Datei: " + str(path))
    return digest.hexdigest(), count


def _pair_matches(save, identity):
    try:
        digest, size = _digest(save, MAX_SAVE_BYTES)
        lua_digest, lua_size = _digest(Path(str(save) + ".lua"), MAX_LUA_BYTES)
        return identity is None or (
            digest == identity.sav_sha256 and lua_digest == identity.sav_lua_sha256
            and (identity.sav_bytes is None or size == identity.sav_bytes)
            and (identity.sav_lua_bytes is None or lua_size == identity.sav_lua_bytes))
    except (OSError, BaselineError):
        return False


def _previous_save(state_root):
    """Follow only our one recorded run, confined to local launcher state."""
    try:
        settings = _json(state_root / "launcher.json")
        previous = settings.get("last_run")
        if not isinstance(previous, str) or not previous or not Path(previous).is_absolute():
            return None
        run = _plain_path(previous)
        if not _inside(run, state_root):
            return None
        record = _json(run / "run.json")
        output = record.get("output")
        if not isinstance(output, str) or not output or not Path(output).is_absolute():
            return None
        payload = _plain_path(output)
        if not _inside(payload, run):
            return None
        return payload / "save/initial.sav"
    except (OSError, ValueError, UnicodeError):
        return None


def _copy_file(source, target, expected_hash, expected_size, limit):
    digest, count = hashlib.sha256(), 0
    with _open_regular(source, limit) as src, target.open("xb") as dst:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            count += len(chunk)
            if count > limit:
                raise BaselineError("Testspielstand-Datei ist während des Kopierens zu groß geworden.")
            digest.update(chunk)
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    if digest.hexdigest() != expected_hash or (expected_size is not None and count != expected_size):
        raise BaselineError("Der Testspielstand wurde während des Kopierens verändert.")


def _cleanup_temp(directory, cache_root):
    # Only our two known temporary files; no recursive delete or traversal.
    try:
        directory = _plain_path(directory)
        if directory.parent != cache_root:
            return
        for name in ("initial.sav", "initial.sav.lua"):
            _plain_path(directory / name).unlink(missing_ok=True)
        directory.rmdir()
    except (OSError, BaselineError):
        pass  # Preserve an unexpected entry rather than deleting unknown data.


def _publish(save, cache_root, destination, identity):
    temp = Path(tempfile.mkdtemp(prefix=".import-", dir=cache_root))
    try:
        _plain_path(temp)
        _copy_file(save, temp / "initial.sav", identity.sav_sha256,
                   identity.sav_bytes, MAX_SAVE_BYTES)
        _copy_file(Path(str(save) + ".lua"), temp / "initial.sav.lua", identity.sav_lua_sha256,
                   identity.sav_lua_bytes, MAX_LUA_BYTES)
        if not _pair_matches(temp / "initial.sav", identity):
            raise BaselineError("Die kopierte Testspielstand-Datei hat die Prüfung nicht bestanden.")
        _plain_path(cache_root)
        _plain_path(destination)
        if destination.exists():
            if _pair_matches(destination / "initial.sav", identity):
                return destination / "initial.sav"
            preserved = cache_root / ("rejected-" + identity.cache_key + "-" + uuid.uuid4().hex)
            if destination.parent != cache_root or preserved.parent != cache_root:
                raise BaselineError("Ungültiger lokaler Testspielstand-Speicher.")
            # Preserve a damaged cache directory instead of overwriting its files.
            try:
                destination.rename(preserved)
            except FileNotFoundError:
                pass  # A concurrent resolver may already have moved it.
        try:
            temp.rename(destination)  # Publish both fully verified files together.
        except OSError:
            if not _pair_matches(destination / "initial.sav", identity):
                raise
        return destination / "initial.sav"
    finally:
        _cleanup_temp(temp, cache_root)


def resolve_baseline(package_dir: Path, state_root: Path,
                     selected_save: Path | None = None) -> Path:
    """Find and verify this release's private baseline, caching a fresh local pair.

    New public releases specify ``baseline.sav_sha256`` and
    ``baseline.sav_lua_sha256`` in ``package_manifest.json``. Optional ``sav_bytes``
    and ``sav_lua_bytes`` constrain sizes too. No source outside the documented
    locations is searched, and a different save is never silently accepted.
    """
    try:
        package_dir, state_root = _plain_path(package_dir), _plain_path(state_root)
        identity = _identity(package_dir)
        bundled = package_dir / "Testspielstand/initial.sav"
        if identity is None:
            if _pair_matches(bundled, None):
                return bundled
            raise BaselineError("Dem alten Paket fehlt sein vollständiger Testspielstand. " + _GUIDANCE)
        cache_root = _plain_path(state_root / "baseline")
        destination = _plain_path(cache_root / identity.cache_key)
        cached = destination / "initial.sav"
        if _pair_matches(cached, identity):
            return cached
        previous = _previous_save(state_root)
        candidates = [bundled, previous, selected_save]
        for candidate in candidates:
            if candidate is None:
                continue
            candidate = _absolute(candidate)
            if not _pair_matches(candidate, identity):
                continue
            cache_root.mkdir(parents=True, exist_ok=True)
            _plain_path(cache_root)
            return _publish(candidate, cache_root, destination, identity)
        raise BaselineError("Der passende private Testspielstand wurde lokal nicht gefunden "
                            "oder seine Prüfsummen stimmen nicht mit diesem Paket überein. " + _GUIDANCE)
    except BaselineError:
        raise
    except (OSError, ValueError) as exc:
        raise BaselineError("Der lokale Testspielstand konnte nicht vorbereitet werden: " + str(exc)) from exc
