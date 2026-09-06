"""Bautest desktop launcher. Importing this module creates no window."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from coop.install import discover_game
from coop.native import NativeError, game_is_running
from prototype.strict_sync import launcher_session as workflow
from prototype import diagnostic_session as diagnostics


class App:
    def __init__(self, root, *, skip_update=False):
        self.root = root
        root.title("TF2-Koop · " + workflow.VERSION)
        root.geometry("980x810")
        root.minsize(860, 650)
        self.events = queue.Queue()
        self.busy = False
        self.prepared = None
        self.controller = None
        self.last_status = ""
        self.last_run = None
        self.diagnostic = self.last_diagnostic = None
        self.diagnostic_finished = False
        self.diagnostic_ticks = 0
        self.diagnostic_started = time.monotonic()
        self.skip_update = skip_update
        self.baseline_ready = False
        self.closing_for_update = False
        self.settings_path = workflow.local_root() / "launcher.json"
        settings = workflow.read_json(self.settings_path) or {}
        self.game = tk.StringVar(value=settings.get("game_dir", ""))
        self.saves = tk.StringVar(value=settings.get("save_dir", ""))
        self.role = tk.StringVar(value="a")
        self.host = tk.StringVar(value="")
        self.code = tk.StringVar(value=workflow.new_code())
        self.status = tk.StringVar(value="Beide: TF2 und den bisherigen Koop-Launcher schließen. Dann Pfade prüfen und Test vorbereiten.")
        self.save_name = tk.StringVar(value="Wird bei der Vorbereitung als eigene Kopie angelegt.")
        self.network = tk.StringVar(value="Mitspieler: noch nicht verbunden")
        self.engine = tk.StringVar(value="Spielkontakt: noch nicht gestartet")
        self.progress_text = tk.StringVar(value="Messung: noch nicht gestartet")
        self.update_status = tk.StringVar(value="Updates werden beim Start über GitHub geprüft.")
        self.baseline_status = tk.StringVar(value="Lokalen Testspielstand prüfen …")
        self.diagnostic_status = tk.StringVar(value="Allein möglich. TF2 und den bisherigen Test zuerst schließen, dann Diagnose vorbereiten.")
        self.diagnostic_save = tk.StringVar(value="Die Vorbereitung legt einen eigenen Diagnosespielstand an.")
        self._build()
        if settings.get("last_run"):
            record = workflow.read_json(Path(settings["last_run"]) / "run.json")
            try:
                if record:
                    self.last_run = workflow.PreparedRun(**record)
            except (TypeError, ValueError):
                pass
        if settings.get("last_diagnostic"):
            try:
                self.last_diagnostic = diagnostics.load_diagnostic(Path(settings["last_diagnostic"]))
                self.diagnostic_save.set(Path(self.last_diagnostic.imported_save).name)
                self.diagnostic_status.set("Vorherige Diagnose verfügbar. Bericht exportieren oder bei geschlossenem TF2 neu vorbereiten.")
            except (OSError, TypeError, ValueError):
                pass
        self._work(self._discover, self._discovered)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(250, self.tick)

    def _build(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 11))
        shell = ttk.Frame(self.root)
        shell.pack(fill="both", expand=True)
        canvas = tk.Canvas(shell, highlightthickness=0)
        scroll = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        outer = ttk.Frame(canvas, padding=18)
        embedded = canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(embedded, width=event.width))
        self.root.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        ttk.Label(outer, text="TF2-Koop  /  " + workflow.VERSION, style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Straße, Depot, Fahrzeug und Linienfahrt gemeinsam prüfen", font=("Segoe UI", 12)).pack(anchor="w", pady=(3, 6))
        ttk.Label(outer, text="Auf beiden PCs neu vorbereiten. Vorher TF2 schließen und eine vorhandene Diagnoseinstallation unten wiederherstellen. Für diesen Bautest ist kein neuer Solo-Diagnoselauf nötig.",
                  wraplength=900).pack(anchor="w", pady=(0, 13))
        ttk.Label(outer, textvariable=self.update_status, wraplength=900).pack(anchor="w", pady=(0, 8))
        paths = ttk.LabelFrame(outer, text="1  ·  Ordner prüfen", padding=12)
        paths.pack(fill="x")
        paths.columnconfigure(1, weight=1)
        self.inputs = []
        for row, label, variable in ((0, "TF2-Installationsordner", self.game), (1, "Steam-Saveordner", self.saves)):
            ttk.Label(paths, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            entry = ttk.Entry(paths, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            button = ttk.Button(paths, text="Auswählen …", command=lambda v=variable: self.choose_directory(v))
            button.grid(row=row, column=2, padx=(8, 0))
            self.inputs.extend((entry, button))
        baseline_button = ttk.Button(paths, text="Testspielstand übernehmen …", command=self.choose_baseline)
        baseline_button.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.inputs.append(baseline_button)
        ttk.Label(paths, textvariable=self.baseline_status, wraplength=620).grid(
            row=2, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 0))
        tabs = ttk.Notebook(outer)
        tabs.pack(fill="both", expand=True, pady=(12, 0))
        solo = ttk.Frame(tabs, padding=12)
        build = ttk.Frame(tabs, padding=12)
        tabs.add(build, text="Bautest (experimentell)")
        tabs.add(solo, text="API-Diagnose allein")
        ttk.Label(solo, text="2  ·  Diagnose vorbereiten", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(solo, text="Die Vorbereitung stellt die native Testinstallation zurück, installiert die Diagnosemod und kopiert den lokalen Ausgangsspielstand. IP, Sitzungscode und Verbindung werden nicht benötigt.", wraplength=850).pack(anchor="w", pady=8)
        self.diagnostic_button = ttk.Button(solo, text="Diagnose vorbereiten", command=self.prepare_diagnostic)
        self.diagnostic_button.pack(anchor="w", pady=(0, 10))
        ttk.Label(solo, text="3  ·  TF2 selbst über Steam starten und diesen Spielstand laden", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Entry(solo, textvariable=self.diagnostic_save, state="readonly").pack(fill="x", pady=7)
        ttk.Label(solo, text="Spiel laden → OPTIONEN AUSWÄHLEN / Mods: 'TF2 API-Diagnose (Alpha5.8)' und Legacy Fahrzeuge aktivieren. Strict Sync und alte Koop-Mods deaktivieren. Nach dem Laden etwa 10 Sekunden warten.", wraplength=850).pack(anchor="w")
        ttk.Label(solo, text="Die Diagnose baut nichts und ändert keine Pause. Sie liest vorhandene Objekte und getrennt davon neu angelegte Konfigurationsobjekte. Fehlende Fahrzeuge oder Depots bleiben als ungeprüft erkennbar.", wraplength=850).pack(anchor="w", pady=9)
        ttk.Label(solo, textvariable=self.diagnostic_status, style="Status.TLabel", wraplength=850).pack(anchor="w", pady=7)
        self.diagnostic_export_button = ttk.Button(solo, text="Diagnosebericht als ZIP …", command=self.export_diagnostic)
        self.diagnostic_export_button.pack(anchor="w", pady=8)
        ttk.Label(solo, text="Nur diesen eigenen Bericht zur Auswertung schicken. Anschließend TF2 schließen und unten die bisherige Installation wiederherstellen.", wraplength=850).pack(anchor="w")
        ttk.Label(build, text=f"Automatischer Bautest mit {workflow.ROUNDS} Runden. Der Test baut und fährt auf beiden PCs. Bitte nichts selbst bauen oder pausieren. Bei Abschluss oder Abbruch beide Testberichte exportieren.", wraplength=850).pack(anchor="w", pady=(0, 9))
        form = ttk.LabelFrame(build, text="Auf beiden PCs vorbereiten", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        rolebox = ttk.Frame(form)
        rolebox.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 4))
        for label, value in (("Ich bin Host", "a"), ("Ich trete meinem Freund bei", "b")):
            button = ttk.Radiobutton(rolebox, text=label, value=value, variable=self.role)
            button.pack(side="left", padx=(0, 22))
            self.inputs.append(button)
        ttk.Label(form, text="IP des Hosts (Hamachi/LAN)").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=4)
        self.addresses = ttk.Combobox(form, textvariable=self.host)
        self.addresses.grid(row=3, column=1, sticky="ew", pady=4)
        self.inputs.append(self.addresses)
        ttk.Label(form, text="Auf beiden PCs dieselbe Host-IP.").grid(row=3, column=2, padx=(8, 0), sticky="w")
        ttk.Label(form, text="Gemeinsamer Sitzungscode").grid(row=4, column=0, sticky="w", padx=(0, 12), pady=4)
        entry = ttk.Entry(form, textvariable=self.code, font=("Consolas", 10))
        entry.grid(row=4, column=1, sticky="ew", pady=4)
        self.inputs.append(entry)
        code_buttons = ttk.Frame(form)
        code_buttons.grid(row=4, column=2, padx=(8, 0))
        ttk.Button(code_buttons, text="Kopieren", command=lambda: self.copy(self.code.get())).pack(side="left")
        new = ttk.Button(code_buttons, text="Neu", command=lambda: self.code.set(workflow.new_code()))
        new.pack(side="left", padx=(4, 0))
        self.inputs.append(new)
        ttk.Label(form, text="Host kopiert seinen Code zum Freund. Der Freund ersetzt damit seinen angezeigten Code.",
                  wraplength=860).grid(row=5, column=0, columnspan=3, sticky="w", pady=(3, 7))
        self.prepare_button = ttk.Button(form, text="Test vorbereiten und installieren", command=self.prepare)
        self.prepare_button.grid(row=6, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(form, text="Sichert die bisherige Installation und importiert eine neue Testsave-Kopie.",
                  wraplength=850).grid(row=7, column=0, columnspan=3, sticky="w")
        connection = ttk.LabelFrame(build, text="Verbinden und Spiel starten", padding=12)
        connection.pack(fill="x", pady=(12, 0))
        actions = ttk.Frame(connection)
        actions.pack(fill="x")
        self.connect_button = ttk.Button(actions, text="Verbinden & Test bereitstellen", command=self.connect, state="disabled")
        self.connect_button.pack(side="left")
        self.game_button = ttk.Button(actions, text="TF2 über Steam starten", command=self.start_game, state="disabled")
        self.game_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(actions, text="Test beenden", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Label(connection, textvariable=self.network).pack(anchor="w", pady=(9, 2))
        ttk.Label(connection, textvariable=self.engine).pack(anchor="w", pady=2)
        ttk.Label(connection, textvariable=self.progress_text).pack(anchor="w", pady=2)
        self.bar = ttk.Progressbar(connection, maximum=workflow.ROUNDS, mode="determinate")
        self.bar.pack(fill="x", pady=(5, 7))
        ttk.Label(connection, textvariable=self.status, style="Status.TLabel", wraplength=870).pack(anchor="w")
        savebox = ttk.Frame(build)
        savebox.pack(fill="x", pady=10)
        ttk.Label(savebox, text="Im Spiel ausdrücklich diese Testsave wählen:").pack(anchor="w")
        ttk.Entry(savebox, textvariable=self.save_name, state="readonly").pack(fill="x", pady=3)
        ttk.Label(savebox, text="Spiel laden → OPTIONEN AUSWÄHLEN / Mods: 'TF2 Strict Sync - automatischer Bautest (Alpha5.8)' und Legacy Fahrzeuge aktivieren; Diagnosemod und alte Koop-Mods deaktivieren.",
                  wraplength=900).pack(anchor="w")
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(7, 0))
        self.restore_button = ttk.Button(footer, text="Bisherige Installation wiederherstellen", command=self.restore)
        self.restore_button.pack(side="left")
        ttk.Button(footer, text="Testbericht als ZIP …", command=self.export).pack(side="left", padx=8)
        ttk.Button(footer, text="Anleitung öffnen", command=self.guide).pack(side="right")

    def _discover(self):
        update = None
        if getattr(sys, "frozen", False) and not self.skip_update:
            from prototype.updater import check_for_update
            from prototype.update_startup import session_active
            update = check_for_update(workflow.package_directory(), workflow.local_root() / "updates",
                progress=lambda value: self.events.put((self._update_progress, str(value), None)),
                active_check=session_active)
        baseline_error = ""
        try:
            baseline = workflow.baseline_save()
            if not baseline.is_file() or not Path(str(baseline) + ".lua").is_file():
                raise ValueError("Testspielstand aus dem bisherigen Paket einmal übernehmen.")
        except (OSError, ValueError) as exc:
            baseline_error = str(exc)
        game = discover_game()
        return game, workflow.save_directories(), workflow.suggested_addresses(), update, baseline_error

    def _update_progress(self, value):
        self.update_status.set(value)

    def _discovered(self, result):
        game, saves, addresses, update, baseline_error = result
        if update:
            self.update_status.set(update.message)
            if update.executable:
                try:
                    from prototype.update_startup import handoff
                    handoff(update.executable)
                    self.closing_for_update = True
                    self.root.destroy()
                    return
                except (OSError, ValueError, NativeError) as exc:
                    self.update_status.set("Die bisherige Version bleibt geöffnet: " + str(exc))
        else:
            self.update_status.set("Aktuelle Version gestartet." if self.skip_update else "Entwicklungsstart: keine automatischen Downloads.")
        self.baseline_ready = not baseline_error
        self.baseline_status.set(baseline_error or "Gemeinsamer Testspielstand ist lokal verfügbar.")
        if game and not self.game.get():
            self.game.set(str(game))
        if not self.saves.get() and len(saves) == 1:
            self.saves.set(saves[0])
        self.addresses.configure(values=addresses)
        if addresses:
            self.host.set(addresses[0])
        if self.last_diagnostic and Path(self.last_diagnostic.game_dir) == Path(self.game.get()):
            try:
                installed = diagnostics.diagnostic_status(self.game.get())
                if installed.get("installed") and installed.get("request_id") == self.last_diagnostic.request_id:
                    self.diagnostic = self.last_diagnostic
                    self.diagnostic_status.set("Vorbereitete Diagnose wieder aufgenommen. Den angezeigten Spielstand mit der Diagnosemod laden oder vorhandenen Bericht exportieren.")
            except (OSError, ValueError) as exc:
                self.diagnostic_status.set("Diagnoseinstallation prüfen: " + str(exc))
        self._buttons()

    def _work(self, job, done):
        self.busy = True
        self._buttons()
        def run():
            try:
                self.events.put((done, job(), None))
            except Exception as exc:
                self.events.put((done, None, str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def _buttons(self):
        locked = self.busy or self.prepared is not None or self.diagnostic is not None
        for widget in self.inputs:
            widget.configure(state="disabled" if locked else "normal")
        self.prepare_button.configure(state="disabled" if locked or not self.baseline_ready else "normal")
        active = bool(self.controller and self.controller.alive())
        self.diagnostic_button.configure(state="disabled" if locked or active or not self.baseline_ready else "normal")
        self.diagnostic_export_button.configure(state="normal" if self.last_diagnostic and not self.busy else "disabled")
        self.connect_button.configure(state="normal" if self.prepared and not self.controller and not self.busy else "disabled")
        self.restore_button.configure(state="disabled" if self.busy or active else "normal")
        self.stop_button.configure(state="normal" if active else "disabled")

    def choose_directory(self, variable):
        directory = filedialog.askdirectory(parent=self.root, initialdir=variable.get() or None)
        if directory:
            variable.set(directory)

    def choose_baseline(self):
        selected = filedialog.askopenfilename(parent=self.root,
            title="Aus dem bisherigen Paket: Testspielstand / initial.sav auswählen",
            filetypes=[("TF2-Spielstand", "*.sav")])
        if selected:
            from prototype.baseline import resolve_baseline
            self._work(lambda: resolve_baseline(workflow.package_directory(), workflow.local_root(), Path(selected)),
                       self._baseline_selected)

    def _baseline_selected(self, path):
        self.baseline_ready = True
        self.baseline_status.set("Gemeinsamer Testspielstand lokal übernommen; bleibt bei Updates erhalten.")
        self._buttons()

    def copy(self, value):
        self.root.clipboard_clear()
        self.root.clipboard_append(value)

    def _save_settings(self):
        workflow.write_json(self.settings_path, {"game_dir": self.game.get(), "save_dir": self.saves.get(),
                                                "last_run": self.last_run.run_dir if self.last_run else None,
                                                "last_diagnostic": self.last_diagnostic.run_dir if self.last_diagnostic else None})

    def prepare_diagnostic(self):
        if self.busy or self.prepared or self.diagnostic or (self.controller and self.controller.alive()):
            return
        game, saves = self.game.get(), self.saves.get()
        self.diagnostic_status.set("Bisherige Testinstallation wird zurückgebaut; Diagnose und eigene Save-Kopie werden vorbereitet …")
        self._work(lambda: diagnostics.prepare_diagnostic(game, saves), self._diagnostic_prepared)

    def _diagnostic_prepared(self, run):
        self.diagnostic = self.last_diagnostic = run
        self.diagnostic_finished = False
        self.diagnostic_ticks = 0
        self.diagnostic_started = time.monotonic()
        self.diagnostic_save.set(Path(run.imported_save).name)
        self.diagnostic_status.set("Vorbereitet. Jetzt TF2 selbst über Steam starten, Diagnosemod aktivieren und den angezeigten Diagnosespielstand laden.")
        self._save_settings()
        self._buttons()

    def _poll_diagnostic(self):
        run = self.diagnostic or self.last_diagnostic
        if not run or self.diagnostic_finished or self.busy:
            return
        self.diagnostic_ticks += 1
        if self.diagnostic_ticks % 3:
            return
        try:
            report = diagnostics.read_diagnostic_report(run)
            if report is None:
                if self.diagnostic and time.monotonic() - self.diagnostic_started >= 60:
                    self.diagnostic_status.set("Noch kein Diagnosebericht. Falls die Karte bereits geladen ist: angezeigten Diagnosespielstand und aktive Diagnosemod prüfen. Bei weiter ausbleibendem Bericht diese Meldung schicken; sie beweist keinen API-Fehler.")
                return
            self.diagnostic_finished = True
            if report["status"] == "completed":
                count = len(report.get("records", []))
                suffix = " Bericht wurde an der Größenbegrenzung gekürzt." if report.get("truncated") else ""
                self.diagnostic_status.set(f"Diagnosebericht vorhanden: {count} Einträge. Fehlende oder auffällige Felder stehen im Bericht; dies ist kein bestandener Synchronitätstest." + suffix + " Jetzt 'Diagnosebericht als ZIP …' speichern.")
            else:
                self.diagnostic_status.set("Die Diagnose meldet einen Fehler. Den Diagnosebericht als ZIP zur Auswertung speichern.")
        except (OSError, TypeError, ValueError) as exc:
            self.diagnostic_finished = True
            self.diagnostic_status.set("Diagnosebericht konnte nicht geprüft werden: " + str(exc))

    def export_diagnostic(self):
        if not self.last_diagnostic:
            messagebox.showinfo("Diagnosebericht", "Bitte zuerst eine Diagnose vorbereiten.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Diagnosebericht speichern", defaultextension=".zip",
            initialfile=f"TF2-API-Diagnose-{datetime.now():%Y%m%d-%H%M%S}.zip", filetypes=[("ZIP", "*.zip")])
        if path:
            try:
                diagnostics.export_diagnostic(self.last_diagnostic, Path(path))
                self.diagnostic_status.set("Diagnosebericht gespeichert. Diesen eigenen Bericht zur Auswertung schicken; dein Freund braucht keinen Durchlauf zu starten.")
            except (OSError, TypeError, ValueError) as exc:
                messagebox.showerror("Diagnosebericht", str(exc), parent=self.root)

    def prepare(self):
        values = (self.game.get(), self.saves.get(), self.role.get(), self.host.get(), self.code.get())
        self.status.set("Testdateien werden geprüft, bisherige Dateien gesichert und die Testsave kopiert …")
        def prepare_build():
            if diagnostics.diagnostic_status(values[0]).get("installed"):
                raise ValueError("Zuerst TF2 schließen und die Diagnoseinstallation wiederherstellen.")
            return workflow.prepare(*values)
        self._work(prepare_build, self._prepared)

    def _prepared(self, prepared):
        self.prepared = self.last_run = prepared
        self.save_name.set(Path(prepared.imported_save).name)
        self.status.set("Vorbereitet. Host-IP und Sitzungscode an den Freund geben. Dann auf beiden PCs 'Verbinden & Test bereitstellen'.")
        self._save_settings()
        self._buttons()

    def connect(self):
        try:
            self.controller = workflow.SessionController(self.prepared)
            self.controller.start()
            self.status.set("Verbindung wird aufgebaut …")
            self._buttons()
        except Exception as exc:
            if self.controller and not self.controller.started and not self.controller.alive():
                self.controller = None
            self._buttons()
            self.status.set(str(exc))
            messagebox.showerror("Verbindung konnte nicht starten", str(exc), parent=self.root)

    def start_game(self):
        # Only a direct user click reaches the Steam protocol handler. The
        # developer's tests never call this method or control a game window.
        try:
            if not self.controller or self.controller.stopping:
                raise ValueError("Zuerst beide Spieler verbinden.")
            progress = workflow.read_json(self.prepared.directory / "peer-progress.json") or {}
            if progress.get("state") != "waiting_game":
                raise ValueError("Bitte auf die Startfreigabe im Launcher warten.")
            if game_is_running():
                self.status.set("TF2 läuft bereits. Dort den angezeigten Testspielstand mit der Testmod laden.")
                return
            os.startfile("steam://rungameid/1066780")
            self.game_button.configure(state="disabled")
        except Exception as exc:
            messagebox.showerror("Spielstart", str(exc), parent=self.root)

    def stop(self):
        if self.controller:
            self.controller.stop()
            self.status.set("Messcontroller werden geordnet beendet. Ein laufender Abschluss kann bis zu 30 Sekunden dauern.")
            self.game_button.configure(state="disabled")

    def restore(self):
        game = self.game.get()
        if self.last_run and not self.controller:
            self.last_run.stop_path.write_text("restore requested\n", encoding="ascii")
        self.status.set("Bisherige Installation wird geprüft und wiederhergestellt …")
        self.diagnostic_status.set("Bisherige Installation wird geprüft und wiederhergestellt …")
        def restore_all():
            diagnostics.restore_diagnostic(game)
            return workflow.restore_probe(game)
        self._work(restore_all, self._restored)

    def _restored(self, result):
        self.prepared = self.controller = None
        self.diagnostic = None
        if self.role.get() == "a":
            self.code.set(workflow.new_code())
        self.status.set("Bisherige Installation wiederhergestellt. Testsave-Kopien und Berichte bleiben erhalten. Für einen neuen Test neuen Code teilen.")
        self.diagnostic_status.set("Bisherige Installation wiederhergestellt. Diagnosespielstand und Bericht bleiben erhalten.")
        self.network.set("Mitspieler: nicht verbunden")
        self.engine.set("Spielkontakt: beendet")
        self.progress_text.set("Messung: beendet")
        self.bar["value"] = 0
        self.game_button.configure(state="disabled")
        self._buttons()

    def export(self):
        prepared = self.prepared or self.last_run
        if not prepared:
            messagebox.showinfo("Testbericht", "Bitte zuerst einen Test vorbereiten.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Testbericht speichern", defaultextension=".zip",
                initialfile=f"TF2-{workflow.VERSION.split('-', 1)[0]}-Bericht-{prepared.role}-{datetime.now():%Y%m%d-%H%M%S}.zip", filetypes=[("ZIP", "*.zip")])
        if path:
            try:
                workflow.export_diagnostics(prepared, path)
                self.status.set("Testbericht gespeichert. Für die Auswertung die Berichte von beiden PCs schicken.")
            except Exception as exc:
                messagebox.showerror("Testbericht", str(exc), parent=self.root)

    def guide(self):
        path = workflow.package_directory() / "Anleitung.html"
        if not path.is_file():
            path = workflow.resources() / "prototype/ANLEITUNG.html"
        try:
            os.startfile(str(path))
        except OSError as exc:
            messagebox.showerror("Anleitung", str(exc), parent=self.root)

    def tick(self):
        try:
            while True:
                done, value, error = self.events.get_nowait()
                if done == self._update_progress:
                    done(value)
                    continue  # Progress does not unlock Prepare during download.
                self.busy = False
                if error:
                    self.status.set(error)
                    self.diagnostic_status.set(error)
                    messagebox.showerror(workflow.VERSION, error, parent=self.root)
                else:
                    done(value)
                if self.closing_for_update:
                    return
                self._buttons()
        except queue.Empty:
            pass
        if self.controller:
            try:
                status = self.controller.poll()
                self.status.set(workflow.describe_status(status))
                connected = status["lobby"].get("state") == "connected"
                self.network.set("Mitspieler: verbunden · gleiche Testdateien" if connected else "Mitspieler: Verbindung wartet / beendet")
                peer = status["peer"]
                native = peer.get("native") or {}
                contact = bool(native.get("outer_calls")) or peer.get("state") in ("waiting_peer", "running", "completed")
                self.engine.set("Spielkontakt: Test angehalten" if peer.get("state") == "halted" else
                                "Spielkontakt: vorhanden" if contact else "Spielkontakt: wartet auf TF2 und Testmod")
                self.progress_text.set("Bautest: abgeschlossen · begrenzte Prüfung" if status["completed"] else
                                       f"Messung: Runde {status['round']} / {workflow.ROUNDS}")
                self.bar["value"] = workflow.ROUNDS if status["completed"] else status["round"]
                self.game_button.configure(state="normal" if peer.get("state") == "waiting_game" and not status["stopping"] else "disabled")
                self._buttons()
            except Exception as exc:
                self.controller.stop()
                self.status.set("Launcher hat angehalten: " + str(exc))
                self.game_button.configure(state="disabled")
        self._poll_diagnostic()
        self.root.after(400, self.tick)

    def close(self):
        if self.busy:
            self.status.set("Bitte die laufende Dateivorbereitung / Wiederherstellung noch abschließen lassen.")
            return
        if self.controller:
            self.controller.stop()
        self._save_settings()
        self.root.destroy()


def main(*, skip_update=False):
    root = tk.Tk()
    App(root, skip_update=skip_update)
    root.mainloop()


if __name__ == "__main__":
    main()
