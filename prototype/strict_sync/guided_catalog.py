"""Versioned launcher-only fixed-action test catalogue, never runtime evidence.

Only compared actual receipts can complete these steps. Labels describe what the
user authorizes in the launcher; normal TF2 tools are not connected by this mode.
"""
from __future__ import annotations

import copy

CONTRACT = "guided_suite_v1"

_ROWS = (
    ("host_pause", "a", "PAUSE", "Host pausiert gemeinsam", "Gemeinsam pausieren", "Host: Jetzt gemeinsam pausieren. Danach bleibt der Aufbau für beide angehalten."),
    ("friend_buy_bus", "b", "BUY_BUS", "Freund kauft ein Fahrzeug", "Fahrzeug kaufen", "Freund: Ein fest ausgewähltes Straßenfahrzeug im vorbereiteten Depot kaufen."),
    ("host_create_line", "a", "CREATE_LINE", "Host erstellt eine Linie", "Leere Linie erstellen", "Host: Eine neue, zunächst leere Testlinie erstellen."),
    ("friend_add_stop_a", "b", "ADD_STOP_A", "Freund fügt den ersten Halt hinzu", "Halt A hinzufügen", "Freund: Den ersten vorbereiteten Halt einzeln zur neuen Linie hinzufügen."),
    ("host_add_stop_b", "a", "ADD_STOP_B", "Host fügt den zweiten Halt hinzu", "Halt B hinzufügen", "Host: Den zweiten vorbereiteten Halt einzeln zur neuen Linie hinzufügen."),
    ("friend_remove_stop_b", "b", "REMOVE_STOP_B", "Freund entfernt einen einzelnen Halt", "Halt B entfernen", "Freund: Nur den zweiten Halt aus der Testlinie entfernen. Der erste Halt muss erhalten bleiben."),
    ("host_restore_stop_b", "a", "RESTORE_STOP_B", "Host fügt den Halt erneut hinzu", "Halt B erneut hinzufügen", "Host: Den zuvor entfernten Halt wieder einzeln als zweiten Halt hinzufügen."),
    ("friend_rename_line", "b", "RENAME_LINE", "Freund benennt die Linie um", "Linie umbenennen", "Freund: Den festen Testnamen für die neue Linie setzen."),
    ("host_color_line", "a", "COLOR_LINE", "Host ändert die Linienfarbe", "Linienfarbe ändern", "Host: Die feste Testfarbe setzen und das bestätigte Ergebnis abwarten."),
    ("friend_rename_bus", "b", "RENAME_BUS", "Freund benennt das Fahrzeug um", "Fahrzeug umbenennen", "Freund: Den festen Testnamen für das gekaufte Fahrzeug setzen."),
    ("host_maintenance", "a", "MAINTENANCE", "Host ändert die Wartung", "Wartung einstellen", "Host: Die vereinbarte Wartungsstufe des Testfahrzeugs einstellen."),
    ("friend_assign_bus", "b", "ASSIGN_BUS", "Freund weist das Fahrzeug zu", "Der Testlinie zuweisen", "Freund: Das gekaufte Fahrzeug der neuen Linie mit festem ersten Halt zuweisen."),
    ("host_resume", "a", "RESUME", "Host setzt das Spiel fort", "Gemeinsam fortsetzen", "Host: Gemeinsam fortsetzen. Das Fahrzeug soll aus dem Depot auf die Strecke fahren."),
    ("friend_verify_movement", "b", "VERIFY_MOVEMENT", "Freund prüft die Fahrt", "Fahrt prüfen", "Freund: Den tatsächlichen Fahrtzustand prüfen. Solange die Fahrt noch nicht bestätigt wurde, kurz weiterlaufen lassen und erneut prüfen."),
    ("host_stop_bus", "a", "STOP_BUS", "Host hält das Fahrzeug an", "Fahrzeug anhalten", "Host: Nur das Testfahrzeug anhalten. Die gemeinsame Simulation läuft weiter."),
    ("friend_start_bus", "b", "START_BUS", "Freund lässt das Fahrzeug weiterfahren", "Fahrzeug starten", "Freund: Das angehaltene Testfahrzeug wieder starten."),
    ("friend_pause", "b", "PAUSE", "Freund pausiert gemeinsam", "Gemeinsam pausieren", "Freund: Jetzt die gemeinsame Simulation pausieren."),
    ("host_reverse_stops", "a", "REVERSE_STOPS", "Host verschiebt die Halte", "Haltereihenfolge ändern", "Host: Die beiden einzelnen Halte in umgekehrte Reihenfolge bringen."),
    ("friend_restore_stops", "b", "RESTORE_STOPS", "Freund stellt die Haltereihenfolge her", "Haltereihenfolge wiederherstellen", "Freund: Die beiden Halte wieder in die ursprüngliche Reihenfolge bringen."),
    ("host_line_rules", "a", "LINE_RULES", "Host ändert die Linienregeln", "Lade- und Wartebedingungen setzen", "Host: Die fest vorgegebenen Lade- und Wartebedingungen der Testlinie einstellen."),
    ("friend_reverse_bus", "b", "REVERSE_BUS", "Freund wendet das Fahrzeug", "Fahrzeug wenden", "Freund: Das Testfahrzeug wenden. Beide bestätigten Fahrzeugzustände werden verglichen."),
    ("host_resume_again", "a", "RESUME", "Host setzt erneut fort", "Gemeinsam fortsetzen", "Host: Gemeinsam fortsetzen, damit das Fahrzeug wieder fahren kann."),
    ("friend_send_depot", "b", "SEND_DEPOT", "Freund schickt das Fahrzeug zum Depot", "Zum Depot schicken", "Freund: Das Testfahrzeug zur Rückfahrt in das vorbereitete Depot schicken."),
    ("host_verify_depot", "a", "VERIFY_DEPOT", "Host prüft die Rückkehr", "Ankunft im Depot prüfen", "Host: Die tatsächliche Ankunft im Depot prüfen. Wenn es noch unterwegs ist, weiterlaufen lassen und erneut prüfen."),
    ("friend_sell_bus", "b", "SELL_BUS", "Freund verkauft das Fahrzeug", "Fahrzeug verkaufen", "Freund: Das zurückgekehrte Testfahrzeug verkaufen. Bestand und tatsächlicher Geldbetrag werden verglichen."),
    ("host_delete_line", "a", "DELETE_LINE", "Host entfernt die Testlinie", "Testlinie löschen", "Host: Die jetzt fahrzeuglose Testlinie löschen. Anschließend wird der gemeinsame Abschluss geprüft."),
)


def _step(number, row):
    key, actor, action, title, label, instruction = row
    result = {"step": number, "id": key, "actor": actor, "action": action,
              "title": title, "action_label": label, "instruction": instruction,
              "command": {"op": "GUIDED_ACTION", "step": number},
              "expected": "applied", "read_only": action in ("VERIFY_MOVEMENT", "VERIFY_DEPOT")}
    if action in ("PAUSE", "RESUME"):
        result["pause"] = action == "PAUSE"
    return result


STEPS = tuple(_step(index + 1, row) for index, row in enumerate(_ROWS))


def get_step(number):
    """Return a defensive copy; booleans must never identify step one."""
    if type(number) is not int or not 1 <= number <= len(STEPS):
        raise ValueError("guided step outside the versioned catalogue")
    return copy.deepcopy(STEPS[number - 1])


def catalogue():
    return {"contract": CONTRACT, "steps": copy.deepcopy(list(STEPS)),
            "normal_game_tools_connected": False,
            "scope": "fixed_launcher_road_vehicle_and_line_lifecycle",
            "not_covered": ["railway_signal_train", "free_placement", "native_ui_capture",
                            "terrain", "full_world", "save_rejoin", "same_batch_new_lifecycle_conflicts"]}
