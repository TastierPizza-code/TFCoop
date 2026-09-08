-- Separate bounded railway experiment. Native identities stay local; shared
-- observations use the generations established by successful callbacks.
local A=require 'tf2_strict_probe/rail_assets'
local M={}
function M.new(json,E,H)
  local R={completed=0,train='',clone='',line='',station_a='',station_b='',depot='',
    connectors='',signal_a='',signal_b='',waypoint=''}
  local site,network,construction_records,names,motions=nil,nil,{},{},{}
  local need,field,read,num,int,dec,arr=H.need,H.field,H.read,H.num,H.int,H.dec,H.arr
  local function fail(s)error('rail suite: '..s,0)end
  local function expect(v,s)if not v then fail(s)end end
  local function plain(v)return json.decode(json.encode(v))end
  local function same(a,b)return json.encode(a)==json.encode(b)end
  local function cp(id,kind)return H.component(id,kind)end
  local function id(key)return H.localid(key)end
  local function point(v)return H.vector(v,3,'rail.vector')end
  local function vec(v)return api.type.Vec3f.new(num(v[1]),num(v[2]),num(v[3]))end
  local function exists(n)return api.engine.entityExists(n)==true end
  local function position(n)return point(read(cp(n,'BASE_NODE'),'position','rail.BASE_NODE'))end
  local function lookup(snapshot,key)
    for _,v in ipairs(snapshot.objects)do if v.logical_id==key then return v.state end end
    fail('tracked object missing: '..key)
  end
  local function world()
    local s=E.snapshot()
    if #s.coverage.missing>0 then
      local reasons=table.concat(s.coverage.missing,'; '):sub(1,768)
      fail('observation unavailable: '..reasons:gsub('0[xX]%x+','[address]'):gsub('[%z\1-\31\127-\255]','?'))
    end
    return s
  end
  local function actual_name(key)
    local value=read(cp(id(key),'NAME'),'name','rail.NAME')
    expect(type(value)=='string','NAME.name unavailable');return value
  end
  local function register_name(key)
    expect(names[key]==nil,'vehicle name already witnessed')
    names[key]={entity=id(key),actual=actual_name(key),mode='automatic'}
  end
  local function name_state(key)
    local witness=names[key]
    expect(witness and witness.entity==id(key),'vehicle name witness absent or stale')
    expect(actual_name(key)==witness.actual,'vehicle name changed outside its approved rename')
    if witness.mode=='automatic'then return {mode='automatic'}end
    expect(witness.mode=='explicit','invalid name witness mode')
    return {mode='explicit',value=witness.actual}
  end
  local function callable(value)
    if type(value)=='function'then return true end
    if type(value)~='table'and type(value)~='userdata'then return false end
    local ok,mt=pcall(getmetatable,value)
    return ok and type(mt)=='table'and type(rawget(mt,'__call'))=='function'
  end
  local function require_resource(rep,name)
    local n=int(rep.find(name),0);expect(rep.getName(n)==name,'resource identity differs');return n
  end
  local function from_canonical(rows,numeric)
    local out={}
    for _,row in ipairs(rows)do
      local key=numeric and row.key_type=='number'and num(row.key)or row.key
      local value=row.value
      if row.value_type=='table'then value=from_canonical(value,numeric)
      elseif row.value_type=='number'and numeric then value=num(value)end
      out[key]=value
    end
    return out
  end
  local function module_metadata(name)
    local module=api.res.moduleRep.get(require_resource(api.res.moduleRep,name))
    return from_canonical(H.canonical(read(module,'metadata','rail.ModuleDesc')),true)
  end
  local function choose_site()
    local origin=H.site();local water=H.terrain_water()
    -- A separate bounded footprint, disjoint from the accepted road prelude.
    -- Every candidate is checked for real terrain and existing world objects.
    for ring=1,5 do for ix=-ring,ring do for iy=-ring,ring do
      if math.max(math.abs(ix),math.abs(iy))==ring then
        local x,y=origin.x+ix*640,origin.y+iy*640
        local low,high,valid=math.huge,-math.huge,true
        for sx=-100,180,40 do for sy=-240,240,40 do
          local p=api.type.Vec2f.new(x+sx,y+sy)
          if not H.boolean(api.engine.terrain.isValidCoordinate(p))then valid=false
          else local z=num(api.engine.terrain.getHeightAt(p));low=math.min(low,z);high=math.max(high,z)
            if z<=water+2 then valid=false end end
        end end
        if valid and high-low<=8 then
          local count=0
          api.engine.system.octreeSystem.findIntersectingEntities(api.type.Box3.new(
            api.type.Vec3f.new(x-100,y-240,low-100),api.type.Vec3f.new(x+180,y+240,high+100)),function(n)
            count=count+1;if count>10000 then valid=false end
            for _,kind in ipairs({'CONSTRUCTION','BASE_EDGE','TOWN_BUILDING','SIM_BUILDING'})do
              if api.engine.getComponent(n,api.type.ComponentType[kind])then valid=false end
            end
          end)
          if valid then return {x=x,y=y,z=(low+high)/2}end
        end
      end
    end end end
    fail('no clear dry bounded rail site found')
  end
  function R.initialize()
    local missing=json.array()
    for _,name in ipairs({'buildProposal','buyVehicle','replaceVehicle','createLine','updateLine','deleteLine',
      'setName','setVehicleTargetMaintenanceState','setLine','setUserStopped','reverseVehicle','sendToDepot',
      'sellVehicle','setGameSpeed'})do
      if not callable(field(api.cmd.make,name))then missing[#missing+1]='api.cmd.make.'..name end
    end
    for _,kind in ipairs({'BASE_EDGE_TRACK','BASE_NODE','SIGNAL_LIST','MODEL_INSTANCE_LIST'})do
      if field(api.type.ComponentType,kind)==nil then missing[#missing+1]='ComponentType.'..kind end
    end
    for _,name in ipairs({'getNode2TrackEdgeMap','getEdgeForEdgeObject'})do
      if not callable(field(api.engine.system.streetSystem,name))then missing[#missing+1]='streetSystem.'..name end
    end
    table.sort(missing);R.capabilities={ready=#missing==0,missing=missing}
    expect(R.capabilities.ready,'capability preflight missing: '..table.concat(missing,'; '))
    require_resource(api.res.modelRep,A.locomotive);require_resource(api.res.modelRep,A.coach)
    require_resource(api.res.modelRep,A.signal);require_resource(api.res.modelRep,A.waypoint)
    require_resource(api.res.trackTypeRep,A.track)
    for _,name in pairs(A.station_modules)do module_metadata(name)end
    site=choose_site()
  end
  local function track(n)
    local edge=cp(n,'BASE_EDGE');local rail=cp(n,'BASE_EDGE_TRACK')
    local n0=H.existing(read(edge,'node0','rail.BASE_EDGE'));local n1=H.existing(read(edge,'node1','rail.BASE_EDGE'))
    expect(n0~=n1,'self-linked track')
    return {node0=n0,node1=n1,position0=position(n0),position1=position(n1),
      tangent0=point(read(edge,'tangent0','rail.BASE_EDGE')),tangent1=point(read(edge,'tangent1','rail.BASE_EDGE')),
      track=H.resource(api.res.trackTypeRep,read(rail,'trackType','rail.BASE_EDGE_TRACK')),
      catenary=H.boolean(read(rail,'catenary','rail.BASE_EDGE_TRACK'))}
  end
  local function incidence(n)
    local map=need(api.engine.system.streetSystem.getNode2TrackEdgeMap(),'rail incidence unavailable')
    return H.entity_collection(read(map,n,'rail.incidence'),32,'rail.incidence.node','track incidence')
  end
  local function edge_objects(n)
    local out={}
    for _,pair in ipairs(arr(read(cp(n,'BASE_EDGE'),'objects','rail.BASE_EDGE'),1,'rail.edge.objects'))do
      local p=arr(pair,2,'rail.edge.object');expect(#p==2,'edge object tuple shape')
      out[#out+1]={id=H.existing(p[1]),kind=int(p[2])}
    end
    return out
  end
  local function owned_graph(key)
    local con=cp(id(key),'CONSTRUCTION');local edges=json.array();local degree,points={},{}
    local frozen={};for _,n in ipairs(arr(read(con,'frozenNodes','rail.CONSTRUCTION'),128))do frozen[int(n,1)]=true end
    for _,n in ipairs(arr(read(con,'frozenEdges','rail.CONSTRUCTION'),128))do
      -- Passenger modules also create street paths. Observe the owned rail
      -- graph only; the construction and module recipe is compared separately.
      if api.engine.getComponent(n,api.type.ComponentType.BASE_EDGE_TRACK)then
        local t=track(n);expect(t.track==A.track and not t.catenary,'owned track recipe differs')
        edges[#edges+1]={entity=n,value=t}
        for side=0,1 do local node=t['node'..side];degree[node]=(degree[node]or 0)+1;points[node]=t['position'..side]end
      end
    end
    expect(#edges>0 and #edges<=32,'construction rail edge count outside bound')
    local exposed={};for n,d in pairs(degree)do if d==1 and not frozen[n]then exposed[#exposed+1]={node=n,position=points[n]}end end
    return edges,exposed
  end
  local function port(key,slot)
    local _,ports=owned_graph(key)
    expect(#ports==(slot=='depot'and 1 or 2),'unexpected construction rail ports')
    table.sort(ports,function(a,b)return num(a.position[2])<num(b.position[2])end)
    if #ports==2 then expect(num(ports[1].position[2])<num(ports[2].position[2]),'ambiguous station axis')end
    local p=slot=='a'and ports[#ports]or ports[1]
    return {node=p.node,position=p.position,owner=key,alias=key..':port:'..slot}
  end
  local function construction_state(key)
    local con=cp(id(key),'CONSTRUCTION');local record=need(construction_records[key],'construction receipt absent')
    expect(read(con,'fileName','rail.CONSTRUCTION')==record.file,'construction file changed')
    expect(same(H.matrix(read(con,'transf','rail.CONSTRUCTION')),record.transform),'construction pose changed')
    expect(actual_name(key)==record.name,'construction explicit name changed')
    expect(same(H.canonical(read(con,'params','rail.CONSTRUCTION')),record.actual_params),'construction parameters changed')
    local edges=owned_graph(key);local result=json.array();local nodes={}
    -- Names derive from sorted actual coordinates; enforce uniqueness rather
    -- than assigning IDs from hash/container iteration order.
    local points={}
    for _,item in ipairs(edges)do for side=0,1 do local t=item.value;local n=t['node'..side]
      if not points[n]then points[n]=t['position'..side]end
    end end
    local ordered={};for n,p in pairs(points)do ordered[#ordered+1]={entity=n,p=p}end
    table.sort(ordered,function(a,b)return json.encode(a.p)<json.encode(b.p)end)
    for i,p in ipairs(ordered)do
      if i>1 then expect(not same(p.p,ordered[i-1].p),'ambiguous owned rail node position')end
      nodes[p.entity]=key..':node:'..i
    end
    for _,item in ipairs(edges)do local t=plain(item.value);t.node0=nodes[item.value.node0];t.node1=nodes[item.value.node1];result[#result+1]=t end
    table.sort(result,function(a,b)return json.encode(a)<json.encode(b)end)
    return {file=record.file,params=plain(record.shared_params),
      transform=H.matrix(read(con,'transf','rail.CONSTRUCTION')),name=record.name,tracks=result}
  end
  local function network_state()
    expect(network and network.entity==id(R.connectors),'network generation absent or stale')
    local result={position=position(network.entity),arms=json.array(),connected=true}
    local expected_incidence={}
    for i,arm in ipairs(network.arms)do
      local value=track(H.existing(arm.entity))
      expect(same(value,arm.shape),'connector geometry or endpoints changed')
      local objects=json.array()
      for _,o in ipairs(edge_objects(arm.entity))do
        expect(o.kind==int(api.type.enum.EdgeObjectType.SIGNAL),'unexpected connector object kind')
        local logical=need(E.reverse[o.id],'unbound rail marker')
        expect(logical==arm.marker,'connector marker binding changed')
        objects[#objects+1]={logical_id=logical,kind=arm.marker_kind}
      end
      expect(#objects==(arm.marker~=''and 1 or 0),'connector marker membership changed')
      local t=plain(value);t.slot=arm.slot;t.edge=arm.generation;t.node0=arm.port.alias;t.node1=R.connectors;t.objects=objects
      result.arms[i]=t;expected_incidence[arm.entity]=true
      local matches=0;for _,n in ipairs(incidence(arm.port.node))do if n==arm.entity then matches=matches+1 end end
      expect(matches==1,'connector not attached to its actual construction port')
    end
    local actual=incidence(network.entity);expect(#actual==3,'turnout incidence differs')
    for _,n in ipairs(actual)do expect(expected_incidence[n],'untracked edge attached to turnout')end
    return result
  end
  local function marker_state(key)
    local b=E.bindings[key];local arm=need(network and network.arms[b.arm],'marker arm unavailable')
    expect(arm.marker==key,'marker generation changed')
    expect(int(api.engine.system.streetSystem.getEdgeForEdgeObject(id(key)),1)==arm.entity,'marker actual edge changed')
    local signals=arr(read(cp(id(key),'SIGNAL_LIST'),'signals','rail.SIGNAL_LIST'),1)
    expect(#signals==1,'marker does not have one observed signal')
    local signal=signals[1];local pair=arr(read(signal,'edgePr','rail.Signal'),2);expect(#pair==2,'signal edge pair shape')
    local edgeid=read(pair,1,'rail.edgePr')
    expect(int(read(edgeid,'entity','rail.EdgeId'),1)==arm.entity,'signal edge identity differs')
    local signal_type=int(read(signal,'type','rail.Signal'))
    expect(signal_type==(b.marker_kind=='waypoint'and 2 or 0),'actual marker type differs')
    local fat=arr(read(cp(id(key),'MODEL_INSTANCE_LIST'),'fatInstances','rail.MODEL_INSTANCE_LIST'),1)
    expect(#fat==1,'marker model instance count differs')
    local model=H.resource(api.res.modelRep,read(fat[1],'modelId','rail.ModelInstance'))
    expect(model==(b.marker_kind=='waypoint'and A.waypoint or A.signal),'marker model differs')
    local transf=H.matrix(read(fat[1],'transf','rail.ModelInstance'))
    expect(actual_name(key)==b.name,'marker explicit name changed')
    return {edge=arm.generation,model=model,signal_type=signal_type,
      position=json.array({transf[13],transf[14],transf[15]}),direction=H.boolean(pair[2]),name=b.name}
  end
  local function config_state(cfg)
    local result={vehicles=json.array(),groups=json.array()}
    for i,v in ipairs(arr(read(cfg,'vehicles','rail.Config'),3))do
      local part=read(v,'part','rail.VehiclePart');local load,auto=json.array(),json.array()
      for j,n in ipairs(arr(read(part,'loadConfig','rail.Part'),1))do load[j]=int(n,-1)end
      for j,n in ipairs(arr(read(v,'autoLoadConfig','rail.VehiclePart'),1))do auto[j]=dec(n)end
      expect(#load==1 and #auto==1,'rail load configuration shape differs')
      result.vehicles[i]={model=H.resource(api.res.modelRep,read(part,'modelId','rail.Part')),
        load_config=load,auto_load_config=auto,purchase_time=dec(read(v,'purchaseTime','rail.VehiclePart')),
        maintenance=dec(read(v,'maintenanceState','rail.VehiclePart')),target_maintenance=dec(read(v,'targetMaintenanceState','rail.VehiclePart')),
        reversed=H.boolean(read(part,'reversed','rail.Part')),color=point(read(part,'color','rail.Part')),logo=read(part,'logo','rail.Part')}
      expect(type(result.vehicles[i].logo)=='string','rail logo is not text')
    end
    local count=0;for i,n in ipairs(arr(read(cfg,'vehicleGroups','rail.Config'),3))do result.groups[i]=int(n,1,3);count=count+result.groups[i]end
    expect(#result.vehicles>=2 and count==#result.vehicles,'rail config part/group count differs')
    return result
  end
  local function train_state(key)
    local n=id(key);local v=cp(n,'TRANSPORT_VEHICLE');local state=int(read(v,'state','rail.Vehicle'))
    local parked=state==int(api.type.enum.TransportVehicleState.IN_DEPOT)
    local line=H.reference(read(v,'line','rail.Vehicle'));local stop=field(v,'stopIndex')
    local out={config=config_state(read(v,'transportVehicleConfig','rail.Vehicle')),name=name_state(key),
      carrier=int(read(v,'carrier','rail.Vehicle')),depot=H.reference(read(v,'depot','rail.Vehicle')),
      line=line,state=state,user_stopped=H.boolean(read(v,'userStopped','rail.Vehicle')),
      no_path=H.boolean(read(v,'noPath','rail.Vehicle')),stop_index=stop==nil and {available=false}or {available=true,value=int(stop)}}
    expect(out.carrier==1,'tracked train carrier changed')
    if line~=''then expect(out.stop_index.available,'assigned train stop index unavailable')end
    if parked then out.position='in_depot'
    else
      local data=game.interface.getEntity(n);local p=data and field(data,'position')
      out.world_position_present=p~=nil;if p then out.position=point(p)end
      local move=api.engine.getComponent(n,api.type.ComponentType.MOVE_PATH);out.move_path_present=move~=nil
      if move then
        local dyn=read(move,'dyn','rail.MOVE_PATH');local pos=read(dyn,'pathPos','rail.Dyn')
        out.movement={speed=dec(read(dyn,'speed','rail.Dyn')),edge_index=int(read(pos,'edgeIndex','rail.PathPos')),
          position=dec(read(pos,'pos','rail.PathPos')),position01=dec(read(pos,'pos01','rail.PathPos'))}
      end
    end
    return out
  end
  local function line_state(key)
    local line=cp(id(key),'LINE');local stops,vehicles=json.array(),json.array()
    for i,s in ipairs(arr(read(line,'stops','rail.LINE'),2))do
      local group=int(read(s,'stationGroup','rail.Stop'),1)
      local owner=group==id(R.station_a..':group')and R.station_a or group==id(R.station_b..':group')and R.station_b or nil
      expect(owner~=nil,'unbound rail line station group')
      stops[i]={stop=owner,station=int(read(s,'station','rail.Stop')),terminal=int(read(s,'terminal','rail.Stop')),
        load_mode=int(read(s,'loadMode','rail.Stop')),min_wait=dec(read(s,'minWaitingTime','rail.Stop')),max_wait=dec(read(s,'maxWaitingTime','rail.Stop'))}
    end
    for _,n in ipairs(H.entity_collection(api.engine.system.transportVehicleSystem.getLineVehicles(id(key)),2,'rail.line.vehicles','line vehicles'))do
      vehicles[#vehicles+1]=H.reference(n)
    end
    table.sort(vehicles)
    return {stops=stops,vehicles=vehicles,name=actual_name(key),color=point(read(cp(id(key),'COLOR'),'color','rail.COLOR'))}
  end
  function R.owns(kind)return type(kind)=='string'and kind:sub(1,5)=='rail_'end
  function R.state(key,b)
    H.existing(b.entity)
    if b.kind=='rail_station'or b.kind=='rail_depot'then return construction_state(key)
    elseif b.kind=='rail_network'then return network_state()
    elseif b.kind=='rail_marker'then return marker_state(key)
    elseif b.kind=='rail_train'then return train_state(key)
    elseif b.kind=='rail_line'then return line_state(key)
    elseif b.kind=='rail_station_child'then
      local s=cp(b.entity,'STATION');return {cargo=H.boolean(read(s,'cargo','rail.STATION')),terminals=#arr(read(s,'terminals','rail.STATION'),8)}
    elseif b.kind=='rail_station_group'then
      local list=json.array();for _,n in ipairs(arr(read(cp(b.entity,'STATION_GROUP'),'stations','rail.STATION_GROUP'),1))do list[#list+1]=H.reference(n)end
      return {stations=list}
    elseif b.kind=='rail_depot_child'then
      local d=cp(b.entity,'VEHICLE_DEPOT');return {carrier=int(read(d,'carrier','rail.DEPOT')),state=int(read(d,'state','rail.DEPOT')),
        doors=int(read(d,'doors','rail.DEPOT')),state_time=dec(read(d,'stateTime','rail.DEPOT'))}
    end
    fail('unknown rail binding kind')
  end
  function R.observe(snapshot)
    for _,key in ipairs({R.train,R.clone})do if key~=''and #snapshot.coverage.missing==0 then
      local v=lookup(snapshot,key)
      if v.world_position_present then
        local point_mm=json.array();for i=1,3 do point_mm[i]=int(math.floor(num(v.position[i])*1000+.5))end
        if not motions[key]then motions[key]={time=snapshot.sim_time_us,point=point_mm}end
        local first=motions[key];expect(snapshot.sim_time_us>=first.time,'motion time moved backwards')
        v.guided_motion={first_time_us=first.time,first_position_mm=plain(first.point),observed_time_us=snapshot.sim_time_us,
          observed_position_mm=point_mm,displacement_observed=snapshot.sim_time_us>first.time and not same(first.point,point_mm)}
      end
    end end
    local registry={contract=A.contract,vehicle_name_contract=A.name_contract,capabilities=plain(R.capabilities)}
    for _,k in ipairs({'train','clone','line','station_a','station_b','depot','connectors','signal_a','signal_b','waypoint'})do registry[k]=R[k]end
    snapshot.probe.rail_suite=registry
  end
  local function validate(c,key)
    expect(type(c)=='table'and c.op=='RAIL_ACTION','invalid rail request')
    for k in pairs(c)do expect(k=='op'or k=='step','unexpected rail request field')end
    local step=int(c.step,1,#A.actions);expect(step==R.completed+1,'rail action is not next shared step')
    local actor,sequence;if type(key)=='string'then actor,sequence=key:match('^([ab]):([1-9]%d*)$')end
    expect(actor==(step%2==1 and 'a'or 'b')and sequence~=nil and #key<=96,'wrong rail actor or command identity')
    expect(E.bindings[key]==nil,'reused rail command identity');return step,A.actions[step]
  end
  local function construction_recipe(slot,key)
    local offset=A.offsets[slot];local t={1,0,0,0,0,1,0,0,0,0,1,0,site.x+offset[1],site.y+offset[2],site.z,1}
    if slot=='depot'then t[1]=0;t[2]=-1;t[5]=1;t[6]=0 end
    local track_resource=api.res.trackTypeRep.get(require_resource(api.res.trackTypeRep,A.track))
    local params={year=1850,trackType=0,catenary=0,seed=1}
    if slot=='depot'then params.state={track={railBase=num(read(track_resource,'railBase','rail.TrackType')),
      railHeight=num(read(track_resource,'railHeight','rail.TrackType'))}}end
    local file=slot=='depot'and A.depot or A.station
    if slot~='depot'then
      params.seed=1;params.modules={}
      for module_slot,name in pairs(A.station_modules)do params.modules[module_slot]={name=name,variant=0,metadata=module_metadata(name)}end
    end
    return {file=file,params=params,transform=H.matrix(t),raw_transform=t,name='TFCoop T2 '..slot..' '..key}
  end
  local function base_proposal()return api.type.SimpleProposal.new()end
  local function append(container,key,value)local list=read(container,key,'rail.Proposal');list[#list+1]=value;container[key]=list end
  local function segment(n,n0,n1,t0,t1,marker)
    local edge=api.type.SegmentAndEntity.new();edge.entity=n;edge.type=1
    local comp=read(edge,'comp','rail.SegmentAndEntity');comp.node0=n0;comp.node1=n1;comp.tangent0=vec(t0);comp.tangent1=vec(t1)
    if marker then local objects=read(comp,'objects','rail.BaseEdge');objects[1]={-1,int(api.type.enum.EdgeObjectType.SIGNAL)};comp.objects=objects end
    edge.comp=comp;local rail=api.type.BaseEdgeTrack.new();rail.trackType=require_resource(api.res.trackTypeRep,A.track);rail.catenary=false;edge.trackEdge=rail
    return edge
  end
  local function build_proposal(action,key)
    local p=base_proposal();local meta={};local street=read(p,'streetProposal','rail.SimpleProposal')
    if action=='BUILD_STATION_A'or action=='BUILD_STATION_B'or action=='BUILD_RAIL_DEPOT'then
      local slot=action=='BUILD_STATION_A'and 'station_a'or action=='BUILD_STATION_B'and 'station_b'or 'depot'
      expect(R[slot]=='','rail construction already exists');meta.slot=slot;meta.recipe=construction_recipe(slot,key)
      local con=api.type.SimpleProposal.ConstructionEntity.new();con.fileName=meta.recipe.file;con.params=meta.recipe.params
      local t=meta.recipe.raw_transform
      con.transf=api.type.Mat4f.new(api.type.Vec4f.new(t[1],t[2],0,0),api.type.Vec4f.new(t[5],t[6],0,0),api.type.Vec4f.new(0,0,1,0),api.type.Vec4f.new(t[13],t[14],site.z,1))
      con.name=meta.recipe.name;con.playerEntity=api.engine.util.getPlayer();append(p,'constructionsToAdd',con)
    elseif action=='CONNECT_RAIL'then
      expect(R.connectors==''and R.station_a~=''and R.station_b~=''and R.depot~='','rail prerequisites absent')
      local ports={port(R.station_a,'a'),port(R.station_b,'b'),port(R.depot,'depot')}
      meta.ports=ports;meta.previous={};for i,v in ipairs(ports)do meta.previous[i]=incidence(v.node)end
      local junction={num(ports[1].position[1]),site.y,(num(ports[1].position[3])+num(ports[2].position[3]))/2}
      meta.junction=point(junction);local node=api.type.NodeAndEntity.new();node.entity=-4;local base=read(node,'comp','rail.NodeAndEntity');base.position=vec(junction);node.comp=base;append(street,'nodesToAdd',node)
      meta.shapes={}
      for i,v in ipairs(ports)do
        local dy=junction[2]-num(v.position[2]);local dx=junction[1]-num(v.position[1]);local dz=junction[3]-num(v.position[3])
        local length=math.sqrt(dx*dx+dy*dy+dz*dz);expect(length>=30 and length<=280,'connector length outside safe recipe')
        local t0,t1
        if i<3 then t0={0,dy,dz};t1={0,dy,dz}
        else t0={-length,0,0};t1={0,length,0}end
        append(street,'edgesToAdd',segment(-i,v.node,-4,t0,t1))
        meta.shapes[i]={node0=v.node,node1=-4,position0=v.position,position1=meta.junction,
          tangent0=point(t0),tangent1=point(t1),track=A.track,catenary=false}
      end
    elseif action:match('^ADD_')and(action:find('SIGNAL')or action=='ADD_WAYPOINT')or action:match('^REMOVE_')and(action:find('SIGNAL')or action=='REMOVE_WAYPOINT')then
      expect(R.connectors~=''and R.line=='','marker edge replacement requires no live rail line')
      local marker_slot=action:find('SIGNAL_A')and 'signal_a'or action:find('SIGNAL_B')and 'signal_b'or 'waypoint'
      local arm_index=marker_slot=='signal_a'and 1 or marker_slot=='signal_b'and 2 or 3
      local arm=network.arms[arm_index];local adding=action:sub(1,4)=='ADD_'
      expect((adding and R[marker_slot]=='')or(not adding and R[marker_slot]~=''),'marker lifecycle differs')
      network_state();local shape=track(arm.entity)
      meta.marker_slot=marker_slot;meta.arm=arm_index;meta.old_edge=arm.entity;meta.shape=shape;meta.previous=incidence(arm.port.node)
      meta.adding=adding;meta.marker_kind=marker_slot=='waypoint'and 'waypoint'or 'signal';meta.name='TFCoop T2 '..marker_slot..' '..key
      append(street,'edgesToRemove',arm.entity)
      append(street,'edgesToAdd',segment(-1,shape.node0,shape.node1,shape.tangent0,shape.tangent1,adding))
      if adding then
        local object=api.type.SimpleStreetProposal.EdgeObject.new();object.edgeEntity=-1;object.param=.5;object.oneWay=false;object.left=false
        object.model=require_resource(api.res.modelRep,meta.marker_kind=='waypoint'and A.waypoint or A.signal)
        object.playerEntity=api.engine.util.getPlayer();object.name=meta.name;append(street,'edgeObjectsToAdd',object)
      else meta.removed_key=R[marker_slot];meta.removed_id=id(meta.removed_key);append(street,'edgeObjectsToRemove',meta.removed_id)end
    elseif action=='REMOVE_CONNECTORS'then
      expect(R.line==''and R.train==''and R.clone==''and R.signal_a==''and R.signal_b==''and R.waypoint=='','rail network still in use')
      network_state();meta.removed_key=R.connectors;meta.removed_id=id(R.connectors);meta.edges={}
      for _,arm in ipairs(network.arms)do append(street,'edgesToRemove',arm.entity);meta.edges[#meta.edges+1]=arm.entity end
      append(street,'nodesToRemove',network.entity)
    elseif action:match('^REMOVE_')then
      expect(R.connectors==''and R.line==''and R.train==''and R.clone=='','rail construction still in use')
      local slot=action=='REMOVE_RAIL_DEPOT'and 'depot'or action=='REMOVE_STATION_A'and 'station_a'or 'station_b'
      meta.slot=slot;meta.removed_key=R[slot];meta.removed_id=id(meta.removed_key);meta.removed_bindings={}
      for k,b in pairs(E.bindings)do if k==meta.removed_key or k:sub(1,#meta.removed_key+1)==meta.removed_key..':'then meta.removed_bindings[k]=b.entity end end
      meta.edges={};for _,v in ipairs(owned_graph(meta.removed_key))do meta.edges[#meta.edges+1]=v.entity end
      append(p,'constructionsToRemove',meta.removed_id)
    else fail('unknown rail proposal action')end
    p.streetProposal=street
    local context=H.context();local processed=api.engine.util.proposal.makeProposalData(p,context)
    local err=read(processed,'errorState','rail.ProposalData')
    local critical=H.boolean(read(err,'critical','rail.ErrorState'))
    local messages=H.canonical(read(err,'messages','rail.ErrorState'))
    expect(not critical and #messages==0,'fresh rail proposal rejected by engine preflight')
    meta.cost=int(read(processed,'costs','rail.ProposalData'))
    return p,context,meta
  end
  local target_fields={RENAME_TRAIN='train',TRAIN_MAINTENANCE='train',ASSIGN_TRAIN='train',STOP_TRAIN='train',START_TRAIN='train',
    REVERSE_TRAIN='train',SEND_DEPOT='train',VERIFY_DEPOT='train',VERIFY_TRAIN_MOVEMENT='train',REPLACE_TRAIN='train',
    SELL_TRAIN='train',SELL_CLONE='clone',DELETE_LINE='line',ADD_STOP_A='line',ADD_STOP_B='line',
    REMOVE_WAYPOINT='waypoint',REMOVE_SIGNAL_A='signal_a',REMOVE_SIGNAL_B='signal_b',REMOVE_CONNECTORS='connectors',
    REMOVE_RAIL_DEPOT='depot',REMOVE_STATION_A='station_a',REMOVE_STATION_B='station_b'}
  local function proposal_action(action)
    return action:match('^BUILD_')or action=='CONNECT_RAIL'or action:match('^REMOVE_')or action:match('^ADD_SIGNAL')or action=='ADD_WAYPOINT'
  end
  local function preview(c,key)
    local step,action=validate(c,key);local before=world();local expected={target='',required_effect=action}
    if target_fields[action]then expected.target=R[target_fields[action]];expect(expected.target~='','rail action target absent')end
    local meta,p,context
    if proposal_action(action)then p,context,meta=build_proposal(action,key);expected.cost=meta.cost
      expect(before.company.balance-meta.cost>=0,'insufficient company money for rail proposal')
      if meta.recipe then expected.file=meta.recipe.file;expected.transform=plain(meta.recipe.transform);expected.name=meta.recipe.name
        expected.params=from_canonical(H.canonical(meta.recipe.params),false)
      elseif meta.marker_slot then
        expected.model=meta.marker_kind=='waypoint'and A.waypoint or A.signal
        expected.signal_type=meta.marker_kind=='waypoint'and 2 or 0;expected.name=meta.name
      end
    end
    if action=='PAUSE'or action=='RESUME'then expected.paused=action=='PAUSE'
    elseif action=='BUY_TRAIN'or action=='REPLACE_TRAIN'or action=='CLONE_TRAIN'then
      expect(R.depot~='','train depot absent');expected.depot=R.depot..':depot'
      expected.models=json.array({A.locomotive,A.coach});if action~='BUY_TRAIN'then expected.models[3]=A.coach end
      if action~='BUY_TRAIN'then expect(lookup(before,R.train).position=='in_depot','train change requires actual depot arrival')end
      if action=='BUY_TRAIN'then expect(R.train=='','train already bought')end
      if action=='CLONE_TRAIN'then expect(R.clone=='','clone already exists');expected.source=R.train end
    elseif action=='CREATE_LINE'then expect(R.line=='','rail line already exists');expected.name=A.line_name
    elseif action=='ADD_STOP_A'then expected.stops={R.station_a}
    elseif action=='ADD_STOP_B'then expected.stops={R.station_a,R.station_b}
    elseif action=='RENAME_TRAIN'then expected.name=A.train_name
    elseif action=='TRAIN_MAINTENANCE'then expected.target_maintenance='1'
    elseif action=='ASSIGN_TRAIN'then expect(#lookup(before,R.line).stops==2,'assignment requires two confirmed stops');expected.line=R.line;expected.stop_index=0
    elseif action=='STOP_TRAIN'or action=='START_TRAIN'then expected.user_stopped=action=='STOP_TRAIN'
    elseif action=='VERIFY_DEPOT'then expected.depot=R.depot..':depot'
    elseif action=='DELETE_LINE'then expect(#lookup(before,R.line).vehicles==0,'rail line still has vehicles')
    elseif action=='SELL_TRAIN'or action=='SELL_CLONE'then expect(lookup(before,expected.target).position=='in_depot','sale requires actual depot arrival')end
    local allowed=true
    if action=='VERIFY_TRAIN_MOVEMENT'then
      local v=lookup(before,R.train);allowed=v.world_position_present==true and v.no_path==false and v.user_stopped==false
        and v.guided_motion~=nil and v.guided_motion.displacement_observed==true
    elseif action=='VERIFY_DEPOT'then local v=lookup(before,R.train);allowed=v.position=='in_depot'and v.depot==expected.depot
    elseif action=='VERIFY_RAIL_GRAPH'then
      allowed=network_state().connected and R.signal_a~=''and R.signal_b~=''and R.waypoint~=''
      expected.target=R.connectors
    end
    return {contract=A.contract,step=step,action=action,allowed=allowed,reason=allowed and ''or 'not_ready',
      observation={company=plain(before.company),expected=expected,target=expected.target~=''and plain(lookup(before,expected.target))or {},
      capabilities=plain(R.capabilities)}},p,context,meta,before
  end
  function R.preview(c,key)local value=preview(c,key);return value end
  local function train_config(time_us,models,source)
    local cfg=api.type.TransportVehicleConfig.new();local vehicles=read(cfg,'vehicles','rail.Config')
    for i,model in ipairs(models)do
      local previous=source and source.vehicles[i];local part=api.type.VehiclePart.new()
      part.modelId=require_resource(api.res.modelRep,model);part.reversed=previous and previous.reversed or false
      part.color=previous and vec(previous.color)or api.type.Vec3f.new(-1,-1,-1);part.logo=previous and previous.logo or ''
      local load=read(part,'loadConfig','rail.Part');load[1]=previous and previous.load_config[1]or 0;part.loadConfig=load
      local v=api.type.TransportVehiclePart.new();v.part=part;v.purchaseTime=int(time_us/1000,1);v.maintenanceState=1;v.targetMaintenanceState=previous and num(previous.target_maintenance)or 0
      local auto=read(v,'autoLoadConfig','rail.Part');auto[1]=previous and num(previous.auto_load_config[1])or 1;v.autoLoadConfig=auto;vehicles[i]=v
    end
    cfg.vehicles=vehicles;local groups=read(cfg,'vehicleGroups','rail.Config')
    if source then for i,n in ipairs(source.groups)do groups[i]=n end else groups[1]=#models end
    cfg.vehicleGroups=groups;config_state(cfg);return cfg
  end
  local function line_recipe(keys)
    local line=api.type.Line.new();line.waitingTime=0;local list=read(line,'stops','rail.Line')
    for i,key in ipairs(keys)do
      local s=api.type.Line.Stop.new();s.stationGroup=id(key..':group');s.station=0;s.terminal=0
      s.loadMode=0;s.minWaitingTime=0;s.maxWaitingTime=0;list[i]=s
      local station=cp(id(key..':station'),'STATION');expect(#arr(read(station,'terminals','rail.STATION'),8)>=1,'passenger station terminal absent')
      expect(read(station,'cargo','rail.STATION')==false,'rail station is not passenger')
    end
    line.stops=list;return line
  end
  function R.plan(c,key,time_us)
    local pv,p,context,meta,before=preview(c,key);expect(pv.allowed,'rail action not ready')
    local action=pv.action;local plan={rail=true,key=key,command=plain(c),action=action,preview=pv,expected=pv.observation.expected,
      before=before,meta=meta,created=json.array(),removed=json.array()};local make=api.cmd.make
    if action=='VERIFY_RAIL_GRAPH'or action=='VERIFY_TRAIN_MOVEMENT'or action=='VERIFY_DEPOT'then plan.read_only=true;return plan end
    if p then plan.native=make.buildProposal(p,context,false)
    elseif action=='PAUSE'or action=='RESUME'then plan.requested_paused=action=='PAUSE';plan.native=make.setGameSpeed(plan.requested_paused and 0 or 1)
    elseif action=='BUY_TRAIN'or action=='CLONE_TRAIN'then
      local source=action=='CLONE_TRAIN'and lookup(before,R.train).config or nil
      plan.native=make.buyVehicle(api.engine.util.getPlayer(),id(R.depot..':depot'),train_config(time_us,plan.expected.models,source))
    elseif action=='REPLACE_TRAIN'then
      plan.previous_train=R.train;plan.previous_id=id(R.train)
      plan.previous_name=plain(names[R.train])
      plan.native=make.replaceVehicle(id(R.train),train_config(time_us,plan.expected.models))
    elseif action=='CREATE_LINE'then plan.native=make.createLine(A.line_name,api.type.Vec3f.new(.75,.25,.5),api.engine.util.getPlayer(),line_recipe({}))
    elseif action=='ADD_STOP_A'or action=='ADD_STOP_B'then plan.native=make.updateLine(id(R.line),line_recipe(plan.expected.stops))
    elseif action=='RENAME_TRAIN'then plan.native=make.setName(id(R.train),A.train_name)
    elseif action=='TRAIN_MAINTENANCE'then plan.native=make.setVehicleTargetMaintenanceState(id(R.train),1)
    elseif action=='ASSIGN_TRAIN'then plan.native=make.setLine(id(R.train),id(R.line),0)
    elseif action=='STOP_TRAIN'or action=='START_TRAIN'then plan.native=make.setUserStopped(id(R.train),action=='STOP_TRAIN')
    elseif action=='REVERSE_TRAIN'then plan.native=make.reverseVehicle(id(R.train))
    elseif action=='SEND_DEPOT'then plan.native=make.sendToDepot(id(R.train),false)
    elseif action=='SELL_TRAIN'or action=='SELL_CLONE'then plan.removed_key=plan.expected.target;plan.removed_id=id(plan.removed_key);plan.native=make.sellVehicle(plan.removed_id)
    elseif action=='DELETE_LINE'then plan.removed_key=R.line;plan.removed_id=id(R.line);plan.native=make.deleteLine(plan.removed_id)
    else fail('unimplemented rail action')end
    need(plan.native,'rail command maker returned no command');return plan
  end
  local function callback_entity(result,kind,optional)
    local found
    local function candidate(n)
      local value=tonumber(n);if not value or value<=0 then return end;value=int(value,1)
      if exists(value)and api.engine.getComponent(value,api.type.ComponentType[kind])then
        expect(found==nil or found==value,'ambiguous successful callback identity');found=value
      end
    end
    candidate(field(result,'resultEntity'));candidate(field(result,'resultVehicleEntity'))
    local values=field(result,'resultEntities');if values~=nil then for _,n in ipairs(arr(values,128))do candidate(n)end end
    if not optional then need(found,'successful rail callback lacks exact entity')end;return found
  end
  local function bind(plan,key,kind,n,owner)
    H.bind(key,kind,n,owner);plan.created[#plan.created+1]=key
  end
  local function remove(plan,key,n)
    expect(not exists(n),'removed rail entity still exists')
    expect(E.bindings[key]and E.bindings[key].entity==n,'removed rail binding changed')
    E.bindings[key]=nil;if E.reverse[n]==key then E.reverse[n]=nil end
    names[key]=nil;motions[key]=nil;plan.removed[#plan.removed+1]=key
  end
  local function only_new_edge(previous,node)
    local old={};for _,n in ipairs(previous)do old[n]=true end
    local found;for _,n in ipairs(incidence(node))do if not old[n]then expect(found==nil,'ambiguous new rail incidence');found=n end end
    return H.existing(need(found,'new rail edge not observed in actual incidence'))
  end
  local function finish_proposal(plan,result)
    local action,meta=plan.action,plan.meta
    if meta.recipe then
      local n=callback_entity(result,'CONSTRUCTION');local c=cp(n,'CONSTRUCTION');local recipe=meta.recipe
      expect(read(c,'fileName','rail.CONSTRUCTION')==recipe.file,'built rail construction file differs')
      expect(same(H.matrix(read(c,'transf','rail.CONSTRUCTION')),recipe.transform),'built rail pose differs')
      expect(read(cp(n,'NAME'),'name','rail.NAME')==recipe.name,'built rail name differs')
      local actual_params=read(c,'params','rail.CONSTRUCTION')
      for k,value in pairs(recipe.params)do
        expect(same(H.canonical(read(actual_params,k,'rail.params')),H.canonical(value)),'built rail parameter differs from approved recipe')
      end
      recipe.actual_params=H.canonical(actual_params)
      recipe.shared_params=from_canonical(recipe.actual_params,false)
      bind(plan,plan.key,meta.slot=='depot'and 'rail_depot'or 'rail_station',n)
      construction_records[plan.key]=recipe;R[meta.slot]=plan.key
      if meta.slot=='depot'then
        local children=arr(read(c,'depots','rail.CONSTRUCTION'),1);expect(#children==1,'rail depot child count differs')
        expect(int(read(cp(children[1],'VEHICLE_DEPOT'),'carrier','rail.DEPOT'))==1,'depot carrier is not rail')
        bind(plan,plan.key..':depot','rail_depot_child',children[1],children[1]==n and plan.key or nil)
      else
        local stations=arr(read(c,'stations','rail.CONSTRUCTION'),1);expect(#stations==1,'rail station child count differs')
        local station=stations[1];local group=H.existing(api.engine.system.stationGroupSystem.getStationGroup(station))
        local members=arr(read(cp(group,'STATION_GROUP'),'stations','rail.GROUP'),1)
        expect(#members==1 and members[1]==station,'rail station merged into unexpected station group')
        bind(plan,plan.key..':station','rail_station_child',station,station==n and plan.key or nil)
        bind(plan,plan.key..':group','rail_station_group',group,group==n and plan.key or group==station and E.reverse[station]or nil)
      end
      owned_graph(plan.key)
    elseif action=='CONNECT_RAIL'then
      local arms,center={},nil
      for i,p in ipairs(meta.ports)do
        local edge=only_new_edge(meta.previous[i],p.node);local value=track(edge)
        expect(value.node0==p.node,'new connector endpoint orientation differs')
        expect(center==nil or center==value.node1,'connectors do not meet one actual turnout');center=value.node1
        local shape=plain(meta.shapes[i]);shape.node1=center;expect(same(shape,value),'new connector geometry differs')
        arms[i]={entity=edge,shape=value,port=p,slot=i==1 and 'a'or i==2 and 'b'or 'depot',generation=plan.key..':arm:'..i,marker='',marker_kind=''}
      end
      bind(plan,plan.key,'rail_network',center);R.connectors=plan.key;network={entity=center,arms=arms};network_state()
    elseif meta.marker_slot then
      expect(not exists(meta.old_edge),'marker rebuild left old edge alive')
      local arm=network.arms[meta.arm];local edge=only_new_edge(meta.previous,arm.port.node)
      expect(same(track(edge),meta.shape),'marker rebuild changed connector geometry')
      arm.entity=edge;arm.generation=plan.key..':edge';arm.shape=meta.shape
      if meta.adding then
        local objects=edge_objects(edge);expect(#objects==1,'new marker edge object count differs')
        local n=objects[1].id;bind(plan,plan.key,'rail_marker',n)
        local b=E.bindings[plan.key];b.arm=meta.arm;b.marker_kind=meta.marker_kind;b.name=meta.name
        arm.marker=plan.key;arm.marker_kind=meta.marker_kind;R[meta.marker_slot]=plan.key;marker_state(plan.key)
      else remove(plan,meta.removed_key,meta.removed_id);arm.marker='';arm.marker_kind='';R[meta.marker_slot]=''end
      network_state()
    elseif action=='REMOVE_CONNECTORS'then
      for _,n in ipairs(meta.edges)do expect(not exists(n),'removed connector edge still exists')end
      remove(plan,meta.removed_key,meta.removed_id);R.connectors='';network=nil
    elseif meta.removed_bindings then
      for _,n in ipairs(meta.edges)do expect(not exists(n),'removed owned rail edge still exists')end
      local keys={};for k in pairs(meta.removed_bindings)do keys[#keys+1]=k end;table.sort(keys)
      for _,k in ipairs(keys)do remove(plan,k,meta.removed_bindings[k])end
      construction_records[meta.removed_key]=nil;R[meta.slot]=''
    end
  end
  local function effect(plan,kind)
    local before,after=plan.before,world();local action=plan.action
    expect(after.sim_time_us==before.sim_time_us,'rail command advanced simulation time')
    expect(after.company.loan==before.company.loan,'rail command changed loan')
    if plan.expected.cost~=nil then expect(before.company.balance-after.company.balance==plan.expected.cost,'rail actual debit differs from approved quote')
    elseif action=='BUY_TRAIN'or action=='CLONE_TRAIN'then expect(before.company.balance>after.company.balance and after.company.balance>=0,'train purchase has no valid actual debit')
    elseif action=='SELL_TRAIN'or action=='SELL_CLONE'then expect(after.company.balance>=before.company.balance,'train sale debited money')
    elseif action~='REPLACE_TRAIN'then expect(after.company.balance==before.company.balance,'no-cost rail action changed money')end
    local target=plan.expected.target
    if #plan.created>0 then target=plan.created[1]end
    local observed={}
    if action=='PAUSE'or action=='RESUME'then observed={paused=after.paused};expect(after.paused==plan.requested_paused,'rail pause not applied')
    elseif #plan.removed>0 and #plan.created==0 then observed={entity_absent=true}
    else observed=plain(lookup(after,target));local actual=observed
      if action=='BUY_TRAIN'or action=='CLONE_TRAIN'or action=='REPLACE_TRAIN'then
        expect(actual.position=='in_depot'and actual.depot==plan.expected.depot,'purchased/replaced train not in intended depot')
        expect(#actual.config.vehicles==#plan.expected.models,'train part count differs')
        for i,model in ipairs(plan.expected.models)do expect(actual.config.vehicles[i].model==model,'train model recipe differs')end
      elseif action=='RENAME_TRAIN'then expect(same(actual.name,{mode='explicit',value=A.train_name}),'train rename readback differs')
      elseif action=='TRAIN_MAINTENANCE'then for _,part in ipairs(actual.config.vehicles)do expect(part.target_maintenance=='1','train maintenance readback differs')end
      elseif action=='ASSIGN_TRAIN'then
        expect(actual.line==R.line and actual.stop_index.available and actual.stop_index.value==0,'train assignment differs')
        expect(same(lookup(after,R.line).vehicles,{R.train}),'line actual train membership differs')
      elseif action=='STOP_TRAIN'or action=='START_TRAIN'then expect(actual.user_stopped==plan.expected.user_stopped,'train stop readback differs')
      elseif action=='REVERSE_TRAIN'then
        local previous=lookup(before,target);expect(not same(actual.stop_index,previous.stop_index)or actual.state~=previous.state or not same(actual.movement,previous.movement),'train reverse has no observed route/state change')
        expect(actual.no_path==false,'reversed train has no path')
      elseif action=='SEND_DEPOT'then expect(actual.line==''or actual.state~=lookup(before,target).state,'depot request has no observed assignment/state change')
      elseif action=='VERIFY_DEPOT'then expect(actual.position=='in_depot'and actual.depot==plan.expected.depot,'train depot arrival not observed')
      elseif action=='VERIFY_TRAIN_MOVEMENT'then expect(actual.no_path==false and actual.guided_motion and actual.guided_motion.displacement_observed,'train displacement not observed')
      elseif action=='CREATE_LINE'then expect(actual.name==A.line_name and #actual.stops==0 and #actual.vehicles==0,'created rail line differs')
      elseif action=='ADD_STOP_A'or action=='ADD_STOP_B'then
        expect(#actual.stops==#plan.expected.stops,'rail stop count differs')
        for i,key in ipairs(plan.expected.stops)do local s=actual.stops[i]
          expect(s.stop==key and s.station==0 and s.terminal==0 and s.load_mode==0 and s.min_wait=='0'and s.max_wait=='0','rail stop occurrence differs')end
      elseif action=='VERIFY_RAIL_GRAPH'then expect(actual.connected==true,'rail graph disconnected')end
    end
    if action~='PAUSE'and action~='RESUME'then expect(before.paused==after.paused,'rail action changed pause')end
    if kind=='observation'then expect(same(before,after),'rail observation changed world')end
    table.sort(plan.created);table.sort(plan.removed)
    return {balance_before=before.company.balance,balance_after=after.company.balance,loan_before=before.company.loan,loan_after=after.company.loan,
      target=target,created=plan.created,removed=plan.removed,observed=observed,kind=kind}
  end
  local function completed(plan,kind)
    local result=effect(plan,kind);R.completed=plan.command.step
    return {success=true,result={op='RAIL_ACTION',step=plan.command.step,action=plan.action,command_key=plan.key,effect=result}}
  end
  function R.finish(plan,result,success)
    expect(plan.rail and not plan.read_only,'wrong rail callback completion path')
    local ok,report=pcall(H.capture_callback,plan,result,success);if ok then H.remember_callback(report)end
    if success~=true then return {success=false,result={error='engine_rejected',op='RAIL_ACTION',step=plan.command.step}}end
    local action=plan.action
    if plan.meta then finish_proposal(plan,result)
    elseif action=='BUY_TRAIN'or action=='CLONE_TRAIN'then
      local n=callback_entity(result,'TRANSPORT_VEHICLE');bind(plan,plan.key,'rail_train',n);register_name(plan.key)
      R[action=='BUY_TRAIN'and 'train'or 'clone']=plan.key
    elseif action=='REPLACE_TRAIN'then
      local n=callback_entity(result,'TRANSPORT_VEHICLE',true)
      if exists(plan.previous_id)then expect(n==nil or n==plan.previous_id,'replacement callback disagrees with surviving train');n=plan.previous_id
      else
        need(n,'replacement removed train without new callback identity');remove(plan,plan.previous_train,plan.previous_id)
        bind(plan,plan.key,'rail_train',n);register_name(plan.key);R.train=plan.key
        expect(actual_name(plan.key)==plan.previous_name.actual,'replacement changed confirmed vehicle name')
        names[plan.key].mode=plan.previous_name.mode
      end
    elseif action=='CREATE_LINE'then local n=callback_entity(result,'LINE');bind(plan,plan.key,'rail_line',n);R.line=plan.key
    elseif action=='RENAME_TRAIN'then
      expect(names[R.train]and names[R.train].entity==id(R.train),'rename name witness absent or stale')
      expect(actual_name(R.train)==A.train_name,'train name readback differs')
      names[R.train].actual=A.train_name;names[R.train].mode='explicit'
    elseif action=='SELL_TRAIN'or action=='SELL_CLONE'then remove(plan,plan.removed_key,plan.removed_id);R[action=='SELL_TRAIN'and 'train'or 'clone']=''
    elseif action=='DELETE_LINE'then remove(plan,plan.removed_key,plan.removed_id);R.line=''end
    return completed(plan,'callback')
  end
  function R.finish_read_only(plan)
    expect(plan.rail and plan.read_only and plan.native==nil,'wrong rail observation completion path')
    expect(plan.action=='VERIFY_RAIL_GRAPH'or plan.action=='VERIFY_TRAIN_MOVEMENT'or plan.action=='VERIFY_DEPOT','unsupported rail observation')
    return completed(plan,'observation')
  end
  return R
end
return M
