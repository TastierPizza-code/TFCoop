-- Test doubles for documented engine surfaces. This is never shipped as game code.
files={}; writes=0; reads=0; sends={}; callbacks={}; sync_callback=false; write_fail=false
local function copy(v) if type(v)~='table' then return v end; local o={};for k,x in pairs(v)do o[k]=copy(x)end;return o end
world={}; legacy={}; now=100; speed=1; company={balance=4480019,loan=500000}
local function v3(x,y,z)return{x=x,y=y,z=z}end
local function id(n)return n+(id_offset or 0)end
identity={1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}
local cfg={vehicles={{part={modelId=7,reversed=true,loadConfig={2,4},color=v3(.1,.2,.3),logo='saved_logo'},
 purchaseTime=123,maintenanceState=.75,targetMaintenanceState=.8,autoLoadConfig={1,0}}},vehicleGroups={1}}
function add_vehicle(n,depot,line)
 world[n]={TRANSPORT_VEHICLE={carrier=0,state=0,userStopped=true,depot=depot,sellOnArrival=false,line=line or -1,stopIndex=0,config={capacities={23,0}},
 arrivalStationTerminal={station=0,terminal=0},arrivalStationTerminalLocked=false,timeUntilLoad=0,timeUntilCloseDoors=0,timeUntilDeparture=0,
 noPath=false,daysInDepot=3,daysAtTerminal=0,doorsOpen=false,doorsTime=0,autoDeparture=false,transportVehicleConfig=copy(cfg)}}
 legacy[n]={}
end
function add_depot(n,child,params,transform,name)
 world[n]={CONSTRUCTION={fileName='actual/fixture_depot.con',params=copy(params or {seed=927,module={actual='saved'}}),
 transf=copy(transform or identity),timeBuild=10,depots={child},frozenEdges={}},NAME={name=name or 'Source Depot'}}
 world[child]={VEHICLE_DEPOT={carrier=0,state=0,doors=0,stateTime=0}}
end
function add_road(n,node0,node1,a,b)
 world[node0]={BASE_NODE={position=a or v3(0,0,0)}};world[node1]={BASE_NODE={position=b or v3(10,0,0)}}
 world[n]={BASE_EDGE={node0=node0,node1=node1,tangent0=v3(10,0,0),tangent1=v3(10,0,0),type=0,typeIndex=-1},
 BASE_EDGE_STREET={streetType=8,hasBus=false,tramTrackType=0}}
end
add_depot(id(100),id(101));add_vehicle(id(200),id(101));add_road(id(500),id(501),id(502))
world[id(300)]={LINE={waitingTime=180,stops={{stationGroup=id(400),station=0,terminal=0,loadMode=0,minWaitingTime=0,maxWaitingTime=180,alternativeTerminals={},waypoints={}}}},NAME={name='Source Line'},COLOR={color=v3(.1,.2,.3)}}
world[id(400)]={STATION_GROUP={stations={id(401)}}};world[id(401)]={STATION={terminals={{}}}}
bindings={{logical_id='seed:depot',kind='depot',entity=id(100)},{logical_id='seed:vehicle',kind='vehicle',entity=id(200)},
 {logical_id='seed:line',kind='line',entity=id(300)},{logical_id='seed:group',kind='station_group',entity=id(400)},
 {logical_id='seed:road',kind='road',entity=id(500)}}
local function empty()return{}end
api={type={ComponentType=setmetatable({},{__index=function(_,k)return k end}),Vec3f={new=v3},Vec4f={new=function(x,y,z,w)return{x,y,z,w}end},
 Mat4f={new=function(a,b,c,d)local t={};for _,v in ipairs({a,b,c,d})do for i=1,4 do t[#t+1]=v[i] end end;return t end},
 Context={new=empty},Line={new=function()return{stops={}}end,Stop={new=function()return{alternativeTerminals={},waypoints={}}end}},
 SimpleProposal={new=function()return{streetProposal={nodesToAdd={},edgesToAdd={}},constructionsToAdd={}}end,ConstructionEntity={new=empty}},
 NodeAndEntity={new=function()return{comp={}}end},SegmentAndEntity={new=function()return{comp={}}end},BaseEdgeStreet={new=empty},
 TransportVehicleConfig={new=function()return{vehicles={},vehicleGroups={}}end},VehiclePart={new=function()return{loadConfig={}}end},
 TransportVehiclePart={new=function()return{autoLoadConfig={}}end},enum={TransportVehicleState={IN_DEPOT=0}}},
 engine={entityExists=function(n)return world[n]~=nil end,getComponent=function(n,kind)return world[n] and world[n][kind]end,
 util={getPlayer=function()return id(1)end},system={transportVehicleSystem={getLineVehicles=function(line)
  local a={};for n,obj in pairs(world)do if obj.TRANSPORT_VEHICLE and obj.TRANSPORT_VEHICLE.line==line then a[#a+1]=n end end;table.sort(a);return a end}}},
 res={modelRep={getName=function(n)if n==7 then return'actual/fixture_vehicle.mdl'end end,find=function(n)return n=='actual/fixture_vehicle.mdl' and 7 or -1 end},
 streetTypeRep={getName=function(n)if n==8 then return'actual/fixture_street.lua'end end,find=function(n)return n=='actual/fixture_street.lua' and 8 or -1 end}},cmd={make={}}}
game={interface={getEntity=function(n)if n==id(1)then return company end;return legacy[n]end,getGameTime=function()return{time=now}end,getGameSpeed=function()return speed end}}
api.cmd.make.setGameSpeed=function(v)return{op='pause',value=v}end
api.cmd.make.createLine=function(name,color,player,line)return{op='line',name=name,color=color,line=line,resultEntity=-1}end
api.cmd.make.updateLine=function(n,line)return{op='line_update',entity=n,line=line}end
api.cmd.make.setLine=function(n,line,stop)return{op='assign',entity=n,line=line,stop=stop}end
api.cmd.make.buyVehicle=function(player,depot,config)return{op='buy',depot=depot,config=config,resultVehicleEntity=-1}end
api.cmd.make.buildProposal=function(p,c,ignore)return{op=#p.constructionsToAdd>0 and'depot'or'road',proposal=p,context=c,ignore=ignore,resultEntities={}}end
function complete(index,n,success,no_result)
 local cmd=sends[index];local result={}
 if success then
  if cmd.op=='pause'then speed=cmd.value
  elseif cmd.op=='buy'then add_vehicle(n,cmd.depot);world[n].TRANSPORT_VEHICLE.transportVehicleConfig=copy(cmd.config);company.balance=company.balance-200;result.resultVehicleEntity=n
  elseif cmd.op=='line'then world[n]={LINE=copy(cmd.line),NAME={name=cmd.name},COLOR={color=copy(cmd.color)}};result.resultEntity=n
  elseif cmd.op=='line_update'then world[cmd.entity].LINE=copy(cmd.line)
  elseif cmd.op=='assign'then world[cmd.entity].TRANSPORT_VEHICLE.line=cmd.line;world[cmd.entity].TRANSPORT_VEHICLE.stopIndex=cmd.stop
  elseif cmd.op=='depot'then local p=cmd.proposal.constructionsToAdd[1];add_depot(n,n+1,p.params,p.transf,p.name);company.balance=company.balance-300;result.resultEntities={n}
  elseif cmd.op=='road'then local p=cmd.proposal.streetProposal;add_road(n,n+1,n+2,p.nodesToAdd[1].comp.position,p.nodesToAdd[2].comp.position);company.balance=company.balance-100;result.resultEntities={n,n+1,n+2}
  end
 end
 if no_result then result={}end
 callbacks[index](result,success)
end
api.cmd.sendCommand=function(cmd,callback)sends[#sends+1]=cmd;callbacks[#sends]=callback;if sync_callback then complete(#sends,id(900+#sends*10),true,false)end end
io={open=function(path,mode)
 if mode=='rb' then reads=reads+1;if files[path]==nil then return nil end;local pos=1
  return{read=function(_,n)local data=files[path]:sub(pos,pos+n-1);pos=pos+#data;return data end,close=function()return true end}
 end
 if write_fail then return nil end
 writes=writes+1;files[path]=''
 return{write=function(self,s)files[path]=files[path]..s;return self end,close=function()return true end}
end}
function native_status(frame,changes)
 local v={protocol=1,abi=3,native_step_us=200000,epoch=77,ready=1,initialized=1,armed=1,halted=0,fault=0,runtime_fault=0,
 probe_required=1,pending_state=0,completed_frame=frame or 0,win32_error=0}
 for k,x in pairs(changes or {})do v[k]=x end
 local a={};for k,x in pairs(v)do a[#a+1]=k..'='..x end;table.sort(a);files['C:/probe/native_status.txt']=table.concat(a,'\n')..'\n'
end
native_status(0)
