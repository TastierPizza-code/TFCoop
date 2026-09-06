-- Explicit, bounded test intents. No native UI observation or world mutation
-- outside apply(). There are no guessed model/configuration fallbacks.
local M = {}
local MAX_OBJECTS, MAX_PARTS, MAX_STOPS = 64, 4, 32

function M.new(json)
  local E = { bindings = {}, reverse = {}, count = 0 }
  local function need(v, message) if v == nil then error(message, 0) end; return v end
  local function field(v, key)
    local ok, result = pcall(function() return v[key] end)
    if ok then return result end
  end
  local function number(v)
    local n = tonumber(v)
    if not n or n ~= n or n == math.huge or n == -math.huge or math.abs(n) > 9007199254740991 then error('invalid finite number', 0) end
    return n
  end
  local function integer(v, low, high)
    local n = number(v)
    if n % 1 ~= 0 or n < (low or -9007199254740991) or n > (high or 9007199254740991) then error('integer outside range', 0) end
    return n
  end
  local function bool(v) if type(v) ~= 'boolean' then error('boolean required', 0) end; return v end
  local function text(v)
    if type(v) ~= 'string' or #v == 0 or #v > 256 or v:find('[%z\1-\31]') then error('bounded text required', 0) end
    return v
  end
  local function key(v)
    text(v); if #v > 96 or not v:match('^[%w_:%-%.]+$') then error('invalid logical key', 0) end; return v
  end
  local function decimal(v) return string.format('%.17g', number(v)) end
  local function arr(v, max)
    need(v, 'array unavailable')
    if v==json.null then error('array cannot be null',0) end
    local n = integer(#v, 0, max)
    if type(v)=='table' then for k in pairs(v) do
      if type(k)~='number' or k%1~=0 or k<1 or k>n then error('non-array key in array',0) end
    end end
    local out = json.array(); for i = 1, n do out[i] = v[i] end
    return out
  end
  local function vec(v, n, native)
    need(v, 'vector unavailable')
    local out, names = json.array(), { 'x','y','z','w' }
    for i = 1, n do
      local x = field(v, names[i]); if x == nil then x = field(v, i) end
      out[i] = native and number(x) or decimal(x)
    end
    return out
  end
  local function plain(v, depth)
    depth = depth or 0; if depth > 8 then error('plain-data depth limit', 0) end
    local t = type(v)
    if t == 'number' then return decimal(v) end
    if t == 'string' or t == 'boolean' then return v end
    if t ~= 'table' then error('unreadable nonplain data', 0) end
    local out, count = {}, 0
    -- Preserve map key types explicitly; construction module keys can be ints.
    local entries = json.array()
    for k, value in pairs(v) do
      count = count + 1; if count > 256 then error('plain-data width limit', 0) end
      if type(k) ~= 'number' and type(k) ~= 'string' then error('unsupported plain key', 0) end
      entries[#entries + 1] = { key_type=type(k), key=tostring(k), value=plain(value, depth + 1) }
    end
    table.sort(entries, function(a,b) return a.key_type .. ':' .. a.key < b.key_type .. ':' .. b.key end)
    out.entries = entries; return out
  end
  local function clone(v, depth)
    depth = depth or 0; if depth > 8 then error('template depth limit', 0) end
    if type(v) == 'number' then return number(v) end
    if type(v) == 'boolean' or type(v) == 'string' then return v end
    if type(v) ~= 'table' then error('template parameters are not plain data', 0) end
    local out, count = {}, 0
    for k, x in pairs(v) do count=count+1; if count>256 then error('template width limit',0) end; out[k]=clone(x,depth+1) end
    return out
  end
  local function comp(id, name)
    return need(api.engine.getComponent(id, need(api.type.ComponentType[name], 'component API unavailable: '..name)), 'component absent: '..name)
  end
  local function exists(id) return api.engine.entityExists(integer(id,1,2147483647)) == true end
  local function localid(logical, kind)
    local b=need(E.bindings[key(logical)], 'logical entity not bound: '..logical)
    if kind and b.kind ~= kind then error('logical entity has wrong kind',0) end
    if not exists(b.entity) then error('bound entity no longer exists: '..logical,0) end
    return b.entity
  end
  local function ref(id)
    if id == nil or tonumber(id) == -1 or tonumber(id) == 0 then return '' end
    return need(E.reverse[integer(id,1,2147483647)], 'unbound entity reference')
  end
  local function bind(logical, kind, id)
    key(logical); id=integer(id,1,2147483647)
    if E.bindings[logical] or E.reverse[id] or E.count>=MAX_OBJECTS then error('ambiguous/reused logical binding or binding limit',0) end
    if not exists(id) then error('result entity does not exist',0) end
    local cn={depot='CONSTRUCTION',vehicle='TRANSPORT_VEHICLE',line='LINE',station_group='STATION_GROUP',road='BASE_EDGE',depot_child='VEHICLE_DEPOT'}
    comp(id,need(cn[kind],'unsupported binding kind'))
    E.bindings[logical]={kind=kind,entity=id}; E.reverse[id]=logical; E.count=E.count+1
    if kind=='depot' then
      local children=arr(comp(id,'CONSTRUCTION').depots,4)
      if #children~=1 then error('probe supports exactly one depot child',0) end
      bind(logical..':depot:1','depot_child',children[1])
    end
  end
  local function resource(rep, id)
    local name=text(rep.getName(integer(id,0,2147483647)))
    if integer(rep.find(name),0,2147483647)~=id then error('resource name/index roundtrip failed',0) end
    return name
  end
  local function vehicle_config(cfg)
    local out={vehicles=json.array(),vehicleGroups=json.array()}
    for i,tvp in ipairs(arr(need(cfg.vehicles,'vehicle config unavailable'),MAX_PARTS)) do
      local part=need(tvp.part,'vehicle part unavailable')
      if type(part.logo)~='string' or #part.logo>256 then error('logo unavailable or invalid',0) end
      local lc,ac=json.array(),json.array()
      for j,v in ipairs(arr(part.loadConfig,64)) do lc[j]=integer(v,-1,100000) end
      for j,v in ipairs(arr(tvp.autoLoadConfig,64)) do ac[j]=decimal(v) end
      out.vehicles[i]={model=resource(api.res.modelRep,integer(part.modelId,0)),reversed=bool(part.reversed),
        color=vec(part.color,3),logo=need(part.logo,'logo unavailable'),loadConfig=lc,autoLoadConfig=ac,
        purchaseTime=decimal(tvp.purchaseTime),maintenanceState=decimal(tvp.maintenanceState),targetMaintenanceState=decimal(tvp.targetMaintenanceState)}
    end
    local sum=0; for i,v in ipairs(arr(cfg.vehicleGroups,MAX_PARTS)) do out.vehicleGroups[i]=integer(v,1,MAX_PARTS); sum=sum+v end
    if #out.vehicles<1 or sum~=#out.vehicles then error('invalid complete vehicle groups',0) end
    return out
  end
  local function line_state(id)
    local line=comp(id,'LINE'); local stops=json.array()
    for i,s in ipairs(arr(line.stops,MAX_STOPS)) do
      stops[i]={stationGroup=ref(s.stationGroup),station=integer(s.station,0),terminal=integer(s.terminal,0),
        loadMode=integer(s.loadMode,0),minWaitingTime=decimal(s.minWaitingTime),maxWaitingTime=decimal(s.maxWaitingTime),
        alternativeTerminals=plain(arr(s.alternativeTerminals,32)),waypoints=json.array()}
      for j,v in ipairs(arr(s.waypoints,32)) do stops[i].waypoints[j]=ref(v) end
    end
    local vehicles=json.array()
    for _,id2 in ipairs(arr(api.engine.system.transportVehicleSystem.getLineVehicles(id),64)) do vehicles[#vehicles+1]=ref(id2) end
    table.sort(vehicles)
    return {waitingTime=decimal(line.waitingTime),stops=stops,vehicles=vehicles,
      name=text(comp(id,'NAME').name),color=vec(comp(id,'COLOR').color,3)}
  end
  local function road_state(id)
    local edge=comp(id,'BASE_EDGE'); local street=comp(id,'BASE_EDGE_STREET')
    return {node0_identity=need(E.nodeSymbols[edge.node0],'unbound tracked road node'),node1_identity=need(E.nodeSymbols[edge.node1],'unbound tracked road node'),
      node0=vec(comp(edge.node0,'BASE_NODE').position,3),node1=vec(comp(edge.node1,'BASE_NODE').position,3),
      tangent0=vec(edge.tangent0,3),tangent1=vec(edge.tangent1,3),type=integer(edge.type),typeIndex=integer(edge.typeIndex),
      street=resource(api.res.streetTypeRep,integer(street.streetType,0)),hasBus=bool(street.hasBus),tramTrackType=integer(street.tramTrackType)}
  end
  local function matrix(v)
    local out=json.array()
    for i=1,16 do out[i]=decimal(v[i]) end
    return out
  end
  local function object_state(b)
    local id=b.entity
    if not exists(id) then error('tracked entity deleted',0) end
    if b.kind=='road' then return road_state(id) end
    if b.kind=='line' then return line_state(id) end
    if b.kind=='station_group' then return {station_count=#arr(comp(id,'STATION_GROUP').stations,32)} end
    if b.kind=='depot_child' then
      local d=comp(id,'VEHICLE_DEPOT')
      return {carrier=integer(d.carrier),state=integer(d.state),doors=integer(d.doors),stateTime=decimal(d.stateTime)}
    end
    if b.kind=='depot' then
      local c=comp(id,'CONSTRUCTION'); local edges=json.array()
      for _,edge in ipairs(arr(c.frozenEdges,128)) do edges[#edges+1]=road_state(edge) end
      table.sort(edges,function(a,b2)return json.encode(a)<json.encode(b2)end)
      return {file=text(c.fileName),params=plain(c.params),transform=matrix(c.transf),timeBuild=decimal(c.timeBuild),
        name=text(comp(id,'NAME').name),depot=ref(c.depots[1]),frozen_street_edges=edges}
    end
    local tv=comp(id,'TRANSPORT_VEHICLE')
    local out={config=vehicle_config(need(tv.transportVehicleConfig,'transport config unavailable')),line=ref(tv.line),depot=ref(tv.depot)}
    local arrival=need(tv.arrivalStationTerminal,'arrival terminal unavailable')
    out.arrivalStationTerminal={station=integer(arrival.station,-1),terminal=integer(arrival.terminal,-1)}
    out.capacities=json.array()
    for i,value in ipairs(arr(need(tv.config,'vehicle derived config unavailable').capacities,256)) do out.capacities[i]=integer(value,0) end
    for _,f in ipairs({'carrier','state','stopIndex','daysInDepot','daysAtTerminal'}) do out[f]=integer(need(tv[f],f..' unavailable')) end
    for _,f in ipairs({'userStopped','sellOnArrival','arrivalStationTerminalLocked','noPath','doorsOpen','autoDeparture'}) do out[f]=bool(need(tv[f],f..' unavailable')) end
    for _,f in ipairs({'timeUntilLoad','timeUntilCloseDoors','timeUntilDeparture','doorsTime'}) do out[f]=decimal(need(tv[f],f..' unavailable')) end
    local data=need(game.interface.getEntity(id),'vehicle legacy data unavailable')
    if data.position~=nil then out.position=vec(data.position,3)
    elseif tv.state==api.type.enum.TransportVehicleState.IN_DEPOT then out.position='in_depot'
    else error('moving vehicle position unavailable',0) end
    return out
  end
  function E.bind_initial(values)
    for _,b in ipairs(arr(values,MAX_OBJECTS)) do bind(b.logical_id,b.kind,b.entity) end
  end
  function E.snapshot()
    local missing=json.array(); local objects=json.array(); local keys={}
    for logical in pairs(E.bindings) do keys[#keys+1]=logical end; table.sort(keys)
    -- Canonical symbols preserve actual node sharing, including disconnected
    -- nodes at identical coordinates. No local numeric ID enters the digest.
    E.nodeSymbols={}
    local function nodes(edge_id,logical)
      local edge=comp(edge_id,'BASE_EDGE')
      for i=0,1 do local id=integer(edge['node'..i],1)
        E.nodeSymbols[id]=E.nodeSymbols[id] or (logical..':node:'..i)
      end
    end
    for _,logical in ipairs(keys) do
      local b=E.bindings[logical]
      pcall(function()
        if b.kind=='road' then nodes(b.entity,logical)
        elseif b.kind=='depot' then
          for i,id in ipairs(arr(comp(b.entity,'CONSTRUCTION').frozenEdges,128)) do nodes(id,logical..':frozen:'..i) end
        end
      end)
    end
    for _,logical in ipairs(keys) do
      local b=E.bindings[logical]; local ok,state=pcall(object_state,b)
      if not ok then missing[#missing+1]=logical..':'..tostring(state); state={unavailable=true} end
      objects[#objects+1]={logical_id=logical,kind=b.kind,state=state}
    end
    local player=api.engine.util.getPlayer(); local account=need(game.interface.getEntity(player),'company unavailable')
    local time=number(need(game.interface.getGameTime().time,'game time unavailable'))
    local speed=number(game.interface.getGameSpeed())
    return {sim_time_us=integer(math.floor(time*1000000+0.5),0),paused=speed==0,
      company={balance=integer(need(account.balance,'balance unavailable')),loan=integer(need(account.loan,'loan unavailable'),0)},
      objects=objects,coverage={complete_world=false,tracked_objects=true,missing=missing,
        excluded=json.array({'untracked_world','cargo_contents','path_reservations','terrain','rng','line_cargo_policy','station_internals','untracked_road_connectivity'})}}
  end
  function E.local_bindings()
    local out={}; for k,b in pairs(E.bindings) do out[k]=b.entity end; return out
  end
  local function context(c)
    need(c,'explicit build context required'); local out=api.type.Context:new()
    for _,name in ipairs({'checkTerrainAlignment','cleanupStreetGraph','gatherBuildings','gatherFields'}) do out[name]=bool(c[name]) end
    out.player=api.engine.util.getPlayer(); return out
  end
  local function make_line(c)
    local out=api.type.Line.new(); out.waitingTime=number(c.waiting_time)
    if out.waitingTime<0 then error('negative waiting time',0) end
    for i,v in ipairs(arr(c.stops,MAX_STOPS)) do
      local s=api.type.Line.Stop.new(); s.stationGroup=localid(v.station_group,'station_group')
      local stations=arr(comp(s.stationGroup,'STATION_GROUP').stations,32)
      if #stations==0 then error('station group has no stations',0) end
      s.station=integer(v.station,0,#stations-1)
      local terminals=arr(comp(stations[s.station+1],'STATION').terminals,256)
      if #terminals==0 then error('capability_missing: station has no readable terminals',0) end
      s.terminal=integer(v.terminal,0,#terminals-1); s.loadMode=integer(v.load_mode,0,2)
      s.minWaitingTime=number(v.min_wait); s.maxWaitingTime=number(v.max_wait)
      if s.minWaitingTime<0 or s.maxWaitingTime<s.minWaitingTime then error('invalid wait interval',0) end
      if #arr(v.alternative_terminals,32)~=0 or #arr(v.waypoints,32)~=0 then error('capability_missing: complex line stops',0) end
      out.stops[i]=s
    end
    return out
  end
  function E.plan(c,logical,sim_time_us)
    key(logical); need(c,'command required'); local op=text(c.op); local command; local kind; local target
    if E.bindings[logical] then error('command key already names an entity',0) end
    if op=='SET_PAUSED' then command=api.cmd.make.setGameSpeed(bool(c.value) and 0 or 1)
    elseif op=='LINE_CREATE' then
      if E.count+1>MAX_OBJECTS then error('binding limit',0) end
      local color=vec(c.color,3,true)
      for _,value in ipairs(color) do if value<0 or value>1 then error('color outside unit interval',0) end end
      command=api.cmd.make.createLine(text(c.name),api.type.Vec3f.new(color[1],color[2],color[3]),api.engine.util.getPlayer(),make_line(c)); kind='line'
      need(field(command,'resultEntity'),'capability_missing: CreateLine.resultEntity')
    elseif op=='LINE_UPDATE' then
      target=key(c.line); command=api.cmd.make.updateLine(localid(target,'line'),make_line(c))
    elseif op=='VEHICLE_ASSIGN' then
      target=key(c.vehicle); local line=localid(c.line,'line'); local count=#arr(comp(line,'LINE').stops,MAX_STOPS)
      if count<1 then error('cannot assign to an empty line',0) end
      command=api.cmd.make.setLine(localid(target,'vehicle'),line,integer(c.stop_index,0,count-1))
    elseif op=='DEPOT' then
      if E.count+2>MAX_OBJECTS then error('binding limit',0) end
      local source=comp(localid(c.template,'depot'),'CONSTRUCTION')
      local t=arr(c.transform,16); if #t~=16 then error('explicit 16-value transform required',0) end
      for i=1,16 do t[i]=number(t[i]) end
      if t[4]~=0 or t[8]~=0 or t[12]~=0 or t[16]~=1 then error('affine depot transform required',0) end
      for i=0,2 do for j=0,2 do
        local dot=0; for k2=1,3 do dot=dot+t[4*i+k2]*t[4*j+k2] end
        if math.abs(dot-(i==j and 1 or 0))>0.000001 then error('rigid depot transform required',0) end
      end end
      local det=t[1]*(t[6]*t[11]-t[10]*t[7])-t[5]*(t[2]*t[11]-t[10]*t[3])+t[9]*(t[2]*t[7]-t[6]*t[3])
      if math.abs(det-1)>0.000001 then error('proper rotation required for depot transform',0) end
      local p=api.type.SimpleProposal.new(); local n=api.type.SimpleProposal.ConstructionEntity.new()
      n.fileName=text(source.fileName); n.params=clone(source.params); n.name=text(c.name); n.playerEntity=api.engine.util.getPlayer()
      local cols={}; for i=1,4 do local j=(i-1)*4; cols[i]=api.type.Vec4f.new(number(t[j+1]),number(t[j+2]),number(t[j+3]),number(t[j+4])) end
      n.transf=api.type.Mat4f.new(cols[1],cols[2],cols[3],cols[4]); p.constructionsToAdd[1]=n
      command=api.cmd.make.buildProposal(p,context(c.context),bool(c.ignore_errors)); kind='depot'
      need(field(command,'resultEntities'),'capability_missing: BuildProposal.resultEntities')
    elseif op=='ROAD' then
      -- Upstream lockstep.lua:628 records an actual road build returning an
      -- empty resultEntities vector. Looking up equal geometry is not an exact
      -- native result mapping. Do not mutate the world and discover this later.
      error('capability_missing: exact created road entity mapping is not implemented',0)
    elseif op=='VEHICLE_BUY' then
      if E.count+1>MAX_OBJECTS then error('binding limit',0) end
      local source=comp(localid(c.template,'vehicle'),'TRANSPORT_VEHICLE')
      local depot=localid(key(c.depot)..':depot:1','depot_child'); local dep=comp(depot,'VEHICLE_DEPOT')
      if integer(source.carrier)~=integer(dep.carrier) then error('template carrier differs from depot carrier',0) end
      local cfg=vehicle_config(source.transportVehicleConfig)
      local purchase=integer(c.purchase_time_ms,1)
      if purchase~=math.floor(sim_time_us/1000) then error('purchase time must equal positive current simulation milliseconds',0) end
      local out=api.type.TransportVehicleConfig.new()
      for i,v in ipairs(cfg.vehicles) do
        local p=api.type.VehiclePart.new(); p.modelId=integer(api.res.modelRep.find(v.model),0); p.reversed=v.reversed; p.logo=v.logo
        p.color=api.type.Vec3f.new(number(v.color[1]),number(v.color[2]),number(v.color[3]))
        local load=p.loadConfig; for j,x in ipairs(v.loadConfig) do load[j]=x end; p.loadConfig=load
        local tvp=api.type.TransportVehiclePart.new(); tvp.part=p; tvp.purchaseTime=purchase
        tvp.maintenanceState=number(v.maintenanceState); tvp.targetMaintenanceState=number(v.targetMaintenanceState)
        local auto=tvp.autoLoadConfig; for j,x in ipairs(v.autoLoadConfig) do auto[j]=number(x) end; tvp.autoLoadConfig=auto; out.vehicles[i]=tvp
      end
      local groups=out.vehicleGroups; for i,x in ipairs(cfg.vehicleGroups) do groups[i]=x end; out.vehicleGroups=groups
      command=api.cmd.make.buyVehicle(api.engine.util.getPlayer(),depot,out); kind='vehicle'
      if field(command,'resultVehicleEntity')==nil and field(command,'resultEntity')==nil then error('capability_missing: BuyVehicle result entity',0) end
    else error('capability_missing: '..op,0) end
    return {native=need(command,'maker returned no command'),kind=kind,key=logical,target=target,command=c}
  end
  function E.finish(plan,result,success)
    if success~=true then return {success=false,result={error='engine_rejected'}} end
    local local_entity
    if plan.kind=='vehicle' or plan.kind=='line' then
      local a,b=field(result,'resultEntity'),field(result,'resultVehicleEntity')
      if tonumber(a) and tonumber(a)>0 then local_entity=integer(a,1) end
      if tonumber(b) and tonumber(b)>0 then if local_entity and local_entity~=tonumber(b) then error('ambiguous callback entity',0) end; local_entity=integer(b,1) end
      need(local_entity,'capability_missing: successful callback has no exact entity')
    elseif plan.kind then
      local candidates=arr(need(field(result,'resultEntities'),'callback entities unavailable'),128)
      local ct=plan.kind=='depot' and 'CONSTRUCTION' or 'BASE_EDGE'
      for _,id in ipairs(candidates) do
        local ok,c=pcall(api.engine.getComponent,id,api.type.ComponentType[ct])
        if ok and c then if local_entity then error('ambiguous callback entity set',0) end; local_entity=integer(id,1) end
      end
      need(local_entity,'capability_missing: callback does not expose created '..plan.kind)
    end
    if local_entity then bind(plan.key,plan.kind,local_entity) end
    local outcome=local_entity and {logical_id=plan.key} or {target=plan.target or ''}
    if plan.command.op=='SET_PAUSED' then outcome={paused=plan.command.value} end
    return {success=true,result=outcome,result_entity=local_entity}
  end
  E.integer=integer
  return E
end
return M
