# TFCoop-Prototyp

**Alpha5.19-Testbegleiter** ergänzt den getrennten Modus `guided_suite_v1` mit fester Host-/Freund-Schrittfolge, frischer gemeinsamer Vorschau, echten Callback-/Beobachtungsbelegen und gemeinsam bestätigtem Fortschritt. [Umfang und Grenzen](docs/GUIDED_TEST.md), [Nachweischeckliste](docs/GAMEPLAY_CHECKLIST.md), [Anleitung](ANLEITUNG.md).

Der tatsächliche Zwei-PC-Lauf vom 8. September bestätigt alle 26 Schritte mit 241 bytegleichen Weltjournalzeilen. Kauf, Linienbearbeitung, Fahrt, Depotankunft und Verkauf sind für die feste Szene belegt. Eine zu frühe Depotprüfung bleibt kostenfrei offen und besteht nach der tatsächlichen Ankunft. Alle 27 Eingaben sind gemeinsam bestätigt. [Alpha5.19-Auswertung](docs/ALPHA519_EVIDENCE.md). Normale Spielwerkzeuge und neue gleichzeitige Fahrzeug-/Linienkonflikte bleiben offen.

## Vorheriger Depotversuch und erhaltene Grundlagen

**Alpha5.16-Depotversuch** führt `manual_depot_v1` ein: ein eigener kurzer Launcher-Bauversuch auf Basis des akzeptierten Takts. Die vier Standorte liegen relativ zur vorbereiteten Testszene; Drehungen sind auf Vierteldrehungen begrenzt. `BUILD_DEPOT` erhält vor jeder Ausführung einen frischen Vorschlag auf beiden PCs. Beide Vorschläge, echte Callbacks, Kosten und neu beobachtete Objektbindungen müssen passen. Erwartete Belegungs-/Geländeablehnungen werden ohne Mutation bestätigt; unerwartete Anwendungsfehler halten an.

`manual_depot_probe.py` ordnet gemeinsame Eingaben. `manual_depot_engine.py` kapselt zusätzliche Vorschau, wiederholte Bindungen und Kostenprüfung. Die normale `StreamEngine` und `paced_live_v1` bleiben erhalten. Der zehnrundige Vorlauf ist ein kurzer Bereitschaftsnachweis, kein vollständiger BuildProof. Der erste tatsächliche Zwei-PC-Lauf hat vier Depots während Fahrt/Pause und eine kostenfreie Belegungsablehnung bestätigt: 97 identische Weltjournalzeilen und 45.835 gemeinsame Baukosten. Normale Fahrt lag bei 0,947x/0,951x, mit Bauprüfungen bei 0,904x/0,905x. Der zweite Lauf ergänzt zwei Wünsche für verschiedene Plätze und zwei konkurrierende Wünsche für denselben Platz in jeweils derselben Sammelrunde: beide Bauten beziehungsweise genau ein Bau mit kostenfreier Ablehnung, 49 identische Weltjournalzeilen. Normale Fahrt lag wieder bei etwa 0,948x, mit Bauprüfungen bei 0,889x. Renderflüssigkeit ist damit nicht gemessen. [Vollständige Auswertung](docs/ALPHA516_EVIDENCE.md).

`test_pairing.py` speichert das private Verbindungsprofil getrennt von Installation und Updatecache. Der authentisierte Lobby-Austausch bindet frische Teilnehmerkennungen, Manifest und neue Host-Sitzung zusammen. Erst danach entstehen Spielschlüssel und Eingabequeues. Bereits verbrauchte Vorbereitungen und Wiederbeitritt bleiben gesperrt.

Auf beiden PCs aktualisieren, die vorherige Installation wiederherstellen und denselben Modus frisch vorbereiten. Die saubere sehr große Ausgangskarte bleibt gültig. Frische Kopien enthalten **TF2 Strict Sync - gemeinsamer Depotversuch (Alpha5.16)** und **Legacy Fahrzeuge**. [Bedienfolge](ANLEITUNG.md).

**Alpha5.15 bleibt als Eingabe-/Temporeferenz gesichert:** 133 identische Weltjournalzeilen, sieben Pause-/Fortsetzen-Wechsel und etwa 0,94x in der tatsächlichen Zwei-PC-Messung. Die neue Funktion ersetzt diese Evidenz nicht. [Referenz und Grenzen](docs/ACCEPTED_INPUT_BASELINE.md).

## Neuer Eingabeweg

`live_input.py` speichert echte Wünsche in einer atomaren, sitzungsgebundenen Datei außerhalb der nativen Sitzung. `paced_live_probe.py` versiegelt sie in vorhandenen Antworten und wartet auf beide, liest bei Änderungen frische Weltzustände und wendet denselben Plan an. Explizite Zielzustände und eindeutige Sequenzen verhindern Toggle- und Duplikateffekte. Gegensätzliche Wünsche derselben Runde werden mit Vorrang für Pause geordnet. Der alte separate Abfrageweg bleibt in `live_probe.py`. `short_build_profile.py` prüft die neue Bereitschaft, ohne den vollständigen `BuildProof` zu behaupten.

In Pause folgen begrenzte wiederholte HOLD-Abfragen mit frischen Zuständen und ohne Fortschrittsschritt. Fortsetzen hängt nicht von einem laufenden Tick ab. Bestätigter Zustand und bestätigte Sequenzen werden erst nach gemeinsamer Rückmeldung angezeigt; lokale Annahme bleibt separat. Jeder Peer kann den regulären Abschluss anfordern, der eine letzte frische beidseitige Weltprüfung verlangt. Nach der letzten Sammelrunde eingegangene Wünsche zählen nicht als ausgeführt.

128 Wünsche je Spieler, acht pro Liste, 2048 Sammelrunden und 3000 zusätzliche Fortschrittsschritte begrenzen den Versuch. Überzählige lokale Wünsche werden abgewiesen; das Laufzeit-/Rundenlimit hält mit Diagnose an. Der Bericht trennt Protokollende von tatsächlichen Pause-/Fortsetzen-Übergängen beider Spieler und einer langen unveränderten Pause. Er beweist keine native UI-Eingabe oder freie Platzierung. Der akzeptierte Takt in `stream_engine.py` bleibt erhalten.

## Ablauf des erhaltenen Alpha5.12-Dauertests

Zuerst läuft das unveränderte Profil `build_v2`: zwölf vorgegebene Befehle und 240 Schritte. Straße, Depot, zwei Haltestellen und drei Verbindungen werden gebaut; ein Fahrzeug wird gekauft, einer Linie zugewiesen und fährt. 211 Fortschrittsschritte ergeben 42,2 Sekunden Enginezeit, 29 Pausenschritte halten den beobachteten Zustand an. Der Bauabschlussnachweis bleibt bei Frame 240 erhalten.

Anschließend startet `paced-stream-v1`: Der gemeinsame Plan legt 600 Fortschrittsschritte, leere Eingabebereiche und zwei zusätzliche Pausenbefehle vorab fest. Jeweils zwei Schritte à 200000 Mikrosekunden werden gemeinsam freigegeben. Nach beiden nativen Bestätigungen folgt die nächste Freigabe. Der lokale Zeitplan wird über diese kleinen Freigaben hinweg fortgeführt; verspätete Aufrufe führen zu keiner Aufholserie.

Alle 50 Schritte wird ein frischer Lua-Weltzustand gelesen und zwischen beiden Teilnehmern verglichen. Das sind zwölf Kontrollpunkte mit zehn Sekunden Spielzeit Abstand. Dazwischen prüft die native Steuerung Uhr und Bestätigung jedes einzelnen Schritts. Die dort zuletzt gespeicherte Lua-Beobachtung ist historisch und darf nicht als aktuelle Welt ausgegeben werden.

Nach 300 zusätzlichen Schritten, also 60 Sekunden Fahrt und bei Frame 540, führt der gemeinsame Plan `a:8` für Pause aus. Beide prüfen den gehaltenen Zustand während einer gemessenen Wartezeit von zwei Sekunden. `b:6` setzt an genau demselben Frame die Simulation fort. Weitere 300 Schritte führen zum letzten Kontrollpunkt bei Frame 840. Erst beide finalen frischen Bestätigungen erlauben den gemeinsamen Abschluss. Diese Wünsche kommen automatisch aus dem Test, nicht von den normalen Pause-Tasten.

Die alten Haltepunkte nach jeweils fünf Sekunden entfallen im neuen Modus. Kontrollpunkte und Netzwerkbestätigungen können dennoch kurz anhalten. Zieltempo und sichtbare Flüssigkeit werden getrennt beurteilt. Ausführliche Messkriterien: [BUILD_TEST.md](BUILD_TEST.md).

## Echter Stand und Grenzen

Alpha5.10 bestand einen Record und einen vollständigen Replay in zwei nacheinander gestarteten TF2-Prozessen auf einem PC. Alpha5.11 bestand anschließend den gemeinsamen Zwei-PC-Test: zwölf Baubefehle, 240 Aufbauschritte und zwölf Fahrtabschnitte mit insgesamt 300 weiteren Schritten. Die 278 Journalzeilen waren bytegleich; alle erfassten Kontrollpunkte und Firmenwerte stimmten überein. Es gab keinen nativen Terminalfehler.

Das 1x-Tempoziel war bei Alpha5.11 nicht erreicht. 60 Sekunden zusätzliche Spielzeit benötigten 66,155 beziehungsweise 66,299 Sekunden innerhalb der Fahrtmethoden einschließlich ihrer Weltabfragen, noch ohne die Haltepunkte zwischen den Abschnitten. Die gesamte Timingphase dauerte beim Host 78,078 Sekunden. Die Spieler beobachteten normale Fahrt innerhalb der Abschnitte und kurze Stopps alle fünf Sekunden. Es wurden keine Renderzeiten gemessen.

**Alpha5.12 bleibt die längere akzeptierte Referenz für diese Szene.** Beide Weltjournale mit 270 Einträgen sind identisch; Aufbau, alle 600 zusätzlichen Schritte, zwölf Kontrollpunkte, Pause und Firmenwerte stimmen überein. Das Tempo von ungefähr 0,962x mit kaum sichtbaren Zucklern genügt den Spielern. Die Originalbewertung der strengen 400-ms-Grenze bleibt erhalten. Paket und Code sind eingefroren. Der getrennte Eingabemodus aus Alpha5.15 ist nun ebenfalls akzeptiert; weitere Tempoexperimente werden zurückgestellt. Details: [Alpha5.12-Referenz](docs/ACCEPTED_BASELINE.md), [nächste Eingabeetappe](docs/NEXT_MILESTONE.md).

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
