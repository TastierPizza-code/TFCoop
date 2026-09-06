-- Controlled engine-state test adapter. Stock building UI is never observed.
-- A fresh, exclusive controller owns one contiguous request stream per epoch.
local json = require 'tf2_strict_probe/json'
local config = require 'tf2_strict_probe/config'
local engine_module = require(config.profile == 'build_v1' and 'tf2_strict_probe/build_engine' or 'tf2_strict_probe/engine')
local MAX_BYTES, MAX_STATE_BYTES = 262144, 100000

function data()
  local enabled = config.enabled == true
  local E, path, started, halted, saved_active = nil, '', false, false, false
  local request, revision, signature, pending, in_flight = 0, 0, nil, nil, false
  local seen_sequence={a=0,b=0}
  local current_status, last_snapshot, last_canonical
  local published_revision=0
  local function decimal(v, positive)
    if type(v)~='string' or not v:match('^%d+$') or #v>20 or (#v>1 and v:sub(1,1)=='0')
      or (#v==20 and v>'18446744073709551615') or (positive and v=='0') then error('invalid uint64 decimal string',0) end
    return v
  end
  local function read(name, limit)
    local f=io.open(path..'/'..name,'rb'); if not f then return nil end
    local ok, raw=pcall(function() return f:read(limit+1) end)
    local close_ok, closed=pcall(function() return f:close() end)
    if not ok or not close_ok or not closed or not raw then return nil end
    if #raw>limit then error('mailbox byte limit: '..name,0) end
    return raw
  end
  local function write_status()
    if not current_status then return false end
    -- Rewriting a completed acknowledgement on every update repeatedly
    -- truncates the reader's file. Leave a successfully published revision
    -- stable; retry only a new revision whose previous write did not finish.
    if current_status.revision==published_revision then return true end
    local ok,raw=pcall(json.encode,current_status); if not ok then return false end
    local f=io.open(path..'/lua_status.json','wb'); if not f then return false end
    local written,ret=pcall(function() return f:write(raw) end)
    local closed,close_ret=pcall(function() return f:close() end)
    local complete=written and ret~=nil and closed and close_ret~=nil and close_ret~=false
    if complete then published_revision=current_status.revision end
    return complete
  end
  local function publish(status, complete, extra)
    revision=revision+1
    current_status={protocol=1,epoch=config.epoch,request=request,revision=revision,status=status,complete=complete,
      snapshot=last_snapshot,canonical_state_json=last_canonical,diagnostics={bindings=E and E.local_bindings() or {},
        site_search=E and E.site_diagnostics or nil}}
    if extra then for k,v in pairs(extra) do current_status[k]=v end end
    return write_status()
  end
  local function halt(reason, extra)
    halted=true; pending=nil
    local details={error=tostring(reason):sub(1,1024)}
    if extra then for k,v in pairs(extra) do details[k]=v end end
    publish('halted',true,details)
  end
  local function native(boundary)
    local raw=read('native_status.txt',4096); if not raw then return nil end
    if raw:sub(-1)~='\n' then return nil end -- incomplete status is never a gate acknowledgement
    local values={}
    for line in raw:gmatch('[^\r\n]+') do
      local k,v=line:match('^([a-z][a-z0-9_]*)=(%d+)$')
      if not k or values[k] then error('invalid native gate status',0) end
      values[k]=v
    end
    local required={'protocol','abi','epoch','ready','initialized','armed','halted','fault','runtime_fault','probe_required','pending_state','completed_frame'}
    for _,k in ipairs(required) do if values[k]==nil then return nil end end
    if values.protocol~='1' or values.abi~='3' or values.epoch~=config.epoch or values.probe_required~='1'
      or values.halted~='0' or values.fault~='0' or values.runtime_fault~='0' then error('native gate epoch/ABI/fault mismatch',0) end
    if values.native_step_us~='200000' then error('native gate requires explicit 200000-microsecond engine step',0) end
    if values.ready~='1' or values.initialized~='1' or values.armed~='1' then return nil end
    if values.pending_state~='0' or values.completed_frame~=boundary then error('native gate boundary is not held and complete',0) end
    return true
  end
  local function snapshot(expected)
    local s=E.snapshot(); local canonical=json.encode(s)
    if #canonical>MAX_STATE_BYTES then error('bounded tracked snapshot too large',0) end
    if expected~=nil and s.sim_time_us~=expected then error('observed simulation time differs from requested boundary',0) end
    if #s.coverage.missing>0 then error('capability_missing: '..table.concat(s.coverage.missing,'; '),0) end
    last_snapshot,last_canonical=s,canonical
    return canonical
  end
  local function start()
    decimal(config.epoch,true)
    if config.profile~=nil and config.profile~='time_v1' and config.profile~='build_v1' then error('unknown measurement profile',0) end
    if config.native_gate_required~=true then error('native gate is mandatory',0) end
    if type(config.mailbox_dir)~='string' then error('absolute mailbox directory required',0) end
    path=config.mailbox_dir:gsub('\\','/'):gsub('/+$','')
    if not (path:match('^%a:/') or path:match('^/')) then error('absolute mailbox directory required',0) end
    if saved_active then error('saved active probe sessions cannot resume; prepare a fresh baseline save and epoch',0) end
    if not native('0') then return false end
    E=engine_module.new(json); E.bind_initial(config.initial_bindings)
    snapshot(); started=true
    if not publish('ready',true,{loaded_sim_time_us=last_snapshot.sim_time_us,probe_only=true}) then error('initial status write failed',0) end
    return true
  end
  local function validate_control(c)
    if type(c)~='table' or c.protocol~=1 or c.epoch~=config.epoch then error('control protocol/epoch mismatch',0) end
    E.integer(c.request,1)
    if type(c.action)~='string' then error('control action required',0) end
    if c.action~='halt' then
      decimal(c.boundary,false); E.integer(c.expected_sim_time_us,0)
    end
    if c.action=='plan' or c.action=='apply' then
      if type(c.command_key)~='string' or not c.command_key:match('^[ab]:[1-9]%d*$') or #c.command_key>96 then error('invalid command key',0) end
      if type(c.command)~='table' then error('command object required',0) end
    end
  end
  local function process(c, sig)
    if c.request==request then
      if sig~=signature then error('same request reused with different content',0) end
      if not write_status() then error('status rewrite failed',0) end
      return
    end
    if c.request~=request+1 then error('noncontiguous request; no history skipping',0) end
    if halted then return end
    if c.action~='halt' and not native(c.boundary) then return end
    request,signature=c.request,sig
    if c.action=='halt' then halt('controller requested halt'); return end
    if in_flight then error('command callback still pending',0) end
    if c.action=='snapshot' then
      if pending then error('snapshot cannot replace an unapplied plan',0) end
      snapshot(c.expected_sim_time_us)
      if not publish('ready',true) then error('snapshot status write failed',0) end
    elseif c.action=='plan' then
      if pending then error('only one unapplied plan is permitted',0) end
      local peer,seq=c.command_key:match('^([ab]):([1-9]%d*)$'); seq=E.integer(seq,1)
      if seq<=seen_sequence[peer] then error('command key was already planned; no command replay',0) end
      local before=snapshot(c.expected_sim_time_us)
      local plan=E.plan(c.command,c.command_key,c.expected_sim_time_us)
      seen_sequence[peer]=seq
      pending={plan=plan,key=c.command_key,boundary=c.boundary,time=c.expected_sim_time_us,command=json.encode(c.command),before=before}
      if not publish('planned',true) then error('plan acknowledgement write failed',0) end
    elseif c.action=='apply' then
      local p=pending
      if not p or p.key~=c.command_key or p.boundary~=c.boundary or p.time~=c.expected_sim_time_us
        or p.command~=json.encode(c.command) then error('apply differs from the prepared plan',0) end
      if snapshot(c.expected_sim_time_us)~=p.before then error('tracked world changed between plan and apply',0) end
      pending=nil; in_flight=true
      -- Persist in-flight before handing ownership to the engine, including
      -- when sendCommand invokes its real callback synchronously in engine Lua.
      if not publish('in_flight',false) then error('in-flight write failed; command not sent',0) end
      local callback_called=false
      api.cmd.sendCommand(p.plan.native,function(result,success)
        if callback_called then halt('engine callback invoked more than once'); return end
        callback_called=true; in_flight=false
        local ok,receipt=pcall(function()
          local r=E.finish(p.plan,result,success)
          r.command_key=p.key; r.boundary=p.boundary; r.bindings=E.local_bindings()
          if halted then return r end
          if not native(p.boundary) then error('native gate became unavailable during callback',0) end
          snapshot(p.time)
          if p.plan.command.op=='SET_PAUSED' and last_snapshot.paused~=p.plan.command.value then error('pause callback did not produce requested pause flag',0) end
          return r
        end)
        if not ok then halt(receipt); return end
        if halted then halt('completion observed after halt',{receipt=receipt}); return end
        if receipt.success~=true then halt('engine rejected command',{receipt=receipt}); return end
        if not publish('applied',true,{receipt=receipt}) then halt('applied status write failed; command cannot be retried',{receipt=receipt}) end
      end)
    else error('unsupported control action',0) end
  end
  local function update()
    if not enabled then return end
    local ok,err=pcall(function()
      if halted then write_status(); return end
      if not started and not start() then return end
      local raw=read('lua_control.json',MAX_BYTES); if not raw then return end
      local decoded,c=pcall(json.decode,raw)
      if not decoded then return end -- incomplete direct write; never advance seq
      validate_control(c); process(c,json.encode(c))
    end)
    if not ok then halt(err) end
  end
  return {
    update=update,
    save=function() return {strict_probe_active=enabled and started or false,epoch=enabled and config.epoch or ''} end,
    load=function(state) if enabled and type(state)=='table' and state.strict_probe_active==true then saved_active=true end end,
  }
end
