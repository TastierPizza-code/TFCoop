# Alpha5.12: Aufbau, fortlaufende 1x-Fahrt und gemeinsame Testpause

Beide Testmodi beginnen mit demselben Profil `build_v2`. Der neue Standard
**Neuer 1x-Dauertest** (`stream_v1`, Protokoll `paced-stream-v1`) prüft anschließend
120 Sekunden zusätzliche Spielzeit. **Vergleichstest aus Alpha5.11** (`timing_v1`,
Protokoll `hold-and-pace-v1`) erhält den bisherigen Ablauf mit zwölf kurzen
Fahrtabschnitten. Beide Teilnehmer müssen denselben Modus wählen und frisch
vorbereiten. Die Lobby prüft den Modus zusammen mit den gemeinsamen Testdateien.

Die bisherige sehr große Karte und ihr sauberes privates Savepaar bleiben
unverändert. Beide bisherigen Teilnehmer haben es bereits; ein neuer Import
ist nicht nötig. Frische Kopien enthalten Strict Sync Alpha5.12 und Legacy
Fahrzeuge. Bedienfolge: [ANLEITUNG.md](ANLEITUNG.md).

**Echte Evidenz:** Alpha5.11 wurde auf beiden PCs mit gleichen erfassten Zuständen
abgeschlossen. Seine 278 Journalzeilen waren bytegleich; alle zwölf zusätzlichen
Fahrtgrenzen und Firmenwerte stimmten überein. Das 1x-Tempoziel wurde verfehlt:
60 Sekunden Spielzeit benötigten in den Fahrtmethoden 66,155 beziehungsweise
66,299 Sekunden, noch ohne die Übergänge zwischen ihnen. Die neue
Alpha5.12-Steuerung ist bisher nur ohne Spielstart vorgeprüft. Frühere tatsächliche
Versuche und die Grenzen ihrer Aussage stehen im [Prüfstand](VERIFICATION.md).

## Fester Ablauf in beiden Spielen

| Runde, ab null gezählt | Eingabe stammt von | Gemeinsame Aktion |
|---|---|---|
| 0 | Host a | Pause |
| 1 | Host a | T-förmige Teststraße bauen |
| 2 | Mitspieler b | Straßendepot bauen |
| 3 | Host a | Erste Personenhaltestelle bauen |
| 4 | Mitspieler b | Zweite Personenhaltestelle bauen |
| 5 | Host a | Drei Verbindungsstraßen zwischen vorhandenen Knoten bauen |
| 6 | Mitspieler b | Ein verfügbares Personenfahrzeug von 1850 kaufen |
| 7 | Host a | Linie mit beiden Haltestellen anlegen |
| 8 | Mitspieler b | Fahrzeug der Linie zuweisen |
| 9 | Host a | Simulation fortsetzen |
| 80 | Host a | Gemeinsame Pause |
| 100 | Mitspieler b | Simulation fortsetzen |
| bis einschließlich 239 | beide | Gleiche Zeitpunkte und beobachtete Zustände bestätigen |

Beide Spiele führen jeden Befehl aus. Die wechselnde Herkunft prüft die beiden
Eingabewege; niemand muss diese Aktionen manuell auslösen. Die Runden enthalten
29 Pausenschritte und 211 echte Schritte à 200000 Mikrosekunden, insgesamt
42,2 Sekunden Enginezeit. Die Wartezeiten im Netzwerk zählen nicht als Spielzeit.

## Neuer Standard: 120 Sekunden fortlaufende Spielzeit

Nach der bestätigten Aufbaugrenze bei Frame 240 legt der gemeinsame Plan
**600 Fortschrittsschritte à 200000 Mikrosekunden** fest. Die erste und zweite
Hälfte enthalten je 300 Schritte ohne freie Baueingaben. Die einzige
vorgegebene Änderung dazwischen ist die gemeinsame Testpause. Der Bauabschluss
bleibt separat bei Frame 240 nachgewiesen.

| Zusätzliche Spielzeit | Bestätigter Frame | Aktion |
|---|---|---|
| Start | 240 | Frischen Ausgangszustand des Dauertests vergleichen |
| Je 0,4 Sekunden | Je zwei Schritte weiter | Kleine gemeinsame Freigabe; jeden nativen Schritt prüfen |
| Alle zehn Sekunden | 290, 340, …, 840 | Frische erfasste Welt auf beiden PCs lesen und vergleichen |
| 60 Sekunden | 540 | `a:8`: gemeinsame Pause einschalten |
| Während der Pause | Unverändert 540 | Zustand während zwei Sekunden gemessener Wartezeit halten und erneut prüfen |
| Nach der Wartezeit | Unverändert 540 | `b:6`: gemeinsame Simulation fortsetzen |
| 120 Sekunden | 840 | Zwölften frischen Kontrollpunkt auf beiden PCs bestätigen; erst dann abschließen |

Die Pausebefehle stammen automatisch aus den beiden Test-Eingabewegen.
Sie verändern nur an der gemeinsam bestätigten Grenze den Pausenzustand.
Es gibt dabei keinen zusätzlichen Fortschrittsschritt. Normale UI-Tasten
sind nicht die Quelle dieser Befehle.

Der Koordinator gibt jeweils **zwei** Schritte gemeinsam frei und wartet
auf die beiden nativen Abschlussmeldungen. Der lokale 200-ms-Zeitplan läuft
über diese kleinen Freigaben hinweg fort. Verzögerungen verschieben den
nächsten Aufruf; es gibt keine schnelle Aufholserie. Die native Uhr, Frame,
Schrittweite und vollständige Bestätigung werden nach jeder Freigabe geprüft.

Nach jeweils 50 Schritten, also zehn Sekunden Spielzeit, fordert der
Koordinator neue Weltbeobachtungen an. Erst wenn beide frischen Hashes und
Grenzen übereinstimmen, geht es weiter. Während der kleinen Schrittserien
bleibt die zuletzt gespeicherte Lua-Welt ausdrücklich historisch. Eine native
Zeitbestätigung ist kein neuer Welthash. Antworten auf solche Freigaben
enthalten deshalb ausschließlich die native Zeitgrenze und Messwerte.

Die Übergangsstopps der alten Fünf-Sekunden-Abschnitte entfallen. Kontrollpunkte,
Dateiübertragung, Netzwerkbestätigungen und langsame Verarbeitung können
weiterhin die Fahrt unterbrechen. **Der neue Ablauf ist keine Garantie für
flüssige Bilder oder dauerhaftes 1x.** Genau das muss im echten Versuch geprüft
werden. Die automatische Pause kann durch Abfragen und Bestätigungen länger
sichtbar sein als ihre zwei Sekunden gezielter Wartezeit.

## Tempoauswertung des Dauertests

`stream` im Host-/Peer-Bericht enthält den festen Plan, native Messungen aller
kleinen Freigaben, zwölf frische Kontrollpunkte und den Nachweis beider
Pausebefehle samt Wartephase. `completed` bedeutet, dass der Ablauf mit beiden
finalen Bestätigungen abgeschlossen wurde. `paced_stream_1x_met` bewertet
getrennt davon das Tempo. Bei unvollständigen Daten bleibt diese Bewertung offen.

Die Auswertung betrachtet zwei Teilstrecken mit je 300 Schritten. Der Zeitraum
reicht vom ersten lokalen Aufruf einer nativen Freigabe bis zur zuletzt
beobachteten Bestätigung, zuzüglich einer Schrittperiode. Gewöhnliche
Kontrollpunkte und kleine Netzwerkübergänge innerhalb der Teilstrecke zählen
mit. Die Pause samt Übergang in der Mitte wird zwischen den Teilstrecken
separat ausgewiesen. Die gesamte lokale Versuchsdauer wird zusätzlich berichtet.

Das 1x-Ziel verlangt auf beiden PCs in beiden Teilstrecken:

- 950000 bis 1050000 ppm, also 95 bis 105 Prozent des 1x-Ziels.
- Je 299 Abstände zwischen den lokalen Freigabeaufrufen und zwischen den beobachteten Bestätigungen.
- Für beide Abstandsreihen ein 95. Perzentil von höchstens 250 ms und einen Maximalwert von höchstens 400 ms.

`call_started_offset_us` beschreibt den Beginn des lokalen Python-Aufrufs
vor der Dateiübertragung; `ack_observed_offset_us` beschreibt den Zeitpunkt,
an dem die Steuerung dessen native Bestätigung beobachtet. Ankunftszeiten in
der nativen Engine und gerenderte Bilder werden nicht gemessen. Zeitstempel
verschiedener PCs werden nicht voneinander abgezogen. Der Hostbericht wertet
beide Teilnehmer aus; ein Peerbericht enthält nur die eigenen Tempo-Messwerte.

Die Weltabfragen während gewöhnlicher Kontrollpunkte gehen nun in die
beobachtete Fahrtfolge ein. Auch ein bestandenes 1x-Ziel beweist jedoch keine
visuelle Flüssigkeit: Die Spieler sollen berichten, ob das Fahrzeug an
Kontrollpunkten oder auch dazwischen stockt. Der Vergleich deckt weiterhin nur
die erfasste Testszene und Firmenwerte ab, nicht jeden internen Spielzustand.

## Erhaltener Vergleichstest aus Alpha5.11

Dieser auswählbare Modus verwendet weiter zwölf Abschnitte aus jeweils
25 Schritten à 0,2 Sekunden. Insgesamt entstehen 60 zusätzliche Sekunden
Spielzeit; er endet bei Frame 540. Es handelt sich um den bisherigen
Testablauf im aktuellen Programm, nicht um einen alten Launcherstart.

| Abschnitt | Zusätzliche lokale Wartezeit vor der gemeinsamen Freigabe |
|---|---|
| 1–3 | Keine |
| 4 | Host a: 1000 ms |
| 5 | Mitspieler b: 1500 ms |
| 6 | Host a: 250 ms |
| 7 | Mitspieler b: 750 ms |
| 8 | Host a: 3000 ms |
| 9 | Mitspieler b: 500 ms |
| 10–12 | Keine |

Diese künstlichen Wartezeiten sind keine Netzwerk-RTT-Messung. Beide
Teilnehmer bestätigen Ausgangs- und Endzustand jedes Abschnitts. Dazwischen
prüft die Steuerung die native Uhr nach jedem Schritt; die vollständige
Lua-Beobachtung findet am Anfang und Ende statt.

Das Feld `timing.paced_windows_1x_met` bewertet jeden einzelnen Abschnitt:
95 bis 105 Prozent des Zieltempos, mindestens 24 Freigabe-/Bestätigungsabstände,
95. Perzentil höchstens 250 ms und Maximum höchstens 400 ms. Die Abschnittsdauer
enthält die beiden Weltabfragen; die Abstandsreihen enthalten weder den ersten
Aufruf noch die gemeinsamen Haltepunkte zwischen Abschnitten. Die ältere
Feldbezeichnung `admitted_offset_us` bezeichnet ebenfalls den lokalen Aufruf,
keine gemessene Ankunft in der nativen Engine.

Für einen Moduswechsel Test und TF2 beenden, wiederherstellen und auf beiden PCs
mit gleichem Modus und einem neuen gemeinsamen Code vorbereiten. Die gemeinsame
saubere Basis bleibt dieselbe. Der veröffentlichte Tag `v0.5.11` und private
Sicherungen der damaligen Daten bleiben zur Nachprüfung erhalten; der Updater
wird dafür nicht zurückgesetzt.

## Identitäten und Baustelle

Das Lua-Profil `build_v2` sucht vor der ersten Änderung deterministisch eine
freie, über Wasser liegende Baustelle. Alpha5.1 ersetzt die 81 zentralen Stellen
durch bis zu 4225 Punkte über den anhand gültiger Koordinaten ermittelten
Kartenbereich. Die Suche ist auf 32768 Meter je Achsrichtung begrenzt und meldet
es, wenn diese Grenze erreicht wird. Gute Kandidaten werden mit 169 Geländeproben
verfeinert. Bevorzugt sind höchstens zwei Meter Höhenstreuung; ansonsten ist die
beste geprüfte freie Stelle mit höchstens acht Metern zulässig. Ihre Bauhöhe
ist die Mitte zwischen dem niedrigsten und höchsten gemessenen Geländepunkt.

Die eigene Straßenkonstruktion ebnet als Teil ihres gemeinsam ausgeführten
Bauvorgangs ein Rechteck von 320 × 180 Metern. Dieses umfasst die tatsächlichen
Geländeflächen von Depot und Haltestellen. Die Höhenänderung beträgt an den
gemessenen Stellen maximal vier Meter. Gelände zwischen Messpunkten und die
tatsächliche Annahme durch die Engine bleiben Gegenstand des Nutzertests.
Wasser- und Belegungsprüfungen bleiben aktiv. Geländeproben,
Wasserstand, Baustelle und ausgewählte Ressourcen gehen in den Ausgangsvergleich
ein. Fehlende Ressourcen oder keine passende Baustelle führen zu einem Fehler.
Zusätzliche aktuelle Geländeproben gehen auch nach dem Bau in jeden
Zustandsvergleich ein. Das lokale `lua_status.json` enthält unter
`diagnostics.site_search` die Suchgrenzen, Zähler und Ablehnungsgründe.
Erfolgreich geschriebene Lua-Antworten bleiben beim wiederholten Abfragen nun
unverändert auf der Festplatte stehen. So muss der Leser nicht ständig eine
erneut geleerte und beschriebene große Antwortdatei abpassen.

Die Straße ist eine eigene kleine `STREET_CONSTRUCTION`. Ihr Callback liefert
die Konstruktion; deren `frozenEdges` führen zu tatsächlichen Straßenknoten.
Dasselbe gilt für Depot und Stationen. Die geometrischen Rezeptwerte dienen nur
zur Auswahl eines eindeutigen Außenendes innerhalb dieser bekannten Objekte.
Gleiche räumliche Koordinaten sind keine Objekt- oder Verbindungsidentität.

`PROBE_CONNECT` fügt drei gewöhnliche Straßenkanten zwischen den bestehenden
Anschlussknoten hinzu. Es erzeugt keine neuen Knoten und entfernt keine Kanten.
Der normale Straßen-Callback kann eine leere `resultEntities`-Liste liefern.
Deshalb wird die tatsächliche neue Kante durch den strikten Vorher-/Nachher-
Vergleich an den bereits bekannten Knoten belegt: genau eine neue Kante je
beabsichtigtem Knotenpaar, keine entfernten oder veränderten Bestandskanten.
Alle drei Verbindungen müssen bestätigt sein, bevor Bindings übernommen werden.
Ein fehlender, falscher oder mehrdeutiger Nachweis hält den Test an.

Die neuen Kanten `a:4:link:1` bis `a:4:link:3` stehen mit ihrer vollständigen
beobachteten Geometrie und Straßenkonfiguration im gemeinsamen Snapshot.
Ihr wirklicher Graph muss Straße, Depot und beide Haltestellen verbinden,
bevor ein Fahrzeug gekauft wird. Der generische `ROAD`-Befehl des früheren
Adapters bleibt gesperrt; diese begrenzte Verbindung nutzt ausschließlich die
bereits verifizierten Testobjekte. Spielinterne Nummern dürfen auf beiden PCs
verschieden sein. Originale Spielmodelle werden nur lokal referenziert.

## Abschluss, Berichte und Unterbrechung

Vor dem Ende des Aufbaus prüft jeder Teilnehmer die Testobjekte, tatsächliche
Straßenverbindung, Fahrzeug- und Linienmitgliedschaft, Kaufabbuchung, Abfahrt
ohne Pfadfehler und mindestens einen Meter Bewegung an unterschiedlichen
bestätigten Simulationszeiten. Identische, aber unvollständige Vorgänge ergeben
keinen Bauabschluss. Danach muss zusätzlich der gewählte Fahrtversuch enden.

`peer-journal.jsonl` enthält die Bauzustände und ausschließlich frische
Weltbeobachtungen der Fahrt: Start, Kontrollpunkte und vorgegebene
Pauseänderungen. Native Antworten ohne Weltbeobachtung stehen mit ihren
Zeitmessungen in `stream.chunk_records`; sie erzeugen keinen vorgetäuschten
aktuellen Journalsnapshot. Im Fehlerfall wird der gespeicherte Snapshot als
zuletzt beobachtet gekennzeichnet. `last_observed_frame` und
`last_observed_sim_time_us` unterscheiden dessen Grenze vom gegebenenfalls
weiteren nativen Fortschritt. Das Journal bleibt auf 64 MiB begrenzt.

Die normalen Bericht-ZIPs enthalten Peerbericht, Journal und beim Host den
Koordinatorbericht. Beide Berichte privat zur Auswertung weitergeben und
zusätzlich kurz die Fahrzeugbewegung beschreiben. Historische Berichte und
Ausgangsspielstände nicht überschreiben. Die Daten werden nicht veröffentlicht.

Bei einem strikten Baufehler kann die Mod unabhängig vom fehlgeschlagenen
Zustandsleser eine begrenzte API-Rohdiagnose erzeugen. Diese ist als ungültiger
Snapshot gekennzeichnet, auf 98304 Bytes begrenzt und getrennt von der letzten
bestätigten Welt im Export enthalten. Es ist keine weitere Solo-Diagnose nötig.

Normale UI-Pausetasten, freie gleichzeitige Bauwünsche, konkurrierende Umbauten,
Cursor, Speichern/Fortsetzen, unbeobachtete Weltobjekte und langfristige
Wirtschaft sind mit diesem Ablauf noch nicht nachgewiesen. Auch bei gehaltener
Spielzeit kann interne Wartungs- und Befehlsarbeit weiterlaufen.

Lokales Stoppen wird zwischen Freigaben geprüft. Eine bereits freigegebene
Serie kann im Dauertest noch bis zu zwei Schritte ausführen, bevor die
TCP-Schleife eine entfernte Unterbrechung verarbeitet: bis zu 0,4 Sekunden
Spielzeit, nicht eine zugesicherte Reaktionsdauer in Echtzeit. Im
Vergleichsmodus sind noch bis zu 25 Schritte möglich. Operationen haben
begrenzte Wallzeitbudgets. Fehler schließen die Sitzung dauerhaft; es gibt
keinen verteilten Rollback oder automatisches Weiterlaufen nach Abbruch.
