"""Read-only presentation for the guided test, independent of Tk and the game.

The catalog describes instructions. Only the controller's mutually settled
progress is allowed to check off a step; clicking a button is never evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


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


def guided_progress(status: Mapping) -> Mapping:
    value = (status.get("guided") or (status.get("live") or {}).get("guided")
             or (status.get("live_result") or {}).get("guided") or {})
    return value if isinstance(value, Mapping) else {}


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
    index = progress.get("index")
    coherent = coherent and type(index) is int and index == count
    if progress.get("completed_steps", count) != count:
        coherent = False
    if progress.get("total_steps", total) != total:
        coherent = False
    failure = status.get("failure") or progress.get("error")
    terminal = bool(failure or status.get("stopping") or phase == "halted")
    complete = coherent and count == total and phase in ("completed", "pending")
    current = steps[count] if coherent and count < total else None
    if current and (progress.get("step_id") != current["id"]
                    or progress.get("step") != current["step"]):
        current = None
        coherent = False
    # Invalid progress must never turn a catalog entry into a green checkmark.
    if not coherent:
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
    if not current:
        return GuidedCard("Gemeinsamen Aufbau abwarten",
                          "Sobald beide denselben frischen Spielstand geladen haben und die kurze Vorbereitung "
                          "bestätigt ist, erscheint hier der erste Auftrag. Im Spiel nur die Kamera bewegen.",
                          "Beide", "Warte auf beide Spiele", None, False, count, total, checklist, "waiting")
    actor = ROLE_NAMES.get(current["actor"], "Unbekannte Rolle")
    pending = bool(progress.get("pending") or phase == "pending" or locally_pending)
    own = current["actor"] == role
    enabled = bool(available and not pending and own and phase == "ready"
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
