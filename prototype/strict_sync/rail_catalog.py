"""T2 fixed railway lifecycle; a test catalogue, not runtime coverage evidence.

T1 retains its own frozen catalogue and behavior. The T2 signal chapter verifies
placement and observed membership; it does not prove red signals or reservations.
"""
from __future__ import annotations

import copy

CONTRACT = "guided_rail_v1"

_ROWS = (
    ("PAUSE", "aufbau", "Gemeinsam pausieren", "Die gemeinsame Simulation für den Aufbau pausieren.", "Beide bestätigten Zustände zeigen Pause bei derselben Simulationszeit."),
    ("BUILD_STATION_A", "aufbau", "Bahnhof A bauen", "Den ersten fest platzierten Personenbahnhof bauen.", "Tatsächlicher Bahnhof, Gleisanschlüsse und Firmenbetrag stimmen überein."),
    ("BUILD_STATION_B", "aufbau", "Bahnhof B bauen", "Den zweiten fest platzierten Personenbahnhof bauen.", "Tatsächlicher Bahnhof, Gleisanschlüsse und Firmenbetrag stimmen überein."),
    ("BUILD_RAIL_DEPOT", "aufbau", "Bahndepot bauen", "Das feste Bahndepot an der vorgesehenen Stelle bauen.", "Depot und tatsächliche Gleisanschlüsse sind auf beiden PCs vorhanden."),
    ("CONNECT_RAIL", "aufbau", "Gleise und Abzweig bauen", "Die vorbereiteten Anschlüsse mit festen Gleisen und einem Abzweig verbinden.", "Tatsächliche Gleise verbinden beide Bahnhöfe und das Depot."),
    ("ADD_SIGNAL_A", "aufbau", "Signal A setzen", "Das erste Signal an seinem festgelegten Gleisabschnitt setzen.", "Signalmodell, Richtung und Zugehörigkeit zum tatsächlichen Gleis stimmen überein."),
    ("ADD_SIGNAL_B", "aufbau", "Signal B setzen", "Das zweite Signal an seinem festgelegten Gleisabschnitt setzen.", "Signalmodell, Richtung und Zugehörigkeit zum tatsächlichen Gleis stimmen überein."),
    ("ADD_WAYPOINT", "aufbau", "Wegpunkt setzen", "Den festen Schienenwegpunkt setzen.", "Wegpunkt und seine tatsächliche Gleiszuordnung stimmen überein."),
    ("VERIFY_RAIL_GRAPH", "aufbau", "Gleisnetz prüfen", "Die tatsächlichen Verbindungen, Signale und den Wegpunkt prüfen.", "Das beobachtete Gleisnetz ist verbunden; Signal- und Wegpunktobjekte sind zugeordnet. Signalblockierung wird hier nicht gemessen."),
    ("BUY_TRAIN", "zug", "Lok und Wagen kaufen", "Die fest ausgewählte Lok mit einem Personenwagen im Bahndepot kaufen.", "Beide PCs melden dieselbe tatsächliche zweiteilige Zugkonfiguration und denselben Kaufbetrag."),
    ("CREATE_LINE", "zug", "Bahnlinie erstellen", "Eine leere Testlinie für den Zug erstellen.", "Die neue Linie hat keine Halte und keine zugewiesenen Fahrzeuge."),
    ("ADD_STOP_A", "zug", "Bahnhof A hinzufügen", "Bahnhof A als ersten Halt zur neuen Linie hinzufügen.", "Die tatsächliche Haltereihenfolge enthält genau Bahnhof A."),
    ("ADD_STOP_B", "zug", "Bahnhof B hinzufügen", "Bahnhof B als zweiten Halt hinzufügen.", "Die tatsächlichen Halte und Terminals sind auf beiden PCs gleich."),
    ("RENAME_TRAIN", "zug", "Zug umbenennen", "Den vereinbarten Testnamen für den Zug setzen.", "Der tatsächliche explizite Fahrzeugname stimmt überein."),
    ("TRAIN_MAINTENANCE", "zug", "Zugwartung einstellen", "Die feste Wartungsstufe für die Zugteile einstellen.", "Die tatsächliche Wartungszielstufe ist für alle Zugteile gleich; die Konfiguration bleibt sonst erhalten."),
    ("ASSIGN_TRAIN", "zug", "Zug der Linie zuweisen", "Den Zug mit festem erstem Halt der Bahnlinie zuweisen.", "Linie, Zugmitgliedschaft und erster Halt stimmen tatsächlich überein."),
    ("RESUME", "fahrt", "Gemeinsam fortsetzen", "Die gemeinsame Simulation fortsetzen und den Zug abfahren lassen.", "Beide PCs bestätigen Fortsetzen am gleichen Simulationspunkt."),
    ("VERIFY_TRAIN_MOVEMENT", "fahrt", "Zugfahrt prüfen", "Die tatsächliche Zugfahrt prüfen. Falls er noch nicht unterwegs ist, weiterlaufen lassen und erneut prüfen.", "Außerhalb des Depots wird tatsächliche Ortsänderung bei fortschreitender gemeinsamer Zeit nachgewiesen."),
    ("STOP_TRAIN", "fahrt", "Zug anhalten", "Nur den Testzug anhalten; die gemeinsame Simulation läuft weiter.", "Der tatsächliche Benutzer-Stopp des Zuges wird auf beiden PCs gesetzt."),
    ("START_TRAIN", "fahrt", "Zug weiterfahren lassen", "Den Benutzer-Stopp des Testzuges wieder aufheben.", "Der tatsächliche Benutzer-Stopp ist auf beiden PCs aufgehoben."),
    ("REVERSE_TRAIN", "fahrt", "Zug wenden", "Den Testzug wenden lassen.", "Der bestätigte Zugauftrag erzeugt die erwartete beobachtete Fahrtrichtungs- oder Fahrwegänderung."),
    ("SEND_DEPOT", "fahrt", "Zug zum Depot schicken", "Den Zug zurück zum Bahndepot schicken.", "Die tatsächliche Rückfahrt zum Depot wird bestätigt."),
    ("VERIFY_DEPOT", "fahrt", "Ankunft im Bahndepot prüfen", "Die tatsächliche Depotankunft prüfen. Falls er noch unterwegs ist, weiterlaufen lassen und erneut prüfen.", "Der Zug ist im festgelegten Bahndepot angekommen; die Prüfung verändert nichts."),
    ("PAUSE", "umbau", "Gemeinsam pausieren", "Vor dem Umbau des zurückgekehrten Zuges gemeinsam pausieren.", "Beide PCs bestätigen Pause am gleichen Simulationspunkt."),
    ("REPLACE_TRAIN", "umbau", "Zug umkonfigurieren", "Den festen Zug auf die vorgegebene dreiteilige Zusammenstellung umbauen.", "Tatsächliche Teile, Reihenfolge, Depotzugehörigkeit und Firmenänderung stimmen überein."),
    ("CLONE_TRAIN", "umbau", "Zugzusammenstellung duplizieren", "Einen zweiten Zug aus der tatsächlich beobachteten Konfiguration kaufen.", "Der neue Zug übernimmt die freigegebene Zusammenstellung. Der tatsächliche Kauf wird einmal abgerechnet."),
    ("SELL_CLONE", "umbau", "Duplizierten Zug verkaufen", "Den neu gekauften zweiten Zug im Depot verkaufen.", "Seine tatsächliche Entfernung und der gemeinsame Verkaufserlös stimmen überein."),
    ("SELL_TRAIN", "umbau", "Testzug verkaufen", "Den ursprünglichen, umgebauten Testzug im Depot verkaufen.", "Der tatsächliche Zug ist entfernt; Linie und Firmenbetrag stimmen überein."),
    ("DELETE_LINE", "abbau", "Bahnlinie löschen", "Die nun fahrzeuglose Testlinie löschen.", "Die tatsächlich leere Linie wird auf beiden PCs entfernt."),
    ("REMOVE_WAYPOINT", "abbau", "Wegpunkt entfernen", "Den getesteten Schienenwegpunkt entfernen.", "Das tatsächliche Wegpunktobjekt ist entfernt; das Gleis bleibt vorhanden."),
    ("REMOVE_SIGNAL_A", "abbau", "Signal A entfernen", "Das erste getestete Signal entfernen.", "Das tatsächliche Signalobjekt ist entfernt; das Gleis bleibt vorhanden."),
    ("REMOVE_SIGNAL_B", "abbau", "Signal B entfernen", "Das zweite getestete Signal entfernen.", "Das tatsächliche Signalobjekt ist entfernt; das Gleis bleibt vorhanden."),
    ("REMOVE_CONNECTORS", "abbau", "Verbindungsgleise abreißen", "Die festen Verbindungsgleise und den Abzweig entfernen.", "Die bestätigten Gleisobjekte werden entfernt, während die Bahnhöfe und das Depot noch bestehen."),
    ("REMOVE_RAIL_DEPOT", "abbau", "Bahndepot abreißen", "Das leere, getrennte Bahndepot entfernen.", "Depot und zugehörige tatsächliche Objekte sind entfernt."),
    ("REMOVE_STATION_B", "abbau", "Bahnhof B abreißen", "Den zweiten getrennten Bahnhof entfernen.", "Bahnhof und zugehörige tatsächliche Objekte sind entfernt."),
    ("REMOVE_STATION_A", "abbau", "Bahnhof A abreißen", "Den ersten getrennten Bahnhof entfernen.", "Die letzten zugehörigen T2-Bahnhofsobjekte sind entfernt."),
    ("RESUME", "abbau", "Gemeinsam abschließen", "Das Spiel gemeinsam fortsetzen. Anschließend den bestätigten gemeinsamen Testabschluss abwarten.", "Der Schlusszustand und der Abschluss werden auf beiden PCs bestätigt."),
)
CHAPTERS = {"aufbau": "1 · Gleisnetz, Signale und Wegpunkt", "zug": "2 · Lok, Wagen und Linie",
            "fahrt": "3 · Zugbetrieb und Depotfahrt", "umbau": "4 · Umbau, Duplizieren und Verkauf",
            "abbau": "5 · Gemeinsamer Abbau und Abschluss"}


def _step(number, row):
    action, chapter, label, instruction, verification = row
    actor = "a" if number % 2 else "b"
    role = "Host" if actor == "a" else "Freund"
    finance = ("debit" if action in ("BUY_TRAIN", "CLONE_TRAIN") else
               "credit" if action in ("SELL_TRAIN", "SELL_CLONE") else
               "observed" if action.startswith(("BUILD_", "REMOVE_")) or action in
                   ("CONNECT_RAIL", "ADD_SIGNAL_A", "ADD_SIGNAL_B", "ADD_WAYPOINT", "REPLACE_TRAIN") else "none")
    value = {"step": number, "id": f"rail_{number:02d}_{action.lower()}", "actor": actor,
             "action": action, "title": f"{role}: {label}", "action_label": label,
             "instruction": f"{role}: {instruction}", "verification": verification,
             "chapter": chapter, "chapter_title": CHAPTERS[chapter],
             "command": {"op": "RAIL_ACTION", "step": number}, "finance": finance,
             "expected": "applied", "read_only": action.startswith("VERIFY_")}
    if action in ("PAUSE", "RESUME"):
        value["pause"] = action == "PAUSE"
    return value


STEPS = tuple(_step(index + 1, row) for index, row in enumerate(_ROWS))


def get_step(number):
    if type(number) is not int or not 1 <= number <= len(STEPS):
        raise ValueError("rail step outside the versioned catalogue")
    return copy.deepcopy(STEPS[number - 1])


def catalogue():
    return {"contract": CONTRACT, "steps": copy.deepcopy(list(STEPS)),
            "normal_game_tools_connected": False,
            "scope": "fixed_launcher_railway_construction_train_lifecycle_and_removal",
            "not_covered": ["dynamic_signal_red_block_reservation", "free_placement", "native_ui_capture",
                            "cargo_policy", "terrain", "full_world", "save_rejoin", "same_batch_rail_conflicts",
                            "native_clone_button"]}
