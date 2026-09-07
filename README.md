# TFCoop für Transport Fever 2

**Alpha5.10-Bautest / v0.5.10 behebt einen mit Alpha5.9 eingeführten Startfehler.** Das saubere Savepaar der bisherigen sehr großen Karte bleibt dasselbe wie in Alpha5.9. Wer es bereits übernommen hat, muss es nicht erneut importieren. Die benötigten Testmods sind darin bereits ausgewählt.

**Die echte Alpha5.10-Nachprüfung ist vollständig durchgelaufen:** Ein TF2-Prozess zeichnete zwölf Befehle und 240 Schritte einschließlich Straßenverbindungen, Fahrzeugkauf, Linienfahrt und vorgegebener Pausen auf. Ein zweiter, frisch gestarteter Prozess spielte die Aufzeichnung vom selben Ausgangsspielstand nach. Nach jeder Aktion stimmten Ergebnisse und gemessene Zustände überein. Beide Prozesse wurden regulär beendet und die vorherige Installation wiederhergestellt. Das waren nacheinander ausgeführte Läufe auf einem PC, kein gemeinsamer Netzwerktest.

Der in Alpha5.9 eingeführte Schutz hält native Elternobjekte während einer vollständigen Leseoperation fest. Seine Rückgabe verwendete jedoch eine Lua-Hilfsfunktion, deren Verhalten TF2 verändert: `table.unpack` ignoriert dort die angeforderten Bereichsgrenzen. Dadurch kam beim Spielstart ein Wahrheitswert statt des Zustands zurück. Alpha5.10 reicht die Rückgabewerte direkt weiter und behält den Lebensdauerschutz bei. Freies gleichzeitiges Bauen, Cursor und normale gemeinsame Pause-Tasten sind nicht freigeschaltet.

## Download und Start

1. Auf beiden PCs TF2, laufenden Test und alten Launcher schließen. Den vorhandenen Launcher ab Alpha5.2 normal öffnen und das automatische Update auf **Alpha5.10-Bautest** abwarten. Bei erster Einrichtung einmal [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python werden nicht benötigt.
2. **Bisherige Installation wiederherstellen** verwenden. Das seit Alpha5.9 bereitgestellte private Paar `Testspielstand/initial.sav` und `Testspielstand/initial.sav.lua` bleibt gültig. Falls noch nicht übernommen, beide Dateien unverändert nebeneinander entpacken und über **Testspielstand übernehmen …** diese `initial.sav` auswählen. Ein vorhandener passender Cache genügt; die Basis aus Paketen vor Alpha5.9 passt nicht.
3. Eigene Spiel-/Saveordner prüfen und **Bautest (experimentell)** verwenden. Rollen, dieselbe Host-IP und einen neuen gemeinsamen Sitzungscode wählen. Beide **Test vorbereiten und installieren**, dann **Verbinden & Test bereitstellen**. Nach der Startfreigabe TF2 starten und jeweils die neu angezeigte `TF2-Koop-Messtest-….sav` laden. **TF2 Strict Sync - automatischer Bautest (Alpha5.10)** und **Legacy Fahrzeuge** sind bereits ausgewählt; erneutes Umstellen ist nicht nötig.
4. Kamera bewegen ist erlaubt; nicht selbst bauen, pausieren oder die Geschwindigkeit ändern. Nach Abbruch oder 240 Runden auf **beiden PCs** **Testbericht als ZIP …** exportieren und beide ZIPs privat zur Auswertung weitergeben. Anschließend Test und TF2 beenden und wiederherstellen. Alle Schritte stehen in der [Anleitung](prototype/ANLEITUNG.md).

Der bestätigte Ablauf enthält drei ausdrückliche Straßenverbindungen, 211 Fortschrittsschritte mit zusammen 42,2 Sekunden Enginezeit und 29 Pausenrunden. Der lokale Erfolg bestätigt die dabei gemessenen Vorgänge, keine vollständige oder dauerhafte Synchronität der Spielwelt. Als Nächstes folgt derselbe Bautest auf beiden PCs über das Netzwerk. Zweck und Grenzen: [Bautest](prototype/BUILD_TEST.md), [Prüfstand](prototype/VERIFICATION.md).

Die seit Alpha5.9 verwendete Basis erhält die bisherige sehr große Karte. Dem Freund müssen beide Dateien einmal privat weitergegeben werden, falls er sie noch nicht hat; sie werden anhand der im Launcherpaket festgelegten Prüfsummen geprüft. Nach der Übernahme genügt der lokale Speicher, auch für Alpha5.10. Das öffentliche Release enthält keine Spielstände oder Berichte. Der Updater lädt solche privaten Dateien nicht auf GitHub hoch und behält bei einem fehlgeschlagenen Download eine vorhandene Programmversion.

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
