# Alpha4-Abbruch bei der ersten Fortschrittsfreigabe

Die Ursache der beobachteten Assertion ist die zu kleine, vom Prototyp gesetzte
Schrittweite: **100000 Mikrosekunden ergeben 0,1 Sekunden; die Emissionssimulation
verlangt mindestens 0,2 Sekunden.** Die Korrektur verwendet den normalen
200000-us-Schritt des geprüften Spielbuilds. Die Engine-Assertion wird weder
unterdrückt noch verändert.

## Tatsächliche Laufzeitbelege

Der erste Zweirechnertest wurde vom Nutzer durchgeführt. Die Fehleranalyse und
die neuen automatisierten Tests starten, steuern oder beenden TF2 nicht.

- Host-Bericht: `TF2-Alpha4-Bericht-a-20260906-184052.zip` im Steam-Saveordner.
- Darin: 206 erfolgreiche HOLD-Durchläufe, erster Fortschrittsframe noch laufend
  (`pending_state=3`, `pending_frame=1`, `pending_dt_us=100000`), ursprüngliches
  Aufruferargument `original_frame_time_us=200000`, Enginezeit weiter 13400 ms.
- Die lokale `crash_dump/stdout.txt` endet bei
  `Game/Terrain/EmissionMap.cpp:428`, `EmissionMap::Update(...) const`, mit
  `Assertion 'dt >= .2f' failed`.
- Eine spätere HALT-Datei beweist keinen angenommenen HALT: Der native Status
  blieb beim ersten laufenden Permit stehen. Die Engine hatte den Step nicht
  erfolgreich verlassen; der Prototyp meldete ihn auch nicht als abgeschlossen.

## Read-only-Befunde aus der Spiel-EXE

Windows-Build 35924, SHA256
`782b904a8f7bbdac1f7a18528f1a5c778691e5aa3087c37c351bf6912585175c`.
Alle Adressen sind relative virtuelle Adressen (RVAs).

| Stelle | Tatsächlicher Code und Folgerung |
|---|---|
| `0x11858d` | `RunGameSimLoop` lädt seinen Frame-Parameter aus `0x4133170`. Die gespeicherten Ausgangsbytes sind `40 0d 03 00`, also 200000. |
| `0x1185a0` | Der äußere Aufruf geht an `GameSim::Step`, `0x15aa00`. Der Nutzertest bestätigt ebenfalls ein eingehendes Argument von 200000. |
| `0x15aa7f..0x15aaa2` | `GameSim::Step` teilt den Mikrosekundenparameter ganzzahlig durch 1000. |
| `0x15aaa5..0x15aaaa` | Die Millisekunden werden in Float umgewandelt und mit `.001f` multipliziert; daraus entstehen Sekunden. |
| `0x15abb4..0x15abbb` | Der laufende Step übergibt diese Sekunden an die nachfolgende Update-Verarbeitung bei `0x23e1850`. |
| `0x2f7850` | Anfang der durch ihre Assertiontexte identifizierten Funktion `EmissionMap::Update`. |
| `0x2f7881` | `movss xmm0, [0x2f304c8]`; dort liegen `cd cc 4c 3e`, IEEE-754 `.2f`. |
| `0x2f7889..0x2f788c` | `comiss xmm3, xmm0; jb 0x2f7a98`: ein zu kleiner eingehender Zeitschritt führt zum Fehlerpfad. |
| `0x2f7a98..0x2f7ab3` | Assertionpfad enthält Funktionsname, `EmissionMap.cpp`, Zeile `0x1ac = 428` und `dt >= .2f`. |

Die Emissionsfunktion wird über Funktionszeiger angesprochen; die EXE enthält
bei `0x2f83d30` einen Zeiger auf `0x2f7850`. Die statische Prüfung allein behauptet
keinen vollständigen dynamischen Aufrufgraphen. Der tatsächlich protokollierte
Assertionpfad liefert hier den ergänzenden Laufzeitbeleg.

Die verwendete Skriptdatei `inspect_step_contract.py` liest ausschließlich die
EXE-Datei, prüft ihren vollständigen Hash und disassembliert begrenzte Bereiche.
Sie lädt die EXE nicht als ausführbaren Code. Ihre optionalen Analysepakete liegen
lokal unter `.analysis_deps`; sie gehören nicht zum Launcherpaket.

## Korrektur und Regression

- `TF2_PROBE_STEP_US=200000`, Permit nur für `0` oder `200000`.
- Auch HOLD und Pause übergeben einen gültigen 200000-us-Frame-Parameter;
  Geschwindigkeit null verhindert den Simulationsfortschritt.
- ABI 3, unverändertes 144-Byte-C-Statuslayout, Dateistatus zusätzlich
  `native_step_us=200000`. Alte 100000-us-Datensätze werden vor der Freigabe verworfen.
- Die tatsächliche Uhrdifferenz muss 200 ms für Fortschritt und null für HOLD/Pause
  betragen. Fehler werden nicht als erfolgreiche Frames bestätigt.
- Die Native-Kompatibilitätsprüfung umfasst nun auch den vollständigen
  `EmissionMap::Update`-Funktionskörper und die `.2f`-Konstante.
- Die Fake-Engine bildet unabhängig vom Prototypkonstanten die echte Umrechnung
  und `.2f`-Vorbedingung nach. Der alte 100000-us-Aufruf würde daran scheitern.
  Native Hook-/ASM-Tests, 10000 konkurrierende Permits, neun Dateilaufzeitfälle
  und die 20 bisherigen Deferred-Command-Szenarien bestehen.

**Noch nicht bestätigt:** ein erfolgreicher Wiederholungstest in zwei echten
TF2-Instanzen, unveränderte vollständige Weltzustände während HOLD oder die
zuverlässige Synchronisation beliebiger normaler Bau- und Fahrzeugaktionen.
