# TFCoop für Transport Fever 2

**Alpha5.9-Bautest / v0.5.9 verbessert das Lesen nativer Spielobjekte und verwendet ein neues sauberes Savepaar der bisherigen sehr großen Karte.** Die benötigten Testmods sind darin bereits ausgewählt. Beide Spieler übernehmen dieses Paar einmal privat; danach bleibt es für spätere Updates lokal gespeichert.

Ein echter lokaler Alpha5.8-Lauf hat alle 240 Runden einschließlich Verbindungsbau, Fahrzeugkauf, Linienfahrt und der vorgegebenen Pausen bestanden. Ein zweiter, frisch gestarteter TF2-Prozess spielte dieselben Befehle nach: Bis Frame 99 stimmten alle bestätigten Beobachtungen überein, dann stoppte ein vorübergehender Lesefehler an einer Konstruktionsliste den Versuch. Das war ein nacheinander ausgeführter Test auf einem PC, kein gemeinsamer Netzwerktest.

Alpha5.9 hält native Elternobjekte während einer vollständigen Leseoperation fest. Dadurch können deren geliehene Listen nicht allein wegen fehlender Lua-Referenzen zu früh freigegeben werden. Das ist eine gezielte Korrektur einer gefundenen Lücke; ob genau diese Ursache den echten Fehler ausgelöst hat und ob der Wiederholungslauf vollständig durchläuft, muss noch im Spiel geprüft werden. Freies gleichzeitiges Bauen, Cursor und normale gemeinsame Pause-Tasten sind nicht freigeschaltet.

## Download und Start

1. Auf beiden PCs TF2, laufenden Test und alten Launcher schließen. Den vorhandenen Launcher ab Alpha5.2 normal öffnen und das automatische Update auf **Alpha5.9-Bautest** abwarten. Bei erster Einrichtung einmal [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python werden nicht benötigt.
2. **Bisherige Installation wiederherstellen** verwenden. Für Alpha5.9 einmal das neu bereitgestellte private Paar `Testspielstand/initial.sav` und `Testspielstand/initial.sav.lua` unverändert nebeneinander entpacken. Auf beiden PCs **Testspielstand übernehmen …** verwenden und diese `initial.sav` auswählen. Die Basis aus alten Paketen passt nicht mehr.
3. Eigene Spiel-/Saveordner prüfen und **Bautest (experimentell)** verwenden. Rollen, dieselbe Host-IP und einen neuen gemeinsamen Sitzungscode wählen. Beide **Test vorbereiten und installieren**, dann **Verbinden & Test bereitstellen**. Nach der Startfreigabe TF2 starten und jeweils die neu angezeigte `TF2-Koop-Messtest-….sav` laden. **TF2 Strict Sync - automatischer Bautest (Alpha5.9)** und **Legacy Fahrzeuge** sind bereits ausgewählt; erneutes Umstellen ist nicht nötig.
4. Kamera bewegen ist erlaubt; nicht selbst bauen, pausieren oder die Geschwindigkeit ändern. Nach Abbruch oder 240 Runden auf **beiden PCs** **Testbericht als ZIP …** exportieren und beide ZIPs privat zur Auswertung weitergeben. Anschließend Test und TF2 beenden und wiederherstellen. Alle Schritte stehen in der [Anleitung](prototype/ANLEITUNG.md).

Der unveränderte Ablauf enthält drei ausdrückliche Straßenverbindungen und 211 Fortschrittsschritte, zusammen 42,2 Sekunden Enginezeit. Ein erfolgreicher lokaler Ablauf bestätigt diese geprüften Vorgänge, keine vollständige oder dauerhafte Synchronität der Spielwelt. Der echte Folgetest der Alpha5.9-Korrektur steht noch aus. Zweck und Grenzen: [Bautest](prototype/BUILD_TEST.md), [Prüfstand](prototype/VERIFICATION.md).

Die neue Basis verwendet weiterhin die bisherige sehr große Karte. Dem Freund müssen beide neuen Dateien einmal privat weitergegeben werden; sie werden anhand der im Launcherpaket festgelegten Prüfsummen geprüft. Nach der Übernahme genügt der lokale Speicher, solange spätere Versionen dieselbe Basis verwenden. Das öffentliche Release enthält keine Spielstände oder Berichte. Der Updater lädt solche privaten Dateien nicht auf GitHub hoch und behält bei einem fehlgeschlagenen Download eine vorhandene Programmversion.

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
