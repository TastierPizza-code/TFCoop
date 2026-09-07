# TFCoop für Transport Fever 2

**Alpha5.11-1x-Test / v0.5.11 bereitet den gemeinsamen Versuch mit ungleichen Wartezeiten und gleichmäßig freigegebenen Simulationsschritten vor.** Nach dem bisherigen automatischen Bau folgen zwölf Fahrtabschnitte mit 1x als Ziel. Die bisherige sehr große Karte und das saubere private Savepaar aus Alpha5.9 bleiben unverändert; ein vorhandener Cache genügt.

**Bisherige echte Evidenz:** Alpha5.10 bestand einen vollständigen Aufnahme- und Wiederholungslauf in zwei nacheinander gestarteten TF2-Prozessen auf einem PC. Zwölf Befehle und 240 Schritte lieferten nach jeder Aktion gleiche gemessene Ergebnisse. **Die neuen Fahrtabschnitte aus Alpha5.11 sind bisher nur ohne TF2 mit Testmodellen und nachgebildeten Schnittstellen geprüft. Ihr echter Zwei-PC-Versuch steht aus.**

## Download und gemeinsamer Versuch

1. Auf beiden PCs Test, TF2 und Launcher schließen. Den vorhandenen Launcher ab Alpha5.2 normal öffnen und das automatische Update auf **Alpha5.11-1x-Test** abwarten. Bei erster Einrichtung einmal [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python werden nicht benötigt.
2. **Bisherige Installation wiederherstellen** verwenden. Das seit Alpha5.9 bereitgestellte private Paar `Testspielstand/initial.sav` und `initial.sav.lua` bleibt gültig. Nur falls es noch fehlt: beide Dateien nebeneinander entpacken und über **Testspielstand übernehmen …** die `initial.sav` auswählen. Ein vorhandener passender Cache braucht keinen erneuten Import.
3. Im Reiter **Aufbau + 1x-Test (experimentell)** eigene Ordner, Rollen, dieselbe Host-IP und einen frischen gemeinsamen Sitzungscode festlegen. Beide **Test vorbereiten und installieren**, dann **Verbinden & Test bereitstellen**. Nach der Startfreigabe TF2 starten und jeweils die neu angezeigte `TF2-Koop-Messtest-….sav` laden. **TF2 Strict Sync - automatischer Bautest (Alpha5.11)** und **Legacy Fahrzeuge** sind bereits ausgewählt.
4. Kamera bewegen und die Fahrzeugfahrt beobachten; nicht selbst bauen, pausieren oder die Geschwindigkeit ändern. Nach den 240 Aufbaurunden läuft der neue Versuch automatisch weiter. Erst nach Abschluss aller zwölf Fahrtabschnitte oder einem Abbruch auf **beiden PCs** **Testbericht als ZIP …** exportieren. Beide ZIPs und eure Beobachtung der Bewegung privat zur Auswertung schicken. Danach Test und TF2 beenden und die Installation wiederherstellen. Die [Anleitung](prototype/ANLEITUNG.md) führt beide Spieler durch den Ablauf.

Der Aufbau umfasst 211 Fortschrittsschritte und 29 Pausenschritte, zusammen 42,2 Sekunden Enginezeit. Danach folgen zwölf Abschnitte mit jeweils 25 Schritten à 0,2 Sekunden, also weitere 60 Sekunden Enginezeit: drei ohne Zusatzwartezeit, sechs mit absichtlichen Wartezeiten von abwechselnd Host und Mitspieler und drei weitere ohne Zusatzwartezeit.

An jedem Abschnittsanfang und -ende werden die erfassten Weltzustände verglichen. Dazwischen prüft die native Steuerung die Uhr und Bestätigung jedes einzelnen Schritts. Die 1x-Auswertung bewertet gemessene Freigabe- und Bestätigungsabstände innerhalb dieser Abschnitte. Sie misst keine gerenderten Bilder und bestätigt weder sichtbare Flüssigkeit noch durchgängiges 1x-Tempo über die dazwischenliegenden gemeinsamen Haltepunkte. Die absichtlichen Wartezeiten sind keine Messung eurer Netzwerk-Latenz.

Freies gleichzeitiges Bauen, Cursor und normale gemeinsame Pause-Tasten sind noch nicht freigeschaltet. Vollständige oder dauerhafte Synchronität der Spielwelt bleibt ungeprüft. Zweck, Ablauf und Grenzen: [Bau- und Fahrtversuch](prototype/BUILD_TEST.md), [Prüfstand](prototype/VERIFICATION.md).

Das öffentliche Release enthält keine Spielstände oder Berichte. Die große Ausgangskarte muss nur einmal privat als vollständiges Paar weitergegeben werden, falls der Freund sie noch nicht hat. Der Updater prüft Dateien und Prüfsummen, verwendet den bestehenden passenden Savecache und lädt private Dateien nicht auf GitHub hoch.

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
