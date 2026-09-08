-- Guided fixed road-vehicle lifecycle. No arbitrary UI interception. Each
-- mutation uses one real API command and its actual callback; observation
-- steps have a separate completion path with no synthetic native callback.
local assets=require 'tf2_strict_probe/guided_assets'
local M={}
function M.new(json,E,H)
  local G={completed=0,vehicle='',line='',removed={}}
  local need,read,field,int,arr=H.need,H.read,H.field,H.int,H.arr
  local function same(a,b)return json.encode(a)==json.encode(b)end
  local function fail(message)error('guided suite: '..message,0)end
  local function expect(value,message)if not value then fail(message)end end
  local function plain(v)return json.decode(json.encode(v))end
  local function component(key,kind)return H.component(H.localid(key),kind)end
  local function object(snapshot,key)
    for _,value in ipairs(snapshot.objects)do if value.logical_id==key then return value.state end end
    fail('tracked object absent: '..key)
  end
  local function observe_world()
    local snapshot=E.snapshot()
    expect(#snapshot.coverage.missing==0,'tracked observation unavailable')
    return snapshot
  end
  local function request(c,key)
    expect(type(c)=='table'and c.op=='GUIDED_ACTION','invalid action')
    for k in pairs(c)do expect(k=='op'or k=='step','unexpected action field')end
    local step=int(c.step,1,#assets.actions,'guided.step')
    expect(step==G.completed+1,'action is not the next shared step')
    local role,seq
    -- Do not use and/or to forward multiple Lua returns.
    if type(key)=='string'then role,seq=key:match('^([ab]):([1-9]%d*)$')end
    expect(role==assets.roles[step]and seq~=nil and #key<=96,'wrong actor or command identity')
    expect(E.bindings[key]==nil,'reused live object identity')
    return step,assets.actions[step]
  end
  local function capability_report()
    local missing=json.array()
    local function callable(value)
      if type(value)=='function'then return true end
      if type(value)~='table'and type(value)~='userdata'then return false end
      -- TF2 exposes command makers as tables with a native __call function.
      -- Inspect that actual metamethod without constructing or sending a
      -- command. Merely being a table, or exposing an __index fallback named
      -- __call, is insufficient. An opaque/missing metatable stays unverified.
      local ok,mt=pcall(getmetatable,value)
      return ok and type(mt)=='table'and type(rawget(mt,'__call'))=='function'
    end
    local function check(label,fn)
      local ok,result=pcall(fn)
      if not ok or result~=true then missing[#missing+1]=label end
    end
    for _,name in ipairs(assets.required_makers)do
      check('api.cmd.make.'..name,function()return callable(field(api.cmd.make,name))end)
    end
    for _,name in ipairs({'VehiclePart','TransportVehiclePart','TransportVehicleConfig','Line','Vec3f'})do
      check('api.type.'..name..'.new',function()return callable(field(api.type[name],'new'))end)
    end
    check('api.type.Line.Stop.new',function()return callable(field(api.type.Line.Stop,'new'))end)
    check('Line mutable stops and wait fields',function()
      local line=api.type.Line.new();line.waitingTime=0
      local stop=api.type.Line.Stop.new();stop.stationGroup=1;stop.station=0;stop.terminal=0
      stop.loadMode=0;stop.minWaitingTime=0;stop.maxWaitingTime=10
      local values=read(line,'stops','guided.preflight.Line');values[1]=stop;line.stops=values
      local observed=arr(read(line,'stops','guided.preflight.Line'),8,'guided.preflight.Line.stops')
      return #observed==1 and int(read(observed[1],'maxWaitingTime','guided.preflight.Stop'))==10
    end)
    table.sort(missing)
    return {ready=#missing==0,missing=missing,blocked_chapters=plain(assets.blocked_chapters)}
  end
  function G.initialize()
    G.capabilities=capability_report()
    if not G.capabilities.ready then
      fail('capability preflight missing: '..table.concat(G.capabilities.missing,'; '))
    end
  end
  function G.observe(snapshot)
    -- Sample only observed coordinates at a real simulation time. Repeated
    -- snapshots/previews at one frontier reproduce the same certificate and
    -- cannot create displacement. This is measurement history, not animation
    -- speed or a requested destination masquerading as actual movement.
    if G.vehicle~=''and #snapshot.coverage.missing==0 then
      for _,item in ipairs(snapshot.objects)do if item.logical_id==G.vehicle then
        local v=item.state
        if v.world_position_present==true and type(v.position)=='table'then
          local point=json.array()
          for i=1,3 do point[i]=int(math.floor(H.num(v.position[i],'guided.motion.position')*1000+.5))end
          if not G.motion then G.motion={time_us=snapshot.sim_time_us,position_mm=point}end
          expect(snapshot.sim_time_us>=G.motion.time_us,'motion observation moved backwards in time')
          local changed=not same(point,G.motion.position_mm)
          v.guided_motion={first_time_us=G.motion.time_us,first_position_mm=plain(G.motion.position_mm),
            observed_time_us=snapshot.sim_time_us,observed_position_mm=point,
            displacement_observed=changed and snapshot.sim_time_us>G.motion.time_us}
        end
      end end
    end
    snapshot.probe.guided_suite={contract=assets.contract,
      vehicle=G.vehicle,line=G.line,capabilities=plain(need(G.capabilities,'guided capabilities absent'))}
  end
  local function state_for(snapshot,key)
    return key~=''and object(snapshot,key)or nil
  end
  local function expected(action,snapshot)
    local out={target='',cost_scope='actual_callback_debit',required_effect=action}
    if action=='PAUSE'or action=='RESUME'then out.paused=action=='PAUSE'
    elseif action=='BUY_BUS'then
      out.model=H.vehicle_model();out.depot=need(E.scene.depot,'guided road depot not prepared')..':depot'
      out.creates='vehicle'
    elseif action=='CREATE_LINE'then out.creates='line';out.stops=json.array()
    elseif action=='VERIFY_DEPOT'or action=='SELL_BUS'or action=='VERIFY_MOVEMENT'
      or action=='STOP_BUS'or action=='START_BUS'or action=='REVERSE_BUS'
      or action=='SEND_DEPOT'or action=='RENAME_BUS'or action=='MAINTENANCE'or action=='ASSIGN_BUS'then
      out.target=G.vehicle;expect(out.target~='','guided bus not created')
      if action=='RENAME_BUS'then out.name=assets.vehicle_name
      elseif action=='MAINTENANCE'then out.target_maintenance='1'
      elseif action=='ASSIGN_BUS'then out.line=G.line;out.stop_index=0
      elseif action=='STOP_BUS'or action=='START_BUS'then out.user_stopped=action=='STOP_BUS'
      elseif action=='VERIFY_DEPOT'then out.depot=E.scene.depot..':depot'
      elseif action=='SEND_DEPOT'then out.sell_on_arrival=false
      end
    else
      out.target=G.line;expect(out.target~='','guided line not created')
      if action=='RENAME_LINE'then out.name=assets.renamed_line
      elseif action=='COLOR_LINE'then out.color={'0.75','0.25','0.5'}
      elseif action=='ADD_STOP_A'or action=='REMOVE_STOP_B'then out.stops={E.scene.stops[1]}
      elseif action=='ADD_STOP_B'or action=='RESTORE_STOP_B'or action=='RESTORE_STOPS'then out.stops={E.scene.stops[1],E.scene.stops[2]}
      elseif action=='REVERSE_STOPS'then out.stops={E.scene.stops[2],E.scene.stops[1]}
      elseif action=='LINE_RULES'then out.stops={E.scene.stops[1],E.scene.stops[2]};out.min_wait='0';out.max_wait='10';out.load_mode=1
      end
    end
    return out
  end
  function G.preview(c,key)
    local step,action=request(c,key)
    local snapshot=observe_world()
    local ex=expected(action,snapshot)
    local allowed,reason=true,''
    local v=state_for(snapshot,G.vehicle)
    if action=='VERIFY_MOVEMENT'then
      allowed=v~=nil and v.position~='in_depot'and v.world_position_present==true and v.no_path==false
        and v.movement~=nil and tonumber(v.movement.speed)>0
        and v.guided_motion~=nil and v.guided_motion.displacement_observed==true
      reason=allowed and ''or 'not_ready'
    elseif action=='VERIFY_DEPOT'then
      allowed=v~=nil and v.position=='in_depot'and v.depot==E.scene.depot..':depot'
      reason=allowed and ''or 'not_ready'
    elseif action=='SELL_BUS'then
      expect(v.position=='in_depot','sale requires the observed returned bus')
    elseif action=='DELETE_LINE'then
      expect(#object(snapshot,G.line).vehicles==0,'line still has assigned vehicles')
    elseif action=='BUY_BUS'then
      expect(G.vehicle=='','guided bus already exists')
      expect(snapshot.company.balance>0,'no money for a vehicle')
    elseif action=='CREATE_LINE'then expect(G.line=='','guided line already exists')end
    return {contract=assets.contract,step=step,action=action,allowed=allowed,reason=reason,
      observation={company=plain(snapshot.company),expected=ex,
        target=ex.target~=''and plain(object(snapshot,ex.target))or {},
        capabilities=plain(G.capabilities)}}
  end
  local function vehicle_config(time_us)
    local part=api.type.VehiclePart.new()
    part.modelId=int(api.res.modelRep.find(H.vehicle_model()),0)
    part.reversed=false;part.color=api.type.Vec3f.new(-1,-1,-1);part.logo=''
    local load=part.loadConfig;load[1]=0;part.loadConfig=load
    local vehicle=api.type.TransportVehiclePart.new();vehicle.part=part
    vehicle.purchaseTime=int(time_us/1000,1);vehicle.maintenanceState=1;vehicle.targetMaintenanceState=0
    local auto=vehicle.autoLoadConfig;auto[1]=1;vehicle.autoLoadConfig=auto
    local cfg=api.type.TransportVehicleConfig.new()
    local vehicles=cfg.vehicles;vehicles[1]=vehicle;cfg.vehicles=vehicles
    local groups=cfg.vehicleGroups;groups[1]=1;cfg.vehicleGroups=groups
    expect(H.vehicle_config(cfg).vehicles[1].model==H.vehicle_model(),'vehicle config readback differs')
    return cfg
  end
  local function line_recipe(stop_keys,rules)
    local line=api.type.Line.new();line.waitingTime=0
    local stops=read(line,'stops','guided.Line')
    for i,key in ipairs(stop_keys)do
      local s=api.type.Line.Stop.new()
      s.stationGroup=H.localid(key..':group');s.station=0;s.terminal=0;s.loadMode=rules and 1 or 0
      s.minWaitingTime=0;s.maxWaitingTime=rules and 10 or 0
      expect(#arr(read(component(key..':station','STATION'),'terminals','guided.STATION'),16)>=1,'station terminal absent')
      stops[i]=s
    end
    line.stops=stops
    expect(#arr(line.stops,8)==#stop_keys,'line stop writeback differs')
    return line
  end
  function G.plan(c,key,time_us)
    local preview=G.preview(c,key);expect(preview.allowed,'action not ready')
    local step,action=preview.step,preview.action
    local before=observe_world()
    local plan={guided=true,key=key,command=plain(c),preview=preview,
      action=action,before=before,expected=preview.observation.expected}
    local make=api.cmd.make;local native
    local function vid()return H.localid(G.vehicle)end
    local function lid()return H.localid(G.line)end
    if action=='VERIFY_MOVEMENT'or action=='VERIFY_DEPOT'then plan.read_only=true;return plan
    elseif action=='PAUSE'or action=='RESUME'then
      plan.requested_paused=action=='PAUSE';native=make.setGameSpeed(plan.requested_paused and 0 or 1)
    elseif action=='BUY_BUS'then native=make.buyVehicle(api.engine.util.getPlayer(),H.localid(E.scene.depot..':depot'),vehicle_config(time_us))
    elseif action=='CREATE_LINE'then
      native=make.createLine(assets.line_name,api.type.Vec3f.new(assets.initial_color[1],assets.initial_color[2],assets.initial_color[3]),api.engine.util.getPlayer(),line_recipe({}))
    elseif action=='ADD_STOP_A'or action=='ADD_STOP_B'or action=='REMOVE_STOP_B'or action=='RESTORE_STOP_B'
      or action=='REVERSE_STOPS'or action=='RESTORE_STOPS'or action=='LINE_RULES'then
      native=make.updateLine(lid(),line_recipe(plan.expected.stops,action=='LINE_RULES'))
    elseif action=='RENAME_LINE'then native=make.setName(lid(),assets.renamed_line)
    elseif action=='COLOR_LINE'then native=make.setColor(lid(),api.type.Vec3f.new(assets.line_color[1],assets.line_color[2],assets.line_color[3]))
    elseif action=='RENAME_BUS'then native=make.setName(vid(),assets.vehicle_name)
    elseif action=='MAINTENANCE'then native=make.setVehicleTargetMaintenanceState(vid(),1)
    elseif action=='ASSIGN_BUS'then
      expect(#object(before,G.line).stops==2,'assignment requires two confirmed stops')
      native=make.setLine(vid(),lid(),0)
    elseif action=='STOP_BUS'or action=='START_BUS'then native=make.setUserStopped(vid(),action=='STOP_BUS')
    elseif action=='REVERSE_BUS'then native=make.reverseVehicle(vid())
    elseif action=='SEND_DEPOT'then native=make.sendToDepot(vid(),false)
    elseif action=='SELL_BUS'then plan.removed_id=vid();plan.removed_key=G.vehicle;native=make.sellVehicle(vid())
    elseif action=='DELETE_LINE'then plan.removed_id=lid();plan.removed_key=G.line;native=make.deleteLine(lid())
    else fail('unimplemented action')end
    plan.native=need(native,'guided command maker returned no command')
    return plan
  end
  local function actual_entity(result)
    local entity
    for _,name in ipairs({'resultEntity','resultVehicleEntity'})do
      local value=field(result,name)
      if value~=nil then
        local id=tonumber(value)
        if id and id>0 then expect(entity==nil or entity==id,'ambiguous created callback identity');entity=int(id,1)end
      end
    end
    return H.existing(need(entity,'guided successful callback has no created entity'))
  end
  local function remove_binding(plan)
    expect(api.engine.entityExists(plan.removed_id)==false,'deleted entity still exists after callback')
    expect(E.bindings[plan.removed_key]and E.bindings[plan.removed_key].entity==plan.removed_id,'deleted logical identity changed')
    E.bindings[plan.removed_key]=nil;E.reverse[plan.removed_id]=nil
  end
  local function observed_effect(plan,kind)
    local action=plan.action
    local after=observe_world();local before=plan.before
    expect(after.sim_time_us==before.sim_time_us,'command advanced simulation time')
    local target=plan.expected.target
    local result={balance_before=before.company.balance,balance_after=after.company.balance,
      loan_before=before.company.loan,loan_after=after.company.loan,
      target=target,created=json.array(),removed=json.array(),observed={},kind=kind}
    expect(after.company.loan==before.company.loan,'command changed company loan')
    if action=='BUY_BUS'then
      result.created[1]=G.vehicle;result.target=G.vehicle
      result.observed=plain(object(after,G.vehicle))
      expect(before.company.balance>after.company.balance and after.company.balance>=0,'vehicle purchase has no valid actual debit')
      expect(result.observed.config.vehicles[1].model==H.vehicle_model()and result.observed.carrier==0
        and result.observed.position=='in_depot'and result.observed.depot==E.scene.depot..':depot','bought bus differs from fixed recipe')
    elseif action=='SELL_BUS'then
      result.removed[1]=plan.removed_key;result.observed={entity_absent=true}
      expect(after.company.balance>=before.company.balance,'vehicle sale debited money')
    else expect(after.company.balance==before.company.balance,'no-cost guided action changed money')end
    if action=='CREATE_LINE'then
      result.created[1]=G.line;result.target=G.line;result.observed=plain(object(after,G.line))
      expect(#result.observed.stops==0 and #result.observed.vehicles==0 and result.observed.name==assets.line_name,'new line differs')
    elseif action=='DELETE_LINE'then result.removed[1]=plan.removed_key;result.observed={entity_absent=true}
    elseif action=='PAUSE'or action=='RESUME'then
      result.observed={paused=after.paused};expect(after.paused==plan.requested_paused,'pause not applied')
    elseif action~='BUY_BUS'and action~='SELL_BUS'then
      result.observed=plain(object(after,target))
      local actual=result.observed
      if action=='RENAME_LINE'or action=='RENAME_BUS'then expect(actual.name==plan.expected.name,'name readback differs')
      elseif action=='COLOR_LINE'then expect(same(actual.color,plan.expected.color),'line color readback differs')
      elseif action=='MAINTENANCE'then expect(actual.config.vehicles[1].target_maintenance=='1','maintenance readback differs')
      elseif action=='ASSIGN_BUS'then
        expect(actual.line==G.line and actual.stop_index.available and actual.stop_index.value==0,'vehicle assignment readback differs')
        expect(same(object(after,G.line).vehicles,{G.vehicle}),'line actual vehicle membership differs')
      elseif action=='STOP_BUS'or action=='START_BUS'then expect(actual.user_stopped==plan.expected.user_stopped,'user-stopped readback differs')
      elseif action=='VERIFY_MOVEMENT'then
        expect(actual.position~='in_depot'and actual.world_position_present and actual.no_path==false
          and actual.movement and tonumber(actual.movement.speed)>0
          and actual.guided_motion and actual.guided_motion.displacement_observed==true,'displacement not observed')
      elseif action=='VERIFY_DEPOT'then expect(actual.position=='in_depot'and actual.depot==plan.expected.depot,'depot return not observed')
      elseif action=='REVERSE_BUS'then
        local previous=object(before,target)
        expect(not same(actual.stop_index,previous.stop_index)or actual.state~=previous.state
          or not same(actual.movement,previous.movement),'reverse command has no observed route/state change')
        expect(actual.no_path==false,'reverse command left no path')
      elseif action=='SEND_DEPOT'then
        -- TransportVehicle.depot is documented only for IN_DEPOT. Arrival is
        -- independently required by the next observation step.
        expect(actual.line==''or actual.state~=object(before,target).state,'depot request has no observed assignment/state change')
      elseif plan.expected.stops then
        expect(#actual.stops==#plan.expected.stops,'line stop count differs')
        for i,key in ipairs(plan.expected.stops)do
          local stop=actual.stops[i]
          expect(stop.stop==key and stop.station==0 and stop.terminal==0 and stop.load_mode==(action=='LINE_RULES'and 1 or 0)
            and stop.min_wait=='0'and stop.max_wait==(action=='LINE_RULES'and '10'or '0'),'line stop occurrence/rules readback differs')
        end
      end
    end
    if action~='PAUSE'and action~='RESUME'then expect(after.paused==before.paused,'action changed pause')end
    if kind=='observation'then expect(same(after,before),'observation completion changed tracked world')end
    return result
  end
  local function finish(plan,kind)
    local effect=observed_effect(plan,kind)
    G.completed=plan.command.step
    return {success=true,result={op='GUIDED_ACTION',step=plan.command.step,action=plan.action,
      command_key=plan.key,effect=effect}}
  end
  function G.finish(plan,result,success)
    expect(plan.guided==true and not plan.read_only,'wrong guided mutation completion path')
    local ok,report=pcall(H.capture_callback,plan,result,success);if ok then H.remember_callback(report)end
    if success~=true then return {success=false,result={error='engine_rejected',op='GUIDED_ACTION',step=plan.command.step}}end
    if plan.action=='BUY_BUS'then
      local id=actual_entity(result);H.component(id,'TRANSPORT_VEHICLE')
      H.bind(plan.key,'vehicle',id);G.vehicle=plan.key;G.motion=nil
    elseif plan.action=='CREATE_LINE'then
      local id=actual_entity(result);H.component(id,'LINE')
      H.bind(plan.key,'line',id);G.line=plan.key
    elseif plan.action=='SELL_BUS'then remove_binding(plan);G.vehicle=''
    elseif plan.action=='DELETE_LINE'then remove_binding(plan);G.line=''end
    return finish(plan,'callback')
  end
  function G.finish_read_only(plan)
    expect(plan.guided==true and plan.read_only==true and plan.native==nil,'wrong observation completion path')
    expect(plan.action=='VERIFY_MOVEMENT'or plan.action=='VERIFY_DEPOT','unsupported observation completion')
    return finish(plan,'observation')
  end
  return G
end
return M
