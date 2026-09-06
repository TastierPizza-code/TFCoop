"""Build an isolated portable folder; never deploy into a game or open a window."""
from pathlib import Path
import datetime
import importlib.metadata
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
output = ROOT / "dist" / stamp
output.mkdir(parents=True, exist_ok=False)
subprocess.run([sys.executable, "-m", "PyInstaller", "--onedir", "--noconsole", "--noupx",
                "--name", "TF2-Coop", "--hidden-import", "coop.native", "--hidden-import", "coop.diagnostics",
                "--distpath", str(output), "--workpath", str(ROOT / "build" / stamp),
                "--specpath", str(ROOT / "build" / stamp), str(ROOT / "launcher.py")], cwd=ROOT, check=True)
bundle = output / "TF2-Coop"
for relative in ("mod", "docs", "upstream/tpf2-multiplayer/mod/mp_lockstep_1"):
    shutil.copytree(ROOT / relative, bundle / relative)
for name in ("README.md", "THIRD_PARTY_NOTICES.md", "requirements-build.txt", "upstream/tpf2-multiplayer/LICENSE", "upstream/tpf2-multiplayer/THIRD_PARTY_NOTICES.md"):
    target = bundle / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / name, target)
for name in ("alut.dll", "tpf2_bridge_mp.dll", "tpf2_slice.dll"):
    target = bundle / "native" / "out" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "native" / "out" / name, target)
licenses = bundle / "licenses"
licenses.mkdir()
for distribution in ("pyinstaller", "pyinstaller-hooks-contrib"):
    dist = importlib.metadata.distribution(distribution)
    for file in dist.files or []:
        if "license" in str(file).lower() or "copying" in str(file).lower():
            src = Path(dist.locate_file(file))
            if src.is_file():
                target = licenses / distribution / str(file).replace("..", "_")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
base = Path(sys.base_prefix)
for src in [base / "LICENSE.txt", *list((base / "tcl").glob("*/license.terms"))]:
    if src.is_file():
        target = licenses / "python-tcl" / src.relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
archive = output / "TF2-Coop-Alpha.zip"
with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
    for file in sorted(bundle.rglob("*")):
        if file.is_file():
            package.write(file, str(Path("TF2-Coop") / file.relative_to(bundle)))
print(str(bundle / "TF2-Coop.exe"))
print(str(archive))
