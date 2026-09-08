# Alpha5.18-Testbegleiter

Der geführte Versuch konnte direkt beim Laden an einer falschen API-Vorprüfung
anhalten: TF2 stellt seine Befehls-Maker als aufrufbare Lua-Objekte bereit, die
Prüfung akzeptierte bislang nur gewöhnliche Funktionen. Sie erkennt jetzt beide
Formen, ohne zur Erkennung Befehle auszuführen. Tatsächlich fehlende oder nicht
aufrufbare Maker werden weiterhin gesammelt gemeldet und halten den Test an.

Der erste Host-/Freund-Auftrag erscheint erst nach dem vollständigen kurzen
Aufbau und der Startbestätigung beider Spiele. Der Launcher zeigt zuvor das
Warten auf die Spiele und den tatsächlichen Fortschritt des zehnrundigen
Automatikaufbaus: Straße, Depot, Haltestellen, Fahrzeug und Linie. Auch die letzte
Prüfung vor dem Schreiben eines Auftrags verlangt die gemeinsame Freigabe.

Die Host-Adresse steht sichtbar in der Verbindungsübersicht. Für Hamachi müssen
Host und Freund dieselbe Hamachi-IPv4 des Hosts verwenden. Gespeicherte Adressen
werden nicht heimlich durch lokale Vorschläge ersetzt; Änderungen erfolgen im
privaten Profil. Private Adressen und Schlüssel sind kein Teil des Updates.

Auf beiden PCs TF2 und den alten Test schließen, Launcher neu öffnen und das
Update abwarten. Verbindung kontrollieren, **Test vorbereiten → Verbinden → den
angezeigten frischen Spielstand laden**. Den gemeinsamen Automatikaufbau
abwarten, dann den einzelnen Aufträgen folgen. Aktionen und Pause weiterhin im
Launcher auslösen. Die vorhandene saubere Ausgangskarte bleibt verwendbar.

Die 26 festen Fahrzeug-/Linienaufträge, die akzeptierte Simulations-Taktung und
alle fünf älteren Testmodi bleiben erhalten. Die Regression verwendet zusätzlich
die tatsächliche Form der aufrufbaren API-Maker und verzögerte beidseitige
Startbestätigungen. Dies ist kein neuer TF2-Zwei-PC-Nachweis; die noch offenen
Funktionen und Nachweisgrenzen bleiben in der Checkliste sichtbar.
