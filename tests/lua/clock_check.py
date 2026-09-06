"""Exercise actual clock/pause code with delayed engine commands, without TF2.

These tests prove speed-command ownership only. The simulated command delay is
deliberate: making sendCommand synchronous hid the live pause/play echo bug.
They do not test deterministic engine stepping or multiplayer world agreement.
"""
from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / ".deps"))
SOURCE = ROOT / "upstream/tpf2-multiplayer/mod/mp_lockstep_1/res/config/game_script/lockstep.lua"
TEXT = SOURCE.read_text(encoding="utf-8")

SETUP = r'''
os = {getenv=function(name)
    if name == "TF2COOP_SESSION" then return "1" end
    if name == "TPF2MP_DATADIR" then return "C:/clock-test" end
end, clock=function() return 1 end, time=function() return 100 end,
date=function() return "00:00:00" end}
io = {open=function(path, mode)
    if path == "C:/clock-test/tpf2_instance.txt" and mode == "r" then
        return {read=function() return "a" end,close=function() end}
    end
    return nil
end}
print = function() end
'''

HARNESS = r'''
function up(fn, wanted, replace)
    for i=1,200 do
        local name,value=debug.getupvalue(fn,i)
        if not name then break end
        if name == wanted then
            if replace ~= nil then debug.setupvalue(fn,i,replace) end
            return value
        end
    end
    error("missing upvalue: "..wanted)
end
update = data().update
cm = up(compareAt,"CM")
k = up(update,"K"); k.INSTANCE="a"
onLine = up(up(update,"pollEvents"),"onLine")
barrier = up(update,"applyBarrier")
ensureRunning = up(update,"ensureRunning")
wire = {}; commands = {}; speed = 1
up(cm.shareSpeed,"broadcast",function(line) wire[#wire+1]=line end)
api={cmd={make={setGameSpeed=function(value) return value end},
sendCommand=function(command) commands[#commands+1]=command end}}
game={interface={getGameSpeed=function() return speed end}}
function tick(n) up(update,"ticks",n) end
function observe(value) speed=value; cm.shareSpeed() end
function delivered()
    assert(#commands>0,"no pending engine command")
    observe(table.remove(commands,1))
end
remoteRevision = 0
function incoming(value, revision)
    revision = revision or remoteRevision + 1
    remoteRevision = math.max(remoteRevision, revision)
    onLine("LSSPEED v="..value.." o=b rev="..revision)
end
'''

CASES = {
    "remote pause does not echo the old running speed": r'''
        observe(1); incoming(0)
        observe(1); observe(1)
        assert(#wire==0,"old engine speed was rebroadcast as player input")
        assert(cm.baseSpeed==0 and #commands==1)
        delivered()
        cm.pace(-5,-5)
        assert(speed==0 and #wire==0 and #commands==0)
        assert(cm.baseSpeed==0,"pacer discarded shared pause")
    ''',
    "rapid remote pause/play remains owned until both land": r'''
        observe(1); incoming(0); incoming(1)
        observe(1)
        assert(#cm.speedPending==2,"unchanged old value acknowledged future play")
        delivered(); delivered()
        assert(speed==1 and cm.baseSpeed==1 and #wire==0)
        assert(#cm.speedPending==0)
    ''',
    "repeated remote values do not consume future transitions": r'''
        observe(1); incoming(0); incoming(1); incoming(0)
        observe(1)
        delivered(); delivered(); delivered()
        assert(speed==0 and cm.baseSpeed==0 and #wire==0)
    ''',
    "a later player selection of an old internal value is shared": r'''
        observe(4); cm.setSpeed(1,"test pacing"); delivered()
        cm.setSpeed(2,"test pacing"); delivered()
        observe(1)
        assert(#wire==1 and wire[1]=="LSSPEED v=1 o=a rev=1")
        assert(cm.baseSpeed==1)
    ''',
    "a genuine player choice supersedes an in-flight remote command": r'''
        observe(1); incoming(0); observe(4)
        assert(#wire==1 and wire[1]=="LSSPEED v=4 o=a rev=2")
        delivered(); delivered()
        assert(speed==4 and cm.baseSpeed==4 and #wire==1)
    ''',
    "pause received during a barrier remains after release": r'''
        observe(1)
        up(barrier,"paused",true)
        cm.setSpeed(0,"test barrier"); delivered()
        incoming(0)
        assert(cm.baseSpeed==0,"equal actual speed discarded peer pause intent")
        up(barrier,"paused",false)
        cm.releaseSpeed("test barrier complete"); delivered()
        assert(speed==0 and #wire==0)
    ''',
    "remote play cannot release an active barrier": r'''
        observe(1)
        up(barrier,"paused",true)
        cm.setSpeed(0,"test barrier"); delivered()
        incoming(2)
        assert(speed==0 and #commands==0 and cm.baseSpeed==2)
        up(barrier,"paused",false)
        cm.releaseSpeed("test barrier complete"); delivered()
        assert(speed==2 and #wire==0)
    ''',
    "common paused save stays paused when both players load": r'''
        observe(0); tick(150)
        cm.cfgCache={load_gate="1",expect_players="2"}
        cm.peers.b={time=0,at=150}
        ensureRunning()
        assert(#commands==0 and speed==0,"startup silently pressed play")
    ''',
    "load gate restores shared pause instead of old running speed": r'''
        observe(1); tick(5)
        cm.cfgCache={load_gate="1",expect_players="2"}
        ensureRunning(); delivered()
        assert(speed==0 and #wire==0,"load gate pause echoed")
        incoming(0)
        tick(6); cm.peers.b={time=0,at=6}
        ensureRunning(); delivered()
        assert(speed==0 and cm.baseSpeed==0 and #wire==0)
    ''',
    "invalid remote speed is ignored": r'''
        observe(1); incoming(3); incoming(99)
        assert(#commands==0 and #wire==0 and cm.baseSpeed==1)
    ''',
    "missing, malformed or out-of-range ordering is ignored": r'''
        observe(1)
        for _, line in ipairs({"LSSPEED v=0 o=b", "LSSPEED v=0 o=bb rev=1",
            "LSSPEED v=0 o=b rev=1.5", "LSSPEED v=0 o=b rev=1suffix",
            "LSSPEED v=0 o=b rev=-1", "LSSPEED v=0 o=b rev=2147483648"}) do
            onLine(line)
        end
        assert(#commands==0 and cm.speedClock==0 and cm.speedIntent==nil)
    ''',
    "duplicate and older intent cannot undo a newer choice": r'''
        observe(1); incoming(0,7); incoming(0,7); incoming(4,6)
        assert(#commands==1 and cm.speedClock==7 and cm.baseSpeed==0)
        delivered(); observe(2)
        assert(wire[1]=="LSSPEED v=2 o=a rev=8")
        incoming(0,7)
        assert(cm.baseSpeed==2 and #commands==0)
    ''',
}


def instance(version, origin="a"):
    lua = importlib.import_module("lupa." + version).LuaRuntime()
    lua.execute(SETUP)
    lua.execute(TEXT)
    lua.execute(HARNESS)
    lua.globals().k.INSTANCE = origin
    return lua


def concurrent_choices(version):
    """Two real Lua states exchange simultaneous intents in arbitrary orders."""
    for order in ("host-first", "guest-first"):
        host, guest = instance(version, "a"), instance(version, "b")
        h, g = host.globals(), guest.globals()
        h.observe(2)
        g.observe(2)
        h.observe(1)
        g.observe(0)
        host_message, guest_message = h.wire[1], g.wire[1]
        assert host_message == "LSSPEED v=1 o=a rev=1"
        assert guest_message == "LSSPEED v=0 o=b rev=1"
        if order == "host-first":
            g.onLine(host_message)
            h.onLine(guest_message)
        else:
            h.onLine(guest_message)
            g.onLine(host_message)
        # The winner is b:1 on both machines; repeated packets cannot enqueue
        # another command. Leave the host's old running state observable first.
        h.onLine(guest_message)
        g.onLine(host_message)
        h.observe(1)
        assert len(h.commands) == 1 and len(g.commands) == 0
        h.delivered()
        assert h.speed == g.speed == 0
        assert h.cm.baseSpeed == g.cm.baseSpeed == 0
        assert len(h.wire) == len(g.wire) == 1, "internal command echoed"

        # A subsequent local gesture has a greater logical revision and wins
        # regardless of late arrivals of either original simultaneous message.
        h.observe(4)
        newer = h.wire[2]
        assert newer == "LSSPEED v=4 o=a rev=2"
        g.onLine(newer)
        g.onLine(host_message)
        h.onLine(guest_message)
        g.onLine(newer)
        g.observe(0)
        assert len(g.commands) == 1
        g.delivered()
        assert h.speed == g.speed == 4
        assert h.cm.speedIntent.revision == g.cm.speedIntent.revision == 2
        assert h.cm.speedIntent.origin == g.cm.speedIntent.origin == "a"
        assert len(h.wire) == 2 and len(g.wire) == 1

    # A received old choice is still in the engine queue when the other player
    # makes a newer local choice. That winning revision must execute LAST and
    # the transient old command must not create another network intent.
    host, guest = instance(version, "a"), instance(version, "b")
    h, g = host.globals(), guest.globals()
    h.observe(2)
    g.observe(2)
    h.observe(1)
    g.onLine(h.wire[1])
    g.observe(0)
    winner = g.wire[1]
    assert winner == "LSSPEED v=0 o=b rev=2"
    assert len(g.commands) == 2
    h.onLine(winner)
    g.onLine(h.wire[1])
    h.onLine(winner)
    g.delivered()
    g.delivered()
    h.delivered()
    assert h.speed == g.speed == 0
    assert h.cm.speedIntent.revision == g.cm.speedIntent.revision == 2
    assert len(h.wire) == len(g.wire) == 1


for version in ("lua51", "lua52", "lua53", "lua54"):
    for name, case in CASES.items():
        lua = instance(version)
        try:
            lua.execute(case)
        except Exception as exc:
            raise AssertionError(f"{version}: {name}") from exc
    concurrent_choices(version)
    print(f"PASS {version}: {len(CASES)} delayed-engine regressions + two-instance intent ordering")
