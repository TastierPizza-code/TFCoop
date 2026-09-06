"""Read-only native Lua checks. Never starts the game, UI, DLLs or network.

The entire modified lockstep chunk is compiled by real Lua 5.1--5.4 compilers,
which enforce the 200-live-local limit. Passive imports may attempt the one
process-authenticated activation pipe; all game APIs, disk files, imports and
process functions are denied. Active imports use in-memory identity/config data.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / ".deps"))
SOURCE = ROOT / "upstream/tpf2-multiplayer/mod/mp_lockstep_1/res/config/game_script/lockstep.lua"
text = SOURCE.read_text(encoding="utf-8")


def runtime(version: str):
    return importlib.import_module("lupa." + version).LuaRuntime(unpack_returned_tuples=True)


def setup(lua, env_value, active=False):
    lua.globals().test_session_value = env_value
    lua.execute(r'''
        test_calls = {}; test_max_locals = 0; test_pipe_reads = 0
        function deny(name)
            return function(...)
                test_calls[#test_calls + 1] = name
                error("Forbidden test capability: " .. name)
            end
        end
        local getenv = function(name)
            if name == "TF2COOP_SESSION" then return test_session_value end
            if name == "TPF2MP_DATADIR" then return "C:/session-fresh" end
            return nil
        end
        os = { getenv = getenv, execute = deny("execute"), remove = deny("remove"),
               rename = deny("rename"), exit = deny("exit"),
               time = function() return 100 end, clock = function() return 1 end }
        io = { open = function(path, mode)
                   if path == "\\\\.\\pipe\\TF2CoopActivation" and mode == "rb" then
                       test_pipe_reads = test_pipe_reads + 1
                       return nil
                   end
                   return deny("open")()
               end, popen = deny("popen") }
        api = nil; game = nil
        require = deny("require"); dofile = deny("dofile")
        print = function(...) end
    ''')
    if active:
        lua.execute(r'''
            test_file_reads = {}
            io.open = function(path, mode)
                assert(mode == "r", "Unexpected module-init write")
                test_file_reads[#test_file_reads + 1] = path
                if path == "C:/session-fresh/tpf2_instance.txt" then
                    return { close = function() end, read = function() return "a" end }
                end
                return nil
            end
            -- Count live locals at each line in the main chunk. This detects
            -- compiler-slot pressure without parsing comments or nested fns.
            debug.sethook(function()
                local info = debug.getinfo(2, "S")
                if info and info.what == "main" then
                    local count = 0
                    for i = 1, 250 do
                        local name = debug.getlocal(2, i)
                        if not name then break end
                        if name:sub(1, 1) ~= "(" then count = count + 1 end
                    end
                    if count > test_max_locals then test_max_locals = count end
                end
            end, "l")
        ''')


def pipe_input(lua, wire):
    """Simulate only framed bytes returned by the process-authenticated proxy."""
    lua.globals().test_wire = wire
    lua.execute(r'''
        test_pipe_closed = 0
        local previousOpen = io.open
        io.open = function(path, mode)
            if path ~= "\\\\.\\pipe\\TF2CoopActivation" then return previousOpen(path, mode) end
            assert(mode == "rb")
            test_pipe_reads = test_pipe_reads + 1
            local offset = 1
            return {
                read = function(_, size)
                    assert(type(size) == "number" and size >= 1 and size <= 4096)
                    local result = test_wire:sub(offset, offset + size - 1)
                    offset = offset + size
                    return #result > 0 and result or nil
                end,
                close = function() test_pipe_closed = test_pipe_closed + 1; return true end,
            }
        end
    ''')


def frame(value):
    return f"{len(value.encode('utf-8')):04d}" + value


PIPE_PAYLOAD = ("format=1\nactive=1\ndata_dir=C:/session-fresh\n"
                "game_exe=X:/SteamLibrary/TransportFever2.exe\ngame_pid=123\nnonce=0123abcd\n")


for version in ("lua51", "lua52", "lua53", "lua54"):
    lua = runtime(version)
    compile_lua = lua.eval("function(s, n) return assert((loadstring or load)(s, n)) end")
    compiled = compile_lua(text, "@" + str(SOURCE))
    print(f"PASS {version}: entire {len(text.splitlines())}-line chunk compiles (local limit enforced)")
    for value in (None, "0", "", "true", "11"):
        lua = runtime(version)
        setup(lua, value)
        compiled = lua.eval("function(s,n) return assert((loadstring or load)(s,n)) end")(text, "@lockstep.lua")
        compiled()
        assert len(lua.globals().data()) == 0
        assert len(lua.globals().test_calls) == 0
    lua = runtime(version)
    setup(lua, None)
    lua.execute("os = nil")
    lua.execute(text)
    assert len(lua.globals().data()) == 0
    assert len(lua.globals().test_calls) == 0
    lua = runtime(version)
    setup(lua, None)
    lua.execute('os.getenv = function() error("environment access unavailable") end')
    lua.execute(text)
    assert len(lua.globals().data()) == 0
    assert len(lua.globals().test_calls) == 0
    print(f"PASS {version}: ordinary launches and missing os remain passive with absent activation pipe")

    for wire in ("", "abcd", "0000", "4097", "0030short",
                 frame(PIPE_PAYLOAD.replace("active=1", "active=0")),
                 frame(PIPE_PAYLOAD + "format=1\n"),
                 frame(PIPE_PAYLOAD.replace("C:/session-fresh", "relative/path")),
                 frame(PIPE_PAYLOAD.replace("game_pid=123", "game_pid=-1")),
                 frame(PIPE_PAYLOAD.replace("nonce=0123abcd", "nonce=")),
                 frame(PIPE_PAYLOAD.replace("format=1", "format=2"))):
        lua = runtime(version)
        setup(lua, None)
        pipe_input(lua, wire)
        lua.execute(text)
        assert len(lua.globals().data()) == 0, wire
        assert len(lua.globals().test_calls) == 0
        assert lua.globals().test_pipe_closed == 1
    print(f"PASS {version}: invalid/truncated/oversized pipe frames stay passive and close handles")

    lua = runtime(version)
    setup(lua, None)
    pipe_input(lua, frame(PIPE_PAYLOAD.replace("C:/session-fresh", "\\\\server\\share\\session")))
    activation = lua.execute(text.split("-- MP Lockstep -- prototype.")[0] + "\nreturn K.ACTIVATION\n")
    assert activation["data_dir"] == "\\\\server\\share\\session"
    assert lua.globals().test_pipe_closed == 1
    assert len(lua.globals().test_calls) == 0

    lua = runtime(version)
    setup(lua, None, active=True)
    lua.execute("os.getenv = nil; os.rename = nil; os.remove = nil")
    pipe_input(lua, frame(PIPE_PAYLOAD))
    lua.execute(text)
    lua.execute("debug.sethook()")
    callbacks = lua.globals().data()
    assert callbacks["update"] is not None and callbacks["guiUpdate"] is not None
    assert lua.globals().test_pipe_closed == 1
    assert len(lua.globals().test_calls) == 0
    assert all(str(path).startswith("C:/session-fresh/")
               for path in lua.globals().test_file_reads.values())
    print(f"PASS {version}: native pipe starts actual lockstep script without getenv/rename/remove")

    lua = runtime(version)
    setup(lua, "1", active=True)
    lua.execute(text)
    lua.execute("debug.sethook()")
    callbacks = lua.globals().data()
    assert callbacks["update"] is not None and callbacks["guiUpdate"] is not None
    assert len(lua.globals().test_calls) == 0
    print(f"PASS {version}: opted-in top-level initialization; max live named locals={lua.globals().test_max_locals}")

    # Reach the real comparison tables through Lua's debug API, then feed a
    # controlled peer hash. No engine callbacks or game mutation are invoked.
    lua.execute(r'''
        local function upvalue(fn, name)
            for i = 1, 100 do
                local n, v = debug.getupvalue(fn, i)
                if not n then break end
                if n == name then return v end
            end
            error("Missing upvalue " .. name)
        end
        test_cm = upvalue(compareAt, "CM")
        test_hashes = upvalue(compareAt, "myHashes")
        test_compare_one = upvalue(compareAt, "compareOne")
        test_details = upvalue(test_compare_one, "myDetails")
        assert(test_cm.lastComparison == nil)
        compareAt(4)
        assert(test_cm.lastComparison == nil, "No local hash cannot count as comparison")
        test_hashes[4] = "same-hash"
        test_details[4] = "v2,c1:a,e1:a,m:1000,l:200,t1"
        test_cm.peers.b = { hashes = {[4]="same-hash"},
            details = {[4]="v2,c1:a,e1:a,m:875,l:200,t1"}, streak = 0 }
        compareAt(4)
        assert(test_cm.dashVerdict == "SYNC")
        assert(test_cm.moneyGap.mb == 125 and test_cm.moneyGap.lb == 0)
        assert(test_cm.lastComparison.t == 4 and test_cm.lastComparison.wall == 100)
        assert(test_cm.lastComparison.peer == "b" and test_cm.lastComparison.match == true)
        assert(test_cm.moneyGapWall.b == 100)
        os.time = function() return 101 end
        compareAt(4)
        assert(test_cm.lastComparison.wall == 100, "Duplicate stamp must not refresh comparison")
    ''')
    # Compile and run the actual dashboard extension as written in the source.
    # The outer dashboard normally opens a file; the injected sink is in-memory.
    start = text.index("\t\t\t\t\t\t-- TF2 Co-op diagnostics.")
    end = text.index("\t\t\t\t\t\t-- The GUI used to decide", start)
    extension = text[start:end]
    lua.globals().test_dash_write = lua.eval("function(CM,f)\n" + extension + "\nend")
    lua.execute(r'''
        function test_render()
            local chunks = {}
            test_dash_write(test_cm, {write=function(_,s) chunks[#chunks+1]=s end})
            return table.concat(chunks)
        end
        local data = test_render()
        assert(data:find("comparison_t=4\n", 1, true))
        assert(data:find("comparison_match=yes\n", 1, true))
        assert(data:find("money_gap=b:125:0\n", 1, true))
        assert(data:find("money_gap_wall=b:100\n", 1, true))

        -- A current mismatch has its own signal while the upstream hysteresis
        -- has not yet replaced its previous SYNC verdict.
        test_hashes[8] = "local-hash"
        test_details[8] = "v2,c1:a,e1:a,m:-,l:-,t1"
        test_cm.peers.b.hashes[8] = "other-hash"
        test_cm.peers.b.details[8] = "v2,c1:a,e1:b,m:875,l:200,t1"
        compareAt(8)
        assert(test_cm.lastComparison.match == false)
        assert(test_cm.dashVerdict == "SYNC")
        assert(test_cm.moneyGapWall.b == nil, "Missing lanes must invalidate prior money sample")
        data = test_render()
        assert(data:find("comparison_match=no\n", 1, true))
        assert(data:find("money_gap=b:-:-\n", 1, true))
        assert(data:find("money_gap_wall=b:-\n", 1, true))
        assert(#test_calls == 0, "Diagnostics must never call engine/file APIs")
    ''')
    print(f"PASS {version}: actual comparison and dashboard distinguish money gap, early mismatch and unknown accounts")
