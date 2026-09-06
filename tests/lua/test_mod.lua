-- Run from the repository root in Lua 5.3/5.4 or with the Python/Lupa runner.
package.path = './mod/tf2coop_1/res/scripts/?.lua;' .. package.path
local json = require 'tf2coop/json'
local geo = require 'tf2coop/geometry'
local count = 0
local function test(name, fn)
  local ok, err = pcall(fn)
  assert(ok, name .. ': ' .. tostring(err))
  count = count + 1
  print('PASS ' .. name)
end
local function rejects(text) assert(not pcall(json.decode, text), 'accepted ' .. text:sub(1, 80)) end
test('JSON round-trip including null, arrays and German names', function()
  local value = json.decode('{"name":"Jörg","data":[null,false,1.5,-2e3],"empty":[]}')
  assert(value.name == 'Jörg' and value.data[1] == json.null and value.data[2] == false)
  local result = json.decode(json.encode(value))
  assert(result.data[4] == -2000 and #result.empty == 0)
  assert(json.encode(result.empty) == '[]')
end)
test('JSON Unicode surrogate pair and escaping', function()
  local result = json.decode('"\\uD83D\\uDE82\\n\\t\\\\\\\""')
  assert(result:sub(1, 4) == '🚂')
  assert(json.decode(json.encode(result)) == result)
end)
test('JSON rejects executable Lua and malformed input', function()
  for _, input in ipairs({ 'return os.execute("bad")', '{"a":1,"a":2}', '[1,]', '{"a":1,}', '01', '+1', '1.', '1e', '1e400', 'NaN', 'true false', '"\\uD800"', '"\\uDC00"', '"\\x11"', '"\n"' }) do rejects(input) end
end)
test('JSON enforces complexity and byte limits', function()
  rejects(string.rep('[', 22) .. '0' .. string.rep(']', 22))
  rejects('"' .. string.rep('x', 262144) .. '"')
  local circular = {}; circular.self = circular
  assert(not pcall(json.encode, circular))
  assert(not pcall(json.encode, math.huge))
end)
test('legacy street proposal resolves added and existing nodes', function()
  local preview = geo.capture('streetBuilder', { proposal = { proposal = {
    addedNodes = { { entity = -1, comp = { position = { 10, 20, 3 } } } },
    addedSegments = { { comp = { node0 = -1, node1 = 42 } } },
  } } }, function(id) assert(id == 42); return { position = { 20, 30, 3 } } end)
  assert(preview.kind == 'street' and #preview.points == 2 and preview.points[2][1] == 20)
end)
test('construction placement extracts actual transform', function()
  local transf = {}; transf[13], transf[14], transf[15] = 30, 40, 5
  local preview = geo.capture('constructionBuilder', { proposal = { toAdd = { { transf = transf } } } })
  assert(preview.kind == 'construction' and preview.points[1][1] == 30)
end)
test('branches do not become fictional connecting lines', function()
  local nodes = {}
  for i = 1, 4 do nodes[i] = { entity = -i, comp = { position = { i*10, 0, 0 } } } end
  local preview = geo.capture('trackBuilder', { proposal = { proposal = { addedNodes = nodes,
    addedSegments = { { comp = { node0 = -1, node1 = -2 } }, { comp = { node0 = -3, node1 = -4 } } },
  } } })
  assert(#preview.points == 2)
end)
test('malformed proposals and non-finite coordinates are ignored', function()
  assert(geo.capture('streetBuilder', {}) == nil)
  assert(geo.capture('vehicleManager', {}) == nil)
  assert(geo.point({ math.huge, 1, 2 }) == nil)
end)
local function snapshot()
  return { protocol = 1, connected = true, local_peer_id = 'me', written_at = 100,
    peers = { { id = 'friend', name = 'Freund', color = '#34d399', presence = { cursor = { 1,2,3 }, preview = { kind='street', points = {{1,2,3},{4,5,6}} } } } } }
end
test('peer input validates and expires without retaining cursor', function()
  local data = snapshot()
  assert(#geo.peers(data, 100) == 1)
  assert(#geo.peers(data, 106) == 0)
  data.written_at = 'bad'; assert(#geo.peers(data, 100) == 0)
  data = snapshot(); data.connected = false; assert(#geo.peers(data, 100) == 0)
  data = snapshot(); data.local_peer_id = 'friend'; assert(#geo.peers(data,100) == 0)
end)
test('peer input bounds preview geometry and removes control characters', function()
  local data = snapshot(); data.peers[1].name = 'Bad\nName'
  assert(geo.peers(data,100)[1].name == 'BadName')
  data.peers[1].presence.preview.points[2] = {1,math.huge,3}
  assert(geo.peers(data,100)[1].preview == nil)
  data.peers[1].color = 'red'; assert(#geo.peers(data,100) == 0)
end)
test('zone geometry stays finite for overlapping points', function()
  assert(#geo.circle({0,0,0},8) == 20)
  assert(#geo.strip({0,0,0},{0,0,0},2) == 20)
  local strip = geo.strip({0,0,0},{10,0,0},2)
  assert(#strip == 4 and strip[1][2] == 2 and strip[3][1] == 10)
end)
test('cursor radius scales at map overview and bounds missing or invalid camera data', function()
  assert(geo.cursorRadius(100) == 12)
  assert(geo.cursorRadius(2000) == 44)
  assert(geo.cursorRadius(12000) == 264)
  assert(geo.cursorRadius(100000) == 900)
  for _, value in ipairs({ -1, 0, math.huge, 'bad' }) do assert(geo.cursorRadius(value) == 24) end
  assert(geo.cursorRadius(nil) == 24 and geo.cursorRadius(0/0) == 24)
end)
test('cursor ring uses bounded simple arcs with an open centre', function()
  local arcs = geo.ring({10,20,0}, 20, 30)
  assert(#arcs == 4)
  local totalArea = 0
  for _, arc in ipairs(arcs) do
    assert(#arc == 18)
    local area = 0
    for i, point in ipairs(arc) do
      local radius = math.sqrt((point[1]-10)^2 + (point[2]-20)^2)
      assert(radius >= 19.999 and radius <= 30.001)
      local nextPoint = arc[i % #arc + 1]
      area = area + point[1] * nextPoint[2] - nextPoint[1] * point[2]
    end
    assert(area > 0, 'Every arc must retain consistent winding without crossings')
    totalArea = totalArea + area / 2
  end
  local expectedArea = math.pi * (30^2 - 20^2)
  assert(math.abs(totalArea / expectedArea - 1) < 0.01)
end)
print(string.format('%d Lua tests passed', count))
