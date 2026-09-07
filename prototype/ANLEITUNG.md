# TF2-Koop Alpha5.11-1x-Test — Anleitung für beide Spieler

**Der neue Versuch ist vorbereitet:** Zuerst baut der Test wie bisher die gemeinsame Szene auf. Danach folgen zwölf kurze Fahrtabschnitte mit 1x als Ziel und absichtlichen Wartezeiten. Ihr könnt dabei zuschauen, ob sich das Fahrzeug gleichmäßig bewegt. Eine weitere Solo-Diagnose ist nicht nötig.

**Alpha5.11 verwendet dasselbe private Savepaar wie Alpha5.9.** Die bisherige sehr große Karte und die bereits ausgewählten Testmods bleiben erhalten. Wer das Paar schon übernommen hat, braucht keinen erneuten Import. Nur die Basis aus Paketen vor Alpha5.9 passt nicht.

Alpha5.10 bestand bereits den echten Aufbau mit zwölf Befehlen und 240 Schritten in zwei nacheinander gestarteten TF2-Prozessen auf einem PC. Alle gemessenen Ergebnisse stimmten überein. **Die neuen Fahrtabschnitte aus Alpha5.11 sind bisher ohne TF2 geprüft; ihr echter gemeinsamer Versuch steht noch aus.** Die Messung bestätigt keine vollständige Synchronität der ganzen Spielwelt. Freies Bauen, Cursor und normale gemeinsame Pause-Tasten sind noch nicht freigeschaltet. Einzelheiten stehen im [Prüfstand](https://github.com/TastierPizza-code/TFCoop/blob/main/prototype/VERIFICATION.md).

## 1. Beide aktualisieren und die vorherige Installation zurücksetzen

1. Den laufenden Test beenden, **TF2 vollständig schließen** und den bisherigen Launcher schließen. Ein Versionswechsel wartet, solange TF2 oder ein Messcontroller läuft.
2. Den vorhandenen Launcher normal neu öffnen und die Updateprüfung abwarten. Ab Alpha5.2 lädt er neuere GitHub-Releases automatisch. Auf beiden PCs muss oben **Alpha5.11-1x-Test** stehen. Das Programm aktualisiert sich; ein bereits übernommenes Alpha5.9-Savepaar bleibt gültig.
3. Auf beiden PCs **Bisherige Installation wiederherstellen** verwenden. Das gilt insbesondere für eine noch installierte **API-Diagnosemod**. Der Programm-Download allein ersetzt die installierten Testdateien nicht.
4. Oben unter **Ordner prüfen** den eigenen **TF2-Installationsordner** und **Steam-Saveordner** prüfen. Übliche Pfade sind `…\steamapps\common\Transport Fever 2` und `…\Steam\userdata\<Kontonummer>\1066780\local\save`.
5. **Nur falls die saubere Basis aus Alpha5.9 noch fehlt:** Das private Savepaar entpacken: `Testspielstand/initial.sav` und `Testspielstand/initial.sav.lua` müssen unverändert nebeneinanderliegen. Beide Dateien einmal privat an den Freund weitergeben. Auf jedem PC ohne diese Basis **Testspielstand übernehmen …** anklicken und diese `initial.sav` auswählen. Der Launcher prüft beide Dateien und speichert sie lokal. Wer sie bereits übernommen hat, überspringt diesen Schritt. Nichts von Hand in den TF2-Ordner kopieren.
6. Im ersten, standardmäßig geöffneten Reiter **Aufbau + 1x-Test (experimentell)** bleiben. **API-Diagnose allein** ist als zweiter Reiter für gezielte spätere Untersuchungen vorhanden und wird für diesen Versuch nicht verwendet.
7. Bei Hamachi beide PCs in dasselbe Hamachi-Netz verbinden. Ihr verwendet die **IPv4-Adresse des Hosts**, normalerweise eine Adresse mit `25.` am Anfang. Im selben lokalen Netzwerk genügt stattdessen die LAN-IPv4 des Hosts.

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
4. Unter **Aktivierte Mods** stehen bereits **TF2 Strict Sync - automatischer Bautest (Alpha5.11)** und **Legacy Fahrzeuge**. Die Modliste muss nicht jedes Mal umgestellt werden. Stehen dort alte Koop-Mods, wurde eine alte Save gewählt: Zurück zur Liste und den exakten neuen Namen aus dem Launcher auswählen. Keine weiteren Mods einschalten.
5. Die Testsave laden. Wenn einer früher fertig ist, bleibt seine Spielzeit gehalten, bis beide geladen haben und der gemeinsame Startvergleich passt.

## 5. Aufbau, Wartezeiten und Fahrt beobachten

- **Nur zuschauen; die Kamera dürft ihr bewegen.** Nicht selbst bauen, kaufen, Linien bearbeiten, pausieren oder die Geschwindigkeit umschalten. Alle Bau-, Fahr- und Pausenwünsche kommen vom Test.
- Zuerst folgen **240 Aufbaurunden**. Die ersten neun richten die Szene bei gehaltener Simulation ein; ab Runde 9 fährt das Fahrzeug. Von Runde 80 bis 99 pausiert der Test, Runde 100 setzt die Fahrt fort. Rundennummern beginnen bei null.
- Die 211 Fortschrittsschritte und 29 Pausenschritte ergeben zusammen 42,2 Sekunden Enginezeit. **Bei 240 nicht beenden:** Danach wechselt die Anzeige automatisch zum 1x-/Warteversuch.
- Es folgen **zwölf Fahrtabschnitte mit jeweils fünf Sekunden Spielzeit**. Die ersten drei haben keine zusätzliche Wartezeit. Vor den nächsten sechs wartet abwechselnd ein PC absichtlich zwischen 0,25 und 3 Sekunden. Die letzten drei haben wieder keine Zusatzwartezeit. Beide bestätigen jeden gemeinsamen Übergang.
- Die Stopps vor Fahrtabschnitten sind beabsichtigt. Achtet innerhalb der Abschnitte darauf, ob das Fahrzeug gleichmäßig fährt oder sichtbar springt. Vergleicht besonders die letzten drei Abschnitte mit den ersten drei. Kurzes Stocken beim Übergang und Stocken während der Fahrt sind für die Auswertung unterschiedliche Beobachtungen.
- Die Kamera wird nicht automatisch bewegt. Die Linie heißt **TF2 Coop Test Line**; über sie könnt ihr das Fahrzeug auswählen und seine Fahrt verfolgen. Schickt später kurz dazu, ob und in welchem Abschnitt ihr Ruckeln gesehen habt. Ein Screenshot zeigt die Ergebnisanzeige, aber nicht die Gleichmäßigkeit der Bewegung.
- Bei einem Fehler hält der Test an. Nicht durch Pause/Play versuchen weiterzuspielen. Der normale Testbericht enthält die Diagnose; keine zweite Solo-Diagnose vorbereiten.

Die Fahrtabschnitte verwenden ausschließlich **1x als Ziel**. Vor und nach jedem Abschnitt werden die erfassten Weltzustände verglichen; währenddessen wird die native Spielzeit nach jeder Freigabe kontrolliert. Die sichtbare Bewegung wird nicht automatisch gemessen. Die absichtlichen Wartezeiten sind keine Messung eurer tatsächlichen Netzwerk-Latenz.

Der Abschluss zeigt getrennt, ob die Messwerte verglichen wurden und ob das **1x-Ziel in den Fahrtabschnitten** erreicht wurde. Ein abgeschlossener Zustandsvergleich kann mit einem noch nicht erreichten Tempoziel zusammenfallen. Beim Host bezieht sich **Beide PCs** auf beide Tempoergebnisse; beim Mitspieler bewertet **Tempo auf deinem PC** nur dessen lokale Messung. Deshalb brauchen wir beide Berichte. Eine positive Tempoanzeige bestätigt weder die gerenderten Bilder noch durchgängiges 1x über die gemeinsamen Übergänge hinweg.

## 6. Nach Abbruch oder nach allen zwölf Fahrtabschnitten

1. Auf **beiden PCs** im Bautestreiter **Testbericht als ZIP …** verwenden. **Beide ZIPs** privat zur Auswertung schicken, auch wenn nur einer einen Fehler sieht. Gemeint ist der normale Testbericht, nicht der Solo-Diagnoseexport.
2. **Test beenden** klicken. Ein bereits laufender Engineauftrag wird noch beendet oder läuft in seine Zeitgrenze. Das Spiel wird dadurch nicht geschlossen.
3. TF2 selbst vollständig schließen. Eure normale Partie nicht mit der Testsave überschreiben.
4. **Bisherige Installation wiederherstellen** verwenden. Testsave-Kopien, vorhandene Sicherungen und exportierte Berichte bleiben erhalten.

Für einen neuen Versuch wieder einen frischen gemeinsamen Sitzungscode und neu vorbereitete Testsave-Kopien verwenden. Eine bereits gestartete Sitzung oder eine im Messmodus gespeicherte Fortsetzung ist kein neuer Ausgangsstand.

## Erste Einrichtung, große Karte und spätere Updates

Wer noch keinen Launcher ab Alpha5.2 hat, lädt einmal das vollständige Paket: **[TFCoop-Windows.zip — neueste Version](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip)**. Die ZIP vollständig in einen eigenen Ordner, beispielsweise `C:\Games\TFCoop`, entpacken. Nicht in den Spielordner oder über einen alten Launcher entpacken. `TF2-Coop.exe`, `_internal` und `package_manifest.json` zusammenlassen. Git und Python werden auf Spieler-PCs nicht benötigt. Diese Anleitung gehört zu [Alpha5.11 / v0.5.11](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.11).

Die **bisherige sehr große Karte** wird weiterverwendet; ihr müsst keine neue Karte erzeugen. Seit Alpha5.9 wird ein **sauberes Savepaar** dieser Karte verwendet; Alpha5.11 verwendet es unverändert weiter. Die öffentliche Programm-ZIP enthält keinen Spielstand. Die Basis aus Paketen vor Alpha5.9 hat andere Prüfsummen und ersetzt dieses Paar nicht.

Falls noch nicht übernommen, **Testspielstand übernehmen …** anklicken und die seit Alpha5.9 bereitgestellte `Testspielstand/initial.sav` auswählen. Die zugehörige `initial.sav.lua` muss danebenliegen. Beide Dateien unverändert privat weitergeben; keine inzwischen fortgesetzte Testsave verwenden. Nach erfolgreicher Übernahme bleibt das geprüfte Paar lokal erhalten und wird bei weiteren Programmupdates mit derselben Basis wiederverwendet. Für Alpha5.11 ist kein erneuter Import nötig.

Später genügt derselbe Launcher: TF2 und laufende Tests schließen, Launcher neu öffnen, Updateprüfung abwarten. Nach einem Update die vorherige Installation wiederherstellen und den neuen Test über seinen Vorbereitungsknopf installieren. Wenn GitHub nicht erreichbar ist, bleibt eine vorhandene Version nutzbar; beide Spieler müssen vor dem gemeinsamen Versuch dieselbe aktuelle Version verwenden.

Private Spielstände liegen unter `%LOCALAPPDATA%\TF2StrictProbe\baseline`, Updateversionen unter `%LOCALAPPDATA%\TF2StrictProbe\updates`. Der Updater lädt Spielstände oder Berichte nicht auf GitHub hoch. Berichte können lokale Pfade und Kartendaten enthalten und sind für die private Auswertung bestimmt.

## Wenn etwas nicht klappt

| Anzeige / Problem | Nächster Schritt |
|---|---|
| Es steht noch eine ältere Version im Fenster | TF2 und Messcontroller schließen, Launcher normal neu öffnen und Updateprüfung abwarten. Bleibt das Update unerreichbar, die aktuelle ZIP oben separat entpacken. |
| Diagnose noch installiert / Vorbereitung blockiert | TF2 schließen und **Bisherige Installation wiederherstellen** verwenden; danach im Bautestreiter neu vorbereiten. |
| Wartet auf Mitspieler | Auf beiden PCs Host-IP, frischen gemeinsamen Sitzungscode, Hamachi-Verbindung und Firewallzugriff prüfen. |
| Verbunden, aber kein Spielkontakt | Startfreigabe abwarten, dann TF2 starten und die neu angezeigte Messtest-Save mit der Alpha5.11-Strict-Mod laden. |
| Testmod oder Save fehlt | Eigene Spiel-/Saveordner prüfen; die Vorbereitung muss erfolgreich beendet sein. Den genauen Dateinamen im Bautestreiter verwenden. |
| Beim Laden stehen alte Mods in der Liste | Eine alte Save ist ausgewählt. Zurück zur Ladeliste und den exakten neuen Namen aus dem Launcher wählen. Die neue Basis enthält bereits Strict Sync und Legacy Fahrzeuge. |
| Ausgangsspielstand fehlt / Prüfsummen passen nicht | Das seit Alpha5.9 bereitgestellte private Paar vollständig entpacken und seine `initial.sav` über **Testspielstand übernehmen …** auswählen. Die Basis vor Alpha5.9 passt nicht mehr; die zugehörige `.sav.lua` muss danebenliegen. |
| Unterschiedliche Testdateien / Ausgangszustände | Versionen und Modlisten vergleichen; beide wiederherstellen und mit frischem gemeinsamem Code neu vorbereiten. |
| Lua-/Native-Fehler oder Bauabbruch | Auf beiden PCs **Testbericht als ZIP …** exportieren und beide Berichte mit Fehlertext schicken. Keine erneute Solo-Diagnose nötig. |
| Berichtsexport nicht möglich | Zunächst den genauen Fehlertext schicken; vorhandene Sitzungsdateien und Sicherungen behalten. |
| Wiederherstellung blockiert | TF2 und Messcontroller vollständig beenden. Bei nachträglich veränderten installierten Dateien den Fehlertext schicken; die Sicherung bleibt erhalten. |
| Zugriff verweigert | Schreibrechte auf Spiel- und Saveordner prüfen. Falls dort Administratorrechte nötig sind, den Launcher nach dem Schließen mit diesen Rechten neu öffnen. |

Der native Bautest unterstützt den geprüften Windows-Spielbuild 35924. Bei einem abweichenden Build den Fehlertext schicken, statt DLLs manuell auszutauschen. Nach einem Launcherabsturz das Programm erneut öffnen und bei geschlossenem TF2 die Wiederherstellung verwenden. Sicherungen nicht von Hand löschen.
