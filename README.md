# TFCoop für Transport Fever 2

**Alpha5.20-Testbegleiter / v0.5.20** ergänzt **T2 · Schiene** neben dem erhaltenen **T1 · Straße**. Host und Freund bauen eine feste Bahnstrecke, setzen Signale und Wegpunkt und prüfen den Zugbetrieb bis zum Umbau, Verkauf und Abbau. Der Launcher zeigt die aktuelle Rolle und einen Aktionsknopf. Fortschritt braucht verglichene Ergebnisse beider Spiele. T2 ist vorbereitet; sein tatsächlicher Zwei-PC-Nachweis steht noch aus. Die normale freie Spieloberfläche folgt später.

## Download und Start

1. TF2 und den alten Test schließen. Den vorhandenen Launcher neu öffnen und aktualisieren lassen. Erstmalig: [TFCoop-Windows.zip](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip) vollständig entpacken und `TF2-Coop.exe` starten.
2. **T2 · Schiene** und Host/Freund wählen, **Test vorbereiten**, anschließend **Verbinden**. Die private gemerkte Verbindung und passende saubere große Ausgangskarte werden weiterverwendet.
3. TF2 über Steam starten und den jeweils genau angezeigten frischen Spielstand laden. Die kurze Vorbereitung abwarten; danach den einzelnen Host-/Freund-Aufträgen im Launcher folgen.
4. Am Ende beide Berichte speichern. Bei Fehlern bleiben die bisherigen bestätigten Schritte im Bericht erhalten.

[Kurze Anleitung](prototype/ANLEITUNG.md) · [T2-Schienenversuch](prototype/docs/RAIL_TEST.md) · [T1-Straßentest](prototype/docs/GUIDED_TEST.md) · [Nachweischeckliste](prototype/docs/GAMEPLAY_CHECKLIST.md) · [Alle Befehlsfamilien](prototype/docs/COMMAND_COVERAGE_PLAN.md)

Der tatsächliche [Alpha5.19-Lauf auf zwei PCs](prototype/docs/ALPHA519_EVIDENCE.md) bestätigt alle 26 festen Aufträge mit 241 bytegleichen Journalzeilen: zusätzliches Straßenfahrzeug, schrittweise bearbeitete Linie, Namen/Farbe, Wartung, Zuweisung, Fahrt, Anhalten/Starten, Wenden, Depotfahrt und Verkauf. Gleise/Signale/Züge, freie Platzierungen, native UI-Pause, Cursor/Blaupausen und Speichern/Wiederbeitritt bleiben offen. Die Nachweise gelten für die aufgezeichnete feste Szene und die Launcher-Bedienung.

Die akzeptierten [Alpha5.15-Eingaben und ihr Tempo](prototype/docs/ACCEPTED_INPUT_BASELINE.md), [Alpha5.12-Dauerlauf](prototype/docs/ACCEPTED_BASELINE.md) sowie die [beiden Alpha5.16-Depotläufe](prototype/docs/ALPHA516_EVIDENCE.md) bleiben erhalten. Alle fünf bisherigen Modi sind unter den weiteren Tests auswählbar; ihre Abläufe und die akzeptierte Taktung werden nicht verkürzt oder ersetzt.

Das öffentliche Release enthält keine Spielstände, Berichte, Sitzungsschlüssel oder originalen Spieldateien. Updates prüfen Paketdateien; Verbindungsdaten, Saves und Sicherungen bleiben lokal.

## Entwicklung und Veröffentlichungen

Der aktuelle Launcher startet aus dem Quellcode mit `py -3.10 probe_launcher.py` beziehungsweise `Start-Coop.cmd`. Python 3.10 oder neuer mit Tkinter ist erforderlich. Quellcode-Starts laden keine Updates. Die älteren Module unter `coop/`, `mod/` und `upstream/` bleiben als Vergleich und für gemeinsame Hilfsfunktionen erhalten; `prototype/` enthält den aktuellen Test.

Native Test-DLLs lassen sich mit Visual Studio 2022 Build Tools (C++ x64) über `prototype/build-native.cmd` bauen. Der native Adapter ist an einen bestimmten TF2-Build gebunden und verweigert unbekannte Builds. Keine originalen Spielbinärdateien werden mitgeliefert.

Portable Veröffentlichung auf Windows:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
prototype\build-native.cmd
.venv\Scripts\python.exe tools\build_probe_package.py --save "D:\PrivateTestdaten\initial.sav"
```

Der Paketbau liest das private Spielstandpaar ausschließlich für seine Prüfsummen. Standardmäßig enthält die ZIP keinen Spielstand. Der abschließende eingefrorene Selbsttest startet nur verborgene Modellprozesse, kein TF2 und kein Fenster.

Versionsnummern stehen in `prototype/release_version.py`; Modname und Anleitung müssen dazu passen. Mit dem fertigen öffentlichen Archiv und seinem bestandenen Selbsttest veröffentlicht:

```powershell
py -3.10 tools\publish_release.py --archive "dist\<Build>\TFCoop-Windows.zip" --self-check "dist\<Build>\self-check.json" --publish
```

Ohne `--publish` wird nur lokal geprüft. Der Publisher verwendet die vorhandene GitHub-Anmeldung von Git Credential Manager, überträgt eine geprüfte Quellcodeauswahl, erstellt zunächst ein Draft-Release und gibt es erst nach dem Vergleich der hochgeladenen SHA-256 frei. Veröffentlichung erfolgt im festgelegten Repository `TastierPizza-code/TFCoop`. Details: [GitHub-Updates](prototype/docs/GITHUB_UPDATES.md).

Testabdeckung und Einschränkungen: [Prototyp-Dokumentation](prototype/README.md). Herkunft und Lizenzen: [Third-party notices](THIRD_PARTY_NOTICES.md).
