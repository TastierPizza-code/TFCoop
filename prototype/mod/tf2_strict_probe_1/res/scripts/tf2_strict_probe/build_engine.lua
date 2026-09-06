-- Fixed, bounded build experiment. Commands mutate only when the common
-- coordinator applies them; callback identities are never guessed by location.
local assets = require 'tf2_strict_probe/build_assets'
local M = {}
function M.new(json)
  local E = {bindings={},reverse={},scene={stops={}},groups={},stations={}}
  local diagnostic_candidate
  local function need(v,msg) if v==nil then error(msg,0) end return v end
  -- Native usertypes may throw for an absent member. Always return one value:
  -- falling through returns zero values, which breaks type(field(...)) and
  -- tonumber(field(...)) before the supported alternative can be inspected.
  local function field(v,k) local ok,x=pcall(function()return v[k]end);if ok then return x end;return nil end
  local function safe_error(v)
    if type(v)=='string'then
      local text=v:gsub('0[xX]%x+','[address]')
      if #text>1024 then return text:sub(1,256)..' ... '..text:sub(-768)end
      return text
    end
    return 'error value has Lua type='..type(v)
  end
  local function invalid(reason,path,v)
    error(reason..' at '..(path or 'build value')..' (Lua type='..type(v)..')',0)
  end
  local function read(v,k,path)
    local ok,x=pcall(function()return v[k]end)
    if not ok then error('getter threw at '..path..'.'..k..' (container Lua type='..type(v)..'): '..safe_error(x),0)end
    return x
  end
  local function num(v,path)
    local ok,n=pcall(tonumber,v)
    if not ok or not n or n~=n or math.abs(n)>9007199254740991 then invalid('invalid finite build value',path,v)end;return n
  end
  local function int(v,lo,hi,path) local n=num(v,path);if n%1~=0 or n<(lo or -9007199254740991) or n>(hi or 9007199254740991)then invalid('invalid build integer',path,v)end;return n end
  local function dec(v,path)return string.format('%.17g',num(v,path))end
  local function boolean(v,path)if type(v)~='boolean'then invalid('build boolean unavailable',path,v)end;return v end
  local function arr(v,max,path)
    path=path or 'build array'
    if v==nil then invalid('build array unavailable',path,v)end
    local ok,n=pcall(function()return #v end)
    if not ok then invalid('build array length unavailable',path,v)end
    n=int(n,0,max,path..'.#');local out=json.array()
    for i=1,n do out[i]=need(read(v,i,path),'build array hole at '..path..'['..i..'] (Lua type=nil)')end;return out
  end
  local function vector(v,n,path)
    path=path or 'build vector'
    local out=json.array();local names={'x','y','z','w'}
    for i=1,n do local x=field(v,names[i]);local p=path..'.'..names[i]
      if x==nil then x=field(v,i);p=p..'/['..i..']'end;out[i]=dec(x,p)end;return out
  end
  local function matrix(v,path)
    path=path or 'CONSTRUCTION.transf'
    local out=json.array()
    if type(field(v,'col'))=='function' then
      for i=0,3 do local col=vector(v:col(i),4,path..':col('..i..')');for j=1,4 do out[#out+1]=col[j]end end
    else for i=1,16 do out[i]=dec(field(v,i),path..'['..i..']')end end
    return out
  end
  local function clone(v,depth)
    depth=depth or 0;if depth>10 then error('build params depth',0)end
    if type(v)=='number'then return num(v)end
    if type(v)=='string'or type(v)=='boolean'then return v end
    if type(v)~='table'then error('nonplain build params',0)end
    local out,n={},0;for k,x in pairs(v)do n=n+1;if n>256 then error('build params width',0)end;out[k]=clone(x,depth+1)end;return out
  end
  local function canonical(value)
    -- Construction.params is exposed as native userdata in TF2, including
    -- nested containers. The game's serialize.lua reads these with pairs or
    -- the native __members list. Read every observed value by that contract;
    -- never substitute our requested recipe or stringify a native pointer.
    local active,budget={}, {nodes=0,bytes=0}
    local function fail(path,reason)error('observed params '..path..': '..reason,0)end
    local function text_size(s,path)
      budget.bytes=budget.bytes+#s;if budget.bytes>1048576 then fail(path,'text budget exceeded')end
      return s
    end
    local visit
    visit=function(v,depth,path)
      budget.nodes=budget.nodes+1;if budget.nodes>4096 then fail(path,'node budget exceeded')end
      if depth>10 then fail(path,'depth exceeded')end
      local kind=type(v)
      if kind=='number'then return dec(v,'CONSTRUCTION.params'..path)end
      if kind=='string'then return text_size(v,path)end
      if kind=='boolean'then return v end
      if kind~='table'and kind~='userdata'then fail(path,'unsupported value type '..kind)end
      if active[v]then fail(path,'cycle')end;active[v]=true
      local out,seen=json.array(),{}
      local function entry(k,x)
        if #out>=256 then fail(path,'width exceeded')end
        local kt=type(k)
        if kt~='string'and kt~='number'then fail(path,'unsupported key type '..kt)end
        local key=kt=='number'and dec(k,'CONSTRUCTION.params'..path..'.key')or text_size(k,path)
        local identity=kt..':'..key
        if seen[identity]then fail(path,'duplicate key '..identity)end;seen[identity]=true
        local child=path..'['..identity..']';local xt=type(x)
        out[#out+1]={key_type=kt,key=key,value_type=xt=='userdata'and 'table'or xt,
          value=visit(x,depth+1,child)}
      end
      local mt=kind=='userdata'and getmetatable(v)or nil
      local members=mt and field(mt,'__members')or nil
      if members~=nil and not field(mt,'pairs')and not field(mt,'__pairs')then
        -- Lua 5.3+ pairs(opaque_userdata) may return next successfully and fail
        -- only on its first call. Select a published member contract up front.
        local count_ok,count=pcall(function()return #members end)
        if not count_ok then fail(path,'member list length unavailable')end
        count=int(count,0,256,'CONSTRUCTION.params'..path..'.__members.#')
        for i=1,count do
          local key=field(members,i);if key==nil then fail(path,'member list hole')end
          local read,x=pcall(function()return v[key]end)
          if not read then fail(path,'member read failed: '..safe_error(key))end
          entry(key,x)
        end
      else
        local ok,iter,state,control=pcall(pairs,v)
        if not ok then fail(path,kind..' is not enumerable: '..safe_error(iter))end
        -- A failing iterator must fail the snapshot, even after partial output.
        local read,err=pcall(function()for k,x in iter,state,control do entry(k,x)end end)
        if not read then fail(path,kind..' iteration failed: '..safe_error(err))end
      end
      active[v]=nil
      table.sort(out,function(a,b)return a.key_type..':'..a.key<b.key_type..':'..b.key end)
      return out
    end
    return visit(value,0,'$')
  end
  local function component(id,kind)
    return need(api.engine.getComponent(id,need(api.type.ComponentType[kind],'component API '..kind)), 'build component absent: '..kind)
  end
  local function existing(id) id=int(id,1,2147483647);if not api.engine.entityExists(id)then error('build entity missing',0)end;return id end
  local function bind(key,kind,id,owner)
    id=existing(id);if E.bindings[key]or(E.reverse[id]and E.reverse[id]~=owner)then error('ambiguous build identity',0)end
    E.bindings[key]={entity=id,kind=kind};E.reverse[id]=E.reverse[id]or key
  end
  local function localid(key)return existing(need(E.bindings[key],'build dependency absent').entity)end
  local function reference(id,path)
    if id==nil then return ''end
    local value=int(id,nil,nil,path)
    if value==-1 or value==0 then return ''end
    return need(E.reverse[int(value,1,nil,path)],'unbound build reference at '..(path or 'entity reference'))
  end
  local function resource(rep,id,path)
    id=int(id,0,nil,path);local name=need(rep.getName(id),'resource name absent')
    if rep.find(name)~=id then error('resource name differs',0)end;return name
  end
  local function terrain_water()
    local found={}
    api.engine.forEachEntityWithComponent(function(id)
      if #found>=2 then error('ambiguous terrain',0)end;found[#found+1]=id
    end,api.type.ComponentType.TERRAIN)
    if #found~=1 then error('build_water_level_unavailable',0)end
    return num(component(found[1],'TERRAIN').waterLevel)
  end
  local function choose_site()
    local vehicle_model
    for _,name in ipairs(assets.vehicle_models or {assets.vehicle_model})do
      local id=api.res.modelRep.find(name)
      if type(id)=='number'and id>=0 and api.res.modelRep.getName(id)==name then
        local model=api.res.modelRep.get(id);local metadata=model and field(model,'metadata')
        if metadata and field(metadata,'transportVehicle')~=nil then vehicle_model=name;break end
      end
    end
    need(vehicle_model,'build_vehicle_model_unavailable')
    local water=terrain_water()
    local half=num(assets.half_extent)
    local preferred=num(assets.preferred_height_span)
    local maximum=num(assets.max_height_span)
    local report={version=2,examined=0,height_reads=0,water_level=dec(water),
      rejected={outside=0,water=0,too_uneven=0,occupied=0,not_better=0}}
    E.site_diagnostics=report
    local function valid(x,y)
      return boolean(api.engine.terrain.isValidCoordinate(api.type.Vec2f.new(x,y)))
    end
    if not valid(0,0)then error('build_site_map_bounds_unavailable: map origin is outside terrain',0)end
    -- Probe actual coordinate validity; Terrain.size is a tile count, not a
    -- world-space bounding box. All subsequent points are checked again.
    local function extent(axis,sign)
      local low,high=0,256
      local function inside(distance)
        return valid(axis==1 and sign*distance or 0,axis==2 and sign*distance or 0)
      end
      while high<32768 and inside(high)do low=high;high=high*2 end
      if inside(high)then report.extent_capped=true;low=high else
        while high-low>1 do
          local middle=math.floor((low+high)/2)
          if inside(middle)then low=middle else high=middle end
        end
      end
      if low<=half+1 then error('build_site_map_bounds_unavailable: terrain is too small',0)end
      return sign*(low-half-1)
    end
    local bounds={extent(1,-1),extent(1,1),extent(2,-1),extent(2,1)}
    report.center_bounds=json.array(bounds)
    local function samples(x,y,divisions)
      local low,high,heights=math.huge,-math.huge,json.array()
      for ix=0,divisions do for iy=0,divisions do
        local sx,sy=x-half+2*half*ix/divisions,y-half+2*half*iy/divisions
        if not valid(sx,sy)then return nil,'outside' end
        local h=num(api.engine.terrain.getHeightAt(api.type.Vec2f.new(sx,sy)))
        report.height_reads=report.height_reads+1
        if h<=water+2 then return nil,'water' end
        low=math.min(low,h);high=math.max(high,h);heights[#heights+1]=dec(h)
      end end
      return {low=low,high=high,span=high-low,heights=heights}
    end
    local best
    local function consider(ix,iy)
      report.examined=report.examined+1
      local x=math.floor(math.abs(ix)*(ix<0 and bounds[1]or bounds[2])/32+.5)
      local y=math.floor(math.abs(iy)*(iy<0 and bounds[3]or bounds[4])/32+.5)
      local measured,reason=samples(x,y,4)
      if measured then
        local span_mm=int(math.floor(measured.span*1000+.5))
        report.best_dry_span_mm=math.min(report.best_dry_span_mm or span_mm,span_mm)
        if measured.span>maximum then reason='too_uneven'
        elseif best and measured.span>=best.span then reason='not_better'
        else
          -- Refine promising patches before admitting them. This catches wet
          -- depressions and ridges between the initial 25 sample points.
          measured,reason=samples(x,y,12)
          if measured and measured.span>maximum then reason='too_uneven' end
        end
      end
      if reason then report.rejected[reason]=report.rejected[reason]+1;return false end
      if best and measured.span>=best.span then
        report.rejected.not_better=report.rejected.not_better+1;return false
      end
      local occupied,count=false,0
      local box=api.type.Box3.new(api.type.Vec3f.new(x-half,y-half,measured.low-100),
        api.type.Vec3f.new(x+half,y+half,measured.high+100))
      api.engine.system.octreeSystem.findIntersectingEntities(box,function(id)
        count=count+1;if count>10000 then occupied=true;return end
        for _,kind in ipairs({'CONSTRUCTION','BASE_EDGE','TOWN_BUILDING','SIM_BUILDING'})do
          if api.engine.getComponent(id,api.type.ComponentType[kind])then occupied=true end
        end
      end)
      if occupied then report.rejected.occupied=report.rejected.occupied+1;return false end
      best={x=x,y=y,z=(measured.low+measured.high)/2,span=measured.span,
        heights=measured.heights,examined=report.examined}
      return measured.span<=preferred
    end
    local preferred_found=consider(0,0)
    for ring=1,32 do
      if preferred_found then break end
      for x=-ring,ring do
        if preferred_found then break end
        for y=-ring,ring do
          if math.max(math.abs(x),math.abs(y))==ring and consider(x,y)then preferred_found=true;break end
        end
      end
    end
    if not best then
      local r=report.rejected
      error('build_site_unavailable: checked='..report.examined..' outside='..r.outside..
        ' water='..r.water..' uneven='..r.too_uneven..' occupied='..r.occupied..
        ' best_dry_span_mm='..tostring(report.best_dry_span_mm or 'none'),0)
    end
    report.selected={x_mm=best.x*1000,y_mm=best.y*1000,
      span_mm=int(math.floor(best.span*1000+.5)),candidate=best.examined}
    return {x=best.x,y=best.y,z=best.z,vehicle_model=vehicle_model,description={
      x_mm=int(best.x*1000),y_mm=int(best.y*1000),z_mm=int(math.floor(best.z*1000+.5)),
      recipe_id=assets.id,water_level=dec(water),height_samples=best.heights,
      terrain_preparation={kind='construction_alignment',preferred_span_m=dec(preferred),
        maximum_span_m=dec(maximum),sampled_span_m=dec(best.span)},
      assets={road=assets.road_file,depot=assets.depot_file,stop=assets.stop_file,vehicle=vehicle_model,street=assets.street_type}}}
  end
  local site
  local function transform(offset,rotation)
    offset=offset or {0,0,0};rotation=rotation or {1,0,0,1}
    return api.type.Mat4f.new(api.type.Vec4f.new(rotation[1],rotation[2],0,0),api.type.Vec4f.new(rotation[3],rotation[4],0,0),
      api.type.Vec4f.new(0,0,1,0),api.type.Vec4f.new(site.x+offset[1],site.y+offset[2],site.z+(offset[3]or 0),1))
  end
  local function context()
    local c=api.type.Context.new();c.player=api.engine.util.getPlayer();c.checkTerrainAlignment=true
    c.cleanupStreetGraph=false;c.gatherBuildings=false;c.gatherFields=false;return c
  end
  local function construction(file,params,offset,rotation,name)
    local proposal=api.type.SimpleProposal.new();local c=api.type.SimpleProposal.ConstructionEntity.new()
    c.fileName=file;c.params=clone(params);c.transf=transform(offset,rotation);c.name=name;c.playerEntity=api.engine.util.getPlayer()
    proposal.constructionsToAdd[1]=c
    return api.cmd.make.buildProposal(proposal,context(),false)
  end
  local function vehicle_config(cfg,path)
    path=path or 'TRANSPORT_VEHICLE.transportVehicleConfig'
    local out={vehicles=json.array(),groups=json.array()}
    for i,v in ipairs(arr(read(cfg,'vehicles',path),1,path..'.vehicles'))do
      local vp=path..'.vehicles['..i..']';local pp=vp..'.part'
      local p=need(read(v,'part',vp),'vehicle part absent at '..pp);local load,auto=json.array(),json.array()
      -- -1 is the documented automatic load configuration; retain it as read.
      for j,x in ipairs(arr(read(p,'loadConfig',pp),1,pp..'.loadConfig'))do load[j]=int(x,-1,nil,pp..'.loadConfig['..j..']')end
      for j,x in ipairs(arr(read(v,'autoLoadConfig',vp),1,vp..'.autoLoadConfig'))do auto[j]=dec(x,vp..'.autoLoadConfig['..j..']')end
      if #load~=1 or #auto~=1 then error('invalid one-compartment vehicle config',0)end
      out.vehicles[i]={model=resource(api.res.modelRep,read(p,'modelId',pp),pp..'.modelId'),load_config=load,auto_load_config=auto,
        purchase_time=dec(read(v,'purchaseTime',vp),vp..'.purchaseTime'),maintenance=dec(read(v,'maintenanceState',vp),vp..'.maintenanceState'),
        target_maintenance=dec(read(v,'targetMaintenanceState',vp),vp..'.targetMaintenanceState'),
        reversed=boolean(read(p,'reversed',pp),pp..'.reversed'),color=vector(read(p,'color',pp),3,pp..'.color'),logo=need(read(p,'logo',pp),'vehicle logo absent')}
    end
    for i,x in ipairs(arr(read(cfg,'vehicleGroups',path),1,path..'.vehicleGroups'))do out.groups[i]=int(x,1,1,path..'.vehicleGroups['..i..']')end
    if #out.vehicles~=1 or #out.groups~=1 then error('incomplete build vehicle config',0)end;return out
  end
  function E.bind_initial(values)
    if #arr(values,0)~=0 then error('build test requires empty initial bindings',0)end
    site=choose_site()
  end
  function E.local_bindings()local out={};for k,b in pairs(E.bindings)do out[k]=b.entity end;return out end
  function E.diagnostic_bindings()
    local out=E.local_bindings()
    -- An exact callback identity is useful for raw failure diagnosis before
    -- recipe validation succeeds. It never enters verified bindings or state.
    if diagnostic_candidate and not E.reverse[diagnostic_candidate.entity]then
      out['callback:'..diagnostic_candidate.key]=diagnostic_candidate.entity
    end
    return out
  end
  function E.plan(c,key,time_us)
    if type(key)~='string'or not key:match('^[ab]:[1-9]%d*$')or E.bindings[key]then error('invalid build key',0)end
    local op=need(c.op,'build op absent');local allowed={op=true};if op=='SET_PAUSED'then allowed.value=true elseif op=='PROBE_STOP'then allowed.index=true end
    for k in pairs(c)do if not allowed[k]then error('unexpected build command field',0)end end
    local command,kind,index
    if op=='SET_PAUSED'then command=api.cmd.make.setGameSpeed(boolean(c.value)and 0 or 1)
    elseif op=='PROBE_ROAD'then
      if E.scene.road then error('road already built',0)end;kind='road'
      command=construction(assets.road_file,assets.road_params,nil,nil,'TF2 Coop Test Road')
    elseif op=='PROBE_DEPOT'then
      need(E.scene.road,'road not built');if E.scene.depot then error('depot already built',0)end;kind='depot'
      command=construction(assets.depot_file,assets.depot_params,assets.depot_offset,nil,'TF2 Coop Test Depot')
    elseif op=='PROBE_STOP'then
      need(E.scene.depot,'depot not built');index=int(c.index,0,1)+1
      if E.scene.stops[index]or(index==2 and not E.scene.stops[1])then error('stop order',0)end;kind='stop'
      command=construction(assets.stop_file,assets.stop_params,assets.stop_offsets[index],assets.stop_rotations[index],'TF2 Coop Test Stop '..index)
    elseif op=='PROBE_VEHICLE'then
      need(E.scene.stops[2],'stops not built');if E.scene.vehicle then error('vehicle already bought',0)end;kind='vehicle'
      if not E.snapshot().probe.connectivity.connected then error('build_road_connectivity_missing',0)end
      local depot=localid(E.scene.depot..':depot');if int(component(depot,'VEHICLE_DEPOT').carrier)~=0 then error('road depot carrier mismatch',0)end
      local model=int(api.res.modelRep.find(site.vehicle_model),0);local part=api.type.VehiclePart.new()
      part.modelId=model;part.reversed=false;part.color=api.type.Vec3f.new(-1,-1,-1);part.logo=''
      local load=part.loadConfig;load[1]=0;part.loadConfig=load
      local v=api.type.TransportVehiclePart.new();v.part=part;v.purchaseTime=int(time_us/1000,1);v.maintenanceState=1;v.targetMaintenanceState=0
      local auto=v.autoLoadConfig;auto[1]=1;v.autoLoadConfig=auto
      local cfg=api.type.TransportVehicleConfig.new();cfg.vehicles[1]=v;local groups=cfg.vehicleGroups;groups[1]=1;cfg.vehicleGroups=groups
      local check=vehicle_config(cfg);if check.vehicles[1].model~=site.vehicle_model then error('build vehicle config readback differs',0)end
      command=api.cmd.make.buyVehicle(api.engine.util.getPlayer(),depot,cfg)
    elseif op=='PROBE_LINE'then
      need(E.scene.vehicle,'vehicle not bought');if E.scene.line then error('line already built',0)end;kind='line'
      local line=api.type.Line.new();line.waitingTime=0
      for i=1,2 do
        local s=api.type.Line.Stop.new();s.stationGroup=localid(E.scene.stops[i]..':group');s.station=0;s.terminal=0;s.loadMode=0;s.minWaitingTime=0;s.maxWaitingTime=0
        if #arr(component(localid(E.scene.stops[i]..':station'),'STATION').terminals,16)<1 then error('stop has no terminal',0)end
        line.stops[i]=s
      end
      if #arr(line.stops,2)~=2 then error('line stop writeback failed',0)end
      command=api.cmd.make.createLine('TF2 Coop Test Line',api.type.Vec3f.new(.1,.5,.9),api.engine.util.getPlayer(),line)
    elseif op=='PROBE_ASSIGN'then
      need(E.scene.line,'line not built');if E.assigned then error('vehicle already assigned',0)end
      if #arr(component(localid(E.scene.line),'LINE').stops,2)~=2 then error('line lacks two stops',0)end
      command=api.cmd.make.setLine(localid(E.scene.vehicle),localid(E.scene.line),0)
    else error('unsupported build op',0)end
    return {native=need(command,'build maker returned nil'),key=key,kind=kind,index=index,command=c}
  end
  function E.finish(plan,result,success)
    diagnostic_candidate=nil
    if success~=true then return {success=false,result={error='engine_rejected',op=plan.command.op}}end
    local id
    if plan.kind=='vehicle'or plan.kind=='line'then
      for _,name in ipairs({'resultEntity','resultVehicleEntity'})do local n=tonumber(field(result,name))
        if n and n>0 then if id and id~=n then error('ambiguous callback vehicle/line',0)end;id=int(n,1)end
      end
    elseif plan.kind then
      for _,n in ipairs(arr(need(field(result,'resultEntities'),'construction callback has no resultEntities'),128))do
        n=existing(n)
        if api.engine.getComponent(n,api.type.ComponentType.CONSTRUCTION)then if id then error('ambiguous construction callback',0)end;id=n end
      end
    end
    if plan.kind then
      id=existing(need(id,'successful build callback lacks exact entity'))
      diagnostic_candidate={key=plan.key,entity=id}
      if plan.kind=='vehicle'then
        local v=component(id,'TRANSPORT_VEHICLE')
        if int(v.carrier)~=0 or v.depot~=localid(E.scene.depot..':depot')or vehicle_config(v.transportVehicleConfig).vehicles[1].model~=site.vehicle_model then error('bought vehicle differs from requested recipe',0)end
      elseif plan.kind=='line'then component(id,'LINE')
      else
        local expected=plan.kind=='road'and assets.road_file or plan.kind=='depot'and assets.depot_file or assets.stop_file
        if component(id,'CONSTRUCTION').fileName~=expected then error('callback construction differs from requested recipe',0)end
      end
      bind(plan.key,plan.kind,id)
      if plan.kind=='depot'then
        local children=arr(component(id,'CONSTRUCTION').depots,1);if #children~=1 then error('depot child count',0)end
        component(children[1],'VEHICLE_DEPOT');bind(plan.key..':depot','depot_child',children[1],children[1]==id and plan.key or nil);E.scene.depot=plan.key
      elseif plan.kind=='stop'then
        local stations=arr(component(id,'CONSTRUCTION').stations,1);if #stations~=1 then error('station child count',0)end
        local group=api.engine.system.stationGroupSystem.getStationGroup(stations[1]);local members=arr(component(group,'STATION_GROUP').stations,1)
        if #members~=1 or members[1]~=stations[1]then error('unexpected station grouping',0)end
        bind(plan.key..':station','station',stations[1],stations[1]==id and plan.key or nil)
        -- A construction may itself carry STATION_GROUP. Preserve the
        -- authoritative component alias instead of requiring different IDs.
        local owner=group==id and plan.key or group==stations[1]and E.reverse[stations[1]]or nil
        bind(plan.key..':group','station_group',group,owner)
        E.groups[group]=plan.key;E.stations[stations[1]]=plan.key;E.scene.stops[plan.index]=plan.key
      else E.scene[plan.kind]=plan.key end
    elseif plan.command.op=='PROBE_ASSIGN'then E.assigned=true end
    local outcome=id and {logical_id=plan.key}or{target=plan.command.op=='PROBE_ASSIGN'and E.scene.vehicle or ''}
    if plan.command.op=='SET_PAUSED'then outcome={paused=plan.command.value}end
    return {success=true,result=outcome,result_entity=id}
  end
  function E.snapshot()
    need(site,'build site not initialized');local keys={};for k in pairs(E.bindings)do keys[#keys+1]=k end;table.sort(keys)
    local objects,missing,observed_unavailable=json.array(),json.array(),json.array();local node_names,graph,anchors={},{},{}
    local function optional_numeric(v,k,path,integer,required)
      local x=read(v,k,path);local p=path..'.'..k
      if x==nil and not required then
        observed_unavailable[#observed_unavailable+1]=p
        return {available=false}
      end
      return {available=true,value=integer and int(x,required and 0 or nil,nil,p)or dec(x,p)}
    end
    local function edges_for(key,id)
      local cp=key..'.CONSTRUCTION'
      local edges=arr(read(component(id,'CONSTRUCTION'),'frozenEdges',cp),128,cp..'.frozenEdges');if #edges==0 then error('construction has no owned road edges',0)end
      for i,edgeid in ipairs(edges)do local e=component(int(edgeid,1,nil,cp..'.frozenEdges['..i..']'),'BASE_EDGE')
        local p=key..'.roads['..i..'].BASE_EDGE';local nodes={}
        for side=0,1 do local k='node'..side;local n=int(read(e,k,p),1,nil,p..'.'..k);nodes[side]=n;node_names[n]=node_names[n]or key..':edge:'..i..':node:'..side end
        graph[nodes[0]]=graph[nodes[0]]or{};graph[nodes[1]]=graph[nodes[1]]or{};graph[nodes[0]][nodes[1]]=true;graph[nodes[1]][nodes[0]]=true
        anchors[key]=anchors[key]or nodes[0]
      end;return edges
    end
    for _,key in ipairs(keys)do local b=E.bindings[key]
      if b.kind=='road'or b.kind=='depot'or b.kind=='stop'then
        local ok,err=pcall(edges_for,key,b.entity);if not ok then missing[#missing+1]=key..':'..safe_error(err)end
      end
    end
    local function road_edge(id,path)
      local e=component(id,'BASE_EDGE');local s=component(id,'BASE_EDGE_STREET')
      local ep,sp=path..'.BASE_EDGE',path..'.BASE_EDGE_STREET'
      local n0=int(read(e,'node0',ep),1,nil,ep..'.node0');local n1=int(read(e,'node1',ep),1,nil,ep..'.node1')
      local p0,p1=path..'.node0.BASE_NODE',path..'.node1.BASE_NODE'
      return {node0=need(node_names[n0],'missing node identity'),node1=need(node_names[n1],'missing node identity'),
        position0=vector(read(component(n0,'BASE_NODE'),'position',p0),3,p0..'.position'),position1=vector(read(component(n1,'BASE_NODE'),'position',p1),3,p1..'.position'),
        tangent0=vector(read(e,'tangent0',ep),3,ep..'.tangent0'),tangent1=vector(read(e,'tangent1',ep),3,ep..'.tangent1'),
        street=resource(api.res.streetTypeRep,read(s,'streetType',sp),sp..'.streetType'),
        type=int(read(e,'type',ep),nil,nil,ep..'.type'),type_index=int(read(e,'typeIndex',ep),nil,nil,ep..'.typeIndex'),
        has_bus=boolean(read(s,'hasBus',sp),sp..'.hasBus'),tram_track=int(read(s,'tramTrackType',sp),nil,nil,sp..'.tramTrackType')}
    end
    local probe={profile='build_v1',site=clone(site.description),scene={stops=json.array()}}
    -- Observe the real terrain again after construction alignment. The frozen
    -- site description keeps the original samples; these current values enter
    -- every shared digest and can expose a differing terrain result.
    probe.terrain_height_samples=json.array()
    for ix=-2,2 do for iy=-2,2 do
      local p=api.type.Vec2f.new(site.x+ix*assets.half_extent/2,site.y+iy*assets.half_extent/2)
      local path='terrain.samples['..ix..','..iy..']'
      if not boolean(api.engine.terrain.isValidCoordinate(p),path..'.isValidCoordinate')then error('build terrain sample outside map',0)end
      probe.terrain_height_samples[#probe.terrain_height_samples+1]=dec(api.engine.terrain.getHeightAt(p),path..'.getHeightAt')
    end end
    for _,name in ipairs({'road','depot','vehicle','line'})do probe.scene[name]=E.scene[name]end
    for i=1,2 do probe.scene.stops[i]=E.scene.stops[i]end
    local function state(key,b)
      local id=existing(b.entity)
      if b.kind=='road'or b.kind=='depot'or b.kind=='stop'then
        local p=key..'.CONSTRUCTION';local c=component(id,'CONSTRUCTION');local edges=json.array()
        for i,edge in ipairs(arr(read(c,'frozenEdges',p),128,p..'.frozenEdges'))do edges[#edges+1]=road_edge(int(edge,1,nil,p..'.frozenEdges['..i..']'),key..'.roads['..i..']')end
        table.sort(edges,function(a,z)return json.encode(a)<json.encode(z)end)
        return {file=c.fileName,params=canonical(c.params),transform=matrix(read(c,'transf',p),p..'.transf'),time_build=optional_numeric(c,'timeBuild',p,false,false),
          name=component(id,'NAME').name,roads=edges}
      elseif b.kind=='depot_child'then
        local d=component(id,'VEHICLE_DEPOT');local p=key..'.VEHICLE_DEPOT'
        return{carrier=int(read(d,'carrier',p),nil,nil,p..'.carrier'),state=int(read(d,'state',p),nil,nil,p..'.state'),
          doors=int(read(d,'doors',p),nil,nil,p..'.doors'),state_time=dec(read(d,'stateTime',p),p..'.stateTime')}
      elseif b.kind=='station_group'then
        local p=key..'.STATION_GROUP';local out=json.array()
        for i,s in ipairs(arr(read(component(id,'STATION_GROUP'),'stations',p),1,p..'.stations'))do out[#out+1]=reference(s,p..'.stations['..i..']')end;return{stations=out}
      elseif b.kind=='station'then
        local s=component(id,'STATION');local p=key..'.STATION'
        return {cargo=boolean(read(s,'cargo',p),p..'.cargo'),terminals=#arr(read(s,'terminals',p),16,p..'.terminals')}
      elseif b.kind=='line'then
        local l=component(id,'LINE');local p=key..'.LINE';local stops,vehicles,details=json.array(),json.array(),json.array()
        for i,s in ipairs(arr(read(l,'stops',p),2,p..'.stops'))do
          local sp=p..'.stops['..i..']'
          local group=int(read(s,'stationGroup',sp),1,nil,sp..'.stationGroup')
          stops[i]=need(E.groups[group],'unknown line station group at '..sp..'.stationGroup')
          details[i]={stop=stops[i],station=int(read(s,'station',sp),nil,nil,sp..'.station'),terminal=int(read(s,'terminal',sp),nil,nil,sp..'.terminal'),
            load_mode=int(read(s,'loadMode',sp),nil,nil,sp..'.loadMode'),min_wait=dec(read(s,'minWaitingTime',sp),sp..'.minWaitingTime'),max_wait=dec(read(s,'maxWaitingTime',sp),sp..'.maxWaitingTime')}
        end
        for i,v in ipairs(arr(api.engine.system.transportVehicleSystem.getLineVehicles(id),1,p..'.getLineVehicles'))do vehicles[#vehicles+1]=reference(v,p..'.getLineVehicles['..i..']')end;table.sort(vehicles)
        probe.line={logical_id=key,stops=stops,vehicles=vehicles}
        return {stops=details,vehicles=vehicles,name=component(id,'NAME').name,color=vector(read(component(id,'COLOR'),'color',key..'.COLOR'),3,key..'.COLOR.color')}
      elseif b.kind=='vehicle'then
        local v=component(id,'TRANSPORT_VEHICLE');local p=key..'.TRANSPORT_VEHICLE'
        local state_value=int(read(v,'state',p),nil,nil,p..'.state')
        local parked=state_value==int(api.type.enum.TransportVehicleState.IN_DEPOT,nil,nil,'api.type.enum.TransportVehicleState.IN_DEPOT')
        local line_ref=reference(read(v,'line',p),p..'.line')
        local out={config=vehicle_config(read(v,'transportVehicleConfig',p),p..'.transportVehicleConfig'),line=line_ref,
          depot=reference(read(v,'depot',p),p..'.depot'),state=state_value,
          user_stopped=boolean(read(v,'userStopped',p),p..'.userStopped'),no_path=boolean(read(v,'noPath',p),p..'.noPath'),
          stop_index=optional_numeric(v,'stopIndex',p,true,line_ref~=''),carrier=int(read(v,'carrier',p),nil,nil,p..'.carrier')}
        probe.vehicle={logical_id=key,line=out.line,in_depot=parked,state=out.state,no_path=out.no_path}
        if parked then out.position='in_depot' else
          -- Assignment can change state before first world placement. Record
          -- observed absence; final proof still requires real changed positions.
          local data=game.interface.getEntity(id);local position=data and field(data,'position')
          out.world_position_present=position~=nil;probe.vehicle.world_position_present=position~=nil
          if position then
            out.position=vector(position,3,key..'.game.interface.getEntity.position')
            local mm=json.array();for i=1,3 do mm[i]=int(math.floor(num(out.position[i],key..'.position['..i..']')*1000+.5),nil,nil,key..'.position_mm['..i..']')end;probe.vehicle.position_mm=mm
          end
          local move=api.engine.getComponent(id,api.type.ComponentType.MOVE_PATH);out.move_path_present=move~=nil
          if move then
            local mp=key..'.MOVE_PATH';local dyn=read(move,'dyn',mp);mp=mp..'.dyn'
            local pos=read(dyn,'pathPos',mp);local pp=mp..'.pathPos'
            out.movement={speed=dec(read(dyn,'speed',mp),mp..'.speed'),edge_index=int(read(pos,'edgeIndex',pp),nil,nil,pp..'.edgeIndex'),
              position=dec(read(pos,'pos',pp),pp..'.pos'),position01=dec(read(pos,'pos01',pp),pp..'.pos01')}
          end
        end
        return out
      end
      error('unsupported build binding kind',0)
    end
    for _,key in ipairs(keys)do
      local ok,s=pcall(state,key,E.bindings[key]);if not ok then missing[#missing+1]=key..':'..safe_error(s);s={unavailable=true}end
      objects[#objects+1]={logical_id=key,kind=E.bindings[key].kind,state=s}
    end
    if E.scene.road and E.scene.depot and E.scene.stops[2]then
      local first=anchors[E.scene.road];local visited,queue={},{};if first then visited[first]=true;queue[1]=first end
      local at=1;while at<=#queue do local n=queue[at];at=at+1;for other in pairs(graph[n]or{})do if not visited[other]then visited[other]=true;queue[#queue+1]=other end end end
      local connected=true;for _,key in ipairs({E.scene.road,E.scene.depot,E.scene.stops[1],E.scene.stops[2]})do if not visited[anchors[key]or -1]then connected=false end end
      probe.connectivity={connected=connected}
    end
    local account=need(game.interface.getEntity(api.engine.util.getPlayer()),'company unavailable')
    table.sort(observed_unavailable)
    local time=read(game.interface.getGameTime(),'time','game.interface.getGameTime')
    return {sim_time_us=int(math.floor(num(time,'game.interface.getGameTime.time')*1000000+.5),0,nil,'sim_time_us'),paused=num(game.interface.getGameSpeed(),'game.interface.getGameSpeed')==0,
      company={balance=int(read(account,'balance','company'),nil,nil,'company.balance'),loan=int(read(account,'loan','company'),0,nil,'company.loan')},objects=objects,probe=probe,
      coverage={complete_world=false,tracked_objects=true,missing=missing,observed_unavailable=observed_unavailable,
        excluded=json.array({'untracked_world','cargo_contents','rng','path_reservations','terrain_outside_test','station_internals','movement_before_world_placement'})}}
  end
  E.integer=int
  return E
end
return M
