"""Headless workflow behind the Bautest. Only explicit Prepare installs files.

Connection starts our own hidden controllers. Starting TF2 remains a manual
Steam action. This module never sends UI input or launches the game executable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
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
from .short_build_profile import SHORT_BUILD_ROUNDS, SHORT_BUILD_CONTRACT
from .core import digest
from .test_pairing import (connection_identity, game_secret, new_code, redact_addresses,
                           validate_connection, validate_host, validate_token)
from prototype.release_version import DISPLAY_VERSION

PORT = 34207
LOBBY_PORT = 34208
ROUNDS = BUILD_ROUNDS
TIMING_WINDOWS = 12
PROGRESS_TOTAL = ROUNDS + TIMING_WINDOWS
STREAM_MODE = "stream_v1"
TIMING_MODE = "timing_v1"
LIVE_MODE = "live_input_v1"
PACED_LIVE_MODE = "paced_live_v1"
MANUAL_DEPOT_MODE = "manual_depot_v1"
GUIDED_MODE = "guided_suite_v1"
LIVE_MODES = (LIVE_MODE, PACED_LIVE_MODE, MANUAL_DEPOT_MODE, GUIDED_MODE)
TEST_MODES = {
    GUIDED_MODE: "Geführter gemeinsamer Test",
    MANUAL_DEPOT_MODE: "Depot selbst beauftragen · kurzer Aufbau",
    PACED_LIVE_MODE: "Fahrt und Eingaben aus Alpha5.15 · kurzer Aufbau",
    LIVE_MODE: "Eingabetest aus Alpha5.13 · vollständiger Aufbau",
    STREAM_MODE: "Referenztest aus Alpha5.12",
    TIMING_MODE: "Vergleichstest aus Alpha5.11",
}
STREAM_STEPS = 600
STREAM_CHECKPOINTS = 12
PROFILE = BUILD_PROFILE
VERSION = DISPLAY_VERSION


def preparation_rounds(test_mode):
    if test_mode not in TEST_MODES:
        raise ValueError("Unbekannter Testablauf.")
    return SHORT_BUILD_ROUNDS if test_mode in (PACED_LIVE_MODE, MANUAL_DEPOT_MODE, GUIDED_MODE) else ROUNDS


def input_queue_options(test_mode):
    if test_mode == GUIDED_MODE:
        from .guided_input import validate_command
        return {"command_validator": validate_command}
    if test_mode == MANUAL_DEPOT_MODE:
        from .manual_depot_input import validate_command
        return {"command_validator": validate_command}
    return {}


def resources():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def package_directory():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else resources()


def baseline_save():
    base = package_directory()
    if getattr(sys, "frozen", False):
        from prototype.baseline import resolve_baseline
        return resolve_baseline(base, local_root())
    return base / "prototype/staged/local-clean-20260907/save/initial.sav"


def local_root():
    if not os.environ.get("LOCALAPPDATA"):
        raise ValueError("Dieses Testpaket benötigt Windows mit LOCALAPPDATA.")
    return Path(os.environ["LOCALAPPDATA"]) / "TF2StrictProbe"


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


def read_json(path, *, limit=1024 * 1024):
    try:
        raw = _shared_read(Path(path), limit)
        if len(raw) > limit:
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
    test_mode: str = TIMING_MODE
    pairing_epoch: str = ""
    local_run: str = ""

    def __post_init__(self):
        if self.test_mode not in TEST_MODES:
            raise ValueError("Unbekannter Testablauf. Bitte neu vorbereiten.")
        if self.pairing_epoch or self.local_run:
            validate_token(self.pairing_epoch)
            validate_token(self.local_run)
            if self.epoch:
                validate_token(self.epoch)

    @property
    def directory(self):
        return Path(self.run_dir)

    @property
    def stop_path(self):
        return self.directory / "stop.txt"

    @property
    def live_input_path(self):
        return self.directory / "live-input.json"


def lobby_manifest(file_manifest, test_mode):
    if test_mode not in TEST_MODES:
        raise ValueError("Bitte einen gültigen Testablauf auswählen.")
    return digest({"file_manifest": file_manifest, "test_mode": test_mode})


def prepare(game_dir, save_dir, role, host, code, *, source_root=None, save=None, runs_root=None,
            test_mode=PACED_LIVE_MODE):
    if test_mode not in TEST_MODES:
        raise ValueError("Bitte einen gültigen Testablauf auswählen.")
    if role not in ("a", "b"):
        raise ValueError("Bitte Host oder Mitspieler wählen.")
    host = validate_host(host)
    pairing_epoch, secret = connection_identity(code)
    if game_is_running():
        raise ValueError("Bitte TF2 vollständig schließen, bevor du den Test vorbereitest.")
    game = Path(game_dir).resolve()
    if installation_status(game)["installed"]:
        if test_mode != GUIDED_MODE:
            raise ValueError("Der vorherige Test ist noch installiert. Zuerst 'Bisherige Installation wiederherstellen' verwenden.")
        # The verified installer journal, process/lobby guards and exact file
        # conflict checks remain authoritative on a one-button guided rerun.
        restore_probe(game)
    destination = Path(save_dir).resolve()
    if not destination.is_dir():
        raise ValueError("Bitte den vorhandenen Steam-Saveordner auswählen.")
    run = (Path(runs_root) if runs_root else local_root() / "runs") / uuid.uuid4().hex
    run.mkdir(parents=True, exist_ok=False)
    try:
        options = {"preparation": SHORT_BUILD_CONTRACT} if test_mode in (PACED_LIVE_MODE, MANUAL_DEPOT_MODE, GUIDED_MODE) else {}
        if test_mode in (MANUAL_DEPOT_MODE, GUIDED_MODE):
            options["input_mode"] = test_mode
        result = stage_probe(game_dir=game, save=save or baseline_save(), session=run / "session",
                             output=run / "payload", repository_root=source_root or resources(), profile=PROFILE,
                             **options)
        installed = install_probe(game, Path(result["output"]), destination,
                                  session_dir=Path(result["session"]))
        prepared = PreparedRun(str(run), str(game), result["session"], result["output"],
                               installed["imported_save"], installed["backup_path"], role,
                               host, "", lobby_manifest(result["manifest_digest"], test_mode), test_mode,
                               pairing_epoch, uuid.uuid4().hex)
        (run / "pairing.key").write_bytes(secret)
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
        self._input_writer = None
        self.last_submitted_seq = 0
        self.finish_requested = False

    def _spawn(self, label, kind, args):
        log = self.run.directory / (label + ".log")
        child = self.spawn(worker_command(kind, args, log), cwd=package_directory(),
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.children[label] = child

    def _game_args(self, mode):
        if self.run.pairing_epoch and not self.run.epoch:
            raise ValueError("Die frische gemeinsame Sitzung ist noch nicht bestätigt.")
        directory = self.run.directory
        flag = {GUIDED_MODE: "--guided-probe", MANUAL_DEPOT_MODE: "--manual-depot-probe", PACED_LIVE_MODE: "--paced-live-probe", LIVE_MODE: "--live-probe", STREAM_MODE: "--stream-probe",
                TIMING_MODE: "--timing-probe"}[self.run.test_mode]
        args = [mode, "--session", self.run.session, "--epoch", self.run.epoch,
                "--key-file", directory / "session.key", "--report", directory / (mode + "-report.json"),
                "--progress", directory / (mode + "-progress.json"), "--stop-file", self.run.stop_path,
                "--rounds", preparation_rounds(self.run.test_mode), "--profile", PROFILE, "--timeout", 30,
                "--startup-timeout", 600, "--port", PORT, flag]
        if self.run.test_mode in LIVE_MODES and mode == "peer":
            args += ["--live-input-file", self.run.live_input_path]
        return args

    def start(self):
        if self.started or self.run.stop_path.exists():
            raise ValueError("Für einen weiteren Versuch bitte eine neue Testsitzung vorbereiten.")
        if game_is_running():
            raise ValueError("Bitte TF2 schließen. Erst verbinden und auf die Startmeldung warten.")
        if self.run.pairing_epoch:
            if self.run.epoch:
                raise ValueError("Diese Testsitzung wurde schon verbunden. Bitte neu vorbereiten.")
            # A fresh launcher process must not restart an already consumed
            # preparation, even before a game worker has started.
            with (self.run.directory / "launcher-started.json").open("x", encoding="ascii") as claim:
                json.dump({"local_run": self.run.local_run}, claim)
        elif self.run.test_mode in LIVE_MODES:
            from .live_input import InputWriter
            self._input_writer = InputWriter(self.run.live_input_path, self.run.epoch, self.run.role,
                                             **input_queue_options(self.run.test_mode))
        self.started, self.started_at = True, self.clock()
        try:
            if self.run.role == "a" and not self.run.pairing_epoch:
                self._spawn("host", "game", self._game_args("host") +
                            ["--bind", "0.0.0.0", "--ready", self.run.directory / "host-ready.json"])
            pairing = bool(self.run.pairing_epoch)
            self._spawn("lobby", "lobby", ["--role", self.run.role, "--host", self.run.host,
                "--bind", "0.0.0.0", "--port", LOBBY_PORT, "--epoch", self.run.pairing_epoch if pairing else self.run.epoch,
                "--manifest", self.run.manifest, "--key-file", self.run.directory / ("pairing.key" if pairing else "session.key"),
                "--progress", self.run.directory / "lobby-progress.json", "--stop-file", self.run.stop_path,
                "--timeout", 600] + (["--local-run", self.run.local_run] if pairing else []))
        except Exception:
            self.stop()
            raise

    def _activate_connection(self, lobby):
        """One-shot key/queue initialization after the authenticated run commit."""
        if not self.run.pairing_epoch or self.run.epoch:
            raise ValueError("Die gemeinsame Sitzung darf nur einmal bestätigt werden.")
        secret = (self.run.directory / "pairing.key").read_bytes().strip()
        epoch = validate_connection(secret, lobby, role=self.run.role,
                                     local_run=self.run.local_run, manifest=self.run.manifest)
        with (self.run.directory / "session.key").open("xb") as output:
            output.write(game_secret(secret, epoch, self.run.manifest))
        if self.run.test_mode in LIVE_MODES:
            from .live_input import create, InputWriter
            create(self.run.live_input_path, epoch, self.run.role)
            self._input_writer = InputWriter(self.run.live_input_path, epoch, self.run.role,
                                             **input_queue_options(self.run.test_mode))
        self.run.epoch = epoch
        write_json(self.run.directory / "run.json", asdict(self.run))

    def stop(self):
        self.stopping = True
        self.run.stop_path.write_text("stop requested by launcher\n", encoding="ascii")

    def alive(self):
        return any(child.poll() is None for child in self.children.values())

    def submit_live(self, command):
        status = self.poll()
        if not self._input_writer or not live_input_ready(status):
            raise ValueError("Die gemeinsame Eingabephase ist noch nicht bereit oder bereits beendet.")
        if self.run.test_mode == GUIDED_MODE:
            from .guided_catalog import get_step
            guide = guided_status(status)
            acknowledged = (status.get("live", {}).get("acknowledged_seq") or {}).get(self.run.role, 0)
            if (guide.get("phase") != "ready" or guide.get("pending")
                    or guide.get("actor") != self.run.role or self.last_submitted_seq > acknowledged):
                raise ValueError("Bitte den angezeigten Auftrag und die gemeinsame Bestätigung abwarten.")
            if command != get_step(guide.get("step"))["command"]:
                raise ValueError("Diese Aktion gehört nicht zum aktuellen geführten Schritt.")
        sequence = self._input_writer.submit(command)
        self.last_submitted_seq = sequence
        if command.get("op") == "END_TEST":
            self.finish_requested = True
        return sequence

    def poll(self):
        directory = self.run.directory
        lobby = read_json(directory / "lobby-progress.json") or {}
        peer = read_json(directory / "peer-progress.json") or {}
        host = read_json(directory / "host-progress.json") or {}
        # Two peers' 600 native measurements exceed the compact progress limit.
        # Keep progress bounded separately while accepting the fixed test report.
        report_limit = (16 if self.run.test_mode in LIVE_MODES else 4) * 1024 * 1024
        peer_report = read_json(directory / "peer-report.json", limit=report_limit) or {}
        host_report = read_json(directory / "host-report.json", limit=report_limit) or {}
        completed = bool(peer_report.get("finished"))
        coordinated = bool(host.get("coordinated_completed") or host_report.get("coordinated_completed"))
        failure = failure_reason(self.failure, peer, peer_report, host, host_report)
        if lobby.get("state") == "connected":
            if self.run.pairing_epoch:
                try:
                    epoch = validate_connection((directory / "pairing.key").read_bytes().strip(), lobby,
                                                role=self.run.role, local_run=self.run.local_run,
                                                manifest=self.run.manifest)
                    if self.run.epoch and epoch != self.run.epoch:
                        raise ValueError("coordinated run changed")
                except (OSError, ValueError) as exc:
                    failure = "Die Verbindungsbestätigung gehört nicht zu dieser Testsitzung."
            elif (lobby.get("epoch") != self.run.epoch or lobby.get("manifest") != self.run.manifest
                    or lobby.get("protocol") != 1):
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
        if (self.started and not self.stopping and self.run.pairing_epoch and not self.run.epoch
                and lobby.get("state") == "connected"):
            try:
                self._activate_connection(lobby)
                if self.run.role == "a":
                    self._spawn("host", "game", self._game_args("host") +
                                ["--bind", "0.0.0.0", "--ready", directory / "host-ready.json"])
            except Exception as exc:
                self.failure = failure = "Die gemeinsame Sitzung konnte nicht starten: " + str(exc)
                self.stop()
        if (self.started and not self.stopping and not self.peer_started and lobby.get("state") == "connected"
                and (self.run.role == "b" or ready_valid)):
            try:
                self._spawn("peer", "game", self._game_args("peer") +
                        ["--peer", self.run.role, "--host", "127.0.0.1" if self.run.role == "a" else self.run.host,
                         "--inputs", resources() / "prototype/examples" / ("probe-a.json" if self.run.role == "a" else "probe-b.json"),
                         "--delay-ms", 0])
                self.peer_started = True
            except Exception as exc:
                self.failure = failure = "Messcontroller konnte nicht starten: " + str(exc)
                self.stop()
        return {"lobby": lobby, "peer": peer, "host": host, "failure": failure,
                "test_mode": self.run.test_mode,
                "guided": (peer.get("live") or {}).get("guided") or (host.get("live") or {}).get("guided")
                          or (host_report.get("live") or {}).get("guided") or (peer_report.get("live") or {}).get("guided") or {},
                "live": peer.get("live") or host.get("live") or {},
                "live_result": host_report.get("live") or peer_report.get("live") or {},
                "role": self.run.role, "submitted_seq": self.last_submitted_seq,
                "finish_requested": self.finish_requested,
                "peer_started": self.peer_started,
                "stream": peer.get("stream") or host.get("stream") or {},
                "stream_result": host_report.get("stream") or peer_report.get("stream") or {},
                "timing": peer.get("timing") or host.get("timing") or {},
                "timing_result": host_report.get("timing") or peer_report.get("timing") or {},
                "round": measured_round(peer, peer_report, host, host_report),
                "completed": completed, "coordinated_completed": coordinated,
                "stopping": self.stopping, "alive": self.alive()}


def live_input_ready(status):
    live = status.get("live") or {}
    if status.get("test_mode") == GUIDED_MODE:
        guide = guided_status(status)
        if (type(live.get("confirmed_paused")) is not bool
                or type(status.get("round")) is not int
                or status["round"] < SHORT_BUILD_ROUNDS or guide.get("ready") is not True):
            return False
    return bool(status.get("test_mode") in LIVE_MODES and status.get("peer_started")
                and status.get("alive") and not status.get("failure") and not status.get("stopping")
                and not status.get("completed") and not status.get("finish_requested")
                and live.get("started") and not live.get("completed") and not live.get("ending"))


def live_input_status(status):
    if status.get("test_mode") == GUIDED_MODE:
        return guided_input_status(status)
    live = status.get("live") or {}
    if not live.get("started"):
        return "Die Tasten werden nach dem gemeinsamen automatischen Aufbau freigegeben."
    acknowledged = (live.get("acknowledged_seq") or {}).get(status.get("role"), 0)
    submitted = status.get("submitted_seq", 0)
    pending = max(0, submitted - acknowledged)
    confirmed = live.get("confirmed_paused")
    state = "pausiert" if confirmed is True else "läuft" if confirmed is False else "Startbestätigung ausstehend"
    terminal = status.get("completed") or status.get("stopping") or status.get("failure")
    measured = live.get("paused_duration_ms", 0)
    pause = (" Lange Pause erfasst." if live.get("long_pause_met") is True else
             f" Aktuelle gemessene Pause: {int(measured) // 1000} / 35 Sekunden." if confirmed is True else "")
    if status.get("test_mode") == MANUAL_DEPOT_MODE:
        pause = depot_input_status(status)
    return (f"Gemeinsamer Zustand: {state} · Eigene Wünsche beidseitig bestätigt: {acknowledged}. "
            + (f"Ohne gemeinsame Bestätigung beendet: {pending} Wünsche." if pending and terminal else
               f"Noch {pending} zur Bestätigung offen." if pending else "Kein eigener Wunsch offen.")
            + pause
            + (" Gemeinsamer Abschluss angefordert." if status.get("finish_requested") or live.get("ending") else ""))


def guided_status(status):
    return (status.get("guided") or (status.get("live") or {}).get("guided")
            or (status.get("live_result") or {}).get("guided") or {})


def guided_input_status(status):
    from .guided_catalog import get_step, STEPS
    guide = guided_status(status)
    if status.get("failure"):
        return "Test angehalten. Bestätigte Schritte bleiben im Bericht erhalten."
    if not guide:
        return "Nach dem kurzen Aufbau erscheint der erste gemeinsame Auftrag."
    complete = guide.get("completed_steps", 0)
    if guide.get("phase") == "completed":
        return f"{complete} Schritte bestätigt. Gemeinsamen Abschluss abwarten und beide Berichte exportieren."
    if (not (status.get("live") or {}).get("started")
            or type((status.get("live") or {}).get("confirmed_paused")) is not bool
            or guide.get("phase") == "waiting"):
        return "Kurzen Aufbau und Startbestätigung beider Spiele abwarten."
    number = guide.get("step")
    if type(number) is not int or not 1 <= number <= len(STEPS):
        return "Gemeinsamen Teststand abwarten."
    step = get_step(number)
    if guide.get("pending"):
        return f"Schritt {number}/{len(STEPS)}: Beide Spiele prüfen das Ergebnis."
    return f"Schritt {number}/{len(STEPS)}: {step['instruction']}"


def depot_input_status(status):
    """Show only settled outcomes; local execution is not joint approval."""
    outcomes = (status.get("live") or {}).get("acknowledgements") or []
    own = [item for item in outcomes if item.get("peer") == status.get("role")
           and (item.get("command") or {}).get("op") == "BUILD_DEPOT"]
    if not own:
        return " Noch kein eigener Depotauftrag gemeinsam abgeschlossen."
    last = own[-1]
    place = last["command"]["site"]
    if last.get("status") == "applied":
        cost = f"{last['cost']:,}".replace(",", ".")
        return f" Eigener Depotauftrag {last['seq']}: Platz {place} beidseitig gebaut, Kosten {cost}."
    reasons = {"site_occupied": "Platz bereits belegt", "outside_map": "außerhalb der Karte",
               "water": "Platz im Wasser", "too_uneven": "Gelände zu uneben",
               "engine_rejected": "Spiel lehnt diesen Bauvorschlag ab",
               "insufficient_funds": "Geld reicht nicht aus"}
    if last.get("status") == "rejected":
        return (f" Eigener Depotauftrag {last['seq']}: Platz {place} beidseitig abgelehnt – "
                + reasons.get(last.get("reason"), "Ablehnungsgrund im Bericht") + ". Keine Baukosten.")
    return " Depotauftrag noch ohne bestätigtes Ergebnis."


def describe_status(status):
    if status["failure"]:
        return "Test angehalten: " + status["failure"]
    if status.get("test_mode") == GUIDED_MODE and status["completed"]:
        return ("Geführter Ablauf gemeinsam beendet. Beide Berichte exportieren und TF2 schließen. "
                "Die bestätigten festen Aktionen sind im Bericht einzeln aufgeführt.")
    if status["completed"]:
        if status.get("test_mode") in LIVE_MODES:
            live = status.get("live_result") or {}
            met = live.get("required_interactions_met")
            coverage = (("Bau durch beide Spieler, Bau während Fahrt/Pause und Belegungsablehnung sind erfasst"
                         if status.get("test_mode") == MANUAL_DEPOT_MODE else
                         "Die vorgesehenen Pause-/Fortsetzen-Proben sind erfasst") if met is True else
                        "Nicht alle vorgesehenen Bedienproben wurden erfasst" if met is False else
                        "Bedienproben anhand beider Berichte auswerten")
            return ("Eingabetest mit gemeinsamem Abschluss beendet. " + coverage +
                    ". Beide Berichte exportieren und TF2 schließen. Dies prüft die gemessene Testszene.")
        stream = status.get("stream_result") or {}
        if stream:
            met = stream.get("paced_stream_1x_met")
            pace = ("1x-Ziel erreicht" if met is True else "1x-Ziel noch nicht erreicht" if met is False else
                    "Tempoauswertung unvollständig")
            scope = ("Beide PCs" if str(stream.get("completion_scope", "")).startswith("both_peer") else
                     "Tempo auf deinem PC")
            return (f"Gemeinsame Kontrollpunkte und Testpause abgeschlossen · {scope}: {pace}. "
                    "Darstellung separat beurteilen; beide Berichte exportieren und TF2 schließen.")
        timing = status.get("timing_result") or {}
        if timing:
            met = timing.get("paced_windows_1x_met")
            result = ("1x-Ziel in den Fahrtabschnitten erreicht" if met is True else
                      "1x-Ziel noch nicht erreicht" if met is False else "1x-Auswertung unvollständig")
            scope = ("Beide PCs: " if timing.get("completion_scope") == "both_peer_window_boundaries" else
                     "Tempo auf deinem PC: ")
            return ("Vergleich der Messwerte abgeschlossen · " + scope + result +
                    ". Darstellung separat beurteilen; beide Berichte exportieren und TF2 schließen.")
        return ("Gemeinsamer Bautest abgeschlossen. Beide Ergebnisanzeigen vergleichen; TF2 jetzt schließen."
                if status["coordinated_completed"] else
                "Bautest abgeschlossen. Host-Ergebnis mit dem Freund vergleichen; TF2 jetzt schließen.")
    if status["stopping"]:
        return "Test wird beendet. Die Spielzeit bleibt gehalten. TF2 selbst schließen."
    peer = status["peer"]
    if peer.get("state") == "running":
        live = status.get("live") or {}
        if live.get("started"):
            if status.get("test_mode") == GUIDED_MODE:
                return guided_input_status(status)
            if status.get("test_mode") == MANUAL_DEPOT_MODE:
                return ("Depotaufträge sind bereit: zuerst unterschiedliche Plätze, dann denselben Platz versuchen. "
                        "Während Fahrt und gemeinsamer Pause testen; jede Bestätigung abwarten. "
                        "Normale Spielwerkzeuge noch nicht verwenden. Danach 'Messung gemeinsam abschließen'.")
            return ("Jetzt die gemeinsamen Tasten unten nach Anleitung verwenden. "
                    "Jeder pausiert und setzt selbst fort; eine Pause mindestens 45 Sekunden halten. "
                    "Danach 'Messung gemeinsam abschließen'. Im Spiel nichts bauen oder umschalten.")
        stream = status.get("stream") or {}
        if stream.get("started"):
            seconds = min(STREAM_STEPS, stream.get("advanced_steps", 0)) // 5
            checkpoints = stream.get("checkpoint_index", 0)
            return (f"1x-Dauertest: {seconds} / 120 Sekunden Spielzeit · "
                    f"Kontrollpunkt {checkpoints} / {STREAM_CHECKPOINTS}. "
                    "Nach 60 Sekunden kommt die automatische Testpause. Bitte nur zuschauen.")
        timing = status.get("timing") or {}
        if timing.get("started") is True or str(timing.get("stage", "")).startswith("timing"):
            number = min(TIMING_WINDOWS, max(0, timing.get("segment_index", 0)) + 1)
            label = ("Fahrt vor den Warteproben" if number <= 3 else
                     "Warteprobe und Fahrt" if number <= 9 else "Fahrt nach den Warteproben")
            return f"1x-/Warteversuch {number}/{TIMING_WINDOWS}: {label} · {peer.get('phase_label', '')}"
        phase = peer.get("phase_label") or "Bau- und Fahrzeugwerte vergleichen"
        return f"{phase} · Runde {peer.get('round', '?')} von {preparation_rounds(status['test_mode'])}. Bitte nichts bauen oder umschalten."
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
        archive.writestr("INFO.txt", VERSION + "; " + TEST_MODES[prepared.test_mode] +
                         "; begrenzter Engineversuch, kein vollständiger Synchronitätsnachweis.\n")
        assertion = current_game_assertion(prepared)
        if assertion:
            archive.writestr("game-assertion.txt", redact_addresses(assertion) + "\n")
        for directory, names, prefix in (
            (prepared.directory, ("host.log", "peer.log", "lobby.log", "host-report.json", "peer-report.json",
                                  "host-progress.json", "peer-progress.json", "lobby-progress.json", "preparation-error.json",
                                  "peer-journal.jsonl"), ""),
            (Path(prepared.session), ("probe_manifest.json", "native_status.txt", "lua_status.json",
                                      "lua_api_audit.json", "loader_status.txt"), "session/")):
            for name in names:
                path = directory / name
                limit = (64 if name == "peer-journal.jsonl" else 16) * 1024 * 1024
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= limit:
                    try:
                        raw = _shared_read(path, limit)
                    except (FileNotFoundError, PermissionError):
                        continue  # An in-progress publication is not a complete diagnostic.
                    if len(raw) <= limit:
                        # Reports deliberately omit the private profile/key/run
                        # files. Socket exception text can still contain IPs.
                        archive.writestr(prefix + name, redact_addresses(raw.decode("utf-8", errors="replace")))
    return destination
