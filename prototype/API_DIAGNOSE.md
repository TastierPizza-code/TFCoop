# API-Diagnose und Baufehlerberichte in Alpha5.7

**Die zwei vorhandenen Alpha5.4-Soloberichte wurden geborgen und ausgewertet.
Eine erneute Solo-Diagnose ist für den nächsten Schritt nicht nötig.** Jetzt
folgt der gemeinsame automatische 240-Runden-Bautest auf beiden PCs. Die
Schritt-für-Schritt-Anleitung steht in [ANLEITUNG.md](ANLEITUNG.md).

## Alpha5.7: Rohdiagnose beim tatsächlichen Bauabbruch

Der Strict-Mod enthält eine eigene byteidentische Kopie des begrenzten
Rohdaten-Collectors. Ein strikter Bauabbruch löst damit automatisch eine
unabhängige Erfassung der aktuell gebundenen Testobjekte aus. Die normale
Solo-Diagnosemod bleibt dafür deaktiviert.

Der Rohbericht wird separat als `lua_api_audit.json` in der Sitzung geschrieben
und automatisch in die private **Testbericht-ZIP** aufgenommen. Seine Größe ist
auf 98304 Bytes und höchstens 16 Bindings begrenzt. `lua_status.json` enthält dazu einen Dateihinweis,
den Status des vollständigen Schreibens und Rücklesens sowie begrenzte
Fehlversuchsmetadaten. Zusätzlich bleiben tatsächliche Callback-Rückgabefelder
einschließlich verfügbarer Proposal-Fehler in einer eigenen, auf 16 KiB begrenzten
Diagnose erhalten. Undokumentierte Methoden werden dabei nicht aufgerufen.
Der letzte gültige Snapshot bleibt davon getrennt und ist
als historischer Zustand markiert.

Die Rohdiagnose enthält ausdrücklich `valid_snapshot=false`. Auch rohe
Fließkommazahlen bleiben in dieser separaten Datei, außerhalb des auf Ganzzahlen
und dezimale Zeichenketten begrenzten Synchronitätsprotokolls. Die Daten helfen
bei der Fehlersuche; sie sind weder ein Ersatzsnapshot noch ein Beleg für
übereinstimmende Spielwelten. Falls auch die Ausgabe scheitert, bleiben ihr
Fehlerstatus und der eigentliche Baufehler unterscheidbar.

Deshalb nach dem nächsten gemeinsamen Abbruch oder nach 240 Runden die
**normalen Testbericht-ZIPs von beiden PCs** exportieren. Dafür nicht noch
einmal **Diagnose vorbereiten** verwenden.

## Beobachtete Verfügbarkeit und Grenzen

Die geborgenen Daten zeigen `timeBuild=nil` bei zwei vorhandenen
Industriekonstruktionen. Die anschließenden Alpha5.6-Berichte beider PCs
bestätigen dieselbe Abwesenheit unmittelbar an der erfolgreich gebauten
Teststraße. Welches Feld den allgemeinen Zahlenfehler früherer Versionen
auslöste, lässt sich aus deren unvollständigen Berichten nicht rückwirkend beweisen.

Seit Alpha5.6 wird ein fehlendes `CONSTRUCTION.timeBuild` ausdrücklich als
`{available=false}` im gehashten Zustand gespeichert. Ein vorhandener Wert bleibt samt
Verfügbarkeit enthalten. Eine künstliche Null würde den Unterschied verdecken
und wird nicht eingesetzt. `stopIndex` darf vor einer Linienzuordnung fehlen,
ist nach Zuordnung aber verpflichtend. `loadConfig` akzeptiert außerdem den
dokumentierten automatischen Wert `-1`; siehe die
[offizielle Beschreibung von VehiclePart.loadConfig](https://wiki.transportfever2.com/api/modules/api.type.html).
Ungültige verpflichtende Zahlenwerte
stoppen den Test weiterhin; Fehlermeldungen nennen den konkreten Feldpfad.

Der weitere Ablauf mit Depot, Haltestellen, Fahrzeug und Linie
muss im tatsächlichen gemeinsamen Test bestätigt werden.

## Alpha5.5: vorhandene Berichte übernehmen

Zwei reale Alpha5.4-Läufe hinterließen jeweils einen vollständigen Bericht mit
281 Einträgen als `report.json.part`, während `report.json` fehlte. Die
Mod war aktiv und die Datenerfassung erfolgreich. Der genaue Fehler des
anschließenden Dateischritts wurde von Alpha5.4 nicht aufgezeichnet.

Der Leser prüft jetzt auch eine temporäre Datei: zwei identische begrenzte
Lesevorgänge, vollständiges gültiges JSON und die passende Auftragskennung
sind erforderlich. Angefangene Dateien werden erneut gelesen; falsche
Kennungen, ungültige Daten und Größenüberschreitungen bleiben Fehler. Die
Übernahme verändert weder die Quelldatei noch Spielstand oder Installation.
Neue Ausgaben schreiben nach dem vollständigen temporären Bericht die
Zieldatei direkt und prüfen ihre Bytes durch Rücklesen. Die Ausgabe hängt
nicht mehr von `os.rename` ab. Begrenzte Statusmeldungen im TF2-Protokoll
machen den erreichten Schritt und Schreibfehler sichtbar.

Die vorhandenen Daten zeigen numerische flache Matrizen mit 16 Einträgen.
`timeBuild` ist bei den beiden untersuchten Industriekonstruktionen nicht
vorhanden. Dies ist ein konkreter Unterschied zu den bisherigen
Modellannahmen, aber keine Beobachtung der später gebauten Teststraße.
Depots, Linien und eigene Transportfahrzeuge fehlen in dieser Karte; ihre
Livewerte waren damit weiterhin ungeprüft. In Alpha5.5 blieb der Bauzustandsleser
unverändert; die oben beschriebenen Anpassungen folgten mit Alpha5.6.


Der Solo-Diagnosemodus sammelt auf einem einzelnen PC, welche Daten TF2 über seine
Lua-API tatsächlich zugänglich macht. Anlass war der echte Alpha5.3-Abbruch
`invalid finite build value` nach dem Straßenbau. Der bisherige Bericht ordnet
diesen Fehler keinem bestimmten Feld zu. Eine Matrix als Ursache anzunehmen
oder einen fehlenden Zahlenwert durch null zu ersetzen wäre deshalb unbegründet.

## Optionaler Solo-Modus für gezielte spätere Untersuchungen

**Diesen Modus jetzt nicht erneut ausführen.** Die vorhandenen Berichte sind
ausgewertet; der nächste Versuch ist der gemeinsame Bautest. Falls später
ausdrücklich eine weitere Solo-Messung benötigt wird, bleibt der Modus im
zweiten Reiter **API-Diagnose allein** verfügbar:

1. TF2 und bisherigen Test schließen, vorhandenen Launcher ab Alpha5.2 neu öffnen
   und das Update auf **Alpha5.7-Bautest** abwarten; vorherige Installation wiederherstellen.
2. Oben lokale Pfade prüfen und im zweiten Reiter **API-Diagnose allein**
   **Diagnose vorbereiten** verwenden. Host-IP, Sitzungscode und Mitspieler
   werden nicht benötigt.
3. TF2 manuell über Steam starten. Die angezeigte `TF2-API-Diagnose-….sav` mit
   ausschließlich **TF2 API-Diagnose (Alpha5.7)** und **Legacy Fahrzeuge** laden.
   Die Modliste unter **Spiel laden → OPTIONEN AUSWÄHLEN → Mods** ändern.
4. Etwa zehn Sekunden warten, ohne selbst zu bauen oder die Geschwindigkeit
   umzuschalten. **Diagnosebericht als ZIP …** exportieren; ein eigener Bericht
   genügt. Danach TF2 schließen und die bisherige Installation wiederherstellen.

## Was gemessen wird

Die Diagnose behandelt zwei Arten von Beobachtungen getrennt:

- **Liveobjekte:** Vorhandene Objekte der geladenen Karte und ihre tatsächlich
  lesbaren Komponenten, Feldtypen und Werte. Ein nicht vorhandenes Fahrzeug
  liefert keinen erfolgreichen Fahrzeugtest. Fehlende Objekte oder nicht
  verfügbare Felder bleiben als fehlende Abdeckung beziehungsweise Lesefehler
  sichtbar.
- **Konstruktorproben:** Eigenständig erzeugte Lua/API-Werte, deren Zugriffe
  geprüft werden, ohne daraus Bau- oder andere Spielbefehle auszuführen. Ein
  erfolgreich erzeugter Matrixwert belegt nur diesen Konstruktor und diesen
  Zugriff; der entsprechende Live-Getter kann anders reagieren.

Die Diagnosemod gibt keine Bau-, Kauf-, Linien-, Pause- oder Weiterlaufbefehle
aus. Die Vorbereitung entfernt die aktive strikte native Teststeuerung vor
diesem Lauf; es wird kein gemeinsamer Messcontroller gestartet. TF2 läuft mit
seiner normalen Simulation, die während des Lesens weitergehen kann. Die
frische Kopie schützt den gemeinsamen Ausgangsstand vor einer versehentlichen
Fortsetzung des bisherigen Versuchs.

## Interpretation und Grenzen

Ein vollständiger Bericht heißt, dass die Erfassung abgeschlossen wurde.
Er bedeutet nicht, dass jede API-Funktion vorhanden war, alle Werte lesbar waren
oder alle Objektarten auf der Karte existierten. Fehlende Abdeckung darf nicht
als bestandene Prüfung gewertet werden.

Die Solo-Diagnose liefert konkrete beobachtete Zugriffspfade. Sie führt den fehlgeschlagenen
Straßenbau nicht aus und muss seinen Fehler daher nicht reproduzieren. Sie
kann anhand vorhandener Kartenobjekte und isolierter Proben helfen, falsche
API-Annahmen einzugrenzen. Die Auswertung begründet die oben beschriebenen
Anpassungen, ersetzt aber keine Beobachtung der tatsächlich gebauten Testobjekte.

Die Diagnose prüft weder deterministische Simulation noch gemeinsame Zeit,
Pause, Geld, Fahrzeugfahrt, konkurrierende Eingaben oder freie Bauwerkzeuge.
Der frühere begrenzte Zeit-/Pausetest und die automatisierten Modelltests
werden durch diesen Bericht nicht zu einem vollständigen Multiplayer-Nachweis.
Der gemeinsame Bautest ist weiterhin experimentell.

## Private Dateien

Die öffentliche Programm-ZIP enthält keinen Ausgangsspielstand. Der passende
private Ausgangsstand bleibt lokal verwahrt; die Diagnose erstellt daraus eine
eigene Save-Kopie. Der Updater lädt weder Spielstände noch Berichte hoch.

Ein Diagnosebericht kann lokale Pfade, Komponentenwerte und Objektdaten aus
der Karte enthalten. Er ist für die private Auswertung bestimmt und gehört
nicht in ein öffentliches GitHub-Issue, Quellcode-Commit oder Release. Die
Wiederherstellung nach Spielschluss erhält die Save-Kopie und exportierte
Berichte.
