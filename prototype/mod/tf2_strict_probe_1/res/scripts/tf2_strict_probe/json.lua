-- Strict, bounded JSON. Network data is never passed to Lua's load/loadfile.
local M = { null = {} }
local arrayMT = {}
function M.array(t) return setmetatable(t or {}, arrayMT) end
local function finite(n) return n == n and n ~= math.huge and n ~= -math.huge end
local escapes = { ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
local function quote(s)
  return '"' .. s:gsub('[%z\1-\31\\"]', function(c) return escapes[c] or string.format('\\u%04x', c:byte()) end) .. '"'
end
function M.encode(value)
  local seen, count = {}, 0
  local function encode(v, depth)
    count = count + 1
    assert(depth <= 20 and count <= 10000, 'JSON complexity limit')
    if v == M.null or v == nil then return 'null' end
    if type(v) == 'boolean' then return tostring(v) end
    if type(v) == 'number' then assert(finite(v), 'Non-finite number'); return string.format('%.17g', v) end
    if type(v) == 'string' then return quote(v) end
    assert(type(v) == 'table' and not seen[v], 'JSON requires acyclic plain data')
    seen[v] = true
    local out = {}
    if getmetatable(v) == arrayMT or #v > 0 then
      for k in pairs(v) do assert(type(k) == 'number' and k >= 1 and k <= #v and k % 1 == 0, 'Invalid array key') end
      for i = 1, #v do out[i] = encode(v[i], depth + 1) end
      seen[v] = nil
      return '[' .. table.concat(out, ',') .. ']'
    end
    local keys = {}
    for k in pairs(v) do assert(type(k) == 'string', 'Invalid object key'); keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do out[#out + 1] = quote(k) .. ':' .. encode(v[k], depth + 1) end
    seen[v] = nil
    return '{' .. table.concat(out, ',') .. '}'
  end
  local result = encode(value, 0)
  assert(#result <= 262144, 'JSON byte limit')
  return result
end
local function utf8char(n)
  if n < 128 then return string.char(n) end
  if n < 2048 then return string.char(192 + math.floor(n / 64), 128 + n % 64) end
  if n < 65536 then return string.char(224 + math.floor(n / 4096), 128 + math.floor(n / 64) % 64, 128 + n % 64) end
  return string.char(240 + math.floor(n / 262144), 128 + math.floor(n / 4096) % 64, 128 + math.floor(n / 64) % 64, 128 + n % 64)
end
function M.decode(source)
  assert(type(source) == 'string' and #source <= 262144, 'JSON byte limit')
  local pos, count = 1, 0
  local function fail(message) error(message .. ' at byte ' .. pos, 0) end
  local function ws() local _, last = source:find('^[ \t\r\n]*', pos); pos = (last or pos - 1) + 1 end
  local function hex4()
    local h = source:sub(pos, pos + 3)
    if #h ~= 4 or not h:match('^%x%x%x%x$') then fail('Invalid Unicode escape') end
    pos = pos + 4
    return tonumber(h, 16)
  end
  local function str()
    pos = pos + 1
    local parts, start = {}, pos
    while pos <= #source do
      local c = source:sub(pos, pos)
      if c == '"' then parts[#parts + 1] = source:sub(start, pos - 1); pos = pos + 1; return table.concat(parts) end
      if c:byte() < 32 then fail('Control character in string') end
      if c == '\\' then
        parts[#parts + 1] = source:sub(start, pos - 1)
        pos = pos + 1
        local esc = source:sub(pos, pos)
        pos = pos + 1
        local values = { ['"'] = '"', ['\\'] = '\\', ['/'] = '/', b = '\b', f = '\f', n = '\n', r = '\r', t = '\t' }
        if esc == 'u' then
          local n = hex4()
          if n >= 55296 and n <= 56319 then
            if source:sub(pos, pos + 1) ~= '\\u' then fail('Missing low surrogate') end
            pos = pos + 2
            local low = hex4()
            if low < 56320 or low > 57343 then fail('Invalid low surrogate') end
            n = 65536 + (n - 55296) * 1024 + low - 56320
          elseif n >= 56320 and n <= 57343 then fail('Unexpected low surrogate') end
          parts[#parts + 1] = utf8char(n)
        elseif values[esc] then parts[#parts + 1] = values[esc]
        else fail('Invalid string escape') end
        start = pos
      else pos = pos + 1 end
    end
    fail('Unterminated string')
  end
  local parse
  parse = function(depth)
    count = count + 1
    if depth > 20 or count > 10000 then fail('JSON complexity limit') end
    ws()
    local c = source:sub(pos, pos)
    if c == '"' then return str() end
    if c == '{' then
      pos = pos + 1; ws()
      local result = {}
      if source:sub(pos, pos) == '}' then pos = pos + 1; return result end
      while true do
        if source:sub(pos, pos) ~= '"' then fail('Expected object key') end
        local key = str(); ws()
        if result[key] ~= nil then fail('Duplicate object key') end
        if source:sub(pos, pos) ~= ':' then fail('Expected colon') end
        pos = pos + 1
        result[key] = parse(depth + 1); ws()
        local delim = source:sub(pos, pos); pos = pos + 1
        if delim == '}' then return result end
        if delim ~= ',' then fail('Expected object delimiter') end
        ws()
      end
    end
    if c == '[' then
      pos = pos + 1; ws()
      local result = M.array()
      if source:sub(pos, pos) == ']' then pos = pos + 1; return result end
      while true do
        result[#result + 1] = parse(depth + 1); ws()
        local delim = source:sub(pos, pos); pos = pos + 1
        if delim == ']' then return result end
        if delim ~= ',' then fail('Expected array delimiter') end
      end
    end
    for literal, value in pairs({ ['true'] = true, ['false'] = false, ['null'] = M.null }) do
      if source:sub(pos, pos + #literal - 1) == literal then pos = pos + #literal; return value end
    end
    local start = pos
    if c == '-' then pos = pos + 1 end
    c = source:sub(pos, pos)
    if c == '0' then pos = pos + 1
    elseif c:match('[1-9]') then repeat pos = pos + 1 until not source:sub(pos, pos):match('%d')
    else fail('Expected value') end
    if source:sub(pos, pos) == '.' then
      pos = pos + 1
      if not source:sub(pos, pos):match('%d') then fail('Expected fractional digit') end
      repeat pos = pos + 1 until not source:sub(pos, pos):match('%d')
    end
    if source:sub(pos, pos):match('[eE]') then
      pos = pos + 1
      if source:sub(pos, pos):match('[+-]') then pos = pos + 1 end
      if not source:sub(pos, pos):match('%d') then fail('Expected exponent digit') end
      repeat pos = pos + 1 until not source:sub(pos, pos):match('%d')
    end
    local n = tonumber(source:sub(start, pos - 1))
    if not n or not finite(n) then fail('Invalid number') end
    return n
  end
  local result = parse(0); ws()
  if pos <= #source then fail('Trailing data') end
  return result
end
return M
