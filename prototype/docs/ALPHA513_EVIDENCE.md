# Alpha5.13: tatsächlicher Zwei-PC-Eingabetest vom 8. September 2026

Der Versuch mit Alpha5.13 / `v0.5.13` hat die vorgesehenen gegenseitigen
Pause-/Fortsetzen-Eingaben, eine lange Pause und den gemeinsamen Abschluss
bestanden. Das gilt für die Launchersteuerung und die erfasste Testszene.
Das Fahrttempo ist gegenüber der akzeptierten Alpha5.12-Referenz schlechter;
Alpha5.13 ersetzt diese Referenz nicht.

## Herkunft und unabhängige Nachrechnung

Beide Original-ZIPs sind CRC-fehlerfrei. Ihre gemeinsamen Manifeste sind
gleich; 37 enthaltene Payload-Prüfsummen passen zum veröffentlichten Paket.
Die vollständigen Weltjournale sind mit 380 Zeilen bytegleich. Journal-SHA-256:
`77ab0c519ae481bb59d4eca2b104246bef6e89b948e4ad5d290b413e79402f56`.

Der vollständige Bauabschluss wurde aus den Beobachtungen erneut berechnet.
Die zwölf Baubefehle, 240 Aufbaugrenzen und 29 unveränderten Pausenschritte
passen. Für die anschließende Eingabephase wurden alle 248 nativen
Fortschrittsquittungen je Peer, zehn frische Checkpoints, 108 frische
Pausenprüfungen, sechs tatsächliche Kommandorückgaben und sieben
Eingabe-Batches einschließlich ihrer Hashes erneut geprüft.

Beide Archive, private Auswertungsskripte und Resultate sind lokal gesichert.
Private Spielstände, Sitzungsschlüssel, Rohberichte und persönliche Pfade
werden nicht veröffentlicht.

## Tatsächlich ausgeführte Eingaben

| Gemeinsamer Frame | Eingabe |
|---|---|
| 384 | Host pausiert, anschließend setzt der Mitspieler fort |
| 418 | Mitspieler pausiert, anschließend setzt der Host fort |
| 472 | Mitspieler pausiert länger, anschließend setzt der Host fort |
| 488 | Host fordert den gemeinsamen Abschluss an |

Alle sechs Pause-/Fortsetzen-Befehle waren echte Zustandswechsel. Jeder wurde
an derselben Frame- und Zeitgrenze beider Spiele ausgeführt; die unmittelbar
davor und danach beobachteten Zustände unterscheiden sich nur in `paused`.
Geld, Objekte und Spielzeit änderten sich während dieser Kommandos nicht.
Alle sieben protokollierten Wünsche sind gemeinsam bestätigt: Host a:1–4
und Mitspieler b:1–3. Der Host sandte sieben Commit- und Settlement-Phasen
und erst nach der frischen finalen Weltprüfung den Abschluss an beide Peers.

Die lange Pause dauerte nach gemeinsamer Hostmessung 59,297 Sekunden.
Die lokalen Spannen betragen 59,389 beziehungsweise 59,202 Sekunden. Zusätzlich
zeigen 90 frische Hold-Beobachtungen dieser Pause und die unabhängigen nativen
Zähler mindestens 58,203 beziehungsweise 58,187 Sekunden unveränderte
Simulationsgrenzen und Zustände. Die Eingabeverarbeitung blieb dabei bedienbar.

Beide schließen bei Frame 488 und 105,2 Sekunden Enginezeit ab. Firmenkonto:
4.651.939; Darlehen: 5.000.000. Der gemeinsame letzte Welt-Hash ist
`46e5e0e6d16dd267b2ae4a50f7484fa0a770a4aabfa144e34c0bd4b2ad1286d8`.
Native Fehler, ausstehende Permits und Laufzeitfehler sind am Ende null.
Das abschließende `halted=1` und Lua `controller requested halt` gehören zum
vorgesehenen terminalen Aufräumen. Sie sind hier kein Testfehler.

Es gab keine gegensätzlichen Wünsche verschiedener Spieler in derselben
Sammelrunde: Alle sieben nichtleeren Listen hatten jeweils einen Absender.
Diese optionale Konfliktprobe bleibt als echte Spielevidenz offen; sie ist
keine Voraussetzung für die bestandene gegenseitige Bedienprobe.

## Fahrt und Unterbrechungen

Die Eingabephase enthält 49,6 Sekunden tatsächlichen Simulationsfortschritt.
Die aktiven Messspannen benötigen beim Host-PC 60,482455 Sekunden und beim
Mitspieler 60,756269 Sekunden: etwa 0,820× beziehungsweise 0,816×.
Zum Vergleich erreichte die akzeptierte Alpha5.12-Szene rund 0,962×.
Die Nutzer berichten entsprechend häufigere sichtbare Zuckler.

Die Rechnung folgt der bisherigen lokalen Tempomethode: Für jede Fahrtspanne
wird letzter gelesener ACK minus erster Aufruf plus 200 ms angesetzt. Die vier
Spannen umfassen Frames 241–384, 385–418, 419–472 und 473–488. Gewollte
Pause-/Fortsetzen-Lücken sind ausgeschlossen. Leere Eingabeabfragen und
gewöhnliche Checkpoints innerhalb der Spannen zählen mit; die zusätzlichen
Kommandophase-Übergänge an ihren Enden zählen nicht mit. Der unabhängige
Host-Aktionsverlauf ergibt für die entsprechenden Fahrtspannen etwa 60,657 s.

51 von 244 aktiven ACK-Abständen je Peer sind länger als 250 ms, also etwa
21 Prozent; bei Alpha5.12 waren es je 22 von 598, etwa 3,7 Prozent. Das
95. Perzentil liegt jetzt bei rund 402/405 ms statt 219/219 ms. Der größte
Abstand beträgt 417 ms beim Host-PC und 619 ms beim Mitspieler.

Die reguläre Weltprüfung bleibt bei 50 Fortschrittsschritten, also zehn
Sekunden Spielzeit. Es gibt drei solche periodischen Checkpoints und sieben
weitere an echten Eingabebatches. Neu sind 233 Eingabeabfrage-Barrieren. Die
Hostzeit vom Versand einer Abfrage zur nächsten Phase hat einen Median von
32 ms; das ist keine isolierte Netzwerk-RTT. Der längste ACK-Abstand des
Mitspielers liegt nach einer leeren Abfrage mit 328 ms Hostspanne, ohne
periodischen Weltcheckpoint an dieser Stelle.

Damit sind häufigere Unterbrechungen messbar und zusätzliche
Eingabeabstimmung als Mitursache plausibel. Welcher Anteil auf Netzwerk,
Datei-IPC, Engine-/Betriebssystemplanung oder Fensterzustand entfällt, ist
nicht getrennt instrumentiert. Gerenderte Bilder beziehungsweise FPS wurden
nicht gemessen; die Berichte beweisen keine alleinige Ursache.

Der automatische Vorlauf zwischen anfänglichem gemeinsamem Weltkontakt
und Start der Eingabephase beanspruchte 170,907 Sekunden, ohne vorherige
Ladezeit. Neue Testmodi erhalten gemäß Nutzervorgabe einen eigenen kurzen
Vorlauf. Die bestehenden vollständigen Tests bleiben erhalten.

## Grenzen und nächster Schritt

Dieser Lauf bestätigt die neue gegenseitige Launchersteuerung mit echten
Eingaben. Er beweist keine normale Ingame-Pause, freie Bauwerkzeuge,
vollständige Weltdeterministik, Langzeitstabilität oder Konfliktauflösung bei
freiem Bauen. Die Queuedateien und Roh-TCP-Pakete sind nicht Teil des Exports;
unübertragene Klicks und die genaue Zeit vom Klick zur Bestätigung können
deshalb nicht unabhängig gezählt beziehungsweise vermessen werden.

Frühere Start-Timeouts/Lua-Fehler werden durch diesen erfolgreichen Lauf
nicht als behoben erklärt. Ein Zusammenhang mit Minimieren wurde berichtet,
aber nicht kontrolliert nachgewiesen. Die akzeptierte Alpha5.12-Referenz
bleibt erhalten. Als nächster Funktionsschritt ist ein begrenzter manuell
ausgelöster Bauauftrag mit kurzem Vorlauf vorgesehen. Mehr dazu:
[nächste Etappe](NEXT_MILESTONE.md).
