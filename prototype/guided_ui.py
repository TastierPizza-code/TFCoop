"""Read-only presentation for the guided test, independent of Tk and the game.

The catalog describes instructions. Only the controller's mutually settled
progress is allowed to check off a step; clicking a button is never evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from prototype.strict_sync.short_build_profile import SHORT_BUILD_ROUNDS


ROLE_NAMES = {"a": "Host", "b": "Freund"}


@dataclass(frozen=True)
class GuidedCard:
    title: str
    instruction: str
    actor: str
    action_label: str
    command: dict | None
    enabled: bool
    completed: int
    total: int
    checklist: tuple[tuple[str, str, str], ...]
    phase: str


@dataclass(frozen=True)
class StartupCard:
    title: str
    instruction: str
    action_label: str
    start_game: bool
    phase: str
    setup_round: int = 0
    total_rounds: int = SHORT_BUILD_ROUNDS
    progress_text: str = ""


def guided_progress(status: Mapping) -> Mapping:
    value = (status.get("guided") or (status.get("live") or {}).get("guided")
             or (status.get("live_result") or {}).get("guided") or {})
    return value if isinstance(value, Mapping) else {}


def joint_started(status: Mapping) -> bool:
    """A latent catalogue entry or local live_start is not joint readiness.

    confirmed_paused first becomes a bool after both live_ready receipts on the
    coordinator, or its next authenticated operation on the replica. This comes
    after the shared short preparation; later failures retain that evidence.
    """
    live = status.get("live") or {}
    if live.get("started") is not True:
        live = (status.get("live_result") or {}).get("progress") or {}
    number = status.get("round")
    return (live.get("started") is True and type(live.get("confirmed_paused")) is bool
            and type(number) is int and number >= SHORT_BUILD_ROUNDS)


def startup_card(status: Mapping) -> StartupCard:
    """Translate observed worker states; never infer loading from process launch."""
    peer = status.get("peer") or {}
    live = status.get("live") or {}
    number = peer.get("round", status.get("round", 0))
    number = min(SHORT_BUILD_ROUNDS, max(0, number)) if type(number) is int else 0
    if (status.get("lobby") or {}).get("state") != "connected":
        return StartupCard("Verbindung zum Mitspieler aufbauen",
            "Beide drücken Verbinden und lassen den Launcher geöffnet. Die gemeinsame Verbindung wird erst geprüft; "
            "das Spiel noch nicht starten.", "Auf den Mitspieler warten", False, "connecting",
            progress_text="Verbindung noch nicht bestätigt")
    if peer.get("state") == "waiting_game":
        native = peer.get("native") or {}
        if type(native.get("outer_calls")) is int and native["outer_calls"] > 0:
            return StartupCard("Den frischen Testspielstand laden",
                "TF2 hat sich auf diesem PC gemeldet. Jetzt im Spiel genau den unten genannten Spielstand laden. "
                "Auf den bestätigten Kontakt mit der Testmod warten.", "Auf den geladenen Spielstand warten",
                False, "waiting_world", progress_text="Verbindung bestätigt · Spielkontakt vorhanden · Spielstand wird noch geprüft")
        return StartupCard("3  ·  TF2 starten und den Testspielstand laden",
            "Die Launcher sind verbunden. Jetzt TF2 über diese Taste starten und genau den unten genannten Spielstand laden. "
            "Beide laden ihren frischen Testspielstand; danach folgt automatisch die kurze gemeinsame Prüfung.",
            "TF2 über Steam starten", True, "waiting_game",
            progress_text="Verbindung bestätigt · Warte auf TF2 und Testspielstand")
    if peer.get("state") == "waiting_peer":
        return StartupCard("Dein Testspielstand ist geladen",
            "Der Spielstand und die Testmod auf diesem PC sind bereit. Warte, bis auch der Mitspieler geladen hat "
            "und beide Ausgangszustände verglichen sind. Im Spiel nur die Kamera bewegen.",
            "Auf beide Spielstände warten", False, "waiting_peer",
            progress_text="Verbindung bestätigt · Eigener Spielstand bereit · Mitspieler wird erwartet")
    if peer.get("state") == "running":
        if live.get("started") is True or number >= SHORT_BUILD_ROUNDS:
            return StartupCard("Gemeinsame Kurzprüfung abschließen",
                "Beide Spielstände haben den gemeinsamen Aufbau erreicht. Jetzt werden die letzten Rückmeldungen "
                "beider Spiele bestätigt. Der erste Host-Auftrag erscheint danach automatisch.",
                "Gemeinsame Bestätigung abwarten", False, "confirming", number,
                progress_text="Verbindung und beide Spielstände bestätigt · Abschluss der Kurzprüfung ausstehend")
        phase = peer.get("phase_label")
        detail = (str(phase) + ". ") if phase else ""
        return StartupCard(f"Kurzer gemeinsamer Aufbau · Runde {number + 1} / {SHORT_BUILD_ROUNDS}",
            "Beide Ausgangsspielstände sind verbunden und verglichen. " + detail +
            "Der Test baut eine kleine Straße mit Depot, Halten und einem Fahrzeug und prüft die Ergebnisse beider PCs. "
            "Bitte zuschauen; der erste Host-Auftrag folgt nach der gemeinsamen Bestätigung.",
            "Aufbau auf beiden PCs prüfen", False, "preparing", number,
            progress_text=f"Verbindung und beide Spielstände bestätigt · Aufbau bei Runde {number + 1} / {SHORT_BUILD_ROUNDS}")
    return StartupCard("Spielstart wird bereitgestellt",
        "Die Launcher sind verbunden und ihre Testdateien stimmen überein. Der Spielstart wird vorbereitet. "
        "Sobald die Startfreigabe vorliegt, erscheint hier die Steam-Taste.",
        "Startfreigabe abwarten", False, "starting_controller",
        progress_text="Verbindung bestätigt · Spielstart wird vorbereitet")


def card(status: Mapping, steps: Sequence[Mapping], *, role: str,
         available: bool = False, locally_pending: bool = False) -> GuidedCard:
    """Build one safe action card, retaining no mutable progress of its own."""
    total = len(steps)
    progress = guided_progress(status)
    completed_ids = progress.get("completed_step_ids", [])
    coherent = (isinstance(completed_ids, list) and len(completed_ids) <= total
                and completed_ids == [item["id"] for item in steps[:len(completed_ids)]])
    count = len(completed_ids) if coherent else 0
    phase = progress.get("phase", "waiting")
    started = joint_started(status)
    index = progress.get("index")
    coherent = coherent and type(index) is int and index == count
    if progress.get("completed_steps", count) != count:
        coherent = False
    if progress.get("total_steps", total) != total:
        coherent = False
    failure = status.get("failure") or progress.get("error")
    terminal = bool(failure or status.get("stopping") or phase == "halted")
    complete = started and coherent and count == total and phase in ("completed", "pending")
    current = steps[count] if started and coherent and count < total else None
    if current and (progress.get("step_id") != current["id"]
                    or progress.get("step") != current["step"]):
        current = None
        coherent = False
    # Invalid progress must never turn a catalog entry into a green checkmark.
    if not coherent or not started:
        count = 0
    checklist = tuple((item["id"], item["title"],
                       "confirmed" if offset < count else
                       "current" if current is item and not terminal else "untested")
                      for offset, item in enumerate(steps))
    if terminal:
        return GuidedCard("Test angehalten", str(failure or "Der Test wird beendet."), "Beide",
                          "Berichte von beiden PCs speichern", None, False, count, total, checklist, "halted")
    if complete:
        return GuidedCard("Alle geführten Schritte gemeinsam bestätigt",
                          "Der gemeinsame Abschluss läuft. Danach auf beiden PCs den Testbericht speichern. "
                          "Die Auswertung zeigt den Umfang der tatsächlich bestandenen Prüfungen.",
                          "Beide", "Gemeinsamen Abschluss abwarten", None, False,
                          count, total, checklist, "completed" if phase == "completed" else "finishing")
    if not started:
        startup = startup_card(status)
        return GuidedCard(startup.title, startup.instruction, "Beide", startup.action_label,
                          None, False, 0, total, checklist, startup.phase)
    if not current:
        return GuidedCard("Gemeinsamen Aufbau abwarten",
                          "Sobald beide denselben frischen Spielstand geladen haben und die kurze Vorbereitung "
                          "bestätigt ist, erscheint hier der erste Auftrag. Im Spiel nur die Kamera bewegen.",
                          "Beide", "Warte auf beide Spiele", None, False, count, total, checklist, "waiting")
    actor = ROLE_NAMES.get(current["actor"], "Unbekannte Rolle")
    pending = bool(progress.get("pending") or phase == "pending" or locally_pending)
    own = current["actor"] == role
    enabled = bool(available and not pending and own and phase == "ready" and progress.get("ready") is True
                   and not status.get("completed") and not status.get("finish_requested"))
    label = ("Gemeinsame Bestätigung abwarten …" if pending else
             current["action_label"] if own else f"Warte auf {actor}")
    instruction = current["instruction"]
    attempt = progress.get("last_attempt") or {}
    if (attempt.get("step") == current["step"] and attempt.get("status") in ("rejected", "not_ready")
            and attempt.get("reason") == "not_ready" and not pending):
        instruction += " Die Voraussetzung war beim letzten Versuch noch nicht erfüllt. Kurz weiter beobachten und erneut auslösen."
    if not own:
        instruction += f" {actor} löst diesen Schritt in seinem Launcher aus."
    return GuidedCard(f"{count + 1} / {total}  ·  {current['title']}", instruction,
                      actor, label, dict(current["command"]), enabled, count, total, checklist,
                      "pending" if pending else phase)
