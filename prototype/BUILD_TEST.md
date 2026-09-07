# Alpha5.11: Aufbau, ungleiche Wartezeiten und 1x-Fahrtabschnitte

Der aktuelle Versuch besteht aus dem bisherigen Bauprofil `build_v2` und dem
anschließenden Messprofil `hold-and-pace-v1`. Die saubere Basis der bisherigen
sehr großen Karte aus Alpha5.9 bleibt unverändert. Beide PCs brauchen einen
frischen gemeinsamen Code und neu vorbereitete Testsave-Kopien. Strict Sync
Alpha5.11 und Legacy Fahrzeuge sind darin bereits ausgewählt. Ein bestehender
passender Savecache genügt; die Bedienfolge steht in [ANLEITUNG.md](ANLEITUNG.md).

**Echte Evidenz:** Alpha5.10 bestand den vollständigen Aufbau in zwei nacheinander
gestarteten TF2-Prozessen auf einem PC. Record und Replay bestätigten zwölf
Aufträge, 240 Schritte und gleiche beobachtete Ergebnisse nach jeder Aktion.
Verbindung der Teststraßen, Kauf, Linienfahrt und Pausen wurden tatsächlich
ausgeführt. **Die neuen Alpha5.11-Fahrtabschnitte sind bislang nur ohne TF2
geprüft.** Ihr gemeinsamer Zwei-PC-Versuch steht aus. Frühere Alpha5.7-/5.8-
Abbrüche sind historische Befunde im [Prüfstand](VERIFICATION.md).

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

## Zwölf zusätzliche Fahrtabschnitte

Nach dem bestätigten Aufbau folgen zwölf Abschnitte aus jeweils **25 Schritten
à 0,2 Sekunden**, also fünf Sekunden Simulationszeit. Zusammen kommen weitere
60 Sekunden hinzu. Die Zielgeschwindigkeit ist ausschließlich **1x**. Native
Schrittweite, ABI und Bauprofil bleiben unverändert.

| Abschnitt | Phase | Zusätzliche lokale Wartezeit vor der gemeinsamen Freigabe |
|---|---|---|
| 1–3 | Ausgangsmessung | Keine |
| 4 | Ungleiche Wartezeit | Host a: 1000 ms |
| 5 | Ungleiche Wartezeit | Mitspieler b: 1500 ms |
| 6 | Ungleiche Wartezeit | Host a: 250 ms |
| 7 | Ungleiche Wartezeit | Mitspieler b: 750 ms |
| 8 | Ungleiche Wartezeit | Host a: 3000 ms |
| 9 | Ungleiche Wartezeit | Mitspieler b: 500 ms |
| 10–12 | Vergleich nach den Wartephasen | Keine |

Die angegebenen Zeiten werden lokal künstlich eingefügt. Sie sind keine Messung
der Netzwerk-Roundtripzeit. Der andere PC meldet seine Bereitschaft ohne diesen
Zusatz; der Koordinator wartet vor dem gemeinsamen Start auf beide Teilnehmer.

Vor jedem Abschnitt werden fester Plan, Ausgangsgrenze, erfasster Zustand und
eigene Wartezeit geprüft. Erst nach beiden Bestätigungen ist die Serie
freigegeben. Zwischen den Schrittanforderungen der Steuerung liegen mindestens
200 ms; Verzögerungen verschieben den Zeitplan ohne Aufholserie der Anforderungen. Pro Freigabe müssen native
Uhr, Frame und Auftragsabschluss stimmen. Die Lua-Weltbeobachtung erfolgt am
Anfang und Ende des Abschnitts. Der nächste Abschnitt beginnt erst, wenn beide
Endzeiten, Frames und erfassten Zustandsprüfsummen übereinstimmen.

Der kombinierte Ablauf endet bei Protokollframe 540: 240 Aufbauschritte plus
300 zusätzliche Fortschrittsschritte. Der Bau-Rundenzähler bleibt nach dem
Aufbau bei 240; die Anzeige wechselt auf Abschnitt 1 bis 12. Ein abgebrochener
oder nur einseitig beendeter Abschnitt ergibt keinen gemeinsamen Abschluss.

## Messwerte und Tempoauswertung

`admitted_offset_us` misst den lokalen Aufrufbeginn von `native.permit()`,
vor dessen Dateiübertragung und Warten auf Bestätigung. Die native Ankunftszeit
ist damit nicht erfasst. `ack_observed_offset_us` misst, wann die Steuerung die
Bestätigung liest. Unterschiede in der Dateiübertragung können die tatsächlichen
Schrittanfänge verschieben; deshalb muss die sichtbare Fahrt gesondert beurteilt werden.

`timing` in Host-/Peer-Berichten enthält erwartete und ausgeführte Wartezeiten,
lokale Wallzeit, Anfangs-/Endgrenzen, native Diagnosedaten und jede Freigabe samt
beobachteter Bestätigung. Zeitstempel verschiedener PCs werden nicht voneinander
abgezogen. Native HOLD-/Aufrufzähler zeigen zusätzliche Wartungsarbeit, sofern
frische Samples sie belegen. Es sind Diagnosewerte und kein Welthash.

`completed` beschreibt den abgeschlossenen Vergleich. `paced_windows_1x_met`
ist davon getrennt und bleibt ohne vollständige Messdaten offen. Das Tempoziel
verlangt auf beiden PCs in jedem einzelnen Abschnitt:

- Eine gemessene Rate von 950000 bis 1050000 ppm, also 95 bis 105 Prozent des 1x-Ziels.
- Jeweils mindestens 24 Abstände zwischen aufeinanderfolgenden Freigaben und zwischen beobachteten Bestätigungen.
- Für beide Abstandsreihen ein 95. Perzentil von höchstens 250 ms und einen Maximalwert von höchstens 400 ms.

Die Abschnittsdauer umfasst auch die anfängliche und abschließende Weltabfrage.
Die Abstandsreihen gelten nur innerhalb desselben Abschnitts. Die erste
Freigabe und gemeinsame Haltepunkte zwischen Abschnitten gehören nicht dazu;
zusätzliche Wartezeit und gesamte Wallzeit stehen separat im Bericht. Rate und
Dauer sowie einzelne Zeitdifferenzen müssen konsistent sein; unabhängige
Rundung erlaubt höchstens 1 Mikrosekunde beziehungsweise 1 ppm Toleranz.

**Diese Messung bewertet die Steuerung, keine gerenderten Bilder.** Sie bestätigt
weder sichtbare Flüssigkeit noch durchgängiges 1x-Tempo über die gemeinsamen
Übergänge hinweg. Beide Spieler sollen deshalb die Fahrzeugbewegung innerhalb
der Abschnitte beobachten und kurze Angaben dazu mit beiden normalen
Testbericht-ZIPs schicken. Die Hostanzeige bewertet beide PCs; die Anzeige beim
Mitspieler beschreibt dessen lokales Tempoergebnis.

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
Der Alpha5.10-Solovergleich bestätigte die beschriebenen Bauvorgänge; der neue
Zwei-PC-Versuch muss sie und die zusätzlichen Fahrtabschnitte gemeinsam prüfen.
Während der Fahrtabschnitte wird die Welt an deren Grenzen verglichen, nicht
nach jedem inneren Schritt. Die native Uhr bleibt nach jeder Freigabe geprüft.

Lokales Stoppen wird zwischen Freigaben berücksichtigt. Eine bereits gemeinsam
freigegebene Serie kann noch bis zu 25 Schritte laufen, bevor die TCP-Schleife
entfernten HALT oder Verbindungsabbruch verarbeitet. Der Abschnitt hat ein
begrenztes Wallzeitbudget. Es gibt keine sofortige verteilte Unterbrechung,
keinen Rollback und kein automatisches Fortsetzen nach Fehlern.
