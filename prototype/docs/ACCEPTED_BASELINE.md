# Akzeptierte Referenz: Alpha5.12

Am 7. September 2026 haben beide Spieler den gemeinsamen Alpha5.12-Lauf
abgeschlossen. Der Nutzer akzeptiert das erreichte Tempo von ungefähr 0,962x
und die fast unsichtbaren kurzen Zuckler. Dieser Entwicklungsabschnitt ist
für die erfasste Szene abgeschlossen. Tempo- und Darstellungsoptimierungen
werden zurückgestellt, bis die übrigen Koop-Funktionen arbeiten.

## Unveränderter Stand

- Release und Quelltag: [v0.5.12](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.12).
- Commit: `28c739880870b66ad0ebe59882f8de4c729489aa`.
- Windows-Paket: `TFCoop-Windows.zip`, 11.555.964 Bytes.
- Paket-SHA-256: `fabd96dc0e4bf4887ad278174c9125ef5f51515eda21eeddfab3cd4ba54b4234`.
- Der Modus `stream_v1` bleibt als Referenz für weitere Entwicklung erhalten.
- Die private saubere große Ausgangskarte bleibt unverändert.

Eine zusätzliche private Sicherung enthält ein geprüftes Git-Bundle mit der
vollständigen bisherigen Historie, das veröffentlichte Paket, die Ausgangsbasis,
beide Originalberichte und ihre Auswertung. Kopierprüfsummen, ZIP-CRCs und Bundle
wurden geprüft. Die Sicherung verändert die installierten Spieldateien nicht.
Spielstände, Berichtdateien und private Sicherungen werden nicht veröffentlicht.

Der normale Start einer älteren EXE kann automatische Updates auslösen. Zum
Wiederherstellen des exakt alten Stands dienen Quelltag beziehungsweise Bundle
und das archivierte Paket mit seinen Prüfsummen; der Updater wird nicht durch
eine ungeprüfte Rückstufung umgangen. Eine künftige Version soll den bestehenden
Referenzmodus neben einem neuen Eingabemodus behalten.

## Tatsächliche Zwei-PC-Evidenz

Beide Archive sind CRC-fehlerfrei. Gemeinsames Manifest und 35 ausgelieferte
Payload-Dateien stimmen mit dem öffentlichen Alpha5.12-Paket überein. Beide
Weltjournale sind bytegleich: 270 Einträge, SHA-256
`91757db405b0d3828a8e455e57cd64ec63414d448873f275e3c56ff09fa18333`.

Der Bauabschluss mit zwölf Befehlen und 240 Schritten wurde aus den beobachteten
Zuständen erneut berechnet. Alle 29 Pausenschritte im Aufbau halten die erfassten
Werte unverändert. Anschließend wurden auf jedem PC 600 native Schrittquittungen
und alle zwölf frischen Kontrollpunkte nachgeprüft. Pause `a:8` und Fortsetzen
`b:6` verändern den Zustand am selben Frame 540, ohne dazwischen Spielzeit
freizugeben. Die beobachtete Welt bleibt während des gemessenen Halts unverändert.

Beide enden bei Frame 840 und Enginezeit 175,6 Sekunden. Das Firmenkonto beträgt
auf beiden PCs 4.647.799, das Darlehen 5.000.000. Es liegt kein nativer
Terminalfehler und keine Abweichung der erfassten Zustände vor.

Die aktiven Fahrtspannen einschließlich gewöhnlicher Kontrollpunkte ergeben
120 Sekunden Spielzeit in 124,737507 beziehungsweise 124,733292 Sekunden:
0,962020x beziehungsweise 0,962053x. Die absichtliche mittlere Testpause ist
aus diesen Spannen ausgeschlossen. Einschließlich Pause und Übergängen dauert
die gesamte Phase beim Host 128,969 Sekunden.

Die Anzeige `paced_stream_1x_met=false` entsteht allein durch einzelne maximale
beobachtete Bestätigungsabstände über der bisherigen 400-ms-Grenze: höchstens
419,403 beziehungsweise 418,154 ms. Mitteltempo und 95. Perzentil bestehen ihre
bisherigen Vorgaben. Die gespeicherten Originalmesswerte und diese Bewertung
werden nicht nachträglich auf Erfolg umgeschrieben; die Nutzerakzeptanz ist eine
zusätzliche Entscheidung über die weitere Priorität.

Die Spieler beschreiben eine gute Fahrt mit kaum sichtbaren Zucklern. Dies ist
ihre Beobachtung. Die Instrumentierung misst Python-Anforderungszeitpunkte und
gelesene native Quittungen, keine Renderzeiten oder Bildraten.

## Abgrenzung und nächste Etappe

Akzeptiert sind die gemeinsame Zeitsteuerung und der automatische Bau-/Fahrtpfad
für diese beobachtete Szene. Normale UI-Pause, beliebige Bauwerkzeuge, konkurrierende
Umbauten, Cursor, Speichern/Fortsetzen und vollständige langfristige Weltsynchronität
sind damit noch nicht nachgewiesen.

Die nächste Etappe sind [frei ausgelöste Eingaben und ihr gemeinsamer Commit](NEXT_MILESTONE.md).
