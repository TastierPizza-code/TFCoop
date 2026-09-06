"""Run Lua tests through optional Lupa (pip install lupa)."""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / '.deps'))
from lupa import LuaRuntime

root = Path(__file__).resolve().parents[2]
os.chdir(root)
runtime = LuaRuntime(unpack_returned_tuples=True)
runtime.execute((root / 'tests/lua/test_mod.lua').read_text(encoding='utf-8'))
runtime.execute((root / 'tests/lua/test_game_script.lua').read_text(encoding='utf-8'))
for path in (root / 'mod').rglob('*.lua'):
    # Compile every resource with its filename so syntax failures are actionable.
    runtime.execute('assert(load(...))', path.read_text(encoding='utf-8'), str(path))
print('All mod Lua resources compile.')
