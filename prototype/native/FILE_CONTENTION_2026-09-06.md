# Alpha4.1: Windows-Dateikonflikt nach erfolgreichen Messrunden

## Laufzeitbelege

Die beiden vom Nutzer bereitgestellten Host-Berichte vom 6. September 2026
melden `runtime_fault=102`, `win32_error=5` und weiterhin `fault=0` im
eigentlichen Schritt-Gate:

- `TF2-Alpha4.1-Bericht-a-20260906-191032.zip`: sechs verglichene Runden,
  anschließend `completed_frame=7` und Enginezeit 14800 ms.
- `TF2-Alpha4.1-Bericht-a-20260906-191357.zip`: 38 verglichene Runden bis
  21000 ms, anschließend `completed_frame=39` und Enginezeit 21200 ms.

Anders als beim vorherigen `.2f`-Absturz wurden hier also mehrere 200-ms-Schritte
ausgeführt und bestätigt. Fehler 102 stammt aus der Dateiverbindung. Windows-
Fehler 5 bedeutet Zugriff verweigert. Der damalige Status nennt die betroffene
Dateioperation nicht; die genaue Operation lässt sich daraus rückwirkend nicht
sicher bestimmen. Ein Disconnect wie `IncompleteReadError` beschreibt die
anschließende abgebrochene Verbindung, nicht den ursprünglichen Dateifehler.

## Reproduzierbarer Mechanismus

`AtomicStatus` schrieb bisher eine vollständige temporäre Datei und ersetzte
`native_status.txt` mit genau einem `MoveFileExW`-Versuch. Jeder Fehler dieses
Versuchs sperrte sofort und dauerhaft das Gate. Ein gewöhnlicher Windows-CRT-
Leser wie Lua `io.open` kann die Datei ohne `FILE_SHARE_DELETE` öffnen. Solange
dieser kurze Lesezugriff offen ist, darf Windows das atomare Ersetzen ablehnen.
Auch das Öffnen einer Steuerdatei kann kurz mit einem inkompatiblen Handle
zusammentreffen. Beides ist mit echten Windows-Datei-Handles reproduziert.

## Korrektur

- Ausschließlich das Öffnen der Steuerdatei und das atomare Ersetzen der
  Statusdatei wiederholen Fehler 5, 32 oder 33. Jeder Vorgang hat eine feste
  Obergrenze von 250 ms und wartet zwischen Versuchen 5 ms.
- Gewartet wird nur im Dateiarbeiter. Der Simulations-Hook wartet nicht und
  erhält durch einen Wiederholungsversuch keine zusätzliche Freigabe.
- Die veröffentlichte Datei wird niemals direkt überschrieben oder zuerst
  gelöscht. Leser sehen weiterhin einen vollständigen alten oder neuen Status.
- Eine gelöschte, bereits gelesene Steuerdatei bleibt ein sofortiger Fehler.
  Ungültige Daten, Schreib-/Flushfehler und nach Ablauf weiterhin blockierte
  Dateien bleiben ebenfalls terminal. Eine spätere erfolgreiche Veröffentlichung
  liefert Diagnostik, setzt die Simulation aber nicht fort.
- `io_operation` bewahrt die Operation des ersten terminalen Fehlers:
  0 keine, 1 Steuerdatei öffnen, 2 Größe lesen, 3 Inhalt lesen,
  4 Status-Temporärdatei öffnen, 5 schreiben, 6 flushen, 7 atomar ersetzen.
- `status_replace_retries`, `status_last_retry_error`, `control_open_retries`
  und `control_last_retry_error` machen erfolgreich überstandene Konflikte
  sichtbar. Native ABI 3 und die 200-ms-Schrittweite bleiben unverändert.

## Prüfung und Grenze

Die nativen Laufzeittests führen 14 Fälle aus. Dazu gehören echte, kurzzeitig
und dauerhaft blockierte Status-/Steuerdateien sowie 200 Freigaben unter einem
gleichzeitig laufenden CRT-Leser. Jede erfolgreiche Lektüre wird auf einen
vollständigen Datensatz geprüft; jede Freigabe muss genau 200 ms ergeben.
Der temporäre Statuskonflikt dauert absichtlich 75 ms und muss sich erholen.
Dauerhafte Konflikte müssen innerhalb der begrenzten Zeit sperren. Die Tests
für gelöschte Steuerdateien, defekte Statuspfade, doppelte/ungültige Nachrichten
und alte 100-ms-Freigaben bleiben bestehen.

Zusätzlich bleiben die Hook-/ASM-Tests mit 10000 konkurrierenden Freigaben und
die 20 Szenarien des zurückgestellten Befehlsadapters Bestandteil des Builds.
Diese Prüfungen laufen ausschließlich in Testprozessen; kein Spiel wird
gestartet, bedient oder verändert. Ein vollständiger erneuter Test auf beiden
Spiel-PCs und ein Nachweis vollständiger Weltsynchronität stehen weiter aus.
