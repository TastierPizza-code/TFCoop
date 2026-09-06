-- Mock integration exercises the actual game script, not a reimplementation.
-- It does NOT establish game-native ABI compatibility or visual verification.
local json = require 'tf2coop/json'
local originalIO, originalOS, oldConfig = io, os, package.loaded['tf2coop/config']
local files, zones, controls, timer, epoch, forbidden = {}, {}, {}, nil, 100, 0
local cameraDistance = 500
package.loaded['tf2coop/config'] = { mailbox_dir = 'C:/mock-mailbox' }
io = { open = function(path, mode)
  if mode == 'rb' then
    if not files[path] then return nil end
    return { read = function(_, limit) return files[path]:sub(1, limit) end, close = function() return true end }
  end
  local text = ''
  return { write = function(_, value) text = text .. value; return true end, close = function() files[path] = text; return true end }
end }
os = { time = function() return epoch end,
  rename = function(from, to) if files[to] then return nil end; files[to], files[from] = files[from], nil; return true end,
  remove = function(path) files[path] = nil; return true end,
}
local function component(text)
  local c = { text = text, visible = true, children = {} }
  function c:setText(value) self.text = value end
  function c:setId(value) controls[value] = self end
  function c:addItem(value) self.children[#self.children+1] = value end
  function c:getLayout() return self.layout or self end
  function c:setLayout(value) self.layout = value end
  function c:setStyleClassList(value) self.styles = value end
  function c:setTooltip() end
  function c:setPosition() end
  function c:addHideOnCloseHandler() end
  function c:onClick(fn) self.click = fn end
  function c:onStep(fn) timer = fn end -- Valid void return must not disable timer.
  function c:setVisible(value) self.visible = value end
  function c:isVisible() return self.visible end
  function c:getMainRendererComponent() return {
    getTerrainPos = function() return { 1, 2, 3 } end,
    getCameraController = function() return { getCameraData = function() return { 0, 0, cameraDistance, 0, 0.7 } end } end,
  } end
  return c
end
local root = component()
api = { gui = { util = { getGameUI = function() return root end, getById = function() return root end },
  layout = { BoxLayout = { new = component } },
  comp = { TextView = { new = component }, Component = { new = function(name, ...)
    -- Build 35924's shipped selectortooltip.lua uses one argument + setId.
    -- Reproduce the observed binding rejecting our former second argument.
    assert(type(name) == 'string' and select('#', ...) == 0, 'Component.new accepts only its name')
    return component(name)
  end }, Button = { new = function(child, clickOnPress)
    assert(type(clickOnPress) == 'boolean', 'Button.new requires clickOnPress')
    return component(child)
  end }, Window = { new = component } },
}, cmd = { sendCommand = function() forbidden = forbidden + 1; error('MUST NOT MUTATE SIMULATION') end } }
game = { interface = { setZone = function(key, value) zones[key] = value end, getEntity = function() return {position={4,5,6}} end } }
local function incoming(connected)
  files['C:/mock-mailbox/peers.json'] = json.encode({protocol=1, written_at=epoch, connected=connected, local_peer_id='me', peers=json.array({
    { id='friend', name='Freund', color='#34d399', presence={cursor={10,20,30}, preview={kind='street', points={{0,0,0},{20,20,0}}}} }
  })})
end
local function update()
  timer(epoch * 1000000)
  script.guiUpdate()
end
dofile('mod/tf2coop_1/res/config/game_script/tf2coop.lua')
script = data()
incoming(true)
script.guiInit()
update()
local outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.protocol == 1 and outgoing.cursor[2] == 2)
assert(outgoing.capabilities.simulation_sync == false)
assert(outgoing.capabilities.gui_timer == true and outgoing.capabilities.gui_timer_registered == true)
assert(zones.tf2coop_peer_1_cursor and zones.tf2coop_peer_1_preview2)
assert(controls['tf2coop.window'] and controls['tf2coop.content'])
assert(outgoing.capabilities.peer_panel == true and not outgoing.capabilities.panel_error)
assert(outgoing.capabilities.camera_scaling == true)
assert(zones.tf2coop_peer_1_ring_edge_1 and zones.tf2coop_peer_1_outer_light_4)
assert(outgoing.status:match('1 Mitspieler'))
print('PASS actual game script reads mailbox and draws peer presence with void onStep return')

epoch = 101
script.guiHandleEvent('streetBuilder', 'builder.proposalCreate', { proposal = { proposal = {
  addedNodes={{entity=-1,comp={position={0,0,0}}}}, addedSegments={{comp={node0=-1,node1=10}}},
} } })
update()
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.preview.kind == 'street' and #outgoing.preview.points == 2)
script.guiHandleEvent('streetBuilder', 'builder.apply', {})
epoch = 102; update()
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.preview == json.null)
assert(forbidden == 0)
print('PASS actual game script publishes preview then clears on apply without commands')

epoch = 110; update()
assert(next(zones) == nil)
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.status:match('nicht verbunden'))
assert(script.save().version == 1 and script.save().peers == nil)
print('PASS actual game script expires markers and omits presence from saves')

incoming(true)
epoch = 111; update(); assert(next(zones))
incoming(false)
epoch = 112; update(); assert(next(zones) == nil)
print('PASS actual game script clears markers on bridge disconnect')

cameraDistance = 12000
epoch = 112.2; incoming(true); update()
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.telemetry.cursor_radius == 264)
local outer = zones.tf2coop_peer_1_outer_edge_1.polygon[1]
assert(math.abs(outer[1] - (10 + 264 * 1.7)) < 0.001)
cameraDistance = nil
game.gui = { getCamera = function() return { 0, 0, 2000, 0, 0.7 } end }
epoch = 112.4; incoming(true); update()
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.telemetry.cursor_radius == 44 and outgoing.capabilities.camera_scaling)
game.gui = nil
epoch = 112.6; incoming(true); update()
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.telemetry.cursor_radius == 24 and not outgoing.capabilities.camera_scaling)
assert(zones.tf2coop_peer_1_cursor, 'A camera API failure must not remove the cursor')
assert(forbidden == 0)
print('PASS cursor scales with zoom and retains a visible fallback without camera writes')

-- The real TF2 GUI Lua state has io.open but removes os.rename/os.remove.
-- Reproduce that capability boundary instead of granting the full desktop API.
os.rename, os.remove = nil, nil
files['C:/mock-mailbox/game.json'] = nil
files['C:/mock-mailbox/game.json.tmp'] = nil
epoch = 113; incoming(true); update()
assert(files['C:/mock-mailbox/game.json'], 'Restricted TF2 state must publish game.json')
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.written_at == 113 and outgoing.cursor[1] == 1)
assert(not files['C:/mock-mailbox/game.json.tmp'], 'Fallback must not leave unpublished temporary data')
epoch = 114; update()
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.written_at == 114 and outgoing.capabilities.mailbox_write == true)
print('PASS actual game script publishes repeatedly without os.rename or os.remove')

-- A panel creation failure must be observable without suppressing heartbeat.
api.gui.comp.Component.new = function() error('simulated component binding failure') end
dofile('mod/tf2coop_1/res/config/game_script/tf2coop.lua')
script = data(); script.guiInit()
epoch = 115; update()
outgoing = json.decode(files['C:/mock-mailbox/game.json'])
assert(outgoing.written_at == 115 and outgoing.capabilities.peer_panel == false)
assert(outgoing.capabilities.panel_error.stage == 'content')
assert(outgoing.capabilities.panel_error.message:find('simulated component binding failure', 1, true))
print('PASS panel binding failures carry stage and error in a live heartbeat')
io, os, package.loaded['tf2coop/config'] = originalIO, originalOS, oldConfig
api, game, script = nil, nil, nil
