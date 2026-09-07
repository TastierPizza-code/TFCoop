"""Prepare a fresh, reviewable TF2 measurement payload; never install or start it.

The selected game and save are only read. Preparation is safe while TF2 is open;
the separate measurement runner requires a fresh game process before activation.
The manifest binds selected files and supplied bindings, not the world actually
loaded later. Neither an equal manifest nor this stage operation proves sync.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil

from coop import native
from coop.install import InstallError, _files, _lua_string
from coop.session import hash_file
from .core import MAX_INT, MAX_MESSAGE_BYTES, canonical_json, decode_message, digest


ROOT = Path(__file__).resolve().parents[2]
MOD = "tf2_strict_probe_1"
CONFIG = "res/scripts/tf2_strict_probe/config.lua"
API_AUDIT = "res/scripts/tf2_strict_probe/api_audit.lua"
# GENERATED COPY CONTRACT: edit the solo collector, then copy its complete bytes
# to API_AUDIT. Package build/self-check reject drift; no cross-mod runtime require.
SOLO_API_AUDIT = "prototype/mod/tf2_api_audit_1/res/scripts/tf2_api_audit/probe.lua"
REQUIRED_MOD_FILES = {
    "mod.lua", CONFIG, "res/scripts/tf2_strict_probe/json.lua",
    "res/scripts/tf2_strict_probe/engine.lua", "res/config/game_script/tf2_strict_probe.lua",
    API_AUDIT,
}
REQUIRED_PYTHON = {"core.py", "replica.py", "transport.py", "runner.py",
                   "engine_mailbox.py", "game_runner.py", "stage_probe.py", "build_profile.py",
                   "timing_probe.py", "stream_probe.py", "stream_engine.py", "live_probe.py", "live_input.py"}
PROFILES = {"time_v1", "build_v2"}
REQUIRED_BUILD_FILES = {"res/scripts/tf2_strict_probe/build_engine.lua",
                        "res/scripts/tf2_strict_probe/build_assets.lua",
                        "res/construction/tf2_strict_probe/road_test.con"}
KEY = re.compile(r"[A-Za-z0-9_:.-]{1,96}\Z")
KINDS = {"depot", "vehicle", "line", "station_group", "road"}
LEASE_PATH_LIMIT = 220  # launch_lease.h: strictly shorter than MAX_PATH - 40.


class StageError(ValueError):
    """Preparation refused before producing an activatable setup."""


def read_templates(path: Path | None) -> dict:
    """Read explicit existing-save references; never invent asset/model defaults."""
    value = {"initial_bindings": []}
    if path is not None:
        with Path(path).open("rb") as file:
            value = decode_message(file.read(MAX_MESSAGE_BYTES + 1))
    if set(value) != {"initial_bindings"} or type(value["initial_bindings"]) is not list:
        raise StageError("Templates require exactly an initial_bindings array.")
    bindings = value["initial_bindings"]
    if len(bindings) > 64:
        raise StageError("At most 64 tracked objects are supported.")
    keys, entities, derived = set(), set(), set()
    for binding in bindings:
        if type(binding) is not dict or set(binding) != {"logical_id", "kind", "entity"}:
            raise StageError("Each binding requires logical_id, kind and an actual saved entity ID.")
        key, kind, entity = binding["logical_id"], binding["kind"], binding["entity"]
        if type(key) is not str or not KEY.fullmatch(key) or key in keys:
            raise StageError("Logical IDs must be unique bounded semantic keys.")
        if type(kind) is not str or kind not in KINDS:
            raise StageError("Unsupported binding kind.")
        if type(entity) is not int or not 1 <= entity <= 2147483647 or entity in entities:
            raise StageError("Saved entity IDs must be unique positive 32-bit integers.")
        keys.add(key)
        entities.add(entity)
        if kind == "depot":
            child = key + ":depot:1"
            if not KEY.fullmatch(child):
                raise StageError("Depot logical ID is too long for its actual depot child.")
            derived.add(child)
    if keys & derived or len(keys) + len(derived) > 64:
        raise StageError("Depot child bindings conflict or exceed the tracked-object limit.")
    # The controlled proof intentionally requires the same saved entity IDs.
    # A later portable binding protocol must use a new manifest version.
    return {"initial_bindings": sorted(bindings, key=lambda binding: binding["logical_id"])}


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def validate_lease_path(value: str | Path) -> None:
    """Match the proxy lease's Windows path ceiling before any activation.

    Windows wchar counts UTF-16 code units; an emoji can occupy two even though
    Python counts it as one character. Long/device paths are unsupported by the
    existing bounded loader and must not produce a silently ignored lease.
    """
    text = str(value)
    try:
        units = len(text.encode("utf-16-le", errors="strict")) // 2
    except UnicodeError as exc:
        raise StageError("Invalid Unicode in the prototype lease path.") from exc
    if (not Path(text).is_absolute() or "\0" in text or units >= LEASE_PATH_LIMIT
            or text.startswith(("\\\\?\\", "\\\\.\\"))):
        raise StageError("Prototype session and game executable paths must be absolute and shorter than 220 UTF-16 units.")


def _new_directory(value: str | Path, name: str, game: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise StageError(f"{name} must be an absolute path to a new directory.")
    if path.exists() or path.is_symlink():
        raise StageError(f"{name} already exists; use a fresh directory without old controls or status files.")
    result = path.resolve()
    if result != path.absolute():
        raise StageError(f"{name} must not pass through linked or noncanonical paths.")
    if _inside(result, game):
        raise StageError("Staging and session files must stay outside the game directory.")
    return result


def _source_file(path: Path) -> Path:
    if not path.is_file() or path.is_symlink() or path.resolve() != path.absolute():
        raise StageError(f"Missing or linked prototype source: {path}")
    return path


def verify_api_audit_copy(repository_root: Path = ROOT) -> str:
    """Require byte-identical solo/strict raw collectors in a distributable package.

    The strict mod owns its own required copy. Staging and runtime do not need the
    solo mod installed or enabled; this cross-check runs only on source/package
    resources to keep the intentionally copied collector from drifting.
    """
    root = Path(repository_root).absolute()
    copies = []
    for path in (root / SOLO_API_AUDIT, root / "prototype/mod" / MOD / API_AUDIT):
        with _source_file(path).open("rb") as source:
            data = source.read(1024 * 1024 + 1)
        if not data or len(data) > 1024 * 1024:
            raise StageError("Shared raw API collector is empty or oversized.")
        copies.append(data)
    if copies[0] != copies[1]:
        raise StageError("Shared raw API collector drift: copy the complete solo probe.lua bytes to the strict api_audit.lua resource.")
    return hashlib.sha256(copies[0]).hexdigest()


def _stock_audio(game: Path) -> Path:
    for path in (game / "alut_real.dll", game / "alut.dll",
                 game / native.STATE_DIR / "original" / "alut.dll"):
        if path.is_file() and hash_file(path) == native.STOCK_ALUT_SHA256:
            return path
    raise StageError("Verified original alut.dll audio library is missing; a proxy is not an original.")


def _config(session: Path, epoch: int, templates: dict, profile: str | None = None) -> str:
    if profile is not None and (type(profile) is not str or profile not in PROFILES):
        raise StageError("Unknown measurement profile.")
    entries = []
    for binding in templates["initial_bindings"]:
        entries.append("    { logical_id=" + _lua_string(binding["logical_id"]) +
                       ", kind=" + _lua_string(binding["kind"]) +
                       ", entity=" + str(binding["entity"]) + " },")
    return ("-- Generated only in the staging payload; no game installation was changed.\n"
            "return {\n  enabled = true,\n  epoch = " + _lua_string(str(epoch)) +
            ",\n  mailbox_dir = " + _lua_string(session.as_posix()) +
            ",\n  native_gate_required = true,\n" +
            ("  profile = " + _lua_string(profile) + ",\n" if profile is not None else "") +
            "  initial_bindings = {\n" +
            "\n".join(entries) + "\n  },\n}\n")


def _write_json(path: Path, value: dict) -> None:
    with path.open("xb") as file:
        file.write(canonical_json(value) + b"\n")


def stage_probe(*, game_dir: str | Path, save: str | Path, session: str | Path,
                output: str | Path, templates: str | Path | None = None,
                native_epoch: int | None = None, repository_root: Path = ROOT,
                profile: str | None = None) -> dict:
    """Create new staging/session artifacts only; no game process operation occurs.

    ``native_epoch`` and ``repository_root`` support reproducible preparation and
    offline fixture tests. Public CLI epochs are fresh random safe JSON integers.
    A failure after copying may leave an incomplete new output for inspection;
    probe_setup.json is written last and no existing directory is overwritten.
    """
    if profile is not None and (type(profile) is not str or profile not in PROFILES):
        raise StageError("Unknown measurement profile.")
    game = Path(game_dir).resolve()
    validate_lease_path(game / "TransportFever2.exe")
    destination = _new_directory(output, "Output", game)
    directory = _new_directory(session, "Session", game)
    validate_lease_path(directory)
    if _inside(directory, destination) or _inside(destination, directory):
        raise StageError("Session and output must be separate, nonnested new directories.")
    epoch = secrets.randbelow(MAX_INT) + 1 if native_epoch is None else native_epoch
    if type(epoch) is not int or not 0 < epoch <= MAX_INT:
        raise StageError("native_epoch must be a positive interoperable JSON integer.")
    build = native.check_game_build(game)
    if not build.get("compatible") or build.get("sha256") != native.EXPECTED_SHA256:
        raise StageError("The game executable is not the exact supported Windows build 35924.")
    save_path = Path(save).resolve()
    sidecar = Path(str(save_path) + ".lua")
    if save_path.suffix.lower() != ".sav" or not save_path.is_file() or not sidecar.is_file():
        raise StageError("An existing .sav and its matching .sav.lua are required.")
    selected = read_templates(Path(templates) if templates is not None else None)
    if profile == "build_v2" and selected["initial_bindings"]:
        raise StageError("The fixed build profile creates its own scene; template bindings cannot be mixed in.")
    root = Path(repository_root).resolve()
    mod_source = root / "prototype" / "mod" / MOD
    mod_hashes = _files(mod_source) if mod_source.is_dir() else {}
    if not REQUIRED_MOD_FILES <= mod_hashes.keys():
        raise StageError("Prototype Lua mod is incomplete; finish its build before staging.")
    if profile == "build_v2" and not REQUIRED_BUILD_FILES <= mod_hashes.keys():
        raise StageError("The controlled build recipe or its Lua engine is incomplete.")
    python_source = root / "prototype" / "strict_sync"
    python_files = {path.name: path for path in python_source.glob("*.py")}
    if not REQUIRED_PYTHON <= python_files.keys():
        raise StageError("Prototype coordinator and engine adapter sources are incomplete.")
    sources = {
        "alut.dll": _source_file(root / "prototype" / "native" / "out" / "probe_alut.dll"),
        "tf2_step_probe.dll": _source_file(root / "prototype" / "native" / "out" / "tf2_step_probe.dll"),
        "alut_real.dll": _stock_audio(game),
    }
    for relative in ("alut.dll", "tf2_step_probe.dll"):
        try:
            if not native._pe(sources[relative])["is_dll"]:
                raise ValueError("not a DLL")
        except (OSError, ValueError) as exc:
            raise StageError(f"Invalid Windows x64 prototype DLL: {relative}") from exc
    source_hashes = {name: hash_file(path) for name, path in sources.items()}
    save_hashes = {"sav_sha256": hash_file(save_path), "sav_lua_sha256": hash_file(sidecar)}
    code = {"game/" + name: sha for name, sha in source_hashes.items()}
    code.update({"mod/" + name: sha for name, sha in mod_hashes.items() if name != CONFIG})
    code.update({"python/" + name: hash_file(_source_file(path)) for name, path in python_files.items()})
    manifest = {
        "protocol": 1,
        "backend": "tf2_controlled_measurement",
        "game_sha256": build["sha256"],
        "save": save_hashes,
        "prototype_files": code,
        "template_bindings": selected["initial_bindings"],
        "config_semantics": {"enabled": True, "native_gate_required": True},
        "complete_world_verified": False,
    }
    if profile is not None:
        manifest["config_semantics"]["profile"] = profile
    manifest_digest = digest(manifest)

    # All read-only compatibility/schema checks are complete before creation.
    destination.mkdir(parents=True, exist_ok=False)
    directory.mkdir(parents=True, exist_ok=False)
    payload = destination / "game"
    payload.mkdir()
    for name, source in sources.items():
        shutil.copyfile(source, payload / name)
        if hash_file(payload / name) != source_hashes[name]:
            raise StageError("Prototype/audio source changed while staging.")
    mod_output = payload / "mods" / MOD
    for name, sha in mod_hashes.items():
        target = mod_output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == CONFIG:
            target.write_text(_config(directory, epoch, selected, profile), encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(mod_source / name, target)
            if hash_file(target) != sha:
                raise StageError("Lua prototype source changed while staging.")
    saved = destination / "save"
    saved.mkdir()
    for source, name, key in ((save_path, "initial.sav", "sav_sha256"),
                              (sidecar, "initial.sav.lua", "sav_lua_sha256")):
        shutil.copyfile(source, saved / name)
        if hash_file(saved / name) != save_hashes[key]:
            raise StageError("The selected save changed while staging; use a fresh preparation.")
    payload_manifest = {"files": _files(payload)}
    _write_json(destination / "probe_manifest.json", manifest)
    _write_json(directory / "probe_manifest.json", manifest)
    _write_json(directory / "probe_payload.json", payload_manifest)
    (directory / "probe_epoch.txt").write_text(str(epoch) + "\n", encoding="ascii")
    (destination / "STAGING_ONLY.txt").write_text(
        "Nur vorbereitete Messdateien. Spielordner und Installation wurden nicht verändert.\n"
        "Dieses Werkzeug installiert nichts und startet kein Spiel.\n"
        "Gleiche Dateihashes beweisen weder den tatsächlich geladenen Stand noch vollständige Synchronität.\n",
        encoding="utf-8")
    setup = {"protocol": 1, "native_epoch": epoch, "manifest_digest": manifest_digest,
             "game_exe": str(game / "TransportFever2.exe")}
    _write_json(directory / "probe_setup.json", setup)  # Activation descriptor last.
    return {"staging_only": True, "output": str(destination), "session": str(directory),
            "manifest_digest": manifest_digest, "native_epoch": epoch,
            "read_only_time_probe": profile != "build_v2" and not selected["initial_bindings"],
            "profile": profile or "time_v1"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--templates", type=Path, help="Explicit initial_bindings JSON; omitted means a time-only probe.")
    parser.add_argument("--profile", choices=sorted(PROFILES), help="Explicit controlled recipe; omitted preserves the legacy time profile.")
    args = parser.parse_args(argv)
    try:
        result = stage_probe(game_dir=args.game_dir, save=args.save, session=args.session,
                             output=args.output, templates=args.templates, profile=args.profile)
    except (OSError, ValueError, InstallError) as exc:
        parser.exit(2, f"Staging refused: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
