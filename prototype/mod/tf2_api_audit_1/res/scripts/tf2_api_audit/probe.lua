-- Raw observations only. This module never dispatches game commands and never
-- promotes an observation (including constructor defaults) to a sync snapshot.
local M = {}
local MAX_BYTES, MAX_RECORDS, MAX_STRING = 98304, 1024, 256
local MAX_MEMBERS, MAX_DEPTH, MAX_ARRAY = 6, 3, 6
local function finite(v)return type(v)=='number' and v==v and v~=math.huge and v~=-math.huge end
local function container(v)return type(v)=='table' or type(v)=='userdata' end
local function safe_field(v,k)
  local ok,x=pcall(function()return v[k]end)
  if ok then return x end
  return nil
end
-- Keep valid Unicode whole; invalid bytes and pointer-looking strings are not
-- written to the report. Never call tostring on an opaque object/error.
function M.safe_text(value)
  if type(value)~='string' then return 'non-string '..type(value) end
  value=value:gsub('0[xX]%x+','[address]')
  local out,n,i={},0,1
  while i<=#value and n<MAX_STRING do
    local b=value:byte(i);local size=b<128 and 1 or (b>=194 and b<=223 and 2 or (b>=224 and b<=239 and 3 or (b>=240 and b<=244 and 4 or 0)))
    local valid=size>0 and i+size-1<=#value
    if valid and size>1 then
      for j=1,size-1 do local c=value:byte(i+j);if c<128 or c>191 then valid=false end end
      local c=value:byte(i+1)
      if (b==224 and c<160)or(b==237 and c>159)or(b==240 and c<144)or(b==244 and c>143)then valid=false end
    end
    if not valid then out[#out+1]='?';n=n+1;i=i+1
    elseif n+size>MAX_STRING then break
    else out[#out+1]=value:sub(i,i+size-1);n=n+size;i=i+size end
  end
  return table.concat(out)
end
function M.collect(api,game,json,options)
  options=options or {}
  local report={format=1,mode='read_only_api_audit',status='completed',valid_snapshot=false,
    request_id=M.safe_text(options.request_id or ''),records=json.array(),truncated=false,
    limits={max_bytes=MAX_BYTES,max_records=MAX_RECORDS,max_string_bytes=MAX_STRING,
      max_depth=MAX_DEPTH,max_members=MAX_MEMBERS,max_array_entries=MAX_ARRAY,
      max_entities_per_component=2,max_bindings=16,dropped_records=0}}
  local records,priorities=report.records,{}
  local sample_priority=2
  local function truncated()report.truncated=true end
  local function priority(origin,path)
    if sample_priority==0 then return 0 end
    if path:find('.params.',1,true)then return 1 end
    if path:find('constructor.Mat4f',1,true)
      or path:find('.CONSTRUCTION.transf',1,true)or path:find('.CONSTRUCTION.timeBuild',1,true)
      or path:find('.BASE_EDGE',1,true)or path:find('.BASE_NODE',1,true)then return 3 end
    return 2
  end
  local function lowest()
    local index=#records
    for i=#records,1,-1 do if priorities[records[i]]<priorities[records[index]]then index=i end end
    return index
  end
  local function emit(origin,path,read)
    local ok,v=pcall(read)
    local row={origin=origin,path=M.safe_text(path),access=ok and (v==nil and 'nil' or 'ok')or 'throws',type=ok and type(v)or 'unavailable'}
    if not ok then row.error=M.safe_text(v)
    else
      local t=type(v)
      if t=='string' then row.value=M.safe_text(v);if row.value~=v then row.value_truncated=true;truncated()end
      elseif t=='boolean' then row.value=v
      elseif t=='number' then
        if finite(v)then row.value=v
        else row.value_text=v~=v and 'NaN' or (v>0 and '+Infinity'or '-Infinity')end
      elseif container(v)then
        local length_ok,length=pcall(function()return #v end)
        row.shape={length_access=length_ok and 'ok'or 'throws'}
        if length_ok and finite(length)then row.shape.length=length end
      end
      local number_ok,n=pcall(tonumber,v)
      row.numeric={conversion=number_ok and (n==nil and 'nil'or 'ok')or 'throws',
        finite=finite(n),integer=finite(n)and n%1==0 or false,
        safe_integer=finite(n)and n%1==0 and math.abs(n)<=9007199254740991 or false}
      if finite(n)then row.numeric.value=n end
    end
    priorities[row]=priority(origin,path)
    if #records<MAX_RECORDS then records[#records+1]=row
    else
      local index=lowest()
      if priorities[row]>priorities[records[index]]then priorities[records[index]]=nil;records[index]=row
      else priorities[row]=nil end
      report.limits.dropped_records=report.limits.dropped_records+1;truncated()
    end
    if ok then return v end
    return nil
  end
  local function leaf(origin,path,v,k)return emit(origin,path..'.'..k,function()return v[k]end)end
  local function leaves(origin,path,v,keys)
    for _,k in ipairs(keys)do leaf(origin,path,v,k)end
  end
  local function vector(origin,path,v,n)
    local names={'x','y','z','w'}
    for i=1,n do leaf(origin,path,v,names[i])end
    -- Read both candidate bases explicitly; do not choose one by assumption.
    for i=0,n do leaf(origin,path,v,i)end
  end
  local function matrix(origin,path,v)
    leaf(origin,path,v,'col') -- Presence/type only, no unknown member invocation.
    for i=0,16 do
      local x=leaf(origin,path,v,i)
      if i<5 and container(x)then vector(origin,path..'.'..i,x,4)end
    end
  end
  local function array(origin,path,v,visit,limit)
    if not container(v)then return end
    local n=emit(origin,path..'.#',function()return #v end)
    if not finite(n)or n<0 or n%1~=0 then return end
    limit=limit or MAX_ARRAY;if n>limit then truncated()end
    for i=1,math.min(n,limit)do
      local x=leaf(origin,path,v,i)
      if visit then visit(path..'.'..i,x)end
    end
  end
  local active={}
  local function generic(origin,path,v,depth)
    if not container(v)then return end
    if active[v]then emit(origin,path..'.@cycle',function()return true end);truncated();return end
    if depth>=MAX_DEPTH then truncated();return end
    active[v]=true
    local keys,seen={},{}
    local function key(k)
      if type(k)~='string'and not finite(k)then return end
      local identity=type(k)..':'..tostring(k)
      if not seen[identity]then
        if #keys<MAX_MEMBERS then keys[#keys+1]=k;seen[identity]=true else truncated()end
      end
    end
    -- __members is an explicit field contract used by the stock serializer.
    local mt=safe_field({getmetatable(v)},1)
    local members=container(mt)and safe_field(mt,'__members')or nil
    if container(members)then
      local n=emit(origin,path..'.@members.#',function()return #members end)
      if finite(n)and n>=0 and n%1==0 then
        if n>MAX_MEMBERS then truncated()end
        for i=1,math.min(n,MAX_MEMBERS)do key(emit(origin,path..'.@members.'..i,function()return members[i]end))end
      end
    else
      -- Manual bounded iteration: never exhaust an unbounded native iterator.
      emit(origin,path..'.@enumeration',function()
        local iter,state,control=pairs(v)
        for i=1,MAX_MEMBERS+1 do
          local k=iter(state,control);if k==nil then return 'complete' end
          control=k;key(k)
        end
        truncated();return 'limited'
      end)
    end
    for _,k in ipairs(keys)do
      local x=leaf(origin,path,v,k)
      generic(origin,path..'.'..k,x,depth+1)
    end
    active[v]=nil
  end
  local function part(origin,path,v)
    leaves(origin,path,v,{'modelId','reversed','logo'})
    local color=leaf(origin,path,v,'color');if container(color)then vector(origin,path..'.color',color,3)end
    array(origin,path..'.loadConfig',leaf(origin,path,v,'loadConfig'))
  end
  local function vehicle_part(origin,path,v)
    leaves(origin,path,v,{'purchaseTime','maintenanceState','targetMaintenanceState'})
    part(origin,path..'.part',leaf(origin,path,v,'part'))
    array(origin,path..'.autoLoadConfig',leaf(origin,path,v,'autoLoadConfig'))
  end
  local function vehicle_config(origin,path,v)
    array(origin,path..'.vehicles',leaf(origin,path,v,'vehicles'),function(p,x)vehicle_part(origin,p,x)end,2)
    array(origin,path..'.vehicleGroups',leaf(origin,path,v,'vehicleGroups'))
  end
  local function stop(origin,path,v)
    leaves(origin,path,v,{'stationGroup','station','terminal','loadMode','minWaitingTime','maxWaitingTime'})
  end
  local function line(origin,path,v)
    leaf(origin,path,v,'waitingTime')
    array(origin,path..'.stops',leaf(origin,path,v,'stops'),function(p,x)stop(origin,p,x)end)
  end
  local schemas={
    CONSTRUCTION=function(o,p,v)
      leaves(o,p,v,{'fileName','timeBuild'})
      generic(o,p..'.params',leaf(o,p,v,'params'),0)
      matrix(o,p..'.transf',leaf(o,p,v,'transf'))
      for _,k in ipairs({'frozenNodes','frozenEdges','depots','stations'})do array(o,p..'.'..k,leaf(o,p,v,k))end
    end,
    BASE_EDGE=function(o,p,v)
      leaves(o,p,v,{'node0','node1','type','typeIndex'})
      for _,k in ipairs({'tangent0','tangent1'})do vector(o,p..'.'..k,leaf(o,p,v,k),3)end
    end,
    BASE_EDGE_STREET=function(o,p,v)leaves(o,p,v,{'streetType','hasBus','tramTrackType'})end,
    BASE_NODE=function(o,p,v)vector(o,p..'.position',leaf(o,p,v,'position'),3)end,
    VEHICLE_DEPOT=function(o,p,v)
      leaves(o,p,v,{'carrier','state','doors','stateTime'})
      for _,k in ipairs({'inNodes','outNodes'})do array(o,p..'.'..k,leaf(o,p,v,k))end
    end,
    STATION=function(o,p,v)
      leaf(o,p,v,'cargo');array(o,p..'.terminals',leaf(o,p,v,'terminals'),function(q,x)generic(o,q,x,0)end)
    end,
    STATION_GROUP=function(o,p,v)array(o,p..'.stations',leaf(o,p,v,'stations'))end,
    LINE=line,
    TRANSPORT_VEHICLE=function(o,p,v)
      leaves(o,p,v,{'carrier','state','userStopped','noPath','line','depot','stopIndex'})
      vehicle_config(o,p..'.transportVehicleConfig',leaf(o,p,v,'transportVehicleConfig'))
    end,
    MOVE_PATH=function(o,p,v)
      local dyn=leaf(o,p,v,'dyn');leaf(o,p..'.dyn',dyn,'speed')
      local pos=leaf(o,p..'.dyn',dyn,'pathPos')
      leaves(o,p..'.dyn.pathPos',pos,{'edgeIndex','pos','pos01'})
    end,
    NAME=function(o,p,v)leaf(o,p,v,'name')end,
    COLOR=function(o,p,v)vector(o,p..'.color',leaf(o,p,v,'color'),3)end,
    TERRAIN=function(o,p,v)leaf(o,p,v,'waterLevel')end,
  }
  local order={'CONSTRUCTION','BASE_EDGE','BASE_EDGE_STREET','BASE_NODE','VEHICLE_DEPOT','LINE','TRANSPORT_VEHICLE','MOVE_PATH','STATION','STATION_GROUP','NAME','COLOR','TERRAIN'}
  local function constructor(name,args,visit)
    local path='constructor.'..name
    local x=emit('constructor',path,function()
      local t=api.type
      for k in name:gmatch('[^.]+')do t=t[k]end
      return t.new((unpack or table.unpack)(args or {}))
    end)
    if x~=nil and visit then visit('constructor',path,x)end
    return x
  end
  local cols={}
  for i=1,4 do cols[i]=constructor('Vec4f',{i==1 and 1 or 0,i==2 and 1 or 0,i==3 and 1 or 0,i==4 and 1 or 0},i==1 and function(o,p,v)vector(o,p,v,4)end or nil)end
  constructor('Mat4f',cols,matrix)
  constructor('Vec2f',{1,2},function(o,p,v)vector(o,p,v,2)end)
  constructor('Vec3f',{1,2,3},function(o,p,v)vector(o,p,v,3)end)
  constructor('VehiclePart',{},part)
  constructor('TransportVehiclePart',{},vehicle_part)
  constructor('TransportVehicleConfig',{},vehicle_config)
  constructor('Line',{},line)
  constructor('Line.Stop',{},stop)
  local player=emit('world','game.player',function()return api.engine.util.getPlayer()end)
  local time=emit('world','game.time',function()return game.interface.getGameTime()end)
  leaf('world','game.time',time,'time')
  emit('world','game.speed',function()return game.interface.getGameSpeed()end)
  local company=emit('world','game.player.entity',function()return game.interface.getEntity(player)end)
  if company~=nil then leaves('world','game.player.entity',company,{'balance','loan'})end
  local function inspect(id,kind,prefix)
    local p=prefix..'.'..kind
    local x=emit('world',p,function()return api.engine.getComponent(id,api.type.ComponentType[kind])end)
    if x~=nil then schemas[kind]('world',p,x)end
    if kind=='TRANSPORT_VEHICLE'and x~=nil then
      local entity=emit('world',prefix..'.entity',function()return game.interface.getEntity(id)end)
      local position=leaf('world',prefix..'.entity',entity,'position')
      if position~=nil then vector('world',prefix..'.entity.position',position,3)end
    end
  end
  if type(options.bindings)=='table'and next(options.bindings)~=nil then
    local n=0
    for logical,id in pairs(options.bindings)do
      n=n+1;if n>16 then truncated();break end
      sample_priority=n==1 and 2 or 0
      if type(logical)=='string'and finite(id)and id%1==0 then
        for _,kind in ipairs(order)do inspect(id,kind,'bindings.'..M.safe_text(logical))end
      else emit('world','bindings.invalid',function()error('binding requires string key and integer entity',0)end)end
    end
  else
    for _,kind in ipairs(order)do
      sample_priority=2
      local found={}
      emit('world','entities.'..kind..'.@enumeration',function()
        api.engine.forEachEntityWithComponent(function(id)
          if #found<2 and finite(id)and id%1==0 then found[#found+1]=id end
        end,api.type.ComponentType[kind])
        return #found
      end)
      for i,id in ipairs(found)do sample_priority=i==1 and 2 or 0;inspect(id,kind,'entities.'..kind..'.'..i)end
    end
  end
  -- Keep the complete first matrix/road example (including successful numbers)
  -- ahead of second examples and deep parameter details. Missing array-base or
  -- method alternatives must not crowd the useful first example out.
  while true do
    local ok,raw=pcall(json.encode,report)
    if ok and #raw<=MAX_BYTES then break end
    if #records==0 then error('API diagnostic envelope cannot be encoded',0)end
    local index=lowest();priorities[records[index]]=nil
    table.remove(records,index);report.limits.dropped_records=report.limits.dropped_records+1;truncated()
  end
  return report
end
return M
