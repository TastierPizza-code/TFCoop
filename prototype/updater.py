"""Verified, startup-only GitHub release downloads. Never starts an app or a game.

Release folders are immutable. A completed, verified folder is published through
an atomic pointer; a failed download leaves the previous usable release intact.
The public GitHub repository and HTTPS are the publisher trust boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zipfile


REPOSITORY = "TastierPizza-code/TFCoop"
ASSET_NAME = "TFCoop-Windows.zip"
EXECUTABLE = "TF2-Coop.exe"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_UNPACKED = 512 * 1024 * 1024
MAX_FILES = 5000
MAX_JSON = 2 * 1024 * 1024
TAG = re.compile(r"v(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LOCK = threading.Lock()
_DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
_PRIVATE_NAMES = {
    "transportfever2.exe", "alut_real.dll", "session.key", "launch.cfg", "launcher.json", "test-pairing.json",
    "run.json", "probe_setup.json", "probe_epoch.txt", "native_status.txt", "lua_status.json",
    "loader_status.txt", "credentials", ".env", ".git", ".svn", "testspielstand",
    "userdata", "crash_dump", "runtime", "staged", "results", "reports", "logs",
}


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateResult:
    executable: Path | None
    message: str
    version: str | None = None


def _version(value):
    if not isinstance(value, str) or not (match := TAG.fullmatch(value)):
        raise UpdateError("Ungültige Versionsnummer im Update.")
    return tuple(map(int, match.groups()))


def _json(raw):
    if len(raw) > MAX_JSON:
        raise UpdateError("Updatebeschreibung ist zu groß.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise UpdateError("Doppelte Felder in der Updatebeschreibung.")
            result[key] = value
        return result
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("Updatebeschreibung ist beschädigt.") from exc
    if type(result) is not dict:
        raise UpdateError("Updatebeschreibung muss ein Objekt sein.")
    return result


def _parts(value):
    if (not isinstance(value, str) or not value or len(value) > 240
            or value.startswith("/") or "\\" in value or any(ord(c) < 32 for c in value)
            or any(c in value for c in ':<>"|?*')):
        raise UpdateError("Unsicherer Dateipfad im Update.")
    parts = value.split("/")
    for part in parts:
        stem = part.split(".", 1)[0].upper()
        if (part in ("", ".", "..") or part.rstrip(" .") != part
                or stem in {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"}
                or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem)):
            raise UpdateError("Ungültiger Windows-Dateiname im Update.")
    return parts


def _public_file(value):
    parts = _parts(value)
    name = parts[-1].lower()
    if (any(part.lower() in _PRIVATE_NAMES for part in parts)
            or name.startswith(".env.")
            or name.endswith((".sav", ".sav.lua", ".dmp", ".log", ".key", ".pfx", ".p12", ".ppk", ".pem"))):
        raise UpdateError("Das öffentliche Update enthält eine private oder fremde Spieldatei.")
    return parts


def _ordinary(path, *, directory=False):
    try:
        info = path.lstat()
    except OSError as exc:
        raise UpdateError("Eine Update-Datei fehlt oder ist nicht lesbar.") from exc
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))):
        raise UpdateError("Verknüpfungen sind im Updateordner nicht erlaubt.")


def _canonical_directory(path, *, create=False):
    path = Path(path).absolute()
    # Inspect existing parents before creating descendants through a junction.
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            _ordinary(parent, directory=True)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    _ordinary(path, directory=True)
    if os.path.normcase(str(path.resolve())) != os.path.normcase(str(path)):
        raise UpdateError("Der Updateordner enthält eine Pfadumleitung.")
    return path


def _read_document(path):
    _ordinary(path)
    with path.open("rb") as source:
        return _json(source.read(MAX_JSON + 1))


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(root, *, expected_tag=None, complete=True):
    root = _canonical_directory(root)
    manifest = _read_document(root / "package_manifest.json")
    tag = manifest.get("release_tag")
    _version(tag)
    if expected_tag is not None and tag != expected_tag:
        raise UpdateError("Paket und veröffentlichte Version stimmen nicht überein.")
    files = manifest.get("files")
    if type(files) is not dict or not 1 <= len(files) <= MAX_FILES or EXECUTABLE not in files:
        raise UpdateError("Das Update enthält keinen vollständigen Launcher.")
    seen = set()
    for relative, expected in files.items():
        parts = _public_file(relative)
        folded = relative.casefold()
        if (folded in seen or folded == "package_manifest.json" or not isinstance(expected, str)
                or not SHA256.fullmatch(expected)):
            raise UpdateError("Die Dateiliste des Updates ist ungültig.")
        seen.add(folded)
        if complete:
            target = root.joinpath(*parts)
            for parent in target.parents:
                if parent == root:
                    break
                _ordinary(parent, directory=True)
            _ordinary(target)
            if _hash(target) != expected:
                raise UpdateError("Prüfsumme einer Update-Datei stimmt nicht.")
    if complete:
        actual = set()
        total = 0
        for directory, folders, names in os.walk(root, followlinks=False):
            for name in folders:
                _ordinary(Path(directory) / name, directory=True)
            for name in names:
                target = Path(directory) / name
                _ordinary(target)
                relative = target.relative_to(root).as_posix()
                if relative == "package_manifest.json":
                    continue
                _public_file(relative)
                total += target.stat().st_size
                actual.add(relative)
                if len(actual) > MAX_FILES or total > MAX_UNPACKED:
                    raise UpdateError("Der entpackte Launcher überschreitet das Größenlimit.")
        if actual != set(files):
            raise UpdateError("Das Update enthält fehlende oder zusätzliche Dateien.")
    return manifest


def _safe_url(url, *, api=False):
    try:
        parsed = urlsplit(url)
        allowed = {"api.github.com"} if api else _DOWNLOAD_HOSTS
        if (parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username
                or parsed.password or parsed.port not in (None, 443) or parsed.fragment):
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise UpdateError("Unerlaubte Downloadadresse.") from exc
    return parsed


class _Redirects(HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _safe_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _open(url, *, api=False):
    _safe_url(url, api=api)
    request = Request(url, headers={"User-Agent": "TFCoop-Updater/1.0",
                                   "Accept": "application/vnd.github+json" if api else "application/octet-stream"})
    return build_opener(_Redirects()).open(request, timeout=15)


def _latest():
    with _open(API_URL, api=True) as response:
        release = _json(response.read(MAX_JSON + 1))
    tag = release.get("tag_name")
    _version(tag)
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise UpdateError("GitHub hat keine freigegebene Launcher-Version geliefert.")
    assets = release.get("assets")
    if type(assets) is not list or len(assets) > 100:
        raise UpdateError("Ungültige GitHub-Dateiliste.")
    matches = [asset for asset in assets if type(asset) is dict and asset.get("name") == ASSET_NAME]
    if len(matches) != 1:
        raise UpdateError("Die veröffentlichte Windows-Datei fehlt oder ist mehrdeutig.")
    asset = matches[0]
    size, digest, url = asset.get("size"), asset.get("digest"), asset.get("browser_download_url")
    if type(size) is not int or not 1 <= size <= MAX_ARCHIVE:
        raise UpdateError("Die Downloadgröße ist ungültig.")
    if not isinstance(digest, str) or not digest.startswith("sha256:") or not SHA256.fullmatch(digest[7:]):
        raise UpdateError("GitHub hat keine gültige SHA-256-Prüfsumme geliefert.")
    if url != f"https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET_NAME}":
        raise UpdateError("Das Update stammt nicht aus dem festgelegten Repository.")
    _safe_url(url)
    return tag, size, digest[7:], url


def _download(url, target, size, expected, progress):
    digest, received = hashlib.sha256(), 0
    deadline = time.monotonic() + 300
    with _open(url) as response, target.open("xb") as output:
        declared = response.headers.get("Content-Length")
        if declared is not None and (not declared.isdecimal() or int(declared) != size):
            raise UpdateError("GitHub-Downloadgröße stimmt nicht mit der Veröffentlichung überein.")
        while True:
            if time.monotonic() > deadline:
                raise UpdateError("Der Update-Download hat zu lange gedauert.")
            chunk = response.read(min(1024 * 1024, size - received + 1))
            if not chunk:
                break
            received += len(chunk)
            if received > size or received > MAX_ARCHIVE:
                raise UpdateError("Der Download überschreitet die angekündigte Größe.")
            output.write(chunk)
            digest.update(chunk)
            progress(f"Update wird geladen: {received // 1024 // 1024} / {(size + 1048575) // 1048576} MB")
        output.flush()
        os.fsync(output.fileno())
    if received != size or digest.hexdigest() != expected:
        raise UpdateError("Der Download ist unvollständig oder seine Prüfsumme stimmt nicht.")


def _extract(archive, destination, tag):
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if not 1 <= len(entries) <= MAX_FILES * 2:
            raise UpdateError("Zu viele Dateien im Updatearchiv.")
        paths, names, prefixes, total = [], set(), {}, 0
        for entry in entries:
            relative = entry.filename[:-1] if entry.is_dir() else entry.filename
            parts = _parts(relative)
            folded = relative.casefold()
            mode = (entry.external_attr >> 16) & 0xFFFF
            kind = stat.S_IFMT(mode)
            if (folded in names or entry.flag_bits & 1 or entry.compress_type not in (0, 8)
                    or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or (kind == stat.S_IFDIR and not entry.is_dir())
                    or (kind == stat.S_IFREG and entry.is_dir())
                    or (entry.external_attr & 0x400)):
                raise UpdateError("Doppelte, verknüpfte oder unerlaubte ZIP-Datei.")
            names.add(folded)
            for length in range(1, len(parts) + 1):
                spelling = "/".join(parts[:length])
                old = prefixes.setdefault(spelling.casefold(), spelling)
                if old != spelling:
                    raise UpdateError("Mehrdeutige Groß-/Kleinschreibung im Updatearchiv.")
            if not entry.is_dir():
                total += entry.file_size
                if total > MAX_UNPACKED or entry.file_size > MAX_UNPACKED:
                    raise UpdateError("Das Updatearchiv überschreitet das entpackte Größenlimit.")
            paths.append((entry, parts))
        # Accept flat public packages or the existing portable single-root layout.
        manifests = [parts for entry, parts in paths if not entry.is_dir() and parts[-1] == "package_manifest.json"]
        if len(manifests) != 1 or len(manifests[0]) not in (1, 2):
            raise UpdateError("Die Paketbeschreibung fehlt oder liegt im falschen Ordner.")
        prefix = manifests[0][:-1]
        destination.mkdir(exist_ok=False)
        written = 0
        for entry, parts in paths:
            if parts[:len(prefix)] != prefix:
                raise UpdateError("Dateien außerhalb des Launcher-Paketordners.")
            stripped = parts[len(prefix):]
            if not stripped:
                if entry.is_dir():
                    continue
                raise UpdateError("Ungültiger Paketordner.")
            relative = "/".join(stripped)
            if relative != "package_manifest.json":
                _public_file(relative)
            target = destination.joinpath(*stripped)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            written += 1
            if written > MAX_FILES + 1:
                raise UpdateError("Zu viele Dateien im Updatearchiv.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as incoming, target.open("xb") as outgoing:
                copied = 0
                while True:
                    chunk = incoming.read(1024 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > entry.file_size:
                        raise UpdateError("ZIP-Dateigröße stimmt nicht.")
                    outgoing.write(chunk)
                if copied != entry.file_size:
                    raise UpdateError("Unvollständige ZIP-Datei.")
                outgoing.flush()
                os.fsync(outgoing.fileno())
    return _manifest(destination, expected_tag=tag)


def _write_pointer(root, pointer):
    temporary = root / ("current-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as output:
            output.write((json.dumps(pointer, sort_keys=True) + "\n").encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        target = root / "current.json"
        if target.exists() or target.is_symlink():
            _ordinary(target)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _quarantine(folder, versions):
    """Preserve one damaged ordinary cache folder without following any links."""
    versions = _canonical_directory(versions)
    folder = _canonical_directory(folder)
    if folder.parent != versions:
        raise UpdateError("Der beschädigte Versionsordner liegt außerhalb des Updatecaches.")
    checked = 0
    for directory, folders, names in os.walk(folder, followlinks=False):
        for name in folders:
            _ordinary(Path(directory) / name, directory=True)
            checked += 1
        for name in names:
            _ordinary(Path(directory) / name)
            checked += 1
        if checked > MAX_FILES * 2:
            raise UpdateError("Der beschädigte Versionsordner enthält zu viele Einträge.")
    preserved = versions / ("quarantine-" + uuid.uuid4().hex)
    # Both resolved paths are checked before the single directory rename. No
    # recursive copy/delete and no game, save or external path is involved.
    _canonical_directory(folder)
    if preserved.parent.resolve() != versions or preserved.exists() or preserved.is_symlink():
        raise UpdateError("Ungültiger Quarantäneordner für das beschädigte Update.")
    folder.rename(preserved)
    return preserved


def _cached(root, current_tag):
    pointer_path = root / "current.json"
    if not pointer_path.exists():
        return None
    pointer = _read_document(pointer_path)
    if set(pointer) != {"format", "release_tag", "directory", "archive_sha256", "manifest_sha256"} or pointer["format"] != 1:
        raise UpdateError("Der gespeicherte Updateverweis ist ungültig.")
    tag, archive_hash, manifest_hash = (pointer[key] for key in ("release_tag", "archive_sha256", "manifest_sha256"))
    if (_version(tag) < _version(current_tag) or not isinstance(archive_hash, str)
            or not SHA256.fullmatch(archive_hash) or not isinstance(manifest_hash, str) or not SHA256.fullmatch(manifest_hash)):
        return None
    name = f"{tag}-{archive_hash[:16]}"
    if pointer["directory"] != name:
        raise UpdateError("Der gespeicherte Versionsordner ist ungültig.")
    folder = _canonical_directory(root / "versions" / name)
    _ordinary(folder / "package_manifest.json")
    if _hash(folder / "package_manifest.json") != manifest_hash:
        raise UpdateError("Die gespeicherte Paketbeschreibung wurde verändert.")
    _manifest(folder, expected_tag=tag)
    return tag, folder / EXECUTABLE


def _runtime_active():
    from coop.native import game_is_running
    if game_is_running():
        return True
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenMutexW(0x00100000, False, "Local\\TF2StrictProbeController")
    if handle:
        kernel.CloseHandle(handle)
        return True
    if ctypes.get_last_error() != 2:
        raise UpdateError("Der laufende Messcontroller konnte nicht sicher geprüft werden.")
    return False


@contextmanager
def _update_lock():
    if not _LOCK.acquire(blocking=False):
        raise UpdateError("Ein anderer Launcher prüft gerade Updates.")
    handle, kernel = None, None
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.CreateMutexW(None, False, "Local\\TFCoopUpdater")
            if not handle or ctypes.get_last_error() == 183:
                raise UpdateError("Ein anderer Launcher prüft gerade Updates.")
        yield
    finally:
        if handle:
            kernel.CloseHandle(handle)
        _LOCK.release()


def check_for_update(current_directory: Path, cache_root: Path, progress=lambda message: None,
                     active_check=lambda: False) -> UpdateResult:
    """Return a verified executable to hand off to, or keep the current launcher.

Callbacks run on the caller's thread. All failures produce a readable result;
neither this function nor its failure handling starts a process or changes TF2.
"""
    current_tag, fallback, cache, temporary, staging = None, None, None, None, None
    try:
        with _update_lock():
            if active_check() or _runtime_active():
                return UpdateResult(None, "Update verschoben: TF2 oder ein Messcontroller läuft noch.")
            current = _canonical_directory(current_directory)
            current_manifest = _read_document(current / "package_manifest.json")
            current_tag = current_manifest.get("release_tag")
            _version(current_tag)
            cache = _canonical_directory(cache_root, create=True)
            cache_warning = ""
            try:
                fallback = _cached(cache, current_tag)
            except (OSError, ValueError, UpdateError) as exc:
                cache_warning = str(exc)
            selected_tag = fallback[0] if fallback else current_tag
            progress("Neueste Launcher-Version wird bei GitHub geprüft …")
            tag, size, digest, url = _latest()
            if _version(tag) <= _version(selected_tag):
                if active_check() or _runtime_active():
                    return UpdateResult(None, "Update verschoben: TF2 oder ein Messcontroller läuft noch.", current_tag)
                executable = fallback[1] if fallback and fallback[1].parent != current else None
                return UpdateResult(executable, f"Launcher {selected_tag} ist aktuell." +
                                    (f" Gespeichertes Update wurde verworfen: {cache_warning}" if cache_warning else ""), selected_tag)
            versions = _canonical_directory(cache / "versions", create=True)
            name = f"{tag}-{digest[:16]}"
            destination = versions / name
            temporary = cache / ("download-" + uuid.uuid4().hex + ".zip.part")
            staging = versions / ("pending-" + uuid.uuid4().hex)
            _download(url, temporary, size, digest, progress)
            progress("Download vollständig. Launcher-Dateien werden geprüft …")
            _extract(temporary, staging, tag)
            if active_check() or _runtime_active():
                return UpdateResult(None, "Update verschoben: TF2 oder ein Messcontroller wurde gestartet.", current_tag)
            if destination.exists() or destination.is_symlink():
                # An unreferenced directory name is not proof that its contents
                # came from GitHub. Compare it with the newly verified archive.
                _canonical_directory(destination)  # Reparse/non-directory: never move it.
                try:
                    _manifest(destination, expected_tag=tag)
                    if _hash(destination / "package_manifest.json") != _hash(staging / "package_manifest.json"):
                        raise UpdateError("Der vorhandene Versionsordner gehört nicht zu diesem Download.")
                except (OSError, ValueError, UpdateError):
                    _quarantine(destination, versions)
                    staging.rename(destination)
                    staging = None
            else:
                staging.rename(destination)
                staging = None
            if active_check() or _runtime_active():
                return UpdateResult(None, "Update verschoben: TF2 oder ein Messcontroller läuft noch.", current_tag)
            pointer = {"format": 1, "release_tag": tag, "directory": name, "archive_sha256": digest,
                       "manifest_sha256": _hash(destination / "package_manifest.json")}
            _write_pointer(cache, pointer)
            return UpdateResult(destination / EXECUTABLE, f"Launcher {tag} wurde vollständig geladen und geprüft.", tag)
    except Exception as exc:
        # A failed fetch must not strand a working offline installation. Recheck
        # activity because the user may have started a game during the request.
        reason = str(exc)[:250] or type(exc).__name__
        try:
            if active_check() or _runtime_active():
                return UpdateResult(None, "Update verschoben: TF2 oder ein Messcontroller läuft noch.", current_tag)
        except Exception:
            return UpdateResult(None, "Update verschoben: laufende Programme konnten nicht sicher geprüft werden.", current_tag)
        if fallback:
            current = Path(current_directory).absolute()
            executable = fallback[1] if fallback[1].parent != current else None
            return UpdateResult(executable, f"Update nicht erreichbar: {reason} Verwende die geprüfte Version {fallback[0]}.", fallback[0])
        return UpdateResult(None, f"Update nicht verfügbar: {reason} Die vorhandene Version bleibt erhalten.", current_tag)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        # Incomplete staging stays unreferenced for inspection. Never recursively
        # delete paths reached through untrusted ZIP names or an external link.
