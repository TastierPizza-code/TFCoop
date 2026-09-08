-- Explicit game primitive fixture for production guided Lua integration.
-- It is a test model, never evidence of actual TF2 command semantics.
local function maker(op)
  return function(entity,value,extra)return{op=op,entity=entity,value=value,extra=extra}end
end
api.cmd.make.updateLine=maker('guided_update_line')
api.cmd.make.setName=maker('guided_name')
api.cmd.make.setColor=maker('guided_color')
api.cmd.make.setVehicleTargetMaintenanceState=maker('guided_maintenance')
api.cmd.make.setUserStopped=maker('guided_stopped')
api.cmd.make.reverseVehicle=maker('guided_reverse')
api.cmd.make.sendToDepot=maker('guided_depot')
api.cmd.make.sellVehicle=maker('guided_sell')
api.cmd.make.deleteLine=maker('guided_delete_line')
-- TF2's command makers are callable tables, as recorded by the existing
-- runtime probe in upstream docs/DEV_STATUS.md. Ordinary function fixtures
-- hid the guided preflight's false rejection of every real maker. Use that
-- API shape throughout the literal lifecycle and production file-IPC tests.
-- Counting factory invocations also detects a preflight that probes by call.
command_factory_calls=0
command_factory_functions={}
for name,fn in pairs(api.cmd.make)do
  assert(type(fn)=='function','fixture expected unwrapped command factory')
  command_factory_functions[name]=fn
  api.cmd.make[name]=setmetatable({},{__call=function(_,...)
    command_factory_calls=command_factory_calls+1
    return fn(...)
  end})
end
local original_apply=apply_command
function apply_command(command,no_result)
  local op=command.op
  if not op:match('^guided_')then
    local result=original_apply(command,no_result)
    if op=='buy'then world[vehicle_id].NAME={name='Bus'}end
    return result
  end
  sent=sent+1
  local entity=world[command.entity]
  assert(entity,'fixture command target missing')
  if op=='guided_update_line'then entity.LINE=command.value
  elseif op=='guided_name'then entity.NAME.name=command.value
  elseif op=='guided_color'then entity.COLOR.color=command.value
  elseif op=='guided_maintenance'then entity.TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].targetMaintenanceState=command.value
  elseif op=='guided_stopped'then entity.TRANSPORT_VEHICLE.userStopped=command.value
  elseif op=='guided_reverse'then entity.TRANSPORT_VEHICLE.stopIndex=1-entity.TRANSPORT_VEHICLE.stopIndex
  elseif op=='guided_depot'then
    entity.TRANSPORT_VEHICLE.line=-1;entity.TRANSPORT_VEHICLE.state=2
    entity.TRANSPORT_VEHICLE.sellOnArrival=command.value;entity.returning=true
  elseif op=='guided_sell'then world[command.entity]=nil;legacy[command.entity]=nil;money=money+900
  elseif op=='guided_delete_line'then world[command.entity]=nil
  else error('unsupported fixture command')end
  return no_result and{}or native_record({})
end
function advance()
  now=now+.2
  for id,entity in pairs(world)do
    local vehicle=entity.TRANSPORT_VEHICLE
    if vehicle then
      if entity.returning then
        vehicle.state=0;entity.returning=nil;legacy[id]=nil;entity.MOVE_PATH=nil
      elseif vehicle.line>0 then
        vehicle.state=1;legacy[id]={position={x=now,y=0,z=10}}
        entity.MOVE_PATH={dyn={speed=vehicle.userStopped and 0 or 4,pathPos={edgeIndex=0,pos=now,pos01=.1}}}
      end
    end
  end
end
