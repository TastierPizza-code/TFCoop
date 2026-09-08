-- Deliberate primitive model, not a game emulator or runtime proof. Geometry
-- below uses the separately executed installed stock generator's actual ports.
local A=rail_assets
api.type.NodeAndEntity={new=function()return{comp={position={x=0,y=0,z=0}}}end}
api.type.BaseEdgeTrack={new=function()return{trackType=-1,catenary=false}end}
api.type.SimpleStreetProposal={EdgeObject={new=function()return{}end}}
api.type.enum.EdgeObjectType={SIGNAL=0}
api.cmd.make.replaceVehicle=setmetatable({},{__call=function(_,entity,cfg)
  command_factory_calls=command_factory_calls+1;return{op='rail_replace',entity=entity,config=cfg}
end})
local original_find,original_name,original_get=api.res.modelRep.find,api.res.modelRep.getName,api.res.modelRep.get
local models={[21]=A.locomotive,[22]=A.coach,[23]=A.signal,[24]=A.waypoint}
api.res.modelRep.find=function(name)for n,v in pairs(models)do if name==v then return n end end;return original_find(name)end
api.res.modelRep.getName=function(n)return models[n]or original_name(n)end
api.res.modelRep.get=function(n)if models[n]then return{metadata={transportVehicle={carrier=1}}}end;return original_get(n)end
api.res.trackTypeRep={find=function(name)return name==A.track and 20 or -1 end,getName=function(n)return n==20 and A.track or nil end,
  get=function(n)return n==20 and {railBase=.4,railHeight=.13}or nil end}
local modules={};for _,name in pairs(A.station_modules)do modules[#modules+1]=name end;table.sort(modules)
api.res.moduleRep={find=function(name)for i,n in ipairs(modules)do if n==name then return i end end;return -1 end,
  getName=function(n)return modules[n]end,get=function(n)
    local name=modules[n];assert(name)
    return {metadata=name:find('platform_track')and {track=true}or name:find('roof')and {platform_roof=true}
      or name:find('stairs')and {underground=true}or name:find('main_building')and {era=0,level=1,moreCapacity={passenger=20,cargo=0},span={1,2}}
      or {platform=true,passenger_platform=true}}
  end}
api.engine.system.streetSystem.getNode2TrackEdgeMap=function()
  local map={};for n,w in pairs(world)do if w.BASE_EDGE_TRACK then
    for _,node in ipairs({w.BASE_EDGE.node0,w.BASE_EDGE.node1})do map[node]=map[node]or {};map[node][#map[node]+1]=n end
  end end
  for node,list in pairs(map)do table.sort(list);map[node]=native_incidence(list)end
  return map
end
api.engine.system.streetSystem.getEdgeForEdgeObject=function(n)
  for eid,w in pairs(world)do if w.BASE_EDGE_TRACK then for _,o in ipairs(w.BASE_EDGE.objects)do if o[1]==n then return eid end end end end
  return -1
end
local function quoted(p)
  return #p.constructionsToAdd*18000+#p.constructionsToRemove*1500+
    #p.streetProposal.edgesToAdd*1000+#p.streetProposal.edgeObjectsToAdd*750+
    (#p.streetProposal.edgesToAdd==0 and #p.streetProposal.edgesToRemove*100 or 0)
end
api.engine.util.proposal={makeProposalData=function(p,context)
  rail_preflight_calls=(rail_preflight_calls or 0)+1
  return native_record({costs=quoted(p),errorState=native_record({critical=rail_fixture_preflight_critical==true,messages=rail_fixture_preflight_messages or {}})})
end}
local function node(position)local n=fresh();world[n]={BASE_NODE={position=copy(position)}};return n end
local function track(n0,n1,t0,t1)
  local n=fresh();world[n]={BASE_EDGE={node0=n0,node1=n1,tangent0=t0,tangent1=t1,type=0,typeIndex=-1,objects={}},BASE_EDGE_TRACK={trackType=20,catenary=false}}
  return n
end
local function placement(t,p)
  local a,b,c,d=t:col(0),t:col(1),t:col(2),t:col(3)
  return {x=d.x+a.x*p[1]+b.x*p[2]+c.x*p[3],y=d.y+a.y*p[1]+b.y*p[2]+c.y*p[3],z=d.z+a.z*p[1]+b.z*p[2]+c.z*p[3]}
end
local function marker(edge,object)
  local n=fresh();local value=world[edge].BASE_EDGE;local p0,p1=world[value.node0].BASE_NODE.position,world[value.node1].BASE_NODE.position
  local position={x=(p0.x+p1.x)/2,y=(p0.y+p1.y)/2,z=(p0.z+p1.z)/2}
  local m=api.type.Mat4f.new(api.type.Vec4f.new(1,0,0,0),api.type.Vec4f.new(0,1,0,0),api.type.Vec4f.new(0,0,1,0),api.type.Vec4f.new(position.x,position.y,position.z,1))
  world[n]={NAME={name=object.name},SIGNAL_LIST={signals={{edgePr={{entity=edge,index=0},not object.left},type=object.model==24 and 2 or 0,state=0,stateTime=0}}},
    MODEL_INSTANCE_LIST={fatInstances={{modelId=object.model,transf=m}},thinInstances={}}}
  value.objects={{n,0}};return n
end
local original_apply=apply_command
local rail_vehicle_counter=0
function apply_command(command,no_result)
  local op=command.op;local p=command.proposal
  local rail_build=op=='build'and((#p.constructionsToAdd>0 and(p.constructionsToAdd[1].fileName==A.station or p.constructionsToAdd[1].fileName==A.depot))
    or #p.constructionsToRemove>0 or #p.streetProposal.nodesToAdd>0 or #p.streetProposal.edgesToRemove>0
    or(#p.streetProposal.edgesToAdd>0 and p.streetProposal.edgesToAdd[1].type==1))
  if rail_build then
    sent=sent+1;local result={resultEntities={}};local street=p.streetProposal
    for _,con in ipairs(p.constructionsToAdd)do
      local n=fresh();local value={fileName=con.fileName,params=native_params(copy(con.params)),transf=observed_matrix(con.transf),frozenEdges={},frozenNodes={},stations={},depots={}}
      world[n]={CONSTRUCTION=observed_construction(value),NAME={name=con.name}}
      if con.fileName==A.station then
        assert(con.params.modules[8401000].name==A.station_modules[8401000],'station module configuration absent')
        local a=node(placement(con.transf,{5,-20,0}));local b=node(placement(con.transf,{5,60,0}))
        local tangent={x=0,y=80,z=0};value.frozenEdges={track(a,b,copy(tangent),copy(tangent))}
        local station,group=fresh(),fresh();world[station]={STATION={cargo=false,terminals={{vehicleNodeId={entity=a,index=0}}}},group=group}
        world[group]={STATION_GROUP={stations={station}},NAME={name=(rail_fixture_station_name_prefix or 'Station')..' automatic'}}
        value.stations={station}
      else
        local a=node(placement(con.transf,{0,-19.1,-.53}));local b=node(placement(con.transf,{0,-39.1,-.53}))
        local p0,p1=world[a].BASE_NODE.position,world[b].BASE_NODE.position
        local t={x=p1.x-p0.x,y=p1.y-p0.y,z=p1.z-p0.z};value.frozenEdges={track(a,b,copy(t),copy(t))};value.frozenNodes={a}
        local child=fresh();world[child]={VEHICLE_DEPOT={carrier=1,state=0,doors=0,stateTime=0}};value.depots={child}
      end
      result.resultEntities[#result.resultEntities+1]=n
    end
    for _,n in ipairs(p.constructionsToRemove)do
      local c=world[n].CONSTRUCTION
      local nodes={};for _,e in ipairs(c.frozenEdges)do local edge=world[e].BASE_EDGE;nodes[edge.node0]=true;nodes[edge.node1]=true;world[e]=nil end
      for node in pairs(nodes)do world[node]=nil end
      for _,s in ipairs(c.stations)do world[world[s].group]=nil;world[s]=nil end
      for _,d in ipairs(c.depots)do world[d]=nil end;world[n]=nil
    end
    for _,n in ipairs(street.edgeObjectsToRemove)do world[n]=nil end
    for _,n in ipairs(street.edgesToRemove)do world[n]=nil end
    for _,n in ipairs(street.nodesToRemove)do world[n]=nil end
    local map={};for _,value in ipairs(street.nodesToAdd)do assert(value.entity<0);map[value.entity]=node(value.comp.position)end
    for _,value in ipairs(street.edgesToAdd)do
      assert(value.type==1 and value.entity<0,'rail segment primitive kind')
      local n0=map[value.comp.node0]or value.comp.node0;local n1=map[value.comp.node1]or value.comp.node1
      assert(world[n0]and world[n1],'rail segment endpoint absent')
      local n=track(n0,n1,copy(value.comp.tangent0),copy(value.comp.tangent1));map[value.entity]=n
      assert(#value.comp.objects<=1,'only one safe marker per edge')
    end
    for _,object in ipairs(street.edgeObjectsToAdd)do
      assert(object.edgeEntity<0 and map[object.edgeEntity],'edge object must reference new negative edge')
      marker(map[object.edgeEntity],object)
    end
    money=money-quoted(p);return no_result and {}or native_record(result)
  elseif op=='buy'and world[command.depot].VEHICLE_DEPOT.carrier==1 then
    sent=sent+1;local n=fresh();rail_vehicle_counter=rail_vehicle_counter+1
    world[n]={TRANSPORT_VEHICLE={state=0,line=-1,depot=command.depot,userStopped=false,noPath=false,carrier=1,transportVehicleConfig=command.config},
      NAME={name=(guided_fixture_vehicle_name_prefix or 'Train')..' '..rail_vehicle_counter}}
    money=money-50000;rail_last_train=n;return no_result and{}or native_record({resultVehicleEntity=n})
  elseif op=='rail_replace'then
    sent=sent+1;local old=world[command.entity];local n=command.entity
    if rail_fixture_replace_new_identity then n=fresh();world[n]=old;world[command.entity]=nil end
    old.TRANSPORT_VEHICLE.transportVehicleConfig=command.config;money=money-10000
    return no_result and{}or native_record(rail_fixture_replace_new_identity and {resultVehicleEntity=n}or{})
  elseif op=='guided_maintenance'and world[command.entity].TRANSPORT_VEHICLE.carrier==1 then
    sent=sent+1;for _,v in ipairs(world[command.entity].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles)do v.targetMaintenanceState=command.value end
    return no_result and{}or native_record({})
  end
  return original_apply(command,no_result)
end
