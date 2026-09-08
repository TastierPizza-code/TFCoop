# Gemeinsame Spielbefehle: Inventar und nächste Etappen

Bestandsaufnahme vom 8. September 2026, Ausgangsstand Alpha5.16. Diese Bestandsaufnahme
verbindet das offizielle TF2-Handbuch, die API-Referenz, gelesene lokale Stock-Skripte,
die vorhandene native Analyse und den tatsächlich ausgelieferten Code. Sie ist
ein Arbeitsplan; aufgeführte API-Funktionen sind keine freigegebenen Multiplayerfunktionen.
Für Modbefehle und unbekannte native Bedienwege bleibt eine ausdrückliche Restkategorie.

Die [Nachweischeckliste](GAMEPLAY_CHECKLIST.md) hakt nur bereits ausgewertete
Zwei-PC-Ergebnisse ab. Auf anschließenden Nutzerwunsch wird zuerst ein umfassenderer
geführter Launcher-Durchlauf mit festen Aufträgen vorbereitet. Die unten beschriebene
normale Ingame-Erfassung folgt nach diesem Zwischenschritt.

## Gemeinsamer Kern und aktueller Nachweis

Gemeinsame Reihenfolge, kleine freigegebene Simulationsschritte, frische Prüfung,
beidseitige Ausführungsergebnisse und kontrollierter Abbruch sind vorhanden.
Der [echte Alpha5.16-Nachweis](ALPHA516_EVIDENCE.md) umfasst begrenzte Depotaufträge
über den Launcher, auch zwei Aufträge derselben Sammelrunde auf verschiedenen
oder demselben Platz. Pause über den Launcher ist ebenfalls im Spiel belegt.

Der automatische Aufbau kauft bereits ein festes Straßenfahrzeug, legt eine
vorgegebene Zweihaltestellenlinie an und weist das Fahrzeug zu. Das belegt dieses
Rezept. Frei ausgelöste Fahrzeug- oder Linienbefehle und normale Bauwerkzeuge
sind darüber noch nicht angeschlossen. Der aktuelle interaktive Validator nimmt
nur Pause, Depot und Testende an. Siehe [Validator](../strict_sync/manual_depot_input.py),
[Aufbaurezept](../strict_sync/build_profile.py) und
[kurzer Bereitschaftsnachweis](../strict_sync/short_build_profile.py).

Der nächste technische Schritt ist die sichere Erfassung eines normalen
Ingame-Auftrags vor seiner lokalen Ausführung. Darauf folgt ein vollständiger,
von den Spielern bedienter Straßenfahrzeugbetrieb. Der vorhandene Kern wird
wiederverwendet; jede zusätzliche Befehlsfamilie benötigt vollständige Eingabedaten,
Objektbindungen und passende Ergebnisprüfungen.

## Was gemeinsam ausgeführt werden muss

| Bereich | Zu erfassende Bedienhandlungen | Zusätzliche Synchronisationsgrenze |
|---|---|---|
| Straßen und Gleise | Bauen, Ersetzen/Aufwerten, Abreißen; Verzweigungen, Brücken/Tunnel, Oberleitung, Tramgleise, Busspuren, Einbahnrichtungen. | Tatsächliche Geometrie und Anschlüsse; Ersetzung kann alte Kanten/Knoten ungültig machen. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:streetstracks) |
| Signale und Verkehrsführung | Signale/Wegpunkte setzen oder entfernen, Signalausrichtung, Ampeln und Straßenbesitz ändern. | Ein Objekt kann sowohl Verkehrsregeln als auch Linienführung beeinflussen. Der Schalter in einer Datenansicht ist eine Weltänderung. [Signale](https://wiki.transportfever2.com/doku.php?id=gamemanual:railwaysignals), [Bedienung der Datenebenen](https://wiki.transportfever2.com/doku.php?id=gamemanual:statisticsdatalayers) |
| Stationen und Depots | Haltestellen, Bahnhöfe, Häfen, Flughäfen und Depots platzieren/entfernen; Module, Bahnsteige, Zugänge und Erweiterungen ändern. | Neben Baukosten und Konstruktion auch Stationsgruppen, Terminals und betroffene Linien/Verbindungen prüfen. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:stationsdepots) |
| Gelände und Dekoration | Gelände formen/glätten, Boden bemalen, Bäume und andere Assets platzieren/entfernen. | Auch kostenloses Bemalen verändert die gespeicherte gemeinsame Karte. Pinselbewegungen ergeben konkrete gemeinsame Änderungen, keine vom lokalen Bildtempo abhängige Wiederholung. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:landscaping) |
| Fahrzeuge erstellen/ändern | Kaufen, Klonen, Ersetzen; Teile/Wagen hinzufügen, entfernen, umordnen oder drehen; Konfiguration und Farben ändern. | Vollständige Fahrzeugzusammenstellung, Kosten, echte neue Identitäten und Erhalt geänderter/bestehender Zustände. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:linesvehicles) |
| Fahrzeuge einsetzen | Linie zuweisen/wechseln, anhalten/starten, wenden, zum Depot schicken, dort verkaufen lassen oder direkt verkaufen; Wartungsziel ändern. | Fahrzeug, Linie, Zielhalt und Infrastruktur gemeinsam prüfen. Mehrfachauswahl wird als konkrete Menge identifizierter Fahrzeuge übertragen. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:linesvehicles) |
| Linien bearbeiten | Anlegen/löschen, benennen/färben; einzelne Halte einfügen, entfernen, verschieben oder leeren; Wegpunkte, Fahrspuren sowie Haupt-/Ausweichterminals wählen. | Bearbeitung einer konkreten Linienfassung und Haltevorkommens; eine ältere Gesamtfassung darf keine fremde Änderung löschen. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:linesvehicles) |
| Linienbetrieb konfigurieren | Warte-/Abfahrtsregeln, Ladeart und Warenfilter mit Be-/Entladegrenzen. | Regeln gehören zum jeweiligen Halt und müssen bei Umordnung erhalten bleiben. Fahrzeugfracht und wartende Güter sind zusätzliche Ergebnisbeobachtungen. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:linesvehicles) |
| Firma und gemeinsame Objektangaben | Kredit aufnehmen/tilgen, Firma oder Objekte umbenennen, Hauptsitz bauen/versetzen; gemeinsame Farben/Logos dort, wo die Bedienung sie anbietet. | Ein gemeinsames Konto und ein gemeinsamer Eigentümer. Logo-/Farbpfad je Objekttyp prüfen; der gesonderte Logopfad ist bislang ein lokaler statischer Befund. [Firmenhandbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:companyandfinances) |
| Simulation und Kalender | Pause/Fortsetzen, erlaubtes Spieltempo, Kalendergeschwindigkeit; Datumseingriffe nur bei unterstütztem Sandboxbetrieb. | Bewegung und Kalender sind getrennte Einstellungen. Kalenderänderungen betreffen unter anderem Verfügbarkeit, Alter und Produktionsausgleich. [Handbuch](https://wiki.transportfever2.com/doku.php?id=gamemanual:simulationoverview) |

Alle Verkehrsträger gehören zum langfristigen Umfang: Bus/Lkw/Tram, Zug, Schiff
und Flugzeug. Ein erfolgreicher Straßenfahrzeugfall belegt deren besondere
Depot-, Fahrzeug-, Terminal- und Wegbedingungen nicht automatisch.

Klonen und das Verschieben von Wagen zwischen Zügen sind in der Bedienung
zusammengesetzte Vorgänge. Es gibt in der geprüften API-Liste keinen eigenen
Klon-Befehl. Automatischer Fahrzeugersatz durch zusätzliche Mods, selbst definierte
Fahrpläne oder weitere Mod-Schaltflächen sind gesonderte Kompatibilitätsarbeit.
API-Fähigkeiten wie manuelle Abfahrt und erzwungene Abfahrt werden mit erfasst;
ihre Existenz beweist keinen entsprechenden normalen Vanilla-Knopf.

## API-Anbindung und offene Datenfelder

Die offizielle [Befehlsreferenz](https://wiki.transportfever2.com/api/modules/api.cmd.html)
enthält unter anderem diese passenden Familien:

| Familie | Dokumentierte Funktionen unter `api.cmd.make` |
|---|---|
| Bauvorschläge | `buildProposal` |
| Fahrzeuge | `buyVehicle`, `replaceVehicle`, `sellVehicle`, `sendToDepot`, `reverseVehicle` |
| Fahrzeugbetrieb | `setLine`, `setUserStopped`, `setVehicleTargetMaintenanceState`, `setVehicleManualDeparture`, `setVehicleShouldDepart` |
| Linien | `createLine`, `updateLine`, `deleteLine` |
| Namen/Farben/Geld | `setName`, `setColor`, `bookJournalEntry` |
| Zeit | `setGameSpeed`, `setCalendarSpeed`, `setDate` |
| Erweiterungen/Editor | `sendScriptEvent` sowie weitere Stadt-, Industrie-, Gelände- und Tierbefehle; einzeln freizugeben |

Die [Typenreferenz](https://wiki.transportfever2.com/api/modules/api.type.html)
beschreibt vollständige Fahrzeugteile/-gruppen und geordnete Linienhalte mit
Stationsgruppe, Station, Terminal, Alternativen, Ladeart, Wartezeiten und Wegpunkten.
Sie erklärt außerdem, dass Bauvorschläge beim Umbau alte Objekte durch neue
ersetzen und abhängige Linien, Personen und Fracht anpassen können. Diese
Folgewirkungen gehören in die Prüfung.

Konkrete noch offene Integrationspunkte aus dem Codeaudit:

- Der allgemeine [Lua-Adapter](../mod/tf2_strict_probe_1/res/scripts/tf2_strict_probe/engine.lua)
  verwirft derzeit komplexe Halte mit Alternativterminals/Wegpunkten und schließt
  Warenregeln, Frachtinhalte sowie weitere Weltzustände aus seiner Beobachtung aus.
  Sein Vorhandensein ersetzt keine Freigabe im ausgelieferten interaktiven Modus.
- Das genaue Lua-Eigentümerfeld der Warenfilter ist in der generierten
  Typendokumentation unklar. Es wird aus einer echten beobachteten Struktur
  bestimmt, bevor das Feld übertragen oder beschrieben wird.
- Ein initialer Zielhalt bei der Linienzuweisung ist Teil des gemeinsamen
  Auftrags. Die lokale Auswahlheuristik darf ihn nicht auf jedem PC neu bestimmen.
- Das Firmenlogo hat einen gesonderten statisch beschriebenen nativen Pfad.
  Die ältere `COMMAND_MAP.md` ist keine verbindliche Enum-Tabelle: Nummern
  widersprechen teilweise der Apply-Analyse und die vorgeschlagenen Hookzeilen
  entsprechen nicht sämtlich ausgelieferten Hooks. Eine Anzahl gelisteter
  Befehle ist kein Abdeckungsnachweis.
- Stock-Skripte verwenden auch `game.interface`, beispielsweise Kalender-,
  Kreditgrenzen-, Eigentums- und Konstruktionsänderungen. Die Stock-Mods für
  Sandbox und kostenlose Bauten ändern Konfiguration direkt. Das umgeht einen
  reinen Wrapper um `api.cmd.make`; der weitere native Weg ist je Funktion zu
  verfolgen. Daraus folgt noch kein Nachweis, dass jede Funktion die native
  Warteschlange umgeht.

## Sitzung, Anwesenheit und lokale Bedienung

**Gemeinsame Sitzung:** Speichern und Wiederaufnehmen brauchen eine bestätigte
gemeinsame Grenze und eine passende gemeinsame Ausgangsbasis. Laden, Wechsel
der Karte, Verbindungsverlust und Wiederbeitritt verändern die Sitzung selbst.
Ein lokaler Save-Aufruf wird daher nicht blind mit dem Dateipfad des anderen
Spielers wiederholt. Spielversion, relevante Ressourcen, Mods samt Einstellungen,
Schwierigkeit und Simulationsoptionen müssen vor einer allgemeinen Freigabe
beim Start gemeinsam geprüft werden. Das bestehende Manifest bindet ausgewählte
Dateien, Save-Hashes, Bindungen und Konfigurationssemantik; es prüft noch nicht
vollständig alle aktiven Ressourcen/Einstellungen oder die tatsächlich geladene Welt.
Änderungen daran während eines Laufs brauchen einen eigenen vereinbarten Ablauf.
[Spiel-/Ladeoptionen](https://wiki.transportfever2.com/doku.php?id=gamemanual:freegame),
[Speichern/Laden in der Oberfläche](https://wiki.transportfever2.com/doku.php?id=gamemanual:userinterface).

**Sandbox, Editor und Mods:** Städte/Industrien erzeugen, entfernen oder
konfigurieren, Karte neu generieren, Geld-/Kostenregeln ändern sowie beliebige
Skriptereignisse sind Welt- oder Sitzungsänderungen. Sie bleiben bis zu einem
eigenen Vertrag ausgeschlossen. Die Karte neu zu erzeugen wird kein gewöhnlicher
Baubefehl im laufenden Koop-Spiel. [Editorumfang](https://wiki.transportfever2.com/doku.php?id=gamemanual:mapeditor).

**Gemeinsame Anwesenheitsanzeige:** Cursorposition, Name/Farbe, aktuelle Vorschau
und hervorgehobene Auswahl können separat mit kurzer Gültigkeit übertragen werden.
Ein veralteter Cursor darf die Simulation nicht anhalten. Eine Vorschau reserviert
noch keinen Bauplatz; ihre endgültige Bestätigung erzeugt erst den Weltauftrag.

**Lokal:** Kamera, Zoom, Mitfahransicht, geöffnete Fenster, Suche, Sortierung,
Statistikansicht, reine Sichtbarkeitsfilter, Grafik, Ton und Tastenbelegung.
Die UI-Darstellung ist von einer darin ausgelösten Änderung getrennt: Das
Ampel-Layer öffnen bleibt lokal, eine Ampel darin ändern wird synchronisiert.
Ein Menü öffnen ist ebenfalls von einer dadurch ausgelösten Pause zu unterscheiden.
[Oberfläche](https://wiki.transportfever2.com/doku.php?id=gamemanual:userinterface),
[Einstellungen](https://wiki.transportfever2.com/doku.php?id=gamemanual:settings).
Die Videoaufnahme des Kamerawerkzeugs kann die Simulationsgeschwindigkeit
verändern. Diese Funktion ist deshalb von bloßer Kamerabewegung zu trennen und
braucht dieselbe gemeinsame Zeitsteuerung. [Kamerawerkzeug](https://wiki.transportfever2.com/doku.php?id=gamemanual:cameratool).

**Automatische Simulation:** Stadtwachstum, Industrieentwicklung, Verkehr,
Frachtbewegung und laufende Kosten sind Wirkungen der gemeinsam gesteuerten
Simulation. Sie werden nicht zusätzlich als künstliche Spielereingaben dupliziert.
Gleiche Eingaben allein beweisen ihre langfristige Übereinstimmung nicht;
die Beobachtung muss für die jeweils freigegebenen Mechaniken erweitert werden.
Die native Pause lässt Wartungs-/Skriptaufrufe absichtlich weiterlaufen. Auch
diese Pfade müssen zum Vertrag passen; Pause bedeutet keine beliebig sichere
direkte Skriptmutation. [Bestehender Grenzvertrag](../native/STEP_BOUNDARY.md).

## Gemeinsame Regeln für Ressourcenkonflikte

Diese Regeln sind der weitere Entwurf, nicht bereits allgemein implementiert:

1. **Gemeinsame Reihenfolge und aktuelle Voraussetzungen.** Auch weit entfernte
   Bauten und Fahrzeuge teilen sich Geld. Vor jedem Auftrag erneut Zustand und
   Kosten prüfen. Bau-/Betriebskosten entstehen einmal durch die Engine;
   Kreditwünsche werden nicht mit den daraus folgenden automatischen Buchungen
   doppelt repliziert.
2. **Versionierte logische Identität.** Neue Fahrzeuge/Linien erhalten Bindungen
   aus echten Rückgaben. Nach Ersatz/Abbruch dürfen spätere Wünsche nicht auf
   eine alte, inzwischen wiederverwendete lokale Objektnummer zeigen.
3. **Kleine Bearbeitungsabsichten erhalten.** Bei A–B–C–B identifiziert der
   Stationsname nicht, welches B gemeint ist. Halt-Vorkommen und Linienfassung
   gehören zum Auftrag. Eine veraltete Änderung wird gezielt neu angewandt oder
   sichtbar abgelehnt; eine alte vollständige Liste überschreibt keine fremde
   Bearbeitung still.
4. **Abhängige Objekte zusammen prüfen.** Verkaufen gegen Zuweisen betrifft ein
   Fahrzeug und seine Linie. Stationsumbau gegen Linienbearbeitung betrifft
   zusätzlich Stationsgruppe, Terminal und Netzwerk. Beim Entfernen müssen
   abhängige Wünsche eine klare Ablehnung oder eine nachgewiesene Neuzuordnung
   erhalten.
5. **Kauf- und Folgeaufträge verbinden.** Erst das tatsächlich bestätigte neue
   Fahrzeug beziehungsweise die neue Linie verwenden. UI-Rückmeldungen können
   weitere Befehle auslösen; diese gehören ebenfalls in die Reihenfolge.
   Ein geschlossener Dialog darf keinen ungültigen Callback hinterlassen.
6. **Mehrfachaktionen ausdrücklich behandeln.** Die Zielmenge bei „alle
   ausgewählten Fahrzeuge“ wird einmal festgelegt. Für Teilfehler muss das
   Ergebnis sichtbar sein; bestehende Technik bietet keinen Welt-Rollback.
   Unerwartete Fehler halten an. Mehrere bestätigte Einzelbefehle werden nicht
   als atomar rückgängig machbare Transaktion bezeichnet.
7. **Unterstützung vor der lokalen Änderung entscheiden.** Der neue normale
   UI-Pfad muss unbekannte Weltmutationen sperren beziehungsweise die Sitzung
   kontrolliert anhalten. Ein unerkannter Klick darf nicht lokal ausführen und
   erst später durch einen Weltvergleich auffallen. Das ist eine noch zu bauende
   Integrationsanforderung, keine heutige Zusage für alle TF2-Werkzeuge.
   Werkzeuge mit ungeklärtem Rückgabe-/Objektbesitzvertrag bleiben vorab gesperrt;
   ein erfundener erfolgreicher Callback ist keine zulässige Sperrmethode.

## Reihenfolge der nächsten Umsetzung

1. **Ein normaler Ingame-Bauweg.** Mit einem begrenzten Straßenbau beginnen:
   echte Eingabe und vollständigen Vorschlag abfangen, Native-Objekte/Callback
   sicher halten, auf dem richtigen Thread nach gemeinsamer Freigabe anwenden
   und Ergebnisse prüfen. Dieselbe Bedienung muss auch bei Pause funktionieren.
   Die [native Warteschlange](../native/DEFERRED_COMMAND_ADAPTER.md) ist dafür
   Vorarbeit; sie ist noch nicht im ausgelieferten Spielpfad verdrahtet.
2. **Vollständiger Straßenfahrzeugbetrieb.** Geeignetes Fahrzeug kaufen, Linie
   anlegen, Halte einzeln ergänzen/ändern, Fahrzeug zuweisen und ausfahren lassen;
   anschließend Stop/Start, Depotfahrt und Verkauf. Beide Spieler bedienen die
   normale Oberfläche. Bestandene automatische Rezepte werden als Vorarbeit
   verwendet, nicht als Nachweis dieser Eingaben ausgegeben.
3. **Bearbeitung und Konkurrenz.** Zwei Spieler an derselben Linie, Kauf bei
   knappem Guthaben, Verkauf gegen Zuweisung, Haltentfernung gegen Linienänderung,
   doppelte Klicks und Menüschließen während ausstehendem Auftrag. Ein gemeinsamer
   Adaptervertrag prüft diese Muster für mehrere Befehle vor dem nächsten
   Nutzertest; keine neue Version pro einzeln geratenem Lua-Feld.
4. **Weitere Konfiguration und Infrastruktur.** Warenregeln, Alternativterminals,
   Wegpunkte, Ersatz/Klonen/Zugbildung, Module, Gleise/Signale und weitere
   Verkehrsträger schrittweise mit vollständigen Daten- und Ergebnisverträgen.
   Firmenänderungen und gewöhnliche Abbruchfälle gehören ebenfalls vor eine Beta.
5. **Dauerhaftes gemeinsames Spiel.** Speichern/Fortsetzen, Verbindungsverlust
   und Wiederaufnahme, größere beobachtete Weltabdeckung und längere echte Läufe;
   Cursor/Blaupausen als separater Anzeigepfad. Steam-Einladungen bleiben eigene
   Verbindungsarbeit.

Neue Nutzertests behalten den kurzen Vorlauf und prüfen einen zusammenhängenden
neuen Ablauf. Die akzeptierten Tempo- und Eingabereferenzen aus Alpha5.12/5.15
sowie die beiden Alpha5.16-Depotläufe bleiben erhalten. Diese Bestandsaufnahme
änderte ursprünglich keine Laufzeitdatei, Spielinstallation oder Releaseversion
und startete keinen Test auf dem Benutzer-PC. Der anschließend beauftragte
[geführte Testbegleiter](GUIDED_TEST.md) wird getrennt davon umgesetzt und geprüft.
