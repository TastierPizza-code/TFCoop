# Prüfstand

## Alpha5.19: geführter Straßenfahrzeug-/Linienversuch auf zwei PCs bestätigt

Der getrennte Modus `guided_suite_v1` führt durch 26 feste Host-/Freund-Aufträge.
Die Testspezifikation, Rolle und aktueller Schritt werden gemeinsam geprüft.
Fortschritt benötigt verglichene Vorschauen, beobachtete Ergebnisse und beide
Bestätigungen. Reine Fahrt-/Depotbeobachtungen sind von nativen Callbacks getrennt.
Der [Testumfang](docs/GUIDED_TEST.md) und die [Nachweischeckliste](docs/GAMEPLAY_CHECKLIST.md)
benennen offene Mechaniken. Der tatsächliche Lauf vom 8. September bestätigt alle
26 Schritte: 241 bytegleiche Journalzeilen, 24 echte Mutations-Callbacks, zwei reine
Beobachtungen und eine unveränderte, kostenfreie Rückstellung der noch zu frühen
Depotankunftsprüfung. Kauf und Verkauf buchen auf beiden PCs 23.890 beziehungsweise
23.777. Alle 27 Eingaben sind bestätigt; Abschluss bei Frame 304, Zeit 72,4 Sekunden
und Kontostand 4.651.328. [Auswertung](docs/ALPHA519_EVIDENCE.md).
Normale Spielwerkzeuge, beliebige Fahrzeugkonfigurationen, neue gleichzeitige
Linienkonflikte und vollständige Weltdeterministik bleiben offen. Die folgenden
älteren realen Nachweise bleiben gültig.

## Alpha5.16: begrenzter manueller Depotversuch im Zwei-PC-Spiel bestätigt

Ein zweiter tatsächlicher Lauf vom 8. September bestätigt jetzt beide
Gleichzeitigkeitsfälle: Host-Platz 1 und Mitspieler-Platz 2 kamen in derselben
Sammelrunde bei Frame 136 an und wurden beide gebaut. Beide Wünsche für Platz 4
kamen gemeinsam bei Frame 296 an: genau ein Bau und eine kostenfreie Ablehnung.
Die zweite Vorschau verwendet jeweils den bestätigten Zustand nach dem ersten
Bau, ohne Fortschrittsschritt innerhalb der Baufolge. 49 Weltjournalzeilen sind
bytegleich, alle acht Eingaben bestätigt, 342 native Fortschrittsschritte exakt.
Gemeinsames Ende bei Frame 352 ohne terminalen nativen Fehler. Normale Fahrt
etwa 0,948x, aktiver Durchschnitt einschließlich Bauprüfungen etwa 0,889x.
Dieser Lauf enthält keinen Bau während Pause; dessen Nachweis bleibt im ersten
Lauf erhalten. [Beide Auswertungen und Messgrenzen](docs/ALPHA516_EVIDENCE.md).

Die zuerst gelieferten Berichte vom 8. September 2026 sind ausgewertet: 97
bytegleiche Weltjournalzeilen, 47 passende öffentliche Payload-Hashes,
erneut geprüfte kurze Bereitschaft und gemeinsamer Abschluss bei Frame 338.
Vier manuell angeforderte Depots wurden während Fahrt und Pause mit passenden
Objekten, Transformationen und tatsächlichen Abbuchungen von zusammen 45.835
gebaut. Ein belegter Platz wurde auf beiden PCs ohne Kosten oder Änderung des
erfassten Zustands abgelehnt. Alle neun Eingaben wurden gemeinsam bestätigt.
Es gab keinen terminalen nativen Laufzeitfehler.

328 lückenlose zusätzliche Schritte bestätigen 65,6 Sekunden Simulationszeit.
Normale Fahrt einschließlich regelmäßiger Kontrollpunkte: 0,946689x/0,950844x.
Aktiver Durchschnitt einschließlich Bauprüfungen: 0,904032x/0,904892x.
Die erfolgreiche Depotanwendung erzeugte während Fahrt native Bestätigungsabstände
von etwa 1,20–1,40 Sekunden. Bewusste Pausen sind aus beiden Raten ausgeschlossen.
Dies misst weder FPS noch die vollständige Welt. [Auswertung und Methode](docs/ALPHA516_EVIDENCE.md).

Der neue getrennte Modus `manual_depot_v1` verbindet die tatsächlichen
Launcher-Handler, sitzungsgebundene Queue, gemeinsame Vorschau/Anwendung und
beidseitige Ergebnisbestätigung. Vier Testplätze und Vierteldrehungen sind
begrenzt; normale TF2-Bauwerkzeuge sind nicht angeschlossen.

Vorab erfolgreich geprüft:

- 15 gezielte Protokollfälle und drei tatsächliche TCP-/Queue-Durchläufe mit
  ausdrücklichen Modellwelten: Bau während Fahrt/Pause, gleiche Plätze,
  unterschiedliche Vorschauen, fehlgeschlagene Callbacks und frischer Abschluss.
- Zwölf Tests der produktiven Lua-/Python-Anbindung über echte Dateien mit
  nachgebildeter Spiel-API. Sie prüfen Vorschau, native Feld-/Arraygrenzen,
  reale Fixture-Callbacks, neue Objektbindungen, Kosten und unveränderte
  vorherige Objekte. Hinzu kommen 32 Geometrieprüfungen der lokal gelesenen
  Stock-Depotdefinition über vier Lua-Versionen; Stock-Dateien werden nicht
  veröffentlicht.
- Private Kopplung über tatsächliche Loopback-Verbindungen, neue interne
  Sitzungen bei gleichbleibendem Zugang, veraltete/manipulierte Nachrichten,
  kein Wiederbeitritt und keine Spielworker vor bestätigter Verbindung.
- Tatsächliche temporäre Vorbereitung, Installation, Startvalidierung und
  Wiederherstellung aller fünf Modi und beider Rollen. Zusätzlich wurden die
  tatsächlichen lokalen Spiel-/Save-Dateien nur gelesen und separat gestagt;
  Installer- und Startvalidierung bestanden ohne Spielinstallation oder Start.
- Eigene Betriebssystem-Sperre für die bereits wartende Lobby, Schutz gegen
  Update/Installation während dieser Wartephase und Prüfungen auf private
  Profile/Adressen in öffentlichen Paketen beziehungsweise Diagnosekopien.

`paced_live_probe.py` und `stream_engine.py` bleiben bytegleich mit der
akzeptierten Alpha5.15-Referenz. Leere Eingaben erzeugen dieselbe Folge von
Fortschrittsfreigaben; der neue Baupfad ist separat. Diese Quell-/Modellprüfung
ist kein neuer Beweis für die tatsächliche Flüssigkeit auf beiden PCs.

Die offizielle API beschreibt die read-only Bauvorprüfung, aber nicht alle
von ihr gelieferten Felder vollständig. Zusätzliche lokale Upstream-Belege
stützen die verwendeten Felder. Die vier erfolgreichen Aufträge bestätigen nun
auch die neue Vorschau für die dort beobachteten Rückgaben. Weitere Fehlerformen
bleiben offen. Unlesbare Daten halten vor Mutation an und erzeugen
begrenzte Diagnosefelder. [Quellen und genaue Grenze](docs/MANUAL_DEPOT_ENGINE_CONTRACT.md).

**Der gemessene Launcher-Depotablauf ist bestanden.** Beide Spieler haben gebaut,
Bau in Fahrt/Pause und belegter Platz sind erfasst. Im ersten Lauf liegen die
zwei Wünsche für Platz 4 in aufeinanderfolgenden Sammelrunden, 0,4
Simulationssekunden auseinander. Der zweite Lauf bestätigt zusätzlich den
Konflikt innerhalb derselben Sammelrunde. Die Läufe bleiben als getrennte
Belege erhalten. Neue Kopfsektionen ersetzen keine historischen Laufbelege unten.

## Alpha5.15: tatsächlicher Zwei-PC-Lauf bestanden und Tempo akzeptiert

Die beiden Originalberichte vom 8. September 2026 sind ausgewertet: 133
bytegleiche Weltjournalzeilen, 40 passende öffentliche Payload-Hashes,
erneut berechneter kurzer Bereitschaftsnachweis und gemeinsamer Abschluss
bei Frame 192. Sieben echte Pause-/Fortsetzen-Wechsel beider Spieler,
acht abgeschlossene Wünsche und 47,375 Sekunden gemeinsam gemessene Pause
sind bestätigt. Alle 182 nativen Fortschrittsschritte der Eingabephase und
93 unveränderten Pausenprüfungen passen zusammen. Keine terminalen Fehler.

36,4 Sekunden aktive Spielzeit benötigen 38,748514 beziehungsweise 38,806138
Sekunden: ungefähr 0,94x. Der Nutzer akzeptiert dieses Fahrgefühl ausdrücklich
und möchte es beibehalten. Längere Bestätigungsabstände treten deutlich
seltener auf als in Alpha5.13. Der kurze Aufbau dauert 12,500 Sekunden.
Paket, Quellstand, Basissave und Originalbelege sind zusätzlich privat gesichert.
[Messdefinitionen, Vergleich und Grenzen](docs/ACCEPTED_INPUT_BASELINE.md).

Die Annahme gilt für die beobachtete kurze Szene. Die folgenden Aussagen über
noch ausstehende Tests beschreiben jeweils den damaligen Stand vor diesem Lauf.
Native Spielbuttons, freies Bauen und vollständige Weltsynchronität sind weiterhin
offen; die ältere Alpha5.12-Ausdauerreferenz bleibt unverändert erhalten.

## Alpha5.15: Vorbereitungspfad zusammenhängend geprüft

Alpha5.14 brach beim Vorbereiten des kurzen Modus vor der Installation ab:
Die Vorbereitung schrieb `preparation=short_scene_v1`, während die getrennte
Prüfliste im Installer das neue Feld noch ablehnte. Die unten aufgeführten
362 Vorabprüfungen deckten diese konkrete Integration nicht ab; sie waren
kein Nachweis, dass der neue Launcherpfad erfolgreich installiert werden konnte.

Vorbereitung, Installer und Startprüfung verwenden in Alpha5.15 dieselbe
strikte Prüfung. Der bekannte kurze Vertrag wird nur mit `build_v2` akzeptiert;
unbekannte Felder, ungültige Kombinationen und unechte boolesche Werte bleiben
unzulässig. Das Simulationsprotokoll und der native Pacer sind unverändert.

`test_preparation_pipeline.py` führt den tatsächlichen Launcher-Vorbereitungspfad
über Staging und Installation bis `read_setup`, Profil-/Payloadprüfung und
Wiederherstellung in temporären Spiel- und Saveordnern aus. Alle vier Modi
und beide Rollen sind abgedeckt; Staging und Installation sind nicht gemockt.
Nur Binary-/Audioidentität und Prozesssuche verwenden Testdaten. Manipulierte
Konfigurationen werden mit neu gebundenen Hashes getestet, damit tatsächlich
die Konfigurationsprüfung greift; die Ablehnung muss vor Spiel-/Saveänderungen
erfolgen. Originalsave, importierte Savebytes und Wiederherstellung werden verglichen.

Zusätzlich wurden alle vier Staging-Pakete aus den tatsächlichen lokalen
Spiel- und Save-Dateien neu erzeugt und durch die vollständige Installer- sowie
Startvalidierung geprüft. Die echte Spielinstallation wurde dabei nur gelesen.
Die konkreten Dateien des gemeldeten Fehlversuchs bestehen jetzt ebenfalls
die korrigierte Installerprüfung. Keine Spielinstanz wurde gestartet.
Die tatsächliche Zwei-PC-Fahrt und die früheren Laufzeit-Timeouts bleiben offen.

Der veröffentlichte Alpha5.14-Installer reproduziert im neuen Integrationstest
den exakten gemeldeten Fehler für beide Rollen; alle sechs alten Modus-/Rollen-
Kombinationen bestehen ihn bereits. Der korrigierte Stand besteht alle acht.
Zusammen mit den betroffenen Vorbereitungs-, Installer-, Treiber-, Launcher-
und Updateprüfungen bestanden 204 ausgewählte Tests vor der Paketbildung.

## Alpha5.14: gezielte Optimierung, echte Flüssigkeit noch offen

`paced_live_v1` ergänzt einen getrennten Modus mit zehn Runden Vorbereitung
und versiegelten Eingaben in bereits notwendigen Bestätigungen. Die vollständigen
bisherigen Modi und der native Pacer bleiben erhalten. Der Anlass ist die
tatsächlich gemessene Regression von ungefähr 0,962x auf ungefähr 0,82x.
In Alpha5.13 entfielen 4,746 Sekunden auf 118 leere Eingabeabfragen direkt vor
Fahrtfreigaben. Allerdings traten große ACK-Abstände auch innerhalb von
Zweierserien auf: Die leere Abfrage ist nicht als alleinige Ursache nachgewiesen.

Die Vorprüfung verwendet ausdrücklich Engine- und Uhrenmodelle und startet
weder TF2 noch eine Desktopoberfläche. Neue Tests prüfen das Versiegeln in
Antworten, beide Freigabebedingungen, späte und doppelte Eingaben, fehlende
oder falsche Siegel, frische Weltprüfungen, tatsächliche modellierte
Befehlsbestätigungen, lange Pause und die finale beidseitige Grenze.
Ein Vergleich bei gleicher Folge von 26 Fahrtblöcken entfernt genau 27
zusätzliche Abfragerunden: 59 Phasenaktionen werden 32, alle anderen bleiben
gleich. Das ist ein Protokollvergleich, kein gemessenes TF2-Tempo.

Der neue Bereitschaftsnachweis verlangt zehn Callback-Ergebnisse, Objekte,
Verbindungen, tatsächlichen Kaufabzug, Linienzuweisung und abgefahrenen
Fahrzeugzustand bei Frame 10. Die letzte Aufbauantwort wird vor diesem
Nachweis nicht versandt. Der Bericht weist ausdrücklich `full_build_proof=false`
und `vehicle_displacement_verified=false` aus. Status-Coalescing lässt
Bestätigungen und Fehler sofort durch und protokolliert seine lokalen Kosten.
TCP-Tests mit echten Dateien und modellierter Engine prüfen auch den Übergang
von Vorbereitung zu Eingaben sowie Stopps bei fehlender Bereitschaft,
fehlender nativer Bestätigung und divergierender Weltbeobachtung.

**Der tatsächliche Zwei-PC-Lauf mit Alpha5.14 steht aus.** Es gibt noch keinen
Beleg für wieder erreichte 0,962x oder weniger sichtbare Zuckler. Die vorherigen
Startprobleme werden ebenfalls nicht als behoben behauptet. Freie Bauwerkzeuge,
native UI-Pause und vollständige Weltzustände sind nicht Teil dieser Freigabe.

Vor Veröffentlichung bestanden 362 ausgewählte Prüfungen: 190 für Launcher,
Dateiqueue, Vorbereitung, Installation und Updates; 108 für neue und erhaltene
Protokolle sowie Statuszusammenfassung; 64 für kurzen Bereitschaftsnachweis,
TCP-Treiber und erhaltene Bau-/Fahrt-/Eingabeabläufe. Die Referenzmodule
`stream_engine`, `stream_probe`, `timing_probe`, `live_probe`, `live_input`,
`engine_mailbox`, `build_profile`, `core` und `replica` sowie die strikte Lua-Engine
wurden bytegleich zum vorherigen veröffentlichten Quellstand geprüft.
Das gesicherte Alpha5.12-Archiv stimmt weiter mit seiner ursprünglichen SHA256 überein.

## Alpha5.13: tatsächlicher Zwei-PC-Eingabetest bestanden, Tempo schlechter

Am 8. September 2026 wurden beide Original-ZIPs geprüft. Ihre Weltjournale
mit 380 Zeilen sind bytegleich, 37 Payload-Hashes passen zum Release und
die vollständige Bauprüfung wurde aus den Daten erneut berechnet.
Alle sechs echten gegenseitigen Pause-/Fortsetzen-Wechsel, sieben gemeinsam
bestätigten Wünsche und der finale Weltvergleich passen zusammen. Die lange
Pause ist mit 59,297 Sekunden gemeinsam gemessen; unabhängige native Zähler
belegen zusätzlich über 58 Sekunden unveränderte Zustände. Abschluss:
Frame 488, Enginezeit 105,2 s, Firmenkonto 4.651.939 und Darlehen 5.000.000.

Die aktive Fahrt erreicht nur etwa 0,820x beziehungsweise 0,816x. Häufigere
Unterbrechungen sind sowohl berichtet als auch in den ACK-Zeitabständen
messbar. Zusätzliche Eingabeabfragen tragen plausibel dazu bei, sind aber
nicht als alleinige Ursache isoliert. Alpha5.12 bleibt die akzeptierte
Temporeferenz. Gleichzeitige Gegensätze wurden nicht protokolliert; normale
UI-Pause, freies Bauen und vollständige Weltprüfung bleiben offen.
Vollständige Nachrechnung, Messdefinitionen und Grenzen:
[Alpha5.13-Evidenz](docs/ALPHA513_EVIDENCE.md).

## Alpha5.13: ursprüngliche Vorabprüfungen vor dem Zwei-PC-Lauf

Der neue Standard `live_input_v1` ergänzt echte Pause-/Fortsetzen- und
Abschlusswünsche aus beiden Launchern. Die normale TF2-UI bleibt unangebunden.
Für diese Vorabprüfungen wurde kein Spiel gestartet und kein Desktop bedient.
Die folgenden Vorabprüfungen verwenden ausdrücklich Engine- und Uhrenmodelle:

- `test_live_input.py`: 15 Datei-/Prozess-/Parallelitätstests prüfen atomare
  Annahme, exklusive Schreibrechte, strikte Sitzung/Sequenz, unveränderte
  Historie, begrenzte Listen, Windows-Sharing und terminales `END_TEST`.
- `test_live_probe.py`: Dynamische Eingaben, Pausevorrang, vollständige
  beidseitige Ergebnisse, unveränderte Pausen, getrennte kurze und lange
  Pausen, Phasentimeouts, fehlende oder doppelte Nachrichten, frische
  Kontrollpunkte und der gemeinsame letzte Abschluss werden geprüft.
  Eine fehlende optionale Konfliktprobe verfälscht die Pflichtabnahme nicht.
- `test_live_driver.py`: Der produktive Host und beide Spieltreiber sprechen
  über echtes lokales TCP und lesen tatsächlich geschriebene Queuedateien.
  Die Welten bleiben Modelle. Ein erweiterter Lauf enthält 1000 modellierte
  Pausen-Heartbeats und 930 kleine Fahrtfreigaben. Sein real erzeugter
  Hostbericht ist über 4 MiB groß und wird mit dem begrenzten 16-MiB-Lesepfad
  vollständig gelesen und exportiert. Beide Weltjournale stimmen überein.
- Die Driverprüfungen halten die letzte Bestätigung eines Peers zurück,
  verzögern alte Poll-/Checkpoint-Duplikate und erzeugen native Messfehler,
  Weltdifferenzen sowie verlorene oder mutierte Eingabequeues. Keine dieser
  Situationen erlaubt einen vorzeitigen regulären Abschluss oder eine weitere
  Freigabe nach erkanntem Fehler. Ungültige Queueidentitäten scheitern vor
  der Erstellung einer Spielstartberechtigung.
- Launcherprüfungen führen reale Ereignisbehandlung ohne Tk-Fenster aus.
  Sie unterscheiden lokale Annahme von gemeinsamer Bestätigung, sperren
  nach `END_TEST` und bei Abbruch und erhalten alle drei Testmodi.
  Paket-, Installations- und Updaterprüfungen bleiben zusätzlich erforderlich.

`required_interactions_met` verlangt nach korrektem Abschluss tatsächliche
Pause- und Fortsetzen-Übergänge beider Spieler sowie mindestens 35 Sekunden
einer zusammenhängenden unveränderten Pause. Der Host misst monotone Zeit
zwischen gemeinsam bestätigten frischen Grenzen, die Peers getrennt ihre
lokalen Spannen. Netzwerk-/Dateiwartezeit innerhalb dieser Pause zählt mit;
mehrere kurze Pausen werden nicht addiert. Konflikte verschiedener Spieler
werden separat ausgewiesen. Die Anleitung verlangt 45 Sekunden und das
Abwarten der gemessenen langen Pause auf beiden PCs.

Native Fortschrittsgrenzen, historische Weltbeobachtungen, lokal angenommene
Wünsche und gemeinsam bestätigte Ausführung bleiben getrennt. Ein nach der
letzten Sammlung angenommener Wunsch kann unbestätigt bleiben. Der finale
Weltvergleich beweist nur die erfasste Szene. Freies Bauen, normale UI-Pause,
vollständige Weltdeterministik und Bildflüssigkeit sind damit nicht nachgewiesen.
Der oben dokumentierte echte Alpha5.13-Lauf ergänzt diese Vorabprüfungen.

Die akzeptierte Referenz `stream_v1`, ihr Taktgeber und der native/Lua-Adapter
bleiben unverändert. Alpha5.12 ist im Launcher weiterhin ausführbar; seine
Release-Dateien und der Quelltag werden nicht überschrieben.

## Alpha5.12: akzeptierter tatsächlicher Zwei-PC-Referenzlauf

Am 7. September 2026 wurden beide Originalberichte geprüft. Die Archive sind
CRC-fehlerfrei, ihr gemeinsames Manifest und 35 Payload-Dateien passen zum
veröffentlichten Paket. Die Weltjournale mit 270 Einträgen sind bytegleich;
SHA-256: `91757db405b0d3828a8e455e57cd64ec63414d448873f275e3c56ff09fa18333`.
Der Bauabschluss, alle 600 weiteren nativen Schrittquittungen, zwölf gemeinsame
Kontrollpunkte und Pause/Fortsetzen wurden aus den Daten erneut nachgerechnet.
Beide erreichen Frame 840 bei 175,6 Sekunden Enginezeit, Firmenkonto 4.647.799
und Darlehen 5.000.000. Es gibt keine Abweichung der erfassten Zustände und keinen
nativen Terminalfehler.

Die Fahrtspannen benötigen für 120 Sekunden Spielzeit 124,737507 beziehungsweise
124,733292 Sekunden, einschließlich gewöhnlicher Kontrollpunkte und ohne die
absichtliche mittlere Testpause. Das entspricht etwa 0,962x. Mitteltempo und
95. Perzentil bestehen die bisherigen Vorgaben. Nur maximale gelesene
Bestätigungsabstände von 419,403 beziehungsweise 418,154 ms überschreiten die
400-ms-Grenze; deshalb bleibt die Originalanzeige des Tempoziels negativ.

Der Nutzer akzeptiert die Fahrt mit fast unsichtbaren kurzen Zucklern und erklärt
diesen Abschnitt für abgeschlossen. Der Stand ist gesichert; weitere Tempo- und
Darstellungsoptimierung wird zurückgestellt. Die Akzeptanz gilt für diese
beobachtete Szene, nicht für noch fehlende freie Eingaben oder die vollständige
Spielwelt. Paketidentität, Grenzen und Sicherung: [akzeptierte Referenz](docs/ACCEPTED_BASELINE.md).

Der erhaltene Referenzmodus `stream_v1` beginnt mit dem vorhandenen Bauprofil:
zwölf Befehle, 240 Schritte und separat abgeschlossener Bauprüfung. Danach
legt `paced-stream-v1` 600 weitere native Fortschrittsschritte à 200000
Mikrosekunden fest, also 120 Sekunden zusätzliche Simulationszeit. Jeweils
zwei Schritte werden gemeinsam freigegeben; jede native Bestätigung muss zur
zulässigen Uhr, Schrittweite und Framegrenze gehören. Alle 50 Schritte gibt
es eine neue Lua-Beobachtung und einen gemeinsamen Weltvergleich.

Nach 300 Fortschrittsschritten, also 60 Sekunden Fahrt und bei Frame 540,
führt der feste Plan `a:8` für Pause aus. Beide prüfen während zwei Sekunden
gemessener Wartezeit dieselbe gehaltene Welt; `b:6` setzt am selben Frame fort.
Erst die beiden letzten frischen Kontrollpunkte bei Frame 840 erlauben den
Abschluss. Die Wünsche sind automatisch vorbereitet. Sie testen keine normalen
Pause-Tasten und keine frei eintreffenden Eingaben.

Der oben beschriebene echte Lauf ergänzt die Vorabprüfungen, die kein Spiel
starteten und keinen Desktop bedienten. Die tatsächlichen Alpha5.11-Ergebnisse
unten bleiben separat für den erhaltenen Vergleichsmodus dokumentiert.

Die Vorabprüfungen behandeln mehrere getrennte Ebenen:

- Protokoll- und Replica-Tests prüfen den unveränderlichen Plan, native Zeitgrenzen, Kontrollpunkte, doppelte Nachrichten, den Pausenablauf und den gemeinsamen Abschluss.
- Adaptertests ersetzen native Engine und Uhr ausdrücklich. Sie prüfen zeitlich begrenzte Operationen, fehlende oder falsche Bestätigungen, Stoppen und die Trennung zwischen nativen Fortschrittsmeldungen und historischen Lua-Beobachtungen.
- `test_stream_driver.py` verbindet den produktiven TCP-Host und beide Spieltreiber mit ausdrücklichen Engine-Modellen. Der vollständige Aufbau mit anschließend 600 Schritten endet bei Frame 840. Ein zurückgehaltener letzter Kontrollpunkt verhindert den globalen Abschluss. Abweichende Kontrollpunkte, fehlende native Messungen und veraltete native Uhrwerte müssen vor einer weiteren Freigabe abbrechen.
- Die gleichen Integrationstests prüfen Journal, Diagnoseexport und Beobachtungsgrenzen. Reine native Antworten enthalten keinen historischen Welthash. Nur frische Weltbeobachtungen dürfen ins Weltjournal; nach einem Fehler bleibt der letzte bestätigte Beobachtungsframe nachvollziehbar.
- Die bestehenden Timing-, Lua-/Datei-IPC-, Bau-, Installer-, Launcher- und Updaterprüfungen sichern die bisherigen Pfade ab. Der erhaltene Alpha5.11-Vergleichsmodus bleibt zusätzlich durch `test_timing_driver.py` abgedeckt. Lua- und Dateischnittstellenprüfungen verwenden Ersatz für die tatsächliche Spielwelt und sind kein weiterer TF2-Lauf.

Diese Prüfungen belegen Programmverhalten in den jeweiligen Testaufbauten.
Ein eingefrorener Paket-Selbsttest und eine spätere Downloadprüfung sind
zusätzliche Lieferprüfungen; auch sie ersetzen keine echte Spielmessung.

Der Dauertest bewertet zwei Teilstrecken mit je 300 Schritten. Gewöhnliche
Kontrollpunkte innerhalb der Strecke gehen in die lokalen Freigabe- und
Bestätigungsabstände ein; die absichtliche Pause in der Mitte wird getrennt
behandelt. Das Tempoziel verlangt 95 bis 105 Prozent von 1x, ein 95. Perzentil
der Abstände von höchstens 250 ms und einen Maximalwert von höchstens 400 ms.
Aufrufzeiten werden vor der Dateiübertragung gemessen, Bestätigungszeiten beim
lokalen Lesen. Native Ankunftszeiten und gerenderte Bilder sind nicht erfasst.
Die Zielspanne und gesamte lokale Wallzeit stehen getrennt im Bericht.

Die bisherigen Übergangsstopps nach jeweils fünf Sekunden werden im neuen
Modus nicht mehr angelegt. Weltabfragen und Netzwerkbestätigungen können aber
weiterhin kurz anhalten. Eine bestandene Tempoauswertung wäre deshalb kein
Nachweis visueller Flüssigkeit. Vollständiger Welthash, langfristige gemeinsame
Simulation, UI-Pause, freie Baueingaben und Cursor bleiben ungeprüft.

Im aktuellen Launcher bleibt **Vergleichstest aus Alpha5.11** (`timing_v1`)
erhalten: zwölf Fünf-Sekunden-Abschnitte mit ungleichen Zusatzwartezeiten.
Dafür ist kein Downgrade nötig. Der alte Git-Tag `v0.5.11` bleibt bestehen;
Quellbundle, damaliges Paket, saubere Basis und beide Originalberichte wurden
zusätzlich privat gesichert. Kopierprüfsummen, ZIP-CRCs und Git-Bundle wurden
geprüft. Diese privaten Sicherungen gehören nicht in den öffentlichen Export.
Die Ausgangsbasis bleibt unverändert und benötigt auf den bisherigen beiden
PCs keinen erneuten Import.

## Alpha5.11: tatsächlicher gemeinsamer Zwei-PC-Test abgeschlossen

Am 7. September 2026 wurden die beiden privaten Originalberichte des gemeinsamen
TF2-Tests ausgewertet. Beide Archive bestehen die CRC-Prüfung. Gemeinsames
Manifest und 33 ausgelieferte Payload-Dateien stimmen mit der veröffentlichten
Version überein. Der Koordinator und beide Teilnehmer melden einen
abgeschlossenen Versuch ohne nativen Terminalfehler.

Die Journale beider PCs sind bytegleich und enthalten jeweils 278 Zeilen:
einen Ausgangszustand, zwölf Baubefehle, 240 Schrittbestätigungen, zwölf
Bereitschaftsbeobachtungen, zwölf Abschnittsabschlüsse und einen Endsatz.
Die gemeinsame SHA-256 lautet
`fe4c7aab250e270bddd5a0366334a72649c6281f675e5ab69eef229bb941a674`.
Bauabschluss und sämtliche erfassten Zustandsprüfsummen wurden aus den
Berichten erneut berechnet. Alle 29 Pausenschritte im Aufbau halten den
beobachteten Zustand unverändert; alle zwölf zusätzlichen Fahrtgrenzen
stimmen überein. Die gemessenen Wartezeiten und nativen Messwerte wurden
gegen den festen Ablauf erneut validiert.

Der Versuch endet auf beiden PCs bei Frame 540 und Enginezeit 115,6 Sekunden.
Auf den Aufbau folgen 300 Fortschrittsschritte mit 60 Sekunden zusätzlicher
Spielzeit. Das Firmenkonto beträgt auf beiden PCs 4.651.939; das Darlehen
bleibt bei 5.000.000. Teststraße, Depot, Haltestellen, Fahrzeug und Linie
wurden vom automatischen Ablauf aufgebaut beziehungsweise verwendet.

**Der Zustandsvergleich wurde abgeschlossen; das 1x-Tempoziel wurde nicht
erreicht.** Die Fahrtmethoden benötigen für 60 Sekunden zusätzliche Spielzeit
auf PC a insgesamt 66,155 Sekunden und auf PC b 66,299 Sekunden. Diese Werte
enthalten ihre Anfangs-/Endbeobachtungen, aber noch nicht die gemeinsamen
Haltepunkte zwischen den Abschnitten. Die gesamte Timingphase beim Host
dauert 78,078 Sekunden. Ein abgeschlossenes Journal darf deshalb nicht als
bestandener durchgängiger 1x-Betrieb dargestellt werden.

Die beobachteten Bestätigungsabstände innerhalb der Abschnitte liegen näher
am Ziel: Das 95. Perzentil beträgt auf beiden PCs 219 ms, das Maximum 235 ms
beziehungsweise 219 ms. Die höheren Abschnittsdauern führen dennoch zu einem
negativen `paced_windows_1x_met`. Es wäre falsch, nur die günstigen inneren
Abstände zu verwenden und den Aufwand der Weltbeobachtungen wegzulassen.

Die Spieler beschreiben normale Fahrzeugbewegung innerhalb der Abschnitte und
kurze Stopps alle fünf Sekunden. Das ist eine Nutzerbeobachtung; Renderzeiten
wurden nicht gemessen. Der Versuch liefert echte Netzwerk- und Spielbelege für
die beobachtete Szene und vorgegebenen Warte-/Pauseabläufe. Er bestätigt weder
sämtliche internen Spielzustände noch native UI-Pause, freie gleichzeitige
Bauwerkzeuge oder dauerhaften gemeinsamen Spielbetrieb.

Die vorausgehenden Alpha5.11-Vorabtests hatten ausschließlich Modelle und
nachgebildete Spiel-/Native-Schnittstellen verwendet. Der jetzt vorliegende
Zwei-PC-Test ist davon als tatsächliche Spielevidenz getrennt. Einzelheiten
beider weiterhin verfügbaren Abläufe: [BUILD_TEST.md](BUILD_TEST.md).
Anleitung: [ANLEITUNG.md](ANLEITUNG.md).

## Alpha5.10: zwei vollständige echte Durchläufe

Am 7. September 2026 haben zwei nacheinander frisch gestartete TF2-Prozesse auf
demselben PC den vollständigen Bautest bestanden. Der erste Prozess zeichnet
die wirklich gesendeten Aufträge und zurückgelesenen Zustände auf. Der zweite
lädt eine frische Kopie desselben Savepaars und liest genau diesen validierten
Befehlsstrom ein. Beide bestätigen zwölf Aufträge und 240 Zeitschritte; alle
252 Anfragen, Ergebnisse und beobachteten Zustandsgrenzen stimmen überein.
Beide Journale enthalten jeweils 507 geprüfte Zeilen mit vollständiger Hashkette.

Die Straße, das Depot, zwei Haltestellen und drei Straßenverbindungen werden
gebaut; das gekaufte Fahrzeug wird einer Linie zugewiesen, verlässt das Depot
und bewegt sich. Die maximale beobachtete Entfernung zur ersten Fahrposition
beträgt 141,81 Meter. 211 Fortschrittsschritte ergeben 42,2 Sekunden Enginezeit
(13,4 bis 55,6 Sekunden). Alle 29 Pausenschritte halten den erfassten Zustand
unverändert, einschließlich der 20 Schritte ab Runde 80. Das Konto sinkt von
5.000.000 auf 4.656.092; der Fahrzeugkauf bucht 23.890 ab. Das Darlehen bleibt
bei 5.000.000. Die Abschlussnachweise stimmen zwischen Record und Replay überein.

Beide Spielprotokolle bestätigen die jeweils frisch importierte Save und
ausschließlich Legacy Fahrzeuge und Strict Sync Alpha5.10. Manifest und
installierter Bauadapter entsprechen der geprüften Quelle. Beide exakt
zugeordneten Spielprozesse beenden sich regulär; Prozessende und anschließende
Wiederherstellung sind bestätigt, ohne Fehler bei der Bereinigung.

Dies ist ein echter lokaler Wiederholbarkeitsnachweis für die beobachteten
Bauvorgänge, Firmenwerte, Fahrzeugzustände und vorgegebenen Pausen. Die Prozesse
laufen nacheinander auf einem PC. Netzwerkverzögerungen zwischen zwei Spielern,
unbeobachtete Weltzustände, vollständige deterministische Simulation, freie
gleichzeitige Eingaben und die normalen Pause-Tasten sind damit nicht geprüft.

### Rückgabewerte unter TF2s Lua-Anpassung

Der erste echte Alpha5.9-Nachtest scheiterte bereits vor Messbeginn:
`snapshot()` lieferte einen Wahrheitswert statt einer Zustandstabelle. Es wurden
keine Bauaufträge oder Zeitschritte freigegeben. Die native Startprüfung war
fehlerfrei; Spielprotokoll und Modliste bestätigten die richtige frische Save
und die Version Alpha5.9. Der eigene Spielprozess wurde nach einem Timeout des
normalen Beendens über seinen zuvor verifizierten Prozesshandle geschlossen.
Prozessende und Wiederherstellung der Installation sind bestätigt.

Ursache ist eine Regression im mit Alpha5.9 eingeführten Lebensdauerschutz.
TF2 überschreibt in seinem installierten `res/scripts/init.lua` die Funktion
`table.unpack(t)` und reicht Anfangs- und Endargumente nicht weiter. Die neue
Operationshülle wollte das erste `pcall`-Ergebnis auslassen, gab dadurch aber
auch dessen Erfolgsboolean zurück. Alpha5.10 reicht die Rückgaben stattdessen
direkt als Lua-Varargs weiter. Der Schutz der nativen Elternobjekte bleibt
unverändert, einschließlich Freigabe auf Erfolg und Fehler. Es werden keine
fehlenden Zustandswerte ersetzt. Weitere Slice-Aufrufe dieses Helpers wurden
im aktuellen Projektcode nicht gefunden.

Die gezielte Regression bildet TF2s ignorierte Sliceparameter zusätzlich zur
erzwungenen Speicherbereinigung nach. Alle 52 Prüfungen bestehen: je 13 unter
Lua 5.1 bis 5.4, einschließlich Bauablauf, exakter Rückgabeanzahl, verschachtelter
Aufrufe sowie Freigabe und Erholung nach Fehlern. Unveränderter Alpha5.9-Code
scheitert dagegen unter jeder Runtime an denselben vier neuen Adapterprüfungen.
Der direkte Lua-Aufruf zeigt unter allen vier Runtimes zwei Rückgaben mit einem
Boolean zuerst für Alpha5.9 und eine Zustandstabelle für Alpha5.10. Die 340
bisherigen Bauadapter-Prüfungen und 85 Python-Prüfungen für Einstieg, Staging,
Baseline, Veröffentlichung und Launcher-Vorbereitung bestehen ebenfalls. Ebenso
bestehen die 16 lokalen Record-/Replay-Prüfungen einschließlich vollständigem
240-Runden-Lua-/Datei-IPC-Vergleich mit nachgebildeten Spiel- und nativen APIs.
Die echte Alpha5.10-Nachprüfung ist oben separat dokumentiert; die bisherigen
Alpha5.8-Ergebnisse unten bleiben als historische Befunde erhalten.
Das neue saubere private Savepaar aus Alpha5.9 bleibt unverändert gültig.

## Alpha5.9: Lebensdauer nativer Objekte und neue Ausgangssave (historischer Stand)

Dieser Abschnitt beschreibt den Stand vor dem Alpha5.10-Nachtest. Neuere
Ergebnisse und die dabei erkannte Rückgaberegression stehen oben.

Ein echter lokaler Alpha5.8-Durchlauf bestätigt alle zwölf Aufträge und 240
Zeitschritte: Straße, Depot, zwei Haltestellen, drei Verbindungen, Fahrzeugkauf,
Linie, Zuweisung, Abfahrt und automatische Pause. Die erfasste Enginezeit steigt
von 13,4 auf 55,6 Sekunden. Das Konto sinkt von 5.000.000 auf 4.656.092,
das Darlehen bleibt bei 5.000.000. Das Fahrzeug verlässt das Depot und erreicht
eine maximale beobachtete Entfernung von 141,81 Metern zur Anfangsposition.
Alle 507 Journalzeilen, ihre Hashkette und der Abschlussnachweis sind geprüft.

Ein zweiter frischer TF2-Prozess spielt genau diesen gespeicherten Befehlsstrom
ab. Bis einschließlich Frame 99 sind alle bestätigten Zustände identisch:
elf Aufträge und 99 Schritte. Beim Lesen vor dem nächsten Pausenschritt scheitert
`a:2.CONSTRUCTION.frozenEdges[1]` mit `nil`. Es gibt keine weitere Schrittfreigabe;
die Zeit bleibt bei 27,6 Sekunden. Die folgenden Graphfehler entstehen aus den
dadurch fehlenden gelesenen Knotennamen. Der unabhängige Rohbericht liest dieselbe
Liste anschließend wieder mit Länge drei und drei gültigen numerischen Einträgen.
Das ist ein fehlgeschlagener Replay mit einem Lesefehler, kein abgeschlossener
Wiederholbarkeitsnachweis und kein beobachteter abweichender gültiger Weltzustand.

Der fehlerhafte Pfad entnimmt die Liste einem nur temporär gehaltenen Component.
Andere Lesepfade halten dessen Besitzer während der Umwandlung fest. Das passt
zu einer geliehenen nativen Unterstruktur, deren Besitzer durch Lua-GC zu früh
freigegeben werden kann. Sol dokumentiert nicht besitzende Referenzen und eigene
Mechanismen zum Erhalten von Elternobjekten; welche Bindung TF2 intern konkret
verwendet, wurde damit nicht direkt gemessen.
[Sol-Referenzen](https://sol2.readthedocs.io/en/latest/api/usertype_memory.html),
[Elternobjekte erhalten](https://sol2.readthedocs.io/en/v2.20.6/api/filters.html).

Alpha5.9 hält die beobachteten Besitzer und Unterstrukturen für die gesamte
Umwandlung einer Bauoperation fest. Verschachtelte Aufrufe teilen diesen Schutz.
Die Referenzen werden bei Erfolg und Fehler freigegeben und nicht über Spielticks
gesammelt; eine feste Obergrenze verhindert unbeschränktes Wachstum. Getter werden
nicht wiederholt, fehlende Werte nicht ersetzt und geordnete Arrays nicht neu
sortiert. Native DLLs und Bauprofil bleiben unverändert. Die Korrektur benötigt
noch den nächsten echten Spielversuch; ein erfolgreicher Alpha5.9-Game-Replay
wird hier ausdrücklich nicht behauptet.

Die 340 bisherigen Bauadapter-Prüfungen bestehen weiterhin. Hinzu kommen 32
Prüfungen (acht unter jeder Lua-Version 5.1 bis 5.4) mit echten Userdata,
`__gc`-Finalisierung und geliehenen Unterstrukturen. Die Fixture erzwingt echte
Speicherbereinigung bei Zugriffen und enthält keinen Fehler-Sonderschalter für
`frozenEdges`. Unveränderter Alpha5.8-Code mit derselben SHA-256 wie im echten
Record reproduziert damit den konkreten Listenfehler auf allen vier Runtimes.
Alpha5.9 besteht den Bauablauf, verschachtelte Aufrufe und Freigaben bei Erfolg
und Fehler. Das belegt den Fehlermechanismus der Nachbildung und den allgemeinen
Schutz, ersetzt aber nicht die nächste reale TF2-Nachprüfung.

Die finale Quellprüfung besteht außerdem aus 184 Python-Prüfungen für Einstieg,
Staging, Import, Update, Veröffentlichung, Launcher, Bauprofil und Teststeuerung,
neun Lua-/Mailbox-Prüfungen sowie 16 lokalen Record-/Replay-Prüfungen. Die beiden
vollständigen Integrationen durchlaufen das Bauprofil mit nachgebildeten Spiel-
und nativen APIs: einmal mit zwei verbundenen Lua-VMs, einmal mit zwei nacheinander
erzeugten VMs und aufgezeichnetem Befehlsstrom. Diese Prüfungen starten kein TF2.

Der Nutzer hat die bisherige sehr große Karte einmal mit ausschließlich Legacy
Fahrzeugen und Strict Sync neu gespeichert. Beide echten Spielprotokolle
bestätigen die jeweiligen frisch importierten Savenamen und genau diese zwei
aktiven Mods. Das neue Savepaar hat eigene Prüfsummen; alte Cacheeinträge werden
nicht umgedeutet. Für das nächste Paket muss der Freund dieses Paar einmal privat
übernehmen. Danach bleiben die richtige Modliste und der lokale Cache bei
unveränderter Baseline erhalten. Private Saves und Berichte werden nicht publiziert.

## Lokaler Record/Replay-Prüfer

`strict_sync/local_replay.py` zeichnet die tatsächlich gesendeten Aufträge sowie
jede zurückgelieferte Beobachtung des begrenzten Bauprofils auf. Ein zweiter,
frischer Lauf liest den vollständig validierten Befehlsstrom des ersten Laufs
und vergleicht das Ergebnis nach jedem Auftrag und Zeitschritt. Er erzeugt keine
neuen Aufträge aus dem Testrezept. Beide Läufe müssen dasselbe vollständige
Savepaar und Manifest, aber getrennte Sitzungen und native Epochen verwenden.
Abweichungen beenden den Vergleich vor dem nächsten Auftrag. Der Nachweis bleibt
auf die erfassten Objekte beschränkt; er ist weder ein Live-Netzwerktest noch
ein vollständiger Weltvergleich.

15 Unit-Prüfungen und eine vollständige sequentielle Lua-/Datei-IPC-Integration
bestehen. Letztere verwendet zwei nacheinander erzeugte Lua-5.3-VMs mit
nachgebildeten Spiel- und nativen APIs: jeweils 240 Runden, zwölf Aufträge,
unterschiedliche lokale Objekt-IDs und passende Abschlussnachweise. Diese
automatisierten Prüfungen verwenden nachgebildete APIs; reale Nachweise
werden davon getrennt in den versionsbezogenen Abschnitten dokumentiert.

`tools/local_game_replay.py` bereitet jeweils genau einen echten Spielprozess
mit dem vorhandenen Installer vor. Es lädt dessen frisch importierte Savekopie
über das Console-Skript oder fordert mit `--manual-load` den genauen Namen zum
manuellen Laden an. Es prüft Prozessidentität, Skriptargument, Loader-PID,
Epoche, installierte Dateien und Lua-Bereitschaft, bevor es den Prüfer freigibt.
Nach dem Spielende wird die Installation wiederhergestellt. Der Modus
`--probe-load-only` prüft nur den Start und sendet keine Messaufträge. 25 isolierte
Orchestrator-Prüfungen bestehen; alle Prozess-, Installations- und Engineaufrufe
dieser Prüfungen sind nachgebildet.

Mit ausdrücklicher Nutzerfreigabe wurden zwei echte Menüproben durchgeführt:
Steam übergibt `--script` mit absolutem Pfad; das Skript meldet das Hauptmenü
und beendet den eindeutig zugeordneten Prozess über `app.quit()`. Kein Save
wurde dabei geladen, kein Bautest ausgeführt und keine Desktop-Eingabe benutzt.
Der dokumentierte `app.loadGame`-Aufruf liefert auf diesem Spielbuild bei einem
vollständigen Savepfad `false`; auch der zuvor versuchte Basenname öffnete keine
Karte. Ein solches `false` wird jetzt sofort als Ladeablehnung gemeldet. Die oben
beschriebenen echten Bautests wurden vom Nutzer manuell geladen. Die anschließende
Aufzeichnung, Wiedergabe und das Beenden liefen ohne Desktop-Eingaben ab.

Der bisherige Ausgangssave enthält die alten Mod-IDs `mp_lockstep` und `tf2coop`.
Seine `.sav.lua` enthält nur Skriptzustände, keine Modauswahl. Für einen einmal
manuell mit Legacy-Fahrzeugen und Strict Sync neu gespeicherten Ausgangssave
wurde die Strict-Mod mit `enabled=false` vorbereitet. Ein solches neues Savepaar
benötigt neue Prüfsummen; es darf nicht stillschweigend als alter Ausgangssave
in einem veröffentlichten Paket akzeptiert werden.

## Alpha5.8: begrenzte Iteration nativer Entity-Sammlungen

Beide echten Alpha5.7-Berichte enthalten identische Manifeste und zwölf identische
Journaleinträge einschließlich der erfassten Snapshots und Prüfsummen. Gemeinsam
bestätigt sind fünf Aufträge: Pause, Straße, Depot und zwei Haltestellen; dazu
fünf Pausenschritte. Straße: 111.618, Depot: 10.000, Haltestellen: je 98.000.
Beide Firmen haben danach 4.682.382 bei unverändertem Kredit von 5.000.000.
Zeit und Pause bleiben durchgehend bei 13.400.000 Mikrosekunden und `true`.
Es gibt in diesem Lauf keine Freigabe eines fortschreitenden Zeitschritts.

Runde 5 stoppt auf beiden PCs im Lua-Plan für `PROBE_CONNECT`: Die Länge einer
nativen Straßenanschluss-Sammlung ist positiv, direkter Zugriff auf `[1]` ergibt
aber `nil`. Der Host hatte den übergeordneten Netzwerk-Apply bereits gesendet;
intern scheitert dieser noch vor Lua-Apply und dem eigentlichen Enginebefehl.
Es wurde keine Verbindungsstraße ausgeführt und kein weiterer Schritt bestätigt.
Der angehängte Fehler-Snapshot ist der letzte gültige historische Zustand. Die
Roh-Audits sind gekürzt und erfassen diese konkrete Sammlung nicht; ein bestimmter
interner C++-Containertyp ist damit nicht nachgewiesen. Es gibt keinen beobachteten
Unterschied zwischen den erfassten Weltzuständen, aber auch keinen vollständigen
Weltvergleich oder erfolgreichen Fahrzeug-/Fahrtnachweis.

Der alte Leser setzte für die innere Straßen-Inzidenzmenge ein geordnetes Array
voraus. Der lokale Upstream iteriert deren tatsächliche Werte (`lockstep.lua`,
Straßenkarten-Leser). Alpha5.8 verwendet einen eigenen geschützten Mengenleser:
höchstens 16 eindeutige, numerische und existierende Kanten-IDs, vollständige
Iteration einschließlich Ende und unveränderte Länge. Ein fehlender, fehlerhafter,
überlanger oder unvollständiger Wert hält weiterhin an. Alle Endpunkt-, Besitz-,
Altgraph- und Drei-Verbindungen-Prüfungen bleiben erhalten; keine Ersatz-IDs,
Positionssuche oder leere Ersatzlisten. Ein Leseabbruch nach dem Bau veröffentlicht
keine teilweise bestätigten Connector-Bindings.

Dieselbe Indexannahme bestand in der ungeordneten Abfrage `getLineVehicles`.
Vier lokale Upstream-Verwendungen in `mptest.lua` iterieren dort mit `pairs`
über Fahrzeugwerte; unser Snapshot sortiert die logischen Referenzen. Deshalb
nutzt auch diese Abfrage den gemeinsamen Leser, begrenzt auf das eine Fahrzeug
des Testprofils. Ein tatsächlicher Fehler dieser späteren Abfrage wurde noch
nicht beobachtet. Geordnete Callback-, Konstruktions-, Vektor- und Fahrzeugteil-
Arrays behalten ihre bisherige Reihenfolge und strikte Indexprüfung.

Die Standardnachbildung stellt beide Mengen als echte Lua-Userdata mit Länge,
fehlendem Positionszugriff und separater Werteiteration bereit. Diese Form
modelliert die beobachtete Index-Eigenschaft und die belegte API-Nutzung; sie ist
kein Mitschnitt des internen TF2-Containers. Native Uhr und Spielwelt bleiben in
den automatisierten Prüfungen Nachbildungen. Profil `build_v2`, Rezept
`road-depot-service-v3`, native DLLs und die private Ausgangskarte bleiben gleich.
Der echte Verbindungsbau, Fahrzeugkauf und die Linienfahrt müssen weiter auf
beiden Nutzer-PCs bestätigt werden. Es wurde kein Spiel gestartet oder installiert.

Die endgültigen Leser und Testnachbildungen bestehen 340 Bauadapter-Prüfungen
(85 Fälle jeweils unter Lua 5.1 bis 5.4). Enthalten sind unnummerierbare native
Sammlungen vor und nach dem Verbindungsbau, umgekehrte Iteration, echte leere
Linienmitgliedschaft, vollständige Zuweisung, falsche Entity-Werte trotz gültiger
Schlüssel, Duplikate, Längenänderungen und fehlgeschlagene Iteratoren. Ein nicht
endender Iterator wird nach höchstens 17 Aufrufen gestoppt; beschädigte Beobachtungen
werden weder als leere Mengen noch als teilweise gültige Bindings veröffentlicht.
Geordnete Callback-Arrays lehnen dieselbe unnummerierbare Form weiterhin ab.

Eine getrennte Gegenprobe lädt den unveränderten veröffentlichten Alpha5.7-Adapter,
dessen SHA mit dem tatsächlichen Nutzerbericht übereinstimmt: Er reproduziert
den Indexfehler in Runde 5 unter allen vier Lua-Versionen, ohne den Verbindungsbau
auszuführen. Alpha5.8 schafft mit derselben Nachbildung alle neun Bau- und
Zuweisungsbefehle, drei Verbindungen und das tatsächliche Modell-Linienmitglied.
Die Gegenprobe benötigt lokal den alten Adapter; die öffentlichen Regressionen
haben keine Abhängigkeit vom Veröffentlichungs-Checkout oder privaten Berichten.

117 Python-Prüfungen für Programmstart ohne GUI, Staging, Collector-Identität,
Updater, Update-Start, Veröffentlichung, Audit-Export, Bauprofil, Abschlussnachweis
und Bau-Driver bestehen ebenfalls. Der Updater und beide nativen DLLs sind
bytegleich mit der vorherigen Veröffentlichung.

Der getrennte Integrationslauf besteht 30 Profil-, Driver-, Beobachtungs- und
Lua-Datei-IPC-Fälle. Zwei Lua-5.3-Instanzen mit unterschiedlichen lokalen IDs
erreichen darin alle 240 gemeinsamen Grenzen, zwölf tatsächlich ausgeführte
Modellbefehle je Instanz und identische bestandene Abschlussnachweise. Ihre
Standard-API liefert jetzt sowohl Straßeninzidenz als auch Linienmitgliedschaft
als nicht indexierbare Userdata. Ein eigener Fehlerlauf bestätigt außerdem:
Ungültige Inzidenzwerte stoppen bereits die Planung, ohne Connector-Senden,
weitere Zeitfreigabe oder neue Bindings. Das ist eine Prüfung der produktiven
Lua-/Python-Anbindung gegen nachgebildete Spiel-API und Uhr, kein TF2-Spieltest.

## Alpha5.7: ausdrückliche Straßenverbindungen und erhaltener Callback-Abschluss

Der echte Alpha5.6-Versuch bestätigte die Teststraße einschließlich der drei
Kanten, Firmenwerte und ausdrücklich fehlendem `timeBuild` bis Frame 2 auf
beiden Teilnehmern. Die Simulation war dabei gehalten. Depot, Fahrzeug und
Linienfahrt sind weiterhin nicht bestätigt. Der lokale Spiel-Log enthält für
diesen Lauf außerdem `Bau nicht möglich`; die genaue Begründung fehlt.

Der anschließend ausgewertete Alpha5.6-Bericht von Teilnehmer b bestätigt:
Beide Manifeste, alle ersten fünf Journaleinträge und alle 153 Roh-Audit-Zeilen
sind identisch. Nur die erwartete lokale Diagnose-Anfragekennung unterscheidet
sich. Die gemeinsame Straße kostete 71.377; beide Firmen hatten danach 4.928.623
bei Kredit 5.000.000. Teilnehmer b erhielt am Depotauftrag b:1 tatsächlich
`success=false`. Teilnehmer a speicherte keine Callback-Aussage; der allgemeine
Text im Spiel-Log allein ersetzt diese nicht. Die angehängten Endsnapshots sind
historisch. Auch das fehlende `timeBuild` der erfolgreich gebauten Straße ist
jetzt auf beiden PCs unmittelbar beobachtet. Der Lauf startete bereits pausiert;
er beweist keinen erneuten Wechsel aus laufender Simulation in Pause.

Eine weitergehende Prüfung des lokalen Upstreams zeigte eine falsche Annahme:
`docs/re/PROPOSAL_STRUCTURE.md` beschreibt den Skript-Construction-Bau mit leerer
`nodes2snap`-Zuordnung; die interaktive Platzierung übergibt eine Zuordnung.
Unsere frühere Testnachbildung verband räumlich übereinanderliegende Anschlüsse
automatisch. Das war kein belegter Vertrag der Engine. Die genaue Ursache des
alten nativen Depot-Rejects fehlt weiterhin; die falsche Anschlussannahme lässt
sich unabhängig davon korrigieren.

Das neue Rezept `road-depot-service-v3` baut Depot und Haltestellen mit jeweils
20 m Lücke zur eigenen Straße. Runde 5 des neuen Profils `build_v2` baut drei
normale Straßenkanten zwischen den sechs beobachteten vorhandenen Anschluss-IDs.
Die 20 m sind eine bewusst gewählte Verbindungsstrecke und kein behaupteter
Mindestabstand der Engine. Die 320 × 180 m große Baufläche und der Prüfbereich
von ±180 m umfassen die ausgeführten Stock-Geometrien mit Reserve.

Reine Straßen-Callbacks können leere Ergebnis-IDs liefern. Der Adapter erfindet
keine IDs, sondern verlangt an jedem bekannten Knoten genau eine passende neue
Kante und unveränderte bestehende Kanten/Positionen. Erst der vollständige
Nachweis aller drei Verbindungen veröffentlicht die neuen Bindings. Die
vollständigen Connector-Zustände gehen in Graph, Digest und Abschlussprüfung
ein. Ein Fahrzeugkauf vor belegter Verbindung wird abgelehnt. Die Testnachbildung
besitzt jetzt tatsächlich getrennte Knoten, bis der Straßenauftrag ausgeführt
wird. Unterschiedliche lokale IDs bleiben erlaubt.

Der Ablauf umfasst weiterhin 240 Runden, davon 211 Fortschrittsschritte und
29 Pausenrunden, insgesamt 42,2 Sekunden Enginezeit. Zeitschritt-DLL und ABI 3
bleiben unverändert. Normaler UI-Bau, Cursor und UI-Pausetasten bleiben getrennte,
noch nicht angeschlossene Arbeiten.

Der bisherige Callback-Ablauf behandelte einen vorübergehend fehlgeschlagenen
Lesezugriff auf die native Statusdatei als endgültigen Fehler. Vor dem Senden
eines Befehls wird derselbe Zustand bereits erneut gelesen. Ein isolierter
Windows-Versuch mit atomarem Dateiersetzen und echtem Lua-`io.open` reproduziert
kurzzeitige Öffnungsfehler ohne teilweise gelesene Inhalte. Der konkrete
Lesezustand am Abbruchzeitpunkt wurde im Alpha5.6-Bericht noch nicht gespeichert.

Die Korrektur bewahrt die Bauantwort genau einmal auf. Bei vorübergehend
nicht lesbarer Statusdatei bleibt der Befehl unbestätigt. Spätere Updates prüfen
erneut dieselbe Grenze, Zeit und Pause; der Befehl wird nicht erneut gesendet.
Echte Fehler, widersprüchliche Grenzen und der Controller-Abbruch bleiben
endgültig. Unveränderte Wartezustände schreiben die Statusdatei nicht ständig
neu. Der vorhandene Controller-Timeout begrenzt das Warten.

Ein abgelehnter Bau-Callback behält seine ursprüngliche Ablehnung, bevor weitere
Statusprüfungen stattfinden. Die getrennte Callback-Diagnose erfasst außerdem
begrenzt die tatsächlichen Rückgabefelder und `resultProposalData.errorState`,
ohne undokumentierte Methoden aufzurufen oder Werte in einen gültigen Snapshot
zu übernehmen. Fehlende Daten bleiben erkennbar; keine Diagnose darf das
ursprüngliche Ergebnis ersetzen.

Der unveränderte installierte Depot-Lua-Code lässt sich mit den verwendeten
Parametern außerhalb des Spiels auswerten. Im bisherigen Rezept lag sein
Anschluss geometrisch auf dem gemessenen Straßenendpunkt; das war kein
Nachweis eines gemeinsamen Knotens. Das bestätigt weder native Kollisions- und
Geländeprüfungen noch einen erfolgreichen Depotbau. Diese Ursache wird nicht
durch Abschalten von Prüfungen oder Ignorieren von Baufehlern umgangen.

Der bisher bestandene Alpha4.2-Zeitversuch bleibt ein begrenzter positiver
Befund; der aktuelle Bauabbruch ist kein Nachweis einer auseinanderlaufenden Welt.
Das neue Profil ist weiterhin erst außerhalb der echten Spiel-Engine geprüft.

Die endgültigen Lua-Änderungen bestehen 172 generische, 272 Bauadapter- und
76 Roh-Audit-Prüfungen unter Lua 5.1 bis 5.4. Weitere 28 Ausführungen gegen die
installierten Stock-Asset-Funktionen bestehen ohne übersprungene Fälle. Die
breite Python-Prüfung von Datei-Adapter, Export, Staging, Installation, Launcher,
Updater und Veröffentlichung besteht 238 Fälle. Die Prüfungen laufen außerhalb
der Spiel-Engine. Weitere 29 Profil-/Beobachtungs-/Driver-/Datei-Integrationsfälle
bestanden ohne Fehler oder übersprungene Fälle. Darin enthalten sind zwei echte
Lua-Instanzen mit unterschiedlichen lokalen IDs und der vollständige gemeinsame
240-Runden-Ablauf über Datei-IPC, einschließlich aller drei ausdrücklich
gebauten Connectoren und passender Abschlussnachweise. Die native Uhr und die
Spiel-Engine sind dabei Testnachbildungen. Geprüft werden unter anderem vorübergehende und
dauerhafte Lesesperren nach der tatsächlichen Callback-Ausführung, kein
erneutes Senden, keine unberechtigten Schritte sowie eine abgelehnte
Depotantwort mit nativen Test-`errorState`-Daten und zugleich unlesbarem Gate.
Die Engine-Antworten in diesen Prüfungen sind Testdaten; sie ersetzen nicht
die fehlende tatsächliche Ablehnungsbegründung aus dem Spiel.

## Alpha5.6: gemeinsamer Bautest nach Auswertung der Rohdaten

Die beiden geborgenen Alpha5.4-Berichte enthalten dieselben 281 Beobachtungen.
Bei zwei vorhandenen Industriekonstruktionen liefert `CONSTRUCTION.timeBuild`
tatsächlich `nil`. Der Bauzustandsleser bildet diese Abwesenheit jetzt explizit
ab, ohne einen Zeitpunkt zu erfinden. Vorhandene Zeitwerte, echte Null und
fehlende Werte bleiben unterscheidbar und gehen in den vollständigen Digest
ein. Ungültige vorhandene Werte und Getterausnahmen bleiben Fehler.

`TRANSPORT_VEHICLE.stopIndex` darf vor einer Linienzuordnung fehlen; nach der
Zuordnung wird ein gültiger Index verlangt. `VehiclePart.loadConfig=-1` ist als
dokumentierter automatischer Auswahlwert zulässig. Fehler in Zahlenfeldern
nennen Feldpfad und Lua-Typ. Weitere fehlende Pflichtwerte, Firmenabweichungen
und unterschiedliche Feldverfügbarkeit halten den Versuch weiterhin an.

Beim Bauabbruch erfasst der unveränderte unabhängige API-Collector begrenzte
Rohdaten der gebundenen Objekte. Auch eine eindeutige Callback-ID eines neu
erzeugten Objekts bleibt bei anschließender Validierungsablehnung für die
Diagnose verfügbar; sie wird nicht als gültiges Sync-Binding übernommen.
Die Datei `lua_api_audit.json` wird zusammen
mit dem Testbericht exportiert. Ihre nativen Zahlen sind vom strikten
Synchronitätsprotokoll getrennt; sie ist ausdrücklich kein gültiger Snapshot.
Der letzte gültige Snapshot bleibt bei einem Fehler als historisch markiert.
Begrenzte Metadaten des fehlgeschlagenen Leseversuchs werden zusätzlich
aufbewahrt. Ein fehlgeschlagener Collector hebt den ursprünglichen Halt nicht
auf. Die Diagnosemod muss für diesen gemeinsamen Versuch nicht aktiviert sein.

188 Python-Prüfungen bestanden, einschließlich Snapshot-/Digest-Verträgen,
Datei-Adapter, Installationssicherungen, Launcher, Ressourcen und Updater.
Weitere acht Export-/Fehlerintegrationsprüfungen bestanden. Dazu kommen
184 Bauadapter- und 116 generische GameScript-Prüfungen unter Lua 5.1 bis 5.4.
Der vollständige Bauablauf bestand auf zwei getrennten Lua-Testinstanzen alle
240 Runden mit unterschiedlichen lokalen Objekt-IDs, fehlender Bauzeit und
fehlendem Halteindex vor der Zuweisung. Die Spiel-API und die native Uhr sind
dabei ausdrücklich Testnachbildungen. Fehlerfälle prüfen zusätzlich die
getrennte Rohdatei, den konkreten Fehlertext und ausbleibende Schrittfreigaben.

Kein Spiel wurde während dieser Entwicklung gestartet, bedient oder verändert.
Die neue Version muss erst auf den beiden echten TF2-Instanzen geprüft werden.
Dass das Bauzeitfeld auch bei der früher fehlgeschlagenen Teststraße fehlte,
ist weiterhin nicht nachgewiesen. Spätere Depot-, Fahrzeug- und Linienfelder
waren in der Solo-Diagnose nicht als Liveobjekte vorhanden. Ein bestandener
Folgetest würde nur den beobachteten Ablauf bestätigen; freies gleichzeitiges
Bauen, Cursor und die normale Pause-Taste sind noch nicht angeschlossen.

## Alpha5.5: abgeschlossene Diagnoseberichte erkennen

Zwei tatsächliche Alpha5.4-Läufe hatten je 281 vollständige, ungekürzte
Beobachtungen als `report.json.part` geschrieben. Die endgültige Datei fehlte.
Die TF2-Protokolle bestätigen die richtige Save und ausschließlich Legacy
Fahrzeuge plus Diagnosemod. Der bisherige Leser ignorierte temporäre Dateien;
der genaue Fehler des abschließenden Dateischritts war nicht protokolliert.

Der neue Leser hat beide vorhandenen Berichte streng validiert und lokal als
ZIP exportiert. Die Hashes der ursprünglichen Dateien blieben unverändert;
kein neuer Spielstart und keine Änderung der Installation waren nötig.
Er akzeptiert nur vollständige, zweimal identisch gelesene temporäre Daten
mit passender Auftragskennung. Neue Ausgaben schreiben die endgültige Datei
ohne Umbenennung und prüfen ihren Inhalt durch Rücklesen. Unvollständige
Schreibstände werden weiterhin nicht als fertiger Bericht gewertet.

**72 Literal-Lua-Prüfungen** unter Lua 5.1 bis 5.4 und **137 Python-Prüfungen**
bestehen, einschließlich temporärer Berichtübernahme, Teilwrites,
vorübergehender Dateisperren, fehlendem `os.rename`, falschen Kennungen,
Größenlimits, Launcher und Updater. Der Pythonlauf enthält den vollständigen
Dateiaustausch mit dem tatsächlichen GameScript in Lua 5.4 und einer
nachgebildeten Spiel-API. Der neue Lua-Ausgabeweg ist noch nicht in TF2
ausgeführt worden; die Übernahme der vorhandenen echten Berichte ist geprüft.

Die beobachteten Matrixzugriffe passen zum vorhandenen Leser. `timeBuild`
fehlt bei zwei bestehenden Industriekonstruktionen und würde dessen
Zahlenprüfung verletzen. Das ist noch kein Beleg für das Feld der gebauten
Teststraße. Keine Live-Depots, Linien oder eigenen Transportfahrzeuge wurden
beobachtet. Der experimentelle Bauablauf bleibt unverändert.

## Alpha5.4: breitere API-Diagnose auf einem PC

Der tatsächliche Alpha5.3-Bericht endet nach dem Straßenbau in Runde 1 mit
`a:2:invalid finite build value`. Der Bericht enthält keinen konkreten Feldpfad
oder Rohwert für diese Ablehnung. Die vorigen Modellprüfungen haben die
Datenformen dieses TF2-Laufs daher nicht hinreichend abgebildet. Die genaue
Ursache bleibt ungeklärt; an der Zahlenvalidierung wird nicht auf Verdacht
vorbeigearbeitet.

Alpha5.4 ergänzt eine getrennte lesende Diagnosemod und einen lokalen
Vorbereitungs-/Exportweg ohne Mitspieler. Feldzugriffe werden einzeln erfasst,
einschließlich fehlender, werfender und nicht endlicher Werte. Vorhandene
Weltobjekte und reine Konstruktorproben bleiben getrennt; der Bericht ist
ausdrücklich kein gültiger Synchronitäts-Snapshot. Der Spielablauf und die
nativen DLLs des experimentellen Bautests sind unverändert.

Für diese Version bestehen **56 Prüfungen unter echtem Lua 5.1 bis 5.4**
und **146 Python-Prüfungen**. Abgedeckt sind mehrere unabhängig fehlschlagende
native Getter, Zahlen-/Größenlimits, der Erhalt wichtiger Felder bei Kürzung,
deaktivierte Diagnose, verzögerte Wiederholungen nach Schreibsperren,
Installationssicherungen, Konflikte beim Wiederherstellen sowie Launcher und
Updater. Ein vollständiger Test koppelt die tatsächliche Vorbereitung in
temporären Verzeichnissen mit dem GameScript in Lua 5.4 und prüft Bericht,
ZIP-Export und Wiederherstellung. Die Spiel-API stammt dabei weiterhin aus
einer Testnachbildung; kein TF2-Prozess und keine Spieloberfläche werden
gestartet oder bedient.

Die neue Diagnose ist noch nicht in TF2 ausgeführt worden. Ihr nächster
Lauf soll mehrere tatsächliche Datenformen gleichzeitig erfassen. Er baut die
fehlgeschlagene Straße nicht erneut und garantiert daher keine Reproduktion
des Alpha5.3-Fehlers. Details und Grenzen: `API_DIAGNOSE.md`.

## Alpha5.3: fehlende native Felder und Lua-Rückgabewerte

Der tatsächliche Alpha5.2-Bericht stoppt in Runde 1 beim Lesen der Transformation
des gebauten Straßenobjekts: `bad argument #1 to 'type' (value expected)`.
Der Hilfsleser lieferte nach einem fehlgeschlagenen nativen Feldzugriff keine
Rückgabewerte statt eines `nil`. Derselbe Fehler betraf einen späteren
`tonumber`-Aufruf beim Lesen der bestätigten Fahrzeug-/Linien-ID.
Beide Fehler wurden mit der bisherigen Implementierung reproduziert.
Details: `docs/FIELD_LOOKUP_FIX.md`.

Die beiden Feldleser liefern jetzt ausdrücklich genau einen fehlenden Wert.
Unlesbare Pflichtwerte werden weiterhin zurückgewiesen; bei einer fehlenden
Matrixkomponente nennt der Fehler deren Index. Die erweiterten Fixtures bilden
native Transformationen, Parameter und Callback-Ergebnisse mit fehlschlagenden
Zugriffen auf unbekannte Felder nach.

**128 Literal-Lua-Bautests** bestehen über Lua 5.1 bis 5.4. Zusätzlich bestehen
**116 Literal-Lua-Adaptertests** sowie **112 Python-Prüfungen** für Launcher,
Update-Handoff, Updater, lokalen Spielstand und Veröffentlichung. Der vollständige
Datei-Mailboxtest mit zwei getrennten Lua-Peers besteht ebenfalls: zwei Fälle
in 156,583 Sekunden, einschließlich aller 240 gemeinsamen Runden und abschließendem
Bewegungsnachweis mit unterschiedlichen lokalen Objektkennungen.

Die nativen DLLs, gemeinsame Ausgangssave und der Bau-/Pausenablauf bleiben
unverändert. Diese Tests führen Produktions-Lua und Dateiaustausch mit einer
nachgebildeten Spiel-API aus. Die tatsächliche Alpha5.3-Bauausführung auf zwei
TF2-Installationen ist weiterhin offen.

## Alpha5.2: Parameterleser und GitHub-Verteilung

Der tatsächliche Alpha5.1-Lauf findet einen Bauplatz und erstellt das Straßenobjekt.
Anschließend stoppt er bei `a:2:nonplain observed params` vor dem nächsten
Simulationsschritt. Der neue Leser unterstützt native, iterierbare Parametercontainer
und behält beobachtete Zusatzfelder bei. Mit der neuen Userdata-Fixture reproduziert
der bisherige Leser genau diesen Fehler; der korrigierte Leser besteht **104
Lua-Prüfungen**. Der vollständige 240-Runden-Dateitest mit zwei getrennten Lua-Peers
und nachgebildeter Spiel-API besteht ebenfalls (zwei Fälle, 156,7 Sekunden).
Details und Grenzen stehen in `docs/CONSTRUCTION_PARAMS_FIX.md`.

Alpha5.2 ergänzt öffentliche GitHub-Releases und einen beim Launcherstart laufenden
Updater. Private Spielstände bleiben lokal und werden anhand beider Datei-Hashes
aus dem bisherigen Testlauf übernommen. Der nächste tatsächliche TF2-Lauf auf zwei
PCs bleibt erforderlich. Die nativen DLLs und der automatische Ablauf sind unverändert.

## Alpha5.1 nach dem abgebrochenen Baustellentest

Der Screenshot und der lokale Lauf `d02ae96802cb44d990cf1ad9fabbce52` zeigen
`build_site_unavailable` vor dem ersten Bau. Der native Abschlusszähler bleibt
bei Frame 0, Enginezeit 13,4 Sekunden; `fault` und `runtime_fault` sind null.
Auswertung: `results/alpha5-user-site-failure/analysis.json`. Alpha5 protokolliert
keine einzelnen Ablehnungsgründe. Deshalb ist nicht belegt, welcher Filter auf
dieser Karte ausschlug. Die alte Suche war auf 81 zentrale Stellen und zwei
Meter Höhenstreuung über 320 × 320 Metern beschränkt.

Alpha5.1 sucht bis zu 4225 deterministische Kandidaten über die anhand tatsächlicher
Koordinatengültigkeit ermittelten Kartengrenzen. Je Achsrichtung gelten maximal
32768 Meter; eine erreichte Suchgrenze wird protokolliert. Aussichtsreiche Stellen
erhalten 169 Höhenproben. Bevorzugt sind weiterhin zwei Meter Höhenstreuung;
andernfalls wird die beste freie trockene Stelle bis acht Meter ausgewählt.
Der gemeinsam ausgeführte Straßenbau gleicht die eigentliche Testfläche an eine
mittlere Höhe an. Gebäudefilter, Wasserabstand und echte Bau-Erfolgsmeldungen
bleiben erforderlich. Aktuelle Geländeproben gehen in den gemeinsamen Digest ein.

**84 Literal-Lua-Bautests** bestehen über Lua 5.1 bis 5.4, einschließlich ferner
Landfläche, geneigtem Gelände, nassen Vertiefungen zwischen groben Messpunkten,
steilen/überschwemmten Karten, deterministischer Auswahl und beobachteter
Geländeänderungen. **28 Stock-Ressourcenprüfungen** bestätigen die Abdeckung der
tatsächlichen Depot-/Stationsflächen und Straßenbreite durch die neue Baufläche.

Ein Dateiaustauschversuch mit größerem Status lief zunächst in seine dreisekündige
Testfrist. Die alte Lua-Antwort wurde bei jedem erneuten Lesen desselben Befehls
wieder in dieselbe Datei geschrieben und dabei kurz geleert. Alpha5.1 belässt
erfolgreich veröffentlichte Revisionen unverändert; neue oder nicht erfolgreich
geschriebene Revisionen werden weiterhin geschrieben. Der In-flight-Nachweis
muss weiterhin vor der tatsächlichen Befehlsausführung gespeichert sein.
**116 Literal-Lua-Prüfungen** einschließlich stabiler Antwortdatei und Schreibfehler
vor Ausführung bestehen. Der vollständige Dateitest verwendet die auch im
Launcher geltende 30-Sekunden-Frist pro Operation. Ein weiterer echter Dateitest
bestätigt die Fehlerdiagnostik mit 4225 abgelehnten Wasserstellen vor jeder Aktion.

Der anschließende vollständige 240-Runden-Dateitest mit zwei getrennten Lua-
Instanzen besteht, ebenso der neue Fehlerdiagnosetest: zwei Fälle in insgesamt
148 Sekunden. Spiel-API und native Uhr sind weiterhin ausdrücklich Nachbildungen;
Lua-/Python-Produktionscode und Dateiaustausch werden tatsächlich ausgeführt.
Weitere **76 Python-Prüfungen** für Launcher, Vorbereitung, Installation und
Mailbox bestehen. Die neue gemeinsame Geländeangleichung wurde nicht in TF2
ausgeführt. Die tatsächlichen Stock-Flächen sind durch die oben genannten
28 Ressourcenprüfungen abgedeckt.

Die nativen DLLs und der 240-Runden-Ablauf sind unverändert. Der nachstehende
Prüfstand von Alpha5 ist historisch; Geländeangleichung und Bauausführung der
Alpha5.1 müssen weiterhin auf beiden Nutzer-PCs im Spiel bestätigt werden.

## Alpha5-Bautest: neue automatische Bau- und Fahrzeugprüfung

Das neue Profil `build_v1` führt 240 gemeinsame Runden mit automatisch erzeugter
Straße, Depot, zwei Haltestellen, Fahrzeugkauf und Linienzuweisung aus. Der
Abschlussnachweis verlangt die tatsächliche Straßenverbindung, Kaufabbuchung,
Abfahrt und mindestens einen Meter Fahrzeugbewegung. Profil, Ressourcen und
Baustelle sind Teil der geprüften Sitzungs-/Ausgangsdaten. Siehe `BUILD_TEST.md`.

Ein vollständiger Integrationstest mit zwei getrennten Lua-5.3-Instanzen, dem
Produktions-Spielskript, dem neuen Lua-Adapter, dem Python-Koordinator und echtem
Dateiaustausch hat alle 240 Runden bestanden. Die physischen Objekt-IDs der
Teilnehmer unterscheiden sich; die beobachteten Zustände und Abschlussnachweise
stimmen überein. Die Enginezeit steigt von 13,4 auf 55,8 Sekunden. Spiel-API und
native Uhr sind ausdrücklich Testnachbildungen; TF2 wurde nicht gestartet.

Zusätzlich bestehen 56 gezielte Lua-Adapterprüfungen und 20 Prüfungen der
Bauressourcen über Lua 5.1 bis 5.4. Letztere lesen die tatsächlich installierten
Originalkonstruktionen und Fahrzeugmodelle. Die unabhängige Prüfung fand eine
zulässige gemeinsame ID von Konstruktion und Stationsgruppe; der Adapter
berücksichtigt sie nun und ein Regressionstest deckt sie ab.

Alle 112 Literal-Lua-Prüfungen des bisherigen Adapters bestehen ebenfalls.
Zwei vollständige TCP-Bautestfälle bestätigen sowohl den gemeinsamen Erfolg
als auch den beidseitigen Stopp bei identischen Welten ohne tatsächliche
Kaufabbuchung: Der Host bleibt vor der letzten Bestätigung bei Frame 239.
Diese TCP-Fälle verwenden Ersatzengines und blenden die Wartezeit von `fsync`
für ihre Diagnosedateien aus; der oben genannte Lua-Dateitest nutzt echte I/O.

Die erweiterte Suite fand einen realen Rundungsfehler im Übergang der Host-Uhr
vom Laden zur laufenden Sitzung. `started + now - running_started` konnte bei
gleichen aufeinanderfolgenden Uhrwerten minimal unter `started` fallen.
`started + (now - running_started)` beseitigt diesen Rücksprung. Ein
deterministischer TCP-Regressionstest bildet ihn mit einer grob auflösenden Uhr
nach. Alle sieben Modell-Mehrprozessfälle bestehen nach dieser Korrektur;
Ergebnisse: `results/alpha5-model-smoke-20260906-204132/summary.json`.

Die Vorbereitung wurde mit dem tatsächlich installierten Spielbuild und dem
Ausgangssave lesend überprüft; Paketdateien, Profil und lokale Konfiguration
bestehen die Installationsvorprüfung. Es wurde nichts im Spielordner installiert.

Der abschließende Python-Regressionslauf besteht mit **204 Tests**. Der separat
ausgeführte vollständige Lua-Datei-Bautest besteht ebenfalls (321 Sekunden
Laufzeit); zusammen sind das **205 Python-Testfälle**, ergänzt um die oben
genannten Literal-Lua-, Ressourcen- und Mehrprozessprüfungen.

Die nativen DLLs sind bytegleich mit Alpha4.2. Ein echter Alpha5-Zwei-PC-Test
steht aus: Annahme der Bauvorschläge, tatsächliches Einrasten der Straßenknoten
und Abfahrt in der Spielengine lassen sich durch diese Ersatztests nicht belegen.
Der nachfolgende erfolgreiche Nutzertest belegt weiterhin nur das ältere
Zeit-/Pauseprofil, nicht die neue Bauprüfung.

## Erfolgreicher Alpha4.2-Nutzertest: 100 gemeinsame Runden

Der Hostbericht `TF2-Alpha4.2-Bericht-a-20260906-194723.zip` bestätigt den
vollständigen Abschluss des Zeit-/Pauseprofils mit zwei echten Spielinstanzen:
`coordinated_completed=true`, `completion_scope=both_engine_receipts`,
`round=100`, `frame=100`, kein Peer- oder Laufzeitfehler. Der lokale Peerbericht
bestätigt den empfangenen Abschluss ebenfalls. Die Auswertung liegt in
`results/alpha4.2-user-100-rounds/analysis.json` einschließlich SHA-256 des Berichts.

Der Koordinator akzeptiert jede Runde erst nach übereinstimmenden Zeit-/Zustands-
Bestätigungen beider Teilnehmer. Beide erhielten 100 Schrittfreigaben und die
drei Pausebefehle in Runde 0, 40 und 60. Die native Hostdiagnostik bestätigt
80 Fortschrittsrunden à 200000 µs und 20 Pausenrunden ohne Zeitfortschritt:
Enginezeit 13400000 → 29400000 µs, insgesamt exakt 16 simulierte Sekunden.
Die Pause umfasst Runde 40 bis 59, Weiterlauf beginnt in Runde 60.

Der gemeldete Endzustand hat 5000000 Guthaben und 5000000 Kredit; sein Digest
stimmt mit dem Hostabschluss überein. Es wurden keine Bauobjekte verfolgt.
`fault`, `runtime_fault` und `win32_error` sind null. Der abschließende native
HALT bei Anforderung 101 ist der vorgesehene Testabschluss, kein Fehler.
Auch beide Wiederholungszähler sind null: Dieser Lauf zeigt erfolgreichen
Betrieb, aber keine tatsächlich beanspruchte Wiederherstellung einer Dateisperre.

Der Hostbericht genügt für den gemeinsamen Abschlussnachweis dieses Profils.
Die separate ZIP des Freundes fehlt noch und wäre nur für dessen zusätzliche
lokale Abschluss-/Dateidiagnostik nötig. Das Ergebnis ist ein begrenzter Nachweis
kontrollierter Zeitschritte, Pause und übereinstimmender beobachteter Werte über
16 Engine-Sekunden. Bauen, Depot-/Fahrzeugbefehle, laufende Wirtschaft, vollständige
Weltzustände und langfristige Synchronität sind damit noch nicht geprüft.
Alle nachfolgenden Angaben zu ausstehenden Wiederholungstests sind historisch.

## Alpha4.2 nach zwei weiteren echten Nutzertests

Die beiden Alpha4.1-Berichte bestätigen sechs bzw. 38 gemeinsame Runden bis
14600000 bzw. 21000000 Mikrosekunden Enginezeit. Die geprüften Werte stimmen bis
dahin überein. Der anschließende lokale Abbruch lautet in beiden Fällen
`runtime_fault=102`, `win32_error=5`; das `IncompleteReadError` des Hosts ist der
folgende Verbindungsabbruch. Die Berichte identifizieren noch nicht den konkreten
fehlgeschlagenen Dateiaufruf. Details und Aussagegrenzen stehen in `IO_FIX.md`
(Quellordner: `IO_FIX_2026-09-06.md`).

Alpha4.2 behandelt kurze Windows-Zugriffssperren mit begrenzten Wiederholungen,
meldet die ursprüngliche Peer-Fehlerursache und behält den letzten Rundenstand
beim Abbruch. **187 Python-Tests** und **alle sieben Modell-Mehrprozessfälle**
bestehen. Der neue TCP-Fehlerfall prüft, dass beide Ersatzengines anhalten und der
ursprüngliche Fehler den Host und den anderen Teilnehmer erreicht, ohne den
fehlgeschlagenen Schritt als bestätigt darzustellen. Fehlersnapshots sind
ausdrücklich nur als letzter beobachteter Zustand gekennzeichnet.

Die nativen Dateisperrtests verwenden echte Windows-Dateihandles. Die tatsächliche
Spielengine wird dabei nicht aufgerufen. Alle **14 nativen Dateiaustauschfälle**
bestehen, einschließlich 200 Runden mit gleichzeitigem CRT-Leser und exakt
200 ms je Freigabe, Erholung nach tatsächlich beobachteten kurzen Sperren und
Stopp bei dauerhaften Sperren. Die Hook-/ASM-Prüfungen mit 10000 konkurrierenden
Freigaben und die 20 Szenarien des Befehlsadapters bestehen ebenfalls.
Ein voller 100-Runden-Lauf, einschließlich
Pause ab Runde 40, steht in TF2 weiterhin aus. Die folgenden Abschnitte sind
historische Prüfstände; ihre Aussagen über damals ausstehende Nutzertests sind
entsprechend zeitlich einzuordnen.

## Alpha4.1 nach dem ersten echten Nutzertest

Beide Nutzerinstanzen erreichten den gemeinsamen Ausgangsvergleich und den
Weiterlaufbefehl. Beim ersten 100000-Mikrosekunden-Schritt scheiterte die Engine
an ihrer Mindestschrittweite von 0,2 Sekunden. Host-Protokoll, Bericht und
Freund-Screenshot belegen denselben Fehler. Details stehen in
[CRASH_FIX.md](CRASH_FIX.md) im Paket bzw. `CRASH_FIX_2026-09-06.md` im Quellordner.

Der korrigierte Enginepfad verwendet durchgehend 200000 Mikrosekunden, Native
ABI 3 und ein geprüftes `native_step_us`-Statusfeld. **177 Python-Tests**,
**112 Literal-Lua-Ausführungen**, die nativen Regressionstests einschließlich
10000 konkurrierender Freigaben und alle sieben Modell-Mehrprozessfälle bestehen.
Der native Test bildet die tatsächliche Mindestschritt-Vorbedingung nun nach;
100000 Mikrosekunden werden abgewiesen. Ein TCP-Integrationstest prüft zwei
Engine-Ersatzinstanzen mit 200000, 0 und 200000 Mikrosekunden.

Aktuelle Engine-Assertions werden früh im Launcher angezeigt und als einzelne
Fehlerzeilen in den Diagnoseexport aufgenommen. Frühere Spielprotokolle und bloße
Warnungen während des Ladens werden nicht als neuer Assertion-Abbruch gewertet.

Die Korrektur wurde in diesem Entwicklungslauf nicht in TF2 ausgeführt oder
installiert. Der erfolgreiche Wiederholungsversuch mit zwei echten Spielinstanzen
steht weiterhin aus. Die nachfolgenden Abschnitte dokumentieren ältere Prüfstände.

## Nachtrag: verschickbare Alpha4-Testversion

Der neue Launcher ist als `TF2-Coop-Alpha4-Test.zip` gebaut. Er umfasst Host und
Mitspieler, authentifizierte Verbindung vor dem Spielstart, reversible Installation,
einen vom Nutzer betätigten Steam-Startknopf und Diagnoseexport. Die Anleitung
liegt als Markdown und HTML bei; beide Ausgangs-Save-Dateien sind enthalten.

Der erweiterte Python-Testlauf besteht **170 Tests**, einschließlich tatsächlicher
TCP-Lobby-Verbindungen, Installer-/Wiederherstellungsfällen und Launcher-Lebenszyklus.
Die sieben Modellfälle nach den Controlleränderungen bestehen unter
`results/packaged-driver-model/summary.json`.

Die gebaute Windows-EXE hat separat ihre Ressourcen und passive DLL-Prüfung
bestanden und drei eigene, unsichtbare Modellprozesse mit identischem Endzustand
ausgeführt. Die Game- und Lobby-Worker lassen sich aus der EXE aufrufen. Es wurde
dabei kein Fenster geöffnet, kein Spiel gestartet und keine echte Installation
ausgeführt. Die GUI wurde als Quelltext geprüft, nicht visuell am Desktop getestet.
Ein laufender Engineversuch mit zwei Spielern steht weiterhin aus.

Das Alpha4-Test-Profil verwendet 100 Runden mit 300 ms künstlicher Antwortverzögerung
beim Mitspieler. Die unten aufgeführten 14 Runden gehören zum separaten Modelltest.
Der frühere vorbereitete Stand und sein Hash dokumentieren den damaligen Prototyp;
der neue Launcher erzeugt auf jedem PC eine frische Vorbereitung aus dem ZIP.

## Vorheriger Prototypstand

Der kontrollierte Synchronisationsprototyp ist gebaut und separat vorbereitet.
Transport Fever 2 wurde weder gestartet noch bedient. Keine Messdatei wurde in
den Spielordner installiert, keine Startfreigabe erstellt.

| Prüfung | Ergebnis | Aussagegrenze |
|---|---|---|
| Python-Protokoll, Replik, TCP, Datei-Adapter, Vorbereitung und Startschutz | 113 Tests bestanden | Enthält Testersatz für die Engine. |
| Unveränderte Lua-Quelldateien auf Lua 5.1, 5.2, 5.3 und 5.4 | Je 25 Szenarien, insgesamt 100 bestanden | Echte Lua-Ausführung; Spiel-API ist eine Testimplementierung. |
| Koordinator und zwei unabhängige Modellprozesse über TCP | Alle sieben Fälle bestanden | Keine TF2-Simulation; einfache, ausdrücklich erfundene Modellwelt. |
| Native Schrittsteuerung mit ASM-Prologen und echten Threads | Bestanden, einschließlich 10000 geordneter Freigaben | Ersatzfunktionen statt laufender Spielengine. |
| Native Dateikommunikation | Unicode, Bestätigungsphasen, Pause, Duplikate und Fehlerstopps bestanden | Datei-/Threadintegration mit Testuhr. |
| Zurückhalten nativer Befehle und Abschlussfunktionen | 20 Szenarien bestanden | Die normalen UI-Aufrufe sind noch nicht angeschlossen. |
| Produktions-DLL in einem Python-Testprozess | Falscher Host verweigert; passiv geblieben | Kein Test der Hooks in TF2. |
| Audio-Proxy | Alle 20 Exporte entsprechen den Namen und Ordinalwerten des Originals | Exportprüfung, kein Audiotest im Spiel. |

Die sieben TCP-Fälle sind Normalbetrieb, verzögerte/fragmentierte/doppelte
Nachrichten, Verbindungsabbruch, fehlende Eingabeliste, Geldabweichung,
Fahrzeugzuweisungsabweichung und ein anderer Ausgangszustand. Erwartete Fehler
haben weitere Schrittfreigaben verhindert. Der Bericht liegt unter
`results/integrated-model/summary.json`.

Im Modell enden Normalbetrieb und verzögerter Betrieb nach 14 Runden mit demselben
Welt-Hash:
`8690e15335da221665275b9918b082cb558428cd2baadf9d55487e3825065623`.

## Vorbereitete Dateien

`staged/time-probe-20260906` enthält elf Nutzdateien und eine geprüfte Kopie von
`BrazilCorp.sav` samt `.sav.lua`. Beide Save-Hashes, alle Nutzdatei-Hashes und die
aktuellen Python-Quellen stimmen mit dem vorbereiteten Manifest überein:

`db38a85d58ea3f122792313667a6167d8db563e4a8921fa8616237397ca157d7`

`sessions/time-probe-20260906` enthält ausschließlich die vier vorbereiteten
Beschreibungsdateien. Es gibt weder Aktivierungsmarkierung noch native/Lua-
Befehlsdateien. Die Prüfung gegen den tatsächlichen Spielordner verweigert den
Messstart wegen der dort weiterhin vorhandenen Alpha-`alut.dll`, wie vorgesehen.
Auch das bisherige Alpha-Quell-/Save-Manifest stimmt weiterhin mit dem zuvor
gelieferten Alpha3-Paket überein.

## Offener Nachweis

Der nächste Versuch muss die echte Enginezeit, Pause, Firmenwerte und später
explizit erfasste Objekte auf zwei Spielinstanzen unter unterschiedlichen
Wartezeiten vergleichen. Der pausierte Wartungspfad kann weiterhin interne
Weltänderungen auslösen. Der aktuelle Vergleich deckt die gesamte Welt nicht ab.
Eine erfolgreiche Messung wäre zunächst ein begrenzter Befund, kein allgemeiner
Determinismusbeweis.

Normale Bauwerkzeuge, ein exaktes Ergebnis-Mapping für Straßen, vollständige
Zustandsabdeckung und Wiederaufnahme bleiben offen. Der Stand ist deshalb kein
freigegebenes Koop-Update für eine gemeinsame laufende Partie.
