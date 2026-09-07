# TF2-Koop Alpha5.13-Eingabetest — Anleitung für beide Spieler

**Nach dem automatischen Aufbau bestimmt ihr jetzt selbst, wann die gemeinsame Firma pausiert und weiterfährt.** Dafür gibt es im Launcher die Tasten **Gemeinsam pausieren**, **Gemeinsam fortsetzen** und **Messung gemeinsam abschließen**. Beide Spieler können sie verwenden. Nach dem Aufbau gibt es im neuen Modus keine vorprogrammierte Pause mehr.

**Eure bisherige sehr große Karte und das bereits übernommene saubere Spielstandpaar bleiben erhalten. Für dieses Update braucht ihr keinen neuen privaten Saveimport.** Die Vorbereitung erstellt wie bisher auf jedem PC eine frische Testsave-Kopie. Das öffentliche Programmupdate enthält keinen Spielstand.

Alpha5.12 bleibt als akzeptierte Referenz erhalten: Euer tatsächlicher Zwei-PC-Lauf erreichte ungefähr **0,962x** mit kaum sichtbaren kurzen Zucklern. Weitere Tempooptimierungen warten, bis die übrigen Koop-Funktionen arbeiten. Alpha5.13 ist vorab ohne Spielstart geprüft; **der echte Zwei-PC-Eingabetest steht noch aus**. Normale TF2-Pausebuttons, freies Bauen, Cursor und Blaupausen sind in diesem Versuch noch nicht angeschlossen. Mehr zum [Prüfumfang](https://github.com/TastierPizza-code/TFCoop/blob/main/prototype/VERIFICATION.md).

## 1. Beide aktualisieren und denselben Test wählen

1. Laufenden Test beenden, **TF2 vollständig schließen** und den bisherigen Launcher schließen. Ein Update wartet, solange das Spiel oder ein Messcontroller läuft.
2. Den vorhandenen Launcher normal neu öffnen und die Updateprüfung abwarten. Auf beiden PCs muss **Alpha5.13-Eingabetest** stehen. Der Cache des sauberen Spielstandpaars bleibt gültig.
3. **Bisherige Installation wiederherstellen** verwenden. Das Programmupdate allein ersetzt noch keine installierten Testdateien. Sicherungen und eigene Spielstände nicht von Hand löschen.
4. Unter **Ordner prüfen** den eigenen **TF2-Installationsordner** und **Steam-Saveordner** prüfen. Übliche Formen sind `…\steamapps\common\Transport Fever 2` und `…\Steam\userdata\<Kontonummer>\1066780\local\save`.
5. Im Reiter **Gemeinsamer Eingabetest (experimentell)** auf **beiden PCs „Pause selbst steuern“** wählen. **API-Diagnose allein** wird für diesen Versuch nicht gebraucht.
6. Beide PCs mit demselben Hamachi-Netz verbinden oder dasselbe LAN verwenden. Ihr braucht die **IPv4-Adresse des Hosts**; bei Hamachi beginnt sie normalerweise mit `25.`. Für zwei PCs nicht `127.0.0.1` verwenden.

## 2. Du als Host

1. **Ich bin Host** auswählen.
2. Unter **IP des Hosts (Hamachi/LAN)** deine eigene Hamachi- oder LAN-IPv4 eintragen.
3. Neben **Gemeinsamer Sitzungscode** auf **Neu**, dann **Kopieren** klicken. Diesen vollständigen frischen Code und deine Host-IP deinem Freund schicken. Beide verwenden **Pause selbst steuern**.
4. **Test vorbereiten und installieren** klicken und die Fertigmeldung abwarten. Der Launcher sichert die vorherigen Dateien und importiert eine neue Kopie der gemeinsamen Ausgangsbasis.
5. Den angezeigten Namen **`TF2-Koop-Messtest-….sav`** merken. Die zufällige Endung darf bei deinem Freund anders sein; der Inhalt wird geprüft.
6. Sobald beide vorbereitet haben, **Verbinden & Test bereitstellen** klicken.

## 3. Dein Freund als Mitspieler

1. **Ich trete meinem Freund bei** auswählen.
2. Unter **IP des Hosts (Hamachi/LAN)** die vom Host erhaltene IP eintragen. Auf beiden PCs steht dieselbe Host-IP.
3. Den eigenen Sitzungscode vollständig durch den neuen Code des Hosts ersetzen. **Pause selbst steuern** muss auch hier ausgewählt sein.
4. **Test vorbereiten und installieren** klicken und die Fertigmeldung abwarten. Der Launcher importiert auch hier eine frische Testsave samt `.sav.lua`. Nichts von Hand in den Spielordner kopieren.
5. **Verbinden & Test bereitstellen** klicken.

Bei einer Windows-Firewallabfrage den Launcher im verwendeten LAN-/Hamachi-Netz erreichbar machen. Lobby und Test verwenden TCP 34208 und TCP 34207. Unterschiedliche Testmodi oder Testdateien werden vor dem Spielstart zurückgewiesen.

## 4. Beide laden die neu angezeigte Testsave

1. Auf **Mitspieler: verbunden · gleiche Testdateien** und die Startfreigabe warten. Diese Meldung bestätigt Dateien und Modus; die geladene Welt wird danach getrennt verglichen.
2. Nach der Freigabe innerhalb von zwei Minuten **TF2 über Steam starten** klicken oder das Spiel selbst über Steam starten. Für das anschließende Laden wartet der Sitzungsstart bis zu zehn Minuten. Den Launcher offen lassen.
3. In TF2 **Spiel laden** öffnen und genau die **neu im eigenen Launcher angezeigte `TF2-Koop-Messtest-….sav`** auswählen. Nicht **Fortsetzen**, eine alte Testsave oder eine Diagnose-Save wählen.
4. Unter **Aktivierte Mods** stehen bereits **TF2 Strict Sync - gemeinsamer Eingabetest (Alpha5.13)** und **Legacy Fahrzeuge**. Die Modliste braucht keine erneute Umstellung. Stehen dort die alten Koop-Mods, zurück zur Ladeliste gehen und den exakten neuen Namen auswählen. Keine weiteren Mods einschalten.
5. Die Testsave laden. Wer zuerst fertig ist, wartet bei gehaltener Spielzeit, bis beide geladen haben und der Ausgangsvergleich passt.

## 5. Aufbau abwarten und dann selbst steuern

Zuerst laufen **240 automatische Aufbaurunden**. Der Test baut Straße, Depot und Haltestellen, kauft ein Fahrzeug und weist es einer Linie zu. Die vorgegebenen Pausen während dieses Aufbaus bleiben erhalten. Dabei nur zuschauen; die Kamera dürft ihr bewegen. Über **TF2 Coop Test Line** könnt ihr das Fahrzeug auswählen und beobachten.

**Bei Runde 240 nicht beenden.** Danach werden unten im Launcher unter **Gemeinsame Eingaben · erst nach dem Aufbau** die drei neuen Tasten freigegeben. Ab hier kommen Pause und Fortsetzen von euren tatsächlichen Klicks. Bitte während des gesamten Versuchs **keine normalen Pause-/Play-/Tempo-Tasten im Spiel bedienen und nichts selbst bauen, kaufen oder an Linien ändern**. Kamera und Ansicht dürft ihr weiterhin bewegen.

Ein Klick wird zuerst lokal angenommen. Das ist noch keine Bestätigung des anderen PCs. Wartet jeweils, bis der eigene Wunsch **beidseitig bestätigt** ist und beide denselben Zustand sehen. Ein bereits freigegebener kurzer Fahrtabschnitt darf noch fertig werden; die Pause wird am nächsten gemeinsamen Haltepunkt ausgeführt. Bei ausstehender Bestätigung nicht durch weitere Klicks versuchen, den Wunsch zu beschleunigen.

## 6. Eure Bedienprobe

1. **Host pausiert:** Du klickst zu einem selbst gewählten Zeitpunkt **Gemeinsam pausieren**. Beide warten auf den bestätigten Stillstand.
2. **Freund setzt fort:** Dein Freund klickt **Gemeinsam fortsetzen**. Beide warten auf Bestätigung und beobachten, dass das Fahrzeug wieder fährt.
3. **Freund pausiert:** Dein Freund klickt später **Gemeinsam pausieren**. Nach der gemeinsamen Bestätigung klickst du **Gemeinsam fortsetzen**. Damit hat jeder eine echte Pause und ein echtes Fortsetzen ausgelöst; eine Pause bei schon pausiertem Spiel allein genügt dafür nicht.
4. **Längere Pause:** Einer pausiert erneut. Ab der gemeinsamen Bestätigung mindestens **45 Sekunden** warten, ohne umzuschalten. Zusätzlich auf beiden PCs abwarten, bis **Lange Pause erfasst** angezeigt wird; dafür müssen mindestens **35 Sekunden** gemessen sein. Danach setzt der andere fort. Die erfasste Zeit muss zu einer zusammenhängenden Pause mit unverändertem beobachtetem Zustand gehören; mehrere kurze Pausen werden dafür nicht addiert.
5. **Gleichzeitigkeit ausprobieren:** Optional beide ungefähr gleichzeitig dieselbe Taste drücken, anschließend ungefähr gleichzeitig gegensätzliche Wünsche senden. Werden Gegensätze in derselben Sammelrunde erfasst, hat **Pause Vorrang**. Fast gleichzeitige Klicks können auch in verschiedene Runden fallen; dann werden diese nacheinander verarbeitet. Ein neuer Fortsetzenwunsch nach der gemeinsamen Bestätigung bleibt möglich. Eine schnelle eigene Folge Pause/Fortsetzen in derselben Runde endet ebenfalls pausiert.
6. Wenn ihr zufrieden seid, alle noch offenen Wünsche bestätigen lassen. Dann klickt einer von euch **Messung gemeinsam abschließen**. Das funktioniert auch während einer gemeinsamen Pause. Beide warten auf ihre Abschlussmeldung und exportieren anschließend ihre Berichte.

Die Zeitpunkte der Klicks sind nicht vorgegeben; ihr müsst keine bestimmte Aufbaurunde treffen. Die Auswertung prüft echte Pause-/Fortsetzen-Übergänge beider Spieler und eine längere Pause. Fehlt eine dieser erforderlichen Bedienproben, kann die Sitzung korrekt abgeschlossen sein, während die Probe noch als unvollständig angezeigt wird. Gegensätzliche Wünsche verschiedener Spieler in derselben Sammelrunde werden zusätzlich erfasst; dieser optionale Konfliktversuch ist keine Bedingung für die Abschlussbewertung.

**„Test beenden“ oben ist der Abbruchknopf.** Für den regulären Abschluss den neuen Knopf **Messung gemeinsam abschließen** verwenden. Nach einem gemeinsamen Ende werden keine weiteren Wünsche ausgeführt. Ein Wunsch, der erst nach der letzten Sammlung lokal einging, kann unbestätigt bleiben.

Der Versuch ist begrenzt auf **128 Wünsche je Spieler**, **2048 Abfragerunden** und **3000 zusätzliche Fortschrittsschritte**. Letzteres entspricht höchstens zehn Minuten zusätzlicher Spielzeit; lange Pausen verbrauchen ebenfalls Abfragerunden. Bitte den Versuch nach euren Bedienproben deutlich davor gemeinsam abschließen. Ein erreichtes Limit hält den Test an und zählt nicht als erfolgreicher Abschluss. Manuelle Bauaufträge folgen erst in einer anschließenden Etappe.

## 7. Berichte sichern und aufräumen

1. Nach gemeinsamem Abschluss oder einem Fehler auf **beiden PCs** **Testbericht als ZIP …** verwenden. Beide normalen ZIPs privat zur Auswertung schicken, auch wenn nur einer einen Fehler sieht. Alte Berichte aufbewahren.
2. Kurz dazuschreiben, wer Pause und Fortsetzen bedient hat, wie lange die längere Pause dauerte und ob Wünsche deutlich verzögert waren oder die beiden Ansichten voneinander abwichen. Ein Screenshot kann den Ergebnistext ergänzen.
3. Erst nach der gemeinsamen Abschlussmeldung gegebenenfalls **Test beenden** verwenden, um verbleibende Controller zu schließen. Bei einem Abbruch darf ein bereits freigegebener Engineauftrag noch enden oder seine Zeitgrenze erreichen; der Knopf schließt TF2 nicht.
4. TF2 selbst vollständig schließen und **Bisherige Installation wiederherstellen** verwenden. Die Testsave nicht über eure normale Partie speichern. Vorhandene Savekopien, Sicherungen und exportierte Berichte bleiben erhalten.

Jeder weitere Versuch benötigt eine neue Vorbereitung mit einem frischen gemeinsamen Code und neu importierten Testsave-Kopien. Eine fortgesetzte Messsave ist keine neue Ausgangsbasis. Bei Lua-/Native-Fehlern die normalen ZIPs exportieren; keine zusätzliche Solo-Diagnose vorbereiten.

## Die erhaltenen Vergleichsmodi

**Referenztest aus Alpha5.12** bleibt unverändert auswählbar. Er baut dieselbe Szene auf und fährt danach automatisch 120 Sekunden Spielzeit, mit Kontrollpunkten alle zehn Sekunden und einer vorgesehenen Pause nach 60 Sekunden. In diesem Modus nur zuschauen und bis zur Abschlussmeldung warten. Die manuelle Launchersteuerung gehört nicht zu diesem Ablauf.

**Vergleichstest aus Alpha5.11** enthält weiterhin zwölf Abschnitte mit jeweils fünf Sekunden zusätzlicher Spielzeit, teilweise mit absichtlich ungleichen Wartezeiten. Seine Übergangsstopps bleiben Teil des Vergleichs. Auch hier nur zuschauen und erst nach dem Abschluss exportieren.

Für einen Moduswechsel beide Test und TF2 schließen, die vorherige Installation wiederherstellen, auf beiden PCs denselben Modus auswählen und mit neuem gemeinsamen Code frisch vorbereiten. Die Vergleiche laufen im aktuellen Programm; ein Downgrade ist nicht nötig. Paket und Quellstand von [v0.5.12](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.12) bleiben separat erhalten. Die akzeptierte Messung betrifft die automatische Testszene und belegt noch keine freien Baueingaben oder vollständige Weltsynchronität.

## Erste Einrichtung und spätere Updates

Ohne vorhandenen Launcher einmal **[TFCoop-Windows.zip — neueste Version](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip)** herunterladen und vollständig in einen eigenen Ordner entpacken, beispielsweise `C:\Games\TFCoop`. Nicht in den Spielordner oder über eine alte Version entpacken. `TF2-Coop.exe`, `_internal` und `package_manifest.json` zusammenlassen. Git und Python sind nicht nötig. Diese Anleitung gehört zu [Alpha5.13 / v0.5.13](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.13).

Die **sehr große Karte** bleibt dieselbe. Seit Alpha5.9 wird ihr sauberes privates Paar `Testspielstand/initial.sav` und `Testspielstand/initial.sav.lua` verwendet. Falls dieses Paar auf einem neu eingerichteten PC noch fehlt, beide unverändert nebeneinander entpacken und über **Testspielstand übernehmen …** die `initial.sav` wählen. Ein bestehender passender Cache wird weiterverwendet; eure beiden bisherigen Installationen brauchen keinen neuen privaten Import. Die Basis vor Alpha5.9 oder eine fortgesetzte Testsave passt nicht.

Für spätere Updates genügt derselbe Launcher: Test und TF2 schließen, Launcher normal öffnen, Updateprüfung abwarten. Anschließend die vorherige Installation wiederherstellen und frisch vorbereiten. Der Updater lädt Spielstände und Berichte nicht auf GitHub hoch. Berichte können lokale Pfade und Kartendaten enthalten und sind für die private Auswertung bestimmt.

## Wenn etwas nicht klappt

| Anzeige oder Problem | Nächster Schritt |
|---|---|
| Verschiedene Testmodi oder Dateien | Beide dieselbe Version und denselben Modus wählen, wiederherstellen und mit neuem gemeinsamen Code vorbereiten. |
| Warten auf Mitspieler | Dieselbe Host-IP und denselben vollständigen Code prüfen; Hamachi-Verbindung und Firewallzugriff prüfen. |
| Verbunden, aber kein Spielkontakt | Startfreigabe abwarten, TF2 starten und den exakt neu angezeigten Testsave mit Strict Sync Alpha5.13 laden. |
| Beim Laden stehen alte Mods | Zurück zur Ladeliste und den exakten neuen Namen aus dem Launcher auswählen. |
| Neue Tasten bleiben grau | Auf beiden PCs „Pause selbst steuern“ wählen; die Tasten werden erst nach dem gemeinsamen Aufbau freigegeben und nach Abschluss oder Fehler gesperrt. |
| Wunsch lokal angenommen, aber noch offen | Auf gemeinsame Bestätigung warten. Bei Fehler oder unterbrochener Verbindung beide ZIPs sichern; nicht lokal im Spiel fortsetzen. |
| Bedienproben fehlen trotz Abschluss | Beide ZIPs schicken. Die Auswertung unterscheidet echte Zustandsübergänge, gemessene längere Pause und Gegensätze in derselben Sammelrunde. |
| Wunschlimit oder anderes Testlimit erreicht | Beide ZIPs sichern und frisch vorbereiten. Ein Limitabbruch ist kein bestandener Test. |
| Ausgangsspielstand fehlt oder Prüfsummen passen nicht | Das unveränderte saubere Paar aus Alpha5.9 vollständig bereitstellen und seine `initial.sav` übernehmen; die `.sav.lua` muss danebenliegen. |
| Lua-/Native-Fehler oder Bauabbruch | Auf beiden PCs die normalen Testbericht-ZIPs exportieren und mit Fehlertext privat schicken. Keine zusätzliche Solo-Diagnose nötig. |
| Export oder Wiederherstellung blockiert | Den genauen Fehlertext schicken; vorhandene Berichte und Sicherungen behalten. Vor Wiederherstellung Test und TF2 vollständig beenden. |

Der native Test unterstützt den geprüften Windows-Spielbuild 35924. Bei einem anderen Build den Fehlertext schicken, statt DLLs manuell auszutauschen. Nach einem Launcherabsturz bei geschlossenem TF2 erneut öffnen und die Wiederherstellung verwenden.
