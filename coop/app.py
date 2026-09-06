"""Desktop launcher. Tk stays on its own thread; socket and disk work do not."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .bridge import Mailbox
from .install import discover_game, install_mod
from .net import RelayClient, RelayServer
from .session import export_save, save_manifest

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("TF2COOP_DATA_DIR", str(Path(os.environ.get("LOCALAPPDATA", str(ROOT / "runtime"))) / "TF2Coop")))


class Connection:
    def __init__(self, events: queue.Queue, mailbox: Mailbox):
        self.events, self.mailbox = events, mailbox
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.client = None
        self.server = None
        self.pump = None
        self.transition = asyncio.Lock()
        self.snapshots = queue.Queue(maxsize=1)

    def connect(self, config: dict, manifest: dict):
        return asyncio.run_coroutine_threadsafe(self._connect(config, manifest), self.loop)

    async def _connect(self, config, manifest):
        async with self.transition:
            await self._connect_locked(config, manifest)

    async def _connect_locked(self, config, manifest):
        await self._disconnect_locked()
        try:
            if config["role"] == "host":
                self.server = RelayServer(config["token"], manifest, host=config.get("bind", "0.0.0.0"), port=config.get("port", 34197))
                await self.server.start()
            host = "127.0.0.1" if self.server else config["peer_ip"]
            port = self.server.port if self.server else config.get("port", 34197)
            self.client = RelayClient(host, port, config["token"], config["name"], manifest,
                                      on_snapshot=self._snapshot)
            await self.client.connect()
            self.pump = asyncio.create_task(self._pump())
            self.events.put(("connected", config))
        except Exception:
            await self._disconnect_locked()
            raise

    def _snapshot(self, snapshot):
        # A single latest snapshot avoids GUI backlog after window dragging.
        self.latest = snapshot

    async def _io(self, function, *args):
        # Cancelling to_thread does not cancel its OS write. Finish that write
        # before a disconnect is allowed to publish the final offline snapshot.
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _pump(self):
        try:
            while self.client and self.client.connected:
                game = await self._io(self.mailbox.read_game)
                error = self.mailbox.last_error
                presence = {"cursor": game.get("cursor"), "preview": game.get("preview")} if game else {"cursor": None, "preview": None}
                await self.client.send_presence(presence)
                snapshot = self.client.snapshot or {"peers": []}
                peerfile = {"connected": True, "local_peer_id": self.client.peer_id or "", "peers": snapshot.get("peers", [])}
                await self._io(self.mailbox.write_peers, peerfile)
                try:
                    self.snapshots.get_nowait()
                except queue.Empty:
                    pass
                self.snapshots.put_nowait((snapshot, game, error))
                await asyncio.sleep(0.1)
            if self.client:
                self.events.put(("network_error", self.client.last_error or "Verbindung beendet."))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.events.put(("network_error", str(exc)))
        finally:
            await self._io(self.mailbox.write_peers, {"connected": False, "local_peer_id": "", "peers": []})

    async def _disconnect(self):
        async with self.transition:
            await self._disconnect_locked()

    async def _disconnect_locked(self):
        if self.pump:
            self.pump.cancel()
            try:
                await self.pump
            except asyncio.CancelledError:
                pass
            self.pump = None
        if self.client:
            await self.client.close()
            self.client = None
        if self.server:
            await self.server.close()
            self.server = None
        await self._io(self.mailbox.write_peers, {"connected": False, "local_peer_id": "", "peers": []})
        try:
            self.snapshots.get_nowait()
        except queue.Empty:
            pass

    def disconnect(self):
        return asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)


class App:
    def __init__(self, window: tk.Tk):
        self.window = window
        window.title("Transport Fever 2 · Gemeinsam bauen · Alpha 3")
        window.geometry("1040x790")
        window.minsize(1040, 790)
        window.configure(bg="#101b28")
        self.events = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.mailbox = Mailbox(STATE / "mailbox")
        self.connection = Connection(self.events, self.mailbox)
        self.connected = False
        self.busy = False
        self.peers = []
        self.process = None
        self.data_dir = None
        self.session_config = None
        self.session_manifest = None
        self.latest_game = None
        self.last_dash = 0.0
        self.native_status = tk.StringVar(value="Native Simulation: noch kein Spiel gestartet.")
        self.game_path = tk.StringVar(value=str(discover_game() or ""))
        self.name = tk.StringVar(value="Spieler")
        self.role = tk.StringVar(value="host")
        self.peer_ip = tk.StringVar()
        self.token = tk.StringVar(value=secrets.token_urlsafe(24))
        self.save_path = tk.StringVar()
        self.status = tk.StringVar(value="Bereit · LAN / Hamachi · zwei Spieler")
        self.game_status = tk.StringVar(value="Noch kein laufendes Spiel verbunden.")
        self._styles()
        self._layout()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.after(100, self.poll)

    def _styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#101b28")
        style.configure("Card.TFrame", background="#18283a")
        style.configure("TLabel", background="#101b28", foreground="#e5eef6", font=("Segoe UI", 10))
        style.configure("Small.TLabel", foreground="#9eb2c7", font=("Segoe UI", 9))
        style.configure("Error.TLabel", foreground="#ff9e9e", font=("Segoe UI Semibold", 10))
        style.configure("Warning.TLabel", foreground="#ffd084", font=("Segoe UI Semibold", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 25))
        style.configure("TButton", background="#29435d", foreground="#f3f8ff", borderwidth=0, padding=(12, 9), font=("Segoe UI Semibold", 10))
        style.map("TButton", background=[("active", "#365c7c"), ("disabled", "#1f3042")], foreground=[("disabled", "#74889b")])
        style.configure("Go.TButton", background="#28796b")
        style.map("Go.TButton", background=[("active", "#379584"), ("disabled", "#233e3d")])
        style.configure("TEntry", fieldbackground="#213449", foreground="#f2f7ff", insertcolor="white", padding=7)
        style.configure("TRadiobutton", background="#101b28", foreground="#dce7f2", font=("Segoe UI", 10))
        style.map("TRadiobutton", background=[("active", "#101b28")])

    def _layout(self):
        box = ttk.Frame(self.window, padding=28)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="GEMEINSAME FIRMA  /  EXPERIMENTELLE ALPHA", style="Small.TLabel").pack(anchor="w")
        ttk.Label(box, text="Zusammen auf einer Karte.", style="Title.TLabel").pack(anchor="w", pady=(3, 9))
        ttk.Label(box, text="Koop über LAN oder Hamachi · freie Kameras · farbige Positionen und Planung").pack(anchor="w")
        ttk.Label(box, text="Experimentell: Zeit, Fahrzeuge und Firmenkasse können auseinanderlaufen. Einen separaten Testspielstand nutzen.", style="Small.TLabel").pack(anchor="w", pady=(7, 20))
        form = ttk.Frame(box)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.entries = []

        def field(row, label, variable, button=None, action=None, show=None):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 18), pady=5)
            entry = ttk.Entry(form, textvariable=variable, show=show or "")
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            self.entries.append(entry)
            if button:
                ttk.Button(form, text=button, command=action).grid(row=row, column=2, sticky="ew", padx=(10, 0))

        field(0, "Spielordner", self.game_path, "Auswählen", self.choose_game)
        field(1, "Dein Name", self.name)
        modes = ttk.Frame(form)
        modes.grid(row=2, column=1, sticky="w", pady=7)
        ttk.Radiobutton(modes, text="Firma hosten", variable=self.role, value="host").pack(side="left", padx=(0, 22))
        ttk.Radiobutton(modes, text="Freund beitreten", variable=self.role, value="guest").pack(side="left")
        ttk.Label(form, text="Deine Rolle").grid(row=2, column=0, sticky="w")
        field(3, "Hamachi-/LAN-IP des Freundes", self.peer_ip)
        field(4, "Gemeinsamer Sitzungsschlüssel", self.token, "Kopieren", self.copy_token, show="•")
        field(5, "Gemeinsamer Ausgangsspielstand", self.save_path, ".sav wählen", self.choose_save)
        ttk.Label(box, text="Beide wählen exakt dieselbe .sav + .sav.lua. Der Freund übernimmt den Schlüssel des Hosts.\nZusätzliche Mods und DLCs müssen auf beiden PCs übereinstimmen.", style="Small.TLabel").pack(anchor="w", pady=(6, 14))
        actions = ttk.Frame(box)
        actions.pack(fill="x")
        self.install_button = ttk.Button(actions, text="1  Mod installieren", command=self.install)
        self.install_button.pack(side="left", padx=(0, 8))
        self.connect_button = ttk.Button(actions, text="2  Verbinden", command=self.connect, style="Go.TButton")
        self.connect_button.pack(side="left", padx=(0, 8))
        self.launch_button = ttk.Button(actions, text="3  Koop-Spiel starten", command=self.launch, state="disabled", style="Go.TButton")
        self.launch_button.pack(side="left")
        ttk.Button(actions, text="Spielstand als ZIP", command=self.export).pack(side="right")
        ttk.Label(box, textvariable=self.status).pack(anchor="w", pady=(17, 3))
        ttk.Label(box, textvariable=self.game_status, style="Small.TLabel", wraplength=950).pack(anchor="w", pady=(0, 10))
        self.native_label = ttk.Label(box, textvariable=self.native_status, wraplength=950)
        self.native_label.pack(anchor="w", pady=(0, 10))
        self.canvas = tk.Canvas(box, height=140, background="#152536", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(20, 25, text="MIT­SPIELER & PLANUNG", anchor="w", fill="#95b3cd", font=("Segoe UI Semibold", 10))
        self.canvas.create_text(20, 60, text="Nach dem Verbinden erscheinen hier eure Namen und aktuellen Baupositionen.", anchor="w", fill="#d7e4ef")
        footer = ttk.Frame(box)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="Anleitung", command=lambda: os.startfile(str(ROOT / "README.md"))).pack(side="left")
        ttk.Button(footer, text="Native Erweiterung entfernen", command=self.uninstall).pack(side="left", padx=8)
        ttk.Label(footer, text="Koop-Basis: silver2127 / MIT · keine Steam-Einladungen", style="Small.TLabel").pack(side="right")

    def work(self, operation, event):
        if self.busy:
            return
        self.busy = True
        self.refresh_buttons()
        future = self.pool.submit(operation)

        def done(result):
            try:
                self.events.put((event, result.result()))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        future.add_done_callback(done)

    def choose_game(self):
        if self.connected:
            return
        path = filedialog.askdirectory(title="Transport Fever 2 Spielordner")
        if path:
            self.game_path.set(path)

    def choose_save(self):
        if self.connected:
            return
        path = filedialog.askopenfilename(title="Gemeinsamen Ausgangsspielstand wählen", filetypes=[("TF2-Spielstand", "*.sav")])
        if path:
            self.save_path.set(path)

    def copy_token(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(self.token.get())
        self.status.set("Sitzungsschlüssel kopiert. Nur mit deinem Mitspieler teilen.")

    def install(self):
        if self.connected or self.running():
            return
        game = Path(self.game_path.get())

        def operation():
            from .native import install_native
            target = install_native(game, ROOT / "native" / "out", ROOT / "upstream" / "tpf2-multiplayer" / "mod" / "mp_lockstep_1")
            install_mod(game, ROOT / "mod" / "tf2coop_1", self.mailbox.directory)
            return target
        self.status.set("Prüfe Spielversion und installiere mit Wiederherstellungskopie …")
        self.work(operation, "installed")

    def uninstall(self):
        if self.connected or self.running():
            messagebox.showinfo("Erst beenden", "Bitte zuerst das Koop-Spiel schließen und die Verbindung trennen.")
            return
        game = Path(self.game_path.get())
        self.work(lambda: __import__("coop.native", fromlist=["uninstall_native"]).uninstall_native(game), "uninstalled")

    def export(self):
        if not self.save_path.get():
            self.choose_save()
        if not self.save_path.get():
            return
        path = filedialog.asksaveasfilename(title="Spielstand-Paket speichern", defaultextension=".zip", filetypes=[("ZIP", "*.zip")], initialfile="TF2-Gemeinsamer-Spielstand.zip")
        if path:
            source = Path(self.save_path.get())
            self.work(lambda: export_save(source, Path(path)), "exported")

    def connect(self):
        if self.running():
            messagebox.showinfo("Spiel läuft", "Bitte zuerst das Koop-Spiel beenden. Ein Verbindungswechsel braucht einen gemeinsamen Neustart.")
            return
        if self.connected:
            self.connection.disconnect()
            self.connected = False
            self.peers = []
            self.status.set("Verbindung getrennt.")
            self.refresh_buttons()
            return
        try:
            address = str(ipaddress.IPv4Address(self.peer_ip.get().strip()))
            name = self.name.get().strip()
            if not name or len(name) > 32:
                raise ValueError("Der Name muss 1–32 Zeichen lang sein.")
            if len(self.token.get()) < 16:
                raise ValueError("Bitte den vollständigen Sitzungsschlüssel des Hosts verwenden (mindestens 16 Zeichen).")
            config = {"role": self.role.get(), "peer_ip": address, "name": name, "token": self.token.get(), "game_dir": self.game_path.get(), "save_path": self.save_path.get()}
        except ValueError as exc:
            messagebox.showerror("Eingabe prüfen", str(exc))
            return

        def operation():
            manifest = save_manifest(Path(config["save_path"]), ROOT)
            self.session_manifest = manifest
            self.connection.connect(config, manifest).result(timeout=15)
        self.status.set("Prüfe Ausgangsspielstand und verbinde …")
        self.work(operation, "connection_finished")

    def launch(self):
        if not self.connected or len(self.peers) != 2 or self.running():
            return
        config = dict(self.session_config)

        def operation():
            from .native import prepare_session, install_native
            from .launch import LaunchLease, TrackedGame, filetime_now
            game = Path(config["game_dir"])
            if save_manifest(Path(config["save_path"]), ROOT) != self.session_manifest:
                raise ValueError("Spielstand oder Modpaket wurde nach dem Verbinden verändert. Neu verbinden.")
            # The manifest covers this package; ensure the game loads precisely
            # that package, including on PCs with a previous intact installation.
            install_native(game, ROOT / "native" / "out", ROOT / "upstream" / "tpf2-multiplayer" / "mod" / "mp_lockstep_1")
            install_mod(game, ROOT / "mod" / "tf2coop_1", self.mailbox.directory)
            data_dir = STATE / "sessions" / (time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3))
            result = prepare_session(game, data_dir, config["role"], config["peer_ip"])
            env = os.environ.copy()
            env.update(result["env"])
            directory = Path(result["data_dir"])
            executable = game / "TransportFever2.exe"
            lease = LaunchLease.create(executable, directory)
            started = filetime_now()
            try:
                process = subprocess.Popen([str(executable)], cwd=game, env=env)
            except Exception:
                lease.revoke()
                raise
            return (TrackedGame(process, directory, executable, lease, started), directory)
        self.work(operation, "launched")

    def running(self):
        return self.process is not None and self.process.poll() is None

    def refresh_buttons(self):
        self.connect_button.configure(text="Verbindung trennen" if self.connected else "2  Verbinden", state="disabled" if self.busy else "normal")
        self.install_button.configure(state="disabled" if self.busy or self.connected or self.running() else "normal")
        self.launch_button.configure(state="normal" if self.connected and len(self.peers) == 2 and not self.busy and not self.running() else "disabled")
        for entry in self.entries:
            entry.configure(state="disabled" if self.connected or self.busy else "normal")

    def draw_peers(self):
        self.canvas.delete("all")
        self.canvas.create_text(20, 22, text="MIT­SPIELER & PLANUNG", anchor="w", fill="#95b3cd", font=("Segoe UI Semibold", 10))
        for i, peer in enumerate(self.peers):
            y = 58 + i * 32
            self.canvas.create_oval(20, y - 5, 30, y + 5, fill=peer["color"], outline="")
            presence = peer.get("presence", {})
            cursor = presence.get("cursor")
            preview = presence.get("preview")
            activity = (f"x {cursor[0]:.0f} · y {cursor[1]:.0f}" if cursor else "wartet auf Spiel")
            if preview:
                activity += "  ·  plant " + {"street": "Straße", "track": "Gleis", "construction": "Gebäude", "bulldozer": "Abriss"}.get(preview["kind"], preview["kind"])
            self.canvas.create_text(43, y, text=peer["name"], anchor="w", fill=peer["color"], font=("Segoe UI Semibold", 11))
            self.canvas.create_text(290, y, text=activity, anchor="w", fill="#cfdfed", font=("Segoe UI", 10))

    def poll(self):
        try:
            self.events.put(("snapshot", self.connection.snapshots.get_nowait()))
        except queue.Empty:
            pass
        try:
            while True:
                event, value = self.events.get_nowait()
                if event in {"installed", "uninstalled", "exported", "connection_finished", "launched", "error"}:
                    self.busy = False
                if event == "error":
                    self.status.set("Aktion fehlgeschlagen.")
                    messagebox.showerror("TF2 Co-op", value)
                elif event == "installed":
                    self.status.set("Installiert. Im Testspielstand „MP Lockstep“ und „TF2 Co-op“ aktivieren und speichern.")
                elif event == "uninstalled":
                    self.status.set("Native Erweiterung entfernt; ursprüngliche Audio-DLL wiederhergestellt.")
                elif event == "exported":
                    self.status.set(f"Spielstand-Paket gespeichert: {value}")
                elif event == "connected":
                    self.connected = True
                    self.session_config = value
                    self.status.set("Verbunden · warte auf zweiten Spieler mit identischem Ausgangsspielstand.")
                elif event == "snapshot":
                    snapshot, game, error = value
                    if self.connected:
                        self.peers = snapshot.get("peers", [])
                        self.latest_game = game
                        self.status.set(f"{len(self.peers)} / 2 Spieler verbunden · Ausgangsspielstände stimmen überein" if len(self.peers) == 2 else "1 / 2 Spieler verbunden · warte auf deinen Freund")
                        if len(self.peers) > 2:
                            self.status.set("Diese Koop-Version unterstützt genau zwei Spieler. Weitere Verbindungen bitte trennen.")
                        self.game_status.set(game.get("status", "Mod meldet Positionsdaten.") if game else "Warte auf Spiel: beide Mods im identischen Ausgangsspielstand aktivieren und diesen laden.")
                        self.draw_peers()
                elif event == "network_error":
                    self.connected = False
                    self.peers = []
                    self.connection.disconnect()
                    self.status.set("Verbindung verloren: " + value)
                    if self.running():
                        self.game_status.set("Spiel jetzt pausieren. Für die nächste Sitzung beide vom selben gespeicherten Stand neu starten.")
                elif event == "launched":
                    self.process, self.data_dir = value
                    self.status.set("Spiel gestartet. Beide Spieler laden jetzt manuell den ausgewählten Ausgangsspielstand.")
                    messagebox.showinfo("Gemeinsamen Stand laden", "Im Spiel: Spiel laden → den gewählten Ausgangsspielstand laden.\n\nAuf beiden PCs müssen MP Lockstep und TF2 Co-op aktiv sein. Erst bauen, wenn beide geladen sind und die Spielanzeige die Verbindung bestätigt.")
                self.refresh_buttons()
        except queue.Empty:
            pass
        if self.process is not None and self.process.poll() is not None:
            startup_failed = self.process.startup_failed
            self.process = None
            self.status.set("Spielstart nicht bestätigt. Beide Spiele schließen und aus dem aktuellen Launcher neu starten." if startup_failed else "Spiel beendet. Für eine weitere Sitzung einen gemeinsamen gespeicherten Stand wählen und neu verbinden.")
            self.connection.disconnect()
            self.connected = False
            self.peers = []
            self.refresh_buttons()
        if self.running() and self.data_dir and time.monotonic() - self.last_dash >= 1:
            from .diagnostics import read_status
            self.last_dash = time.monotonic()
            report = read_status(self.data_dir, self.session_config["role"], self.process.pid)
            self.native_status.set(report["text"])
            self.native_label.configure(style={"error": "Error.TLabel", "warning": "Warning.TLabel"}.get(report["level"], "TLabel"))
        self.window.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("Vorgang läuft", "Bitte warten, bis der aktuelle Installations- oder Startvorgang abgeschlossen ist.")
            return
        if self.running():
            messagebox.showinfo("Koop läuft", "Bitte zuerst Transport Fever 2 beenden. Der Launcher hält eure Positionsanzeigen aktuell.")
            return
        self.connection.disconnect()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()


def main():
    if "--self-test" in sys.argv:
        from .native import check_game_build, VERSION
        from .launch import process_info
        destination = Path(sys.argv[sys.argv.index("--self-test") + 1])
        game = discover_game()
        output = {"imports": "ok", "version": VERSION, "process_identity": process_info(os.getpid()) is not None,
                  "package_root": str(ROOT), "game": check_game_build(game) if game else None,
                  "payload": all((ROOT / f).is_file() for f in ("README.md", "mod/tf2coop_1/mod.lua", "native/out/alut.dll", "native/out/tpf2_bridge_mp.dll", "native/out/tpf2_slice.dll", "upstream/tpf2-multiplayer/mod/mp_lockstep_1/mod.lua"))}
        destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
        return
    if sys.platform != "win32":
        raise SystemExit("Der native Koop-Launcher benötigt Windows.")
    window = tk.Tk()
    App(window)
    window.mainloop()
