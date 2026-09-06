"""Read-only native diagnostics. A network connection is not proof of world sync."""
from pathlib import Path
import time


def read_status(directory: Path, role: str, process_id: int, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    instance, port = ("a", 7771) if role == "host" else ("b", 7772)
    result = {"ready": False, "level": "waiting", "text": "Warte auf native Mod-Anbindung …"}
    try:
        with (directory / "tpf2_instance.txt").open("r", encoding="ascii") as stream:
            identity = stream.read(1024).splitlines()
        details = dict(line.split("=", 1) for line in identity[1:] if "=" in line)
        if not identity or identity[0] != instance or details.get("pid") != str(process_id):
            return result
        if details.get("port") != str(port):
            return {**result, "level": "error", "text": f"Spielport {port} nicht gebunden. Beide Spiele schließen und Portkonflikt beheben."}
        result["ready"] = True
        with (directory / f"lockstep_dash_{instance}.txt").open("r", encoding="utf-8", errors="replace") as stream:
            text = stream.read(32769)
        if len(text) > 32768:
            raise ValueError("dashboard too large")
        values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("ev="))
        wall = float(values.get("wall", "0"))
        # A stopped simulation produces no new comparison stamps. Its last
        # observed divergence remains unresolved, even when the comparison is
        # older than the freshness window; pause must not erase the warning.
        if values.get("comparison_match") == "no" or values.get("verdict", "").startswith("DESYNC"):
            return {**result, "level": "error", "text": "WELT ABGEWICHEN — letzte Abweichung weiterhin ungeklärt. Beide pausieren und vom selben Ausgangsspielstand neu starten."}
        gap_times = {}
        for item in values.get("money_gap_wall", "-").split(","):
            if ":" in item:
                peer, epoch = item.split(":", 1)
                if epoch not in ("", "-"):
                    gap_times[peer] = float(epoch)
        money_checked = False
        for item in values.get("money_gap", "-").split(","):
            parts = item.split(":")
            if len(parts) != 3 or gap_times.get(parts[0], 0) <= 0:
                continue
            if parts[1] == "-" or parts[2] == "-":
                continue
            if float(parts[1]) != 0 or float(parts[2]) != 0:
                return {**result, "level": "error", "text": f"FIRMENKASSE ABGEWICHEN — zuletzt Geld {parts[1]}, Kredit {parts[2]}. Beide pausieren; Logs sichern."}
            if -2 <= now - gap_times[parts[0]] <= 15:
                money_checked = True
        if not -2 <= now - wall <= 6:
            return {**result, "text": "Kein frischer Spielstatus. Spielstand mit beiden Mods laden; Log prüfen, falls er bereits geladen ist."}
        if values.get("peers", "") in ("", "-", "none"):
            return {**result, "level": "warning", "text": "Spiel meldet keinen aktiven Mitspieler. Jetzt pausieren und nicht weiterbauen."}
        raw_comparison_wall = values.get("comparison_wall", "-")
        comparison_wall = 0.0 if raw_comparison_wall in ("", "-") else float(raw_comparison_wall)
        if comparison_wall == 0 or not -2 <= now - comparison_wall <= 15:
            return {**result, "text": "Spielkontakt vorhanden; noch kein aktueller gemeinsamer Weltvergleich."}
        if float(values.get("applylate", "0")) > 0:
            return {**result, "level": "warning", "text": f"Befehle wurden verspätet ausgeführt ({values['applylate']}). Gleiche Stichproben bestätigen danach keinen synchronen Spielverlauf."}
        if values.get("comparison_match") == "yes":
            return {**result, "level": "info", "text": "Letzte Stichprobe: Bauzustand, Fahrzeuganzahl und Firmenkasse gleich. Gesamte Simulation unbestätigt." if money_checked else "Letzter Bauzustandsvergleich gleich; Firmenkasse noch nicht gemeinsam geprüft."}
        return result
    except (OSError, ValueError, UnicodeError):
        return result
