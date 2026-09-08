# TFCoop für Transport Fever 2

**Korrektur in Alpha5.15:** Der Abbruch beim Vorbereiten des kurzen Tests ist behoben. Vorbereitung, Installer und Startprüfung verwenden nun denselben Konfigurationsvertrag. Beide Launcher aktualisieren und frisch vorbereiten; keine neuen Saves erforderlich.

**Alpha5.15-Eingabetest / v0.5.15 ist nach dem tatsächlichen Zwei-PC-Lauf auch im Tempo akzeptiert.** Beide Weltjournale mit 133 Einträgen sind identisch; der kurze Aufbau, gegenseitige Pause/Fortsetzen und Abschluss passen zusammen. Die aktive Fahrt erreicht ungefähr 0,94x, der Aufbau dauert 12,5 Sekunden. Der Nutzer bewertet die Fahrt wieder als sehr gut und möchte sie so beibehalten. Paket, Quellstand und private Belege sind als Referenz gesichert. [Auswertung und Grenzen](prototype/docs/ACCEPTED_INPUT_BASELINE.md).

**Alpha5.12 bleibt eingefroren** und als **Referenztest aus Alpha5.12** auswählbar. Sein längerer automatischer Zwei-PC-Lauf hatte 270 identische Journaleinträge und etwa 0,962x Fahrttempo. Die spätere Regression aus Alpha5.13 wurde gezielt bearbeitet; der nun akzeptierte Eingabeweg enthält keine zusätzlichen leeren Abfragerunden mehr. Beide Referenzen bleiben erhalten; weitere Tempoexperimente werden zurückgestellt. Siehe [Alpha5.12](prototype/docs/ACCEPTED_BASELINE.md) und [Alpha5.13-Evidenz](prototype/docs/ALPHA513_EVIDENCE.md).

## Download und gemeinsamer Versuch

1. Beide Test, TF2 und Launcher schließen. Den vorhandenen Launcher ab Alpha5.2 normal öffnen und das Update auf **Alpha5.15-Eingabetest** abwarten. Bei erster Einrichtung [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python sind nicht nötig.
2. **Bisherige Installation wiederherstellen** verwenden. Die sehr große Karte und der passende private Savecache bleiben gültig. **Keiner der bisherigen Teilnehmer braucht einen neuen Spielstandimport.**
3. Im Reiter **Gemeinsamer Eingabetest (experimentell)** auf beiden PCs **Fahrt und Eingaben · kurzer Aufbau** wählen. Rollen, dieselbe Host-IP und einen frischen gemeinsamen Sitzungscode festlegen. Beide **Test vorbereiten und installieren**, danach **Verbinden & Test bereitstellen**.
4. Nach der Startfreigabe TF2 über Steam starten und jeweils die neu angezeigte `TF2-Koop-Messtest-….sav` laden. **TF2 Strict Sync - gemeinsamer Eingabetest (Alpha5.15)** und **Legacy Fahrzeuge** sind bereits ausgewählt. Die zufälligen Dateinamen dürfen verschieden sein.
5. Nach zehn Aufbaurunden zunächst eine Minute fahren lassen. Dann gegenseitig **Gemeinsam pausieren** und **Gemeinsam fortsetzen** im Launcher auslösen; jede Bestätigung abwarten. Eine Pause mindestens 45 Sekunden halten und **Lange Pause erfasst** abwarten. Noch eine Minute fahren lassen, dann **Messung gemeinsam abschließen**. Die normalen Pause-/Tempotasten und Bauwerkzeuge im Spiel noch nicht verwenden; Kamera bewegen ist möglich.
6. Auf **beiden PCs** **Testbericht als ZIP …** exportieren und privat zur Auswertung schicken. Danach Test und TF2 beenden und die Installation wiederherstellen. Die [Anleitung](prototype/ANLEITUNG.md) enthält die genaue Bedienprobe für beide Spieler.

Der Host sammelt Wünsche beider Spieler und legt vor Änderungen eine frische gemeinsame Grenze fest. Erst passende Ausführungsergebnisse beider PCs bestätigen einen Wunsch. In Pause bleibt die Eingabeverarbeitung ohne Fortschrittsschritt aktiv. Gegensätzliche Wünsche derselben Sammelrunde enden in Pause. Lokale Annahme und gemeinsame Bestätigung stehen getrennt im Launcher. Ein reguläres Ende bedeutet nicht automatisch, dass alle Bedienproben ausgeführt wurden.

**Eingabetest aus Alpha5.13 · vollständiger Aufbau** behält seinen bisherigen Ablauf. **Referenztest aus Alpha5.12** erhält den automatischen 120-Sekunden-Dauertest und seine ursprüngliche strenge Tempoauswertung. **Vergleichstest aus Alpha5.11** erhält die zwölf kürzeren Fahrtabschnitte. Alle drei behalten ihre 240 Aufbaurunden. Ein Moduswechsel braucht eine frische Vorbereitung auf beiden PCs. Die alten Releases bleiben erhalten, der Updater führt keinen Downgrade aus.

Der neue Versuch ist der Pause-Teil der [Eingabeetappe](prototype/docs/NEXT_MILESTONE.md). Ein begrenzter manueller Bauauftrag folgt danach. Freies gleichzeitiges Bauen, Cursor, normale gemeinsame Pause-Tasten, Speichern/Fortsetzen und Steam-Einladungen sind noch nicht angeschlossen. Vollständige oder dauerhafte Synchronität der ganzen Welt bleibt ungeprüft. Ablauf und Grenzen: [Bau- und Eingabeversuch](prototype/BUILD_TEST.md), [Prüfstand](prototype/VERIFICATION.md).

Das öffentliche Release enthält keine Spielstände, Berichte, Sitzungsschlüssel oder originalen Spieldateien. Der Updater prüft Paket und Prüfsummen und verwendet den bestehenden passenden Savecache. Private Sicherungen und Berichtdaten werden nicht auf GitHub hochgeladen.

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
