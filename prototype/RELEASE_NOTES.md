Alpha5.10-Bautest (`v0.5.10`) behebt einen mit Alpha5.9 eingeführten Startfehler: Der Bauadapter lieferte einen Wahrheitswert statt des gelesenen Spielzustands zurück.

- TF2 verändert `table.unpack` so, dass die optionalen Bereichsgrenzen ignoriert werden. Die neue Rückgabe reicht Lua-Varargs direkt weiter und hängt nicht mehr von diesem Verhalten ab.
- Der Lebensdauerschutz aus Alpha5.9 bleibt erhalten: Besitzer und Unterstrukturen bleiben während einer vollständigen Bauoperation erreichbar, auch bei verschachtelten Abfragen. Danach werden die Referenzen bei Erfolg oder Fehler freigegeben. Es werden keine fehlerhaften Werte ersetzt oder Getter wiederholt.
- Die bisherige sehr große Karte und das saubere private Savepaar aus Alpha5.9 bleiben unverändert. Es enthält bereits ausschließlich **Legacy Fahrzeuge** und **Strict Sync**. Wer es bereits übernommen hat, braucht keinen erneuten Import.

**Die echte Nachprüfung mit Alpha5.10 ist bestanden:** Ein TF2-Prozess zeichnete zwölf Befehle und 240 Schritte auf; ein zweiter frischer Prozess spielte dieselbe Aufzeichnung vom selben Ausgangsspielstand vollständig nach. Nach jeder Aktion stimmten Ergebnisse und gemessene Zustände überein. Bestätigt wurden Straße, Depot, zwei Haltestellen, drei Verbindungen, Fahrzeugkauf, Linienzuweisung, Abfahrt und Bewegung sowie 29 Pausenrunden. Die 211 Fortschrittsschritte ergaben 42,2 Sekunden Enginezeit. Beide Prozesse wurden regulär beendet und die vorherige Installation wiederhergestellt.

Diese nacheinander ausgeführten Läufe auf einem PC prüfen die gemessenen Vorgänge. Der entsprechende Bautest auf zwei PCs über das Netzwerk steht noch aus. Freies gleichzeitiges Bauen, Cursor und normale gemeinsame Pause-Tasten sind weiterhin nicht freigeschaltet; vollständige oder dauerhafte Weltsynchronität ist nicht belegt.

**Spielstand:** Der lokale Cache aus Alpha5.9 genügt. Falls die saubere Basis noch fehlt, das seit Alpha5.9 bereitgestellte private Paar vollständig entpacken und über **Testspielstand übernehmen …** dessen `Testspielstand/initial.sav` auswählen. `initial.sav.lua` muss daneben liegen. Das Paar aus Paketen vor Alpha5.9 passt nicht. Danach bleibt die geprüfte Basis im lokalen Cache.

**Beide:** TF2, Test und alten Launcher schließen; Launcher erneut öffnen und Update auf Alpha5.10 abwarten. Vorherige Installation wiederherstellen, neuen gemeinsamen Code setzen, Test vorbereiten, verbinden und jeweils die neu angezeigte Messtest-Save laden. Die Modliste sollte bereits passen. Nach Abbruch oder Abschluss beide normalen Testbericht-ZIPs privat schicken.

Das öffentliche Paket enthält keine Spielstände oder Berichte. Vollständige Anleitung: **ANLEITUNG.html**. Prüfumfang und Grenzen: **VERIFICATION.md**.
