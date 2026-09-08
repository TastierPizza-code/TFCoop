# TFCoop: Funktionscheckliste und Nachweise

Stand: 8. September 2026. Ein Häkchen bedeutet einen ausgewerteten tatsächlichen
TF2-Lauf auf zwei PCs im angegebenen Umfang. Vorbereiteter Code, Modelltests und
die Bestätigung eines einzelnen Launchers erhalten kein solches Häkchen.

Die ausführliche [Befehlsübersicht](COMMAND_COVERAGE_PLAN.md) bleibt der Gesamtumfang.
Für den nächsten Versuch werden feste Aufträge im Testbegleiter verwendet.
Die normale freie Bedienung der Spielwerkzeuge folgt danach.

## Bereits im Zwei-PC-Spiel nachgewiesen

- [x] Gemeinsame Simulationsschritte und passende beobachtete Firmen-/Szenenwerte
  im automatischen Referenzlauf: [Alpha5.12](ACCEPTED_BASELINE.md).
- [x] Akzeptiertes Tempo mit kurzem Aufbau und Launcher-Eingaben: etwa 0,94x
  im [Alpha5.15-Lauf](ACCEPTED_INPUT_BASELINE.md). Renderflüssigkeit bleibt eine
  separate Nutzerbeobachtung; kein pauschaler Nachweis für beliebige Karten.
- [x] Host und Freund können über den Launcher gegenseitig pausieren/fortsetzen.
- [x] Eine gemeinsame Pause über 47 Sekunden bleibt in der beobachteten Szene stabil.
- [x] Automatischer fester Straßenaufbau mit Depot, zwei Haltestellen und Verbindungen.
- [x] Automatischer Kauf eines bestimmten Straßenfahrzeugs mit tatsächlicher Abbuchung.
- [x] Automatisches Anlegen einer festen Zweihaltestellenlinie und Fahrzeugzuweisung.
- [x] Abfahrt und Fahrt dieses Fahrzeugs im festen automatischen Szenario.
- [x] Beide Spieler können feste Depotaufträge über den Launcher erteilen.
- [x] Depotbau während gemeinsamer Fahrt und während gemeinsamer Pause.
- [x] Tatsächliche Depotobjekte und Baukosten auf beiden PCs stimmen überein.
- [x] Zwei Depotaufträge in derselben Sammelrunde an verschiedenen Testplätzen bauen beide.
- [x] Zwei Depotaufträge in derselben Sammelrunde am gleichen Testplatz ergeben
  einen Bau und eine kostenfreie Ablehnung. Die zweite Prüfung sieht das erste Ergebnis.

Die letzten Depotpunkte sind durch die beiden getrennten
[Alpha5.16-Auswertungen](ALPHA516_EVIDENCE.md) belegt. Sie gelten für die begrenzten
Testplätze und Vierteldrehungen, nicht für beliebige Bauwerke oder native Mausklicks.

## Geführter Straßenfahrzeug-/Linienablauf: auf zwei PCs nachgewiesen

Der tatsächliche [Alpha5.19-Lauf](ALPHA519_EVIDENCE.md) bestätigt alle 26 festen
Host-/Freund-Aufträge mit 241 bytegleichen Journalzeilen. Der Umfang bleibt das
vorgegebene Straßenfahrzeug und die vorbereiteten Halte, bedient über den Launcher.

- [x] Frei zeitlich ausgelöster Kauf und Verwaltung eines zusätzlichen Testfahrzeugs.
- [x] Neue Linie über getrennte Aufträge anlegen und einzelne Halte ergänzen.
- [x] Haltereihenfolge ändern, einen Halt entfernen und erneut hinzufügen.
- [x] Liniennamen, Linienfarbe und Halte-/Warteregeln bearbeiten.
- [x] Fahrzeug benennen, zuweisen und seine tatsächliche Abfahrt/Fahrt beobachten.
- [x] Fahrzeug anhalten/starten, wenden und Wartungsziel ändern.
- [x] Fahrzeug zum Depot schicken, tatsächliche Ankunft erkennen und verkaufen.
- [x] Nicht mehr verwendete Testlinie löschen.
- [x] Diese Aktionen durch wechselnde Aufträge von Host und Freund auslösen.
- [x] Kosten, Bindungen, Betriebszustände und Ergebnisse über den gesamten Ablauf vergleichen.
- [x] Eine zu frühe Depotankunftsprüfung ohne Kosten oder Fortschritt zurückstellen;
  denselben Schritt nach beobachteter Ankunft erfolgreich erneut prüfen.
- [ ] Veraltete/doppelte oder rollenfalsche neue Aufträge im tatsächlichen Spiel ablehnen.
- [ ] Gleichzeitige konkurrierende Fahrzeug-/Linienaufträge im tatsächlichen Spiel prüfen.

Ein fehlendes Merkmal wird als offen oder nicht unterstützt ausgewiesen. Ein
grüner Abschluss eines Teilablaufs ist kein Häkchen für die gesamte Befehlsfamilie.
Bereits bestandene lange Referenztests müssen dafür nicht jedes Mal wiederholt werden.

## Weitere Befehlsfamilien: offen

- [ ] Gleise, Bahnweichen, Oberleitungen und feste Schienenverbindungen.
- [ ] Signale und Wegpunkte mit tatsächlichem Einfluss auf einen Zug.
- [ ] Zugdepot, Lok/Wagen kaufen und Zug auf einer funktionierenden Strecke einsetzen.
- [ ] Zugbildung, Klonen und Fahrzeugersatz mit vollständiger Teilekonfiguration.
- [ ] Tram, Schiff und Flugzeug samt eigenen Depot-/Stationsbedingungen.
- [ ] Warenfilter, Ladegrenzen, alternative Terminals und komplexe Linienführung.
- [ ] Bahnhofs-/Stationsmodule umbauen und abhängige Linien/Fahrzeuge prüfen.
- [ ] Infrastruktur aufwerten und abreißen; abhängige Aufträge behandeln.
- [ ] Gelände formen/bemalen, Bäume und Dekoration gemeinsam ändern.
- [ ] Firmennamen, Kreditaufnahme/-tilgung und Hauptsitz ändern.
- [ ] Konflikte an beliebigen Fahrzeugen/Linien/Stationen und bei gemeinsam knappem Geld.
- [ ] Mehrfachauswahl mit klaren Ergebnissen bei teilweise fehlgeschlagenen Aktionen.
- [ ] Gemeinsamer Speicherstand, reguläres Fortsetzen und Verbindungswiederaufnahme.
- [ ] Größere Weltabdeckung einschließlich autonomer Stadt-/Industrie-/Frachtentwicklung.
- [ ] Weitere Mods und deren direkte Skript-/Konfigurationsänderungen.

## Normale Spieloberfläche und Anwesenheit: eigener nächster Schritt

- [ ] Normalen Straßenbau vor lokaler Ausführung erfassen und gemeinsam freigeben.
- [ ] Weitere normale Bau-, Fahrzeug-, Linien- und Firmenwerkzeuge anschließen.
- [ ] Native Pause-/Geschwindigkeitstasten sowie menübedingte Zeitänderungen anschließen.
- [ ] Farbige Cursor mit Namen und gut sichtbare Anzeige bei weitem Zoom.
- [ ] Gemeinsame Bauvorschauen/Blaupausen mit begrenzter Gültigkeit.
- [ ] Steam-Einladungen und komfortabler Beitritt.

Kamera, Zoom und reine Fenster-/Filterbedienung bleiben individuell. Cursor und
Vorschau sind Anwesenheitsdaten; sie buchen kein Geld und reservieren keinen Bauplatz.
