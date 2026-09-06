Alpha5.8-Bautest (`v0.5.8`) korrigiert den gemeinsamen Abbruch beim Lesen der Straßenanschlüsse in Runde 5.

- Der Leser durchläuft jetzt die tatsächlichen Einträge der nativen Anschluss-Sammlung, statt direkten Zugriff über laufende Nummern vorauszusetzen. Anzahl, eindeutige gültige Kanten und passende Endpunkte werden weiterhin geprüft.
- Die Tests bilden ausdrücklich eine nicht leere Sammlung nach, deren Zugriff auf Eintrag 1 `nil` ergibt. Geordnete Arrays und ihre Prüfung bleiben unverändert.
- Die spätere Abfrage der Linienfahrzeuge nutzt denselben begrenzten Sammlungsleser. Auch dort verwendet der lokale GitHub-Ausgangscode Werteiteration; ein tatsächlicher Fehler dieses späteren Schritts ist bisher nicht beobachtet.
- Bauprofil, native Schrittsteuerung, 240 Runden und die sehr große private Ausgangskarte bleiben gleich. Der Test arbeitet automatisch; nur zuschauen oder Kamera bewegen.

Beide echten Alpha5.7-Berichte bestätigen Straße, Depot und zwei Haltestellen mit identischen protokollierten Zuständen, Prüfsummen und Baukosten. Der anschließende Anschluss-Lesefehler tritt auf beiden PCs vor dem eigentlichen Verbindungsbau auf. Alle bisher erreichten Bauten erfolgten bei gehaltener Simulation. Die Korrektur, Verbindungsbau, Fahrzeugkauf und Fahrt müssen im echten Spiel noch bestätigt werden; freies Bauen, Cursor und normale gemeinsame Pause-Tasten sind weiterhin nicht freigeschaltet.

**Beide:** TF2, Test und alten Launcher schließen; Launcher erneut öffnen und Update auf Alpha5.8 abwarten. **Bisherige Installation wiederherstellen**, frischen gemeinsamen Code setzen, **Test vorbereiten und installieren**, verbinden und jeweils die neu angezeigte Messtest-Save laden. Nur **TF2 Strict Sync - automatischer Bautest (Alpha5.8)** und **Legacy Fahrzeuge** aktivieren. Nach Abbruch oder Abschluss beide normalen Testbericht-ZIPs privat schicken.

Das öffentliche Paket enthält keine Spielstände oder Berichte. Vollständige Anleitung: **ANLEITUNG.html**.
