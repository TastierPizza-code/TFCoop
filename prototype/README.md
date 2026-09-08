# TF2: Prototyp für strikte Synchronisation

**Alpha5.13-Eingabetest** führt `live_input_v1` als Standard ein: Nach dem automatischen Aufbau erzeugen echte Launcher-Klicks beider Spieler Pause-, Fortsetzen- und Abschlusswünsche. **Referenztest aus Alpha5.12** (`stream_v1`) und **Vergleichstest aus Alpha5.11** (`timing_v1`) bleiben separat auswählbar. Der tatsächliche Zwei-PC-Lauf vom 8. September bestätigt die gegenseitige Bedienprobe und den gemeinsamen Abschluss. Seine 380 Journalzeilen sind identisch; die aktive Fahrt fiel jedoch auf rund 0,82x zurück. [Echte Evidenz und Einschränkungen](docs/ALPHA513_EVIDENCE.md).

Auf beiden PCs aktualisieren, die vorherige Installation wiederherstellen und mit demselben Modus neu vorbereiten. Die saubere Basis der sehr großen Karte bleibt unverändert. Die bisherigen Teilnehmer brauchen keinen erneuten Import. Frische Testsave-Kopien enthalten **TF2 Strict Sync - gemeinsamer Eingabetest (Alpha5.13)** und **Legacy Fahrzeuge**. Bedienfolge: [ANLEITUNG.md](ANLEITUNG.md).

## Neuer Eingabeweg

`live_input.py` speichert echte Wünsche in einer atomaren, sitzungsgebundenen Datei außerhalb der nativen Sitzung. Beide Peers versiegeln pro Abfragerunde die nächste Liste. `live_probe.py` wartet auf beide, liest bei Änderungen frische Weltzustände und wendet denselben Plan an. Explizite Zielzustände und eindeutige Sequenzen verhindern Toggle- und Duplikateffekte. Gegensätzliche Wünsche derselben Runde werden mit Vorrang für Pause geordnet.

In Pause folgen begrenzte wiederholte HOLD-Abfragen mit frischen Zuständen und ohne Fortschrittsschritt. Fortsetzen hängt nicht von einem laufenden Tick ab. Bestätigter Zustand und bestätigte Sequenzen werden erst nach gemeinsamer Rückmeldung angezeigt; lokale Annahme bleibt separat. Jeder Peer kann den regulären Abschluss anfordern, der eine letzte frische beidseitige Weltprüfung verlangt. Nach der letzten Sammelrunde eingegangene Wünsche zählen nicht als ausgeführt.

128 Wünsche je Spieler, acht pro Liste, 2048 Abfragerunden und 3000 zusätzliche Fortschrittsschritte begrenzen den Versuch. Grenzerreichen hält mit Diagnose an. Der Bericht trennt Protokollende von tatsächlichen Pause-/Fortsetzen-Übergängen beider Spieler und einer langen unveränderten Pause. Er beweist keine native UI-Eingabe oder freie Platzierung. Der akzeptierte Takt in `stream_engine.py` bleibt erhalten.

## Ablauf des erhaltenen Alpha5.12-Dauertests

Zuerst läuft das unveränderte Profil `build_v2`: zwölf vorgegebene Befehle und 240 Schritte. Straße, Depot, zwei Haltestellen und drei Verbindungen werden gebaut; ein Fahrzeug wird gekauft, einer Linie zugewiesen und fährt. 211 Fortschrittsschritte ergeben 42,2 Sekunden Enginezeit, 29 Pausenschritte halten den beobachteten Zustand an. Der Bauabschlussnachweis bleibt bei Frame 240 erhalten.

Anschließend startet `paced-stream-v1`: Der gemeinsame Plan legt 600 Fortschrittsschritte, leere Eingabebereiche und zwei zusätzliche Pausenbefehle vorab fest. Jeweils zwei Schritte à 200000 Mikrosekunden werden gemeinsam freigegeben. Nach beiden nativen Bestätigungen folgt die nächste Freigabe. Der lokale Zeitplan wird über diese kleinen Freigaben hinweg fortgeführt; verspätete Aufrufe führen zu keiner Aufholserie.

Alle 50 Schritte wird ein frischer Lua-Weltzustand gelesen und zwischen beiden Teilnehmern verglichen. Das sind zwölf Kontrollpunkte mit zehn Sekunden Spielzeit Abstand. Dazwischen prüft die native Steuerung Uhr und Bestätigung jedes einzelnen Schritts. Die dort zuletzt gespeicherte Lua-Beobachtung ist historisch und darf nicht als aktuelle Welt ausgegeben werden.

Nach 300 zusätzlichen Schritten, also 60 Sekunden Fahrt und bei Frame 540, führt der gemeinsame Plan `a:8` für Pause aus. Beide prüfen den gehaltenen Zustand während einer gemessenen Wartezeit von zwei Sekunden. `b:6` setzt an genau demselben Frame die Simulation fort. Weitere 300 Schritte führen zum letzten Kontrollpunkt bei Frame 840. Erst beide finalen frischen Bestätigungen erlauben den gemeinsamen Abschluss. Diese Wünsche kommen automatisch aus dem Test, nicht von den normalen Pause-Tasten.

Die alten Haltepunkte nach jeweils fünf Sekunden entfallen im neuen Modus. Kontrollpunkte und Netzwerkbestätigungen können dennoch kurz anhalten. Zieltempo und sichtbare Flüssigkeit werden getrennt beurteilt. Ausführliche Messkriterien: [BUILD_TEST.md](BUILD_TEST.md).

## Echter Stand und Grenzen

Alpha5.10 bestand einen Record und einen vollständigen Replay in zwei nacheinander gestarteten TF2-Prozessen auf einem PC. Alpha5.11 bestand anschließend den gemeinsamen Zwei-PC-Test: zwölf Baubefehle, 240 Aufbauschritte und zwölf Fahrtabschnitte mit insgesamt 300 weiteren Schritten. Die 278 Journalzeilen waren bytegleich; alle erfassten Kontrollpunkte und Firmenwerte stimmten überein. Es gab keinen nativen Terminalfehler.

Das 1x-Tempoziel war bei Alpha5.11 nicht erreicht. 60 Sekunden zusätzliche Spielzeit benötigten 66,155 beziehungsweise 66,299 Sekunden innerhalb der Fahrtmethoden einschließlich ihrer Weltabfragen, noch ohne die Haltepunkte zwischen den Abschnitten. Die gesamte Timingphase dauerte beim Host 78,078 Sekunden. Die Spieler beobachteten normale Fahrt innerhalb der Abschnitte und kurze Stopps alle fünf Sekunden. Es wurden keine Renderzeiten gemessen.

**Alpha5.12 ist nach dem echten Zwei-PC-Lauf als Referenz für diese Szene akzeptiert.** Beide Weltjournale mit 270 Einträgen sind identisch; Aufbau, alle 600 zusätzlichen Schritte, zwölf Kontrollpunkte, Pause und Firmenwerte stimmen überein. Das Tempo von ungefähr 0,962x mit kaum sichtbaren Zucklern genügt den Spielern. Die Originalbewertung der strengen 400-ms-Grenze bleibt erhalten. Paket und Code sind eingefroren; Tempooptimierung folgt erst nach den übrigen Funktionen. Details: [akzeptierte Referenz](docs/ACCEPTED_BASELINE.md), [nächste Eingabeetappe](docs/NEXT_MILESTONE.md).

Die früheren Protokoll-, TCP-, Adapter- und Lua-Vorabprüfungen bleiben davon getrennt. Ihre Modelle ersetzen keine echte Spielevidenz. Der [Prüfstand](VERIFICATION.md) dokumentiert beide Ebenen.

Die erfasste Testszene ist kein vollständiger Welthash. Unbeobachtete Fahrzeuge, Fracht, Zufallszustände, Gleisreservierungen sowie langfristige Stadt-, Industrie- und Wirtschaftsentwicklung sind nicht vollständig abgedeckt. Normale Bauwerkzeuge, gemeinsame UI-Pause, Cursor, konkurrierende freie Umbauten, Speichern/Fortsetzen und Steam-Einladungen sind noch nicht freigegeben. Die Verbindung läuft über TCP im LAN oder Hamachi; Steam dient dem Spielstart.

## Erhaltener Vergleichsmodus

**Vergleichstest aus Alpha5.11** wählt `timing_v1` mit dem bisherigen `hold-and-pace-v1`: zwölf Abschnitte à 25 Schritte, drei Ausgangsabschnitte, sechs mit ungleichen lokalen Zusatzwartezeiten und drei weitere zur Kontrolle. Insgesamt entstehen 60 Sekunden Spielzeit; der Abschluss liegt bei Frame 540. Diese künstlichen Wartezeiten sind keine Netzwerk-RTT-Messung.

Ein Moduswechsel erfordert auf beiden PCs eine neue Vorbereitung und denselben neuen Sitzungscode. Die Lobby bindet den Modus zusammen mit den Testdateien; unterschiedliche Abläufe dürfen nicht miteinander starten. Der alte Git-Tag `v0.5.11`, das damalige Paket und die privaten Belege bleiben erhalten. Der neue Vergleichsmodus verwendet die aktuelle geprüfte Installation, keinen Rückfall des Updaters auf eine alte EXE.

## Komponenten

- `strict_sync/core.py` und `replica.py` ordnen den Bauablauf und vergleichen seine Grenzen. `stream_probe.py` verwaltet den festen Dauertestplan, Freigaben, frische Kontrollpunkte und die automatische Pause. `timing_probe.py` erhält den Vergleichsmodus.
- `strict_sync/stream_engine.py` trennt die bestätigte native Schrittgrenze von der letzten vollständigen Lua-Beobachtung. `engine_mailbox.py` bleibt der native/Lua-Adapter. `game_runner.py` verbindet die drei Testmodi mit TCP, Fortschritt und Berichten. Rein native Antworten erhalten keinen historischen Welthash und keinen fingierten aktuellen Snapshot.
- `native/step_probe.*` unterstützt ausschließlich den geprüften Spielbuild 35924 und Native ABI 3. Die Mindestschrittweite bleibt 200000 Mikrosekunden; Originalassertions werden nicht entfernt. HOLD lässt Wartungsarbeit weiterlaufen. Details: [STEP_BOUNDARY.md](native/STEP_BOUNDARY.md).
- `mod/tf2_strict_probe_1` führt begrenzte Testbefehle aus und liest Firmenwerte und gebundene Objekte. Identitäten stammen aus überprüften Rückgaben und Graphänderungen. Der generische Eingabepfad bleibt offen: [DEFERRED_COMMAND_ADAPTER.md](native/DEFERRED_COMMAND_ADAPTER.md).
- `strict_sync/stage_probe.py`, Installerjournal und Launcher erstellen frische Sitzungen und Savekopien. Spielbuild, Quelle und Ausgangsbasis werden per Hash gebunden. Die vorherige Installation lässt sich nach Prozessende wiederherstellen.

Der Lebensdauerschutz nativer Lua-Objekte und die korrigierte Varargs-Rückgabe bleiben erhalten. Die separate **API-Diagnose allein** wird für diesen Versuch nicht gebraucht. Rohdiagnosen bleiben von gültigen Zustandsbeobachtungen getrennt.

## Entwicklung und Prüfung

Einstieg: `py -3.10 probe_launcher.py`, Python 3.10 oder neuer mit Tkinter. Native DLLs werden mit Visual Studio 2022 C++ x64 Build Tools über `prototype\build-native.cmd` gebaut. Quellcode-Starts laden keine Programmupdates. Paketbau und Veröffentlichung: [GITHUB_UPDATES.md](docs/GITHUB_UPDATES.md).

```powershell
py -3.10 -B -m unittest prototype.tests.test_stream_driver prototype.tests.test_timing_driver -v
py -3.10 -B -m unittest discover -s prototype/tests -v
```

Diese Tests starten kein TF2 und bedienen keinen Desktop. Echte lokale Record-/Replay-Versuche verwenden den getrennten Orchestrator `tools/local_game_replay.py`, sein Installationsjournal und exakt zugeordnete Prozesse. Auf dem aktuellen System muss die frisch benannte Save manuell geladen werden. Ein aufeinanderfolgender lokaler Vergleich ersetzt keinen Zwei-PC-Versuch.

Die öffentliche ZIP enthält keine privaten Saves, Berichte, Schlüssel oder originalen Spieldateien. Die bisherige große saubere Basis bleibt im passenden lokalen Cache. Die Lobby verwendet TCP 34208, der Koordinator TCP 34207.

Ein Fehler oder Messende schließt die Steuerung für diese Sitzung. Eine bereits freigegebene kleine Serie kann im Dauertest noch bis zu zwei Schritte ausführen, bevor die TCP-Schleife entfernten HALT verarbeitet; das entspricht bis zu 0,4 Sekunden zusätzlicher Spielzeit, nicht einer garantierten Reaktionsdauer. Im Vergleichsmodus können noch bis zu 25 Schritte folgen. Lokales Stoppen wird zwischen Freigaben geprüft. Es gibt keinen verteilten Rollback und kein stilles Fortsetzen nach Fehlern; ein neuer Versuch verwendet eine frische Ausgangskopie.
