# TF2-Koop Alpha5.12-Dauertest — Anleitung für beide Spieler

**Der neue Standard ist „Neuer 1x-Dauertest“.** Er baut zuerst die gemeinsame Testszene auf und fährt danach 120 Sekunden Spielzeit. Die Haltepunkte nach jeweils fünf Sekunden aus dem vorigen Test entfallen. Alle zehn Sekunden Spielzeit gibt es einen gemeinsamen Kontrollpunkt; dabei kann die Fahrt weiterhin kurz stocken. Nach 60 Sekunden kommt eine automatische Pause mit zwei Sekunden gemessener Wartezeit.

**Eure bisherige sehr große Karte bleibt erhalten. Ihr habt das passende saubere Spielstandpaar bereits übernommen und braucht für dieses Update keinen neuen Import.** Das öffentliche Programmupdate enthält keinen Spielstand. Nur bei einer neuen Einrichtung muss das private Paar einmal separat übernommen werden.

Der Alpha5.11-Test wurde auf euren beiden PCs mit gleichen erfassten Zuständen abgeschlossen; das gesamte 1x-Tempoziel wurde dabei noch nicht erreicht. Alpha5.12 soll die Unterbrechungen verkürzen und ist bisher ohne Spielstart vorgeprüft. Ob die neue Fahrt bei euch flüssig läuft, müssen wir mit diesem Versuch feststellen. Die normale Pause-Taste, freies Bauen und Cursor sind noch nicht angeschlossen. Mehr zum [Prüfumfang](https://github.com/TastierPizza-code/TFCoop/blob/main/prototype/VERIFICATION.md).

## 1. Beide aktualisieren und denselben Test wählen

1. Laufenden Test beenden, **TF2 vollständig schließen** und den bisherigen Launcher schließen. Ein Update wartet, solange das Spiel oder ein Messcontroller läuft.
2. Den vorhandenen Launcher normal neu öffnen und die Updateprüfung abwarten. Auf beiden PCs muss **Alpha5.12-Dauertest** stehen. Der lokale Cache des sauberen Spielstandpaars bleibt gültig.
3. **Bisherige Installation wiederherstellen** verwenden. Das Programmupdate allein ersetzt noch keine installierten Testdateien. Sicherungen und eigene Spielstände nicht von Hand löschen.
4. Unter **Ordner prüfen** den eigenen **TF2-Installationsordner** und **Steam-Saveordner** prüfen. Übliche Formen sind `…\steamapps\common\Transport Fever 2` und `…\Steam\userdata\<Kontonummer>\1066780\local\save`.
5. Im Reiter **Aufbau + 1x-Test (experimentell)** auf **beiden PCs „Neuer 1x-Dauertest“** wählen. **API-Diagnose allein** wird für diesen Versuch nicht gebraucht.
6. Beide PCs mit demselben Hamachi-Netz verbinden oder dasselbe LAN verwenden. Ihr braucht die **IPv4-Adresse des Hosts**; bei Hamachi beginnt sie normalerweise mit `25.`. Für zwei PCs nicht `127.0.0.1` verwenden.

## 2. Du als Host

1. **Ich bin Host** auswählen.
2. Unter **IP des Hosts (Hamachi/LAN)** deine eigene Hamachi- oder LAN-IPv4 eintragen.
3. Neben **Gemeinsamer Sitzungscode** auf **Neu**, dann **Kopieren** klicken. Diesen vollständigen frischen Code und deine Host-IP deinem Freund schicken. Beide verwenden denselben gewählten Testmodus.
4. **Test vorbereiten und installieren** klicken und die Fertigmeldung abwarten. Der Launcher sichert die vorherigen Dateien und importiert eine neue Kopie der gemeinsamen Ausgangsbasis.
5. Den angezeigten Namen **`TF2-Koop-Messtest-….sav`** merken. Die zufällige Endung darf bei deinem Freund anders sein; der Inhalt wird geprüft.
6. Sobald beide vorbereitet haben, **Verbinden & Test bereitstellen** klicken.

## 3. Dein Freund als Mitspieler

1. **Ich trete meinem Freund bei** auswählen.
2. Unter **IP des Hosts (Hamachi/LAN)** die vom Host erhaltene IP eintragen. Auf beiden PCs steht dieselbe Host-IP.
3. Den eigenen Sitzungscode vollständig durch den neuen Code des Hosts ersetzen. **Neuer 1x-Dauertest** muss auch hier ausgewählt sein.
4. **Test vorbereiten und installieren** klicken und die Fertigmeldung abwarten. Der Launcher importiert auch hier eine eigene frische Testsave samt `.sav.lua`. Nichts von Hand in den Spielordner kopieren.
5. **Verbinden & Test bereitstellen** klicken.

Bei einer Windows-Firewallabfrage den Launcher im verwendeten LAN-/Hamachi-Netz erreichbar machen. Lobby und Test verwenden TCP 34208 und TCP 34207. Unterschiedliche Testmodi oder Testdateien werden vor dem Spielstart zurückgewiesen.

## 4. Beide laden die neu angezeigte Testsave

1. Auf **Mitspieler: verbunden · gleiche Testdateien** und die Startfreigabe warten. Diese Meldung bestätigt Dateien und Modus; die geladene Welt wird danach getrennt verglichen.
2. Nach der Freigabe innerhalb von zwei Minuten **TF2 über Steam starten** klicken oder das Spiel selbst über Steam starten. Für das anschließende Laden wartet der Sitzungsstart bis zu zehn Minuten. Den Launcher offen lassen.
3. In TF2 **Spiel laden** öffnen und genau die **neu im eigenen Launcher angezeigte `TF2-Koop-Messtest-….sav`** auswählen. Nicht **Fortsetzen**, eine alte Testsave oder eine Diagnose-Save wählen.
4. Unter **Aktivierte Mods** stehen bereits **TF2 Strict Sync - automatischer Bautest (Alpha5.12)** und **Legacy Fahrzeuge**. Die Modliste braucht keine erneute Umstellung. Stehen dort die alten Koop-Mods, zurück zur Ladeliste gehen und den exakten neuen Namen auswählen. Keine weiteren Mods einschalten.
5. Die Testsave laden. Wer zuerst fertig ist, wartet bei gehaltener Spielzeit, bis beide geladen haben und der Ausgangsvergleich passt.

## 5. Aufbau und Dauertest beobachten

- **Nur zuschauen; die Kamera dürft ihr bewegen.** Nicht selbst bauen, kaufen, Linien bearbeiten, pausieren oder die Geschwindigkeit verändern. Die Eingaben kommen automatisch vom Test.
- Zuerst laufen **240 Aufbaurunden**. Der Test baut Straße, Depot und Haltestellen, kauft ein Fahrzeug und weist es einer Linie zu. Vorgegebene Pausen gehören zum Aufbau. **Bei 240 nicht beenden.**
- Die Anzeige wechselt danach auf **1x-Dauertest: 0 / 120 Sekunden Spielzeit**. Diese 120 Sekunden sind zusätzliche Spielzeit, keine feste Stoppuhrdauer. Weltabfragen, Warten und ein langsamerer PC können die tatsächliche Laufzeit verlängern.
- Der Dauertest gibt immer zwei kleine Simulationsschritte gemeinsam frei. Frische erfasste Weltzustände werden alle zehn Sekunden Spielzeit verglichen. Achtet darauf, ob die Fahrt zwischen diesen Punkten gleichmäßig aussieht und ob an den Punkten kurze Stopps auftreten.
- **Nach 60 Sekunden Spielzeit pausiert der Test automatisch.** Beide halten denselben Spielzustand während einer gemessenen Wartezeit von zwei Sekunden. Danach setzt der Test selbst fort. Die sichtbare Pause kann durch Abfragen und Bestätigungen etwas länger ausfallen; keine Pause-/Play-Taste drücken.
- Über die Linie **TF2 Coop Test Line** könnt ihr das Fahrzeug auswählen und seine Fahrt beobachten. Kamera und Ansicht werden nicht automatisch bewegt. Merkt euch, ob es durchgehend fährt, nur an Kontrollpunkten stockt oder auch dazwischen springt.
- Bis **120 / 120 Sekunden und zur Abschlussmeldung** weiterlaufen lassen. Beide letzten Kontrollpunkte müssen bestätigt sein. Bei einem Fehler nicht versuchen weiterzuspielen: Der normale Bericht enthält die Diagnose; keine weitere Solo-Diagnose vorbereiten.

Die Anzeige trennt den abgeschlossenen Zustandsvergleich vom **1x-Ziel**. Ein gemeinsamer Abschluss kann mit **1x-Ziel noch nicht erreicht** zusammenfallen. Beim Host bedeutet **Beide PCs** die gemeinsame Tempoauswertung; beim Mitspieler beschreibt **Tempo auf deinem PC** nur dessen lokale Messung. Eine positive Tempoanzeige ist kein automatischer Nachweis flüssiger Bilder. Deshalb werden eure Beobachtung und beide Berichte benötigt.

## 6. Berichte sichern und den Test beenden

1. Nach Abschluss oder Abbruch auf **beiden PCs** im Bautestreiter **Testbericht als ZIP …** verwenden. Beide normalen ZIPs privat zur Auswertung schicken, auch wenn nur einer einen Fehler sieht. Alte Berichte aufbewahren.
2. Kurz dazuschreiben, ob das Fahrzeug gleichmäßig fuhr und wann Stopps oder Sprünge auftraten: an Kontrollpunkten, bei der vorgesehenen Pause oder zwischendurch. Ein Screenshot kann die Ergebnisanzeige zeigen, aber keine Bewegungsflüssigkeit belegen.
3. **Test beenden** klicken. Ein bereits freigegebener Engineauftrag kann noch enden oder in seine Zeitgrenze laufen. Der Knopf schließt TF2 nicht.
4. TF2 selbst vollständig schließen und **Bisherige Installation wiederherstellen** verwenden. Die Testsave nicht über eure normale Partie speichern. Vorhandene Savekopien, Sicherungen und exportierte Berichte bleiben erhalten.

Jeder weitere Versuch benötigt eine neue Vorbereitung mit einem frischen gemeinsamen Code und neu importierten Testsave-Kopien. Eine fortgesetzte Messsave ist keine neue Ausgangsbasis.

## Den bisherigen Test zum Vergleich verwenden

Der aktuelle Launcher enthält weiterhin **Vergleichstest aus Alpha5.11**. Wenn ihr diesen Ablauf wiederholen wollt, beide Test und TF2 schließen, die vorherige Installation wiederherstellen, auf beiden PCs den Vergleichsmodus auswählen und mit neuem gemeinsamen Code frisch vorbereiten.

Dieser Modus baut dieselbe Szene auf und fährt danach zwölf Abschnitte mit jeweils fünf Sekunden Spielzeit. Einige beginnen mit absichtlich ungleichen Wartezeiten. Die alten Übergangsstopps gehören hier weiterhin zum Ablauf. Erst nach allen zwölf Abschnitten exportieren. Beide müssen denselben Modus verwenden.

Der Vergleichsmodus läuft im aktuellen Programm. Dafür wird weder eine alte EXE gestartet noch der Updater zurückgesetzt. Quellstand und Release von [v0.5.11](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.11) bleiben erhalten; die bisherigen Berichte und die saubere Ausgangsbasis sind zusätzlich privat gesichert.

## Erste Einrichtung und spätere Updates

Ohne vorhandenen Launcher einmal **[TFCoop-Windows.zip — neueste Version](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip)** herunterladen und vollständig in einen eigenen Ordner entpacken, beispielsweise `C:\Games\TFCoop`. Nicht in den Spielordner oder über eine alte Version entpacken. `TF2-Coop.exe`, `_internal` und `package_manifest.json` zusammenlassen. Git und Python sind nicht nötig. Diese Anleitung gehört zu [Alpha5.12 / v0.5.12](https://github.com/TastierPizza-code/TFCoop/releases/tag/v0.5.12).

Die **sehr große Karte** bleibt dieselbe. Seit Alpha5.9 wird ihr sauberes privates Paar `Testspielstand/initial.sav` und `Testspielstand/initial.sav.lua` verwendet. Falls dieses Paar auf einem neu eingerichteten PC noch fehlt, beide unverändert nebeneinander entpacken und über **Testspielstand übernehmen …** die `initial.sav` wählen. Ein bestehender passender Cache wird weiterverwendet; eure beiden bisherigen Installationen brauchen keinen neuen Import. Die Basis vor Alpha5.9 oder eine fortgesetzte Testsave passt nicht.

Für spätere Updates genügt derselbe Launcher: Test und TF2 schließen, Launcher normal öffnen, Updateprüfung abwarten. Anschließend die vorherige Installation wiederherstellen und frisch vorbereiten. Der Updater lädt Spielstände und Berichte nicht auf GitHub hoch. Berichte können lokale Pfade und Kartendaten enthalten und sind für die private Auswertung bestimmt.

## Wenn etwas nicht klappt

| Anzeige oder Problem | Nächster Schritt |
|---|---|
| Verschiedene Testmodi oder Dateien | Beide dieselbe Version und denselben Modus wählen, wiederherstellen und mit neuem gemeinsamen Code vorbereiten. |
| Warten auf Mitspieler | Dieselbe Host-IP und denselben vollständigen Code prüfen; Hamachi-Verbindung und Firewallzugriff prüfen. |
| Verbunden, aber kein Spielkontakt | Startfreigabe abwarten, TF2 starten und den exakt neu angezeigten Testsave mit Strict Sync Alpha5.12 laden. |
| Beim Laden stehen alte Mods | Zurück zur Ladeliste; die alte Save durch den exakten neuen Namen aus dem Launcher ersetzen. |
| Ausgangsspielstand fehlt oder Prüfsummen passen nicht | Das unveränderte saubere Paar aus Alpha5.9 vollständig bereitstellen und seine `initial.sav` übernehmen; die `.sav.lua` muss danebenliegen. |
| Lua-/Native-Fehler oder Bauabbruch | Auf beiden PCs die normalen Testbericht-ZIPs exportieren und mit Fehlertext privat zur Auswertung schicken. Keine zusätzliche Solo-Diagnose nötig. |
| 1x-Ziel noch nicht erreicht | Beide Berichte und die Beobachtung der Fahrzeugfahrt schicken. Die Meldung allein bedeutet noch keine Zustandsabweichung. |
| Export oder Wiederherstellung blockiert | Den genauen Fehlertext schicken; vorhandene Berichte und Sicherungen behalten. Vor Wiederherstellung Test und TF2 vollständig beenden. |

Der native Test unterstützt den geprüften Windows-Spielbuild 35924. Bei einem anderen Build den Fehlertext schicken, statt DLLs manuell auszutauschen. Nach einem Launcherabsturz bei geschlossenem TF2 erneut öffnen und die Wiederherstellung verwenden.
