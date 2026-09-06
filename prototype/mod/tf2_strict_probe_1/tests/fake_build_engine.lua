-- Purpose-built field-shape fixture; no production game or game files touched.
world={};legacy={};now=13.4;speed=1;money=5000000;sent=0;nextid=100+(id_offset or 0)
function fresh()nextid=nextid+1;return nextid end
function copy(v)if type(v)~='table'or getmetatable(v)then return v end;local out={};for k,x in pairs(v)do out[k]=copy(x)end;return out end
-- Closed temporary handles provide genuine Lua userdata on all four runtimes.
-- No live handle remains; its private metatable models TF2's native containers.
-- This deliberately does not spoof type(), and plain pairs() cannot traverse
-- an opaque userdata. TF2/sol2 supplies the pairs dispatch on Lua 5.1 as well.
local standard_pairs=pairs
if _VERSION=='Lua 5.1'then
  pairs=function(value)
    if type(value)=='userdata'then
      local mt=getmetatable(value)
      if mt and mt.__pairs then return mt.__pairs(value)end
    end
    return standard_pairs(value)
  end
end
function native_params(value,mode,seen)
  if type(value)~='table'then return value end
  mode=mode or 'pairs';seen=seen or {};if seen[value]then return seen[value]end
  local backing,members={},{}
  local object=assert(io.tmpfile());assert(object:close());seen[value]=object
  local enumerate=function()return next,backing,nil end
  local mt={__index=function(_,key)return backing[key]end,__newindex=function(_,key,v)backing[key]=v end}
  if mode=='pairs'then mt.__pairs=enumerate;mt.pairs=enumerate
  elseif mode=='members'then mt.__members=members
  elseif mode~='opaque'then error('unknown fixture params mode')end
  debug.setmetatable(object,mt)
  for key,child in standard_pairs(value)do
    members[#members+1]=key;backing[key]=native_params(child,mode,seen)
  end
  return object
end
local function v3(x,y,z)return{x=x,y=y,z=z}end
local function v4(x,y,z,w)return{x=x,y=y,z=z,w=w}end
local function mat(a,b,c,d)
  local cols={a,b,c,d};local object=native_params({},'opaque')
  getmetatable(object).__index=function(_,k)
    if k=='col'then return function(_,i)return cols[i+1]end end
    error('Mat4f has no flat index')
  end
  return object
end
function native_indexed(values)
  local object=native_params(values,'opaque');local mt=getmetatable(object);local read=mt.__index
  mt.__index=function(self,k)
    if type(k)~='number'or k%1~=0 then error('native indexed value rejects named member')end
    local value=read(self,k);if value==nil then error('native indexed value has no index '..k)end
    return value
  end
  return object
end
function native_record(values)
  local object=native_params({},'opaque');local mt=getmetatable(object)
  mt.__index=function(_,key)
    local value=values[key];if value==nil then error('native record has no member '..tostring(key))end
    return value
  end
  return object
end
function observed_matrix(value)
  local values,names={},{'x','y','z','w'}
  for i=0,3 do local column=value:col(i)
    for j=1,4 do values[#values+1]=column[names[j]]end
  end
  return native_indexed(values)
end
local function vecfields(fields)
  local stored=fields
  return setmetatable({},{__index=function(_,k)local v=stored[k];return type(v)=='table'and copy(v)or v end,
    __newindex=function(_,k,v)stored[k]=copy(v)end})
end
world[0]={TERRAIN={waterLevel=0}}
api={type={ComponentType=setmetatable({},{__index=function(_,k)return k end}),
  Vec2f={new=function(x,y)return{x=x,y=y}end},Vec3f={new=v3},Vec4f={new=v4},Mat4f={new=mat},
  Box3={new=function(a,b)return{min=a,max=b}end},Context={new=function()return{}end},
  SimpleProposal={new=function()return{constructionsToAdd={}}end,ConstructionEntity={new=function()return{}end}},
  VehiclePart={new=function()return vecfields({loadConfig={}})end},TransportVehiclePart={new=function()return vecfields({autoLoadConfig={}})end},
  TransportVehicleConfig={new=function()return{vehicles={},vehicleGroups={}}end},
  Line={new=function()return{stops={}}end,Stop={new=function()return{alternativeTerminals={},waypoints={}}end}},
  enum={TransportVehicleState={IN_DEPOT=0,EN_ROUTE=1}}},
  engine={entityExists=function(id)return world[id]~=nil end,getComponent=function(id,kind)return world[id]and world[id][kind]end,
    forEachEntityWithComponent=function(fn,kind)for id,w in pairs(world)do if w[kind]then fn(id)end end end,
    util={getPlayer=function()return 1 end},terrain={isValidCoordinate=function()return true end,getHeightAt=function()return 10 end},
    system={octreeSystem={findIntersectingEntities=function()end},stationGroupSystem={getStationGroup=function(s)return world[s].group end},
      transportVehicleSystem={getLineVehicles=function(id)local out={};for n,w in pairs(world)do if w.TRANSPORT_VEHICLE and w.TRANSPORT_VEHICLE.line==id then out[#out+1]=n end end;return out end}}},
  res={modelRep={find=function(name)return name==assets.vehicle_model and 7 or -1 end,getName=function(id)return id==7 and assets.vehicle_model or nil end,
      get=function(id)return id==7 and {metadata={transportVehicle={}}}or nil end},
    streetTypeRep={find=function(name)return name==assets.street_type and 8 or -1 end,getName=function(id)return id==8 and assets.street_type or nil end}},
  cmd={make={}}}
game={interface={getEntity=function(id)if id==1 then return{balance=money,loan=5000000}end;return legacy[id]end,
  getGameTime=function()return{time=now}end,getGameSpeed=function()return speed end}}
api.cmd.make.setGameSpeed=function(s)return{op='pause',value=s}end
api.cmd.make.buildProposal=function(p,c,ignore)return{op='build',proposal=p,context=c,ignore=ignore}end
api.cmd.make.buyVehicle=function(player,depot,cfg)return{op='buy',depot=depot,config=cfg}end
api.cmd.make.createLine=function(name,color,player,line)return{op='line',name=name,color=color,line=line}end
api.cmd.make.setLine=function(v,l,stop)return{op='assign',vehicle=v,line=l,stop=stop}end
local function node(x,y,z)local id=fresh();world[id]={BASE_NODE={position=v3(x,y,z)}};return id end
local function edge(a,b)
  local id=fresh();world[id]={BASE_EDGE={node0=a,node1=b,tangent0=v3(1,0,0),tangent1=v3(1,0,0),type=0,typeIndex=-1},
    BASE_EDGE_STREET={streetType=8,hasBus=false,tramTrackType=0}};return id
end
function apply_command(cmd,no_result)
  sent=sent+1;local result={}
  if cmd.op=='pause'then speed=cmd.value
  elseif cmd.op=='build'then
    local c=cmd.proposal.constructionsToAdd[1];local id=fresh();local co={fileName=c.fileName,params=native_params(copy(c.params)),transf=observed_matrix(c.transf),timeBuild=math.floor(now*1000),frozenEdges={},stations={},depots={}}
    world[id]={CONSTRUCTION=co,NAME={name=c.name}}
    if c.fileName==assets.road_file then
      junction=node(0,0,10);roadends={node(-80,0,10),node(80,0,10),node(0,40,10)}
      for _,n in ipairs(roadends)do co.frozenEdges[#co.frozenEdges+1]=edge(junction,n)end
    elseif c.fileName==assets.depot_file then
      local child=fresh();world[child]={VEHICLE_DEPOT={carrier=0,state=0,doors=0,stateTime=0}};co.depots={child}
      co.frozenEdges={edge(roadends[3],node(0,65,10))}
    else
      local index=c.name:sub(-1)=='1'and 1 or 2;co.frozenEdges={edge(roadends[index],node(index==1 and -115 or 115,0,10))}
      local s,g=fresh(),fresh();world[s]={STATION={cargo=false,terminals={{},{}}},group=g};world[g]={STATION_GROUP={stations={s}}};co.stations={s}
    end
    money=money-10000;result.resultEntities={id}
  elseif cmd.op=='buy'then
    local id=fresh();world[id]={TRANSPORT_VEHICLE={state=0,line=-1,depot=cmd.depot,userStopped=false,noPath=false,stopIndex=0,carrier=0,transportVehicleConfig=cmd.config}}
    money=money-1000;vehicle_id=id;result.resultVehicleEntity=id
  elseif cmd.op=='line'then
    local id=fresh();world[id]={LINE=cmd.line,NAME={name=cmd.name},COLOR={color=cmd.color}};result.resultEntity=id
  elseif cmd.op=='assign'then world[cmd.vehicle].TRANSPORT_VEHICLE.line=cmd.line end
  return no_result and{}or native_record(result)
end
function advance()
  now=now+.2
  if vehicle_id then local v=world[vehicle_id].TRANSPORT_VEHICLE
    if v.line>0 then v.state=1;legacy[vehicle_id]={position=v3(now,0,10)}
      world[vehicle_id].MOVE_PATH={dyn={speed=4,pathPos={edgeIndex=0,pos=now,pos01=.1}}}
    end
  end
end
