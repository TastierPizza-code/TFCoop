# Akzeptierte Eingabe-/Temporeferenz: Alpha5.15

Der Nutzer akzeptiert die Fahrt des tatsächlichen Zwei-PC-Laufs vom
8. September 2026 ausdrücklich: Das Tempo sei wieder sehr gut und soll so
beibehalten werden. Die beiden Originalberichte bestätigen den erfolgreichen
kurzen Aufbau, gegenseitige Launcher-Eingaben, unveränderte Pause und den
gemeinsamen Abschluss. **Dieser Stand ist die Referenz für weitere Eingabefunktionen.**

Die frühere [Alpha5.12-Referenz](ACCEPTED_BASELINE.md) bleibt mit ihrem längeren
automatischen Test unverändert erhalten. Die neue Annahme ersetzt weder dessen
Originalmessungen noch dessen Prüfumfang. Weitere Tempoexperimente werden
zurückgestellt; die nächsten Funktionen sollen dieses Fahrverhalten erhalten.

## Gesicherter Quell- und Paketstand

- Release/Tag: [v0.5.15](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.15).
- Commit: `3b24380284c82ee0c4199e8eb94b90dc463bf708`.
- Modus: `paced_live_v1`; Vorbereitung: `short_scene_v1` mit zehn Runden.
- Paket: `TFCoop-Windows.zip`, 11.635.178 Bytes.
- Paket-SHA256: `97b836d779638616826653c895432d86518b81a61f2bf59d93d47fd8bb7a8547`.

Eine zusätzliche private Sicherung enthält das geprüfte Paket, ein verifiziertes
Git-Bundle mit vollständiger Historie, die saubere Ausgangsbasis, beide
Originalberichte und reproduzierbare Auswertungen. Kopierhashes und ZIP-CRCs
wurden geprüft. Die Sicherung verändert keine Spielinstallation und keinen Save.
Der normale Start einer archivierten EXE kann Updates auslösen; der alte
Quelltag und das geprüfte ZIP dienen der Wiederherstellung, ohne den Updater
zurückzustufen oder seine Prüfung zu umgehen.

## Tatsächliches Tempo

Die interaktive Phase umfasst **182 Fortschrittsschritte**, also 36,4 Sekunden
Spielzeit, verteilt auf vier Fahrtspannen. Zwischen absichtlichen Pausen und
Befehlsphasen ergeben sich folgende Werte:

| Messwert | Host-PC | Mitspieler-PC |
|---|---:|---:|
| Aktive reale Fahrtzeit | 38,748514 s | 38,806138 s |
| Spielzeit / reale Fahrtzeit | 0,939391x | 0,937996x |
| Median der Bestätigungsabstände | 200,424 ms | 201,859 ms |
| 95. Perzentil | 226,148 ms | 392,116 ms |
| Größter Bestätigungsabstand | 424,166 ms | 408,162 ms |
| Abstände über 250 ms | 8 von 178 (4,49 %) | 9 von 178 (5,06 %) |

Die Messdefinition entspricht den bisherigen Nachrechnungen: pro ununterbrochener
Fahrtspanne letzter ACK-Zeitpunkt minus erster Anforderungszeitpunkt plus
200 ms; normale Kontrollpunkte innerhalb der Spanne sind enthalten. Absichtliche
Pause-/Fortsetzen-Grenzen werden nicht als Fahrtzeit mitgezählt. Unabhängig
ergeben die Host-Phasenspannen 38,795 Sekunden beziehungsweise 0,938265x.

Das Tempo liegt deutlich über den etwa 0,82x aus Alpha5.13 und etwas unter den
etwa 0,962x aus Alpha5.12. Längere Bestätigungsabstände sind wesentlich seltener
als in Alpha5.13 (dort jeweils 51 von 244, rund 20,9 %). Einzelne kurze Stopps
bleiben vorhanden; das hohe 95. Perzentil beim Mitspieler entsteht durch neun
längere Abstände knapp über der Fünf-Prozent-Grenze. **Die Nutzerakzeptanz
betrifft die beobachtete gute Fahrt, keine nachträglich behauptete exakte 1x-Rate.**

Der kurze Aufbau dauert ab gemeinsamer Ausgangsbestätigung **12,500 Sekunden**,
gegenüber 170,907 Sekunden im vorherigen vollständigen Alpha5.13-Aufbau. Ladezeit
ist darin nicht enthalten. Es wurden tatsächlich **keine separaten Eingabeabfragen**
versandt: 185 Sammelrunden reisen mit einer Startantwort, 91 Fahrtblöcken und
93 Pausenbestätigungen. Neun frische Kontrollpunkte sind enthalten, davon acht
wegen Eingaben und einer als regelmäßige Kontrolle.

Statusveröffentlichungen wurden tatsächlich zusammengefasst, ohne Fehler zu
verbergen. Ihre gemessenen Gesamtkosten betreffen aber auch Aufbau, Warten und
Pause. Daraus lässt sich keine isolierte Ursache oder exakte Einsparung der
aktiven Fahrt berechnen. Die Messung enthält keine FPS, Renderzeiten oder
isolierte Netzlatenz.

## Übereinstimmung und Eingaben

Beide ZIPs sind CRC-fehlerfrei. Das gemeinsame Manifest ist identisch; 40
ausgelieferte Payload-Dateien passen zum öffentlichen Alpha5.15-Paket. Die
Weltjournale sind bytegleich: **133 Einträge**, SHA256
`fb805ee368dfa92ad9eef2e4558054ad675d641b826f06e1e9572962a4a4e1f4`.

Der kurze Bereitschaftsnachweis wurde aus allen zehn Befehlsrückmeldungen und
ihren beobachteten Welten erneut berechnet. Objekte, Verbindungen, Kaufabzug,
Linienzuweisung und abgefahrener Fahrzeugzustand passen zusammen. Die neun
Pausenschritte im Aufbau halten die beobachteten Werte unverändert. Dies ist
weiterhin der kurze Bereitschaftsnachweis, kein voller 240-Runden-`BuildProof`.

Alle **acht Wünsche** wurden gemeinsam übernommen und abgeschlossen (vier je
Spieler): sieben echte Pause-/Fortsetzen-Wechsel und ein Abschlusswunsch.
Beide Spieler lösten Pause und Fortsetzen aus. Batch-Hashes, Reihenfolge,
tatsächliche Callback-Ergebnisse, Bestätigungen und alle 218 beidseitigen
Protokolloperationen stimmen überein. Zwischen Eingabeprüfung, Anwendung und
gemeinsamer Bestätigung wurde kein Fortschritt freigegeben.

Die längste gemeinsame Pause beträgt **47,375 Sekunden**. Insgesamt 93 frische
Pausenbeobachtungen blieben unverändert; während der langen Pause bestätigen
77 Beobachtungen am Frame 154 den gehaltenen Zustand. Unabhängige native
Zeitstempel belegen darin zusätzlich mindestens 46 Sekunden ohne Fortschritt.
Ein Abschluss während Pause funktioniert einschließlich der frischen letzten
Bestätigung. Gleichzeitige gegensätzliche Wünsche wurden in diesem Lauf nicht
in derselben Sammelrunde erfasst.

Beide enden bei **Frame 192**, Enginezeit **50 Sekunden**, Konto **4.656.092** und
Darlehen **5.000.000**, gemeinsam pausiert. Alle 182 nativen Schritte der
Eingabephase sind nachgeprüft. Es gibt keinen terminalen nativen Fehler oder
abweichenden beobachteten Weltzustand. Das abschließende `halted` ist das
beabsichtigte Aufräumen nach erfolgreichem Abschluss. Ein wiederholter
Statusdatei-Schreibversuch beim Mitspieler wurde erfolgreich aufgefangen.

## Für weitere Entwicklung

`paced_live_v1`, die native 200-ms-Schrittweite, die Zweierserien, der bestehende
Pacer und die regelmäßigen 50-Schritt-Kontrollen dienen als Vergleichsbasis.
Neue Funktionen dürfen keine zusätzlichen leeren Abfragerunden im normalen
Fahrtweg einführen. Der kurze Aufbau bleibt für neue Tests erhalten, soweit
die tatsächlichen Voraussetzungen der jeweiligen Funktion damit geprüft sind.

Die Annahme umfasst die beobachtete Szene dieses kurzen Laufs. 36,4 Sekunden
Fahrt und ein regelmäßiger Kontrollpunkt ersetzen keinen langfristigen
Ausdauertest. Normale TF2-Pausebuttons, freie konkurrierende Bauwerkzeuge,
vollständige Weltzustände, Speichern/Fortsetzen und Steam-Einladungen bleiben
offen. Auch frühere Laufzeit-Timeouts sind dadurch nicht allgemein widerlegt.
Die nächsten Aufgaben sind das vorgemerkte private Test-Verbindungsprofil und
anschließend der begrenzte manuelle Bauauftrag; siehe [nächste Etappe](NEXT_MILESTONE.md).
