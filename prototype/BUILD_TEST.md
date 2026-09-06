# Alpha5.1: automatischer Bau- und Fahrzeugversuch

Dieses Paket erweitert den erfolgreich abgeschlossenen Alpha4.2-Zeitversuch um
ein festes Bauprofil auf der unveränderten Ausgangskarte. Die native ABI-3-
Schrittsteuerung und die Alpha4.2-Dateisperrkorrektur bleiben unverändert.
Die neue Szene ist noch nicht in zwei echten TF2-Instanzen bestätigt.

Außerdem korrigiert Alpha5 einen Rundungsfehler beim Übergang vom Laden zum
laufenden Protokoll. Bei zwei identischen Messwerten der Windows-Uhr konnte
die bisherige Rechenreihenfolge die Protokollzeit minimal zurücksetzen und
einen sofortigen Stopp auslösen. Die neue Reihenfolge erhält den Zeitursprung.

## Fester Ablauf in beiden Spielen

| Runde, ab null gezählt | Eingabe stammt von | Gemeinsame Aktion |
|---|---|---|
| 0 | Host a | Pause |
| 1 | Host a | T-förmige Teststraße bauen |
| 2 | Mitspieler b | Straßendepot bauen |
| 3 | Host a | Erste Personenhaltestelle bauen |
| 4 | Mitspieler b | Zweite Personenhaltestelle bauen |
| 5 | Mitspieler b | Ein verfügbares Personenfahrzeug von 1850 kaufen |
| 6 | Host a | Linie mit beiden Haltestellen anlegen |
| 7 | Mitspieler b | Fahrzeug der Linie zuweisen |
| 8 | Host a | Simulation fortsetzen |
| 80 | Host a | Gemeinsame Pause |
| 100 | Mitspieler b | Simulation fortsetzen |
| bis einschließlich 239 | beide | Gleiche Zeitpunkte und beobachtete Zustände bestätigen |

Beide Spiele führen jeden Befehl aus. Die wechselnde Herkunft prüft die beiden
Eingabewege; niemand muss diese Aktionen manuell auslösen. Die Runden enthalten
28 Pausenschritte und 212 echte Schritte à 200000 Mikrosekunden, insgesamt
42,4 Sekunden Enginezeit. Die Wartezeiten im Netzwerk zählen nicht als Spielzeit.

## Identitäten und Baustelle

Das Lua-Profil `build_v1` sucht vor der ersten Änderung deterministisch eine
freie, über Wasser liegende Baustelle. Alpha5.1 ersetzt die 81 zentralen Stellen
durch bis zu 4225 Punkte über den anhand gültiger Koordinaten ermittelten
Kartenbereich. Die Suche ist auf 32768 Meter je Achsrichtung begrenzt und meldet
es, wenn diese Grenze erreicht wird. Gute Kandidaten werden mit 169 Geländeproben
verfeinert. Bevorzugt sind höchstens zwei Meter Höhenstreuung; ansonsten ist die
beste geprüfte freie Stelle mit höchstens acht Metern zulässig. Ihre Bauhöhe
ist die Mitte zwischen dem niedrigsten und höchsten gemessenen Geländepunkt.

Die eigene Straßenkonstruktion ebnet als Teil ihres gemeinsam ausgeführten
Bauvorgangs ein Rechteck von 280 × 160 Metern. Dieses umfasst die tatsächlichen
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

Die Straße ist eine eigene kleine `STREET_CONSTRUCTION`. Ihr wirklicher
Callback liefert die Konstruktion; deren tatsächliche Straßenkanten und Knoten
liefern die überprüfbare Verbindung zu Depot und Haltestellen. Der generische
`ROAD`-Befehl des früheren Adapters bleibt weiterhin gesperrt. Gleiche räumliche
Koordinaten reichen nicht als Nachweis einer Straßenverbindung.

Spielinterne Nummern dürfen auf beiden PCs verschieden sein. Gemeinsame
logische Kennungen werden ausschließlich an tatsächliche Rückgabeobjekte und
deren bestätigte Komponenten gebunden. Originale Spielmodelle und Konstruktionen
werden aus der lokalen TF2-Installation verwendet, nicht mitverteilt.

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
