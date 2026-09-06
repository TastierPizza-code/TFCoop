"""Headless workflow behind the Bautest. Only explicit Prepare installs files.

Connection starts our own hidden controllers. Starting TF2 remains a manual
Steam action. This module never sends UI input or launches the game executable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import uuid
import zipfile

from coop.install import _steam_roots
from coop.native import game_is_running
from .engine_mailbox import _shared_read
from .probe_install import install_probe, installation_status, restore_probe
from .stage_probe import stage_probe
from .build_profile import BUILD_PROFILE, BUILD_ROUNDS
from prototype.release_version import DISPLAY_VERSION

PORT = 34207
LOBBY_PORT = 34208
ROUNDS = BUILD_ROUNDS
PROFILE = BUILD_PROFILE
VERSION = DISPLAY_VERSION


def resources():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def package_directory():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else resources()


def baseline_save():
    base = package_directory()
    if getattr(sys, "frozen", False):
        from prototype.baseline import resolve_baseline
        return resolve_baseline(base, local_root())
    return base / "prototype/staged/time-probe-20260906/save/initial.sav"


def local_root():
    if not os.environ.get("LOCALAPPDATA"):
        raise ValueError("Dieses Testpaket benötigt Windows mit LOCALAPPDATA.")
    return Path(os.environ["LOCALAPPDATA"]) / "TF2StrictProbe"


def new_code():
    raw = secrets.token_hex(16).upper()
    return "-".join(raw[index:index + 4] for index in range(0, 32, 4))


def connection_identity(code):
    raw = str(code).replace("-", "").replace(" ", "").strip().lower()
    if len(raw) != 32 or any(c not in "0123456789abcdef" for c in raw):
        raise ValueError("Bitte den vollständigen Sitzungscode des Hosts einfügen (8 Gruppen).")
    return (hashlib.sha256(("tf2-probe-epoch:" + raw).encode()).hexdigest()[:32],
            hashlib.sha256(("tf2-probe-key:" + raw).encode()).hexdigest().encode("ascii"))


def validate_host(value):
    try:
        address = ipaddress.IPv4Address(str(value).strip())
        if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
            raise ValueError()
    except ValueError as exc:
        raise ValueError("Bitte die IPv4-Adresse des Hosts aus Hamachi oder dem gemeinsamen LAN eingeben.") from exc
    return str(address)


def suggested_addresses():
    try:
        addresses = set(socket.gethostbyname_ex(socket.gethostname())[2])
        return sorted((a for a in addresses if not a.startswith("127.")),
                      key=lambda a: (not a.startswith("25."), a))
    except OSError:
        return []


def save_directories():
    found = set()
    for root in _steam_roots():
        userdata = root / "userdata"
        if userdata.is_dir():
            for account in userdata.iterdir():
                candidate = account / "1066780/local/save"
                if account.name.isdigit() and candidate.is_dir():
                    found.add(str(candidate.resolve()))
    return sorted(found)


def read_json(path):
    try:
        raw = _shared_read(Path(path), 1024 * 1024)
        if len(raw) > 1024 * 1024:
            return None
        value = json.loads(raw.decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def current_game_assertion(prepared):
    """Recognize a fatal assertion from this actual launch, not old game logs.

    TF2's fatal handler may leave the process alive and our worker waiting. The
    selected save's sibling crash_dump is the game's existing diagnostic path.
    Only assertion lines are retained, never the full game log or arbitrary data.
    """
    marker = Path(prepared.session) / "controller_started.json"
    path = Path(prepared.imported_save).parent.parent / "crash_dump/stdout.txt"
    try:
        if not marker.is_file() or not path.is_file() or path.is_symlink():
            return None
        if path.stat().st_mtime_ns < marker.stat().st_mtime_ns:
            return None
        with path.open("rb") as stream:
            stream.seek(0, 2)
            length = stream.tell()
            stream.seek(max(0, length - 262144))
            lines = stream.read(262144).decode("utf-8", errors="replace").splitlines()
        relevant = [line[-2048:] for line in lines if "Assertion" in line and "failed" in line]
        return "\n".join(relevant[-5:]) if relevant else None
    except OSError:
        return None


def failure_reason(previous, *sources):
    """Keep the originating failure visible when shutdown produces follow-on errors."""
    reasons = [previous] if previous else []
    for source in sources:
        if source.get("state") == "halted" or source.get("halted") is True:
            reason = source.get("reason")
            if isinstance(reason, str) and reason:
                reasons.append(reason[:2048])
    if not reasons:
        return ""
    # An EOF is useful only until the originating local/remote report arrives.
    for reason in reasons:
        if not any(fragment in reason for fragment in (
                "IncompleteReadError", "local stop requested", "local stop file",
                "controller requested halt", "measurement stopped by local user",
                "Controller beendet (Code", "Messcontroller hat angehalten.")):
            return reason
    return reasons[0]


def measured_round(*sources):
    """Progress/report files can arrive separately; a halt must not reset to zero."""
    rounds = [source.get("round") for source in sources]
    return max((value for value in rounds if type(value) is int and 0 <= value <= ROUNDS), default=0)


@dataclass
class PreparedRun:
    run_dir: str
    game_dir: str
    session: str
    output: str
    imported_save: str
    backup_path: str
    role: str
    host: str
    epoch: str
    manifest: str

    @property
    def directory(self):
        return Path(self.run_dir)

    @property
    def stop_path(self):
        return self.directory / "stop.txt"


def prepare(game_dir, save_dir, role, host, code, *, source_root=None, save=None, runs_root=None):
    if role not in ("a", "b"):
        raise ValueError("Bitte Host oder Mitspieler wählen.")
    host = validate_host(host)
    epoch, secret = connection_identity(code)
    if game_is_running():
        raise ValueError("Bitte TF2 vollständig schließen, bevor du den Test vorbereitest.")
    game = Path(game_dir).resolve()
    if installation_status(game)["installed"]:
        raise ValueError("Der vorherige Test ist noch installiert. Zuerst 'Bisherige Installation wiederherstellen' verwenden.")
    destination = Path(save_dir).resolve()
    if not destination.is_dir():
        raise ValueError("Bitte den vorhandenen Steam-Saveordner auswählen.")
    run = (Path(runs_root) if runs_root else local_root() / "runs") / uuid.uuid4().hex
    run.mkdir(parents=True, exist_ok=False)
    try:
        result = stage_probe(game_dir=game, save=save or baseline_save(), session=run / "session",
                             output=run / "payload", repository_root=source_root or resources(), profile=PROFILE)
        installed = install_probe(game, Path(result["output"]), destination,
                                  session_dir=Path(result["session"]))
        prepared = PreparedRun(str(run), str(game), result["session"], result["output"],
                               installed["imported_save"], installed["backup_path"], role,
                               host, epoch, result["manifest_digest"])
        (run / "session.key").write_bytes(secret)
        write_json(run / "run.json", asdict(prepared))
        return prepared
    except Exception as exc:
        # Keep incomplete preparation/installer recovery evidence. Never claim
        # a playable result and never delete the user's game/save as cleanup.
        write_json(run / "preparation-error.json", {"error": str(exc), "game_dir": str(game)})
        raise


def worker_command(kind, args, log):
    entry = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(resources() / "probe_launcher.py")]
    return [*entry, "--worker-log", str(log), "--worker", kind, *map(str, args)]


class SessionController:
    """UI-polled lifecycle. Never launches or terminates another application."""
    def __init__(self, prepared, *, spawn=subprocess.Popen, clock=time.monotonic):
        self.run = prepared
        self.spawn, self.clock = spawn, clock
        self.children = {}
        self.started = False
        self.peer_started = False
        self.stopping = False
        self.started_at = 0
        self.failure = ""

    def _spawn(self, label, kind, args):
        log = self.run.directory / (label + ".log")
        child = self.spawn(worker_command(kind, args, log), cwd=package_directory(),
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.children[label] = child

    def _game_args(self, mode):
        directory = self.run.directory
        return [mode, "--session", self.run.session, "--epoch", self.run.epoch,
                "--key-file", directory / "session.key", "--report", directory / (mode + "-report.json"),
                "--progress", directory / (mode + "-progress.json"), "--stop-file", self.run.stop_path,
                "--rounds", ROUNDS, "--profile", PROFILE, "--timeout", 30,
                "--startup-timeout", 600, "--port", PORT]

    def start(self):
        if self.started or self.run.stop_path.exists():
            raise ValueError("Für einen weiteren Versuch bitte eine neue Testsitzung vorbereiten.")
        if game_is_running():
            raise ValueError("Bitte TF2 schließen. Erst verbinden und auf die Startmeldung warten.")
        self.started, self.started_at = True, self.clock()
        try:
            if self.run.role == "a":
                self._spawn("host", "game", self._game_args("host") +
                            ["--bind", "0.0.0.0", "--ready", self.run.directory / "host-ready.json"])
            self._spawn("lobby", "lobby", ["--role", self.run.role, "--host", self.run.host,
                "--bind", "0.0.0.0", "--port", LOBBY_PORT, "--epoch", self.run.epoch,
                "--manifest", self.run.manifest, "--key-file", self.run.directory / "session.key",
                "--progress", self.run.directory / "lobby-progress.json", "--stop-file", self.run.stop_path,
                "--timeout", 600])
        except Exception:
            self.stop()
            raise

    def stop(self):
        self.stopping = True
        self.run.stop_path.write_text("stop requested by launcher\n", encoding="ascii")

    def alive(self):
        return any(child.poll() is None for child in self.children.values())

    def poll(self):
        directory = self.run.directory
        lobby = read_json(directory / "lobby-progress.json") or {}
        peer = read_json(directory / "peer-progress.json") or {}
        host = read_json(directory / "host-progress.json") or {}
        peer_report = read_json(directory / "peer-report.json") or {}
        host_report = read_json(directory / "host-report.json") or {}
        completed = bool(peer_report.get("finished"))
        coordinated = bool(host.get("coordinated_completed") or host_report.get("coordinated_completed"))
        failure = failure_reason(self.failure, peer, peer_report, host, host_report)
        if lobby.get("state") == "connected" and (lobby.get("epoch") != self.run.epoch
                or lobby.get("manifest") != self.run.manifest or lobby.get("protocol") != 1):
            failure = "Die Verbindungsbestätigung gehört nicht zu dieser Testsitzung."
        ready = read_json(directory / "host-ready.json")
        ready_valid = bool(ready and ready.get("epoch") == self.run.epoch and ready.get("port") == PORT
                           and ready.get("backend") == "tf2_controlled_measurement")
        if self.run.role == "a" and ready is not None and not ready_valid:
            failure = "Ungültige Startbestätigung des Testservers."
        if not failure and any(source.get("state") == "halted" for source in (peer, host)):
            failure = "Messcontroller hat angehalten."
        if not failure and not completed and lobby.get("state") == "halted":
            failure = lobby.get("reason") or "Verbindung zum Mitspieler unterbrochen."
        for label, child in self.children.items():
            code = child.poll()
            normal_finish = ((label == "peer" and completed) or (label == "host" and coordinated)) and code == 0
            if code is not None and not normal_finish and not self.stopping and not failure:
                failure = f"{label}-Controller beendet (Code {code}). Details im Testbericht."
        assertion = current_game_assertion(self.run) if self.started else None
        if assertion:
            failure = "TF2 meldet einen Engine-Abbruch: " + assertion.splitlines()[-1][-500:]
        if failure:
            self.failure = failure
            if not self.stopping:
                self.stop()
        if (self.started and not self.stopping and not self.peer_started and lobby.get("state") == "connected"
                and (self.run.role == "b" or ready_valid)):
            try:
                self._spawn("peer", "game", self._game_args("peer") +
                        ["--peer", self.run.role, "--host", "127.0.0.1" if self.run.role == "a" else self.run.host,
                         "--inputs", resources() / "prototype/examples" / ("probe-a.json" if self.run.role == "a" else "probe-b.json"),
                         "--delay-ms", 0 if self.run.role == "a" else 100])
                self.peer_started = True
            except Exception as exc:
                self.failure = failure = "Messcontroller konnte nicht starten: " + str(exc)
                self.stop()
        return {"lobby": lobby, "peer": peer, "host": host, "failure": failure,
                "round": measured_round(peer, peer_report, host, host_report),
                "completed": completed, "coordinated_completed": coordinated,
                "stopping": self.stopping, "alive": self.alive()}


def describe_status(status):
    if status["failure"]:
        return "Test angehalten: " + status["failure"]
    if status["completed"]:
        return ("Gemeinsamer Bautest abgeschlossen. Beide Ergebnisanzeigen vergleichen; TF2 jetzt schließen."
                if status["coordinated_completed"] else
                "Bautest abgeschlossen. Host-Ergebnis mit dem Freund vergleichen; TF2 jetzt schließen.")
    if status["stopping"]:
        return "Test wird beendet. Die Spielzeit bleibt gehalten. TF2 selbst schließen."
    peer = status["peer"]
    if peer.get("state") == "running":
        phase = peer.get("phase_label") or "Bau- und Fahrzeugwerte vergleichen"
        return f"{phase} · Runde {peer.get('round', '?')} von {ROUNDS}. Bitte nichts bauen oder umschalten."
    if peer.get("state") == "waiting_peer":
        return "Dein Testspielstand ist geladen. Warte auf den geladenen Spielstand deines Freundes."
    if peer.get("state") == "waiting_game":
        native = peer.get("native") or {}
        if native.get("outer_calls", 0):
            return "Spielkontakt vorhanden. Warte auf die aktivierte Testmod im richtigen Spielstand."
        return "Mitspieler verbunden. TF2 jetzt selbst über Steam starten (innerhalb von 2 Minuten), dann Testspielstand laden."
    if status["lobby"].get("state") == "connected":
        return "Mitspieler verbunden; Testdateien stimmen überein. Messcontroller wird bereitgestellt …"
    return "Warte auf den Mitspieler. Auf beiden PCs müssen Host-IP und Sitzungscode übereinstimmen."


def export_diagnostics(prepared, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Der Bericht existiert schon. Bitte einen neuen Dateinamen wählen.")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("INFO.txt", VERSION + "; begrenzter Engineversuch, kein vollständiger Synchronitätsnachweis.\n")
        assertion = current_game_assertion(prepared)
        if assertion:
            archive.writestr("game-assertion.txt", assertion + "\n")
        for directory, names, prefix in (
            (prepared.directory, ("host.log", "peer.log", "lobby.log", "host-report.json", "peer-report.json",
                                  "host-progress.json", "peer-progress.json", "lobby-progress.json", "preparation-error.json",
                                  "peer-journal.jsonl"), ""),
            (Path(prepared.session), ("probe_manifest.json", "native_status.txt", "lua_status.json", "loader_status.txt"), "session/")):
            for name in names:
                path = directory / name
                limit = (64 if name == "peer-journal.jsonl" else 16) * 1024 * 1024
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= limit:
                    try:
                        raw = _shared_read(path, limit)
                    except (FileNotFoundError, PermissionError):
                        continue  # An in-progress publication is not a complete diagnostic.
                    if len(raw) <= limit:
                        archive.writestr(prefix + name, raw)
    return destination
