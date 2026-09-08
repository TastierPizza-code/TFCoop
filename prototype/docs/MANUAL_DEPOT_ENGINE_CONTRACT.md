# Begrenzter Depotauftrag: Engine-Anbindung

`manual_depot_v1` ergänzt einen eigenen Auftrag `BUILD_DEPOT` mit vier relativen
Standorten und vier Vierteldrehungen. Die bestehende automatische Szene und
`PROBE_DEPOT` bleiben unverändert. Die Konfiguration muss diesen Modus ausdrücklich
aktivieren; die geladenen Snapshots enthalten anschließend die eigene
`probe.manual_depot`-Kennung und die tatsächlich bestätigten Platzierungen.

## Geprüfte Quellen und verbleibende API-Grenze

Die lokale Stock-Datei `res/construction/construction.zip`, Eintrag
`depot/road_depot_era_a.con`, wurde am 8. September 2026 gelesen. Sie enthält den
Kollider, die Depotstraße und die Geländeangleichungsflächen. Ihre Geometrie passt
bei den vier Vierteldrehungen innerhalb der konservativen horizontalen Freihaltebox
mit 45 Metern Halbausdehnung. Es werden keine Stock-Dateien mitgeliefert. Die
vier Positionen relativ zur bestehenden Testszene sind `(-90,-100)`, `(90,-100)`,
`(-90,90)` und `(90,90)` Meter. Die oberen Plätze können durch den konservativen
Abstand zur bestehenden Szene abgelehnt werden. Eine Standortnummer ist keine
vorweggenommene Zusage, dass die Engine den Bau erlaubt.

Die offizielle API dokumentiert `api.engine.util.proposal.makeProposalData` mit
`SimpleProposal` und `Context` sowie den Rückgabetyp `ProposalData`. Die Funktion
prüft Bauvorschläge einschließlich Kollisionen, Formen und Kosten.
[Offizielle Engine-Referenz](https://wiki.transportfever2.com/api/modules/api.engine.html#util.proposal.makeProposalData)

Die offizielle Typenreferenz beschreibt `ErrorState` und `ProposalData`, führt
deren einzelne Felder aber nicht vollständig auf.
[Offizielle Typenreferenz](https://transportfever2.com/wiki/api/modules/api.type.html#ProposalData)
Die hier verwendeten Namen `errorState.critical`, `errorState.messages` und
`costs` sind zusätzlich durch die lokal vorhandene Upstream-Implementierung
`upstream/tpf2-multiplayer/mod/mp_lockstep_1/res/config/game_script/lockstep.lua`
begründet: Dort ist `resultProposalData.costs` ausdrücklich als gemessen
beschrieben (Bereich 612–624); die Fehlerauswertung verwendet `critical` und
`messages` (Bereich 2617–2627). Die lokale Rekonstruktionsdokumentation
`docs/re/PROPOSAL_STRUCTURE.md` bestätigt `errorState.critical` als native
Gültigkeitsprüfung. Das sind zusätzliche Integrationsbelege, keine aktuelle
Messung des neuen Vorabaufrufs auf den beiden Benutzer-PCs.

Der echte Alpha5.15-Bericht bestätigt das bisherige Depot mit unveränderten
Rezeptparametern, beobachteter Konstruktionstransformation, tatsächlich gebundenem
Depotkind und 10.000 Geldabbuchung. Er enthält noch keine eigene Beobachtung des
neuen `makeProposalData`-Aufrufs. Die Vorabfelder und deren aktueller Datentyp
bleiben deshalb eine ausdrücklich noch im Spiel zu prüfende Schnittstelle.
Die Tests bilden die gelesenen API-Verträge nach und werden nicht als Nachweis
ausgegeben, dass diese neue Engine-Methode bereits im Spiel gelaufen ist.

## Verhalten an einer gemeinsamen Grenze

Die Vorschau prüft den aktuellen Slotbesitz, 81 aktuelle Geländepunkte und die
Octree-Kollisionen. Ein bereits bebauter Slot, Wasser, unzulässige Kartenkoordinaten,
zu unebenes Gelände, ein von der Engine abgelehnter Vorschlag oder unzureichendes
beobachtetes Guthaben ergeben eine begrenzte Ablehnung ohne `sendCommand`.
Die Nachrichten im beobachteten Fehlercontainer werden über die schon vorhandene
native `pairs`-/`__members`-Konvertierung gelesen. Nullbasierte oder nicht
aufeinanderfolgende Schlüssel dürfen nicht als leere Liste gelten.

Eine Zusage setzt lesbare echte Vorabdaten und positive ganzzahlige Kosten voraus.
Fehlende oder unlesbare API-Daten halten den Versuch an, bevor ein Baukommando
gesendet wird. Bei einem solchen Fehler bleiben getrennte, begrenzte
Vorabdiagnosen mit beobachteten Feldtypen erhalten. Sie ersetzen keinen Weltnachweis.

Nach dem Vergleich beider Vorschauen wird jeder einzelne Bau gegen den dann
aktuellen Zustand erneut geprüft. Der erneut erzeugte Plan muss genau zur
gemeinsam bestätigten Vorschau passen. Der eigentliche Bau darf nur einmal
gesendet werden. Sein Callback muss die exakte Konstruktion liefern; Dateiname,
Parameter, Transformation, Name, Depotkind und tatsächliche Abbuchung werden
kontrolliert. Anschließend vergleicht der Python-Adapter diese Angaben mit dem
frischen Weltsnapshot, den beiden neuen logischen Objektbindungen und dem
Platzierungsregister. Vorherige beobachtete Objekte bleiben unverändert.

Ein unerwarteter Fehler erst bei der Anwendung hält den Versuch an. Er wird nicht
als sichere Konfliktablehnung ausgegeben. Native Schrittweite, Takt und
Fortschrittsfreigaben des akzeptierten Eingabetests bleiben unverändert.
