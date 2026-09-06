# TF2-Koop Alpha5.3-Bautest — Anleitung für beide Spieler

**Ihr habt schon Alpha5.2?** Auf beiden PCs den Test beenden, TF2 vollständig
schließen und den vorhandenen Launcher normal neu öffnen. Die Updateprüfung
lädt **Alpha5.3** und öffnet den aktualisierten Launcher automatisch. Sobald oben
**Alpha5.3-Bautest** steht, **Bisherige Installation wiederherstellen** verwenden
und mit einem neuen gemeinsamen Sitzungscode neu vorbereiten. Ihr braucht
dafür keine neue ZIP von Hand herunterzuladen oder weiterzuschicken.

**Bei der ersten Einrichtung** laden beide einmal das vollständige Windows-Paket herunter:
**[TFCoop-Windows.zip — neueste Version](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip)**.
Ab Alpha5.2 prüft der Launcher beim Start selbst auf neue GitHub-Releases,
lädt eine neuere Version herunter, prüft die Dateien und startet den aktualisierten
Launcher. Ihr braucht weder Git noch Python und müsst neue ZIPs nicht mehr
regelmäßig untereinander verschicken. Die Erstversion dieses Updatewegs ist
[Alpha5.2 / v0.5.2](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.2).
Diese Anleitung gehört zu [Alpha5.3 / v0.5.3](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.3).

**Beim Wechsel von Alpha5.1 oder älter:** Auf beiden PCs den Test beenden, TF2
vollständig schließen und **Bisherige Installation wiederherstellen** verwenden.
Das geht auch im neuen Launcher. Das neue Paket separat entpacken; den alten
Paketordner zunächst behalten. Der Launcher übernimmt den passenden privaten
Ausgangsspielstand normalerweise automatisch aus eurem letzten vorbereiteten Testlauf.

**Neu in Alpha5.3:** Der letzte Test baute die Straße und brach anschließend
beim Lesen ihrer Konstruktionstransformation ab: `bad argument #1 to 'type' (value expected)`.
Diese Version korrigiert den Umgang mit einem dort nicht verfügbaren Datenfeld,
damit der vorgesehene alternative Leseweg genutzt werden kann. Die Korrektur
und der weitere Bauablauf müssen im echten Zwei-PC-Test noch bestätigt werden.

**Was diese Version macht:** Sie verbindet euch über LAN/Hamachi und führt einen
automatischen Bautest **in euren beiden Spielen** aus: eine kleine Straße, ein
Depot, zwei Haltestellen, ein gekauftes Fahrzeug und dessen Zuordnung zu einer
Linie. Anschließend prüft er Abfahrt, Bewegung, Pause und gemeinsame Firmenwerte.
Ihr müsst dafür nichts von Hand bauen oder Fahrzeuge vorbereiten.
Euer bisheriger privater Ausgangsspielstand mit der **sehr großen Karte** bleibt
erhalten. Die öffentliche ZIP enthält keinen Spielstand; der Launcher prüft und
verwahrt das passende lokale Dateipaar für weitere Updates. Die Baustelle wird
auf dieser Karte automatisch gesucht; keine neue Map erzeugen.
Freies gemeinsames Bauen und Spielercursor sind in diesem Test noch nicht aktiv.
Der neue Bauablauf ist automatisiert mit Ersatzengines geprüft; euer Durchlauf
ist die Prüfung der tatsächlichen Bau- und Fahrzeugfunktionen in TF2.

## 1. Das machen beide zuerst

1. Den bisherigen Test beenden, Transport Fever 2 vollständig schließen und den
   bisherigen Launcher schließen. Der Versionswechsel wartet, solange TF2 oder ein Messcontroller läuft.
2. **Mit vorhandenem Alpha5.2-Launcher:** Den bisherigen Programmordner weiterverwenden;
   nichts neu herunterladen oder entpacken. **Bei erster Einrichtung:** Die ZIP
   jeweils vollständig in einen eigenen Ordner entpacken, beispielsweise
   `C:\Games\TFCoop`. **Nicht in den Spielordner und nicht über den alten Launcher
   entpacken.** `TF2-Coop.exe`, `_internal` und `package_manifest.json` zusammenlassen.
   Im neuen öffentlichen Paket gibt es absichtlich keinen Ordner `Testspielstand`.
3. Bei Hamachi beide PCs in dasselbe Hamachi-Netz verbinden. Ihr verwendet die
   **IPv4-Adresse des Hosts**, normalerweise eine Adresse mit `25.` am Anfang.
   Im selben lokalen Netzwerk geht stattdessen die LAN-IP des Hosts.
4. `TF2-Coop.exe` starten und die Updateprüfung abwarten.
   Falls eine neuere Version vorliegt, öffnet sich der aktualisierte Launcher automatisch.
   Oben muss **Alpha5.3-Bautest** stehen. Dann, falls noch ein vorheriger Test
   installiert ist, **Bisherige Installation wiederherstellen** verwenden.
   Ihr könnt künftig dieselbe EXE oder eine Verknüpfung darauf verwenden.
   Der alte Alpha5.1-Launcher hat diese Updatefunktion noch nicht.
5. Den **TF2-Installationsordner** prüfen. Jeder wählt seine eigene Steam-Installation
   nach dem Muster `…\steamapps\common\Transport Fever 2`.
6. Den **Steam-Saveordner** prüfen. Jeder wählt seinen eigenen Ordner nach dem Muster
   `…\Steam\userdata\<Kontonummer>\1066780\local\save`.
   Der Launcher trägt ihn automatisch ein, wenn er genau einen findet.
7. Bei **Gemeinsamer Testspielstand ist lokal verfügbar** ist die Übernahme fertig.
   Falls der Launcher keinen passenden Spielstand findet, **Testspielstand übernehmen …**
   anklicken und im alten privaten Paket `Testspielstand\initial.sav` auswählen.
   Die dazugehörige `initial.sav.lua` muss im selben Ordner liegen. Der Launcher
   prüft beide Dateien und kopiert sie in seinen lokalen Speicher. Eure normale
   Partie oder einen inzwischen fortgesetzten Testsave hier nicht auswählen.

Der Spielbuild wird automatisch geprüft; dieser Versuch unterstützt den geprüften
Windows-Build 35924. Bei einem abweichenden Build zeigt der Launcher einen Fehler.
Dann den Fehlertext schicken, statt Dateien manuell auszutauschen.

## 2. Du als Host

1. **Ich bin Host** auswählen.
2. In **IP des Hosts (Hamachi/LAN)** deine eigene Hamachi- oder LAN-IPv4 eintragen.
   Nicht die Adresse deines Freundes und für zwei PCs nicht `127.0.0.1` verwenden.
3. Für diesen neuen Versuch neben **Gemeinsamer Sitzungscode** auf **Neu** und
   anschließend auf **Kopieren** klicken. Deinem Freund
   die Host-IP und diesen vollständigen Code schicken.
4. **Test vorbereiten und installieren** klicken und die Fertigmeldung abwarten.
   Der Launcher sichert die zuvor vorhandenen Dateien, installiert den Messmodus
   und importiert eine frische Kopie des lokal verwahrten Ausgangsspielstands in deinen Saveordner.
5. Den angezeigten Namen `TF2-Koop-Messtest-….sav` merken. Die zufällige Endung
   darf bei deinem Freund anders sein; der Inhalt der Kopie ist derselbe.
6. Wenn dein Freund ebenfalls vorbereitet hat, **Verbinden & Test bereitstellen** klicken.

## 3. Dein Freund als Mitspieler

1. **Ich trete meinem Freund bei** auswählen.
2. In **IP des Hosts (Hamachi/LAN)** die vom Host erhaltene IP eintragen.
3. Den angezeigten Sitzungscode vollständig durch den Code des Hosts ersetzen.
4. **Test vorbereiten und installieren** klicken. Auch hier wird eine eigene
   Kopie des lokal verwahrten Testspielstands automatisch importiert — beide Dateien,
   `.sav` und `.sav.lua`. Nichts davon muss manuell in einen Spielordner kopiert werden.
5. **Verbinden & Test bereitstellen** klicken.

Bei einer Windows-Firewallabfrage muss der neue Launcher im verwendeten
LAN-/Hamachi-Netz erreichbar sein. Verwendet werden TCP 34207 für den Test und
TCP 34208 für den Verbindungsstatus. Im Hamachi-Test ist keine Routerfreigabe vorgesehen.

## 4. Das machen wieder beide

1. Im Launcher auf **Mitspieler: verbunden · gleiche Testdateien** und die
   Startmeldung warten. Die Verbindung prüft zunächst das Paket; die geladene
   Spielwelt wird erst später verglichen.
2. Sobald freigegeben, **TF2 über Steam starten** klicken. Alternativ selbst in
   Steam starten. **Innerhalb von zwei Minuten nach der Startmeldung starten.**
   Für das anschließende Laden bleibt Zeit; der gesamte Sitzungsstart wartet bis
   zu zehn Minuten. Den Launcher offen lassen.
3. Im TF2-Hauptmenü **Spiel laden** verwenden und ausdrücklich die im Launcher
   angezeigte `TF2-Koop-Messtest-….sav` auswählen. Nicht einfach **Fortsetzen**
   drücken: Das könnte eure alte Partie laden.
4. Vor dem Laden beim ausgewählten Spielstand die **Optionen** öffnen und zum
   Reiter **Mods** wechseln. Die offizielle englische Bezeichnung des Knopfs ist
   **SELECT OPTIONS**. Dort die Mod
   **TF2 Strict Sync - automatischer Bautest (Alpha5.3)** aktivieren.
   Der Knopf **OPTIONEN AUSWÄHLEN** steht rechts direkt über der Liste
   **Aktivierte Mods**, neben **GRUNDOPTIONEN**.
5. Für diesen Test die bisherigen Koop-Mods deaktivieren, insbesondere
   **TF2 Co-op — gemeinsame Planung (Prototyp)**, **MP Lockstep** und, falls vorhanden,
   **MP Bridge**. Keine zusätzlichen Mods einschalten. Die bisherigen Moddateien
   werden nicht gelöscht; hier geht es um die Aktivierung für diese Testkopie.
   **Legacy Fahrzeuge** bleibt auf beiden PCs aktiviert, wie im Ausgangsspielstand.
6. Den gewählten Testspielstand laden. Wenn einer schneller fertig ist, bleibt
   seine Spielzeit gehalten, bis beide geladen haben und der Startvergleich passt.

TF2 aktiviert Mods für einen ausgewählten Spielstand über diesen Ladedialog.
Siehe dazu die [offizielle Mod-Anleitung](https://www.transportfever2.com/wiki/doku.php?id=gamemanual%3Amodinstallation).

## 5. Während des Tests

- Nichts bauen, kaufen, Linien bearbeiten, pausieren oder die Geschwindigkeit
  ändern. Der Test gibt Pause und Weiterlauf selbst vor. Anschauen und die Kamera
  bewegen ist möglich.
- Die Pausenwünsche stammen jeweils von einem Teilnehmer und werden gemeinsam
  freigegeben. Die normale Pause-Taste im Spiel wird durch diesen Versuch noch
  nicht als gemeinsame Spielereingabe geprüft. Auch gleichzeitige konkurrierende
  Bauwünsche sind noch kein Bestandteil des Testprofils.
- Der Launcher zeigt den Mitspieler, Spielkontakt, die aktuelle Bau-/Fahrphase und
  **240 Testrunden** an. Die ersten acht Runden bauen bei gehaltener Simulation
  die Szene auf. Ab Runde 8 fährt das Fahrzeug los, sofern TF2 die Route annimmt.
  Von Runde 80 bis 99 wird gemeinsam pausiert; Runde 100 setzt die Fahrt fort.
- Insgesamt sind 212 Fortschrittsschritte à 0,2 Sekunden und 28 Pausenrunden
  vorgesehen: **42,4 Sekunden Enginezeit**. Das Kalenderdatum hat eine eigene Rate.
  Durch gemeinsame Bestätigungen, Dateiaustausch und eine absichtliche Verzögerung
  von 100 ms beim Mitspieler dauert der Test in echt mehrere Minuten.
- Die Kamera wird nicht automatisch bewegt. Die Testobjekte entstehen auf einer
  automatisch gewählten freien Stelle. Die Linie heißt **TF2 Coop Test Line**;
  ihr könnt sie zum Zuschauen auswählen. Der Test läuft auch ohne Hinsehen.
- Bei einer erkannten Abweichung hält der Versuch an und zeigt den Grund.
  Nicht versuchen, ihn durch Pause/Play wieder zum Laufen zu bringen.
- Nach dem Abschluss bleibt die Spielzeit gehalten. Ein erfolgreicher Abschluss
  verlangt übereinstimmende beobachtete Zustände, verbundene Teststraßen, die echte
  Abbuchung beim Fahrzeugkauf, passende Linienzuordnung und mindestens einen
  Meter tatsächliche Fahrzeugbewegung über mehrere bestätigte Zeitpunkte.
  Das beweist noch keine vollständige oder dauerhafte Synchronität der ganzen Welt.

## 6. Nach Abschluss oder Fehler

1. Auf **beiden PCs** im Launcher **Testbericht als ZIP …** verwenden. Die zwei
   erzeugten Berichte für die Auswertung aufbewahren bzw. mir schicken. Der Export
   enthält jetzt zusätzlich ein Verlaufsprotokoll der Bauobjekte, Fahrzeugpositionen
   und Geldänderungen. Er enthält keinen Sitzungsschlüssel und keinen Save.
2. **Test beenden** klicken. Bei einem noch ausstehenden Engineabschluss kann das
   bis zu 30 Sekunden dauern. Das Spiel wird dadurch nicht geschlossen.
3. TF2 selbst vollständig schließen. Im Test nicht eure normale Partie überschreiben.
4. Im Launcher **Bisherige Installation wiederherstellen** klicken. Die vorherigen
   Dateien werden bytegenau zurückkopiert; Testsave-Kopien und Berichte bleiben erhalten.
5. Danach könnt ihr den bisherigen Alpha-Launcher mit eurer ursprünglichen Partie
   wieder verwenden. Dessen bisherige Synchronisationsprobleme sind damit nicht behoben.

Für einen weiteren Bautest zuerst wiederherstellen, dann erneut vorbereiten.
Der Host erhält einen neuen Sitzungscode und gibt ihn wieder an den Freund.
Eine bereits gestartete Sitzung oder ein im Messmodus fortgesetzter Save wird
nicht als neuer Ausgangsstand wiederverwendet.

## 7. So funktionieren spätere Updates

1. Vor einem neuen gemeinsamen Versuch auf beiden PCs TF2 und den bisherigen
   Test beenden. Falls noch eine Testinstallation aktiv ist, diese wiederherstellen.
2. Beide öffnen ihren Launcher ab Alpha5.2. Er prüft die neueste veröffentlichte
   Version im Repository **TastierPizza-code/TFCoop** und lädt sie bei Bedarf
   automatisch. Beim anschließenden Neustart erscheinen die neuen Versionsangaben.
3. Beide warten auf die abgeschlossene Updateprüfung. Für eine neue Version wieder
   mit einem neuen gemeinsamen Sitzungscode **Test vorbereiten und installieren**
   verwenden. Der Download allein installiert noch keine neuen Dateien in TF2.
4. Danach wie oben verbinden und die neu angelegte Testsave mit der zu dieser
   Version gehörenden Testmod laden. Maßgeblich ist die Modbezeichnung im Launcher.

Während TF2 oder ein Messcontroller läuft, wird der Versionswechsel verschoben.
Wenn GitHub nicht erreichbar ist, bleibt eine vorhandene Version nutzbar; eine
bereits vollständig geladene und geprüfte neuere Version kann aus dem lokalen
Speicher starten. Bei unterschiedlichen Versionen bitte erst auf beiden PCs
die Updateprüfung wiederholen. Die Verbindungsprüfung gleicht eure Testdateien ab.

Private Spielstände bleiben unter `%LOCALAPPDATA%\TF2StrictProbe\baseline`,
Updateversionen unter `%LOCALAPPDATA%\TF2StrictProbe\updates` gespeichert.
Der Updater lädt öffentliche Programmdateien herunter und lädt eure Spielstände
oder Berichte nicht auf GitHub hoch. Für spätere Updates genügt derselbe Launcher;
die ursprüngliche Alpha5.2-EXE kann auch eine schon gespeicherte neuere Version öffnen.

## Wenn etwas nicht klappt

| Anzeige / Problem | Nächster Schritt |
|---|---|
| Wartet auf Mitspieler | Auf beiden PCs dieselbe **Host-IP** und denselben Sitzungscode prüfen; Hamachi-Verbindung und Firewallzugriff kontrollieren. |
| Verbunden, aber kein Spielkontakt | Erst die Startfreigabe abwarten, dann TF2 starten. Die angezeigte Testsave mit aktivierter Testmod laden. Die zwei Minuten Startfreigabe beachten. |
| Testmod fehlt in der Liste | Installationsordner prüfen; Vorbereitung muss erfolgreich beendet sein. Nicht manuell alte DLLs darüberkopieren. |
| Spielstand fehlt in der Liste | Den ausgewählten Steam-Saveordner prüfen. Der Launcher zeigt den genauen importierten Dateinamen. |
| Privater Testspielstand fehlt / Prüfsummen stimmen nicht | **Testspielstand übernehmen …** verwenden und die ursprüngliche `Testspielstand\initial.sav` aus einem alten privaten Paket auswählen; die `.sav.lua` muss daneben liegen. |
| Update verschoben | TF2 und laufenden Test beenden, dann den Launcher neu starten. |
| Update nicht erreichbar / nicht verfügbar | Der Launcher behält die vorhandene Version. Später bei Internetzugang neu starten; beide Versionsanzeigen vergleichen. |
| Es steht weiterhin Alpha5.2 im Fenster | TF2 und Messcontroller schließen, den Launcher normal neu starten und die Updateprüfung abwarten. Falls das Update weiterhin nicht verfügbar ist, die aktuelle **TFCoop-Windows.zip** über den Downloadlink oben separat entpacken. |
| Unterschiedliche Testdateien / Ausgangszustände | Auf beiden PCs dieselbe aktuelle Version starten; für einen neuen Versuch wiederherstellen und mit dem passenden lokalen Ausgangsspielstand neu vorbereiten. |
| Native- oder Lua-Fehler | Testbericht von beiden PCs exportieren und Fehlertext schicken. Das kann eine Grenze der noch ungeprüften Engineanbindung zeigen. |
| `build_site_unavailable` | Es wurde keine passende freie und ausreichend ebene Baustelle gefunden. Berichte schicken; nichts von Hand vorbauen. |
| Bau, Verbindung oder Fahrzeugbewegung nicht bestätigt | Beide Berichte exportieren. Der Test hält auch dann an, wenn beide Spiele denselben unvollständigen Bauzustand haben. |
| Bereits installiert / Sitzung verbraucht | TF2 und Test beenden, bisherige Installation wiederherstellen, neu vorbereiten. |
| Wiederherstellung blockiert | TF2 und Messcontroller vollständig beenden. Wurden installierte Dateien nachträglich geändert, den Fehlertext schicken; die Sicherung bleibt erhalten. |
| Zugriff verweigert | Schreibrecht auf den gewählten Spiel-/Saveordner prüfen. Falls dort Administratorrechte erforderlich sind, den Launcher nach dem Schließen erneut mit diesen Rechten starten. |

Bei einem Fehler während der Vorbereitung bleibt die Sicherung unter
`<TF2-Installationsordner>\.tf2-strict-probe-install` erhalten. Nach einem
Launcherabsturz das neue Programm erneut öffnen und bei geschlossenem TF2 die
Wiederherstellung verwenden. Die lokalen Sitzungsberichte liegen unter
`%LOCALAPPDATA%\TF2StrictProbe\runs`.
