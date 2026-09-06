Alpha5.5-Diagnose (`v0.5.5`) erkennt vollständige Diagnoseberichte, die in Alpha5.4 als temporäre Datei liegen geblieben sind. In den beiden untersuchten Spieltests waren bereits jeweils 281 Einträge erfasst; der Launcher hatte sie nicht angezeigt.

- TF2 schließen und den vorhandenen Launcher neu öffnen. Das Update erfolgt automatisch ab Alpha5.2. Bei vorhandenem Bericht ist kein neuer Spielstart und keine erneute Vorbereitung nötig.
- Im Reiter **API-Diagnose allein** lässt sich der bisherige Bericht mit **Diagnosebericht als ZIP …** exportieren. Das funktioniert auch nach Wiederherstellung der Diagnosemod.
- Temporäre Berichte werden nur nach zwei identischen Lesevorgängen, vollständigem gültigem JSON und passender Auftragskennung übernommen. Angefangene Dateien gelten nicht als fertiger Bericht.
- Neue Diagnoseausgaben benötigen keine Lua-Dateiumbenennung. Der geschlossene temporäre Bericht bleibt erhalten; die endgültige Datei wird direkt geschrieben und durch Rücklesen geprüft. Schreibfehler erhalten begrenzte Statusmeldungen im TF2-Protokoll.
- Die Daten zeigen lesbare Matrizen und ein fehlendes `timeBuild` bei zwei vorhandenen Industriekonstruktionen. Das ist ein Hinweis, aber noch kein Nachweis für die Ursache des Alpha5.3-Straßenbauabbruchs. Der experimentelle Bauablauf bleibt unverändert.

Die Diagnose gibt keine Bau- oder Pausebefehle aus. Die öffentliche ZIP enthält keine privaten Spielstände oder Berichte. Freies Multiplayer-Bauen ist weiterhin nicht freigeschaltet. Anleitung: **ANLEITUNG.html**; technische Grenzen: **API_DIAGNOSE.md**.
