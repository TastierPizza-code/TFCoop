# Alpha5.7: automatischer Bau- und Fahrzeugversuch

Dieses Paket erweitert den erfolgreich abgeschlossenen Alpha4.2-Zeitversuch um
ein festes Bauprofil auf der unveränderten Ausgangskarte. Die native ABI-3-
Schrittsteuerung und die Alpha4.2-Dateisperrkorrektur bleiben unverändert.
Die neue Szene ist noch nicht in zwei echten TF2-Instanzen bestätigt.

Alpha5.7 behandelt zwei grundlegende Probleme: Der Skript-Bauweg verbindet
aufeinanderliegende Construction-Anschlüsse nicht automatisch wie das UI;
die bisherige Testnachbildung nahm das fälschlich an. Außerdem durfte ein
vorübergehender Dateilesefehler nach einem Callback die Bauantwort verdrängen.

Depot und Haltestellen stehen nun mit 20 m Abstand zu den Straßenenden. Ein
separater gemeinsamer Bauauftrag verbindet sie über bereits vorhandene,
autoritativ beobachtete Knoten. Eine Bauantwort wird genau einmal verarbeitet;
bei kurzzeitig unlesbarer Statusdatei bleibt der Auftrag unbestätigt, bis dieselbe
Grenze und Zeit wieder geprüft werden können. Kein erneutes Senden oder
Simulationsschritt ist dafür erlaubt. Ablehnungen bleiben endgültig und behalten
ihre ursprünglichen Callback-Daten in einer getrennten begrenzten Diagnose.

Beide echten Alpha5.6-Berichte enthalten dieselben ersten fünf Journaleinträge:
Ausgangszustand, angewandte Pause, Pausenschritt, angewandte Straße und zweiter
Pausenschritt. Zeit 13,4 Sekunden; Geld nach Straße 4.928.623 bei Kredit 5.000.000.
Beim Depotauftrag meldet b ausdrücklich `success=false`; a verliert die
Callback-Aussage durch einen Statuslesefehler. Beide historischen Endsnapshots
zeigen nur die Straße. Daraus folgt kein beobachteter Welt-Desync und noch kein
Beweis der genauen nativen Depot-Ablehnungsursache. Die getrennten Rohdaten
bestätigen jetzt auch `timeBuild=nil` an der erfolgreich gebauten Straße.

Der nächste gemeinsame Versuch nutzt auf beiden PCs einen frischen Sitzungscode
und neue Testsave-Kopien. Nur Strict Sync Alpha5.7 und Legacy Fahrzeuge aktivieren.
Eine Solo-Diagnose ist nicht nötig; die komplette Bedienfolge steht in
[ANLEITUNG.md](ANLEITUNG.md).

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

## Abschluss und Diagnose

Vor der letzten Schrittbestätigung prüft jeder Teilnehmer alle Testobjekte,
die tatsächliche Straßenverbindung, Fahrzeug- und Linienmitgliedschaft, die
beim Kauf beobachtete Abbuchung, Abfahrt ohne Pfadfehler und mindestens einen
Meter Bewegung an unterschiedlichen bestätigten Simulationszeitpunkten.
Ein auf beiden PCs identischer, aber unvollständiger Ablauf ergibt keinen Erfolg.
Der gemeinsame Abschluss erfordert die Bestätigung beider Teilnehmer.

`peer-journal.jsonl` zeichnet die beobachteten Zustände und Bau-/Fahrphasen auf;
`peer-report.json` enthält den abschließenden Nachweis und tatsächliche Geldänderungen.
Diese Dateien sind im Berichtsexport enthalten. Fehlersnapshots sind als zuletzt
beobachtet gekennzeichnet. Ein Journal ist auf 64 MiB begrenzt.

Bei einem strikten Bauabbruch erfasst der Mod außerdem automatisch eine unabhängige
API-Rohdiagnose der aktuell gebundenen Objekte. Sie ist auf 98304 Bytes begrenzt,
weist `valid_snapshot=false` aus und wird als separate `lua_api_audit.json` in
den normalen Testberichtsexport aufgenommen. `lua_status.json` enthält nur den
Dateihinweis, den Schreib-/Rücklesestatus, begrenzte Fehlversuchsmetadaten
und die getrennt markierten tatsächlichen Callback-Daten. Bis zu 16 Bindings
passen in die Erfassung; globale Byte-/Zeilenlimits bleiben bestehen.
Rohe Fließkommazahlen bleiben außerhalb des strikten Synchronitätsprotokolls;
der letzte gültige Snapshot ist getrennt als historisch markiert.
Die Erfassung hängt nicht vom bereits fehlgeschlagenen Zustandsleser und nicht
von einer aktiven Solo-Diagnosemod ab. Sie ist weder ein Ersatzsnapshot noch ein
zusätzlicher Synchronitätsnachweis. Deshalb nach Abbruch oder Abschluss die
**normalen Testbericht-ZIPs beider PCs** exportieren; keine weitere Solo-Diagnose starten.

Der Nachweis umfasst die Testszene, Firmenwerte und gemeinsame Enginezeit.
Ein Teilnehmer erzeugt den jeweiligen Pause-/Weiterlaufwunsch; der Koordinator
ordnet ihn gemeinsam ein und wartet auf beide Bestätigungen. Die normale
Pause-Taste im Spiel und die Annahme konkurrierender freier Bauwünsche werden
damit noch nicht getestet. Die Spieloberfläche speist noch keine Eingaben in
diesen kontrollierten Ablauf ein.
Unbeobachtete Weltobjekte, langfristige Wirtschaft, freie Baueingaben, konkurrierende
Umbauten, Speichern/Fortsetzen und Cursor sind damit weiterhin nicht nachgewiesen.
Die tatsächliche Annahme der Bauvorschläge, Straßenverknüpfung und Fahrzeugfahrt
müssen in eurem neuen Zwei-PC-Test bestätigt werden.
