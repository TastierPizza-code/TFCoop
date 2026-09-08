# TF2-Koop Alpha5.16-Depotversuch — für beide Spieler

**Neu:** Ihr löst im Launcher selbst Depotaufträge aus. Das Depot wird tatsächlich auf beiden Karten gebaut, sobald beide den Auftrag geprüft und gemeinsam freigegeben haben. Vier begrenzte Testplätze und vier Drehungen sind auswählbar. Normale Bauwerkzeuge, Cursor und Pause-Tasten im Spiel sind weiterhin nicht angeschlossen.

Der kurze Aufbau bleibt bei zehn Runden. Der neue Modus übernimmt Schrittweite, Zweierserien und Kontrollabstände aus der akzeptierten Alpha5.15-Referenz. Die echte Fahrt und die neue Depotfunktion dieser Version müssen erst auf beiden PCs geprüft werden; Vorabprüfungen sind kein neuer Spielnachweis.

## 1 · Aktualisieren und Verbindung einmalig merken

1. Beide schließen TF2, den Test und den Launcher. Den vorhandenen Launcher neu öffnen und das Update abwarten. Auf beiden PCs muss **Alpha5.16-Depotversuch** stehen. Updates warten auf laufende Spiele und Testcontroller.
2. Eine bisherige Test- oder Diagnoseinstallation mit **Bisherige Installation wiederherstellen** zurückbauen.
3. Spiel- und Saveordner prüfen. Die bisherige saubere sehr große Ausgangskarte bleibt gültig. **Keinen neuen Spielstand verschicken oder übernehmen**, wenn auf beiden PCs „Gemeinsamer Testspielstand ist lokal verfügbar“ steht.
4. Den Modus **Depot selbst beauftragen · kurzer Aufbau** wählen. Du bleibst Host, dein Freund wählt Beitreten.
5. Einmalig auf beiden PCs dieselbe Host-IP und denselben **Testschlüssel** eintragen. Der Host teilt seinen Schlüssel mit dem Freund; der Freund ersetzt seinen eigenen. Beim Vorbereiten werden IP, Schlüssel und Rolle lokal gespeichert. Weitere Starts, Updates und Wiederherstellungen behalten diese Daten. **Neu** nur verwenden, wenn ihr den gemeinsamen Zugang bewusst wechseln wollt.

Für die erste Einrichtung ohne vorhandenen Launcher: [TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip), vollständig entpacken und `TF2-Coop.exe` öffnen. Git und Python sind nicht erforderlich. Ein erstmals fehlender gemeinsamer Ausgangsspielstand wird weiterhin privat als passendes `.sav`/`.sav.lua`-Paar übernommen; er liegt nicht im öffentlichen Update.

## 2 · Frisch vorbereiten und laden

1. Beide klicken **Test vorbereiten und installieren**. Das sichert die bisherige Installation und erzeugt jeweils eine frische Testsave-Kopie. Unterschiedliche zufällige Dateinamen sind normal.
2. Beide klicken **Verbinden & Test bereitstellen**. Der Launcher vereinbart für diesen Versuch intern eine neue Sitzung. Der gemerkte Testschlüssel bleibt gleich.
3. Erst nach der Startfreigabe **TF2 über Steam starten** klicken. Im Spiel ausdrücklich den unten im jeweiligen Launcher genannten Save laden.
4. **TF2 Strict Sync - gemeinsamer Depotversuch (Alpha5.16)** und **Legacy Fahrzeuge** sind bereits ausgewählt. Bei alten Koop-Mods zuerst den exakten neuen Savenamen prüfen. Keine weiteren Mods aktivieren.
5. Zehn Aufbaurunden abwarten. Danach werden die gemeinsamen Tasten freigegeben. TF2 möglichst sichtbar lassen, etwa neben dem Launcher; die frühere Ursache von Timeouts nach Minimieren ist nicht abschließend geklärt. Kamera bewegen ist möglich.

## 3 · Kurzer manueller Depotversuch

Die vier Testplätze liegen nahe der automatisch angelegten Testszene. Es sind keine frei gewählten Mauspositionen. Gelände, vorhandene Objekte oder eine andere Platzierung können einen Auftrag ablehnen. **Eine gemeinsam bestätigte Ablehnung ist ein Ergebnis; „Test angehalten“ ist ein Fehler.**

1. Fahrt kurz beobachten. **Host:** Testplatz **1**, Drehung **0**, **Depot gemeinsam bauen** drücken. Gemeinsame Bestätigung abwarten; auf beiden Karten und bei den Firmenwerten vergleichen.
2. **Host:** **Gemeinsam pausieren** und die Bestätigung abwarten. **Freund:** Testplatz **2**, Drehung **90**, Depot beauftragen. Auch während Pause muss der Auftrag bedienbar sein und auf beiden PCs gleich enden.
3. **Freund:** **Gemeinsam fortsetzen**. Jetzt beide **Testplatz 3, Drehung 0** einstellen und möglichst gleichzeitig bauen. Ein erfolgreich belegter Platz darf nicht doppelt bebaut oder doppelt bezahlt werden. Der zweite Auftrag wird nach dem ersten erneut geprüft. Falls beide wegen Gelände abgelehnt werden, ist dieser Konfliktfall noch nicht erfolgreich getestet.
4. Optional **Testplatz 4** mit einer anderen Drehung versuchen. Eine bereits belegte Stelle erneut beauftragen, um die Ablehnung zu prüfen. Die sichtbare Rückmeldung abwarten; Mehrfachklicken beschleunigt nichts.
5. **Messung gemeinsam abschließen** drücken und den regulären Abschluss auf beiden PCs abwarten. Danach TF2 schließen und jeweils **Testbericht als ZIP …** exportieren. Beide Berichte zur Auswertung schicken.

Eine lokale Annahme bestätigt nur, dass der Launcher den Wunsch eingereiht hat. Erst die beidseitige Bestätigung zeigt das gemeinsame Ergebnis. Der Bau kann eine kurze Unterbrechung verursachen: beide prüfen denselben gehaltenen Zustand, bauen in gemeinsamer Reihenfolge und vergleichen die tatsächlichen Rückmeldungen. Ohne Auftrag gibt es keine zusätzliche leere Bauabfrage.

Es muss für diesen neuen Bautest keine weitere lange Pause-/Fahrtmessung wiederholt werden. Ein sauberer Abschluss wird getrennt davon bewertet, ob alle Bau- und Konfliktfälle tatsächlich erfasst wurden. Fast gleichzeitige Klicks beweisen allein noch nicht, dass beide Wünsche in derselben Sammelrunde angekommen sind.

## Bei einem Fehler

**Test beenden** oben ist der Abbruchknopf. Bei „Test angehalten“, Lua-Fehler oder ausbleibendem gemeinsamen Ergebnis beide Berichte sichern. Nicht mit normalen Spielwerkzeugen weiterbauen. TF2 schließen, **Bisherige Installation wiederherstellen**, danach frisch vorbereiten. Der gespeicherte gemeinsame Zugang bleibt erhalten; alte native Sitzungen werden nicht fortgesetzt.

Die neue Mod gehört zum vorbereiteten Messversuch. Es gibt keinen automatischen Rollback beider Welten nach einer unerwarteten fehlgeschlagenen Anwendung.

## Gesicherte Vergleichsmodi

- **Fahrt und Eingaben aus Alpha5.15 · kurzer Aufbau:** akzeptierter Launcher-Pauseversuch, etwa 0,94x im tatsächlichen Lauf. Für seinen vollständigen Bediennachweis pausiert und setzt jeder fort; eine Pause mindestens 45 Sekunden halten.
- **Eingabetest aus Alpha5.13 · vollständiger Aufbau:** ursprünglicher langer Pauseversuch.
- **Referenztest aus Alpha5.12:** akzeptierter längerer automatischer Test mit etwa 0,962x.
- **Vergleichstest aus Alpha5.11:** älterer Fahrt-/Wartevergleich.

Ein Moduswechsel verlangt auf beiden PCs eine frische Vorbereitung. Die unveränderten veröffentlichten Alpha5.12- und Alpha5.15-Pakete bleiben gesichert. Die beobachtete Testszene ist kein vollständiger Weltnachweis. Freies gleichzeitiges Bauen mit normalen Spielwerkzeugen, normale UI-Pause, Speichern/Fortsetzen und Steam-Einladungen bleiben weitere Arbeit.
