Alpha5.11-1x-Test (`v0.5.11`) bereitet den gemeinsamen Versuch zu ungleichen Wartezeiten und gleichmäßig freigegebenen Simulationsschritten vor.

- Nach dem bisherigen Aufbau mit zwölf Befehlen und 240 Runden folgen zwölf Fahrtabschnitte. Jeder enthält 25 Schritte à 0,2 Sekunden, also fünf Sekunden Simulationszeit; zusammen kommen 60 Sekunden hinzu. Das Ziel ist ausschließlich 1x.
- Drei Abschnitte laufen ohne Zusatzwartezeit, sechs mit abwechselnd künstlichen lokalen Wartezeiten von 0,25 bis 3 Sekunden, danach folgen drei weitere ohne Zusatzwartezeit. Beide Teilnehmer müssen vor und nach jedem Abschnitt dieselbe erfasste Weltgrenze bestätigen.
- Innerhalb der Fahrtabschnitte werden die native Uhr und der Abschluss jedes einzelnen Schritts geprüft. Die aufwendige Lua-Weltbeobachtung erfolgt an Anfang und Ende des Abschnitts. Es gibt keine schnelle Aufholserie nach Verzögerungen.
- Der Bericht trennt übereinstimmende Messwerte vom erreichten Tempoziel. Er enthält lokale Dauer, tatsächliche Zusatzwartezeiten und Freigabe-/Bestätigungsabstände. Diese Daten messen keine gerenderten Bilder. Ein erreichter Zielwert beweist weder sichtbare Flüssigkeit noch durchgängiges 1x über die gemeinsamen Haltepunkte hinweg.
- Die bisherige sehr große Karte und das saubere private Savepaar aus Alpha5.9 bleiben unverändert. Ein bestehender passender Cache genügt; kein erneuter Import ist nötig.

**Evidenz:** Alpha5.10 bestand den tatsächlichen Aufbau in einem Record und einem vollständigen Replay in zwei nacheinander gestarteten TF2-Prozessen auf einem PC. Die neuen Alpha5.11-Fahrtabschnitte sind bislang ausschließlich ohne TF2 mit Protokoll-, Adapter-, Lua-/Datei-IPC- und TCP-Testaufbauten geprüft. Ihr erster echter Zwei-PC-Versuch steht noch aus. Vollständige Weltsynchronität, freie gleichzeitige Eingaben, normale Pause-Tasten, Cursor und sichtbare Flüssigkeit werden nicht als bestanden dargestellt.

**Beide:** Test, TF2 und alten Launcher schließen; den vorhandenen Launcher öffnen und Update auf **Alpha5.11-1x-Test** abwarten. Vorherige Installation wiederherstellen. Im Reiter **Aufbau + 1x-Test (experimentell)** mit neuem gemeinsamen Code vorbereiten, verbinden und nach Startfreigabe die jeweils neu angezeigte Messtest-Save laden. Strict Sync Alpha5.11 und Legacy Fahrzeuge sind bereits ausgewählt.

**Bei 240 Aufbaurunden weiterlaufen lassen:** Danach alle zwölf Fahrtabschnitte abwarten. Die Fahrzeugfahrt beobachten; nicht selbst bauen, pausieren oder die Geschwindigkeit verändern. Anschließend oder bei Abbruch beide normalen Testbericht-ZIPs privat exportieren und kurz angeben, ob das Fahrzeug innerhalb der Abschnitte gleichmäßig fuhr oder sichtbar sprang. Die Hostanzeige bezieht sich auf beide Tempoergebnisse, die Mitspieleranzeige auf dessen lokalen PC.

Das öffentliche Paket enthält keine Spielstände oder Berichte. Vollständige Anleitung: **ANLEITUNG.html**. Ablauf und Messkriterien: **BUILD_TEST.md**. Prüfumfang und Grenzen: **VERIFICATION.md**.
