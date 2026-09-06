# TF2-Koop Alpha5.4-Diagnose — Anleitung

**Der nächste Schritt geht allein auf deinem PC. Dein Freund muss dafür nichts
starten und keine ZIP schicken.** Alpha5.4 liest die tatsächlich verfügbaren
TF2-Daten aus einer frischen Kopie eures bisherigen Testspielstands. Dafür sind
keine Verbindung, Host-IP, Sitzungscode oder Hamachi erforderlich.

Im letzten Alpha5.3-Bautest wurde die Straße gebaut; danach erschien
`invalid finite build value`. Welches Datenfeld das verursacht, ist noch nicht
bekannt. **Alpha5.4 ist eine Diagnoseversion, kein bestätigter Fix für diesen
Abbruch und kein Nachweis für deterministischen Multiplayer.** Der gemeinsame
Bautest bleibt im Reiter **Bautest (experimentell)** erhalten.

## 1. API-Diagnose allein

1. Den bisherigen Test beenden, **TF2 vollständig schließen** und den alten
   Launcher schließen. Während TF2 oder ein Messcontroller läuft, wird der
   Versionswechsel verschoben.
2. Den vorhandenen Launcher normal neu öffnen und die Updateprüfung abwarten.
   Ab Alpha5.2 lädt er neuere GitHub-Releases automatisch. Oben muss
   **Alpha5.4-Diagnose** stehen. Du musst dafür keine neue ZIP von Hand laden.
3. Oben unter **Ordner prüfen** den **TF2-Installationsordner** und
   **Steam-Saveordner** prüfen, dann den ersten Reiter **API-Diagnose allein**
   verwenden. Es sind deine eigenen lokalen Ordner:
   `…\steamapps\common\Transport Fever 2` und
   `…\Steam\userdata\<Kontonummer>\1066780\local\save`.
4. **Diagnose vorbereiten** klicken und die Fertigmeldung abwarten. Die
   Vorbereitung setzt eine vorhandene Strict-Sync-Testinstallation sicher
   zurück, installiert die Diagnosemod und legt eine neue, geprüfte Save-Kopie
   an. Es wird kein gemeinsamer Messcontroller gestartet.
5. Den angezeigten Namen **`TF2-API-Diagnose-….sav`** merken und den Launcher
   offen lassen. TF2 anschließend **selbst ganz normal über Steam starten**.
   Dafür nicht die Verbindungs- oder Startknöpfe des Bautests verwenden.
6. In TF2 **Spiel laden** öffnen und genau die angezeigte Diagnose-Save wählen.
   Nicht einfach **Fortsetzen** drücken. Rechts über **Aktivierte Mods** auf
   **OPTIONEN AUSWÄHLEN** klicken, dann den Reiter **Mods** öffnen.
7. Für diese Save nur **TF2 API-Diagnose (Alpha5.4)** und **Legacy Fahrzeuge**
   aktivieren. Die bisherigen Koop-Mods, **MP Lockstep**, **MP Bridge** und
   **TF2 Strict Sync** deaktivieren; keine zusätzlichen Mods einschalten.
   Die Modauswahl der Save ist maßgeblich, auch wenn bei **Freies Spiel** bereits
   andere Mods ausgewählt sind.
8. Die Diagnose-Save laden und die Karte **etwa zehn Sekunden** geöffnet lassen.
   Die Kamera darfst du bewegen. Bitte nichts bauen, kaufen, Linien bearbeiten
   oder die Geschwindigkeit umschalten. Die Diagnose sendet selbst keine Bau-,
   Pause- oder Weiterlaufbefehle; die normale Simulation kann weiterlaufen.
9. Im Diagnoseabschnitt des Launchers **Diagnosebericht als ZIP …** verwenden
   und **diese eine ZIP von deinem PC** zur Auswertung schicken. Ein Bericht
   deines Freundes ist für diesen Schritt nicht nötig. Bei einer Fehlermeldung
   ebenfalls den Export versuchen und den Fehlertext mitgeben. Falls der
   Export nicht möglich ist, genügt zunächst dessen Fehlertext.
10. TF2 vollständig schließen. Anschließend **Bisherige Installation
    wiederherstellen** verwenden. Deine normale Partie nicht mit der
    Diagnose-Save überschreiben.

Die Diagnose liest vorhandene Objekte der Karte und prüft getrennt davon,
welche Werte sich mit API-Konstruktoren erzeugen und lesen lassen. Ein erfolgreich
erzeugtes Probeobjekt beweist nichts über ein tatsächlich vorhandenes Fahrzeug.
Fehlende Livefahrzeuge, Depots oder andere Objektarten werden als fehlende
Abdeckung ausgewiesen, nicht als erfolgreiche Prüfung. Die Diagnose prüft
keine gemeinsame Pause und keinen synchronen Bauablauf.

## 2. Erste Einrichtung oder fehlender Testspielstand

Wer noch keinen Launcher ab Alpha5.2 hat, lädt einmal das vollständige Paket:
**[TFCoop-Windows.zip — neueste Version](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip)**.
Die ZIP vollständig in einen eigenen Ordner, beispielsweise `C:\Games\TFCoop`,
entpacken. Nicht in den Spielordner oder über einen alten Launcher entpacken.
`TF2-Coop.exe`, `_internal` und `package_manifest.json` zusammenlassen, dann
`TF2-Coop.exe` öffnen. Git und Python werden auf Spieler-PCs nicht benötigt.

Der bisherige private Ausgangsspielstand mit der **sehr großen Karte** bleibt
lokal erhalten. Die öffentliche ZIP enthält keinen Spielstand. Der Launcher
übernimmt das passende Dateipaar normalerweise automatisch aus dem letzten
vorbereiteten Testlauf und verwahrt eine geprüfte Kopie für spätere Updates.

Wenn **Gemeinsamer Testspielstand ist lokal verfügbar** angezeigt wird, ist
diese Übernahme erledigt. Falls der Ausgangsspielstand fehlt, **Testspielstand
übernehmen …** anklicken und aus dem alten privaten Paket
`Testspielstand\initial.sav` auswählen. Die zugehörige `initial.sav.lua` muss
daneben liegen. Keine normale Partie oder inzwischen fortgesetzte Testsave als
Ausgangsstand auswählen. Anschließend oben **Diagnose vorbereiten** verwenden.

Für den gemeinsamen nativen Bautest prüft der Launcher den Spielbuild; er
unterstützt den geprüften Windows-Build 35924. Bei einer Build-Fehlermeldung
den Fehlertext schicken, statt Dateien manuell auszutauschen.

## 3. Was später automatisch aktualisiert wird

Ab Alpha5.2 genügt künftig derselbe Launcher oder eine Verknüpfung darauf:
TF2 und laufende Tests schließen, Launcher neu öffnen, Updateprüfung abwarten.
Er lädt veröffentlichte Programmversionen aus **TastierPizza-code/TFCoop**,
prüft ihre Dateien und öffnet die aktualisierte Version. Der Download allein
installiert noch keine neue Mod in TF2; dafür dient der jeweilige
Vorbereitungsknopf im Launcher.

Wenn GitHub nicht erreichbar ist, bleibt eine vorhandene Version nutzbar.
Eine bereits vollständig geladene und geprüfte neuere Version kann aus dem
lokalen Speicher starten. Solange oben eine ältere Version steht, ist der
hier beschriebene neue Diagnoseablauf noch nicht verfügbar.

Private Spielstände liegen unter `%LOCALAPPDATA%\TF2StrictProbe\baseline`,
Updateversionen unter `%LOCALAPPDATA%\TF2StrictProbe\updates`.
**Spielstände und Diagnoseberichte bleiben privat.** Der Updater lädt sie
nicht auf GitHub hoch. Berichte können lokale Pfade und Daten aus der Karte
enthalten; sie gehören zur privaten Auswertung, nicht in ein öffentliches
GitHub-Issue oder Release.

## 4. Gemeinsamer Bautest — experimentelle Option

**Den Bautest jetzt nicht erneut als nächsten Diagnoseschritt ausführen.**
Zuerst den Solo-Bericht aus Abschnitt 1 auswerten. Die folgenden Schritte
dokumentieren die weiterhin vorhandene Option für einen späteren Versuch.
Freies gleichzeitiges Bauen und Spielercursor sind darin noch nicht aktiv.

1. Auf beiden PCs TF2 und vorherige Tests schließen. Vorhandene Diagnose- oder
   Testinstallationen mit **Bisherige Installation wiederherstellen** zurücksetzen.
   Beide benötigen dieselbe aktuelle Programmversion und den passenden lokalen
   Ausgangsspielstand.
2. Für zwei PCs Hamachi verbinden oder dasselbe lokale Netzwerk verwenden.
   Im Reiter **Bautest (experimentell)** wählt der Host **Ich bin Host**, der Freund
   **Ich trete meinem Freund bei**. Auf beiden PCs dieselbe **IP des Hosts
   (Hamachi/LAN)** eintragen. Für zwei PCs nicht `127.0.0.1` verwenden.
3. Der Host erzeugt mit **Neu** einen frischen **Gemeinsamen Sitzungscode**,
   kopiert ihn und schickt Code und Host-IP an den Freund. Der Freund ersetzt
   seinen eigenen Code vollständig durch diesen Code.
4. Beide klicken **Test vorbereiten und installieren**. Jeder erhält eine
   frische `TF2-Koop-Messtest-….sav`. Unterschiedliche zufällige Dateiendungen
   sind korrekt; die Ausgangsinhalte werden geprüft.
5. Beide klicken **Verbinden & Test bereitstellen** und warten auf
   **Mitspieler: verbunden · gleiche Testdateien** sowie die Startfreigabe.
   Diese Meldung bestätigt zunächst das Paket, noch nicht die geladene Welt.
6. Nach der Freigabe innerhalb von zwei Minuten **TF2 über Steam starten**
   anklicken oder TF2 selbst über Steam starten. Für das anschließende Laden
   wartet der gesamte Sitzungsstart bis zu zehn Minuten. Launcher offen lassen.
7. Über **Spiel laden → OPTIONEN AUSWÄHLEN → Mods** die neu angezeigte
   `TF2-Koop-Messtest-….sav` mit der im Bautestabschnitt genannten
   **TF2 Strict Sync**-Mod und **Legacy Fahrzeuge** laden. Diagnosemod und alte
   Koop-Mods deaktivieren. Nicht die `TF2-API-Diagnose-….sav` auswählen.
8. Während des automatischen Tests nichts bauen, kaufen, Linien bearbeiten,
   pausieren oder die Geschwindigkeit ändern. Anschauen und Kamera bewegen
   ist möglich. Bei Abschluss oder Abbruch auf beiden PCs **Testbericht als
   ZIP …** exportieren, **Test beenden**, TF2 schließen und danach die bisherige
   Installation wiederherstellen. Für diesen gemeinsamen Versuch werden beide
   Berichte benötigt.

Der Bautest umfasst 240 Runden für Straße, Depot, zwei Haltestellen, Fahrzeugkauf,
Linienzuordnung, Abfahrt und gesteuerte Pausen. Die Pausenwünsche stammen jeweils
von einem Teilnehmer und werden gemeinsam freigegeben. Die normale Pause-Taste
im Spiel und gleichzeitige konkurrierende Bauwünsche werden damit noch nicht
als gemeinsame Spielereingaben geprüft. Ein erfolgreicher Abschluss würde nur
die ausdrücklich beobachteten Zustände dieses Versuchs bestätigen, keine
vollständige oder dauerhafte Synchronität der Welt.

Nur für den gemeinsamen Bautest werden TCP 34207 und TCP 34208 verwendet.
Bei einer Windows-Firewallabfrage den Launcher im verwendeten LAN-/Hamachi-Netz
erreichbar machen. Für die Solo-Diagnose ist keine Netzwerkverbindung nötig.

## Wenn etwas nicht klappt

| Anzeige / Problem | Nächster Schritt |
|---|---|
| Es steht noch eine ältere Version im Fenster | TF2 und Messcontroller schließen, Launcher normal neu öffnen und Updateprüfung abwarten. Falls das Update nicht erreichbar bleibt, die aktuelle ZIP über den Link oben separat entpacken. |
| Diagnosemod fehlt | TF2-Installationsordner prüfen; **Diagnose vorbereiten** muss erfolgreich abgeschlossen sein. Keine alten DLLs manuell darüberkopieren. |
| Diagnose-Save fehlt | Den eigenen Steam-Saveordner prüfen und den genauen importierten Dateinamen aus dem Diagnoseabschnitt suchen. |
| Beim Laden stehen alte Mods in der Liste | Beim ausgewählten Spielstand **OPTIONEN AUSWÄHLEN → Mods** öffnen. Die Auswahl bei **Freies Spiel** ändert die gespeicherte Modliste dieser Save nicht. |
| Privater Testspielstand fehlt / Prüfsummen stimmen nicht | Die ursprüngliche `Testspielstand\initial.sav` aus einem alten privaten Paket über **Testspielstand übernehmen …** auswählen; die `.sav.lua` muss daneben liegen. |
| Nach dem Laden keine Diagnose oder eine Fehlermeldung | Gewählte Save und Modliste prüfen, **Diagnosebericht als ZIP …** exportieren und den Fehlertext mitgeben. Nicht den gemeinsamen Bautest als Ersatz starten. |
| Wiederherstellung blockiert | TF2 und Messcontroller vollständig beenden. Bei nachträglich geänderten installierten Dateien den Fehlertext schicken; die Sicherung bleibt erhalten. |
| Zugriff verweigert | Schreibrechte auf Spiel- und Saveordner prüfen. Falls dort Administratorrechte nötig sind, den Launcher nach dem Schließen mit diesen Rechten neu öffnen. |

Nach einem Launcherabsturz das Programm erneut öffnen und bei geschlossenem
TF2 die Wiederherstellung verwenden. Vorhandene Sicherungen nicht von Hand
löschen. Testsave-Kopien und exportierte Berichte bleiben nach der
Wiederherstellung erhalten.
