# Alpha5.16: tatsächlicher Zwei-PC-Depotversuch

Die beiden vom Nutzer gelieferten Berichte vom 8. September 2026 bestätigen
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

## Grenzen und nächste offene Fälle

Der zweite Auftrag für Platz 4 kam in der nächsten Sammelrunde an, 0,4 Sekunden
Simulationszeit nach dem ersten. Die Ablehnung eines bereits belegten Platzes
ist damit im Spiel bestätigt. Zwei konkurrierende Aufträge in derselben
Sammelrunde wurden in diesem Lauf nicht erfasst; die entsprechenden
Berichtsfelder sind leer. Modellprüfungen dieses Falls bleiben davon getrennt.

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
Der noch offene Konflikt in derselben Sammelrunde muss gezielt erfasst werden,
ohne erneut einen langen automatischen Vorlauf zu verlangen.

## Erhaltung

Originalberichte, drei unabhängige Auswertungsskripte, Ergebnisdateien und
Prüfsummen bleiben privat unter `prototype/results/alpha516-two-pc-20260908-1946`.
Öffentlich wird nur diese Auswertung dokumentiert. Der Release-Tag, das Paket
und die früheren Referenzen werden durch die Dokumentation nicht verändert.

- Öffentliche ZIP-SHA-256:
  `7f2a7dd10c4156fe3caad0cc3a22e0b94b5f4f7794ebc2bcc8495402de0614c8`
- Identisches beobachtetes Weltjournal:
  `a5c5cd7c29341dfd2a0f0940d61570000d946a085093ef4265ff803f01b977bd`
- Finaler Hash der erfassten Welt:
  `7fec9047dc158ec8de817e5609b94e8df0a76c26d2432c4f571fb5d8007fd900`
