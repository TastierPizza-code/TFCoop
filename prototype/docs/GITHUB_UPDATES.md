# GitHub-Verteilung und automatische Launcher-Updates

Das öffentliche Repository ist
[TastierPizza-code/TFCoop](https://github.com/TastierPizza-code/TFCoop).
Der erste Launcher mit automatischer Updateprüfung ist **Alpha5.2**, Release-Tag
**`v0.5.2`**. Spieler laden einmal das vollständige Windows-Paket herunter:
[TFCoop-Windows.zip](https://github.com/TastierPizza-code/TFCoop/releases/latest/download/TFCoop-Windows.zip).
Git, Python und eine eigene Entwicklungsumgebung sind dafür nicht erforderlich.

## Ablauf auf den Spieler-PCs

Der Launcher prüft beim Start das neueste veröffentlichte GitHub-Release dieses
Repositories. Er verwendet dessen Windows-Asset `TFCoop-Windows.zip` und akzeptiert
eine Versionsnummer der Form `vMAJOR.MINOR.PATCH`. Entwürfe und als Vorabversion
markierte GitHub-Releases werden nicht für diesen Updateweg verwendet. Dass ein
Release für den Updater veröffentlicht ist, besagt nichts über die Spielreife;
der aktuelle Bautest bleibt ausdrücklich experimentell.

Eine neuere Version wird vollständig heruntergeladen, geprüft und in einen
eigenen Versionsordner unter `%LOCALAPPDATA%\TF2StrictProbe\updates` übernommen.
Erst danach startet der Launcher deren `TF2-Coop.exe`. Die ursprüngliche EXE ab
Alpha5.2 oder eine Verknüpfung darauf kann weiterhin als Einstieg dienen: Sie
findet auch eine bereits gespeicherte neuere Version. Ein alter Alpha5.1-Launcher
kann diese Aktualisierung noch nicht ausführen.

Solange TF2 oder ein Messcontroller läuft, wird der Versionswechsel verschoben.
Das gilt auch, wenn während des Downloads ein Test gestartet wird. Der Updateweg
startet oder beendet TF2 nicht und installiert keine Dateien in dessen Ordner.
Nach dem Update müssen beide Spieler die vorherige Testinstallation
wiederherstellen und eine neue Sitzung über **Test vorbereiten und installieren**
anlegen. Vorbereitete Sitzungen eines alten Pakets werden nicht fortgesetzt.

Bei einem Download- oder Netzwerkfehler bleibt die vorhandene Version erhalten.
Eine schon vollständig gespeicherte und erneut geprüfte neuere Version kann auch
ohne erfolgreichen GitHub-Zugriff gestartet werden. Beide Spieler sollten vor
einem gemeinsamen Versuch die Updateprüfung abschließen; die Lobby prüft
anschließend, dass ihre Testdateien übereinstimmen.

## Welche Dateien geprüft werden

`prototype/updater.py` bindet den Download an das festgelegte Repository,
den Release-Tag und den Assetnamen. Die Größe und die SHA-256-Prüfsumme des
gesamten Downloads müssen zu den von GitHub gelieferten Assetdaten passen.
Das `package_manifest.json` im Archiv muss denselben Release-Tag nennen und
enthält die Prüfsummen aller ausgelieferten Dateien.

Vor dem Start werden die vollständige Dateiliste und alle Dateiprüfsummen
geprüft. Unerwartete zusätzliche oder fehlende Dateien, unsichere Archivpfade,
Windows-Sondernamen, Verknüpfungen und Junctions werden abgewiesen. Größen- und
Dateizahllimits begrenzen die Verarbeitung. Ein unvollständiger Download wird
nicht zur aktuellen Version erklärt; der Zeiger auf einen neuen Versionsordner
wird erst nach erfolgreicher Prüfung veröffentlicht.

Die Veröffentlichungsberechtigung für dieses GitHub-Repository und HTTPS bilden
die Vertrauensgrundlage des Updatewegs. Die Prüfsummen erkennen beschädigte oder
abweichende Dateien; es gibt keine zusätzliche unabhängige Codesignatur dieses
Projektpakets.

## Private Ausgangsspielstände bleiben lokal

Öffentliche Releases enthalten keine `.sav`- oder `.sav.lua`-Dateien, keine
Sitzungsschlüssel, Nutzerberichte oder Originaldateien von Transport Fever 2.
Das Paketmanifest enthält unter `baseline` lediglich die erwarteten SHA-256-Werte
des Save-Paars und optional die beiden Dateigrößen. Ein anderer Spielstand wird
nicht stillschweigend als derselbe Ausgangsstand akzeptiert.

`prototype/baseline.py` sucht in dieser Reihenfolge nach dem passenden Paar:

1. Bereits geprüfter lokaler Speicher unter `%LOCALAPPDATA%\TF2StrictProbe\baseline`.
2. Optional eingebettetes `Testspielstand/initial.sav` mit zugehöriger `.sav.lua`
   im gerade verwendeten privaten Paket. Öffentliche Pakete enthalten kein Paar.
3. Die Ausgangskopie im letzten vom Launcher aufgezeichneten lokalen Testlauf.
4. Eine ausdrücklich über **Testspielstand übernehmen …** gewählte `.sav`-Datei
   mit danebenliegender `.sav.lua`.

**Seit Alpha5.9 wird ein sauberes Savepaar der bisherigen sehr großen Karte verwendet.**
Alpha5.10 verwendet dasselbe Paar weiter; ein bereits erfolgter Import genügt.
Die Basis aus Paketen vor Alpha5.9 und deren Cache haben andere Prüfsummen.
Beide Spieler benötigen deshalb einmal das seit Alpha5.9 bereitgestellte private Paar:
`Testspielstand/initial.sav` und `Testspielstand/initial.sav.lua`. Beide Dateien
unverändert privat weitergeben und nebeneinander entpacken. Anschließend auf
beiden PCs **Testspielstand übernehmen …** verwenden und diese neue `initial.sav`
auswählen. Die Modliste enthält bereits Legacy Fahrzeuge und die Strict-Testmod;
die neu vorbereiteten Messtest-Saves brauchen keine wiederholte Modumstellung.

Der Import prüft beide Hashes und die im Paket genannten Größen und veröffentlicht
erst dann ein frisches Paar atomar im lokalen Speicher. Nach der einmaligen
Übernahme wird dieser Cache auch ohne die ursprünglichen Importdateien wiederverwendet,
solange das neue Programm dieselbe Basis verlangt. Alte oder beschädigte
Cacheordner werden aufbewahrt. Es gibt keine Suche über beliebige Benutzerordner,
keine Annahme beliebiger Spielstände und keinen Download oder Upload der privaten
Spielstände.

Die eigentliche Vorbereitung erzeugt aus dieser lokalen Ausgangskopie weiterhin
eine eigene Testsave im gewählten Steam-Saveordner. Die zufälligen Dateinamen dürfen
auf beiden PCs verschieden sein; der gemeinsame Ausgangsinhalt muss übereinstimmen.

## Eine neue Version veröffentlichen

Für spätere Versionen werden Quellcode und ein vollständiges gebautes
Windows-Paket in diesem Repository veröffentlicht. Ein Commit allein löst beim
Launcher noch kein Update aus: Er bezieht veröffentlichte Release-Assets und
führt keine Dateien direkt aus dem Entwicklungsbranch aus.

Der Ablauf für die Veröffentlichung ist:

1. Versionsangabe des Launchers, Modbezeichnung, Release-Tag und Anleitung gemeinsam
   aktualisieren. Eine höhere Versionsnummer wählen; vorhandene Release-Tags und
   bereits veröffentlichte Pakete nicht nachträglich für andere Inhalte wiederverwenden.
2. Die zum Code passenden Prüfungen ausführen und die Anleitung mit
   `py -3.10 tools/render_probe_guide.py` erzeugen. Ein Test mit Ersatzengines wird
   in den Versionshinweisen als solcher ausgewiesen.
3. Mit `tools/build_probe_package.py` ein frisches öffentliches Windows-Paket bauen.
   Der öffentliche Build lässt das private Save-Paar weg, bindet dessen Identität
   im Manifest und führt den Paket-Selbsttest aus. Für ein öffentliches Release
   keinen privaten Build mit eingebettetem Spielstand verwenden.
4. Die für die Veröffentlichung vorgesehenen Dateien auf private Spielstände,
   lokale Nutzerpfade, Berichte, Schlüssel und fremde Spielbinärdateien prüfen.
   Nur freigegebene Projektdateien committen und den passenden Stand veröffentlichen.
5. Das Release mit `tools/publish_release.py` vorbereiten und veröffentlichen.
   Die verfügbaren Argumente beschreibt dessen `--help`. Das Windows-Asset muss
   exakt **`TFCoop-Windows.zip`** heißen; Release-Tag und Manifest müssen übereinstimmen.
6. Das fertige Release als aktuelle Veröffentlichung zugänglich machen. Die
   GitHub-Assetdaten müssen eine gültige SHA-256-Prüfsumme enthalten. Download und
   Paketidentität abschließend kontrollieren. Erst dann beziehen die Launcher
   diese Version über den festen Download- und Updateweg.

Die Schritt-für-Schritt-Anleitung für beide Spieler steht in
[ANLEITUNG.md](../ANLEITUNG.md). Der aktuelle Alpha5.10-Bautest bleibt bei 240 Runden
mit automatisch vorgegebenen Bau-, Fahr- und Pausenbefehlen. Freies Bauen,
Spielercursor und gemeinsame normale Pause-Tasten sind noch nicht angeschlossen.
Alpha5.10 behebt den mit dem Lebensdauerschutz aus Alpha5.9 eingeführten Startfehler:
TF2 ignoriert die Bereichsgrenzen von `table.unpack`; der Adapter reicht die
Rückgabewerte deshalb direkt als Lua-Varargs weiter und behält den Schutz bei.
Ein echter lokaler Record und sein Replay in einem zweiten frischen TF2-Prozess
haben inzwischen jeweils zwölf Befehle und alle 240 Schritte bestanden.
Ergebnisse und gemessene Zustände stimmten nach jeder Aktion überein. Beide
Prozesse wurden regulär beendet und die Installation wiederhergestellt.
Diese nacheinander ausgeführten Läufe sind kein Nachweis gemeinsamer
Netzwerksynchronität oder vollständiger Deterministik der Spielwelt. Der entsprechende
Zweirechnertest steht noch aus. Einzelheiten stehen im
[Prüfstand](../VERIFICATION.md).
