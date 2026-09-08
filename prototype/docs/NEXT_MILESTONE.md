# Nächste Etappe: frei ausgelöste Eingaben

## Aktueller Nachweis: geführter Straßenfahrzeugbetrieb abgeschlossen

Der tatsächliche [Alpha5.19-Lauf](ALPHA519_EVIDENCE.md) bestätigt alle 26 festen
Host-/Freund-Aufträge für Straßenfahrzeug und Linie. 241 bytegleiche Journalzeilen,
passende Kosten und tatsächliche Fahrt/Depotankunft tragen die neuen Häkchen in
der [Checkliste](GAMEPLAY_CHECKLIST.md). Die älteren Referenzen bleiben erhalten.

Als nächstes zusammenhängendes, noch offenes Kapitel bietet sich der feste
Schienenbetrieb an: Gleis und Bahnhof, Depot, Signal, Lok/Wagen, Linie, Abfahrt
und Rückkehr. Er benötigt eigene tatsächliche Geometrie-, Signal-, Zugbildungs-
und Fahrtnachweise. Die normale freie Ingame-Bedienung bleibt ein anschließender
Integrationsschritt. Die Auswertung selbst verändert keinen Laufzeitcode,
startet keinen weiteren Spieltest und veröffentlicht kein neues Updatepaket.
Die folgenden Abschnitte bewahren die bisherige Planung und ihre Prioritätswechsel.

## Neuer Auftrag: geführter gemeinsamer Funktionstest

Der Nutzer möchte vor der normalen Ingame-Erfassung mehrere Befehlsfamilien
in einem zusammenhängenden festen Test prüfen. Ein vereinfachter Testbegleiter
zeigt jeweils nur den aktuellen Host-/Freund-Auftrag. Fortschritt entsteht aus
beidseitig verglichenen Ergebnissen, nicht aus einem manuellen Weiter-Häkchen.
Die [Nachweischeckliste](GAMEPLAY_CHECKLIST.md) trennt bestehende Laufnachweise,
vorbereitete neue Schritte und offene Befehlsfamilien. Dieser Auftrag ersetzt
die unmittelbare Priorität der normalen Straßenbau-Erfassung im folgenden Plan.
Die akzeptierten Referenzen und ihre auswählbaren alten Abläufe bleiben erhalten.

## Aktueller Arbeitsplan nach der Befehlsbestandsaufnahme

Die [Befehlsübersicht](COMMAND_COVERAGE_PLAN.md) erfasst Bauen/Abbruch,
Fahrzeuge und deren Konfiguration, einzelne Linienhalte und Betriebsregeln,
Firma, Zeit, Sitzung sowie Mod-/Skriptgrenzen. Sie trennt gemeinsame Änderungen
von individuellen Ansichten und vom separaten Cursor-/Vorschaukanal.

Der Synchronisationskern wird wiederverwendet. Nächster technischer Schritt
ist ein vollständiger normaler Ingame-Straßenbauweg mit zurückgehaltener lokaler
Ausführung und echten Rückmeldungen. Danach folgt ein zusammenhängender
Straßenfahrzeugbetrieb: kaufen, Linie anlegen und Halte bearbeiten, zuweisen,
stoppen/starten, zurückschicken und verkaufen. Objektversionen, gemeinsame
Kosten, tatsächliche neue Objektbindungen und abhängige Folgeaufträge gehören
zum Adaptervertrag. Linienänderungen dürfen keine ältere Gesamtfassung über
eine neuere fremde Bearbeitung schreiben. Diese Etappen sind geplant, noch
nicht implementiert; die Bestandsaufnahme veröffentlicht keine neue Version.

## Erhaltener Depotversuch: Alpha5.16

`manual_depot_v1` ist als eigener Launcher-Depotversuch implementiert: vier
Testplätze, Vierteldrehungen, zehnrundiger Aufbau und ein frischer gemeinsamer
Bauvorschlag vor jedem Auftrag. Die Anwendung prüft tatsächliche Rückmeldungen,
neue Depotbindungen und Baukosten. Belegungsablehnungen verändern die Welt nicht;
unerwartete Anwendungsfehler halten an. Der normale Spielbau bleibt offen.

Das private Verbindungsprofil wird beim Vorbereiten gespeichert. Die Lobby
vereinbart für jeden Versuch eine frische Sitzung vor dem Start der Spielworker.
Die nachfolgenden Abschnitte bewahren Vorgaben und Entwurfsgrenzen; die genannten
Alpha5.13-/Alpha5.14-Planungsstände sind historische Grundlagen.

Der tatsächliche Zwei-PC-Lauf vom 8. September bestätigt vier Depots mit
passenden Objekten und Kosten während Fahrt/Pause sowie eine kostenfreie
Belegungsablehnung. Normale Fahrt erreichte 0,947x/0,951x, der aktive Durchschnitt
mit Bauprüfungen 0,904x/0,905x. Die 97 Weltjournalzeilen sind identisch.
Der belegte Platz wurde im ersten Lauf in zwei aufeinanderfolgenden Sammelrunden
angefragt. Der zweite Lauf bestätigt nun zusätzlich zwei erfolgreiche Bauten
auf verschiedenen Plätzen und einen Bau mit kostenfreier Ablehnung am gleichen
Platz, jeweils aus Wünschen beider Spieler in derselben Sammelrunde. Seine
49 Weltjournalzeilen stimmen überein; normale Fahrt blieb bei etwa 0,948x.
[Auswertung](ALPHA516_EVIDENCE.md). Der akzeptierte Alpha5.15-Lauf bleibt die
Referenz. Kein neuer langer Vorlauf oder Tempoexperiment folgt allein aus
dieser Auswertung.

Die nächste funktionale Etappe ist ein begrenztes normales TF2-Bauwerkzeug:
seinen Auftrag vor der lokalen Änderung erfassen, bis zur gemeinsamen Freigabe
zurückhalten und tatsächliche Ergebnisse beidseitig prüfen. Dieser Pfad ist
noch nicht implementiert oder im Spiel bestätigt. Die nun nachgewiesene
Reihenfolge, frische Prüfung jedes Folgeauftrags und Ergebnisbestätigung müssen
auch bei diesem neuen Eingabeweg erhalten bleiben. Neue Tests behalten den
kurzen Aufbau.

## Für die nächste Version: Testverbindung merken

Nutzervorgabe vom 8. September 2026: Bis zur Beta sollen Host-IPv4 und ein
fester gemeinsamer Testzugang automatisch vorausgefüllt bleiben. Nach einmaliger
Einrichtung soll der Freund diese Daten nicht für jeden Versuch erneut kopieren
müssen. Start, Update und Wiederherstellen behalten das lokale Testprofil;
automatisch erkannte lokale Adressen dürfen die gespeicherte Host-Adresse nicht
überschreiben. Eine bewusste Änderung des Profils bleibt möglich.

Der feste Zugang ist eine private Kopplungskennung. Die jeweilige Versuchssitzung
erhält weiterhin eine eigene Identität, die beide Teilnehmer über die authentisierte
Verbindung übernehmen. Native Epochen, verbrauchte Sitzungen, neue Eingabequeues
und Verbindungsabbruch bleiben getrennt abgesichert. Bis Alpha5.15 leitete
`connection_identity` die Netzkennung direkt aus dem sichtbaren Code ab;
Alpha5.16 vereinbart stattdessen eine frische gemeinsame Sitzung.
Host-Adresse und Zugangscode werden nicht ins öffentliche Repository oder
Updatepaket geschrieben. Diese Änderung ist in Alpha5.16 umgesetzt,
in Alpha5.15 noch nicht enthalten. Die endgültige Verbindungsoberfläche
kann nach der Testphase gestaltet werden.

## Funktionsstand

Status: Der tatsächliche Alpha5.15-Lauf vom 8. September ist ausgewertet und
vom Nutzer auch im Fahrgefühl akzeptiert. 133 Weltjournalzeilen sind identisch;
kurze Vorbereitung, 182 native Fortschrittsschritte, sieben gegenseitige
Pause-/Fortsetzen-Wechsel, eine 47,375-Sekunden-Pause und gemeinsamer Abschluss
passen zusammen. Die aktive Fahrt erreicht ungefähr 0,94x. Der Aufbau dauert
12,500 Sekunden. Dieses Tempo soll bei den nächsten Funktionen erhalten bleiben;
weitere Tempoexperimente sind nicht vorgesehen. Gesicherter Stand und Grenzen:
[akzeptierte Alpha5.15-Eingabereferenz](ACCEPTED_INPUT_BASELINE.md).

Die [akzeptierte Alpha5.12-Referenz](ACCEPTED_BASELINE.md) mit ihrem längeren
automatischen Test bleibt ebenfalls unverändert als `stream_v1` verfügbar.
Der begrenzte manuelle Depotauftrag ist inzwischen in Alpha5.16 im Spiel
bestätigt; das private Testprofil ist implementiert. Die normale TF2-Eingabe
bleibt offen. Die folgenden Planungsabschnitte dokumentieren den Weg bis zu
diesem Stand und dessen weiterhin gültige Grenzen.

## Kurzer Vorlauf für neue Tests

Nutzervorgabe vom 8. September 2026: Neue Testmodi sollen nur die notwendigen
automatischen Voraussetzungen herstellen und danach zügig die neue Bedienprobe
freigeben. Bereits akzeptierte lange Bau-, Pause- und Fahrtabschnitte werden
nicht vor jedem neuen Versuch vollständig wiederholt. Die vorhandenen
auswählbaren Tests behalten ihren bisherigen vollständigen Ablauf.

Der abgeschlossene Alpha5.13-Testmodus wird dafür nicht geändert. Alpha5.14
erhält den eigenen kurzen Vorlauf `short_scene_v1` und die eindeutige
Modus-/Protokollidentität `paced_live_v1`. Beide Teilnehmer müssen denselben Ablauf verwenden.
Die gemeinsame Ausgangswelt, tatsächlich benötigte Objekte, Verbindungen,
Linienzuweisung und echte Befehlsbestätigungen bleiben Voraussetzungen.
Eine Bewegungsprüfung wird nur aufgenommen, wenn die neue Probe sie benötigt,
und endet nach ausreichender echter Beobachtung statt einer langen festen
Wiederholung. Kann die notwendige Bereitschaft innerhalb der begrenzten
Vorbereitung nicht bestätigt werden, hält der Versuch mit Diagnose an.

Die aktuelle Zahl `BUILD_ROUNDS = 240` darf nicht einfach global verkleinert
werden: Der vollständige `BuildProof`, die automatischen Pausebefehle bei
80/100, die Startgrenze der Folgeprotokolle und ihre Befehlssequenzen sind daran
gebunden. Der kurze Vorlauf benötigt eigene Abschlussbedingungen und meldet
nur seine tatsächlich geprüfte Bereitschaft. Er wird nicht als bestandener
vollständiger Bau-/Dauertest bezeichnet. Diese Änderung wird zusammen mit dem
neuen Alpha5.14-Test umgesetzt; in Alpha5.13 ist sie nicht enthalten.

## Fehlendes Verhalten

Im jetzigen `stream_v1` sind alle 600 Schritte und beide Pausebefehle bereits beim
Start festgelegt. Die Spieler können den Auslösezeitpunkt nicht bestimmen.
Die vorhandene strikte Lua-Anbindung kann `SET_PAUSED` bereits mit echter
Engine-Rückmeldung an einer gehaltenen Grenze anwenden. Alpha5.13 ergänzt den
dynamischen Weg vom echten Klick bis zur gemeinsamen Entscheidung als eigenen
Modus `live_input_v1`.

Der nächste Meilenstein führt daher echte, beliebig ausgelöste Wünsche ein:
zunächst Pause/Fortsetzen über eigene Teststeuerungen im Launcher, danach einen
manuell ausgelösten, bekannten Straßen- oder Depotauftrag. Die Teststeuerungen
werden ausdrücklich als solche bezeichnet. Sie beweisen noch nicht, dass die
normalen TF2-Werkzeuge ihre ursprüngliche lokale Ausführung sicher zurückhalten.

## Gemeinsamer Eingabeweg in Alpha5.13

1. Ein echter Klick erzeugt einen begrenzten semantischen Auftrag mit Sitzung,
   Spieler, fortlaufender Nummer, eindeutiger Identität und explizitem Zielzustand.
   Pause ist ein Wunsch nach `true` oder `false`, kein doppelt wirkender Toggle.
2. Der Peer sammelt Wünsche lokal und übermittelt eine abgeschlossene Eingabeliste
   mit der nächsten kleinen Schrittbestätigung beziehungsweise einer Eingaberunde.
   Eine Eingabe darf nicht rückwirkend in eine bereits freigegebene Serie gelangen.
3. Der Host wartet auf beide Antworten und hält vor der nächsten Freigabe an.
   Er liest frische Zustände, legt Grenze und gemeinsame Reihenfolge fest und
   übermittelt denselben Plan an beide Teilnehmer.
4. Beide wenden freigegebene Befehle genau einmal an derselben Grenze an. Erst
   echte Callback-Ergebnisse und passende beobachtete Zustände erlauben weitere
   Fortschrittsschritte. Eine Empfangsbestätigung ist kein Ausführungserfolg.
5. In Pause läuft die Eingabe- und Verbindungsverarbeitung ohne Fortschrittsschritt
   weiter. Fortsetzen darf weder einen zukünftigen Tick voraussetzen noch durch
   einen normalen Phasentimeout an der beabsichtigten Pause scheitern.

Der neue Modus erhält eigene Nachrichtenschemata und eine ausdrückliche gemeinsame
Fähigkeit. Der fest vereinbarte Plan von `stream_v1` und seine Felder werden nicht
still umgedeutet. Die bisherige native Schrittweite und der akzeptierte Takt bleiben
die Ausgangsbasis.

## Gleichzeitigkeit und Rückmeldungen

Gleiche Pausewünsche dürfen keinen Toggle-Effekt erzeugen. Bei gegensätzlichen
Wünschen in derselben Sammelrunde erhält Pause Vorrang; beide sehen dieselbe
Entscheidung. Ein anschließender neuer Fortsetzenwunsch bleibt möglich.
Veraltete oder doppelte Aufträge werden nicht unbemerkt erneut ausgeführt.

Bei späteren Bauaufträgen legt der Host eine gemeinsame Reihenfolge fest. Der
nächste Auftrag muss gegen den Zustand nach dem vorherigen Commit geplant werden.
Damit wird ein durch den ersten Bau ungültig gewordener Auftrag vor weiteren
Änderungen auf beiden PCs gleich abgelehnt. Eine unerwartete Ablehnung erst während
der tatsächlichen Anwendung hält den Versuch an; sie wird nicht als sichere
Konfliktauflösung ausgegeben.

Die Anzeige unterscheidet ausstehend, gemeinsam übernommen und abgelehnt. Nach
dem dynamischen Pausepfad folgt als begrenzter Bauversuch ein bestimmter Depottyp
mit gewähltem Standort und Orientierung. Der neue semantische Auftrag braucht
eigene Objektverfolgung und echte Ergebnisbindungen. Das bisherige `PROBE_DEPOT`
ist nur einmal und am vorbestimmten Teststandort erlaubt; es wird nicht als
allgemeiner Platzierungsbefehl ausgegeben. Auch der rundenabhängige `BuildProof`
muss auf den tatsächlichen Befehlsstrom angepasst werden; der alte feste Test
darf nicht unverändert als Beweis für freie Eingaben dienen.

## Abnahme dieser Etappe

- Beide Spieler lösen Wünsche zu selbst gewählten Zeitpunkten aus; kein Skript
  erzeugt die Eingaben automatisch an festen Runden.
- Host pausiert, Mitspieler setzt später fort, anschließend umgekehrt. Auch eine
  längere beabsichtigte Pause bleibt bedienbar, während die Spielzeit unverändert ist.
- Gleichzeitige gleiche und gegensätzliche Wünsche sowie schnelle wiederholte Klicks
  ergeben auf beiden PCs dieselbe Entscheidung ohne doppelte Ausführung.
- Ein manuell ausgelöster bekannter Bauauftrag wird während laufender Simulation
  und während Pause am gemeinsamen Zeitpunkt angewandt; Objekte, Kosten und
  beobachtete Zustände passen anschließend zusammen.
- Verzögerungen, wiederholte Nachrichten und Verbindungsabbruch erzeugen weder
  eine lokale Vorabausführung noch ein stilles Fortsetzen nach Fehlern.
- Der Alpha5.12-Referenzmodus bleibt separat ausführbar. Vorabmodelle und echte
  Zwei-PC-Läufe werden weiterhin getrennt dokumentiert.

## Danach: normale Werkzeuge anschließen

Die normale TF2-UI muss Befehle vor der lokalen Weltänderung abgeben. Der frühere
optimistische Abgleich bereits ausgeführter Aktionen erfüllt diese Bedingung nicht.
`DeferredCommandQueue` enthält Vorarbeiten für Besitz und verzögerte Ausführung,
ist aber noch nicht mit einem verifizierten Producer-Thread-Pump, vollständiger
Erfassung und echten Ergebnisbeobachtern im ausgelieferten Lauf verbunden.
Siehe [native Integration](../native/DEFERRED_COMMAND_ADAPTER.md).

Nach dem dynamischen Eingabeweg folgt daher ein begrenzter normaler Straßenbaupfad
mit echter Vorschau und zurückgehaltener Ausführung. Weitere Werkzeuge, konkurrierende
Umbauten sowie Cursor und Blaupausen werden auf diesem gemeinsamen Befehlsweg
ergänzt. Nach der jetzt gewünschten gezielten Korrektur des Eingabewegs bleibt
dies der nächste funktionale Meilenstein. Die akzeptierte Referenz wird dabei
nicht ersetzt oder nachträglich umbewertet.
