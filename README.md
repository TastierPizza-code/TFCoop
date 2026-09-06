# TFCoop für Transport Fever 2

**Alpha5.7-Bautest / v0.5.7 korrigiert die Straßenverbindungen im automatischen 240-Runden-Test und die Verarbeitung von Bauantworten.** Beide Alpha5.6-Berichte bestätigen denselben Zustand bis zum Straßenbau; anschließend wurde das Depot auf einem PC abgelehnt, während auf dem anderen ein Statuslesefehler die Bauantwort verdeckte.

Depot und Haltestellen werden mit getrennten Anschlussknoten gebaut. Ein eigener gemeinsamer Bauauftrag verbindet diese mit der Teststraße; neue Kanten werden am tatsächlichen Graphen identifiziert und geprüft. Die lokalen Tests setzen keine automatische Verbindung mehr voraus. Kurzzeitige Dateisperren nach einem Callback werden ohne erneutes Senden überbrückt; ursprüngliche Ablehnungen und verfügbare Engine-Fehlerdetails bleiben erhalten.

**Die Änderungen müssen im echten gemeinsamen Bautest noch bestätigt werden.** Freies gleichzeitiges Bauen, Cursor und normale gemeinsame Pause-Tasten sind nicht freigeschaltet. Die Soloberichte belegen insbesondere kein vollständig synchrones Multiplayer-Spiel.

## Download und Start

1. Auf beiden PCs TF2, laufenden Test und alten Launcher schließen. Den vorhandenen Launcher ab Alpha5.2 normal öffnen und das automatische Update auf **Alpha5.7-Bautest** abwarten. Bei erster Einrichtung einmal [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python werden nicht benötigt.
2. **Bisherige Installation wiederherstellen** verwenden, insbesondere nach der Solo-Diagnose. Eigene Spiel-/Saveordner prüfen und den ersten Reiter **Bautest (experimentell)** verwenden. Host und Mitspieler wählen ihre Rollen, dieselbe Host-IP und einen neuen gemeinsamen Sitzungscode.
3. Beide **Test vorbereiten und installieren**, dann **Verbinden & Test bereitstellen**. Nach der Startfreigabe TF2 starten und jeweils die neu angezeigte `TF2-Koop-Messtest-….sav` laden. Unter **OPTIONEN AUSWÄHLEN → Mods** ausschließlich **TF2 Strict Sync - automatischer Bautest (Alpha5.7)** und **Legacy Fahrzeuge** aktivieren; Diagnosemod und alte Koop-Mods ausschalten.
4. Kamera bewegen ist erlaubt; nicht selbst bauen, pausieren oder die Geschwindigkeit ändern. Nach Abbruch oder 240 Runden auf **beiden PCs** **Testbericht als ZIP …** exportieren und beide ZIPs privat zur Auswertung weitergeben. Anschließend Test und TF2 beenden und wiederherstellen. Alle Schritte stehen in der [Anleitung](prototype/ANLEITUNG.md).

Der neue Ablauf enthält drei ausdrückliche Straßenverbindungen und 211 Fortschrittsschritte, zusammen 42,2 Sekunden Enginezeit. Die Bauannahme und Fahrzeugfahrt müssen im Spiel noch bestätigt werden. Die ursprüngliche Depot-Ablehnungsbegründung fehlt in den alten Berichten; die falsche Annahme einer automatischen Verbindung ist unabhängig davon im Code festgestellt. Zweck und Grenzen: [Bautest](prototype/BUILD_TEST.md), [Prüfstand](prototype/VERIFICATION.md).

Der bisherige private Ausgangsspielstand mit der sehr großen Karte bleibt lokal erhalten. Falls die automatische Übernahme nicht gelingt, **Testspielstand übernehmen …** verwenden und aus dem alten privaten Paket `Testspielstand/initial.sav` auswählen; die zugehörige `.sav.lua` muss daneben liegen. Das öffentliche Release enthält keine Spielstände oder Berichte. Der Updater lädt solche privaten Dateien nicht auf GitHub hoch und behält bei einem fehlgeschlagenen Download eine vorhandene Programmversion.

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
