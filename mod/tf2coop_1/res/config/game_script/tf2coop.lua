local json = require 'tf2coop/json'
local geometry = require 'tf2coop/geometry'
local config = require 'tf2coop/config'

local state = {
  preview = nil, previewTime = 0, clock = 0, nextUpdate = 0,
  zones = {}, rows = {}, peers = {}, snapshot = nil, active = false,
  capabilities = { simulation_sync = false, steam_networking = false, world_name_labels = false, exact_blueprints = false },
  status = 'Positionskanal nicht verbunden. Spiel-Synchronisierung: MP-Lockstep-Anzeige prüfen.',
}
local path = type(config.mailbox_dir) == 'string' and config.mailbox_dir:gsub('\\', '/') or ''
if not (path:match('^%a:/') or path:match('^/')) then path = '' end
path = path:gsub('/+$', '')

local function safe(fn)
  local ok, result = pcall(fn)
  if ok then return result end
end
local function now() return os.time() end
local function writeSnapshot(value)
  if path == '' or not io or type(io.open) ~= 'function' then return false end
  local encoded = safe(function() return json.encode(value) end)
  if not encoded then return false end
  -- TF2's GUI Lua sandbox exposes io.open but can omit os.rename/os.remove.
  -- In that state write the small snapshot directly; the bridge rejects a
  -- transient incomplete JSON read and retries on its next poll.
  local canRename = os and type(os.rename) == 'function' and type(os.remove) == 'function'
  local target = path .. (canRename and '/game.json.tmp' or '/game.json')
  local file = safe(function() return io.open(target, 'wb') end)
  if not file then return false end
  local success = safe(function() return file:write(encoded) end)
  local closed = safe(function() return file:close() end)
  if not success or not closed then return false end
  if not canRename then return true end
  -- Windows rename does not replace an existing file. Readers tolerate the
  -- short absence; they never observe a partially written JSON document.
  local renamed = safe(function() return os.rename(target, path .. '/game.json') end)
  if not renamed then
    safe(function() return os.remove(path .. '/game.json') end)
    renamed = safe(function() return os.rename(target, path .. '/game.json') end)
  end
  return renamed and true or false
end
local function readSnapshot()
  if path == '' or not io or type(io.open) ~= 'function' then return nil end
  local file = io.open(path .. '/peers.json', 'rb')
  if not file then return nil end
  local contents = file:read(65537)
  file:close()
  if not contents or #contents > 65536 then return nil end
  local decoded = safe(function() return json.decode(contents) end)
  if type(decoded) == 'table' and decoded.protocol == 1 then return decoded end
end

local function zone(key, polygon, color, nextZones)
  if not state.capabilities.world_overlays then return end
  local ok = pcall(function() game.interface.setZone(key, { polygon = polygon, draw = true, drawColor = color }) end)
  if ok then nextZones[key] = true else state.capabilities.world_overlays = false end
end
local function cameraDistance()
  local camera = safe(function() return api.gui.util.getGameUI():getMainRendererComponent():getCameraController():getCameraData() end)
  local distance = geometry.get(camera, 3)
  if geometry.number(distance) and distance > 0 then return distance end
  -- Shipped campaign mission 01 also reads this legacy API's third value as
  -- zoom distance. This fallback only reads the camera; it never moves it.
  camera = safe(function() return game.gui.getCamera() end)
  distance = geometry.get(camera, 3)
  if geometry.number(distance) and distance > 0 then return distance end
end
local function ring(key, cursor, innerRadius, outerRadius, color, nextZones)
  for i, polygon in ipairs(geometry.ring(cursor, innerRadius, outerRadius)) do
    zone(key .. '_' .. i, polygon, color, nextZones)
  end
end
local function renderPeers(peers)
  local nextZones = {}
  local distance = cameraDistance()
  local radius = geometry.cursorRadius(distance)
  state.capabilities.camera_scaling = distance ~= nil
  state.cursorRadius = radius
  for i, peer in ipairs(peers) do
    local prefix = 'tf2coop_peer_' .. i
    local color = geometry.color(peer.color, 0.95)
    if peer.cursor then
      local dark, light = { 0.025, 0.035, 0.05, 0.95 }, { 1, 1, 1, 0.95 }
      -- Nonoverlapping bands do not depend on setZone's draw order. The centre
      -- dot preserves the exact point; the open rings keep terrain readable.
      zone(prefix .. '_cursor', geometry.circle(peer.cursor, radius * 0.18), color, nextZones)
      ring(prefix .. '_dot_edge', peer.cursor, radius * 0.18, radius * 0.24, dark, nextZones)
      ring(prefix .. '_ring_inner', peer.cursor, radius * 0.62, radius * 0.72, light, nextZones)
      ring(prefix .. '_ring_color', peer.cursor, radius * 0.72, radius, color, nextZones)
      ring(prefix .. '_ring_edge', peer.cursor, radius, radius * 1.12, dark, nextZones)
      ring(prefix .. '_outer_inner', peer.cursor, radius * 1.48, radius * 1.55, dark, nextZones)
      ring(prefix .. '_outer_light', peer.cursor, radius * 1.55, radius * 1.62, light, nextZones)
      ring(prefix .. '_outer_edge', peer.cursor, radius * 1.62, radius * 1.70, dark, nextZones)
    end
    if peer.preview then
      local points = peer.preview.points
      if #points == 1 then zone(prefix .. '_preview1', geometry.circle(points[1], 12), geometry.color(peer.color, 0.3), nextZones)
      else
        for j = 2, math.min(#points, 65) do
          zone(prefix .. '_preview' .. j, geometry.strip(points[j - 1], points[j], 2), geometry.color(peer.color, 0.3), nextZones)
        end
      end
    end
  end
  for key in pairs(state.zones) do
    if not nextZones[key] then pcall(function() game.interface.setZone(key) end) end
  end
  state.zones = nextZones
end

local palette = { '#60a5fa', '#f472b6', '#34d399', '#fbbf24', '#a78bfa', '#fb923c', '#22d3ee', '#f87171' }
local function styleFor(hex)
  local actual, best, score = geometry.color(hex), 1, math.huge
  for i, candidate in ipairs(palette) do
    local rgb = geometry.color(candidate)
    local d = (rgb[1] - actual[1])^2 + (rgb[2] - actual[2])^2 + (rgb[3] - actual[3])^2
    if d < score then best, score = i, d end
  end
  return 'tf2coop_color_' .. best
end
local function updatePanel()
  if not state.label then return end
  state.label:setText(state.status)
  for i, row in ipairs(state.rows) do
    local peer = state.peers[i]
    if peer then
      local text = peer.name .. '  ' .. peer.color
      if peer.cursor then text = text .. string.format('  (%.0f, %.0f)', peer.cursor[1], peer.cursor[2]) end
      if peer.preview then text = text .. '  | ' .. peer.preview.kind .. ' (Skizze)' end
      row:setText(text)
      row:setStyleClassList({ styleFor(peer.color) })
    else row:setText('') end
  end
end
local function createPanel()
  local gui = api.gui
  state.panelStage = 'layout'
  local layout = gui.layout.BoxLayout.new('VERTICAL')
  state.label = gui.comp.TextView.new(state.status)
  layout:addItem(state.label)
  layout:addItem(gui.comp.TextView.new('Geteilte Planung: farbige Cursor und vereinfachte Bau-Skizzen.'))
  layout:addItem(gui.comp.TextView.new('Spiel-Synchronisierung: MP-Lockstep-Anzeige prüfen.'))
  for i = 1, 8 do state.rows[i] = gui.comp.TextView.new(''); layout:addItem(state.rows[i]) end
  state.panelStage = 'content'
  -- Build 35924 ships this one-argument constructor followed by setId in
  -- res/scripts/selectortooltip.lua; the online two-argument form fails here.
  local content = gui.comp.Component.new('TF2CoopPanel')
  content:setId('tf2coop.content')
  content:setLayout(layout)
  state.panelStage = 'window'
  local window = gui.comp.Window.new('TF2 Co-op | Planung', content)
  window:setId('tf2coop.window')
  window:addHideOnCloseHandler()
  state.panelStage = 'position'
  window:setPosition(30, 100)
  state.window = window
  state.panelStage = 'button'
  local button = gui.comp.Button.new(gui.comp.TextView.new('Co-op'), false)
  button:setTooltip('Gemeinsame Planung: Mitspieler und Verbindungsstatus')
  button:onClick(function() window:setVisible(not window:isVisible(), false) end)
  state.panelStage = 'button_parent'
  gui.util.getById('gameInfo'):getLayout():addItem(button)
end

local function panelError(stage, err)
  local message = tostring(err):sub(1, 768)
  local previous = state.capabilities.panel_error
  state.capabilities.peer_panel = false
  state.capabilities.panel_error = { stage = stage, message = message }
  if not previous or previous.stage ~= stage or previous.message ~= message then
    print('[TF2Coop] Panel ' .. stage .. ': ' .. message)
  end
end

local function guiInit()
  -- onStep is a documented monotonic GUI timer in microseconds. Keeping its
  -- connection alive avoids a CPU-time based presence update frequency.
  state.capabilities.gui_timer = false
  local registered, connection = pcall(function()
    return api.gui.util.getGameUI():onStep(function(total)
      if type(total) ~= 'number' then return end
      if not state.capabilities.gui_timer then state.nextUpdate = 0 end
      state.clock = total / 1000000
      state.capabilities.gui_timer = true
    end)
  end)
  state.timer = connection -- Some builds return no connection on success.
  state.capabilities.gui_timer_registered = registered
  state.capabilities.world_overlays = safe(function() return type(game.interface.setZone) == 'function' end) or false
  state.capabilities.file_io = io ~= nil and type(io.open) == 'function'
  state.capabilities.preview_capture = false
  state.capabilities.cursor_capture = false
  local panelOk, panelErr = pcall(createPanel)
  state.capabilities.peer_panel = panelOk
  if not panelOk then panelError(state.panelStage, panelErr)
  else state.capabilities.panel_error = nil end
  state.active = true
end
local function tick()
  if not state.active then guiInit() end
  -- Fallback remains deliberately 1 Hz when no GUI timer is available.
  local clock = state.capabilities.gui_timer and state.clock or now()
  if clock < state.nextUpdate then return end
  state.nextUpdate = clock + 0.1
  local cursor = safe(function() return geometry.point(api.gui.util.getGameUI():getMainRendererComponent():getTerrainPos()) end)
  state.capabilities.cursor_capture = cursor ~= nil
  if state.preview and now() - state.previewTime > 3 then state.preview = nil end
  local incoming = readSnapshot()
  if incoming then state.snapshot = incoming end
  state.peers = geometry.peers(state.snapshot, now())
  local connected = type(state.snapshot) == 'table' and state.snapshot.connected == true and
    type(state.snapshot.written_at) == 'number' and math.abs(state.snapshot.written_at - now()) <= 5
  if path == '' then state.status = 'Nicht eingerichtet: Installer ausführen und Spiel neu laden.'
  elseif connected then state.status = 'Positionskanal verbunden | ' .. #state.peers .. ' Mitspieler | MP-Lockstep-Anzeige prüfen'
  else state.status = 'Positionskanal nicht verbunden. Spiel-Synchronisierung: MP-Lockstep-Anzeige prüfen.' end
  renderPeers(state.peers)
  local panelOk, panelErr = pcall(updatePanel)
  if not panelOk then panelError('update', panelErr) end
  local ok = writeSnapshot({
    protocol = 1, written_at = now(), cursor = cursor or json.null, preview = state.preview or json.null,
    capabilities = state.capabilities, status = state.status, telemetry = { cursor_radius = state.cursorRadius },
  })
  state.capabilities.mailbox_write = ok
  if not ok and path ~= '' then state.status = 'Mailbox nicht beschreibbar. Pfad/Bridge im Launcher prüfen.' end
end
function data()
  return {
    -- Presence is transient. A savegame never persists peers, paths or zones.
    save = function() return { version = 1 } end,
    load = function() end,
    guiInit = guiInit,
    guiUpdate = function()
      local ok, err = pcall(tick)
      if not ok then
        state.status = 'Co-op Planung: API-Fehler; Details im Spiel-Log.'
        if not state.loggedError then print('[TF2Coop] ' .. tostring(err)); state.loggedError = true end
      end
    end,
    guiHandleEvent = function(id, name, param)
      if not geometry.kind(id) then return end
      if name == 'builder.apply' then state.preview = nil; return end
      if name == 'builder.proposalCreate' then
        local preview = safe(function() return geometry.capture(id, param, game.interface.getEntity) end)
        state.preview, state.previewTime = preview, now()
        state.capabilities.preview_capture = preview ~= nil
      end
      -- Never return a proposal veto and never execute a received build.
    end,
  }
end
