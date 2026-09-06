"""Fingerprint precisely selected initial saves; never infer a running world match."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_manifest(save_path: Path, root: Path) -> dict[str, str]:
    save_path = Path(save_path)
    if save_path.suffix.lower() != ".sav" or not save_path.is_file():
        raise ValueError("Bitte einen vorhandenen .sav-Spielstand auswählen.")
    sidecar = Path(str(save_path) + ".lua")
    if not sidecar.is_file():
        raise ValueError("Die zugehörige .sav.lua fehlt. Beide Dateien werden benötigt.")
    digest = hashlib.sha256()
    for part in (save_path, sidecar):
        digest.update(bytes.fromhex(hash_file(part)))
    code = hashlib.sha256(b"tf2coop-protocol-1")
    for folder in (root / "mod", root / "native" / "out", root / "upstream" / "tpf2-multiplayer" / "mod" / "mp_lockstep_1"):
        if not folder.is_dir():
            raise ValueError(f"Paket unvollständig: {folder}")
        for file in sorted(folder.rglob("*")):
            if file.is_file() and file.suffix in (".lua", ".dll") and file.name != "config.lua":
                code.update(file.relative_to(root).as_posix().encode("utf-8"))
                code.update(bytes.fromhex(hash_file(file)))
    return {"map_fingerprint": digest.hexdigest(), "mod_fingerprint": code.hexdigest()}


def export_save(save_path: Path, destination: Path) -> Path:
    """User-directed export, with bounded extra content and no automatic upload."""
    save_path, destination = Path(save_path), Path(destination)
    sidecar = Path(str(save_path) + ".lua")
    if not save_path.is_file() or save_path.suffix.lower() != ".sav" or not sidecar.is_file():
        raise ValueError("Es werden eine .sav und die zugehörige .sav.lua benötigt.")
    if destination.exists():
        raise FileExistsError("Die Zieldatei existiert bereits. Bitte einen neuen Namen wählen.")
    files = [save_path, sidecar]
    preview = save_path.with_suffix(".jpg")
    if preview.is_file():
        files.append(preview)
    hashes = {f.name: hash_file(f) for f in files}
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                for file in files:
                    archive.write(file, file.name)
                archive.writestr("SHA256.json", json.dumps(hashes, indent=2))
                archive.writestr("LESEN.txt", "Beide Spielstanddateien (.sav und .sav.lua) in deinen TF2-save-Ordner kopieren.\nVorhandene Dateien nicht überschreiben. Im Spiel denselben Stand laden.\nZusätzliche Mods und DLCs müssen auf beiden PCs dieselben Versionen haben.\n")
    except Exception:
        if created and destination.is_file():
            destination.unlink()
        raise
    return destination
