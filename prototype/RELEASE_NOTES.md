Alpha5.2 enthält die Korrektur für den Alpha5.1-Abbruch `a:2:nonplain observed params` nach dem Straßenbau. Native Parametercontainer werden vollständig ausgelesen, einschließlich verschachtelter Werte und zusätzlich beobachteter Felder.

- 104 Lua-Prüfungen und der vollständige 240-Runden-Dateitest mit zwei getrennten Lua-Peers bestehen. Der tatsächliche Zwei-PC-Test in TF2 steht noch aus.
- Neuer Launcher mit automatischen, geprüften Downloads aus diesem GitHub-Repository. Bitte auf beiden PCs einmal **TFCoop-Windows.zip** vollständig entpacken und **TF2-Coop.exe** öffnen. Danach diesen Launcher weiterverwenden; Git/Python werden nicht benötigt.
- Spiel und laufenden Test vor Updates schließen. Nach einem Update auf beiden PCs die Testdateien neu vorbereiten und **TF2 Strict Sync - automatischer Bautest (Alpha5.2)** im Testspielstand aktivieren; alte Koop-Mods deaktivieren.
- Der gemeinsame Testspielstand wird lokal aus dem bisherigen Lauf übernommen. Falls nötig **Testspielstand übernehmen …** anklicken und `Testspielstand/initial.sav` im alten privaten Paket auswählen; `.sav.lua` muss daneben liegen. Das öffentliche Paket enthält keine Spielstände oder Testberichte.

Der automatische Bautest umfasst Straße, Depot, zwei Haltestellen, Kauf, Linie, Abfahrt und gesteuerte Pausen. Freies gleichzeitiges Bauen, Cursor und die normalen Pause-Tasten sind weiterhin nicht freigeschaltet. Anleitung liegt als **ANLEITUNG.html** und **ANLEITUNG.md** bei.
