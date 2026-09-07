# TF2: Prototyp für strikte Synchronisation

**Alpha5.11-1x-Test** erweitert den bisherigen automatischen Bau um einen begrenzten Versuch zu Wartezeiten und Schrittfolge. Es ist weiterhin ein Entwicklungsprototyp. Die neuen Abschnitte warten noch auf ihren ersten echten TF2-Test; Modellprüfungen werden nicht als Nachweis für den Spielbetrieb dargestellt.

Der aktuelle Launcher öffnet **Aufbau + 1x-Test (experimentell)**. Auf beiden PCs das Update abwarten, die vorherige Installation wiederherstellen und eine frische gemeinsame Sitzung vorbereiten. Die seit Alpha5.9 verwendete saubere Basis der bisherigen sehr großen Karte bleibt unverändert; wer sie übernommen hat, braucht keinen neuen Import. Die frische Testsave enthält bereits **TF2 Strict Sync - automatischer Bautest (Alpha5.11)** und **Legacy Fahrzeuge**. Bedienfolge und Berichtsexport stehen in [ANLEITUNG.md](ANLEITUNG.md).

## Aktueller Versuch

Zuerst läuft das bestehende Profil `build_v2`: zwölf vorgegebene Bau-/Fahr-/Pausenbefehle und 240 Schritte. Straße, Depot, zwei Haltestellen und drei Verbindungen werden gebaut; ein Fahrzeug wird gekauft, einer Linie zugewiesen und fährt. 211 Fortschrittsschritte ergeben 42,2 Sekunden Enginezeit, 29 Schritte halten die erfasste Welt an. Der Bauabschlussnachweis bleibt an Grenze 240 erhalten.

Anschließend läuft `hold-and-pace-v1` mit zwölf Abschnitten von jeweils 25 nativen Schritten à 200000 Mikrosekunden. Drei Abschnitte dienen als Ausgangsmessung, sechs enthalten abwechselnd lokale Zusatzwartezeiten von 1000, 1500, 250, 750, 3000 und 500 Millisekunden, drei dienen als anschließende Vergleichsmessung. Die zwölf Abschnitte ergeben weitere 60 Sekunden Simulationszeit; die Zielgeschwindigkeit ist ausschließlich 1x.

Vor jedem Abschnitt prüfen beide Teilnehmer Plan, Ausgangszustand und die für sie vorgesehene Wartezeit. Erst nach beiden Bereitschaftsbestätigungen darf der Abschnitt beginnen. Innerhalb des Abschnitts fordert die Steuerung Schritte im Abstand von mindestens 0,2 Sekunden an. Bei Verzögerungen verschiebt sich der Ablauf, ohne eine Aufholserie der Anforderungen. Die gemessenen Anforderungszeiten liegen vor der Dateiübertragung zur nativen Engine; ihre tatsächlichen Ankunftszeiten werden nicht gemessen. Danach müssen beide erfassten Endzustände und die exakten Zeit-/Schrittgrenzen übereinstimmen, bevor der nächste Abschnitt freigegeben wird.

Die Welt wird am Anfang und Ende jedes Fahrtabschnitts gelesen, die native Uhr nach jeder einzelnen Freigabe geprüft. Das reduziert die aufwendigen Lua-Weltabfragen während der Fahrt. Es ist ein anderer Prüfumfang als die vollständigen Zustandsvergleiche nach jeder Aktion im vorausgehenden Aufbau. Das Tempoergebnis gilt für die zwölf einzelnen Abschnitte; gemeinsame Haltepunkte zwischen ihnen gehören weiterhin zum Ablauf. Einzelheiten und Messkriterien: [BUILD_TEST.md](BUILD_TEST.md).

## Bisherige echte Evidenz und Grenzen

Alpha5.10 bestand auf einem PC zwei nacheinander gestartete echte TF2-Prozesse: einen Record und einen vollständigen Replay desselben Befehlsstroms aus einer frischen Kopie desselben Savepaars. Alle zwölf Befehle, 240 Schritte und beobachteten Ergebnisse stimmten überein. Firmenwerte, Straßenverbindung, Linienzuweisung, Fahrzeugbewegung und vorgegebene Pausen wurden erfasst. Beide Prozesse wurden regulär beendet und die Installation wiederhergestellt. Das war kein Live-Netzwerktest.

Die neue Alpha5.11-Steuerung ist bisher ohne Spielstart geprüft. Die Tests prüfen beide Protokollteilnehmer, vollständige Fahrtabschnitte, ungleiche Wartezeiten, Abbrüche und die Anbindung an Lua-/Datei-IPC mit Ersatz für Spiel und native Engine. Sie beweisen weder TF2-Determinismus noch sichtbare Flüssigkeit. Der [Prüfstand](VERIFICATION.md) trennt diese Nachweise von den tatsächlichen Spielversuchen.

Auch bei gehaltener Spielzeit läuft interne Wartungs-, Skript- und Befehlsarbeit. Die Warteversuche erfassen zusätzliche native Wartungszähler und prüfen erfasste Zustände erneut. Diese Zähler sind Diagnosewerte und kein vollständiger Welthash. Unbeobachtete Fahrzeuge, Frachtinhalte, Zufallszustände, Gleisreservierungen und Stationsinternes sind nicht vollständig abgedeckt. Langfristige Stadt-, Industrie- und Wirtschaftsentwicklung braucht weitere Versuche.

Normale Bauwerkzeuge und Pause-Tasten speisen noch keine Eingaben in diesen kontrollierten Ablauf ein. Freies gleichzeitiges Bauen, konkurrierende Umbauten, Spielercursor, beliebige Ausgangskarten, Fortsetzen nach Absturz und Steam-Einladungen werden noch nicht zugesichert. Der Test verbindet über TCP im LAN oder über Hamachi; Steam dient dem Spielstart.

## Komponenten

- `strict_sync/core.py` und `replica.py` ordnen Befehle, vergleichen Grenzen und stoppen bei widersprüchlichen Ergebnissen. `timing_probe.py` ergänzt ausschließlich nach dem vollständigen Aufbau die fest vorgegebenen Fahrtabschnitte. Eine zusätzliche gemeinsame Fähigkeit verhindert das Mischen alter und neuer Steuerungen.
- `strict_sync/engine_mailbox.py` steuert tatsächliche native Freigaben und Lua-Beobachtungen. Ein nativer Zeitschritt allein wird nicht als erfolgreicher Weltvergleich dargestellt. `game_runner.py` verbindet Adapter und TCP-Protokoll.
- `native/step_probe.*` unterstützt ausschließlich den geprüften Spielbuild 35924 und Native ABI 3. Die native Mindestschrittweite bleibt 200000 Mikrosekunden; Originalassertions werden nicht entfernt. HOLD hält die Zeit, lässt aber Wartungsarbeit weiterlaufen. Details: [STEP_BOUNDARY.md](native/STEP_BOUNDARY.md).
- `mod/tf2_strict_probe_1` führt vorbereitete Testbefehle über die Spiel-API aus und liest tatsächliche Firmenwerte und gebundene Objekte. Straßen- und Fahrzeugidentitäten stammen aus echten Rückgaben bzw. überprüften Graphänderungen. Fehlende Werte werden nicht durch geratene Identitäten oder Preise ersetzt.
- Der allgemeine native Eingabepfad ist noch nicht fertig angeschlossen. Seine offenen Voraussetzungen stehen in [DEFERRED_COMMAND_ADAPTER.md](native/DEFERRED_COMMAND_ADAPTER.md).
- `strict_sync/stage_probe.py`, Installerjournal und Launcher erstellen frische Sitzungen und Savekopien. Spielbuild, Quellstand und Ausgangsspielstand werden durch Hashes gebunden. Die vorherige Installation lässt sich nach Prozessende wiederherstellen.

Der Lebensdauerschutz nativer Besitzer aus Alpha5.9 und dessen korrigierte Rückgabe aus Alpha5.10 bleiben erhalten. Die separate **API-Diagnose allein** ist für gezielte Untersuchungen weiterhin verfügbar, aber für diesen Versuch nicht erforderlich. Rohdiagnosen bleiben als ungültige Messversuche getrennt vom letzten bestätigten Zustand.

## Entwicklung und Prüfung

Der aktuelle Einstieg ist `py -3.10 probe_launcher.py`; benötigt wird Python 3.10 oder neuer mit Tkinter. Native DLLs werden mit Visual Studio 2022 C++ x64 Build Tools über `prototype\build-native.cmd` gebaut. Die portable ZIP und ihr Startupdate sind in [GITHUB_UPDATES.md](docs/GITHUB_UPDATES.md) beschrieben. Quellcode-Starts laden keine Programmupdates.

```powershell
py -3.10 -B -m unittest prototype.tests.test_timing_probe prototype.tests.test_engine_timing prototype.tests.test_timing_driver -v
py -3.10 -B -m unittest discover -s prototype/tests -v
```

Die Tests starten keine TF2-Prozesse und bedienen keinen Desktop. Echte lokale Record-/Replay-Versuche verwenden den getrennten Orchestrator `tools/local_game_replay.py`, sein Installationsjournal und exakt zugeordnete Prozesse. Die automatisierte Ladefunktion funktioniert auf dem aktuellen System nicht zuverlässig; die tatsächlichen Versuche verwenden manuelles Laden einer frisch benannten Save. Ein aufeinanderfolgender lokaler Vergleich ersetzt keinen Zwei-PC-Netzwerktest.

Die öffentliche ZIP enthält keine privaten Spielstände, Sitzungsschlüssel, Nutzerberichte oder originalen Spielbinärdateien. Ein passendes seit Alpha5.9 importiertes Savepaar bleibt im lokalen Cache auch nach Alpha5.11 verfügbar. Beide Spieler benötigen einen frischen gemeinsamen Code, passende Testdateien und ihre jeweils neu importierte Save. Die Launcher-Lobby verwendet TCP 34208, der Messkoordinator TCP 34207.

Fehler und Messende schließen die Steuerung dauerhaft für diese Sitzung. Bereits freigegebene Aktionen können bei einem Verbindungsabbruch noch enden; es gibt keinen verteilten Rollback und kein stilles Weiterlaufen. Ein neuer Versuch beginnt wieder mit einer frischen Kopie des gemeinsamen Ausgangsspielstands. Private Berichte beider PCs werden zur Auswertung benötigt.

Eine bereits freigegebene Fahrtserie darf bis zu 25 Schritte fertigführen, bevor die TCP-Schleife eine entfernte HALT-Meldung oder einen Verbindungsabbruch verarbeitet. Der einzelne Abschnitt hat ein begrenztes Wallzeitbudget; lokales Stoppen wird zwischen Freigaben geprüft. Das ist keine sofortige verteilte Unterbrechung innerhalb des Abschnitts.
