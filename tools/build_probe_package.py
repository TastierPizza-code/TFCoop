"""Build an isolated public portable ZIP; never install or launch a game/UI.

Invoke only after the launcher, native DLLs, Lua and guides are finalized:
  .venv\\Scripts\\python.exe tools\\build_probe_package.py
The executable's --self-check runs passive validation and three hidden MODEL workers.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prototype.release_version import PACKAGE_NAME as PACKAGE, RELEASE_TAG
EXE = "TF2-Coop.exe"
BASELINE = ROOT / "prototype/staged/time-probe-20260906/save/initial.sav"


def file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def _copy_file(source, target):
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"missing or linked package source: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if file_hash(source) != file_hash(target):
        raise ValueError(f"source changed during packaging: {source}")


def _licenses(bundle, *, include_save):
    for distribution in ("pyinstaller", "pyinstaller-hooks-contrib"):
        dist = importlib.metadata.distribution(distribution)
        for file in dist.files or []:
            if "license" in str(file).lower() or "copying" in str(file).lower():
                source = Path(dist.locate_file(file))
                if source.is_file():
                    _copy_file(source, bundle / "licenses" / distribution / str(file).replace("..", "_"))
    base = Path(sys.base_prefix)
    for source in [base / "LICENSE.txt", *list((base / "tcl").glob("*/license.terms"))]:
        if source.is_file():
            _copy_file(source, bundle / "licenses/python-tcl" / source.relative_to(base))
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        _copy_file(ROOT / "upstream/tpf2-multiplayer" / name,
                   bundle / "upstream/tpf2-multiplayer" / name)
    notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text("utf-8")
    if include_save:
        notice += "\nPrivate build: includes the separately authorized shared test save pair. Do not publish this build.\n"
    else:
        notice += "\nPublic release: no savegame, original game executable or original audio is included.\n"
        notice += "The shared test save is imported locally from an existing private test installation.\n"
    (bundle / "THIRD_PARTY_NOTICES.md").write_text(notice, encoding="utf-8")
    _copy_file(ROOT / "docs/UPSTREAM.patch", bundle / "docs/UPSTREAM.patch")


def build(stamp=None, save=BASELINE, *, skip_self_check=False, include_save=False):
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", stamp):
        raise ValueError("stamp must be a plain bounded directory name")
    save = Path(save).resolve()
    prerequisite = [ROOT / "probe_launcher.py", ROOT / "prototype/launcher.py",
                    ROOT / "prototype/ANLEITUNG.md", ROOT / "prototype/ANLEITUNG.html",
                    ROOT / "prototype/native/out/probe_alut.dll", ROOT / "prototype/native/out/tf2_step_probe.dll",
                    save, Path(str(save) + ".lua")]
    for path in prerequisite:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"finish launcher/guides/native build before packaging: {path}")
    watched = set(prerequisite) | set((ROOT / "prototype/strict_sync").glob("*.py"))
    watched |= set((ROOT / "prototype").glob("*.py")) | set((ROOT / "coop").glob("*.py"))
    watched |= {p for p in (ROOT / "prototype/mod").rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")}
    watched |= {p for p in (ROOT / "prototype/examples").rglob("*") if p.is_file()}
    source_hashes = {p: file_hash(p) for p in watched}
    output = ROOT / "dist" / (stamp + "-probe")
    output.mkdir(parents=True, exist_ok=False)
    work = ROOT / "build" / (stamp + "-probe")
    work.mkdir(parents=True, exist_ok=False)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--onedir", "--noconsole", "--noupx",
                    "--name", Path(EXE).stem, "--collect-submodules", "prototype.strict_sync",
                    "--hidden-import", "prototype.launcher", "--hidden-import", "coop.native",
                    "--hidden-import", "coop.launch", "--hidden-import", "coop.install",
                    "--hidden-import", "coop.session", "--distpath", str(output),
                    "--workpath", str(work), "--specpath", str(work), str(ROOT / "probe_launcher.py")],
                   cwd=ROOT, check=True)
    if any(file_hash(path) != expected for path, expected in source_hashes.items()):
        raise ValueError("source changed while freezing; finish edits and use a new build")
    generated = output / Path(EXE).stem
    bundle = output / PACKAGE
    # One known just-created output directory, contained in this isolated build.
    if generated.resolve().parent != output.resolve() or bundle.resolve().parent != output.resolve():
        raise ValueError("build paths escaped the isolated output directory")
    generated.rename(bundle)
    internal = bundle / "_internal"
    for path in (ROOT / "prototype").glob("*.py"):
        _copy_file(path, internal / "prototype" / path.name)
    for path in (ROOT / "prototype/strict_sync").glob("*.py"):
        _copy_file(path, internal / "prototype/strict_sync" / path.name)
    shutil.copytree(ROOT / "prototype/mod", internal / "prototype/mod",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    shutil.copytree(ROOT / "prototype/examples", internal / "prototype/examples",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    for name in ("probe_alut.dll", "tf2_step_probe.dll"):
        _copy_file(ROOT / "prototype/native/out" / name, internal / "prototype/native/out" / name)
    if include_save:
        _copy_file(save, bundle / "Testspielstand/initial.sav")
        _copy_file(Path(str(save) + ".lua"), bundle / "Testspielstand/initial.sav.lua")
    for name in ("ANLEITUNG.md", "ANLEITUNG.html"):
        _copy_file(ROOT / "prototype" / name, bundle / name)
    _copy_file(ROOT / "prototype/README.md", bundle / "TECHNIK.md")
    _copy_file(ROOT / "prototype/VERIFICATION.md", bundle / "VERIFICATION.md")
    _copy_file(ROOT / "prototype/CRASH_FIX_2026-09-06.md", bundle / "CRASH_FIX.md")
    _copy_file(ROOT / "prototype/IO_FIX_2026-09-06.md", bundle / "IO_FIX.md")
    _copy_file(ROOT / "prototype/BUILD_TEST.md", bundle / "BUILD_TEST.md")
    _copy_file(ROOT / "prototype/docs/BUILD_SCENE_ASSETS_2026-09-06.md", bundle / "docs/BUILD_SCENE_ASSETS.md")
    for name in ("CONSTRUCTION_PARAMS_FIX.md", "FIELD_LOOKUP_FIX.md", "GITHUB_UPDATES.md"):
        _copy_file(ROOT / "prototype/docs" / name, bundle / "docs" / name)
    _licenses(bundle, include_save=include_save)
    if any(file_hash(path) != expected for path, expected in source_hashes.items()):
        raise ValueError("source changed while copying; finish edits and use a new build")
    manifest = {"package": PACKAGE, "release_tag": RELEASE_TAG, "protocol": 1,
                "repository": "TastierPizza-code/TFCoop",
                "distribution": "private" if include_save else "public", "game_runtime_verified": False,
                "source_files": {path.relative_to(ROOT).as_posix(): digest
                                 for path, digest in sorted(source_hashes.items())
                                 if path.is_relative_to(ROOT) and path.suffix in (".py", ".lua", ".con", ".json", ".md", ".html")
                                 and not any(part in ("staged", "sessions", "results", "out") for part in path.relative_to(ROOT).parts)},
                "baseline": {"sav_sha256": file_hash(save), "sav_lua_sha256": file_hash(Path(str(save) + ".lua")),
                             "sav_bytes": save.stat().st_size, "sav_lua_bytes": Path(str(save) + ".lua").stat().st_size},
                "files": {path.relative_to(bundle).as_posix(): file_hash(path)
                          for path in sorted(bundle.rglob("*")) if path.is_file()}}
    (bundle / "package_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    if list(bundle.rglob("alut_real.dll")) or list(bundle.rglob("TransportFever2.exe")):
        raise ValueError("stock game/audio must not be redistributed")
    if not include_save and any(path.name.endswith((".sav", ".sav.lua", ".key")) for path in bundle.rglob("*")):
        raise ValueError("public release must contain no private save or session keys")
    report = output / "self-check.json"
    if not skip_self_check:
        subprocess.run([str(bundle / EXE), "--self-check", str(report)], cwd=bundle,
                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                       check=True, timeout=100)
        if not json.loads(report.read_text("utf-8"))["passed"]:
            raise ValueError("portable self-check failed")
    archive = output / ((PACKAGE + ".zip") if include_save else "TFCoop-Windows.zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                package.write(path, str(Path(PACKAGE) / path.relative_to(bundle)))
    with zipfile.ZipFile(archive) as package:
        bad = package.testzip()
        if bad:
            raise ValueError("ZIP CRC failed: " + bad)
    return {"executable": str(bundle / EXE), "archive": str(archive), "sha256": file_hash(archive),
            "bytes": archive.stat().st_size, "self_check": None if skip_self_check else str(report)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stamp")
    parser.add_argument("--save", type=Path, default=BASELINE)
    parser.add_argument("--skip-self-check", action="store_true")
    parser.add_argument("--private-save", action="store_true", help="Local private bundle only; never publish this archive.")
    args = parser.parse_args(argv)
    print(json.dumps(build(args.stamp, args.save, skip_self_check=args.skip_self_check, include_save=args.private_save), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
