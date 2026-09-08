# Alpha5.19: tatsächlicher geführter Zwei-PC-Durchlauf

Ausgewertet wurden die beiden vom Nutzer gelieferten TF2-Berichte vom
8. September 2026, 23:16 Uhr. Beide Spiele verwendeten das veröffentlichte
`v0.5.19`, Commit `f3f9262328c50d892f6eeb4e6b936aef0ea5712e`.
55 aufgezeichnete Python-/Mod-/Native-Dateiprüfsummen passen zum Releasepaket.
Die privaten Originalberichte und reproduzierbaren Auswertungen sind lokal
gesichert und werden nicht im öffentlichen Repository abgelegt.

## Gemeinsamer Abschluss und tatsächliche Ergebnisse

Alle **26 festen Host-/Freund-Schritte** wurden genau einmal in Katalogreihenfolge
bestätigt. 241 Weltjournalzeilen sind auf beiden PCs bytegleich. Die tatsächlichen
Vorschauen, Ergebnisrückmeldungen und zugehörigen beobachteten Objekt-/Firmenwerte
wurden bei der Auswertung nochmals gemeinsam geprüft. Die zehnrundige kurze
Vorbereitung besteht ebenfalls; sie ist kein vollständiger langer BuildProof.

Der geführte Ablauf enthält 24 tatsächliche Mutations-Callbacks und zwei getrennte
reine Beobachtungen für Fahrt und Depotankunft. Nachgewiesen sind im festen Szenario:

- Kauf eines zusätzlichen Straßenfahrzeugs mit 23.890 Abbuchung auf beiden PCs.
- Leere Linie anlegen; Halte einzeln hinzufügen, entfernen, wiederherstellen und
  umordnen; Linienname und Farbe ändern; Fahrzeugname ausdrücklich setzen.
- Wartungsziel ändern und das Fahrzeug mit passendem Linienbestand zuweisen.
- Gemeinsame Pause durch Host und Freund sowie Fortsetzen durch den Host.
- Fahrt mit beobachteter Positionsänderung von 4,869 Metern zwischen 30,0 und
  32,4 Sekunden Simulationszeit sowie positiver Geschwindigkeit.
- Fahrzeug anhalten und starten: gesetztes Stoppflag, später gemessener Stillstand,
  zurückgenommenes Flag und danach wieder beobachtete Bewegung.
- Feste Halteregeln setzen (`load_mode=1`, minimale Wartezeit 0, maximale Wartezeit
  10); Wendebefehl mit beobachteter Änderung des Fahrwegs/Zustands ohne Pfadfehler.
- Depotfahrt, tatsächliche Ankunft, Verkauf mit 23.777 Gutschrift und bestätigtem
  Entfernen des Fahrzeugs; anschließend die nicht mehr verwendete Linie löschen.

Die erste Depotankunftsprüfung war bei Frame 242 noch nicht bereit. Sie kostete
nichts, änderte den beobachteten Zustand nicht und gab keinen Schritt vorzeitig
frei. Derselbe Auftrag bestand nach der tatsächlichen Ankunft bei Frame 276.
Daher gibt es **27 Eingaben für 26 abgeschlossene Schritte**. Alle Eingaben sind
lückenlos bestätigt: Host Sequenz 1–14, Freund 1–13. Alle Sammelrunden enthalten
jeweils genau eine Eingabe; dies ist kein neuer Gleichzeitigkeitstest.

Der Host bestätigt den gemeinsamen Abschluss nach beiden Endergebnissen. Beide
Peerberichte bestätigen ihren lokalen Abschluss und den empfangenen Hostabschluss.
Ihr Feld `coordinated_completed=false` ist der ausdrücklich lokale Berichtsumfang,
kein fehlender gemeinsamer Abschluss.

Endzustand: **Frame 304, Simulationszeit 72,4 Sekunden, Kontostand 4.651.328,
Kredit 5.000.000**, auf beiden PCs gleich. Die 294 nativen Live-Fortschrittsschritte
betragen jeweils exakt 200 Millisekunden. Keine terminalen Native- oder Lua-Fehler;
der abschließende angeforderte Halt ist das reguläre Schließen des Adapters.

## Taktung im gemessenen Umfang

| Messbereich | Host | Freund |
| --- | ---: | ---: |
| Normales Laufen ohne Eingabegrenzen | 0,9462x | 0,9449x |
| Aktives Laufen einschließlich dazwischenliegender Eingabeprüfungen | 0,8605x | 0,8589x |

Die erste Zeile trennt an jeder laufenden Eingabegrenze und enthält den tatsächlich
aufgetretenen normalen periodischen Kontrollpunkt. Die zweite lässt die dazwischen
liegenden Eingabeprüfungen im Zeitbudget. Bewusste Pausen und Randkosten an
Pause-/Endgrenzen sind in beiden aktiven Schätzungen ausgenommen. Die laufenden
Interaktionsgrenzen benötigen insgesamt etwa 6,2 zusätzliche Sekunden je PC.
Das ist keine Messung von Render-FPS oder genauer Klicklatenz.

Gemessen wurden 58,8 Sekunden laufende Simulationszeit, eine normale periodische
und 27 eingabeausgelöste Zustandsprüfungen. Die beiden gemeinsamen Pausen lagen
zwischen bestätigten Pause-/Fortsetzen-Ergebnissen bei etwa 68,2 und 30,6 Sekunden;
die kurze Vorbereitung dauerte im Hostablauf 13,14 Sekunden. Die normale Taktung
liegt damit in der Größenordnung der erhaltenen Alpha5.15-/Alpha5.16-Referenzen.
Dieser kurze interaktive Lauf ersetzt deren frühere Nachweise nicht.

## Was daraus nicht folgt

Die neuen Häkchen in der [Funktionscheckliste](GAMEPLAY_CHECKLIST.md) gelten für
die feste Straße, das konkrete Fahrzeugmodell und die Launcher-Aufträge. Normale
Ingame-Werkzeuge und native Pause-Tasten sind weiterhin nicht angeschlossen.
Schienen, Signale, Züge, Frachtregeln über die gesetzten Felder hinaus, Gelände,
Speichern/Wiederbeitritt und vollständige Weltdeterministik bleiben offen.

Gleichzeitige Fahrzeug-/Linienkonflikte, knappe gemeinsame Mittel, doppelte,
veraltete oder rollenfalsche Eingaben wurden in diesem tatsächlichen Lauf nicht
ausgelöst. Headless-Fehlerprüfungen ersetzen diese Spielnachweise nicht. Die
früheren tatsächlich getesteten Depotkonflikte bleiben separat gültig.

Die Auswertung ändert keinen Laufzeitcode und kein Releasepaket. Alpha5.19 und
die älteren akzeptierten Versionen bleiben unverändert erhalten.
