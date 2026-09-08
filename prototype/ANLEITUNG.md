# TF2-Koop Alpha5.15-Eingabetest — für beide Spieler

**Korrektur in Alpha5.15:** Der Abbruch beim Vorbereiten des kurzen Tests ist behoben. Vorbereitung, Installer und Startprüfung verwenden nun denselben Konfigurationsvertrag. Beide Launcher aktualisieren und frisch vorbereiten; keine neuen Saves erforderlich.

**Der neue Modus „Fahrt und Eingaben · kurzer Aufbau“ soll die häufigeren Zuckler aus Alpha5.13 reduzieren.** Eingaben werden mit den ohnehin nötigen Schrittbestätigungen übertragen. Die zusätzliche leere Abfragerunde entfällt. Ob die Fahrt auf euren PCs wieder ausreichend ruhig läuft, muss der echte Zwei-PC-Test zeigen.

Der Aufbau hat jetzt **10 Runden**: Straße, Depot, Haltestellen, Fahrzeug und Linie werden erstellt und ihre tatsächliche Bereitschaft geprüft. Die bisherigen vollständigen Tests bleiben separat auswählbar. Eure **sehr große Karte** bleibt dieselbe; **kein neuer privater Saveimport und keine erneute Saveweitergabe nötig**, wenn beide schon die saubere Basis seit Alpha5.9 haben.

## 1. Beide aktualisieren

1. Test beenden, **TF2 vollständig schließen** und den Launcher schließen.
2. Den vorhandenen Launcher neu öffnen und das Update abwarten. Auf beiden PCs muss **Alpha5.15-Eingabetest** stehen. Ein Update wartet auf laufende Spiele oder Testcontroller.
3. **Bisherige Installation wiederherstellen** verwenden. Danach auf beiden PCs **Fahrt und Eingaben · kurzer Aufbau** auswählen. Die API-Diagnose wird nicht gebraucht.
4. Die eigenen Installations- und Steam-Saveordner prüfen. Keine Sicherungen oder alten Spielstände löschen.

## 2. Host und Freund verbinden

1. **Host:** „Ich bin Host“ wählen, eigene Hamachi-/LAN-IPv4 eintragen, frischen Sitzungscode mit **Neu** erzeugen. IP und vollständigen Code an den Freund weitergeben.
2. **Freund:** „Ich trete meinem Freund bei“ wählen und **dieselbe Host-IP** sowie den erhaltenen Code eintragen. Beide müssen im gleichen Hamachi-Netz oder LAN sein; für zwei PCs nicht `127.0.0.1` verwenden.
3. **Beide:** **Test vorbereiten und installieren** klicken. Die Vorbereitung sichert die Installation und erzeugt eine frische Kopie der gemeinsamen Basis.
4. **Beide:** **Verbinden & Test bereitstellen** klicken. Auf **Mitspieler: verbunden · gleiche Testdateien** und die Startfreigabe warten.
5. Nach der Freigabe TF2 über Steam starten; den Launcher offen lassen. Beim Start innerhalb von zwei Minuten beginnen, für das Laden wartet die Sitzung bis zu zehn Minuten.

Bei einer Firewallabfrage Zugriff im verwendeten LAN-/Hamachi-Netz erlauben. Der Launcher verwendet TCP 34208 und 34207. Unterschiedliche Modi oder Dateien werden vor dem gemeinsamen Test zurückgewiesen.

## 3. Jeder lädt seinen frisch angezeigten Save

1. In TF2 **Spiel laden** öffnen und genau die **neu im eigenen Launcher angezeigte `TF2-Koop-Messtest-….sav`** wählen. Nicht „Fortsetzen“ oder einen früheren Test laden.
2. **TF2 Strict Sync - gemeinsamer Eingabetest (Alpha5.15)** und **Legacy Fahrzeuge** sind bereits ausgewählt. Stehen dort alte Koop-Mods, den exakten neuen Savenamen prüfen. Keine weiteren Mods einschalten.
3. Laden und die **10 Aufbaurunden** abwarten. Wer zuerst geladen hat, wartet bei gehaltener Spielzeit auf den anderen. Die zufälligen Savenamen dürfen verschieden sein; die Ausgangsdaten werden geprüft.

TF2 möglichst sichtbar lassen, etwa neben dem Launcher. Ein früherer Timeout trat nach Minimieren auf; dessen Ursache ist bisher nicht sicher geklärt. Die Kamera dürft ihr bewegen. Die normalen Pause-/Tempo-Tasten und Bauwerkzeuge im Spiel sind noch nicht an diesen Eingabeweg angeschlossen.

## 4. Fahrt und Pause testen

Nach dem kurzen Aufbau werden die drei Tasten unter **Gemeinsame Eingaben · erst nach dem Aufbau** freigegeben. Über **TF2 Coop Test Line** könnt ihr das Fahrzeug beobachten.

1. Zunächst ungefähr **eine Minute laufen lassen**, ohne etwas zu drücken. Beurteilt, ob Fahrt und kurze Zuckler angenehmer geworden sind. Diese Minute zählt zur neuen Messung; sie ist kein weiterer vorgeschalteter Automatismus.
2. **Host pausiert** mit **Gemeinsam pausieren**. Beide warten auf den bestätigten Stillstand. **Freund setzt fort** mit **Gemeinsam fortsetzen**.
3. Danach **Freund pausiert**, **Host setzt fort**. Jeweils auf die gemeinsame Bestätigung warten. Damit hat jeder tatsächlich beide Zustandswechsel ausgelöst.
4. Einer pausiert erneut. Ab der gemeinsamen Bestätigung mindestens **45 Sekunden** warten und zusätzlich auf beiden PCs **Lange Pause erfasst** abwarten. Dafür werden mindestens 35 zusammenhängende Sekunden unveränderten Zustands gemessen. Dann setzt der andere fort.
5. Optional gleiche oder gegensätzliche Wünsche ungefähr gleichzeitig ausprobieren. Wenn Gegensätze in derselben Sammelrunde liegen, hat **Pause Vorrang**. Fast gleichzeitige Klicks können auch in verschiedene Runden fallen; ein neuer Fortsetzenwunsch nach Bestätigung bleibt möglich.
6. Noch einmal ungefähr eine Minute fahren lassen. Danach alle eigenen offenen Wünsche bestätigen lassen und einer klickt **Messung gemeinsam abschließen**. Beide warten auf ihre Abschlussmeldung.

Ein Klick wird zuerst lokal angenommen. Erst **beidseitig bestätigt** bedeutet, dass beide ihn verarbeitet haben. Ein schon freigegebener kurzer Fahrtabschnitt darf noch enden; die Pause wird an derselben Grenze auf beiden PCs ausgeführt. Mehrfaches Klicken beschleunigt die Bestätigung nicht. Eine schnelle eigene Folge Pause/Fortsetzen in derselben Sammelrunde endet ebenfalls pausiert.

**„Test beenden“ oben ist der Abbruchknopf.** Für den regulären Abschluss **Messung gemeinsam abschließen** verwenden, auch aus einer gemeinsamen Pause heraus. Später eingereihte Wünsche können danach unbestätigt bleiben. Ein sauberer Abschluss und vollständig erfasste Bedienproben werden getrennt angezeigt.

Der Versuch erlaubt maximal **128 Wünsche pro Spieler**, **2048 Sammelrunden** und **3000 zusätzliche Fortschrittsschritte** (höchstens zehn Minuten Spielzeit). Weitere Wünsche werden am Dateilimit abgewiesen; ein erreichtes Laufzeit-/Rundenlimit hält den Test an. Bitte nach den beschriebenen Proben gemeinsam abschließen.

## 5. Berichte sichern

1. Auf **beiden PCs** **Testbericht als ZIP …** verwenden und beide ZIPs privat zur Auswertung schicken, auch wenn nur einer einen Fehler sieht.
2. Dazuschreiben, wie sich die Fahrt angefühlt hat: häufige Stopps, seltene kurze Zuckler oder etwa wie Alpha5.12. Außerdem auffällig verspätete Eingaben oder unterschiedliche Ansichten erwähnen.
3. TF2 selbst schließen und **Bisherige Installation wiederherstellen** verwenden. Die Testsave nicht über eure normale Partie speichern. Jeder neue Versuch braucht einen frischen gemeinsamen Code, eine neue Vorbereitung und die neu angezeigten Saves.

## Bisherige Tests bleiben erhalten

| Modus | Ablauf |
|---|---|
| Fahrt und Eingaben · kurzer Aufbau | Neuer Ablauf aus Alpha5.14: 10 Runden Vorbereitung, danach freie Launcher-Eingaben und Fahrt. |
| Eingabetest aus Alpha5.13 · vollständiger Aufbau | Bisherige 240 Aufbaurunden, danach die bisherigen Eingabetasten mit eigener Abfragerunde. |
| Referenztest aus Alpha5.12 | Unveränderte 240 Aufbaurunden, anschließend 120 Sekunden automatische Fahrt mit vorgesehenen Kontrollpunkten und Pause. Nur zuschauen. |
| Vergleichstest aus Alpha5.11 | Unveränderte 240 Aufbaurunden und zwölf automatische Fahrt-/Warteabschnitte. Nur zuschauen. |

Ein Moduswechsel benötigt auf beiden PCs eine frische Vorbereitung. [Alpha5.12](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.12) bleibt die akzeptierte Referenz bei ungefähr 0,962x mit kaum sichtbaren Zucklern. Alpha5.13 bestätigte gegenseitige Pause/Fortsetzen, lief aber nur ungefähr 0,82x. Alpha5.15 ist vorab ohne Spielstart geprüft; seine tatsächliche Flüssigkeit ist noch nicht bestätigt. Diese Tests betreffen die beobachtete Szene und belegen keine freie gleichzeitige Bebauung oder vollständige Weltsynchronität.

## Erste Einrichtung und spätere Updates

Ohne Launcher einmal **[TFCoop-Windows.zip herunterladen](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip)**, vollständig in einen eigenen Ordner entpacken und `TF2-Coop.exe` öffnen. `TF2-Coop.exe`, `_internal` und `package_manifest.json` zusammenlassen. Git und Python sind nicht nötig. Später genügt ein normaler Neustart des Launchers bei geschlossenem TF2 und beendetem Test.

Auf einem neu eingerichteten PC muss das private saubere Spielstandpaar `initial.sav` und `initial.sav.lua` separat vorhanden sein. Beide nebeneinander entpacken und über **Testspielstand übernehmen …** die `initial.sav` wählen. Ein passender bestehender Cache bleibt gültig. Das öffentliche Update enthält keine Spielstände; Spielstände und Berichte werden nicht auf GitHub hochgeladen.

Diese Anleitung gehört zu [v0.5.15](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.15). Weitere technische Grenzen stehen in [VERIFICATION.md](https://github.com/TastierPizza-code/TFCoop/blob/main/prototype/VERIFICATION.md).
