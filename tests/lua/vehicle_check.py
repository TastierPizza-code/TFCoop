"""Regressions for actual Lua line replay; no game, UI, DLL or network access.

Reproduces the user's async LCREATE + same-stamp LUPDATE + VLINE sequence.
The complete production Lua chunk runs with a small in-memory engine whose
commands complete later. An empty-line assignment is treated as an assertion.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / ".deps"))
SOURCE = ROOT / "upstream/tpf2-multiplayer/mod/mp_lockstep_1/res/config/game_script/lockstep.lua"
source = SOURCE.read_text(encoding="utf-8")
# Run the literal production retry merge, due-time gate, batch-target prepass,
# execution deduplication and dispatch. Keep this tied to its actual update()
# body: a direct execLine/execVehCmd test alone misses scheduler regressions.
pump_start = source.index("\t\t\t-- Commands that asked to be tried again")
pump_end = source.index("\t\t\t-- EVERY tick, not every 50th", pump_start)
production_pump = source[pump_start:pump_end]

SETUP = r'''
    logs = {}
    print = function(s) logs[#logs+1] = tostring(s) end
    os = { getenv = function(k)
        if k == "TF2COOP_SESSION" then return "1" end
        if k == "TPF2MP_DATADIR" then return "C:/memory-session" end
    end, time=function() return 100 end, clock=function() return 1 end }
    io = { open=function(path, mode)
        assert(mode == "r", "Unexpected test disk write")
        if path == "C:/memory-session/tpf2_instance.txt" then
            return {read=function() return "a" end, close=function() end}
        end
    end }
'''

ENGINE = r'''
    currentTime = 200.8
    local lines, commands, assigned = {}, {}, {}
    local nextLine = 500
    local setLineCalls = 0
    api = {
        type = {
            ComponentType={LINE="LINE", TRANSPORT_VEHICLE="TV"},
            Line={new=function() return {stops={}} end,
                  Stop={new=function() return {} end}},
            Vec3f={new=function(r,g,b) return {r,g,b} end},
        },
        engine = {
            util={getPlayer=function() return 1 end},
            system={lineSystem={getLines=function()
                local ids={}; for id in pairs(lines) do ids[#ids+1]=id end
                return ids
            end}},
            getComponent=function(id, kind)
                if kind == "LINE" then return lines[id] end
                if kind == "TV" then return {} end
            end,
        },
        cmd = {make={}, sendCommand=function(cmd, callback)
            commands[#commands+1]={cmd=cmd, callback=callback}
        end},
    }
    game={interface={
        getGameTime=function() return {time=currentTime} end,
        getEntities=function(_,query)
            assert(query.type == "STATION_GROUP")
            return {701,702}
        end,
        getEntity=function(id)
            if id==701 then return {position={10,20}} end
            if id==702 then return {position={40,50}} end
        end,
        getName=function(id) return "Line" end,
    }}
    api.cmd.make.createLine=function(name,color,player,obj)
        return {kind="create",obj=obj}
    end
    api.cmd.make.updateLine=function(id,obj)
        assert(lines[id], "Update before create")
        return {kind="update",id=id,obj=obj}
    end
    api.cmd.make.deleteLine=function(id)
        assert(lines[id], "Delete before create")
        return {kind="delete",id=id}
    end
    api.cmd.make.setLine=function(id,line,stop)
        setLineCalls=setLineCalls+1
        assert(lines[line] and #lines[line].stops > 0,
               "Native assertion: !line.stops.empty()")
        return {kind="assign",id=id,line=line,stop=stop}
    end
    function flushCommands()
        local pending=commands; commands={}
        for _,p in ipairs(pending) do
            local c=p.cmd; local res={}
            if c.kind=="create" then
                nextLine=nextLine+1; lines[nextLine]=c.obj
                res.resultEntity=nextLine
            elseif c.kind=="update" then lines[c.id]=c.obj
            elseif c.kind=="delete" then lines[c.id]=nil
            elseif c.kind=="assign" then assigned[c.id]=c.line end
            p.callback(res,true)
        end
    end
    function runRetries()
        local pending=test.CM.retryQueue or {}; test.CM.retryQueue={}
        table.sort(pending,test.cmdLess)
        for _,c in ipairs(pending) do
            if c.op=="VLINE" then test.execVehCmd(c) else test.execLine(c) end
        end
    end
    function makeCommand(op,seq,key,stops)
        return {op=op,origin="b",seq=seq,at=200.8,key=key,
                name="Line",color="1,0,0",stops=stops or ""}
    end
    function commandCount() return #commands end
    function assignmentCount() return setLineCalls end
    function lineStops(key)
        local id=test.lineIdFor(key)
        return id and lines[id] and #lines[id].stops or nil
    end
    function assignedLine(id) return assigned[id] end
    function setClock(t) currentTime=t end
'''

EXPORT = "\nfunction vehicleTestPump(now)\n" + production_pump + "\nend\n" + r'''
return {execLine=execLine,execVehCmd=execVehCmd,pollLineKeys=pollLineKeys,
        registerVehKey=registerVehKey,lineIdFor=lineIdFor,
        cmdLess=cmdLess,CM=CM,K=K,pump=vehicleTestPump,
        enqueue=function(c) queue[#queue+1]=c end,
        queued=function() return #queue end}
'''

for version in ("lua51", "lua52", "lua53", "lua54"):
    lua = importlib.import_module("lupa." + version).LuaRuntime(unpack_returned_tuples=True)
    lua.execute(SETUP)
    lua.globals().test = lua.execute(source + EXPORT)
    lua.execute(ENGINE)
    lua.execute(r'''
        local create=makeCommand("LCREATE",27)
        local first=makeCommand("LUPDATE",28,"b:27","10,20,0,0,0,0,180")
        local last=makeCommand("LUPDATE",29,"b:27","10,20,0,0,0,0,180;40,50,0,0,0,0,180")
        test.execLine(create)
        test.execLine(first); test.execLine(last)
        assert(commandCount()==1, "Updates must wait for their async create")
        assert(#test.CM.retryQueue==2, "Both same-stamp edits must be retained")
        assert(first.at==200.8 and last.at==200.8, "Retry must preserve command identity/order")
        assert(first.notBeforeStep==nil, "Dependency retry must preserve original target")
        flushCommands(); test.pollLineKeys()
        assert(lineStops("b:27")==0, "New empty line bound")

        test.registerVehKey("b:41",800)
        local assign=makeCommand("VLINE",51,"b:41")
        assign.line="b:27"; assign.stop=0
        test.execVehCmd(assign)
        assert(assignmentCount()==0, "Never call native setLine on an empty line")
        assert(#test.CM.retryQueue==3)
        setClock(201)
        runRetries()
        assert(commandCount()==2, "Both updates queued in source order")
        assert(assignmentCount()==0, "Wait for actual engine update completion")
        flushCommands()
        assert(lineStops("b:27")==2, "Latest line edit wins after async binding")
        runRetries(); flushCommands()
        assert(assignmentCount()==1 and assignedLine(800)==test.lineIdFor("b:27"))
        assert(#test.CM.retryQueue==0)

        -- Delete immediately after create must likewise wait for its key.
        test.execLine(makeCommand("LCREATE",100))
        test.execLine(makeCommand("LDELETE",101,"b:100"))
        assert(#test.CM.retryQueue==1)
        flushCommands(); test.pollLineKeys(); runRetries(); flushCommands()
        assert(test.lineIdFor("b:100")==nil)

        -- Missing keys remain bounded and explicitly report divergence.
        local absent=makeCommand("LUPDATE",200,"missing")
        test.execLine(absent)
        for i=1,60 do runRetries() end
        assert(#test.CM.retryQueue==0 and absent.lineDependencyTries==61)
        local reported=false
        for _,line in ipairs(logs) do
            if line:find("NOT applied (DIVERGENCE)",1,true) then reported=true end
            assert(not line:find("execVLINE error",1,true),line)
        end
        assert(reported,"An exhausted dependency must be visible")

        -- A strict origin also waits for its own async purchase key.
        local localAssign=makeCommand("VLINE",300,"a:299")
        localAssign.origin="a"; localAssign.armed=1; localAssign.line="b:27"
        test.K.STRICT_OPS.VLINE=true
        test.execVehCmd(localAssign)
        assert(#test.CM.retryQueue==1 and assignmentCount()==1)
        test.registerVehKey("a:299",801)
        runRetries(); flushCommands()
        assert(assignmentCount()==2 and assignedLine(801)==test.lineIdFor("b:27"))

        -- A later edit arriving after the key binds must not overtake a
        -- previous edit whose retry step has not been reached yet. The line
        -- already has a stop, so assignment must also wait for in-flight
        -- updates rather than merely checking that it is nonempty.
        local oneStop="10,20,0,0,0,0,180"
        local twoStops=oneStop..";40,50,0,0,0,0,180"
        test.execLine(makeCommand("LCREATE",400,nil,oneStop))
        test.execLine(makeCommand("LUPDATE",401,"b:400",oneStop))
        flushCommands(); test.pollLineKeys()
        test.execLine(makeCommand("LUPDATE",402,"b:400",twoStops))
        assert(commandCount()==0, "Later edit may not overtake the earlier deferred edit")
        local delayedAssign=makeCommand("VLINE",403,"b:41")
        delayedAssign.line="b:400"
        test.execVehCmd(delayedAssign)
        assert(assignmentCount()==2 and #test.CM.retryQueue==3)
        runRetries()
        assert(commandCount()==2 and assignmentCount()==2,
               "Assignment waits for nonempty line's in-flight edits too")
        flushCommands(); runRetries(); flushCommands()
        assert(lineStops("b:400")==2 and assignmentCount()==3)
        assert(assignedLine(800)==test.lineIdFor("b:400"))
        assert(next(test.CM.lineDependencyWaiters)==nil)
        assert(next(test.CM.lineUpdatesInFlight)==nil)

        -- A thrown command dispatch must release its in-flight marker.
        local send=api.cmd.sendCommand
        api.cmd.sendCommand=function() error("engine rejected dispatch") end
        test.execLine(makeCommand("LUPDATE",404,"b:400",twoStops))
        api.cmd.sendCommand=send
        assert(next(test.CM.lineUpdatesInFlight)==nil)

        -- Use the actual production queue for paused/asynchronous behavior.
        -- Neither callbacks nor key binding advance the simulation clock.
        setClock(200.8)
        local pausedCreate=makeCommand("LCREATE",500)
        local pausedFirst=makeCommand("LUPDATE",501,"b:500",oneStop)
        local pausedLast=makeCommand("LUPDATE",502,"b:500",twoStops)
        local pausedAssign=makeCommand("VLINE",503,"b:41")
        pausedAssign.line="b:500"
        test.enqueue(pausedCreate); test.enqueue(pausedFirst)
        test.enqueue(pausedLast); test.enqueue(pausedAssign)
        test.pump(currentTime)
        assert(pausedFirst.lineDependencyTries==1 and pausedLast.lineDependencyTries==1)
        assert(commandCount()==1 and assignmentCount()==3 and test.queued()==0)
        flushCommands(); test.pollLineKeys()
        test.pump(currentTime)
        assert(commandCount()==2 and assignmentCount()==3,
               "Due line edits must retry through real queue while paused")
        flushCommands()
        test.pump(currentTime); flushCommands()
        assert(currentTime==200.8 and lineStops("b:500")==2)
        assert(assignmentCount()==4 and assignedLine(800)==test.lineIdFor("b:500"))
        assert(pausedFirst.at==200.8 and pausedFirst.notBeforeStep==nil)
        assert(test.queued()==0 and #test.CM.retryQueue==0)

        -- A pre-existing target (including a batch-buy guard) stays in the
        -- future until reached. Once reached, an async key can bind without
        -- requiring another simulation step, including on the originator.
        local guarded=makeCommand("VLINE",600,"a:599")
        guarded.origin="a"; guarded.armed=1; guarded.line="b:500"
        guarded.notBeforeStep=test.CM.stepOf(202.8)
        test.enqueue(guarded)
        test.pump(200.8); test.pump(202.6)
        assert(guarded.tries==nil and test.queued()==1)
        setClock(202.8); test.pump(currentTime)
        assert(guarded.tries==1 and guarded.notBeforeStep==test.CM.stepOf(202.8))
        test.registerVehKey("a:599",802)
        test.pump(currentTime); flushCommands()
        assert(assignmentCount()==5 and assignedLine(802)==test.lineIdFor("b:500"))
        assert(currentTime==202.8 and guarded.notBeforeStep==test.CM.stepOf(202.8))

        -- The original timestamp without a separate guard still prevents
        -- early execution through exactly the same production due-time gate.
        local future=makeCommand("LUPDATE",601,"b:500",oneStop)
        future.at=203.0
        test.enqueue(future); test.pump(currentTime)
        assert(test.queued()==1 and commandCount()==0)
        setClock(203.0); test.pump(currentTime); flushCommands()
        assert(test.queued()==0 and lineStops("b:500")==1)

        -- Late arrivals keep their identity and can complete callbacks while
        -- paused too; retries must not move their at or target into the future.
        local late=makeCommand("LUPDATE",701,"b:700",twoStops)
        late.at=100.0; late.notBeforeStep=test.CM.stepOf(100.0)
        test.enqueue(late); test.pump(currentTime)
        assert(late.lineDependencyTries==1)
        local lateCreate=makeCommand("LCREATE",700)
        lateCreate.at=100.0
        test.enqueue(lateCreate); test.pump(currentTime)
        flushCommands(); test.pollLineKeys()
        test.pump(currentTime); flushCommands()
        assert(late.at==100.0 and late.notBeforeStep==test.CM.stepOf(100.0))
        assert(currentTime==203.0 and lineStops("b:700")==2)

        -- Bounded attempts are update attempts, not an inner-loop spin. Even
        -- with frozen time, each pump retries at most once and eventually
        -- releases all ordering markers after a permanently missing key.
        local never=makeCommand("LUPDATE",800,"missing-through-pump",oneStop)
        test.enqueue(never); test.pump(currentTime)
        assert(never.lineDependencyTries==1)
        test.pump(currentTime)
        assert(never.lineDependencyTries==2)
        for i=1,59 do test.pump(currentTime) end
        assert(never.lineDependencyTries==61 and currentTime==203.0)
        assert(test.queued()==0 and #test.CM.retryQueue==0)
        assert(next(test.CM.lineDependencyWaiters)==nil)
    ''')
    print(f"PASS {version}: async dependencies ordered; production queue retries while paused, preserves future guards and bounds attempts")
