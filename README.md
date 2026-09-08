# TFCoop für Transport Fever 2

**Alpha5.16-Depotversuch / v0.5.16** ergänzt manuell ausgelöste Depotaufträge über den Launcher. Vier begrenzte Testplätze und vier Drehungen stehen zur Wahl. Vor jedem Bau vergleichen beide Spieler einen frischen Bauvorschlag; erfolgreiche Platzierung, tatsächliche Kosten und Objektbindungen müssen gemeinsam bestätigt sein. Ein nach dem vorherigen Bau belegter Platz wird erneut geprüft und ohne Baukosten abgelehnt. Das ist noch keine Platzierung mit normalen Spielwerkzeugen.

Host-IP, privater Testschlüssel und Rolle werden nach einmaliger Einrichtung lokal gemerkt. Jeder Versuch erhält über die authentisierte Verbindung weiterhin eine neue interne Sitzung. Private Verbindungsdaten gehören nicht ins öffentliche Paket.

## Download und gemeinsamer Versuch

1. TF2, Test und Launcher schließen; den vorhandenen Launcher neu öffnen und das Update auf **Alpha5.16-Depotversuch** abwarten. Erstmalig: [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken, `TF2-Coop.exe` starten.
2. Vorherige Installation wiederherstellen. **Depot selbst beauftragen · kurzer Aufbau** wählen. IP und Testschlüssel einmal auf beiden PCs gleich eintragen, jeweilige Rolle wählen und vorbereiten.
3. Beide verbinden, Startfreigabe abwarten und die jeweilige frische Testsave laden. Strict Sync Alpha5.16 und Legacy Fahrzeuge sind bereits gewählt. Die bestehende große Ausgangskarte bleibt gültig; kein neuer Saveimport für die bisherigen Teilnehmer.
4. Nach zehn Aufbaurunden baut der Host Platz 1 während Fahrt, der Freund Platz 2 während gemeinsamer Pause. Anschließend beide denselben frischen Platz 3 versuchen. Ergebnisse abwarten, gemeinsam abschließen und beide Berichte exportieren.

Die vollständige [Anleitung](prototype/ANLEITUNG.md) erklärt Plätze, Drehung, Rückmeldungen und Fehlerfälle. **Der tatsächliche Zwei-PC-Lauf vom 8. September hat vier Depots mit gleichen beobachteten Zuständen und Kosten gebaut, während Fahrt und Pause.** Ein belegter Platz wurde ohne Kosten abgelehnt. Die beiden konkurrierenden Wünsche kamen in aufeinanderfolgenden Sammelrunden an; derselbe Fall innerhalb einer Runde bleibt im Spiel offen. [Auswertung und Grenzen](prototype/docs/ALPHA516_EVIDENCE.md).

Die normale Fahrt erreichte dabei etwa 0,947x/0,951x; einschließlich der zusätzlichen Bauprüfungen lag der aktive Durchschnitt bei 0,904x/0,905x. Das sind native Simulationsmessungen, keine FPS-Werte. Die akzeptierte [Alpha5.15-Referenz](prototype/docs/ACCEPTED_INPUT_BASELINE.md) mit rund 0,94x bleibt separat auswählbar. Die längere [Alpha5.12-Referenz](prototype/docs/ACCEPTED_BASELINE.md) bleibt ebenso erhalten. Die alten Tags und Pakete werden nicht ersetzt.

Normale Bauwerkzeuge und UI-Pause, Cursor/Blaupausen, freie konkurrierende Umbauten, Speichern/Fortsetzen und Steam-Einladungen sind weitere Arbeit. Die beobachtete Testszene ist kein vollständiger oder dauerhafter Weltnachweis. [Prüfstand](prototype/VERIFICATION.md).

Das öffentliche Release enthält keine Spielstände, Berichte, Sitzungsschlüssel oder originalen Spieldateien. Updates prüfen die Paketdateien und verwenden den vorhandenen passenden Savecache. Private Sicherungen bleiben lokal.

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
