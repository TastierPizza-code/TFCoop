# TF2-Koop Alpha5.7-Bautest — Anleitung für beide Spieler

**Alpha5.7 überarbeitet die Straßenanschlüsse und die Verarbeitung von Bauantworten.** Im letzten gemeinsamen Versuch stimmten Straße, Pause und Firmenwerte überein. Danach lehnte TF2 bei einem Teilnehmer den Depotbau ab; beim anderen verdeckte ein Statuslesefehler die Bauantwort.

Depot und Haltestellen werden jetzt mit Abstand zur Teststraße gebaut und anschließend durch drei ausdrücklich gebaute Straßenabschnitte verbunden. Vorübergehende Lesesperren nach einer Bauantwort führen zum Warten an derselben Spielgrenze. Der Baubefehl wird dabei nicht erneut ausgeführt. Ursprüngliche Ablehnungen und verfügbare Fehlerdetails bleiben im normalen Testbericht erhalten.

Der automatische Ablauf hat weiterhin **240 Runden**: Straße, Depot, zwei Haltestellen, Straßenverbindungen, Fahrzeugkauf, Linie, Abfahrt und gemeinsame Pausen. Die Änderungen müssen noch in euren tatsächlichen TF2-Installationen geprüft werden. Freies gleichzeitiges Bauen, Spielercursor und normale gemeinsame Pause-Tasten sind noch nicht freigeschaltet.

## 1. Beide aktualisieren und die vorherige Installation zurücksetzen

1. Den laufenden Test beenden, **TF2 vollständig schließen** und den bisherigen Launcher schließen. Ein Versionswechsel wartet, solange TF2 oder ein Messcontroller läuft.
2. Den vorhandenen Launcher normal neu öffnen und die Updateprüfung abwarten. Ab Alpha5.2 lädt er neuere GitHub-Releases automatisch. Auf beiden PCs muss oben **Alpha5.7-Bautest** stehen. Ihr braucht keine neue ZIP von Hand herunterzuladen oder über Discord auszutauschen.
3. Auf beiden PCs **Bisherige Installation wiederherstellen** verwenden. Das gilt insbesondere für eine noch installierte **API-Diagnosemod**. Der Programm-Download allein ersetzt die installierten Testdateien nicht.
4. Oben unter **Ordner prüfen** den eigenen **TF2-Installationsordner** und **Steam-Saveordner** prüfen. Übliche Pfade sind `…\steamapps\common\Transport Fever 2` und `…\Steam\userdata\<Kontonummer>\1066780\local\save`.
5. Im ersten, standardmäßig geöffneten Reiter **Bautest (experimentell)** bleiben. **API-Diagnose allein** ist als zweiter Reiter für gezielte spätere Untersuchungen vorhanden und wird für diesen Versuch nicht verwendet.
6. Bei Hamachi beide PCs in dasselbe Hamachi-Netz verbinden. Ihr verwendet die **IPv4-Adresse des Hosts**, normalerweise eine Adresse mit `25.` am Anfang. Im selben lokalen Netzwerk genügt stattdessen die LAN-IPv4 des Hosts.

## 2. Du als Host

1. **Ich bin Host** auswählen.
2. Unter **IP des Hosts (Hamachi/LAN)** deine eigene Hamachi- oder LAN-IPv4 eintragen. Für zwei PCs nicht `127.0.0.1` verwenden.
3. Neben **Gemeinsamer Sitzungscode** auf **Neu**, dann auf **Kopieren** klicken. Diesen frischen vollständigen Code und deine Host-IP deinem Freund schicken.
4. **Test vorbereiten und installieren** klicken und die Fertigmeldung abwarten. Der Launcher sichert die vorherigen Dateien und importiert eine frische Kopie des lokal verwahrten gemeinsamen Ausgangsspielstands.
5. Den angezeigten Namen **`TF2-Koop-Messtest-….sav`** merken. Die zufällige Endung darf bei deinem Freund anders sein; der Ausgangsinhalt wird geprüft. Nicht die frühere Diagnose-Save oder eine alte Testfortsetzung verwenden.
6. Sobald beide vorbereitet haben, **Verbinden & Test bereitstellen** klicken.

## 3. Dein Freund als Mitspieler

1. **Ich trete meinem Freund bei** auswählen.
2. Unter **IP des Hosts (Hamachi/LAN)** die vom Host erhaltene IP eintragen. Auf beiden PCs steht dieselbe Host-IP.
3. Den eigenen Sitzungscode vollständig durch den neuen Code des Hosts ersetzen.
4. **Test vorbereiten und installieren** klicken und die Fertigmeldung abwarten. Auch hier werden eine eigene neue Testsave und ihre `.sav.lua` importiert. Nichts davon muss von Hand in den Spielordner kopiert werden.
5. **Verbinden & Test bereitstellen** klicken.

Bei einer Windows-Firewallabfrage den Launcher im verwendeten LAN-/Hamachi-Netz erreichbar machen. Der Bautest verwendet TCP 34207 und TCP 34208.

## 4. Beide laden die neue Testsave

1. Auf **Mitspieler: verbunden · gleiche Testdateien** und die Startfreigabe warten. Diese Meldung bestätigt zunächst die Testdateien; die tatsächlich geladene Welt wird anschließend verglichen.
2. Nach der Freigabe innerhalb von zwei Minuten **TF2 über Steam starten** klicken oder TF2 selbst über Steam starten. Für das anschließende Laden wartet der gesamte Sitzungsstart bis zu zehn Minuten. Den Launcher offen lassen.
3. In TF2 **Spiel laden** öffnen und ausdrücklich die **neu im eigenen Launcher angezeigte `TF2-Koop-Messtest-….sav`** auswählen. Nicht **Fortsetzen** drücken und nicht die `TF2-API-Diagnose-….sav` wählen.
4. Rechts über **Aktivierte Mods**, neben **GRUNDOPTIONEN**, auf **OPTIONEN AUSWÄHLEN** klicken und den Reiter **Mods** öffnen.
5. Für diese Testsave auf beiden PCs ausschließlich **TF2 Strict Sync - automatischer Bautest (Alpha5.7)** und **Legacy Fahrzeuge** aktivieren. **TF2 API-Diagnose**, alte Koop-Mods, **MP Lockstep** und **MP Bridge** deaktivieren; keine weiteren Mods einschalten. Die Modauswahl bei **Freies Spiel** ändert die Liste dieser gespeicherten Save nicht.
6. Die Testsave laden. Wenn einer früher fertig ist, bleibt seine Spielzeit gehalten, bis beide geladen haben und der gemeinsame Startvergleich passt.

## 5. Während der 240 Runden

- **Nur zuschauen; die Kamera dürft ihr bewegen.** Bitte nicht selbst bauen, kaufen, Linien bearbeiten, pausieren oder die Geschwindigkeit umschalten. Der Test gibt alle Bau-, Fahrt- und Pausenwünsche selbst vor.
- Die ersten neun Runden richten die Szene bei gehaltener Simulation ein. Runde 5 baut die Straßenverbindungen; ab Runde 9 ist die Fahrt vorgesehen. Von Runde 80 bis 99 pausiert der Test; Runde 100 setzt die Fahrt fort. Die angezeigten Rundennummern beginnen bei null.
- Insgesamt sind 211 Fortschrittsschritte à 0,2 Sekunden und 29 Pausenrunden vorgesehen: **42,2 Sekunden Enginezeit**. Netzwerkwartezeiten zählen nicht als Spielzeit; der Test dauert deshalb in echt mehrere Minuten.
- Die Bau- und Pausenwünsche stammen abwechselnd von Host und Mitspieler und werden gemeinsam eingeordnet. Normale Pause-Tasten und konkurrierende freie Baueingaben werden damit noch nicht als Spielereingaben geprüft.
- Die Kamera wird nicht automatisch bewegt. Die Baustelle entsteht an einer automatisch gewählten Stelle der vorhandenen Karte. Die Linie heißt **TF2 Coop Test Line** und kann zum Zuschauen ausgewählt werden.
- Bei einem Fehler oder einer erkannten Abweichung hält der Test an. Nicht versuchen, ihn durch Pause/Play wieder zum Laufen zu bringen. Der neue Fehlerbericht kann zusätzlich die tatsächlichen Feldtypen der betroffenen Testobjekte enthalten; ihr braucht dafür keine zweite Diagnose vorzubereiten.

Ein erfolgreicher Abschluss verlangt übereinstimmende beobachtete Zustände, verbundene Teststraßen, eine tatsächliche Kaufabbuchung, passende Linienzuordnung und mindestens einen Meter Fahrzeugbewegung über mehrere bestätigte Zeitpunkte. Das würde diesen begrenzten Versuch bestätigen, keine vollständige oder dauerhafte Synchronität der ganzen Spielwelt.

## 6. Nach Abbruch oder nach 240 Runden

1. Auf **beiden PCs** im Bautestreiter **Testbericht als ZIP …** verwenden. **Beide ZIPs** privat zur Auswertung schicken, auch wenn nur einer einen Fehler sieht. Gemeint ist der normale Testbericht, nicht der Solo-Diagnoseexport.
2. **Test beenden** klicken. Ein noch ausstehender Engineabschluss kann bis zu 30 Sekunden benötigen; das Spiel wird dadurch nicht geschlossen.
3. TF2 selbst vollständig schließen. Eure normale Partie nicht mit der Testsave überschreiben.
4. **Bisherige Installation wiederherstellen** verwenden. Testsave-Kopien, vorhandene Sicherungen und exportierte Berichte bleiben erhalten.

Für einen neuen Versuch wieder einen frischen gemeinsamen Sitzungscode und neu vorbereitete Testsave-Kopien verwenden. Eine bereits gestartete Sitzung oder eine im Messmodus gespeicherte Fortsetzung ist kein neuer Ausgangsstand.

## Erste Einrichtung, große Karte und spätere Updates

Wer noch keinen Launcher ab Alpha5.2 hat, lädt einmal das vollständige Paket: **[TFCoop-Windows.zip — neueste Version](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip)**. Die ZIP vollständig in einen eigenen Ordner, beispielsweise `C:\Games\TFCoop`, entpacken. Nicht in den Spielordner oder über einen alten Launcher entpacken. `TF2-Coop.exe`, `_internal` und `package_manifest.json` zusammenlassen. Git und Python werden auf Spieler-PCs nicht benötigt. Diese Anleitung gehört zu [Alpha5.7 / v0.5.7](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.7).

Euer bisheriger privater Ausgangsspielstand mit der **sehr großen Karte** bleibt lokal erhalten. Es muss keine neue Karte erzeugt werden. Die öffentliche ZIP enthält keinen Spielstand. Der Launcher übernimmt das passende Dateipaar normalerweise automatisch aus dem bisherigen Testlauf oder seinem lokalen Speicher.

Falls der Ausgangsspielstand fehlt, **Testspielstand übernehmen …** anklicken und aus dem alten privaten Paket `Testspielstand\initial.sav` auswählen. Die zugehörige `initial.sav.lua` muss daneben liegen. Keine inzwischen fortgesetzte Testsave als Ausgangsstand auswählen.

Später genügt derselbe Launcher: TF2 und laufende Tests schließen, Launcher neu öffnen, Updateprüfung abwarten. Nach einem Update die vorherige Installation wiederherstellen und den neuen Test über seinen Vorbereitungsknopf installieren. Wenn GitHub nicht erreichbar ist, bleibt eine vorhandene Version nutzbar; beide Spieler müssen vor dem gemeinsamen Versuch dieselbe aktuelle Version verwenden.

Private Spielstände liegen unter `%LOCALAPPDATA%\TF2StrictProbe\baseline`, Updateversionen unter `%LOCALAPPDATA%\TF2StrictProbe\updates`. Der Updater lädt Spielstände oder Berichte nicht auf GitHub hoch. Berichte können lokale Pfade und Kartendaten enthalten und sind für die private Auswertung bestimmt.

## Wenn etwas nicht klappt

| Anzeige / Problem | Nächster Schritt |
|---|---|
| Es steht noch eine ältere Version im Fenster | TF2 und Messcontroller schließen, Launcher normal neu öffnen und Updateprüfung abwarten. Bleibt das Update unerreichbar, die aktuelle ZIP oben separat entpacken. |
| Diagnose noch installiert / Vorbereitung blockiert | TF2 schließen und **Bisherige Installation wiederherstellen** verwenden; danach im Bautestreiter neu vorbereiten. |
| Wartet auf Mitspieler | Auf beiden PCs Host-IP, frischen gemeinsamen Sitzungscode, Hamachi-Verbindung und Firewallzugriff prüfen. |
| Verbunden, aber kein Spielkontakt | Startfreigabe abwarten, dann TF2 starten und die neu angezeigte Messtest-Save mit der Alpha5.7-Strict-Mod laden. |
| Testmod oder Save fehlt | Eigene Spiel-/Saveordner prüfen; die Vorbereitung muss erfolgreich beendet sein. Den genauen Dateinamen im Bautestreiter verwenden. |
| Beim Laden stehen alte Mods in der Liste | Für die ausgewählte Save **OPTIONEN AUSWÄHLEN → Mods** öffnen. Nur Alpha5.7 Strict Sync und Legacy Fahrzeuge aktivieren. |
| Unterschiedliche Testdateien / Ausgangszustände | Versionen und Modlisten vergleichen; beide wiederherstellen und mit frischem gemeinsamem Code neu vorbereiten. |
| Lua-/Native-Fehler oder Bauabbruch | Auf beiden PCs **Testbericht als ZIP …** exportieren und beide Berichte mit Fehlertext schicken. Keine erneute Solo-Diagnose nötig. |
| Berichtsexport nicht möglich | Zunächst den genauen Fehlertext schicken; vorhandene Sitzungsdateien und Sicherungen behalten. |
| Wiederherstellung blockiert | TF2 und Messcontroller vollständig beenden. Bei nachträglich veränderten installierten Dateien den Fehlertext schicken; die Sicherung bleibt erhalten. |
| Zugriff verweigert | Schreibrechte auf Spiel- und Saveordner prüfen. Falls dort Administratorrechte nötig sind, den Launcher nach dem Schließen mit diesen Rechten neu öffnen. |

Der native Bautest unterstützt den geprüften Windows-Spielbuild 35924. Bei einem abweichenden Build den Fehlertext schicken, statt DLLs manuell auszutauschen. Nach einem Launcherabsturz das Programm erneut öffnen und bei geschlossenem TF2 die Wiederherstellung verwenden. Sicherungen nicht von Hand löschen.
