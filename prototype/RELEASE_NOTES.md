Alpha5.4-Diagnose (`v0.5.4`) ergänzt einen **allein ausführbaren API-Diagnosemodus**. Im echten Alpha5.3-Bautest wurde die Straße gebaut; anschließend brach die Zustandsmessung mit `invalid finite build value` ab. Das betroffene Datenfeld ist noch nicht bekannt. Diese Veröffentlichung stellt keinen bestätigten Fix oder erfolgreichen Multiplayer-Bautest dar.

- **Automatisch aktualisieren ab Alpha5.2:** TF2 und den bisherigen Test schließen, den vorhandenen Launcher neu öffnen und auf **Alpha5.4-Diagnose** warten. Kein erneutes Verschicken der Programm-ZIP nötig.
- Oben die lokalen Pfade prüfen und im ersten Reiter **API-Diagnose allein** auf **Diagnose vorbereiten** klicken. Die Vorbereitung setzt eine vorhandene Strict-Sync-Testinstallation zurück, installiert die lesende Diagnosemod und erstellt eine frische, geprüfte Save-Kopie.
- TF2 selbst normal über Steam starten. Die angezeigte `TF2-API-Diagnose-….sav` über **Spiel laden → OPTIONEN AUSWÄHLEN → Mods** nur mit **TF2 API-Diagnose (Alpha5.4)** und **Legacy Fahrzeuge** laden; alte Koop- und Strict-Sync-Mods deaktivieren.
- Etwa zehn Sekunden warten, dann **Diagnosebericht als ZIP …** exportieren. **Nur der eigene Bericht ist nötig; der Freund muss nicht teilnehmen.** Anschließend TF2 schließen und die bisherige Installation wiederherstellen.
- Die Diagnose liest vorhandene Kartenobjekte und getrennte API-Konstruktorproben. Sie sendet keine Bau- oder Pausebefehle. Fehlende Liveobjekte gelten als fehlende Abdeckung, nicht als erfolgreiche Prüfung.
- Der Ausgangsspielstand bleibt lokal. Öffentliche Releases enthalten keine privaten Spielstände oder Berichte; Diagnoseberichte bitte ausschließlich privat weitergeben.

Der gemeinsame 240-Runden-Bautest bleibt im Reiter **Bautest (experimentell)**. Er ist jetzt nicht der empfohlene nächste Versuch. Freies gemeinsames Bauen, Cursor und normale gemeinsame Pause-Tasten sind weiterhin nicht freigeschaltet. Der aktuelle Schritt ist die Auswertung der Solo-Diagnose, bevor weitere Schlussfolgerungen zum Bauablauf möglich sind.

Der vollständige Ablauf steht in **ANLEITUNG.html** und **ANLEITUNG.md**. Zweck und Grenzen der Messung beschreibt **API_DIAGNOSE.md**.
