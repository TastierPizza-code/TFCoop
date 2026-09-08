-- Fixed, bounded build experiment. Commands mutate only when the common
-- coordinator applies them; callback identities are never guessed by location.
local assets = require 'tf2_strict_probe/build_assets'
local M = {}
function M.new(json,config)
  local E = {bindings={},reverse={},scene={stops={}},groups={},stations={}}
  local manual = config and config.input_mode=='manual_depot_v1'
  local rail_mode = config and config.input_mode=='guided_rail_v1'
  local guided_mode = config and(config.input_mode=='guided_suite_v1'or rail_mode)
  local guided,rail
  local manual_assets = manual and require 'tf2_strict_probe/manual_depot_assets' or nil
  local placements = {}
  local diagnostic_candidate
  local callback_report
  local preflight_report
  local function need(v,msg) if v==nil then error(msg,0) end return v end
  -- Native member userdata can borrow storage from their component/container.
  -- Holding the child alone need not keep that owner alive. Root every owner
  -- until this operation has finished converting its observations to plain Lua.
  -- This does not cache observations, retry getters or change collection order.
  local owners
  local MAX_OWNERS=32768
  local function keep(v)
    local t=type(v)
    if owners and(t=='userdata'or t=='table')and not owners.seen[v]then
      if owners.count>=MAX_OWNERS then error('native owner budget exceeded',0)end
      owners.seen[v]=true;owners.count=owners.count+1
    end
    return v
  end
  local function release(ok,...)
    owners=nil -- Release on success and on exceptions; never retain across ticks.
    if not ok then error((...),0)end
    -- TF2 overrides table.unpack(t) and ignores its start/end arguments.
    -- Forward varargs directly so nils and multiple results remain unchanged.
    return ...
  end
  local function operation(fn,...)
    -- Planning a vehicle also takes a snapshot. Its owners belong to the same
    -- outer operation, so a nested call must not release them early.
    if owners then return fn(...)end
    owners={seen={},count=0}
    return release(pcall(fn,...))
  end
  -- Native usertypes may throw for an absent member. Always return one value:
  -- falling through returns zero values, which breaks type(field(...)) and
  -- tonumber(field(...)) before the supported alternative can be inspected.
  local function field(v,k) keep(v);local ok,x=pcall(function()return v[k]end);if ok then return keep(x)end;return nil end
  local function safe_error(v)
    if type(v)=='string'then
      local text=v:gsub('0[xX]%x+','[address]')
      if #text>1024 then return text:sub(1,256)..' ... '..text:sub(-768)end
      return text
    end
    return 'error value has Lua type='..type(v)
  end
  local function capture_callback(plan,result,success)
    local MAX_BYTES,MAX_RECORDS,MAX_DEPTH,MAX_WIDTH,MAX_STRING=16384,128,3,8,256
    local cut=false
    local function text(s)
      -- Same byte validation as the independent API audit: preserve complete
      -- Unicode, replace malformed bytes, and never publish pointer strings.
      local original=s;s=s:gsub('0[xX]%x+','[address]')
      local out,n,i={},0,1
      while i<=#s and n<MAX_STRING do
        local b=s:byte(i);local size=b<128 and 1 or(b>=194 and b<=223 and 2 or(b>=224 and b<=239 and 3 or(b>=240 and b<=244 and 4 or 0)))
        local valid=size>0 and i+size-1<=#s
        if valid and size>1 then
          for j=1,size-1 do local c=s:byte(i+j);if c<128 or c>191 then valid=false end end
          local c=s:byte(i+1)
          if(b==224 and c<160)or(b==237 and c>159)or(b==240 and c<144)or(b==244 and c>143)then valid=false end
        end
        if not valid then out[#out+1]='?';n=n+1;i=i+1
        elseif n+size>MAX_STRING then break
        else out[#out+1]=s:sub(i,i+size-1);n=n+size;i=i+size end
      end
      local clean=table.concat(out);if clean~=original then cut=true end;return clean
    end
    local function primitive(v)
      local t=type(v);local out={type=t}
      if t=='boolean'then out.value=v
      elseif t=='string'then out.value=text(v)
      elseif t=='number'then
        if v~=v then out.value='NaN'
        elseif v==math.huge then out.value='+Infinity'
        elseif v==-math.huge then out.value='-Infinity'
        else out.value=string.format('%.17g',v)end
      end
      return out
    end
    local key=field(plan,'key');local command=field(plan,'command');local op=field(command,'op')
    local report={format=1,valid_snapshot=false,
      command_key=type(key)=='string'and text(key)or '',op=type(op)=='string'and text(op)or '',
      success=primitive(success),result_type=type(result),records=json.array(),truncated=false,
      limits={max_bytes=MAX_BYTES,max_records=MAX_RECORDS,max_depth=MAX_DEPTH,max_width=MAX_WIDTH,max_string_bytes=MAX_STRING,dropped_records=0}}
    -- If any unexpected diagnostic failure escapes a protected field read,
    -- retain this small plain envelope instead of losing the callback facts.
    callback_report={format=1,valid_snapshot=false,command_key=report.command_key,op=report.op,
      success=report.success,result_type=report.result_type,records=json.array(),truncated=true,
      capture_failed=true,limits=report.limits}
    local records,paths=report.records,{}
    local function emit(path,fn)
      if #records>=MAX_RECORDS then cut=true;report.limits.dropped_records=report.limits.dropped_records+1;return nil end
      local ok,value=pcall(fn);local row=ok and primitive(value)or{type='unavailable',error_type=type(value),error=text(safe_error(value))}
      row.path=text(path);row.access=ok and(value==nil and 'nil'or 'ok')or 'throws'
      records[#records+1]=row;paths[path]=true
      if ok then return value end
      return nil
    end
    local function member(value,key,path)
      keep(value)
      return keep(emit(path,function()return value[key]end))
    end
    local active={}
    local visit
    visit=function(value,path,depth)
      local kind=type(value)
      if kind~='table'and kind~='userdata'then return end
      if #records>=MAX_RECORDS then cut=true;return end
      if active[value]then emit(path..'.@cycle',function()return true end);cut=true;return end
      if depth>=MAX_DEPTH then cut=true;return end
      active[value]=true
      local keys,seen={},{}
      local function add_key(k)
        local t=type(k)
        if t~='string'and t~='number'then
          emit(path..'.@unsupported_key',function()return t end);return
        end
        local name=t=='string'and k or primitive(k).value
        local identity=t..':'..name
        if not seen[identity]then
          if #keys>=MAX_WIDTH then cut=true;return end
          seen[identity]=true;keys[#keys+1]={key=k,name=name}
        end
      end
      local mt=kind=='userdata'and getmetatable(value)or nil
      local members=mt and field(mt,'__members')or nil
      if members~=nil then
        local n=emit(path..'.@members.length',function()return #members end)
        if type(n)=='number'and n==n and n>=0 and n%1==0 and n<math.huge then
          if n>MAX_WIDTH then cut=true end
          for i=1,math.min(n,MAX_WIDTH)do add_key(member(members,i,path..'.@members['..i..']'))end
        end
      else
        emit(path..'.@enumeration',function()
          local iterator,state,control=pairs(value)
          for i=1,MAX_WIDTH+1 do
            local k=iterator(state,control)
            if k==nil then return 'complete' end
            control=k;add_key(k)
          end
          cut=true;return 'limited'
        end)
      end
      for _,item in ipairs(keys)do
        local child=path..'.'..item.name
        if not paths[child]then
          local v=member(value,item.key,child)
          visit(v,child,depth+1)
        end
      end
      active[value]=nil
    end
    local observed={}
    for _,name in ipairs({'resultEntities','resultVehicleEntity','resultEntity','resultProposalData'})do
      observed[name]=member(result,name,'result.'..name)
    end
    -- The ErrorState field schema is not documented. Enumerate only observed
    -- members and never invoke methods found in the callback result.
    local proposal=observed.resultProposalData
    member(proposal,'costs','result.resultProposalData.costs')
    local error_state=member(proposal,'errorState','result.resultProposalData.errorState')
    visit(error_state,'result.resultProposalData.errorState',0)
    for _,name in ipairs({'resultEntities','resultVehicleEntity','resultEntity','resultProposalData'})do
      visit(observed[name],'result.'..name,0)
    end
    while true do
      report.truncated=cut
      local ok,encoded=pcall(json.encode,report)
      if ok and #encoded<=MAX_BYTES then return report end
      if #records==0 then error('callback diagnostic envelope cannot be encoded',0)end
      records[#records]=nil;report.limits.dropped_records=report.limits.dropped_records+1;cut=true
    end
  end
  local function invalid(reason,path,v)
    error(reason..' at '..(path or 'build value')..' (Lua type='..type(v)..')',0)
  end
  local function read(v,k,path)
    keep(v)
    local ok,x=pcall(function()return v[k]end)
    if not ok then error('getter threw at '..path..'.'..k..' (container Lua type='..type(v)..'): '..safe_error(x),0)end
    return keep(x)
  end
  local function num(v,path)
    local ok,n=pcall(tonumber,v)
    if not ok or not n or n~=n or math.abs(n)>9007199254740991 then invalid('invalid finite build value',path,v)end;return n
  end
  local function int(v,lo,hi,path) local n=num(v,path);if n%1~=0 or n<(lo or -9007199254740991) or n>(hi or 9007199254740991)then invalid('invalid build integer',path,v)end;return n end
  local function dec(v,path)return string.format('%.17g',num(v,path))end
  local function boolean(v,path)if type(v)~='boolean'then invalid('build boolean unavailable',path,v)end;return v end
  local function arr(v,max,path)
    keep(v)
    path=path or 'build array'
    if v==nil then invalid('build array unavailable',path,v)end
    local ok,n=pcall(function()return #v end)
    if not ok then invalid('build array length unavailable',path,v)end
    n=int(n,0,max,path..'.#');local out=json.array()
    for i=1,n do out[i]=need(read(v,i,path),'build array hole at '..path..'['..i..'] (Lua type=nil)')end;return out
  end
  local function vector(v,n,path)
    keep(v)
    path=path or 'build vector'
    local out=json.array();local names={'x','y','z','w'}
    for i=1,n do local x=field(v,names[i]);local p=path..'.'..names[i]
      if x==nil then x=field(v,i);p=p..'/['..i..']'end;out[i]=dec(x,p)end;return out
  end
  local function matrix(v,path)
    keep(v)
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
      keep(v)
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
    return keep(need(api.engine.getComponent(id,need(api.type.ComponentType[kind],'component API '..kind)), 'build component absent: '..kind))
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
  local function manual_command(c,key)
    if not manual then error('manual depot capability not enabled',0)end
    if type(c)~='table'or c.op~='BUILD_DEPOT'then error('manual depot command required',0)end
    for k in pairs(c)do if k~='op'and k~='site'and k~='rotation'then error('unexpected manual depot field',0)end end
    if type(c.site)~='number'or c.site%1~=0 or c.site<1 or c.site>#manual_assets.sites
      or type(c.rotation)~='number'or manual_assets.rotations[c.rotation]==nil then error('invalid manual depot site/rotation',0)end
    if type(key)~='string'or not key:match('^[ab]:[1-9]%d*$')or #key>96 or E.bindings[key]then error('invalid manual depot identity',0)end
    local peer,seq=key:match('^([ab]):([1-9]%d*)$');seq=int(seq,1,10000)
    return peer,seq
  end
  local function manual_preview(c,key)
    local peer,seq=manual_command(c,key)
    need(site,'manual depot requires the initialized shared site')
    local offset=manual_assets.sites[c.site];local half=manual_assets.half_extent
    local x,y=site.x+offset[1],site.y+offset[2]
    local description={contract=manual_assets.contract,site=c.site,rotation=c.rotation,
      allowed=false,reason='',cost=json.null,position_mm=json.null,
      proposal={file=assets.depot_file,site=c.site,rotation=c.rotation}}
    local function reject(reason)return description,nil,reason end
    -- A previous successful command owns a slot for the entire bounded test.
    -- The actual construction/child stays in every snapshot and is checked
    -- below through its binding; this is not an optimistic occupancy guess.
    for _,placed in pairs(placements)do
      if placed.site==c.site then existing(localid(placed.logical_id));return reject('site_occupied')end
    end
    local heights=json.array();local low,high=math.huge,-math.huge
    local water=terrain_water()
    for ix=-4,4 do for iy=-4,4 do
      local point=api.type.Vec2f.new(x+ix*half/4,y+iy*half/4)
      if not boolean(api.engine.terrain.isValidCoordinate(point),'manual.terrain.valid')then return reject('outside_map')end
      local height=num(api.engine.terrain.getHeightAt(point),'manual.terrain.height')
      if height<=water+2 then return reject('water')end
      low=math.min(low,height);high=math.max(high,height);heights[#heights+1]=dec(height)
    end end
    if high-low>manual_assets.max_height_span then return reject('too_uneven')end
    local z=math.floor((low+high)*500+.5)/1000
    description.position_mm=json.array({int(x*1000),int(y*1000),int(math.floor(z*1000+.5))})
    local occupied,count=false,0
    local box=api.type.Box3.new(api.type.Vec3f.new(x-half,y-half,low-100),api.type.Vec3f.new(x+half,y+half,high+100))
    api.engine.system.octreeSystem.findIntersectingEntities(box,function(id)
      count=count+1;if count>10000 then error('manual collision observation budget exceeded',0)end
      for _,kind in ipairs({'CONSTRUCTION','BASE_EDGE','TOWN_BUILDING','SIM_BUILDING'})do
        if api.engine.getComponent(id,need(api.type.ComponentType[kind],'manual component API '..kind))then occupied=true end
      end
    end)
    if occupied then return reject('site_occupied')end
    local params=clone(assets.depot_params);params.seed=200000+(peer=='b'and 10000 or 0)+seq
    local rotation=manual_assets.rotations[c.rotation]
    local transf=transform({offset[1],offset[2],z-site.z},rotation)
    local proposal=api.type.SimpleProposal.new();local entity=api.type.SimpleProposal.ConstructionEntity.new()
    entity.fileName=assets.depot_file;entity.params=params;entity.transf=transf
    entity.name='TF2 Coop Depot '..key;entity.playerEntity=api.engine.util.getPlayer()
    proposal.constructionsToAdd[1]=entity
    local options=context()
    -- Official proposal processing performs the engine's collision, terrain
    -- and price checks without sendCommand. Require the typed field contract
    -- used by the existing upstream integration; unreadable runtime fields are a terminal API
    -- failure rather than a fabricated successful preflight.
    local processed=keep(need(api.engine.util.proposal.makeProposalData(proposal,options),'manual proposal data absent'))
    -- Retain the observed userdata schema if a later required getter is
    -- absent. This is a read-only preflight observation, never a callback or
    -- permission to construct. Diagnostics cannot replace a validation error.
    local previous_callback=callback_report
    local captured,diagnostic=pcall(capture_callback,{key=key,command=c},{resultProposalData=processed},true)
    callback_report=previous_callback
    if captured then
      preflight_report=diagnostic;preflight_report.context='read_only_proposal_preflight'
      preflight_report.success={type='not_applicable'}
    else preflight_report={format=1,valid_snapshot=false,context='read_only_proposal_preflight',capture_failed=true}end
    local errors=read(processed,'errorState','manual.ProposalData')
    local critical=boolean(read(errors,'critical','manual.ErrorState'),'manual.ErrorState.critical')
    if critical then return reject('engine_rejected')end
    -- Only emptiness matters. Enumerate the observed native container contract
    -- instead of assuming #value and one-based indexing describe its entries.
    local messages=canonical(read(errors,'messages','manual.ErrorState'))
    if #messages~=0 then return reject('engine_rejected')end
    local cost=int(read(processed,'costs','manual.ProposalData'),0,nil,'manual.ProposalData.costs')
    description.cost=cost
    description.proposal={file=assets.depot_file,params=canonical(params),transform=matrix(transf),
      name=entity.name,site=c.site,rotation=c.rotation,terrain_samples=heights,cost=cost,
      clearance_half_extent_mm=half*1000}
    if cost<=0 then error('manual depot preflight did not expose a positive build cost',0)end
    local account=need(game.interface.getEntity(api.engine.util.getPlayer()),'manual company unavailable')
    if int(read(account,'balance','manual.company'))<cost then return reject('insufficient_funds')end
    description.allowed=true
    return description,{native=need(api.cmd.make.buildProposal(proposal,options,false),'manual build maker returned nil'),
      key=key,kind='manual_depot',command=clone(c),preview=description,
      expected_transform=matrix(transf),expected_params=canonical(params),
      before_balance=int(read(account,'balance','manual.company')),before_loan=int(read(account,'loan','manual.company'),0)}
  end
  function E.preview(c,key)
    if rail and c.op=='RAIL_ACTION'then return rail.preview(c,key)end
    if guided and not rail_mode and c.op=='GUIDED_ACTION'then return guided.preview(c,key)end
    preflight_report=nil
    local description,_,reason=manual_preview(c,key)
    if reason then description.reason=reason end
    return description
  end
  local function edge_values(id,path)
    id=existing(id)
    local e=component(id,'BASE_EDGE');local s=component(id,'BASE_EDGE_STREET')
    local ep,sp=path..'.BASE_EDGE',path..'.BASE_EDGE_STREET'
    local n0=existing(read(e,'node0',ep));local n1=existing(read(e,'node1',ep))
    if n0==n1 then error('self-linked street edge at '..path,0)end
    local p0,p1=path..'.node0.BASE_NODE',path..'.node1.BASE_NODE'
    return {node0=n0,node1=n1,
      position0=vector(read(component(n0,'BASE_NODE'),'position',p0),3,p0..'.position'),
      position1=vector(read(component(n1,'BASE_NODE'),'position',p1),3,p1..'.position'),
      tangent0=vector(read(e,'tangent0',ep),3,ep..'.tangent0'),tangent1=vector(read(e,'tangent1',ep),3,ep..'.tangent1'),
      street=resource(api.res.streetTypeRep,read(s,'streetType',sp),sp..'.streetType'),
      type=int(read(e,'type',ep),nil,nil,ep..'.type'),type_index=int(read(e,'typeIndex',ep),nil,nil,ep..'.typeIndex'),
      has_bus=boolean(read(s,'hasBus',sp),sp..'.hasBus'),tram_track=int(read(s,'tramTrackType',sp),nil,nil,sp..'.tramTrackType')}
  end
  local function snap_endpoint(key,point)
    local cp=key..'.CONSTRUCTION';local c=component(localid(key),'CONSTRUCTION')
    local t=matrix(read(c,'transf',cp),cp..'.transf');local p=arr(point,3,key..'.recipe_snap')
    if #p~=3 then error('connection recipe requires three coordinates',0)end
    local expected={}
    for i=1,3 do
      expected[i]=num(t[12+i])+num(t[i])*num(p[1])+num(t[4+i])*num(p[2])+num(t[8+i])*num(p[3])
      expected[i]=num(expected[i],key..'.expected_snap['..i..']')
    end
    if num(t[4])~=0 or num(t[8])~=0 or num(t[12])~=0 or num(t[16])~=1 then error('connection transform is not affine',0)end
    local frozen={}
    for _,n in ipairs(arr(read(c,'frozenNodes',cp),128,cp..'.frozenNodes'))do
      n=existing(n);if frozen[n]then error('duplicate construction frozen node',0)end;frozen[n]=true
    end
    local degrees,owned,observed={},{},{}
    local edges=arr(read(c,'frozenEdges',cp),128,cp..'.frozenEdges')
    if #edges==0 then error('connection construction has no owned street edges',0)end
    for i,id in ipairs(edges)do
      id=existing(id);if owned[id]then error('duplicate construction frozen edge',0)end
      local e=edge_values(id,key..'.connection_edge['..i..']');owned[id]=json.encode(e)
      for side=0,1 do local n=e['node'..side];degrees[n]=(degrees[n]or 0)+1;observed[n]=e['position'..side]end
    end
    local tolerance=num(assets.connection_tolerance,'connection_tolerance')
    if tolerance<=0 or tolerance>0.05 then error('invalid connection precision tolerance',0)end
    local selected
    for n,degree in pairs(degrees)do if degree==1 and not frozen[n]then
      local matches=true
      for i=1,3 do if math.abs(num(observed[n][i])-expected[i])>tolerance then matches=false end end
      if matches then if selected then error('ambiguous owned construction snap endpoint: '..key,0)end;selected=n end
    end end
    selected=need(selected,'owned construction snap endpoint unavailable: '..key)
    return {node=selected,position=observed[selected],owned=owned,owner=key}
  end
  local function street_map()
    -- Official api.engine streetSystem contract: {[nodeEntity]={edgeEntity,...}}.
    -- Read only the six owned endpoints; never locate identity by world position.
    return keep(need(api.engine.system.streetSystem.getNode2StreetEdgeMap(),'street incidence map unavailable'))
  end
  local function entity_collection(values,max,path,label,duplicate_error)
    keep(values)
    if type(values)~='table'and type(values)~='userdata'then invalid(label..' container unavailable',path,values)end
    local function length()
      local ok,n=pcall(function()return #values end)
      if not ok then error(label..' length read failed at '..path..': '..safe_error(n),0)end
      if type(n)~='number'then invalid(label..' length unavailable',path..'.#',n)end
      return int(n,0,max,path..'.#')
    end
    local expected=length()
    -- Native Sol2 lookup containers need not expose positional v[1..#v].
    -- Enumerate their actual values; never reinterpret keys as entity IDs.
    -- Only unordered street incidence and line-vehicle membership use this
    -- reader. Ordered construction, callback and vehicle arrays retain arr().
    local ok,iter,state,control=pcall(pairs,values)
    if not ok then error(label..' iterator unavailable at '..path..': '..safe_error(iter),0)end
    local out,seen,count=json.array(),{},0
    -- At most max values plus one terminating call. Even a broken iterator
    -- which never terminates cannot supply an unbounded or partial proof.
    for step=1,expected+1 do
      local read_ok,key,id=pcall(iter,state,control)
      if not read_ok then error(label..' iteration failed at '..path..' step '..step..': '..safe_error(key),0)end
      if key==nil then
        if id~=nil then invalid(label..' terminal value without key',path,id)end
        if count~=expected then error(label..' count mismatch at '..path..' (expected '..expected..', observed '..count..')',0)end
        if length()~=expected then error(label..' length changed during iteration at '..path,0)end
        return out
      end
      if count>=expected then error(label..' iterator exceeded declared length at '..path,0)end
      local value_path=path..'.value['..step..']'
      if type(id)~='number'then invalid(label..' entity value unavailable',value_path,id)end
      id=existing(int(id,1,2147483647,value_path))
      if seen[id]then error((duplicate_error or 'duplicate '..label..' entity')..' at '..path,0)end
      seen[id]=true;count=count+1;out[count]=id;control=key
    end
    error(label..' iterator did not terminate at '..path,0)
  end
  local function incident(map,node,path)
    local values=read(map,node,path);path=path..'['..node..']'
    local edges=entity_collection(values,16,path,'street incidence','duplicate incident street edge');local out={}
    for i,id in ipairs(edges)do
      local e=edge_values(id,path..'.value['..i..'].edge')
      if e.node0~=node and e.node1~=node then error('street incidence map has unrelated edge',0)end
      out[id]=json.encode(e)
    end
    return out,#edges
  end
  local function plan_connections(key)
    if E.scene.connectors then error('connections already built',0)end
    need(E.scene.road,'road not built');need(E.scene.depot,'depot not built');need(E.scene.stops[2],'stops not built')
    local specs={{E.scene.depot,assets.depot_snap,3},{E.scene.stops[1],assets.stop_snap,1},{E.scene.stops[2],assets.stop_snap,2}}
    local links,before_nodes,before_edges={}, {}, {}
    local map=street_map();local proposal=api.type.SimpleProposal.new()
    local street_proposal=read(proposal,'streetProposal','connection.proposal')
    local edges_to_add=read(street_proposal,'edgesToAdd','connection.streetProposal')
    local street=int(api.res.streetTypeRep.find(assets.street_type),0,nil,'connector.street')
    if resource(api.res.streetTypeRep,street,'connector.street')~=assets.street_type then error('connector street resource mismatch',0)end
    for i,spec in ipairs(specs)do
      local from=snap_endpoint(E.scene.road,assets.road_endpoints[spec[3]])
      local to=snap_endpoint(spec[1],spec[2]);local delta={}
      for _,endpoint in ipairs({from,to})do
        if before_nodes[endpoint.node]then error('connection endpoints are not six distinct owned nodes',0)end
        local edges,count=incident(map,endpoint.node,key..'.before')
        if count~=1 then error('construction snap endpoint is already connected or ambiguous',0)end
        for id,encoded in pairs(edges)do if endpoint.owned[id]~=encoded then error('snap endpoint has an unowned street edge',0)end end
        before_nodes[endpoint.node]={edges=edges,position=clone(endpoint.position)}
        for id,encoded in pairs(endpoint.owned)do
          if before_edges[id]and before_edges[id]~=encoded then error('owned street observation changed during planning',0)end
          before_edges[id]=encoded
        end
      end
      local length2=0
      for axis=1,3 do delta[axis]=num(to.position[axis])-num(from.position[axis]);length2=length2+delta[axis]^2 end
      local length=num(math.sqrt(length2),key..'.link_length')
      if math.abs(length-num(assets.connect_gap))>2*num(assets.connection_tolerance)then error('owned snap endpoints differ from connection gap recipe',0)end
      local e=api.type.SegmentAndEntity.new();e.entity=-i
      e.comp.node0=from.node;e.comp.node1=to.node
      e.comp.tangent0=api.type.Vec3f.new(delta[1],delta[2],delta[3]);e.comp.tangent1=api.type.Vec3f.new(delta[1],delta[2],delta[3])
      e.comp.type=0;e.comp.typeIndex=-1;e.type=0
      e.streetEdge=api.type.BaseEdgeStreet.new();e.streetEdge.streetType=street;e.streetEdge.hasBus=false;e.streetEdge.tramTrackType=0
      edges_to_add[i]=e
      links[i]={node0=from.node,node1=to.node,tangent=clone(delta)}
    end
    -- SimpleProposal uses negative edge IDs and existing positive node IDs.
    -- No nodes, removals or error overrides are part of this transaction.
    for _,name in ipairs({'constructionsToAdd','constructionsToRemove'})do
      if #arr(read(proposal,name,'connection.proposal'),0,'connection.proposal.'..name)~=0 then
        error('connection proposal contains unexpected construction mutation',0)
      end
    end
    for _,name in ipairs({'nodesToAdd','nodesToRemove','edgesToRemove','edgeObjectsToAdd','edgeObjectsToRemove'})do
      if #arr(read(street_proposal,name,'connection.streetProposal'),0,'connection.streetProposal.'..name)~=0 then
        error('connection proposal contains unexpected node/removal/object mutation',0)
      end
    end
    local added=arr(read(street_proposal,'edgesToAdd','connection.streetProposal'),3,'connection.streetProposal.edgesToAdd')
    if #added~=3 then error('connector edge vector writeback failed',0)end
    for i,e in ipairs(added)do
      if int(e.entity)~=-i or int(e.comp.node0)~=links[i].node0 or int(e.comp.node1)~=links[i].node1
        or int(e.comp.type)~=0 or int(e.comp.typeIndex)~=-1 or int(e.type)~=0
        or int(e.streetEdge.streetType)~=street or boolean(e.streetEdge.hasBus) or int(e.streetEdge.tramTrackType)~=0 then
        error('connector edge identities changed during proposal writeback',0)
      end
      for _,name in ipairs({'tangent0','tangent1'})do
        local tangent=vector(read(e.comp,name,'connection.edge.comp'),3,'connection.edge.comp.'..name)
        for axis=1,3 do if math.abs(num(tangent[axis])-links[i].tangent[axis])>num(assets.connection_tolerance)then
          error('connector tangent changed during proposal writeback',0)
        end end
      end
    end
    local options=context()
    if int(options.player,1)~=int(api.engine.util.getPlayer(),1)or not boolean(options.checkTerrainAlignment)
      or boolean(options.cleanupStreetGraph)or boolean(options.gatherBuildings)or boolean(options.gatherFields)then
      error('connector build context writeback differs',0)
    end
    local native=need(api.cmd.make.buildProposal(proposal,options,false),'connector maker returned nil')
    return native,{links=links,before_nodes=before_nodes,before_edges=before_edges}
  end
  local function finish_connections(plan,result)
    local expected=need(plan.connections,'connection plan observation absent')
    local map=street_map();local new_at_node,created={},{}
    for id,encoded in pairs(expected.before_edges)do
      if json.encode(edge_values(id,plan.key..'.preserved_edge'))~=encoded then error('existing street edge changed during connection build',0)end
    end
    for node,before in pairs(expected.before_nodes)do
      local position=vector(read(component(existing(node),'BASE_NODE'),'position',plan.key..'.node'),3,plan.key..'.node.position')
      if json.encode(position)~=json.encode(before.position)then error('existing connector endpoint moved',0)end
      local after=incident(map,node,plan.key..'.after');local fresh
      for id,encoded in pairs(before.edges)do if after[id]~=encoded then error('existing incident edge changed or disappeared',0)end end
      for id in pairs(after)do if not before.edges[id]then
        if fresh then error('multiple new incident edges at owned connector endpoint',0)end
        fresh=id
      end end
      new_at_node[node]=need(fresh,'new connector edge absent from owned endpoint')
    end
    for i,link in ipairs(expected.links)do
      local id=new_at_node[link.node0]
      if id~=new_at_node[link.node1]or created[id]then error('new connector edge does not uniquely join requested endpoint pair',0)end
      local e=edge_values(id,plan.key..':link:'..i)
      local forward=e.node0==link.node0 and e.node1==link.node1
      local reverse=e.node0==link.node1 and e.node1==link.node0
      if not forward and not reverse then error('new connector edge has different endpoint identities',0)end
      if e.street~=assets.street_type or e.type~=0 or e.type_index~=-1 or e.has_bus or e.tram_track~=0 then error('new connector street differs from requested recipe',0)end
      for axis=1,3 do for _,name in ipairs({'tangent0','tangent1'})do
        if math.abs(num(e[name][axis])-(forward and 1 or -1)*link.tangent[axis])>num(assets.connection_tolerance)then
          error('new connector tangent differs from requested straight edge',0)
        end
      end end
      local key=plan.key..':link:'..i
      if E.bindings[key]or E.reverse[id]then error('new connector edge already has a tracked identity',0)end
      created[id]=i
    end
    -- Pure street proposals are observed to return an empty resultEntities.
    -- If the engine does return IDs, require the complete same three-edge set.
    local returned=arr(need(field(result,'resultEntities'),'connector callback resultEntities absent'),3,'connector.resultEntities')
    local seen={}
    if #returned~=0 and #returned~=3 then error('connector callback entity count differs',0)end
    for _,id in ipairs(returned)do
      id=existing(id);if not created[id]or seen[id]then error('connector callback identities differ from exact incidence changes',0)end;seen[id]=true
    end
    -- Publish identities transactionally only after all reads and checks succeed.
    for id,i in pairs(created)do
      local key=plan.key..':link:'..i;local link=expected.links[i]
      E.bindings[key]={entity=id,kind='connector',node0=link.node0,node1=link.node1};E.reverse[id]=key
    end
    E.scene.connectors=plan.key
    return {success=true,result={logical_id=plan.key,links=3}}
  end
  local function vehicle_config(cfg,path)
    keep(cfg)
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
    if guided then guided.initialize()end
    if rail then rail.initialize()end
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
  function E.callback_diagnostics()return callback_report end
  function E.preflight_diagnostics()return preflight_report end
  function E.plan(c,key,time_us)
    if rail and c.op=='RAIL_ACTION'then return rail.plan(c,key,time_us)end
    if guided and not rail_mode and c.op=='GUIDED_ACTION'then return guided.plan(c,key,time_us)end
    if c.op=='BUILD_DEPOT'then
      local description,plan,reason=manual_preview(c,key)
      if not plan or not description.allowed then error('manual depot changed after approved preview: '..(reason or 'unavailable'),0)end
      return plan
    end
    if type(key)~='string'or not key:match('^[ab]:[1-9]%d*$')or E.bindings[key]or E.scene.connectors==key then error('invalid build key',0)end
    local op=need(c.op,'build op absent');local allowed={op=true};if op=='SET_PAUSED'then allowed.value=true elseif op=='PROBE_STOP'then allowed.index=true end
    for k in pairs(c)do if not allowed[k]then error('unexpected build command field',0)end end
    callback_report=nil;diagnostic_candidate=nil -- A new plan has no callback observation yet.
    local command,kind,index,connections
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
    elseif op=='PROBE_CONNECT'then
      command,connections=plan_connections(key);kind='connectors'
    elseif op=='PROBE_VEHICLE'then
      need(E.scene.stops[2],'stops not built');if E.scene.vehicle then error('vehicle already bought',0)end;kind='vehicle'
      need(E.scene.connectors,'connections not built')
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
    return {native=need(command,'build maker returned nil'),key=key,kind=kind,index=index,command=c,connections=connections}
  end
  function E.finish(plan,result,success)
    if plan.rail then return rail.finish(plan,result,success)end
    if plan.guided then return guided.finish(plan,result,success)end
    diagnostic_candidate=nil
    callback_report=nil
    -- This side channel must never replace the original callback result or an
    -- exception from verification, including a rejected engine command.
    local captured,diagnostic=pcall(capture_callback,plan,result,success)
    if captured then callback_report=diagnostic end
    if success~=true then return {success=false,result={error='engine_rejected',op=plan.command.op}}end
    if plan.kind=='connectors'then return finish_connections(plan,result)end
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
        local expected=plan.kind=='road'and assets.road_file or(plan.kind=='depot'or plan.kind=='manual_depot')and assets.depot_file or assets.stop_file
        if component(id,'CONSTRUCTION').fileName~=expected then error('callback construction differs from requested recipe',0)end
      end
      if plan.kind=='manual_depot'then
        local actual=component(id,'CONSTRUCTION')
        if json.encode(matrix(read(actual,'transf','manual.CONSTRUCTION')))~=json.encode(plan.expected_transform)
          or json.encode(canonical(read(actual,'params','manual.CONSTRUCTION')))~=json.encode(plan.expected_params)
          or read(component(id,'NAME'),'name','manual.NAME')~='TF2 Coop Depot '..plan.key then
          error('manual depot callback pose/params/name differs from approved proposal',0)
        end
        local children=arr(read(actual,'depots','manual.CONSTRUCTION'),1,'manual.CONSTRUCTION.depots')
        if #children~=1 or int(read(component(children[1],'VEHICLE_DEPOT'),'carrier','manual.VEHICLE_DEPOT'))~=0 then error('manual depot lacks its exact road depot child',0)end
        local account=need(game.interface.getEntity(api.engine.util.getPlayer()),'manual company unavailable')
        local balance=int(read(account,'balance','manual.company'));local loan=int(read(account,'loan','manual.company'),0)
        if balance~=plan.before_balance-plan.preview.cost or loan~=plan.before_loan then error('manual depot actual debit differs from approved cost',0)end
        bind(plan.key,'manual_depot',id)
        bind(plan.key..':depot','manual_depot_child',children[1],children[1]==id and plan.key or nil)
        local outcome={op='BUILD_DEPOT',site=plan.command.site,rotation=plan.command.rotation,
          logical_id=plan.key,cost=plan.preview.cost,balance_before=plan.before_balance,balance_after=balance,
          loan_before=plan.before_loan,loan_after=loan,position_mm=plan.preview.position_mm}
        placements[plan.key]=clone(outcome)
        return {success=true,result=outcome,result_entity=id}
      end
      bind(plan.key,plan.kind,id)
      if guided and plan.kind=='vehicle'then guided.register_vehicle_name(plan.key,id)end
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
      if b.kind=='road'or b.kind=='depot'or b.kind=='stop'or b.kind=='manual_depot'then
        local ok,err=pcall(edges_for,key,b.entity);if not ok then missing[#missing+1]=key..':'..safe_error(err)end
      end
    end
    local connector_count=0
    for _,key in ipairs(keys)do local b=E.bindings[key]
      if b.kind=='connector'then
        local ok,err=pcall(function()
          local e=edge_values(b.entity,key)
          if not ((e.node0==b.node0 and e.node1==b.node1)or(e.node0==b.node1 and e.node1==b.node0))then
            error('tracked connector endpoint identities changed',0)
          end
          if not node_names[e.node0]or not node_names[e.node1]then error('connector leaves owned construction graph',0)end
          if e.street~=assets.street_type or e.type~=0 or e.type_index~=-1 or e.has_bus or e.tram_track~=0 then error('tracked connector street recipe changed',0)end
          graph[e.node0]=graph[e.node0]or{};graph[e.node1]=graph[e.node1]or{}
          graph[e.node0][e.node1]=true;graph[e.node1][e.node0]=true
          connector_count=connector_count+1
        end)
        if not ok then missing[#missing+1]=key..':'..safe_error(err)end
      end
    end
    local function road_edge(id,path)
      local e=edge_values(id,path)
      e.node0=need(node_names[e.node0],'missing node identity');e.node1=need(node_names[e.node1],'missing node identity')
      return e
    end
    local probe={profile='build_v2',site=clone(site.description),scene={stops=json.array()}}
    if manual then
      local placed=json.array();for _,key in ipairs(keys)do if placements[key]then placed[#placed+1]=clone(placements[key])end end
      probe.manual_depot={contract=manual_assets.contract,placements=placed,site_offsets=clone(manual_assets.sites)}
    end
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
    for _,name in ipairs({'road','depot','connectors','vehicle','line'})do probe.scene[name]=E.scene[name]end
    for i=1,2 do probe.scene.stops[i]=E.scene.stops[i]end
    local function state(key,b)
      if rail and rail.owns(b.kind)then return rail.state(key,b)end
      local id=existing(b.entity)
      if b.kind=='road'or b.kind=='depot'or b.kind=='stop'or b.kind=='manual_depot'then
        local p=key..'.CONSTRUCTION';local c=component(id,'CONSTRUCTION');local edges=json.array()
        for i,edge in ipairs(arr(read(c,'frozenEdges',p),128,p..'.frozenEdges'))do edges[#edges+1]=road_edge(int(edge,1,nil,p..'.frozenEdges['..i..']'),key..'.roads['..i..']')end
        table.sort(edges,function(a,z)return json.encode(a)<json.encode(z)end)
        return {file=c.fileName,params=canonical(c.params),transform=matrix(read(c,'transf',p),p..'.transf'),time_build=optional_numeric(c,'timeBuild',p,false,false),
          name=component(id,'NAME').name,roads=edges}
      elseif b.kind=='connector'then return road_edge(id,key)
      elseif b.kind=='depot_child'or b.kind=='manual_depot_child'then
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
        for i,s in ipairs(arr(read(l,'stops',p),guided_mode and 8 or 2,p..'.stops'))do
          local sp=p..'.stops['..i..']'
          local group=int(read(s,'stationGroup',sp),1,nil,sp..'.stationGroup')
          stops[i]=need(E.groups[group],'unknown line station group at '..sp..'.stationGroup')
          details[i]={stop=stops[i],station=int(read(s,'station',sp),nil,nil,sp..'.station'),terminal=int(read(s,'terminal',sp),nil,nil,sp..'.terminal'),
            load_mode=int(read(s,'loadMode',sp),nil,nil,sp..'.loadMode'),min_wait=dec(read(s,'minWaitingTime',sp),sp..'.minWaitingTime'),max_wait=dec(read(s,'maxWaitingTime',sp),sp..'.maxWaitingTime')}
        end
        for i,v in ipairs(entity_collection(api.engine.system.transportVehicleSystem.getLineVehicles(id),guided_mode and 4 or 1,p..'.getLineVehicles','line vehicle membership'))do vehicles[#vehicles+1]=reference(v,p..'.getLineVehicles['..i..']')end;table.sort(vehicles)
        if not guided_mode or key==E.scene.line then probe.line={logical_id=key,stops=stops,vehicles=vehicles}end
        local out={stops=details,vehicles=vehicles,name=component(id,'NAME').name,color=vector(read(component(id,'COLOR'),'color',key..'.COLOR'),3,key..'.COLOR.color')}
        return out
      elseif b.kind=='vehicle'then
        local v=component(id,'TRANSPORT_VEHICLE');local p=key..'.TRANSPORT_VEHICLE'
        local state_value=int(read(v,'state',p),nil,nil,p..'.state')
        local parked=state_value==int(api.type.enum.TransportVehicleState.IN_DEPOT,nil,nil,'api.type.enum.TransportVehicleState.IN_DEPOT')
        local line_ref=reference(read(v,'line',p),p..'.line')
        local out={config=vehicle_config(read(v,'transportVehicleConfig',p),p..'.transportVehicleConfig'),line=line_ref,
          depot=reference(read(v,'depot',p),p..'.depot'),state=state_value,
          user_stopped=boolean(read(v,'userStopped',p),p..'.userStopped'),no_path=boolean(read(v,'noPath',p),p..'.noPath'),
          stop_index=optional_numeric(v,'stopIndex',p,true,line_ref~=''),carrier=int(read(v,'carrier',p),nil,nil,p..'.carrier')}
        if guided_mode then
          out.name=guided.observe_vehicle_name(key,id)
        end
        local vehicle_probe={logical_id=key,line=out.line,in_depot=parked,state=out.state,no_path=out.no_path}
        if not guided_mode or key==E.scene.vehicle then probe.vehicle=vehicle_probe end
        if parked then out.position='in_depot' else
          -- Assignment can change state before first world placement. Record
          -- observed absence; final proof still requires real changed positions.
          local data=game.interface.getEntity(id);local position=data and field(data,'position')
          out.world_position_present=position~=nil;vehicle_probe.world_position_present=position~=nil
          if position then
            out.position=vector(position,3,key..'.game.interface.getEntity.position')
            local mm=json.array();for i=1,3 do mm[i]=int(math.floor(num(out.position[i],key..'.position['..i..']')*1000+.5),nil,nil,key..'.position_mm['..i..']')end;vehicle_probe.position_mm=mm
          end
          local move=keep(api.engine.getComponent(id,api.type.ComponentType.MOVE_PATH));out.move_path_present=move~=nil
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
      local connected=E.scene.connectors~=nil and connector_count==3
      for _,key in ipairs({E.scene.road,E.scene.depot,E.scene.stops[1],E.scene.stops[2]})do if not visited[anchors[key]or -1]then connected=false end end
      probe.connectivity={connected=connected}
    end
    local account=need(game.interface.getEntity(api.engine.util.getPlayer()),'company unavailable')
    table.sort(observed_unavailable)
    local time=read(game.interface.getGameTime(),'time','game.interface.getGameTime')
    local snapshot={sim_time_us=int(math.floor(num(time,'game.interface.getGameTime.time')*1000000+.5),0,nil,'sim_time_us'),paused=num(game.interface.getGameSpeed(),'game.interface.getGameSpeed')==0,
      company={balance=int(read(account,'balance','company'),nil,nil,'company.balance'),loan=int(read(account,'loan','company'),0,nil,'company.loan')},objects=objects,probe=probe,
      coverage={complete_world=false,tracked_objects=true,missing=missing,observed_unavailable=observed_unavailable,
        excluded=json.array({'untracked_world','cargo_contents','rng','path_reservations','terrain_outside_test','station_internals','movement_before_world_placement'})}}
    if guided then guided.observe(snapshot)end
    if rail then rail.observe(snapshot)end
    return snapshot
  end
  if guided_mode then
    guided=require('tf2_strict_probe/guided_engine').new(json,E,{
      need=need,field=field,read=read,num=num,int=int,dec=dec,boolean=boolean,arr=arr,
      vector=vector,clone=clone,component=component,existing=existing,bind=bind,
      localid=localid,reference=reference,vehicle_config=vehicle_config,
      vehicle_model=function()return site.vehicle_model end,
      entity_collection=entity_collection,capture_callback=capture_callback,
      remember_callback=function(report)callback_report=report end,
    })
    function E.finish_read_only(plan)
      if rail and plan.rail then return rail.finish_read_only(plan)end
      return guided.finish_read_only(plan)
    end
  end
  if rail_mode then
    rail=require('tf2_strict_probe/rail_engine').new(json,E,{
      need=need,field=field,read=read,num=num,int=int,dec=dec,boolean=boolean,arr=arr,
      vector=vector,clone=clone,component=component,existing=existing,bind=bind,
      localid=localid,reference=reference,resource=resource,canonical=canonical,matrix=matrix,
      context=context,terrain_water=terrain_water,site=function()return site end,
      entity_collection=entity_collection,capture_callback=capture_callback,
      remember_callback=function(report)callback_report=report end,
    })
  end
  E.integer=int
  for _,name in ipairs({'bind_initial','plan','finish','snapshot','preview'})do
    local fn=E[name]
    E[name]=function(...)return operation(fn,...)end
  end
  if E.finish_read_only then local fn=E.finish_read_only;E.finish_read_only=function(...)return operation(fn,...)end end
  return E
end
return M
