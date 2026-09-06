# Prüfstand vom 6. September 2026

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
