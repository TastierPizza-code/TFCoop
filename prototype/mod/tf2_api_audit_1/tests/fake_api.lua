-- Literal userdata; no type spoofing and no game process. Closed private
-- handles supply independently throwing native member access on Lua 5.1-5.4.
local original_pairs=pairs
if _VERSION=='Lua 5.1'then
  pairs=function(v)
    local mt=type(v)=='userdata'and getmetatable(v)or nil
    if mt and mt.__pairs then return mt.__pairs(v)end
    return original_pairs(v)
  end
end
function native(values,errors,members)
  local u=assert(io.tmpfile());assert(u:close())
  debug.setmetatable(u,{
    __index=function(_,k)
      if errors and errors[k]then error(errors[k],0)end
      if values[k]==nil then error('absent native member '..tostring(k),0)end
      return values[k]
    end,
    __len=function()return #values end,
    __members=members,
    __pairs=not members and function()return next,values,nil end or nil,
    __tostring=function()error('opaque object must never be stringified',0)end,
  })
  return u
end
function vec(...)return native({x=select(1,...),y=select(2,...),z=select(3,...),w=select(4,...)})end
function part()return native({modelId=4,reversed=false,logo='',color=vec(1,1,1),loadConfig=native({-1})})end
function vehicle_part()return native({part=part(),purchaseTime=13400,maintenanceState=1,targetMaintenanceState=0,autoLoadConfig=native({1})})end
function config()return native({vehicles=native({vehicle_part()}),vehicleGroups=native({1})})end
function stop()return native({stationGroup=80,station=0,terminal=0,loadMode=0,minWaitingTime=0,maxWaitingTime=0})end
function line()return native({stops=native({stop()}),waitingTime=0})end
sent,gets,enumerated,col_called=0,0,{},0
api={type={ComponentType={}},engine={},cmd=setmetatable({},{__index=function()sent=sent+1;error('game command access forbidden')end})}
for _,k in ipairs({'CONSTRUCTION','BASE_EDGE','BASE_EDGE_STREET','BASE_NODE','VEHICLE_DEPOT','LINE','TRANSPORT_VEHICLE','MOVE_PATH','STATION','STATION_GROUP','NAME','COLOR','TERRAIN'})do api.type.ComponentType[k]=k end
api.type.Vec2f={new=vec};api.type.Vec3f={new=vec};api.type.Vec4f={new=vec}
api.type.Mat4f={new=function(a,b,c,d)
  return native({[1]=a,[2]=b,[3]=c,[4]=d,col=function()col_called=col_called+1;error('col must not be invoked')end})
end}
api.type.VehiclePart={new=part};api.type.TransportVehiclePart={new=vehicle_part};api.type.TransportVehicleConfig={new=config}
api.type.Line={new=line,Stop={new=stop}}
transform=native({[1]=vec(1,0,0,0),[2]=vec(0,1,0,0),[3]=vec(0,0,1,0),[4]=vec(0,0,0,1)})
params=native({valid=3,bad=false,nested=native({x=true})},{bad='unreadable member 0x123456'}, {'valid','bad','nested'})
world={
  [1]={CONSTRUCTION=native({fileName='road.con',params=params,transf=transform,timeBuild=13400,
    frozenNodes=native({4}),frozenEdges=native({2}),depots=native({}),stations=native({})})},
  [2]={BASE_EDGE=native({node0=4,node1=4,type=0,typeIndex=-1,tangent0=vec(100,0,0),tangent1=vec(100,0,0)}),
    BASE_EDGE_STREET=native({streetType=2,hasBus=false,tramTrackType=0})},
  [4]={BASE_NODE=native({position=vec(0,0,10)})},
  [5]={VEHICLE_DEPOT=native({carrier=0,state=0,doors=0,stateTime=13400,inNodes=native({4}),outNodes=native({4})})},
  [6]={LINE=line(),NAME=native({name='test line'}),COLOR=native({color=vec(.1,.5,.9)})},
  [7]={TRANSPORT_VEHICLE=native({carrier=0,state=0,userStopped=false,noPath=false,line=6,depot=5,stopIndex=0,transportVehicleConfig=config()}),
    MOVE_PATH=native({dyn=native({speed=4,pathPos=native({edgeIndex=0,pos=1,pos01=.3})})})},
  [8]={STATION=native({cargo=false,terminals=native({native({})})})},
  [9]={STATION_GROUP=native({stations=native({8})})},
  [10]={TERRAIN=native({waterLevel=0})},
}
api.engine.getComponent=function(id,kind)gets=gets+1;return world[id]and world[id][kind]end
api.engine.forEachEntityWithComponent=function(callback,kind)
  enumerated[kind]=(enumerated[kind]or 0)+1
  for id,v in pairs(world)do if v[kind]~=nil then callback(id)end end
end
player_ready=true
api.engine.entityExists=function(id)return player_ready and id==100 or world[id]~=nil end
api.engine.util={getPlayer=function()return 100 end}
game={interface={getGameTime=function()return native({time=13.4})end,getGameSpeed=function()return 1 end,
  getEntity=function(id)
    if id==100 then if player_ready then return native({balance=5000000,loan=0})end;return nil end
    return native({position=vec(10,20,30)})
  end}}
