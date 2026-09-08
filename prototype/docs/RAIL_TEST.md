# Alpha5.20 · T2: gemeinsamer Bahn- und Zugtest

**T2 ist ein eigener geführter Test im Launcher. Ein tatsächlicher gemeinsamer
TF2-Durchlauf dieses Bahnkapitels ist noch nicht nachgewiesen.** Die technischen
Prüfungen mit ausdrücklich nachgebildeten Spielobjekten ersetzen diesen Lauf
nicht. T1 bleibt getrennt verfügbar: Seine 26 festen Straßenfahrzeug- und
Linienaufträge sind durch den [Alpha5.19-Zwei-PC-Lauf](ALPHA519_EVIDENCE.md) belegt.

## So startet ihr

Beide öffnen dieselbe aktuelle Launcher-Version und wählen **T2 · Schiene**.
T2 ist beim Start vorausgewählt; **T1 · Straße** bleibt als eigener Reiter erhalten.
Jeder behält seine Rolle Host oder Freund. Bei Hamachi verwenden beide dieselbe
Hamachi-IPv4 des Hosts. Die gespeicherte Adresse steht sichtbar im Hauptfenster;
Adresse und privater Testschlüssel lassen sich unter den Einstellungen ändern.
Sie gehören nicht ins öffentliche Updatepaket.

Eure gemeinsame saubere große Ausgangskarte wird weiterverwendet. Der Freund
braucht für diesen Test keine neue Basisdatei, wenn dieselbe private Basis bereits
auf seinem PC verfügbar ist. Nur bei fehlender Basis übernimmt er unter den
Einstellungen denselben Ausgangsspielstand. **Test vorbereiten** erstellt auf
jedem PC eine frische Kopie. Die Kopien dürfen verschiedene Namen haben; vor dem
Spielstart werden die zugrunde liegenden Dateien gemeinsam geprüft.

Nach **Verbinden** starten beide TF2 erst bei angezeigter Startfreigabe und laden
jeweils genau ihren frisch genannten Spielstand. Der Launcher wartet auf beide
geladenen Spiele. Es folgt die bestehende kurze Straßen-Vorbereitung mit zehn
Runden. Sie prüft Verbindung, Ausgangszustand, gemeinsame Änderungen und Zeit.
Die Bahn wird erst danach über die sichtbaren T2-Aufträge gebaut. Eine bereits
angelegte Katalogzeile oder nur ein geladenes Spiel gibt keinen Auftrag frei.

## Ein geführter Durchlauf mit mehreren Kapiteln

Der [T2-Katalog](https://github.com/TastierPizza-code/TFCoop/blob/v0.5.20/prototype/strict_sync/rail_catalog.py) enthält 37 feste Aufträge sowie die Reihenfolge,
Rollen und Prüfsätze. Der Launcher übernimmt Kapitel und Schrittzahl daraus.
Jeder Spieler sieht dieselbe aktuelle Aufgabe; nur die vorgesehene Rolle kann sie
auslösen. Ein Auftrag bleibt offen, bis die tatsächlichen Ergebnisse beider Spiele
verglichen und gemeinsam bestätigt sind.

1. **Gleisnetz, Signale und Wegpunkt:** Zwei feste Personenbahnhöfe und ein Bahndepot bauen; Gleise mit Abzweig verbinden; Signale und einen Wegpunkt setzen. Geometrie, Anschlüsse, beobachtete Objekte, Zuordnung und Firmenänderungen werden geprüft.
2. **Lok, Wagen und Linie:** Einen fest ausgewählten Zug kaufen, eine leere Bahnlinie anlegen, beide Bahnhöfe einzeln hinzufügen, Zugname und Wartung setzen und den Zug zuweisen. Die tatsächlichen Teile, ihre Reihenfolge, Halte, Terminals und Linienmitgliedschaft werden verglichen.
3. **Zugbetrieb und Depotfahrt:** Gemeinsam fortsetzen, tatsächliche Bewegung prüfen, den Zug anhalten und starten, wenden und zum Depot zurückschicken. Die Ankunft wird als eigener beobachteter Zustand geprüft.
4. **Umbau, Duplizieren und Verkauf:** Den zurückgekehrten Zug gemeinsam pausiert umkonfigurieren; aus der beobachteten Zusammenstellung einen zweiten Zug kaufen; beide verkaufen. Dieser Kauf prüft die übernommene Konfiguration und den tatsächlichen Betrag, nicht den normalen Ingame-Klonknopf.
5. **Abbau und Abschluss:** Die fahrzeuglose Linie, den Wegpunkt, Signale, Verbindungsgleise, Depot und Bahnhöfe in abhängiger Reihenfolge entfernen. Nach dem letzten bestätigten Auftrag folgt automatisch der gemeinsame Abschluss.

Bei einer Fahrt- oder Ankunftsprüfung darf **noch nicht bereit** erscheinen.
Dann weiterlaufen lassen und denselben Auftrag erneut auslösen. Die reine
Beobachtung kauft oder baut nichts und überspringt keinen fehlenden Nachweis.
Ein unerwarteter Fehler hält den Test an; er wird nicht als bestandener Schritt
gezählt. Schon bestätigte Schritte bleiben im Bericht erhalten.

## Was ein Signalnachweis bedeutet

Ein vorhandenes Signal mit passendem Modell, Richtung und Gleiszuordnung ist ein
Nachweis seiner Platzierung. Ein verbundenes Gleisnetz und tatsächliche Zugfahrt
belegen noch keine Rot-/Grünanzeige, Reservierung oder Blockwirkung.

**Eine dynamische Zwei-Zug-Probe für Blockierung und anschließende Freigabe ist
nicht Teil dieses T2-Durchlaufs.** Die dafür nötige Zuordnung der beobachteten
Blockbeziehungen zu den konkreten Fahrzeugen und ihrer Richtung ist bisher nicht
zuverlässig gesichert. Ein nachgebildetes Testmodell würde diese offene Annahme
lediglich wiederholen. Der zweite Zug wird deshalb in T2 nur aus der beobachteten
Konfiguration im Depot gekauft und dort verkauft. Er ist kein nachgewiesener
Gegenzug oder vorausfahrender Blockierer. Der Katalog weist die offene dynamische
Signalwirkung ausdrücklich aus.

## Bedienung und Berichte

Pause und sämtliche Änderungen dieses Tests über den Launcher auslösen. Im Spiel
könnt ihr beobachten und die Kamera frei bewegen. Normale Bau-, Signal-, Linien-
und Fahrzeugknöpfe sowie die native Pause-Taste sind noch kein gemeinsamer
Eingabeweg dieses Tests.

Am Ende oder bei einer Fehlermeldung speichern **Host und Freund jeweils ihren
ZIP-Testbericht**. Anschließend TF2 schließen. Erst die Auswertung beider
Spielberichte kann T2-Schritte in der [Nachweischeckliste](GAMEPLAY_CHECKLIST.md)
als tatsächlich bestanden abhaken. Ein vollständiger fester Ablauf belegt keine
beliebige Welt, keine beliebige freie Platzierung und keine ungeprüften
Gleichzeitigkeitskonflikte.

Für einen anderen Reiter zuerst TF2 und den laufenden Test schließen. Eine noch
vorbereitete eigene Testinstallation wird vor dem Wechsel über ihre gesicherten
Dateien geprüft wiederhergestellt. Veränderte Dateien oder laufende Controller
blockieren den Wechsel; die alte Auswahl bleibt bestehen. Danach beide denselben
Reiter wählen und frisch vorbereiten. Ausgangskarte, Berichte und private
Verbindung bleiben erhalten; T1 und ältere Referenztests behalten ihre Abläufe.

## Der Rest soll in wenige größere Tests passen

Ziel sind **zwei bis drei größere Testpakete für die noch offenen Bereiche**,
mit zusammenhängenden Abläufen und kurzen Voraussetzungen statt vielen einzelnen
Releases. Der geplante Zuschnitt ist:

- **T2 – Bahn:** der hier beschriebene Netz-, Zug- und Linienbetrieb samt Abbau; weitere Signalwirkung nur mit eigenem belastbarem Nachweis.
- **T3 – weitere Verkehrsarten, Infrastruktur und Firma:** zusammengehörige Abläufe für noch offene Verkehrsarten und Anlagen, Ausbau/Abbruch und Firmenaktionen, soweit die Spiel-API sie kontrolliert ausführen und beobachten lässt.
- **T4 – Sitzung, Speichern und Konflikte, falls als eigener Durchlauf nötig:** gemeinsames Speichern und Laden, ein neuer gemeinsamer Start sowie gezielte konkurrierende Zugriffe und Abbruchfälle. Wiederbeitritt und weitere Sitzungsfunktionen bleiben eigene Entwicklungsaufgaben.

Das ist ein Bündelungsplan, keine Zusage, dass jede Spielmechanik unverändert über
die verfügbare API erreichbar ist oder in genau dieser Anzahl von Durchläufen
abgesichert werden kann. Nach diesen kontrollierten Funktionsprüfungen folgt die
Anbindung der normalen Ingame-Werkzeuge. Cursor und Bauvorschauen gehören zu einem
separaten gemeinsamen Anzeigekanal und gelten durch die festen Aufträge ebenfalls
noch nicht als geprüft.
