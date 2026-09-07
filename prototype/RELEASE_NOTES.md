Alpha5.9-Bautest (`v0.5.9`) schützt die Lebensdauer gelesener nativer Spielobjekte und verwendet einen einmal neu gespeicherten Ausgangsspielstand mit passender Modauswahl.

- Besitzer und Unterstrukturen bleiben während einer vollständigen Bauoperation erreichbar. Der Schutz gilt auch für verschachtelte Abfragen und wird anschließend bei Erfolg oder Fehler freigegeben. Es werden keine fehlerhaften Werte ersetzt oder Getter wiederholt.
- Die bisherige sehr große Karte bleibt erhalten. Ihr neues Savepaar enthält bereits ausschließlich **Legacy Fahrzeuge** und **Strict Sync**. Die wiederholte Änderung der alten Modauswahl entfällt.
- Ein lokaler Prüfer kann echte Befehle und Zustände aufzeichnen und in einem zweiten frischen TF2-Prozess vergleichen. Er unterstützt ausdrücklich manuelles Laden; ein abgelehnter automatischer Ladeaufruf wird klar gemeldet.

Im letzten echten Alpha5.8-Lauf wurden alle zwölf Aufträge und 240 Schritte einschließlich Fahrzeugkauf, Linienzuweisung und Fahrt bestätigt. Ein zweiter Prozess stimmte bis Frame 99 überein und hielt dann bei einem vorübergehenden Lua-Lesefehler an. Die neue Korrektur wird mit gezielter Speicherbereinigung und geliehenen nativen Unterstrukturen nachgebildet geprüft. **Ihre echte Nachprüfung steht noch aus.** Freies gleichzeitiges Bauen, Cursor und normale gemeinsame Pause-Tasten sind weiterhin nicht freigeschaltet; dieser Test belegt keine vollständige Weltsynchronität.

**Einmalige Umstellung:** Das neue private Testspielstandpaar separat erhalten, vollständig entpacken und über **Testspielstand übernehmen …** dessen `Testspielstand/initial.sav` auswählen. `initial.sav.lua` muss daneben liegen. Das alte Paar aus früheren Paketen passt nicht zu dieser Version. Danach bleibt die geprüfte neue Basis im lokalen Cache.

**Beide:** TF2, Test und alten Launcher schließen; Launcher erneut öffnen und Update auf Alpha5.9 abwarten. Vorherige Installation wiederherstellen, neuen gemeinsamen Code setzen, Test vorbereiten, verbinden und jeweils die neu angezeigte Messtest-Save laden. Die Modliste sollte bereits passen. Nach Abbruch oder Abschluss beide normalen Testbericht-ZIPs privat schicken.

Das öffentliche Paket enthält keine Spielstände oder Berichte. Vollständige Anleitung: **ANLEITUNG.html**. Prüfumfang und Grenzen: **VERIFICATION.md**.
