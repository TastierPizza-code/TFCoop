# API-Diagnose in Alpha5.5

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
Livewerte sind weiterhin ungeprüft. Der Bauzustandsleser bleibt unverändert.


Alpha5.5 sammelt auf einem einzelnen PC, welche Daten TF2 über seine Lua-API
tatsächlich zugänglich macht. Anlass ist der echte Alpha5.3-Abbruch
`invalid finite build value` nach dem Straßenbau. Der bisherige Bericht ordnet
diesen Fehler keinem bestimmten Feld zu. Eine Matrix als Ursache anzunehmen
oder einen fehlenden Zahlenwert durch null zu ersetzen wäre deshalb unbegründet.

## Ablauf für den Spieler

Der vollständige Ablauf steht in [ANLEITUNG.md](ANLEITUNG.md). Kurz:

1. TF2 und bisherigen Test schließen, vorhandenen Launcher ab Alpha5.2 neu öffnen
   und das Update auf **Alpha5.5-Diagnose** abwarten.
2. Oben lokale Pfade prüfen und im ersten Reiter **API-Diagnose allein**
   **Diagnose vorbereiten** verwenden. Host-IP, Sitzungscode und Mitspieler
   werden nicht benötigt.
3. TF2 manuell über Steam starten. Die angezeigte `TF2-API-Diagnose-….sav` mit
   ausschließlich **TF2 API-Diagnose (Alpha5.5)** und **Legacy Fahrzeuge** laden.
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

Die Diagnose soll konkrete beobachtete Zugriffspfade liefern, bevor der
Bauzustandsleser erneut geändert wird. Sie führt den fehlgeschlagenen
Straßenbau nicht aus und muss seinen Fehler daher nicht reproduzieren. Sie
kann anhand vorhandener Kartenobjekte und isolierter Proben helfen, falsche
API-Annahmen einzugrenzen; die genaue Ursache bleibt bis zur Auswertung offen.

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
