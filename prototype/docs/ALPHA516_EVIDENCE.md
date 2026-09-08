# Alpha5.16: tatsächlicher Zwei-PC-Depotversuch

Stand nach zwei Läufen: Zusätzlich zum ersten Depotversuch hat der zweite
Versuch vom 8. September echte Wünsche beider Spieler in derselben Sammelrunde
erfasst: zwei verschiedene Plätze erfolgreich und ein gemeinsamer Platz mit
genau einem Bau und kostenfreier Ablehnung. Der Nachtrag unten dokumentiert
diesen zusätzlichen Nachweis; die folgenden ersten Abschnitte gelten für
den ersten Lauf.

Die beiden zuerst vom Nutzer gelieferten Berichte vom 8. September 2026 bestätigen
den begrenzten Launcher-Depotversuch mit v0.5.16, Commit
`79d666ff2b45f125d5ea18c7f1a674fb71c538b9`. Beide Teilnehmer und der Koordinator
haben regulär abgeschlossen. Es gab keinen terminalen nativen Laufzeitfehler.
Der abschließende Lua-Status `controller requested halt` ist die vorgesehene
Bereinigung nach dem gemeinsam bestätigten Ende.

## Tatsächlich beobachtete Bauaufträge

| Auftrag | Grenze | Zustand | Ergebnis | Tatsächliche Kosten |
|---|---:|---|---|---:|
| Host: Platz 1, 0° | 106 | Fahrt | Depot gebaut | 13.143 |
| Mitspieler: Platz 2, 90° | 132 | Pause | Depot gebaut | 12.692 |
| Host: Platz 3, 180° | 162 | Fahrt | Depot gebaut | 10.000 |
| Host: Platz 4, 90° | 280 | Fahrt | Depot gebaut | 10.000 |
| Mitspieler: Platz 4, 270° | 282 | Fahrt | Belegten Platz abgelehnt | 0 |

Alle vier erfolgreichen Aufträge haben auf beiden PCs jeweils eine neue
Konstruktion und das zugehörige Depotobjekt erzeugt. Beobachtete Positionen,
Drehungen, Bindungen und Register stimmen mit den bestätigten Aufträgen überein.
Die tatsächlichen Kontoabbuchungen entsprechen Vorschau und Callback; zusammen
sind es 45.835. Vorherige erfasste Objekte bleiben unverändert. Bei der Ablehnung
bleibt der gesamte erfasste Snapshot einschließlich Geld unverändert.

97 Weltjournalzeilen sind bytegleich. Alle 257 geordneten Live-Aktionen und
neun abgerechneten Eingaben passen in Host- und Teilnehmerberichten zusammen.
Die frischen Vorschauen, Ergebnisse und Kontrollpunkte stimmen überein; zwischen
Prüfung, Anwendung beziehungsweise Ablehnung und gemeinsamer Bestätigung läuft
kein nativer Fortschrittsschritt. Die zehnrundige Bereitschaft wurde aus den
tatsächlichen Rückmeldungen erneut geprüft. 47 öffentliche Payload-Dateihashes
passen zum ausgelieferten Paket.

Der gemeinsame Endstand ist Frame 338, Enginezeit 79,2 Sekunden, Pause,
Kontostand 4.605.841 und Kredit 5.000.000. Alle 328 zusätzlichen Fortschrittsschritte
sind lückenlos mit genau 200 Millisekunden bestätigt. Die Hashes aller erfassten
Weltgrenzen wurden bei der Auswertung erneut berechnet und verglichen.

## Tempo und Bauunterbrechungen

| Messung | Host | Mitspieler |
|---|---:|---:|
| Zusätzliche Simulationszeit | 65,600 s | 65,600 s |
| Normale Fahrt zwischen Bauaufträgen | 0,946689x | 0,950844x |
| Aktiver Durchschnitt einschließlich Bauprüfungen | 0,904032x | 0,904892x |
| Zusätzliche Zeit an vier Bau-/Ablehnungsgrenzen | 3,270 s | 3,503 s |
| Median normaler nativer Bestätigungsabstände | 201,001 ms | 202,244 ms |
| 95. Perzentil normaler Bestätigungsabstände | 219,855 ms | 217,754 ms |
| Größter normaler Bestätigungsabstand | 415,358 ms | 407,643 ms |

Die Berechnung verwendet dieselbe Konvention wie die akzeptierte Alpha5.15-Referenz:
pro zusammenhängendem Fahrabschnitt letzte native Bestätigung minus erster
nativer Aufruf plus 200 Millisekunden. Die aktive Messung trennt nur an echten
Pausen. Die normale Fahrt trennt zusätzlich an jedem während Fahrt bearbeiteten
Depotauftrag, einschließlich Ablehnung. Alle 328 Schritte zählen in beiden
Messungen; die vier regulären Weltkontrollpunkte bleiben enthalten. Bewusste
Pausen einschließlich des dort gebauten Depots sind keine aktive Fahrzeit.

Bei den drei während Fahrt erfolgreichen Bauten lagen zwischen benachbarten
nativen Bestätigungen etwa 1,20 bis 1,40 Sekunden, bei der Ablehnung etwa
0,80 Sekunden. Die gemeinsame Prüfung und Ausführung kostet weiterhin Zeit.
Der gesamte Bauversuch darf daher nicht als 0,95x-Fahrt ausgegeben werden.
Der kurze automatische Vorlauf dauerte 12,890 Sekunden.

Die normale Fahrt liegt in dieser Stichprobe im gewünschten Bereich und zeigt
gegenüber der akzeptierten Alpha5.15-Messung mit etwa 0,94x keine Verschlechterung.
Der Nutzer meldete einen gut verlaufenen Versuch, hat diesmal aber nicht gezielt
auf sichtbare Ruckler geachtet. Native Zeitmessungen sind keine Renderzeiten oder
FPS-Messung. Die bisherigen Alpha5.15- und Alpha5.12-Referenzen bleiben erhalten.

## Grenzen des ersten Laufs

Der zweite Auftrag für Platz 4 kam in der nächsten Sammelrunde an, 0,4 Sekunden
Simulationszeit nach dem ersten. Die Ablehnung eines bereits belegten Platzes
ist damit im Spiel bestätigt. Zwei konkurrierende Aufträge in derselben
Sammelrunde wurden in diesem Lauf nicht erfasst; die entsprechenden
Berichtsfelder sind leer. Der unten beschriebene zweite Lauf schließt diese
konkrete Lücke im Spiel; der erste Lauf wird dadurch nicht umbewertet.

Erfolgreiche Platzierungen umfassen 0°, 90° und 180°. Der 270°-Wunsch wurde
abgelehnt und beweist keinen erfolgreichen Bau mit dieser Drehung. Andere
Ablehnungsgründe wie Wasser, Gelände, Geldmangel oder Engine-Kollisionen sind
durch diesen Lauf nicht nachgewiesen. Die neuen API-Vorschauen funktionierten
für die beobachteten erfolgreichen Aufträge; unbekannte Rückgabeformen bleiben
eine Grenze mit kontrolliertem Abbruch.

Host-Pause und Fortsetzen durch den Mitspieler wurden benutzt, ebenso eine
weitere Host-Pause vor dem Ende. Dieser neue Depotversuch wiederholt nicht alle
Pausefälle oder die lange Pause aus Alpha5.15. Eine solche Wiederholung ist
keine Voraussetzung für seine Depotabdeckung.

Die erfolgreiche Verbindung zeigt eine übereinstimmende neue gemeinsame
Sitzungskennung und unterschiedliche lokale/native Kennungen. Ein einzelner
Lauf beweist nicht das Beibehalten privater Einstellungen über mehrere Updates;
die exportierten Berichte enthalten auch keine Schlüssel zur unabhängigen
erneuten Prüfung der Nachrichtenauthentisierung.

Normale TF2-Bauwerkzeuge, native UI-Pause, freie konkurrierende Umbauten,
Speichern/Fortsetzen und vollständige Weltentwicklung sind weiterhin offen.
Als nächste funktionale Etappe bleibt ein begrenztes normales Bauwerkzeug, dessen
lokale Ausführung vor der gemeinsamen Freigabe sicher zurückgehalten wird.
Der Konflikt in derselben Sammelrunde wurde im zweiten Lauf mit demselben
kurzen automatischen Vorlauf gezielt erfasst.

## Zweiter Lauf: beide Arten gleichzeitiger Bauwünsche bestätigt

Die nach dem gezielten Gleichzeitigkeitstest gelieferten Berichte bestätigen
zwei gemeinsame Eingabelisten mit Wünschen beider Spieler. Es geht um dieselbe
Sammelrunde des Protokolls; die genaue Gleichzeitigkeit der Mausklicks wird
nicht gemessen.

| Gemeinsame Grenze | Wünsche in derselben Sammelrunde | Ergebnis auf beiden PCs |
|---|---|---|
| Frame 136, Enginezeit 38,8 s | Host: Platz 1, 0°; Mitspieler: Platz 2, 90° | Beide gebaut, Kosten 13.143 und 12.692 |
| Frame 296, Enginezeit 70,8 s | Host: Platz 4, 90°; Mitspieler: Platz 4, 270° | Host-Depot gebaut für 10.000; zweiter Wunsch ohne Kosten abgelehnt |

In beiden Fällen wurde der erste Bau beidseitig bestätigt, bevor der zweite
Wunsch seine frische Vorschau erhielt. Die zweite Vorschau bezieht sich
nachweislich auf den beobachteten Zustand nach dem ersten Bau, einschließlich
der Abbuchung und neuen Objektbindungen. Die Enginezeit blieb innerhalb
der gesamten jeweiligen Baufolge gleich. Beim gemeinsamen Platz ist nach
dem ersten Bau genau ein Depot vorhanden; die Ablehnung verändert den erfassten
Zustand nicht. Die feste Reihenfolge innerhalb einer Sammelrunde ordnet den
Host vor dem Mitspieler; sie ist keine Aussage über frühere Mausklicks.

Insgesamt wurden erneut vier Depots gebaut und drei Wünsche für belegte Plätze
kostenfrei abgelehnt. Platz 3 wurde vom Mitspieler an Frame 230 gebaut; der
Host-Wunsch an Frame 236 kam später und wurde abgelehnt. Ein weiterer Wunsch
des Mitspielers für seinen bereits bebauten Platz 2 wurde an Frame 138 ebenfalls
abgelehnt. Diese beiden Fälle sind getrennt vom Konflikt in derselben Runde.
Alle acht Eingaben einschließlich Abschluss wurden bestätigt.

Die 49 Weltjournalzeilen sind bytegleich, 47 öffentliche Payload-Dateihashes
passen weiterhin zur unveränderten v0.5.16. Alle tatsächlichen Objektbindungen,
Positionen, Drehungen und Kontoabbuchungen wurden erneut geprüft. 342 zusätzliche
native Schritte ergeben 68,4 Sekunden bei genau 200 Millisekunden je Schritt.
Gemeinsamer Abschluss: Frame 352, Enginezeit 82,0 Sekunden, laufend,
Kontostand 4.605.841, Kredit 5.000.000. Es gab keinen terminalen nativen Fehler.

Normale Fahrt zwischen Bauaufträgen lag mit derselben Messmethode bei
0,947705x/0,948396x. Einschließlich der sieben Bauwünsche an fünf Baugrenzen
lag der aktive Durchschnitt bei 0,888764x/0,888968x. Das Auftragsbündel mit zwei
erfolgreichen Bauten erzeugte etwa 2,0 Sekunden zwischen benachbarten nativen
Bestätigungen, der gemeinsame Platz etwa 1,6 Sekunden. Der Mitspieler hatte
außerdem einen normalen Bestätigungsabstand von etwa 611 Millisekunden.
Die durchschnittliche Fahrt bleibt ungefähr 0,95x; sie garantiert keine
durchgehend gleichmäßigen Renderzeiten.

Dieser Versuch enthält keine manuelle Pause und keinen Bau während Pause.
Deshalb ist `required_depot_interactions_met` für diesen einzelnen Lauf falsch,
während der gemeinsame Abschluss und die beiden Gleichzeitigkeitsergebnisse
bestätigt sind. Der Bau während Pause bleibt durch den ersten Lauf belegt.
Die allgemeinen `conflict`-Felder der Eingabelisten betreffen Pausekonflikte;
der hier geprüfte Depotkonflikt steht in `same_batch_conflicts_verified`.

Der praktische Nachweis gilt für die begrenzten Launcher-Depotaufträge auf
dieser Karte. Er umfasst keine anderen Gebäudetypen, freien Bauwerkzeuge,
Knappheit des gemeinsamen Guthabens, Wiederherstellung nach einem Teilfehler
oder vollständige Weltentwicklung. Die nächste funktionale Etappe bleibt
das sichere Anschließen eines normalen Bauwerkzeugs.

## Erhaltung

Originalberichte, drei unabhängige Auswertungsskripte, Ergebnisdateien und
Prüfsummen bleiben privat unter `prototype/results/alpha516-two-pc-20260908-1946`
für den ersten und `prototype/results/alpha516-two-pc-20260908-2013` für den
zweiten Lauf. Die ursprünglichen Belege werden nicht überschrieben.
Öffentlich wird nur diese Auswertung dokumentiert. Der Release-Tag, das Paket
und die früheren Referenzen werden durch die Dokumentation nicht verändert.

- Öffentliche ZIP-SHA-256:
  `7f2a7dd10c4156fe3caad0cc3a22e0b94b5f4f7794ebc2bcc8495402de0614c8`
- Identisches beobachtetes Weltjournal:
  `a5c5cd7c29341dfd2a0f0940d61570000d946a085093ef4265ff803f01b977bd`
- Finaler Hash der erfassten Welt:
  `7fec9047dc158ec8de817e5609b94e8df0a76c26d2432c4f571fb5d8007fd900`
- Identisches Weltjournal des zweiten Laufs:
  `0db59f938f71ef898bbd1a62cf51cc085e434c19c23858ce1d153a5b7cf10728`
- Finaler Hash des zweiten Laufs:
  `77f8d80bdb4f02e71c721ff5386d1cd7c8503a6fa7be8b9122b3a0f4db38c6a0`
