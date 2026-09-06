# Native Schrittsteuerung: implementierter Messprototyp

Die Dateien `step_probe.h/.cpp` bilden eine eigenständige DLL. Sie wird weder vom
Alpha-Launcher geladen noch automatisch installiert. Ein Laden allein verändert
kein Spielverhalten; erst der ausdrückliche Aufruf von Initialize und Arm aktiviert
die Steuerung. Die Original-Alpha-Hooks werden nicht überlagert.

## Befunde am tatsächlichen Spielcode

Statisch geprüft wurde die installierte Windows-EXE Build 35924, SHA256
`782b904a8f7bbdac1f7a18528f1a5c778691e5aa3087c37c351bf6912585175c`.
Die nachfolgenden Adressen sind RVAs. Die statische Untersuchung startete oder
bediente das Spiel nicht; der erste tatsächliche Nutzertest ist unten ausgewertet.

- `GameSim::Step` bei `0x15aa00` ist ein äußerer Aufruf, nicht automatisch genau
  ein innerer Simulationsschritt. Die ältere M7-Dokumentation nennt die Einheit
  von `frameTime` irrtümlich Millisekunden. Die bisherigen Laufzeitprotokolle
  beschreiben 200000 Mikrosekunden bei fünf Aufrufen pro Sekunde.
- Bei `0x15aa30` wird der GameSpeed-Getter `0x2877a0` aufgerufen. Rückkehradresse
  ist `0x15aa35`. Geschwindigkeit null führt in den pausierten Wartungspfad.
- Für laufende Simulation wird der Getter bei `0x15aae4` erneut gelesen,
  Rückkehradresse `0x15aae9`. Die Geschwindigkeit bestimmt die Anzahl innerer
  Durchläufe im Bereich `0x15ab04..0x15abe6`.
- `CGame::RunGameSimLoop` bei `0x1184d0` verarbeitet nach Step und Pufferwechsel
  auch Spielbefehle; die Apply-Stelle liegt bei `0x118812`. Ein blockierendes
  Warten im Step verhindert diese nachfolgenden Phasen.
- Auch die Pause führt Arbeit aus: vor der Verzweigung `0x15ac90`, danach unter
  anderem `0xaea970`, `0x231a00`, `0x1011b70`. Die GameTime-Komponente erhöht
  bei Wartung einen Zähler bei `+0x30`, bei laufender Simulation außerdem `+0x34`.
  Unterschiedlich viele Warteaufrufe können deshalb unterschiedliche interne
  Zustände erzeugen, selbst wenn die eigentliche Simulationszeit gleich bleibt.
- Der Zeit-Getter bei `0x287810` liest die tatsächliche Enginezeit in
  Millisekunden. ABI 3 enthält `time_before_ms` und `time_after_ms`; der Hook
  prüft 200 ms pro Fortschrittsfreigabe und null bei HOLD oder Pause. Eine
  abweichende Differenz setzt `CLOCK_MISMATCH`, statt den Schritt zu bestätigen.
- `EmissionMap::Update` bei `0x2f7850` verlangt mindestens `.2f` Sekunden.
  `0x2f7881..0x2f788c` vergleicht den eingehenden Float mit `0x3e4ccccd` und
  verzweigt bei Unterschreitung zur Assertion `dt >= .2f`, Quellzeile 428.
  Der erste Alpha4-Nutzertest traf genau diese Assertion, weil der Prototyp
  fälschlich 100000 Mikrosekunden vorgab. ABI 3 verwendet 200000 Mikrosekunden;
  die Engine-Assertion bleibt unverändert. Die [Fehleranalyse](STEP_MINIMUM_2026-09-06.md)
  trennt Laufzeitbelege, statische Befunde und den noch ausstehenden Wiederholungstest.

## Was die DLL steuert

Die DLL überschreibt nur die beiden Getter-Ergebnisse innerhalb eines aktiven
Step-Aufrufs. GUI und andere Leser erhalten den ursprünglichen Wert. HOLD liefert
null und lässt den pausierten Wartungspfad zu; ein Permit für 200000 Mikrosekunden
liefert an beiden Stellen eins. Ein Pause-Permit mit `dt_us=0` bestätigt einen
pausierten Wartungsdurchlauf. Auch HOLD und Pause übergeben `GameSim::Step` einen
gültigen Frame-Parameter von 200000 Mikrosekunden; die Pause entsteht durch die
Getter-Werte. Es gibt weder Sleep noch Datei-/Netzzugriffe oder
Allokationen im Step-Hook.

Permits sind an eine unveränderliche Epoch und fortlaufende Frame-Nummer gebunden.
Der atomare Slot verhindert doppelte Ausführung. Halt ist dauerhaft; ein bereits
zugelassener Schritt darf fertig werden, weitere Fortschritte werden nicht
zugelassen. Unterschiedliche oder unerwartete Getter-Aufrufe setzen einen Fehler
und werden nicht als erfolgreiche Ausführung bestätigt. Initialize und Arm sind
gegen gleichzeitige Kontrollaufrufe abgesichert.

**HOLD ist noch keine vollständige Sperre sämtlicher Weltänderungen.** Die weiter
laufenden Wartungs-, Skript- und Befehlsphasen müssen kontrolliert werden. Das
Statusfeld `probe_required` ist deshalb immer eins. `completed_frame` meldet einen
passenden Steuerungsdurchlauf, keinen bestätigten vollständigen Weltzustand.

## Hook-Vertrag und Tests

Initialize verlangt einen ruhenden Spielstart vor dem ersten Step. Der übergebene
Bestätigungswert ersetzt keine technische Feststellung dieser Bedingung; ein
künftiger Loader muss sie tatsächlich herstellen. Nach Installation bleiben
DLL und Trampoline bis Prozessende geladen. Die EXE-Metadaten und vollständigen
Bytes von Step, Getter, äußerer Schleife und EmissionMap::Update samt `.2f`-Konstante
müssen dem geprüften Stand entsprechen.
Abweichende oder bereits durch Alpha veränderte Funktionen werden abgewiesen.

Der Getter enthält einen relativen CALL in den überschriebenen Bytes. Der
Trampolin-Code verlegt ihn ausdrücklich als absoluten indirekten Aufruf und
behält den Rückkehrpfad. Ein eigener ASM-Test führt die echten Ersatz-Prologe,
beide Detours und diese Relokation aus.

Der native Test prüft zusätzlich passiven Betrieb, HOLD, Pause, genau einen
Durchlauf bei Spielgeschwindigkeit drei, Duplikate, falsche Epoch und Reihenfolge,
Halt während eines Schritts, konkurrierendes Arm sowie 10000 Freigaben zwischen
zwei echten Threads. Die Produktion-DLL wurde separat nur in einen Python-
Testprozess geladen; dort verweigert Initialize den falschen Host und bleibt passiv.
Eine zusätzliche Regression bildet die im Spiel beobachtete Umrechnung und
`.2f`-Vorbedingung nach: 100000 und 199999 Mikrosekunden werden abgewiesen,
200000 akzeptiert. Die Fake-Engine prüft diese Grenze in jedem Durchlauf,
einschließlich HOLD. Der Laufzeittest verweigert einen alten 100000-us-Datensatz,
bevor ein Permit den Spielthread erreichen könnte.

## Anbindung und verbleibende Grenzen

`probe_runtime.*` verbindet die Exporte über begrenzte, fortlaufend nummerierte
Dateinachrichten mit dem Python-Adapter. Empfang, Annahme und tatsächlicher
Abschluss sind getrennte Statusfelder. Bleibende Statusschreibfehler und
Protokollfehler sperren weitere Freigaben. Kurze Windows-Freigabekonflikte beim
Öffnen der Steuerdatei oder atomaren Ersetzen des Status werden höchstens 250 ms
wiederholt. Die Dateiarbeit läuft außerhalb des Step-Hooks; dabei wird kein
weiterer Befehl angenommen. Die [Dateifehleranalyse](FILE_CONTENTION_2026-09-06.md)
beschreibt die beiden Nutzertests und die tatsächlichen Windows-Regressionsfälle.
`native_status.txt` veröffentlicht `abi=3` und `native_step_us=200000`, sodass
Python und Lua eine gemischte oder veraltete Installation vor der Messung erkennen
können. Das C-Statuslayout bleibt bei 144 Bytes; die ABI-Version ändert die Semantik.

`proxy_probe.cpp` lädt diese Laufzeit ausschließlich mit einer gültigen
Startfreigabe eines lebenden Prototyp-Controllers. Der zugehörige
`strict_sync/game_runner.py` verbindet TCP, native Steuerung und die tatsächlichen
Lua-Messwerte. Eine native Bestätigung allein gilt ausdrücklich nicht als
Weltbestätigung. Der gemeinsame Vergleich umfasst Zeit, Firmenwerte und explizit
erfasste Objekte; seine Abdeckung bleibt unvollständig.

Im ersten Nutzertest wurden 206 HOLD-Durchläufe protokolliert; die erste
Fortschrittsfreigabe erreichte den fehlerhaften 100-ms-Aufruf und brach ab.
Die nachfolgenden Alpha4.1-Nutzertests bestätigten sechs beziehungsweise
38 Runden mit 200-ms-Fortschritten, bevor die Dateiverbindung abbrach. Das ist
noch kein Nachweis eines sicher beherrschten Initialisierungszeitpunkts oder
vollständiger Weltsynchronität. Ebenso offen sind die vollständige Kontrolle der
Wartungseffekte und die Anbindung der zurückgehaltenen normalen UI-Befehle. Die
automatisierten Tests ersetzen diese Engineversuche nicht.
