# TFCoop für Transport Fever 2

**Alpha5.12-Dauertest / v0.5.12 bereitet fortlaufende Fahrt mit 1x als Ziel vor.** Nach dem automatischen Aufbau folgen 120 Sekunden Spielzeit. Der neue Ablauf ersetzt die bisherigen Fünf-Sekunden-Abschnitte durch kleine gemeinsame Freigaben und frische Weltvergleiche alle zehn Sekunden Spielzeit. Der **Vergleichstest aus Alpha5.11** bleibt im aktuellen Launcher auswählbar.

**Bisherige echte Evidenz:** Der gemeinsame Alpha5.11-Test auf zwei PCs wurde vollständig abgeschlossen. Bauzustände, Firmenwerte und alle zwölf erfassten Fahrtgrenzen stimmten überein. Das gesamte 1x-Ziel wurde jedoch verfehlt: Die 60 Sekunden zusätzliche Spielzeit brauchten in den Fahrtmethoden 66,155 beziehungsweise 66,299 Sekunden, noch ohne die dazwischenliegenden gemeinsamen Haltepunkte. Die Spieler beobachteten normale Fahrt innerhalb der Abschnitte und kurze Stopps alle fünf Sekunden. **Alpha5.12 ist bisher nur ohne Spielstart mit Protokoll-, Adapter- und Lua-Prüfungen vorbereitet. Seine tatsächliche Flüssigkeit steht noch zur Prüfung aus.**

## Download und gemeinsamer Versuch

1. Auf beiden PCs Test, TF2 und Launcher schließen. Den vorhandenen Launcher ab Alpha5.2 normal öffnen und das Update auf **Alpha5.12-Dauertest** abwarten. Bei erster Einrichtung einmal [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python werden nicht benötigt.
2. **Bisherige Installation wiederherstellen** verwenden. Das bereits übernommene saubere private Savepaar und die bisherige sehr große Karte bleiben gültig. **Für dieses Update braucht keiner der beiden Spieler einen neuen Spielstandimport.** Nur bei einer neuen Einrichtung wird das unveränderte private Paar einmal über **Testspielstand übernehmen …** eingelesen.
3. Im Reiter **Aufbau + 1x-Test (experimentell)** auf beiden PCs **Neuer 1x-Dauertest** wählen. Rollen, dieselbe Host-IP und einen frischen gemeinsamen Sitzungscode festlegen. Beide **Test vorbereiten und installieren**, anschließend **Verbinden & Test bereitstellen**. Unterschiedliche Testmodi werden schon vor dem Spielstart zurückgewiesen.
4. Nach der Startfreigabe TF2 über Steam starten und jeweils die neu angezeigte `TF2-Koop-Messtest-….sav` laden. **TF2 Strict Sync - automatischer Bautest (Alpha5.12)** und **Legacy Fahrzeuge** sind bereits ausgewählt. Die zufälligen Dateinamen dürfen verschieden sein.
5. Kamera bewegen und die Fahrzeugfahrt beobachten; nicht selbst bauen, pausieren oder die Geschwindigkeit verändern. Nach 240 Aufbaurunden bis zum Ende der zusätzlichen **120 Sekunden Spielzeit** weiterlaufen lassen. Nach 60 Sekunden kommt eine automatische gemeinsame Pause mit zwei Sekunden gemessener Wartezeit. Anschließend fährt der Test selbst weiter.
6. Bei Abschluss oder Abbruch auf **beiden PCs** **Testbericht als ZIP …** exportieren. Beide ZIPs und eure Beobachtung der Fahrt privat zur Auswertung schicken. Danach Test und TF2 beenden und die Installation wiederherstellen. Die [Anleitung](prototype/ANLEITUNG.md) führt Host und Mitspieler einzeln durch den Ablauf.

Der neue Dauertest gibt jeweils zwei Schritte à 0,2 Sekunden gemeinsam frei und kontrolliert die native Spieluhr nach jedem Schritt. Nach jeweils 50 Schritten, also zehn Sekunden Spielzeit, werden frische Weltzustände verglichen. Die regelmäßigen Haltepunkte der alten Fünf-Sekunden-Abschnitte entfallen. **Weltabfragen, Netzwerkbestätigungen oder ein langsamer PC können weiterhin kurze Unterbrechungen verursachen.** Ein flüssiger Spielbetrieb ist damit noch nicht nachgewiesen.

**Vergleichstest aus Alpha5.11** führt im gleichen aktuellen Programm weiterhin den früheren Ablauf mit zwölf Fünf-Sekunden-Abschnitten und ungleichen Zusatzwartezeiten aus. Beide müssen denselben Modus wählen und dafür neu vorbereiten. Das ist kein Launcher-Downgrade. Der [Quellstand v0.5.11](https://github.com/TastierPizza-code/TFCoop/tree/v0.5.11) bleibt zusätzlich erhalten; Spielstandpaar und alte Berichte sind privat gesichert.

Der Bericht trennt gleiche Kontrollpunkte vom erreichten Tempoziel. Er misst Aufruf- und Bestätigungszeiten der Steuerung, keine gerenderten Bilder. Freies gleichzeitiges Bauen, Cursor und normale gemeinsame Pause-Tasten sind noch nicht angeschlossen. Vollständige oder dauerhafte Synchronität der ganzen Spielwelt bleibt ungeprüft. Ablauf und Grenzen: [Bau- und Fahrtversuch](prototype/BUILD_TEST.md), [Prüfstand](prototype/VERIFICATION.md).

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
