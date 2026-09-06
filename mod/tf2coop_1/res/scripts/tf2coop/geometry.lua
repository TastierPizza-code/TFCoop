-- Pure geometry + bounded extraction of the game's legacy GUI proposal format.
-- Field evidence: original res/scripts/mission/proposalutil.lua.
local M = {}
function M.get(v, key)
  local ok, result = pcall(function() return v[key] end)
  if ok then return result end
end
function M.number(n) return type(n) == 'number' and n == n and math.abs(n) <= 1000000 end
function M.point(v)
  local x, y, z = M.get(v, 1) or M.get(v, 'x'), M.get(v, 2) or M.get(v, 'y'), M.get(v, 3) or M.get(v, 'z')
  if M.number(x) and M.number(y) and M.number(z) then return { x, y, z } end
end
local function each(v, limit, fn)
  for i = 1, limit do local item = M.get(v, i); if item == nil then break end; fn(item) end
end
function M.circle(p, radius)
  local polygon = {}
  for i = 1, 20 do local a = (i - 1) * math.pi / 10; polygon[i] = { p[1] + radius * math.cos(a), p[2] + radius * math.sin(a) } end
  return polygon
end
function M.cursorRadius(distance)
  -- Camera distance is the third value in TF2's five-value camera state.
  -- Retain a useful marker if a camera read fails; never shrink to invisibility.
  if not M.number(distance) or distance <= 0 then return 24 end
  return math.max(12, math.min(900, distance * 0.022))
end
function M.ring(p, innerRadius, outerRadius)
  -- Four simple arc polygons avoid unsupported holes/self-crossing polygons.
  local parts = {}
  for quarter = 0, 3 do
    local polygon = {}
    for step = 0, 8 do
      local angle = (quarter + step / 8) * math.pi / 2
      polygon[#polygon + 1] = { p[1] + outerRadius * math.cos(angle), p[2] + outerRadius * math.sin(angle) }
    end
    for step = 8, 0, -1 do
      local angle = (quarter + step / 8) * math.pi / 2
      polygon[#polygon + 1] = { p[1] + innerRadius * math.cos(angle), p[2] + innerRadius * math.sin(angle) }
    end
    parts[#parts + 1] = polygon
  end
  return parts
end
function M.strip(a, b, halfWidth)
  local dx, dy = b[1] - a[1], b[2] - a[2]
  local length = math.sqrt(dx * dx + dy * dy)
  if length < 0.1 then return M.circle(a, halfWidth) end
  local x, y = -dy / length * halfWidth, dx / length * halfWidth
  return { { a[1] + x, a[2] + y }, { a[1] - x, a[2] - y }, { b[1] - x, b[2] - y }, { b[1] + x, b[2] + y } }
end
local kinds = { streetBuilder = 'street', trackBuilder = 'track', constructionBuilder = 'construction', streetTerminalBuilder = 'construction', streetTrackModifier = 'street', bulldozer = 'bulldozer' }
function M.kind(id) return kinds[id] end
function M.capture(id, param, getEntity)
  local kind = kinds[id]
  if not kind then return nil end
  local proposal = M.get(param, 'proposal')
  local street = M.get(proposal, 'proposal')
  local nodes, points = {}, {}
  each(M.get(street, 'addedNodes'), 256, function(node)
    local entity = M.get(node, 'entity')
    if type(entity) == 'number' then nodes[entity] = M.point(M.get(M.get(node, 'comp'), 'position')) end
  end)
  local function nodePoint(entity)
    if type(entity) ~= 'number' then return nil end
    if nodes[entity] then return nodes[entity] end
    if entity >= 0 and getEntity then
      local ok, object = pcall(getEntity, entity)
      if ok then return M.point(M.get(object, 'position')) end
    end
  end
  -- Only take one contiguous path; never draw fictitious links across branches.
  each(M.get(street, id == 'bulldozer' and 'removedSegments' or 'addedSegments'), 64, function(segment)
    if #points >= 64 then return end
    local comp = M.get(segment, 'comp')
    local a, b = nodePoint(M.get(comp, 'node0')), nodePoint(M.get(comp, 'node1'))
    if a and b then
      if #points == 0 then points = { a, b }
      else
        local last = points[#points]
        local function same(p) return math.abs(last[1]-p[1]) < 0.01 and math.abs(last[2]-p[2]) < 0.01 and math.abs(last[3]-p[3]) < 0.01 end
        if same(a) then points[#points + 1] = b elseif same(b) then points[#points + 1] = a end
      end
    end
  end)
  if #points == 0 then
    local first = M.get(M.get(proposal, 'toAdd'), 1)
    local transf = M.get(first, 'transf')
    local p = M.point({ M.get(transf, 13), M.get(transf, 14), M.get(transf, 15) })
    if not p and id == 'bulldozer' and getEntity then
      local entity = M.get(M.get(proposal, 'toRemove'), 1)
      if type(entity) == 'number' and entity >= 0 then
        local ok, object = pcall(getEntity, entity)
        if ok then
          p = M.point(M.get(object, 'position'))
          local t = M.get(object, 'transf')
          p = p or M.point({ M.get(t, 13), M.get(t, 14), M.get(t, 15) })
        end
      end
    end
    if p then points[1] = p end
  end
  if #points == 0 then return nil end
  return { kind = kind, points = points }
end
function M.peers(snapshot, now)
  if type(snapshot) ~= 'table' or snapshot.protocol ~= 1 or snapshot.connected ~= true or
    type(snapshot.written_at) ~= 'number' or snapshot.written_at ~= snapshot.written_at or math.abs(snapshot.written_at - now) > 5 or type(snapshot.peers) ~= 'table' then return {} end
  local result, seen = {}, {}
  for i = 1, math.min(#snapshot.peers, 8) do
    local peer = snapshot.peers[i]
    if type(peer) == 'table' and type(peer.id) == 'string' and #peer.id <= 80 and peer.id ~= snapshot.local_peer_id and not seen[peer.id] and
       type(peer.name) == 'string' and #peer.name <= 96 and type(peer.color) == 'string' and peer.color:match('^#%x%x%x%x%x%x$') then
      seen[peer.id] = true
      local presence = type(peer.presence) == 'table' and peer.presence or {}
      local clean = { id = peer.id, name = peer.name:gsub('[%z\1-\31\127]', ''), color = peer.color, cursor = M.point(presence.cursor) }
      local preview = presence.preview
      if type(preview) == 'table' and (preview.kind == 'street' or preview.kind == 'track' or preview.kind == 'construction' or preview.kind == 'bulldozer') and type(preview.points) == 'table' and #preview.points <= 128 then
        local points = {}
        for j = 1, #preview.points do local p = M.point(preview.points[j]); if not p then points = {}; break end; points[j] = p end
        if #points > 0 then clean.preview = { kind = preview.kind, points = points } end
      end
      result[#result + 1] = clean
    end
  end
  return result
end
function M.color(hex, alpha)
  return { tonumber(hex:sub(2, 3), 16) / 255, tonumber(hex:sub(4, 5), 16) / 255, tonumber(hex:sub(6, 7), 16) / 255, alpha or 0.6 }
end
return M
