# Feste Testszene: Straße, Depot und zwei Personenstationen

Die Mod enthält `res/construction/tf2_strict_probe/road_test.con` und das Rezept
`res/scripts/tf2_strict_probe/build_assets.lua`. Die Straße ist eigene Mod-Datei;
alle Gebäude und Fahrzeuge werden über Dateinamen aus der lokalen TF2-Installation
referenziert. Originalmodelle, Meshes und Vanilla-Konstruktionsdateien werden nicht
mitgeliefert. Die Untersuchung führte keine Spiel-Engine aus und bediente kein UI.

## Herkunft der Gebäudegeometrie

Die installierte `res/construction/construction.zip` enthält:

- `depot/road_depot_era_a.con`: keine eigenen Auswahlparameter. Der äußere
  Anschluss der eingefrorenen Straße liegt lokal bei `(0,-30.4153,0)`;
  der innere Punkt bei `(0,-20.79972,0)`. Beide Tangenten sind
  `(0,-9.6163,0)`, `snapNodes={1}`. Die Straße verwendet
  `street_depot/entrance_old.lua`. Der UI-`snapPoint` bei y=-25 ist ausdrücklich
  eine andere Größe als der Straßenanschluss.
- `station/street/modular_terminal.con`: Das kleinste 1850er Personenstations-
  Template mit `platL=1`, `platR=1`, `length=0`, `tramTrack=0` erzeugt die
  Modulplätze `20009900` und `20010000` mit `passenger_platform.module` und
  `20015503` mit `entrance_exit.module`, jeweils unter `station/street/`.
  Der Anschluss liegt lokal bei `(0,-35,0)`. Er ergibt sich aus der tatsächlichen
  Modulplatztransformation y=-15 und dem äußeren Modulpunkt y=-20.
  Das Literal ergibt eine Personenstation mit Tag 1, zwei Terminalgruppen
  (Tags -1 und 0) und 49000 Modulkosten.

Die Modulparameter des Rezepts enthalten `name`, `metadata`, `variant=0` und
eine leere `updateScript`-Referenz. Die Kennzahlen werden als Lua-Zahlenschlüssel
geführt; sie dürfen nicht mit einem ausschließlich für JSON-Arrays gedachten
Kopiervorgang verändert werden.

## Relative Anordnung in Metern

Die Straße besteht aus genau drei festen Abschnitten mit gemeinsamem Knoten
`(0,0,0)`. Ihre Endpunkte sind `(-80,0,0)`, `(80,0,0)` und `(0,40,0)`.
Die Straßenkanten bleiben zur Konstruktion gehörig; `freeNodes` ist leer.
Die drei äußeren Punkte dürfen über `snapNodes={0,3,5}` angeschlossen werden.
Straßentyp ist `standard/town_medium_old.lua` ohne Tramgleis oder Busspur.

| Bauwerk | Ursprung | Drehung um z | Anschluss nach Transformation |
|---|---|---|---|
| Linke Station | (-135,0,0) | +90° | (-100,0,0) |
| Rechte Station | (135,0,0) | -90° | (100,0,0) |
| Depot | (0,90.4153,0) | 0° | (0,60,0) |

Die 2×2-Rotationswerte im Rezept sind spaltenweise abgelegt. Zur gesamten Szene
kommt genau eine gemeinsame Position und Höhe hinzu, die der Engineadapter nach
einer begrenzten, nur lesenden Geländeprüfung auswählt. Das Rezept reserviert
180 m in jede horizontale Richtung. Version 1 ließ höchstens 2 m Höhenstreuung
zu; die kontrollierte Geländeangleichung von Version 2 ist unten beschrieben.

## Verbindliche Ergebniszuordnung

Der Konstruktionserfolg muss die tatsächliche Konstruktion aus dem
`BuildProposal.resultEntities`-Callback liefern. Von dieser Konstruktion führen
`frozenEdges` und die Kantenkomponenten zu den tatsächlichen Straßenknoten;
`depots` beziehungsweise `stations` führen zu den erzeugten Kindern. Die API
beschreibt diese Beziehungen und `BuyVehicle.resultVehicleEntity` als Ergebnis
des Fahrzeugkaufs. Die Prüfung eines gemeinsamen Anschlusses muss tatsächliche
Knoten-IDs vergleichen. Koordinaten bestätigen die eigene Rezeptgeometrie und
ersetzen keine Ergebniszuordnung. [Offizielle API-Typen](https://wiki.transportfever2.com/api/modules/api.type.html)

## Fahrzeugkonfiguration

Das geprüfte Modell `vehicle/bus/usa/horse_carriage_v2.mdl` existiert im lokalen
`res/models/model.zip`. Sein Zeitbereich umfasst 1850–1905; Carrier ist ROAD,
es gibt genau ein Abteil mit einer Ladekonfiguration für PASSENGERS. Damit
verwendet der Kauf ein `VehiclePart` in einem `TransportVehiclePart`,
`loadConfig={0}`, `autoLoadConfig={1}` und `vehicleGroups={1}`. Der Modellname
muss vor dem Bau über den Ressourcenindex aufgelöst werden. Kaufzeit und
Wartungszustand werden ausdrücklich gesetzt; Ergebnis-ID stammt aus dem Callback.

Zu beachten: `base_mod.lua` filtert Fahrzeuge anhand der gespeicherten Region.
Weitere lokal geprüfte passende 1850er Modelle sind
`vehicle/bus/postkutsche_v2.mdl` (Europa, bis 1907) und
`vehicle/bus/asia/troika_v2.mdl` (Asien, bis 1890). Sie besitzen ebenfalls ein
Personenabteil mit genau einer Ladekonfiguration. Eine Auswahl muss vor der
ersten Mutation feststehen und auf beiden PCs übereinstimmen.
Das Rezept nennt diese Kandidaten in fester Reihenfolge Europa, USA, Asien.
`repository.find` bestätigt einen Repository-Eintrag, keine Sichtbarkeit im
Kaufmenü. Die veröffentlichte API enthält keinen `isVisible`-Getter;
`repository.add` beschreibt seinen Sichtbarkeitsparameter ausdrücklich als
GUI-Eigenschaft. Ein gültiger Index, der passende Rückname und lesbare
Ressourcendaten bilden den Vorabcheck. Ob die Engine den Kauf tatsächlich
angenommen hat, bestätigt erst sein Callback.
[Offizielle Repository-API](https://wiki.transportfever2.com/api-testing/modules/api.res.html)

## Tatsächlich ausgeführte Prüfung

`tests/test_build_assets.py` führt die installierten Vanilla-`.con`- und
`.module`-Funktionen mit den Rezeptparametern außerhalb des Spiels aus. Die
Modulaufrufe folgen der Reihenfolge und den Transformationsregeln des lokalen
`game.config.ConstructWithModules`. Geprüft werden die exakten Template-Modul-IDs,
Anschlüsse, Terminalgruppen, die Depottransformation, alle drei Straßenäste sowie
Verfügbarkeit und Ladekonfiguration des Fahrzeugs.

Die aktuellen sieben Prüfungen bestanden auf Lua 5.1, 5.2, 5.3 und 5.4: insgesamt 28
erfolgreiche Ausführungen, keine übersprungen. Das bestätigt die Asset-Geometrie
und das Rezept. Es bestätigt noch nicht, dass die native Engine die Szene auf
dem konkreten Gelände annimmt, die Verbindungsstraßen baut oder das Fahrzeug die
Stationen tatsächlich erreicht. Diese Punkte müssen die beiden Spielinstanzen
im automatischen Bautest messen.

## Historisch: Version 2 mit gemeinsamer Geländeangleichung beim Straßenbau

Die folgenden Maße beschreiben das frühere Rezept. `road-depot-service-v2`
behielt die Anschlussgeometrie bei. Der gemeinsam ausgeführte Straßenbau
enthielt eine obligatorische `EQUAL`-Fläche bei
lokal z=0: x von -140 bis 140 m, y von -40 bis 120 m. Damit wird die Baufläche
als Teil desselben Baukommandos angeglichen. Eine separate manuelle
Geländeaktion ist nicht nötig. `EQUAL` gleicht an die angegebenen Polygone an;
`slopeLow` und `slopeHigh` bestimmen den Übergang zum Gelände außerhalb.
Beide sind 0,6. Die Engine darf bei unvereinbaren Geländeanforderungen weiterhin
den Bau ablehnen.
[Offizielle Dokumentation zur Geländeangleichung](https://wiki.transportfever2.com/doku.php?id=modding%3Aconstructionbasics#terrain_alignment)

Die Literalprüfung gegen die installierten Stock-Dateien ergibt nach den
Rezepttransformationen folgende Grenzen:

| Geländegeometrie | x in m | y in m | Verhalten bei einer Fläche auf z=0 |
|---|---|---|---|
| Beide Stationen | -130 bis 130 | -15 bis 15 | Alle `EQUAL`-Punkte liegen auf z=0 |
| Depot-Kern | -15 bis 10,02082 | 49,62587 bis 93,4153 | Alle `EQUAL`-Punkte liegen auf z=0 |
| Optionale Depot-Böschungen | -27,47902 bis 22,49984 | 37,80473 bis 105,23644 | `GREATER`-Punkte liegen auf oder unter z=0; `LESS`-Punkte auf oder darüber |

Die Fläche umfasst alle diese Punkte mit mindestens 10 m Abstand zum Rand
sowie die Straßenbreite inklusive Bürgersteigen. Zur weiterhin geprüften
160-m-Grenze bleiben mindestens 20 m. Bevorzugt wird eine gemessene
Höhenstreuung bis 2 m; die Obergrenze für einen weiteren Kandidaten beträgt
8 m. Bei einer Bauhöhe in der Mitte dieses Bereichs liegen die untersuchten
Geländepunkte höchstens 4 m darüber oder darunter. Dafür benötigt eine
Böschung mit Steigung 0,6 rechnerisch weniger als 6,67 m horizontalen Raum.
Diese Rechnung bezieht sich auf die untersuchten Punkte und ist kein Beweis
für das gesamte Gelände zwischen den Abtastungen oder die Annahme durch die
Spiel-Engine.

Die sieben Asset-Prüfungen liefen auf Lua 5.1, 5.2, 5.3 und 5.4 erfolgreich:
28 Ausführungen, keine übersprungen. Die zusätzlichen Prüfungen lesen alle
tatsächlichen Stock-Geländeflächen einschließlich der optionalen
Depot-Dreiecke und prüfen Fläche, Höhenverträglichkeit, Straßenbreite und
Abstand zur Freihaltezone. Das Spiel wurde dafür weder gestartet noch bedient.

## Version 3: ausdrückliche Graphverbindungen

`road-depot-service-v3` lässt zwischen den äußeren Anschlüssen der Gebäude und
der Straße jeweils 20 m Platz. Das ist eine absichtlich neue Verbindungsstrecke;
kein vorhandener Knoten wird verschoben. Die Baufläche reicht nun von x=-160
bis 160 und y=-40 bis 140 m, der gelesene Prüfbereich bis ±180 m.

Die lokale Upstream-Untersuchung `docs/re/PROPOSAL_STRUCTURE.md` beschreibt,
dass `scripting::Convert` die Construction-Vorlage mit einer leeren `nodes2snap`-
Zuordnung verarbeitet. Die interaktive Platzierung übergibt dagegen eine
explizite Snap-Zuordnung. Die früher vorausgesetzte automatische Verbindung
aufeinanderliegender Punkte war somit kein gültiger Skript-Vertrag. Die alte
Testnachbildung hatte dieselbe unbelegte Annahme und wird durch getrennte
Knoten plus wirklich ausgeführte Verbindungsproposals ersetzt.

Drei neue `SimpleStreetProposal`-Kanten referenzieren ausschließlich vorhandene
positive Knoten-IDs; die neuen Kanten erhalten absteigende negative Platzhalter.
Es werden keine Knoten hinzugefügt, entfernt oder geometrisch gesucht. Für jeden
bekannten Anschluss wird der vorherige Incident-Graph erfasst. Nach erfolgreichem
Callback muss genau eine passende neue Kante je ID-Paar vorliegen und der ganze
vorherige Incident-Graph unverändert sein. Eine leere `resultEntities`-Liste wird
nicht mit angenommenen IDs gefüllt. Erst ein vollständiger Nachweis aller drei
neuen Kanten erlaubt Bindings und spätere Fahrzeugkäufe.
[Offizieller SimpleStreetProposal-Vertrag](https://wiki.transportfever2.com/api/modules/api.type.html#SimpleStreetProposal)

Die echte Ablehnungsursache des alten Depot-Callbacks wurde im damaligen Bericht
nicht erfasst. Diese strukturelle Korrektur beseitigt die falsche Anschlussannahme,
beweist aber vor einem tatsächlichen Spielversuch weder die Annahme aller Gebäude
noch erfolgreiche Fahrt.
