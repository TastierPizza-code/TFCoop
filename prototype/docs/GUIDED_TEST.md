# Alpha5.18: gemeinsamer Testbegleiter

`guided_suite_v1` ist ein eigener Test mit festen Aufträgen über den Launcher.
Die Spieler entscheiden durch ihre Aktionstasten, wann der aktuelle Auftrag
ausgeführt wird. Die normale freie Spieloberfläche wird anschließend angebunden.

## Ein zusammenhängender Durchlauf

Der kurze zehnrundige Aufbau aus Alpha5.15 bleibt erhalten. Danach wechseln sich
Host und Freund ab: gemeinsame Pause, zusätzliches Straßenfahrzeug kaufen,
eine neue Linie anlegen, Halte einzeln bearbeiten, Namen/Farbe und Wartung setzen,
zuweisen, fortsetzen, Fahrt beobachten, Fahrzeug anhalten/starten, Haltereihenfolge
und Warteregeln ändern, wenden, Depotfahrt, Ankunft, Verkauf und Linienlöschung.
Der versionierte [Katalog](../strict_sync/guided_catalog.py) enthält die genauen
Rollen und Aktionen. Er ist Bestandteil der verglichenen Testspezifikation.

Gleise, Signale und Züge sind ein noch offenes Kapitel. Der vorhandene Aufbau
liefert eine Straßenverbindung mit Straßenstationen. Daraus folgt kein Nachweis
für Schienengeometrie, Signalzuordnung, Zugbildung oder Eisenbahnterminals.
Die [Gesamtcheckliste](GAMEPLAY_CHECKLIST.md) zeigt diese und weitere offenen Bereiche.

## Was einen Schritt bestätigt

Die erste Anweisung bleibt bis zum vollständigen kurzen Aufbau und der
gemeinsamen Startbestätigung verborgen. Ein vorhandener Katalog, ein gestarteter
Controller oder eine einzelne lokale Spielbestätigung schalten sie nicht frei.
Die Capability-Vorprüfung berücksichtigt neben Lua-Funktionen auch die von TF2
verwendeten aufrufbaren API-Objekte. Sie führt keinen Befehl zur Erkennung aus;
fehlende oder nicht aufrufbare Maker halten weiterhin gesammelt an.

1. Nur der aktuelle Auftrag der vorgesehenen Rolle wird zur Ausführung zugelassen.
   Doppelte, veraltete oder vorgezogene Wünsche führen nicht zu einer zweiten Mutation.
2. Beide Spiele lesen am selben gehaltenen Simulationsstand die Voraussetzungen.
   Die Vorschauen müssen übereinstimmen, bevor der Auftrag freigegeben wird.
3. Der tatsächliche Engine-Callback und die beobachteten Objekte, Firmenwerte und
   Betriebszustände werden geprüft. Die nächsten Schritte verwenden die echten
   zurückgemeldeten Objektbindungen.
4. Erst verglichene und gemeinsam bestätigte Ergebnisse rücken den Test weiter.
   Die Oberfläche hat keinen Knopf zum Überspringen einer fehlgeschlagenen Prüfung.

Fahrt und Depotankunft sind ausdrücklich reine Beobachtungen, keine erfundenen
Engine-Callbacks. Solange das Fahrzeug noch nicht fährt oder noch unterwegs ist,
bleibt derselbe Schritt offen. Der zugeordnete Spieler kann später erneut prüfen.
Ein unerwarteter Widerspruch hält den gemeinsamen Test an und bleibt im Bericht.

## Bestehende Grundlagen bleiben erhalten

Native Simulationsschrittweite, Transport des Eingabestands und regelmäßige
Kontrollpunkte verwenden die akzeptierte Taktung. Der neue Modus verlängert
nur seine eigenen begrenzten Laufzeitbudgets für die menschliche Bedienung.
Die alten fünf auswählbaren Tests und ihre jeweiligen Abläufe bleiben erhalten.

Die neue Vorbereitung kann bei geschlossenem Spiel eine frühere eigene
Testinstallation anhand des bestehenden Journals zurücksetzen. Veränderte
Dateien oder aktive Controller werden dadurch nicht ungeprüft überschrieben.
Ausgangssave, ältere frische Kopien und Berichte bleiben erhalten. IP und privater
Verbindungsschlüssel werden weiterhin lokal gespeichert; jede Sitzung ist frisch.

## Grenzen des Nachweises

Diese Version bereitet den tatsächlichen Zwei-PC-Versuch vor. Headless-Prüfungen
testen Protokoll, Integrationsgrenzen und Adapter mit ausdrücklich künstlicher
Spiel-API. Sie beweisen weder die tatsächliche Annahme jeder neuen Engine-Aktion
noch langfristige Weltdeterministik. Erst die Berichte beider Teilnehmer ergeben
neue Häkchen in der Nachweischeckliste.

Der feste Kauf vergleicht die tatsächliche Abbuchung und den entstandenen Bestand.
Er belegt keine allgemeine Preisvorschau oder Konfliktbehandlung bei knappem Geld.
Die Schrittfolge ist seriell; neue gleichzeitige Linien-/Fahrzeugkonflikte sind
ein weiterer gezielter Test. Die früheren Depot-Konfliktnachweise bleiben gültig.
