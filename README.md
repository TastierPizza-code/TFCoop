# TFCoop für Transport Fever 2

**Alpha5.5 erkennt vollständige temporäre Diagnoseberichte aus Alpha5.4.**
Vorhandene Berichte lassen sich nach dem Launcherupdate ohne neuen
Spielstart exportieren. Der Bauabbruch ist damit noch nicht behoben.

Experimenteller Koop-Prototyp für eine gemeinsame Firma. Der aktuelle Stand **Alpha5.5-Diagnose / v0.5.5** ergänzt einen allein ausführbaren API-Diagnosemodus. Er liest vorhandene Kartenobjekte und getrennte Konstruktorproben, um den ungeklärten Alpha5.3-Abbruch `invalid finite build value` nach dem Straßenbau einzugrenzen.

**Der nächste Schritt benötigt nur einen PC und einen eigenen Diagnosebericht.** Verbindung, Host-IP, Sitzungscode und Mitspieler sind dafür nicht erforderlich. Der gemeinsame Bautest bleibt experimentell; freies gleichzeitiges Bauen, Cursor und die normalen gemeinsamen Pause-Tasten sind noch nicht freigeschaltet. Alpha5.5 ist kein bestätigter Fix und kein Nachweis für deterministischen Multiplayer.

## Download und Start

1. TF2 und den laufenden Test schließen. Wer bereits einen Launcher ab Alpha5.2 verwendet, öffnet ihn anschließend normal und wartet auf das automatische Update auf **Alpha5.5-Diagnose**. Bei der ersten Einrichtung einmal [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python werden auf Spieler-PCs nicht benötigt.
2. Oben die eigenen Spiel- und Saveordner prüfen und im ersten Reiter **API-Diagnose allein** auf **Diagnose vorbereiten** klicken. Die Vorbereitung setzt eine vorhandene Strict-Sync-Testinstallation zurück, installiert die Diagnosemod und erstellt eine frische, geprüfte Save-Kopie.
3. TF2 selbst normal über Steam starten. Die angezeigte `TF2-API-Diagnose-….sav` über **Spiel laden → OPTIONEN AUSWÄHLEN → Mods** nur mit **TF2 API-Diagnose (Alpha5.5)** und **Legacy Fahrzeuge** laden. Alte Koop- und Strict-Sync-Mods deaktivieren.
4. Etwa zehn Sekunden warten, dann **Diagnosebericht als ZIP …** exportieren und privat zur Auswertung weitergeben. Nur ein eigener Bericht ist nötig. TF2 anschließend schließen und die bisherige Installation wiederherstellen. Der vollständige Ablauf steht in der [Anleitung](prototype/ANLEITUNG.md).

Das vom Alpha5.3-Fehler betroffene Zahlenfeld ist noch nicht bekannt. Die Diagnose gibt keine Bau- oder Pausebefehle aus; fehlende Livefahrzeuge oder andere Objekte gelten als fehlende Abdeckung, nicht als erfolgreiche Prüfung. Zweck und Grenzen: [API-Diagnose](prototype/API_DIAGNOSE.md). Den gemeinsamen 240-Runden-Bautest erst nach Auswertung dieses Berichts erneut planen.

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
