# TFCoop für Transport Fever 2

Experimenteller Koop-Prototyp für eine gemeinsame Firma. Der aktuelle Stand **Alpha5.2** ist ein automatischer Bautest mit zwei PCs über LAN oder Hamachi: gemeinsame Simulationsschritte, Straße, Depot, Haltestellen, Fahrzeugkauf, Linie und Abfahrt werden verglichen.

**Freies gleichzeitiges Bauen, Cursor und die normalen Pause-Tasten sind in diesem Test noch nicht freigeschaltet.** Der erfolgreiche Modelltest ersetzt keinen erfolgreichen Lauf auf zwei tatsächlichen TF2-Installationen.

## Download und Start

1. Auf beiden PCs einmal [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python werden dafür nicht benötigt.
2. Der Launcher prüft beim Start GitHub auf neuere Releases und startet die vollständig geprüfte neue Version automatisch. TF2 und laufende Tests vorher schließen. Die vorhandene Version bleibt bei einem fehlgeschlagenen Download erhalten.
3. Der gemeinsame Testspielstand wird lokal aus dem bisherigen Testlauf übernommen. Falls er fehlt: **Testspielstand übernehmen …** und aus dem alten privaten Paket `Testspielstand/initial.sav` auswählen; die zugehörige `.sav.lua` muss daneben liegen. Das öffentliche Release enthält keine Spielstände. Für die derzeitige Testreihe wird dieses vorhandene, übereinstimmende Spielstandpaar benötigt.
4. Für Installation, Host/Client-Verbindung und den 240-Runden-Test die [Anleitung](prototype/ANLEITUNG.md) befolgen. Nach einem Update die Testdateien auf beiden PCs neu vorbereiten.

In Alpha5.2 wurde der Abbruch `nonplain observed params` nach dem Straßenbau korrigiert. Details: [Parameterleser](prototype/docs/CONSTRUCTION_PARAMS_FIX.md), [Prüfstand](prototype/VERIFICATION.md).

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
