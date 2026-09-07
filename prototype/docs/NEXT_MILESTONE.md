# Nächste Etappe: frei ausgelöste Eingaben

Status: identifiziert und als nächste Entwicklungsetappe festgelegt; noch nicht
implementiert oder im Spiel getestet. Die [akzeptierte Alpha5.12-Referenz](ACCEPTED_BASELINE.md)
bleibt unverändert. Es wird kein weiteres Tempoexperiment vorgeschaltet.

## Fehlendes Verhalten

Im jetzigen `stream_v1` sind alle 600 Schritte und beide Pausebefehle bereits beim
Start festgelegt. Die Spieler können den Auslösezeitpunkt nicht bestimmen.
Die vorhandene strikte Lua-Anbindung kann `SET_PAUSED` bereits mit echter
Engine-Rückmeldung an einer gehaltenen Grenze anwenden. Es fehlt der dynamische
Weg von einem echten Klick beider Spieler bis zur gemeinsamen Entscheidung.

Der nächste Meilenstein führt daher echte, beliebig ausgelöste Wünsche ein:
zunächst Pause/Fortsetzen über eigene Teststeuerungen im Launcher, danach einen
manuell ausgelösten, bekannten Straßen- oder Depotauftrag. Die Teststeuerungen
werden ausdrücklich als solche bezeichnet. Sie beweisen noch nicht, dass die
normalen TF2-Werkzeuge ihre ursprüngliche lokale Ausführung sicher zurückhalten.

## Geplanter gemeinsamer Eingabeweg

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
ergänzt. Tempooptimierungen haben bis dahin keine eigene Entwicklungspriorität.
