"""Local, reversible preparation of the solo read-only Lua API audit.

Only an explicit caller action prepares files. There is no network, game launch,
native gate, simulation command or modification of the normal launcher last_run.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile
import uuid

from coop.install import _lua_string
from prototype import baseline
from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync import probe_install as recovery
from prototype.strict_sync.engine_mailbox import _shared_read


MOD = "tf2_api_audit_1"
CONFIG = "res/scripts/tf2_api_audit/config.lua"
REQUIRED_FILES = {
    "mod.lua", CONFIG, "res/config/game_script/tf2_api_audit.lua",
    "res/scripts/tf2_api_audit/probe.lua", "res/scripts/tf2_api_audit/json.lua",
}
STATE_DIR = ".tf2-api-audit-install"
OWNER = "tf2-read-only-api-audit-installer"
MODE = "read_only_api_audit"
MAX_REPORT_BYTES = 98304
MAX_METADATA_BYTES = 1024 * 1024
MAX_MOD_FILE_BYTES = 1024 * 1024
ID = re.compile(r"[0-9a-f]{32}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
STATES = {"backed_up", "installing", "installed", "restoring", "restored", "install_failed"}


class DiagnosticError(ValueError):
    """Diagnostic preparation, recovery or report validation failed safely."""


@dataclass(frozen=True)
class DiagnosticRun:
    request_id: str
    run_dir: str
    game_dir: str
    save_dir: str
    imported_save: str
    report_path: str
    backup_path: str
    mod_dir: str

    @property
    def directory(self):
        return Path(self.run_dir)


def _plain(path):
    return baseline._plain_path(path)


def _directory(path):
    path = _plain(path)
    if not path.is_dir():
        raise DiagnosticError("Ordner fehlt für die API-Diagnose: " + str(path))
    return path


def _path(root, relative):
    if (type(relative) is not str or not relative or "\\" in relative or ":" in relative
            or "\0" in relative or str(PurePosixPath(relative)) != relative
            or PurePosixPath(relative).is_absolute()
            or any(p in (".", "..") or p.rstrip(" .") != p for p in relative.split("/"))):
        raise DiagnosticError("Ungültiger Diagnose-Dateipfad.")
    path = _plain(root.joinpath(*relative.split("/")))
    if not path.is_relative_to(root) or path == root:
        raise DiagnosticError("Diagnose-Dateipfad liegt außerhalb des vorgesehenen Ordners.")
    return path


def _json_bytes(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DiagnosticError("Doppelte Felder in Diagnose-JSON.")
            result[key] = value
        return result

    def invalid_constant(value):
        raise DiagnosticError("Nicht endlicher JSON-Wert im Diagnosebericht: " + value)

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            return invalid_constant(value)
        return number

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                            parse_constant=invalid_constant, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise DiagnosticError("Ungültige Diagnose-JSON: " + str(exc)) from exc
    if type(result) is not dict:
        raise DiagnosticError("Diagnose-JSON muss ein Objekt enthalten.")
    return result


def _read_json(path, limit=MAX_METADATA_BYTES):
    path = _plain(path)
    with baseline._open_regular(path, limit) as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise DiagnosticError("Diagnosedatei überschreitet ihr Größenlimit.")
    return _json_bytes(raw)


def _hash(path, limit=MAX_MOD_FILE_BYTES):
    path = _plain(path)
    if not path.exists():
        return None
    digest, count = hashlib.sha256(), 0
    with baseline._open_regular(path, limit) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            count += len(chunk)
            if count > limit:
                raise DiagnosticError("Diagnosedatei wurde während des Lesens zu groß.")
            digest.update(chunk)
    return digest.hexdigest()  # Existing empty files must also be preserved exactly.


def _owned_file(relative):
    return relative.startswith(f"mods/{MOD}/") and relative.removeprefix(f"mods/{MOD}/") in REQUIRED_FILES


def _journal(game):
    state = _path(game, STATE_DIR)
    pointer = _path(state, "current.json")
    if not pointer.exists():
        return None
    current = _read_json(pointer)
    if (set(current) != {"owner", "request_id"} or current["owner"] != OWNER
            or type(current["request_id"]) is not str or not ID.fullmatch(current["request_id"])):
        raise DiagnosticError("Unbekannte Eigentümerschaft der Diagnoseinstallation.")
    request_id = current["request_id"]
    backup = _path(state, "runs/" + request_id)
    journal = _read_json(_path(backup, "journal.json"))
    if (journal.get("owner") != OWNER or type(journal.get("format")) is not int
            or journal["format"] != 1 or journal.get("request_id") != request_id
            or journal.get("game_dir") != str(game) or type(journal.get("state")) is not str
            or journal["state"] not in STATES
            or type(journal.get("files")) is not list or len(journal["files"]) != len(REQUIRED_FILES)
            or type(journal.get("created_dirs")) is not list or len(journal["created_dirs"]) > 64):
        raise DiagnosticError("Ungültiges Wiederherstellungsjournal der Diagnose.")
    seen = set()
    for entry in journal["files"]:
        if type(entry) is not dict or set(entry) != {"path", "original_sha256", "deployed_sha256"}:
            raise DiagnosticError("Ungültiger Diagnose-Sicherungsdatensatz.")
        relative = entry["path"]
        _path(game, relative)
        if (relative in seen or not _owned_file(relative)
                or type(entry["deployed_sha256"]) is not str
                or not SHA.fullmatch(entry["deployed_sha256"])
                or entry["original_sha256"] is not None and (
                    type(entry["original_sha256"]) is not str or not SHA.fullmatch(entry["original_sha256"]))):
            raise DiagnosticError("Diagnose-Sicherung enthält einen unerlaubten Dateipfad oder Hash.")
        seen.add(relative)
    for relative in journal["created_dirs"]:
        _path(game, relative)
        if relative not in ("mods", f"mods/{MOD}") and not relative.startswith(f"mods/{MOD}/"):
            raise DiagnosticError("Ungültiger Diagnose-Wiederherstellungsordner.")
    return backup, journal


def _conflicts(game, backup, journal):
    result = []
    for entry in journal["files"]:
        relative = entry["path"]
        if (entry["original_sha256"] is not None
                and _hash(_path(backup, "original/" + relative)) != entry["original_sha256"]):
            result.append("Backup beschädigt: " + relative)
        acceptable = {entry["deployed_sha256"]}
        if journal["state"] != "installed":
            acceptable.add(entry["original_sha256"])
        if _hash(_path(game, relative)) not in acceptable:
            result.append("Datei nachträglich verändert: " + relative)
    return result


def diagnostic_status(game_dir: Path) -> dict:
    """Read-only status, compatible with the strict installer's status fields."""
    try:
        game = _directory(game_dir)
        found = _journal(game)
        if found is None:
            return {"installed": False, "state": "absent", "restorable": False, "conflicts": []}
        backup, journal = found
        restored = journal["state"] == "restored"
        conflicts = [] if restored else _conflicts(game, backup, journal)
        return {"installed": not restored, "state": journal["state"],
                "restorable": not restored and not conflicts, "conflicts": conflicts,
                "request_id": journal["request_id"], "backup_path": str(backup),
                "imported_save": journal.get("imported_save", "")}
    except (OSError, baseline.BaselineError, recovery.ProbeInstallError) as exc:
        raise DiagnosticError(str(exc)) from exc


def _restore(game, backup, journal):
    recovery._require_closed()
    conflicts = _conflicts(game, backup, journal)
    if conflicts:
        raise DiagnosticError("Diagnose-Wiederherstellung blockiert: " + "; ".join(conflicts))
    journal["state"] = "restoring"
    recovery._write_json(backup / "journal.json", journal)
    for entry in reversed(journal["files"]):
        recovery._require_closed()
        target = _path(game, entry["path"])
        current = _hash(target)
        if current == entry["original_sha256"]:
            continue
        if current != entry["deployed_sha256"]:
            raise DiagnosticError("Diagnosedatei wurde während der Wiederherstellung verändert.")
        if entry["original_sha256"] is None:
            target.unlink()
        else:
            recovery._replace(_path(backup, "original/" + entry["path"]), target,
                              entry["original_sha256"], current)
    for relative in sorted(journal["created_dirs"], key=lambda p: len(PurePosixPath(p).parts), reverse=True):
        try:
            _path(game, relative).rmdir()  # Empty directories only; preserve all added files.
        except OSError:
            pass
    journal["state"] = "restored"
    recovery._write_json(backup / "journal.json", journal)
    return {"restored": True, "backup_path": str(backup), "imported_save": journal.get("imported_save", "")}


def restore_diagnostic(game_dir: Path) -> dict:
    """Restore only our recorded mod files; preserve saves, reports and history."""
    try:
        with recovery._guard():
            game = _directory(game_dir)
            found = _journal(game)
            if found is None:
                return {"restored": False, "state": "absent"}
            backup, journal = found
            if journal["state"] == "restored":
                return {"restored": True, "state": "restored", "backup_path": str(backup)}
            return _restore(game, backup, journal)
    except (OSError, baseline.BaselineError, recovery.ProbeInstallError) as exc:
        raise DiagnosticError(str(exc)) from exc


def _validate_run(run):
    if not isinstance(run, DiagnosticRun) or not ID.fullmatch(str(run.request_id)):
        raise DiagnosticError("Ungültiger Diagnoselauf.")
    values = asdict(run)
    if any(type(value) is not str for value in values.values()):
        raise DiagnosticError("Ungültige Diagnosepfade.")
    local = _plain(workflow.local_root())
    directory = _plain(run.run_dir)
    game, saves = _plain(run.game_dir), _plain(run.save_dir)
    expected = {
        "run_dir": local / "diagnostics" / run.request_id,
        "imported_save": saves / ("TF2-API-Diagnose-" + run.request_id + ".sav"),
        "report_path": directory / "report.json",
        "backup_path": game / STATE_DIR / "runs" / run.request_id,
        "mod_dir": game / "mods" / MOD,
    }
    for key, path in expected.items():
        if Path(values[key]) != path or _plain(values[key]) != path:
            raise DiagnosticError("Diagnoselauf enthält einen fremden oder umgeleiteten Pfad: " + key)
    return run


def load_diagnostic(path: Path) -> DiagnosticRun:
    """Load one recorded diagnostic without touching normal last_run settings."""
    try:
        path = _plain(path)
        record_path = path / "run.json" if path.is_dir() else path
        record = _read_json(record_path)
        if (set(record) != {"owner", "format", "run"} or record["owner"] != OWNER
                or type(record["format"]) is not int or record["format"] != 1
                or type(record["run"]) is not dict):
            raise DiagnosticError("Ungültige Metadaten des Diagnoselaufs.")
        run = _validate_run(DiagnosticRun(**record["run"]))
        if record_path != Path(run.run_dir) / "run.json":
            raise DiagnosticError("Diagnosemetadaten gehören zu einem anderen Ordner.")
        return run
    except (OSError, TypeError, baseline.BaselineError) as exc:
        raise DiagnosticError(str(exc)) from exc


def _validate_existing_mod(game):
    target = _path(game, f"mods/{MOD}")
    if not target.exists():
        return
    if not target.is_dir():
        raise DiagnosticError("Der vorhandene Diagnose-Modpfad ist kein Ordner.")
    for path in target.rglob("*"):
        path = _plain(path)
        if path.is_file() and path.relative_to(target).as_posix() not in REQUIRED_FILES:
            raise DiagnosticError("Der Diagnosemodordner enthält fremde Dateien. Ordner zuerst separat sichern: " + str(path))
        if not path.is_file() and not path.is_dir():
            raise DiagnosticError("Unbekannter Dateityp im Diagnosemodordner.")


def _require_normal_start(game):
    """No valid launch ticket; reject an orphaned copy of our strict proxy.

    restore_probe may restore the earlier Alpha audio proxy rather than stock
    audio. That proxy enables hooks only for an explicit child session or valid
    live launch ticket. This workflow creates neither and only asks for normal
    Steam launch. It never deletes or replaces an unknown native installation.
    """
    recovery._require_closed()
    strict_proxy = _plain(workflow.resources() / "prototype/native/out/probe_alut.dll")
    if strict_proxy.is_file():
        expected = _hash(strict_proxy, 16 * 1024 * 1024)
        if _hash(_path(game, "alut.dll"), 16 * 1024 * 1024) == expected:
            raise DiagnosticError("Der native Strict-Test-Proxy ist noch installiert. Bitte seine bisherige Installation wiederherstellen; keine DLL von Hand ersetzen.")


def prepare_diagnostic(game_dir: Path, save_dir: Path, on_progress=None) -> DiagnosticRun:
    """Prepare one fresh local save and reversible Lua-only mod after a UI click."""
    def progress(message):
        if on_progress is not None:
            on_progress(message)

    try:
        recovery._require_closed()
        game, saves = _directory(game_dir), _directory(save_dir)
        local = _plain(workflow.local_root())
        source = _directory(workflow.resources() / "prototype/mod" / MOD)
        if (not _path(game, "TransportFever2.exe").is_file() or not _path(game, "res").is_dir()):
            raise DiagnosticError("Transport Fever 2 wurde im gewählten Ordner nicht gefunden.")
        if (game == saves or game in saves.parents or saves in game.parents
                or local == game or local in game.parents or game in local.parents
                or local == saves or local in saves.parents or saves in local.parents):
            raise DiagnosticError("Spiel, Saveordner und lokaler Diagnoseordner müssen getrennt sein.")
        if diagnostic_status(game)["installed"]:
            raise DiagnosticError("Eine Diagnose ist bereits installiert. Zuerst bisherige Installation wiederherstellen.")
        _validate_existing_mod(game)
        files = {name: baseline._digest(_path(source, name), MAX_MOD_FILE_BYTES)[0]
                 for name in sorted(REQUIRED_FILES)}
        original = _plain(workflow.baseline_save())
        original_lua = _plain(Path(str(original) + ".lua"))
        sav_hash, sav_size = baseline._digest(original, baseline.MAX_SAVE_BYTES)
        lua_hash, lua_size = baseline._digest(original_lua, baseline.MAX_LUA_BYTES)
        progress("Vorherige native Testinstallation sicher wiederherstellen …")
        # This existing public operation is the only native-file writer used here.
        workflow.restore_probe(game)
        with recovery._guard():
            if recovery.installation_status(game)["installed"]:
                raise DiagnosticError("Native Testinstallation ist noch aktiv. Bitte zuerst wiederherstellen.")
            _require_normal_start(game)
            if diagnostic_status(game)["installed"]:
                raise DiagnosticError("Eine andere Diagnose wurde inzwischen vorbereitet.")
            _validate_existing_mod(game)
            request_id = uuid.uuid4().hex
            directory = _path(local, "diagnostics/" + request_id)
            directory.mkdir(parents=True, exist_ok=False)
            _plain(directory)
            backup = _path(game, STATE_DIR + "/runs/" + request_id)
            imported = _path(saves, "TF2-API-Diagnose-" + request_id + ".sav")
            run = DiagnosticRun(request_id, str(directory), str(game), str(saves), str(imported),
                                str(directory / "report.json"), str(backup), str(game / "mods" / MOD))
            _validate_run(run)
            payload = directory / "payload"
            payload.mkdir()
            for name, expected in files.items():
                target = _path(payload, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                baseline._copy_file(_path(source, name), target, expected, None, MAX_MOD_FILE_BYTES)
            config = ("-- Locally generated for one read-only API audit.\nreturn { enabled = true, request_id = "
                      + _lua_string(request_id) + ", output_file = "
                      + _lua_string(Path(run.report_path).as_posix()) + " }\n")
            _path(payload, CONFIG).write_text(config, encoding="utf-8")
            files[CONFIG] = _hash(_path(payload, CONFIG))
            journal = {"owner": OWNER, "format": 1, "request_id": request_id, "game_dir": str(game),
                       "state": "backed_up", "imported_save": str(imported), "files": [], "created_dirs": []}
            backup.mkdir(parents=True, exist_ok=False)
            progress("Diagnosemod sichern und eine frische Testkopie vorbereiten …")
            for name, expected in sorted(files.items()):
                relative = f"mods/{MOD}/{name}"
                target = _path(game, relative)
                previous = _hash(target)
                if previous is not None:
                    saved = _path(backup, "original/" + relative)
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    baseline._copy_file(target, saved, previous, None, MAX_MOD_FILE_BYTES)
                journal["files"].append({"path": relative, "original_sha256": previous, "deployed_sha256": expected})
                parent = target.parent
                while parent != game and not parent.exists():
                    relative_dir = parent.relative_to(game).as_posix()
                    if relative_dir not in journal["created_dirs"]:
                        journal["created_dirs"].append(relative_dir)
                    parent = parent.parent
            recovery._write_json(backup / "journal.json", journal)
            recovery._write_json(game / STATE_DIR / "current.json", {"owner": OWNER, "request_id": request_id})
            recovery._write_json(directory / "run.json", {"owner": OWNER, "format": 1, "run": asdict(run)})
            try:
                recovery._require_closed()
                baseline._copy_file(original, imported, sav_hash, sav_size, baseline.MAX_SAVE_BYTES)
                recovery._require_closed()
                baseline._copy_file(original_lua, Path(str(imported) + ".lua"), lua_hash, lua_size, baseline.MAX_LUA_BYTES)
                journal["state"] = "installing"
                recovery._write_json(backup / "journal.json", journal)
                for entry in journal["files"]:
                    recovery._require_closed()
                    target = _path(game, entry["path"])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    name = entry["path"].removeprefix(f"mods/{MOD}/")
                    recovery._replace(_path(payload, name), target, entry["deployed_sha256"], entry["original_sha256"])
                journal["state"] = "installed"
                recovery._write_json(backup / "journal.json", journal)
            except Exception as exc:
                journal["state"] = "install_failed"
                recovery._write_json(backup / "journal.json", journal)
                recovery._write_json(directory / "preparation-error.json", {"error": str(exc)})
                try:
                    _restore(game, backup, journal)
                except Exception as restore_error:
                    raise DiagnosticError(f"Diagnosevorbereitung fehlgeschlagen: {exc}. Wiederherstellung benötigt Hilfe: {restore_error}. Sicherung: {backup}") from exc
                raise DiagnosticError("Diagnosevorbereitung fehlgeschlagen; Moddateien wurden wiederhergestellt: " + str(exc)) from exc
            progress("Solo-Diagnose vorbereitet. TF2 selbst über Steam starten und die angezeigte Diagnose-Save laden.")
            return run
    except (OSError, baseline.BaselineError, recovery.ProbeInstallError) as exc:
        raise DiagnosticError(str(exc)) from exc


def read_diagnostic_report(run: DiagnosticRun) -> dict | None:
    """Read only the bounded report belonging to this exact audit request."""
    try:
        run = _validate_run(run)
        path = _plain(run.report_path)
        if not path.exists():
            return None
        with baseline._open_regular(path, MAX_REPORT_BYTES):
            pass
        raw = _shared_read(path, MAX_REPORT_BYTES)
        if len(raw) > MAX_REPORT_BYTES:
            raise DiagnosticError("Diagnosebericht überschreitet 98304 Bytes.")
        report = _json_bytes(raw)
        if (type(report.get("format")) is not int or report["format"] != 1
                or report.get("mode") != MODE or report.get("request_id") != run.request_id
                or type(report.get("status")) is not str or report["status"] not in {"completed", "error"}
                or report.get("valid_snapshot") is not False
                or type(report.get("records")) is not list
                or len(report["records"]) > 1024 or any(type(record) is not dict for record in report["records"])
                or type(report.get("limits")) is not dict
                or type(report.get("truncated")) is not bool):
            raise DiagnosticError("Diagnosebericht gehört nicht zum aktuellen Auftrag oder hat ein ungültiges Format.")
        return report
    except FileNotFoundError:
        return None  # A report is published only after the Lua collection completes.
    except (OSError, baseline.BaselineError) as exc:
        raise DiagnosticError(str(exc)) from exc


def export_diagnostic(run: DiagnosticRun, destination: Path) -> Path:
    """Export the validated API report only; never saves, keys, configs or logs."""
    report = read_diagnostic_report(run)
    if report is None:
        raise DiagnosticError("Noch kein Diagnosebericht vorhanden. Zuerst die Diagnose-Save laden.")
    try:
        destination = _plain(destination)
        _directory(destination.parent)
        if destination.suffix.lower() != ".zip":
            raise DiagnosticError("Für den Diagnoseexport bitte eine ZIP-Datei wählen.")
        payload = (json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(payload) > MAX_REPORT_BYTES:
            raise DiagnosticError("Der exportierte Diagnosebericht überschreitet sein Größenlimit.")
        info = {"format": 1, "mode": MODE, "request_id": run.request_id,
                "valid_snapshot": False, "note": "API type observations only; no synchronization proof."}
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("api-audit.json", payload)
            archive.writestr("diagnostic-info.json", json.dumps(info, sort_keys=True, indent=2) + "\n")
        return destination
    except (OSError, ValueError, baseline.BaselineError) as exc:
        raise DiagnosticError("Diagnoseexport fehlgeschlagen: " + str(exc)) from exc
