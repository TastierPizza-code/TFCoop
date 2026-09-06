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
-- Alpha5.7 reached a genuine native incidence collection with #value > 0
-- while value[1] was nil. The upstream/Sol2 collection contract uses pairs
-- VALUES; this fixture exercises that contract, which the ZIP did not record.
-- Neither numeric indexing nor the iterator keys identify an edge.
function native_entity_collection(values)
  local object=native_params({},'opaque');local mt=getmetatable(object)
  mt.__len=function()return #values end
  mt.__index=function()return nil end
  mt.__pairs=function()
    local index=0;local reverse=incidence_reverse==true
    return function()
      index=index+1;if index>#values then return nil end
      local at=reverse and #values-index+1 or index
      return 'opaque-incidence-slot-'..index,values[at]
    end,object,nil
  end
  mt.pairs=mt.__pairs
  return object
end
native_incidence=native_entity_collection
-- The recovered Alpha5.4 reports exposed genuine component userdata whose
-- absent timeBuild member returned nil. Preserve that distinction from a
-- native getter exception and keep live mutable backing fields for tests.
function observed_construction(values)
  local object=native_params({},'opaque');local mt=getmetatable(object)
  mt.__index=function(_,key)return values[key]end
  mt.__newindex=function(_,key,value)values[key]=value end
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
  SimpleProposal={new=function()return{constructionsToAdd={},constructionsToRemove={},streetProposal={nodesToAdd={},nodesToRemove={},edgesToAdd={},edgesToRemove={},edgeObjectsToAdd={},edgeObjectsToRemove={}}}end,ConstructionEntity={new=function()return{}end}},
  SegmentAndEntity={new=function()return{comp={node0=-1,node1=-1,type=0,typeIndex=-1,objects={}},type=0}end},
  BaseEdgeStreet={new=function()return{streetType=-1,hasBus=false,tramTrackType=0}end},
  VehiclePart={new=function()return vecfields({loadConfig={}})end},TransportVehiclePart={new=function()return vecfields({autoLoadConfig={}})end},
  TransportVehicleConfig={new=function()return{vehicles={},vehicleGroups={}}end},
  Line={new=function()return{stops={}}end,Stop={new=function()return{alternativeTerminals={},waypoints={}}end}},
  enum={TransportVehicleState={IN_DEPOT=0,EN_ROUTE=1}}},
  engine={entityExists=function(id)return world[id]~=nil end,getComponent=function(id,kind)return world[id]and world[id][kind]end,
    forEachEntityWithComponent=function(fn,kind)for id,w in pairs(world)do if w[kind]then fn(id)end end end,
    util={getPlayer=function()return 1 end},terrain={isValidCoordinate=function()return true end,getHeightAt=function()return 10 end},
    system={octreeSystem={findIntersectingEntities=function()end},stationGroupSystem={getStationGroup=function(s)return world[s].group end},
      streetSystem={getNode2StreetEdgeMap=function()
        local out={};for id,w in pairs(world)do
          if w.BASE_EDGE and w.BASE_EDGE_STREET then
            for _,n in ipairs({w.BASE_EDGE.node0,w.BASE_EDGE.node1})do out[n]=out[n]or{};out[n][#out[n]+1]=id end
          end
        end
        for node,ids in pairs(out)do table.sort(ids);out[node]=native_incidence(ids)end;return out
      end},
      -- Unordered membership uses the same upstream pairs-values contract;
      -- this models it without claiming its native C++ type was measured.
      transportVehicleSystem={getLineVehicles=function(id)local out={};for n,w in pairs(world)do if w.TRANSPORT_VEHICLE and w.TRANSPORT_VEHICLE.line==id then out[#out+1]=n end end;return native_entity_collection(out) end}}},
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
  local pa,pb=world[a].BASE_NODE.position,world[b].BASE_NODE.position
  local tangent=v3(pb.x-pa.x,pb.y-pa.y,pb.z-pa.z)
  local id=fresh();world[id]={BASE_EDGE={node0=a,node1=b,tangent0=copy(tangent),tangent1=copy(tangent),type=0,typeIndex=-1},
    BASE_EDGE_STREET={streetType=8,hasBus=false,tramTrackType=0}};return id
end
function apply_command(cmd,no_result)
  sent=sent+1;local result={}
  if cmd.op=='pause'then speed=cmd.value
  elseif cmd.op=='build'and #cmd.proposal.constructionsToAdd==0 then
    -- The script API never welds coordinates. A link exists only when the
    -- proposal names the two already-existing node identities explicitly.
    local sp=cmd.proposal.streetProposal
    assert(#sp.nodesToAdd==0 and #sp.nodesToRemove==0 and #sp.edgesToRemove==0,'fixture connector must use existing nodes only')
    assert(#cmd.proposal.constructionsToRemove==0,'fixture connector cannot remove constructions')
    connector_ids={}
    for _,e in ipairs(sp.edgesToAdd)do
      assert(e.entity<0 and e.type==0,'fixture connector must be a new road edge')
      assert(e.comp.node0>0 and e.comp.node1>0 and e.comp.node0~=e.comp.node1,'fixture requires distinct existing node IDs')
      assert(world[e.comp.node0]and world[e.comp.node0].BASE_NODE and world[e.comp.node1]and world[e.comp.node1].BASE_NODE,'fixture connector references absent node')
      local id=fresh();world[id]={BASE_EDGE=copy(e.comp),BASE_EDGE_STREET=copy(e.streetEdge)};connector_ids[#connector_ids+1]=id
    end
    money=money-1000*#connector_ids
    -- Measured by the upstream engine integration: pure street commands have
    -- an empty resultEntities vector, even after successful edge creation.
    result.resultEntities={}
  elseif cmd.op=='build'then
    local c=cmd.proposal.constructionsToAdd[1];local id=fresh();local co={fileName=c.fileName,params=native_params(copy(c.params)),transf=observed_matrix(c.transf),timeBuild=observed_time_build,frozenEdges={},frozenNodes={},stations={},depots={}}
    local function placed(point)
      local x,y,z,t=c.transf:col(0),c.transf:col(1),c.transf:col(2),c.transf:col(3)
      return node(t.x+x.x*point[1]+y.x*point[2]+z.x*point[3],t.y+x.y*point[1]+y.y*point[2]+z.y*point[3],t.z+x.z*point[1]+y.z*point[2]+z.z*point[3])
    end
    world[id]={CONSTRUCTION=observed_construction(co),NAME={name=c.name}}
    if c.fileName==assets.road_file then
      junction=placed(assets.road_junction);roadends={};co.frozenNodes={junction}
      for _,point in ipairs(assets.road_endpoints)do roadends[#roadends+1]=placed(point)end
      for _,n in ipairs(roadends)do co.frozenEdges[#co.frozenEdges+1]=edge(junction,n)end
    elseif c.fileName==assets.depot_file then
      local child=fresh();world[child]={VEHICLE_DEPOT={carrier=0,state=0,doors=0,stateTime=0}};co.depots={child}
      local inner=placed({0,-20.79972,0});depot_outer=placed({0,-30.4153,0})
      co.frozenNodes={inner};co.frozenEdges={edge(inner,depot_outer)}
    else
      local index=c.name:sub(-1)=='1'and 1 or 2;stop_outer=stop_outer or{}
      local inner=placed({0,-15,0});stop_outer[index]=placed({0,-35,0})
      co.frozenNodes={inner};co.frozenEdges={edge(inner,stop_outer[index])}
      local s,g=fresh(),fresh();world[s]={STATION={cargo=false,terminals={{},{}}},group=g};world[g]={STATION_GROUP={stations={s}}};co.stations={s}
    end
    money=money-10000;result.resultEntities={id}
  elseif cmd.op=='buy'then
    local id=fresh();world[id]={TRANSPORT_VEHICLE={state=0,line=-1,depot=cmd.depot,userStopped=false,noPath=false,stopIndex=nil,carrier=0,transportVehicleConfig=cmd.config}}
    money=money-1000;vehicle_id=id;result.resultVehicleEntity=id
  elseif cmd.op=='line'then
    local id=fresh();world[id]={LINE=cmd.line,NAME={name=cmd.name},COLOR={color=cmd.color}};result.resultEntity=id
  elseif cmd.op=='assign'then world[cmd.vehicle].TRANSPORT_VEHICLE.line=cmd.line;world[cmd.vehicle].TRANSPORT_VEHICLE.stopIndex=cmd.stop end
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
