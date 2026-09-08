-- Controlled engine-state test adapter. Stock building UI is never observed.
-- A fresh, exclusive controller owns one contiguous request stream per epoch.
local json = require 'tf2_strict_probe/json'
local config = require 'tf2_strict_probe/config'
local engine_module = require(config.profile == 'build_v2' and 'tf2_strict_probe/build_engine' or 'tf2_strict_probe/engine')
local MAX_BYTES, MAX_STATE_BYTES = 262144, 100000

function data()
  local enabled = config.enabled == true
  local E, path, started, halted, saved_active = nil, '', false, false, false
  local request, revision, signature, pending, in_flight = 0, 0, nil, nil, false
  local seen_sequence={a=0,b=0}
  local current_status, last_snapshot, last_canonical
  local failed_observation, failure_diagnostics, request_context
  local awaiting_completion, retained_receipt, last_native_read_issue
  local native_read_issue_count, halt_reason = 0, nil
  local published_revision=0
  local function decimal(v, positive)
    if type(v)~='string' or not v:match('^%d+$') or #v>20 or (#v>1 and v:sub(1,1)=='0')
      or (#v==20 and v>'18446744073709551615') or (positive and v=='0') then error('invalid uint64 decimal string',0) end
    return v
  end
  local function checked_plain(value,limit)
    local remaining=4096
    local function check(v,depth)
      remaining=remaining-1
      if remaining<0 or depth>12 then error('completion data complexity limit',0) end
      local kind=type(v)
      if kind=='nil' or kind=='boolean' or kind=='string' then return end
      if kind=='number' then
        if v%1~=0 or math.abs(v)>9007199254740991 then error('completion data requires finite integer numbers',0) end
        return
      end
      if kind~='table' then error('completion data requires plain data',0) end
      for k,x in pairs(v) do check(k,depth+1); check(x,depth+1) end
    end
    check(value,0)
    local raw=json.encode(value)
    if #raw>limit then error('completion data byte limit',0) end
    return json.decode(raw)
  end
  local function read_issue(name, kind, operation, message, errno)
    if name~='native_status.txt' then return end
    native_read_issue_count=math.min(native_read_issue_count+1,1000000)
    last_native_read_issue={kind=kind,operation=operation,count=native_read_issue_count,
      error=tostring(message or ''):gsub('%c',' '):sub(1,256)}
    if type(errno)=='number' and errno%1==0 and math.abs(errno)<=2147483647 then
      last_native_read_issue.errno=errno
    end
  end
  local function read(name, limit)
    local opened,f,message,errno=pcall(io.open,path..'/'..name,'rb')
    if not opened then
      if name~='native_status.txt' then error(f,0) end
      read_issue(name,'io_error','open',f); return nil
    end
    if not f then read_issue(name,'unavailable','open',message,errno); return nil end
    local ok,raw,read_error,read_errno=pcall(function() return f:read(limit+1) end)
    local close_ok,closed,close_error,close_errno=pcall(function() return f:close() end)
    if not ok or type(raw)~='string' then
      read_issue(name,'io_error','read',ok and read_error or raw,read_errno); return nil
    end
    if not close_ok or not closed then
      read_issue(name,'io_error','close',close_ok and close_error or closed,close_errno); return nil
    end
    if #raw>limit then
      read_issue(name,'invalid','read','mailbox byte limit')
      error('mailbox byte limit: '..name,0)
    end
    return raw
  end
  local function write_status()
    if not current_status then return false end
    -- Rewriting a completed acknowledgement on every update repeatedly
    -- truncates the reader's file. Leave a successfully published revision
    -- stable; retry only a new revision whose previous write did not finish.
    if current_status.revision==published_revision then return true end
    local ok,raw=pcall(json.encode,current_status); if not ok or #raw>MAX_BYTES then return false end
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
        site_search=E and E.site_diagnostics or nil,last_native_read_issue=last_native_read_issue,
        callback_phase=awaiting_completion and 'await_gate' or nil}}
    if extra then for k,v in pairs(extra) do current_status[k]=v end end
    if status=='halted' then
      -- A halt is never a state acknowledgement. Keep the last valid snapshot
      -- explicitly historical. Raw API observations live in their own file:
      -- their native floats must never enter the integer-only state protocol.
      current_status.canonical_state_json=nil
      current_status.diagnostics.snapshot_scope=last_snapshot and 'last_valid_before_failure' or 'unavailable'
      current_status.diagnostics.failure=failure_diagnostics
      local ok,raw=pcall(json.encode,current_status)
      if not ok or #raw>MAX_BYTES then
        current_status.snapshot=nil
        current_status.diagnostics.snapshot_scope='omitted_for_status_limit'
        ok,raw=pcall(json.encode,current_status)
        if not ok or #raw>MAX_BYTES then
          current_status.diagnostics={snapshot_scope='omitted_for_status_limit',
            failure={valid_snapshot=false,audit_error='failure diagnostics exceeded status limit'}}
        end
      end
    end
    return write_status()
  end
  local function halt(reason, extra)
    halted=true; pending=nil; awaiting_completion=nil; in_flight=false
    local observed_reason=tostring(reason):sub(1,1024)
    halt_reason=halt_reason or observed_reason
    local details={error=halt_reason,receipt=retained_receipt}
    if observed_reason~=halt_reason then details.secondary_error=observed_reason end
    if not failure_diagnostics and config.profile=='build_v2' then
      failure_diagnostics={valid_snapshot=false,request_context=request_context,failed_observation=failed_observation}
      if E and details.error~='controller requested halt' then
        local ok,report=pcall(function()
          return require('tf2_strict_probe/api_audit').collect(api,game,json,
            {request_id=tostring(config.epoch)..':'..tostring(request),
              bindings=E.diagnostic_bindings and E.diagnostic_bindings() or E.local_bindings()})
        end)
        if ok then
          local written,problem=pcall(function()
            if type(report)~='table' or report.valid_snapshot~=false then error('invalid audit envelope',0) end
            local raw=json.encode(report)
            if #raw>98304 then error('audit byte limit',0) end
            local f=io.open(path..'/lua_api_audit.json','wb'); if not f then error('audit open failed',0) end
            local write_ok,ret=pcall(function() return f:write(raw) end)
            local close_ok,closed=pcall(function() return f:close() end)
            if not write_ok or not ret or not close_ok or not closed then error('audit write/close failed',0) end
            if read('lua_api_audit.json',98304)~=raw then error('audit readback failed',0) end
          end)
          failure_diagnostics.api_audit={file='lua_api_audit.json',written=written,valid_snapshot=false}
          if not written then failure_diagnostics.audit_error=tostring(problem):sub(1,256) end
        else failure_diagnostics.audit_error='API collector failed ('..type(report)..')' end
      end
    end
    if failure_diagnostics and E and E.callback_diagnostics then
      local ok,callback=pcall(function()
        local observed=E.callback_diagnostics()
        if observed==nil then return nil end
        if type(observed)~='table' then error('invalid callback diagnostic envelope',0) end
        return checked_plain(observed,16384)
      end)
      if ok then failure_diagnostics.callback=callback
      else failure_diagnostics.callback_error=tostring(callback):gsub('%c',' '):sub(1,256) end
    end
    if failure_diagnostics and E and E.preflight_diagnostics then
      local ok,preflight=pcall(function()
        local observed=E.preflight_diagnostics()
        return observed and checked_plain(observed,16384)or nil
      end)
      if ok then failure_diagnostics.preflight=preflight
      else failure_diagnostics.preflight_error=tostring(preflight):gsub('%c',' '):sub(1,256)end
    end
    if extra then for k,v in pairs(extra) do details[k]=v end end
    publish('halted',true,details)
  end
  local function native(boundary)
    local raw=read('native_status.txt',4096); if not raw then return nil end
    if raw:sub(-1)~='\n' then
      read_issue('native_status.txt','incomplete','parse','missing final newline'); return nil
    end -- incomplete status is never a gate acknowledgement
    local function conflict(message)
      read_issue('native_status.txt','invalid','validate',message); error(message,0)
    end
    local values={}
    for line in raw:gmatch('[^\r\n]+') do
      local k,v=line:match('^([a-z][a-z0-9_]*)=(%d+)$')
      if not k or values[k] then conflict('invalid native gate status') end
      values[k]=v
    end
    local required={'protocol','abi','epoch','ready','initialized','armed','halted','fault','runtime_fault','probe_required','pending_state','completed_frame'}
    for _,k in ipairs(required) do if values[k]==nil then
      read_issue('native_status.txt','incomplete','parse','missing field '..k); return nil
    end end
    if values.protocol~='1' or values.abi~='3' or values.epoch~=config.epoch or values.probe_required~='1'
      or values.halted~='0' or values.fault~='0' or values.runtime_fault~='0' then conflict('native gate epoch/ABI/fault mismatch') end
    if values.native_step_us~='200000' then conflict('native gate requires explicit 200000-microsecond engine step') end
    if values.pending_state~='0' or values.completed_frame~=boundary then conflict('native gate boundary is not held and complete') end
    if values.ready~='1' or values.initialized~='1' or values.armed~='1' then
      read_issue('native_status.txt','not_ready','validate','native gate is not initialized, armed and ready'); return nil
    end
    return true
  end
  local function snapshot(expected)
    -- Preserve bounded metadata from an invalid attempt separately. Never
    -- replace last_snapshot with an observation that failed validation.
    failed_observation={valid_snapshot=false,expected_sim_time_us=expected,phase='reading'}
    local s=E.snapshot(); local canonical=json.encode(s)
    failed_observation.phase='validation'
    if type(s.sim_time_us)=='number' and s.sim_time_us==s.sim_time_us and math.abs(s.sim_time_us)<9007199254740992 then
      failed_observation.sim_time_us=s.sim_time_us
    end
    if type(s.coverage)=='table' and type(s.coverage.missing)=='table' then
      local missing=json.array({})
      for i=1,math.min(#s.coverage.missing,32) do missing[i]=tostring(s.coverage.missing[i]):sub(1,512) end
      failed_observation.missing=missing
      failed_observation.missing_count=#s.coverage.missing
    end
    if #canonical>MAX_STATE_BYTES then error('bounded tracked snapshot too large',0) end
    if expected~=nil and s.sim_time_us~=expected then error('observed simulation time differs from requested boundary',0) end
    if #s.coverage.missing>0 then error('capability_missing: '..table.concat(s.coverage.missing,'; '),0) end
    last_snapshot,last_canonical=s,canonical
    failed_observation=nil
    return canonical
  end
  local function checked_receipt(receipt)
    if type(receipt)~='table' or type(receipt.success)~='boolean' or type(receipt.result)~='table' or receipt.result==json.null then
      error('invalid engine completion receipt',0)
    end
    return checked_plain(receipt,32768) -- Own the observation; callbacks cannot mutate it later.
  end
  local function finish_completion()
    local completion=awaiting_completion
    if not completion or halted then return end
    local p=completion.plan
    if not native(p.boundary) then
      if not completion.wait_published then
        completion.wait_published=true
        publish('in_flight',false,{receipt=retained_receipt})
      else write_status() end
      return -- The next update retries observation only, never finish/sendCommand.
    end
    snapshot(p.time)
    if p.plan.command.op=='SET_PAUSED' and last_snapshot.paused~=p.plan.command.value then
      error('pause callback did not produce requested pause flag',0)
    end
    if p.plan.requested_paused~=nil then
      if config.input_mode~='guided_suite_v1' or type(p.plan.requested_paused)~='boolean'
        or last_snapshot.paused~=p.plan.requested_paused then
        error('guided pause callback did not produce requested pause flag',0)
      end
    end
    awaiting_completion=nil; in_flight=false
    if not publish('applied',true,{receipt=retained_receipt}) then
      error('applied status write failed; command cannot be retried',0)
    end
  end
  local function start()
    decimal(config.epoch,true)
    if config.profile~=nil and config.profile~='time_v1' and config.profile~='build_v2' then error('unknown measurement profile',0) end
    if config.native_gate_required~=true then error('native gate is mandatory',0) end
    if type(config.mailbox_dir)~='string' then error('absolute mailbox directory required',0) end
    path=config.mailbox_dir:gsub('\\','/'):gsub('/+$','')
    if not (path:match('^%a:/') or path:match('^/')) then error('absolute mailbox directory required',0) end
    if saved_active then error('saved active probe sessions cannot resume; prepare a fresh baseline save and epoch',0) end
    if not native('0') then return false end
    E=engine_module.new(json,config); E.bind_initial(config.initial_bindings)
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
    if c.action=='plan' or c.action=='apply' or c.action=='preview' then
      if type(c.command_key)~='string' or not c.command_key:match('^[ab]:[1-9]%d*$') or #c.command_key>96 then error('invalid command key',0) end
      if type(c.command)~='table' then error('command object required',0) end
    end
  end
  local function process(c, sig)
    if c.request==request then
      if sig~=signature then error('same request reused with different content',0) end
      if not write_status() and not awaiting_completion then error('status rewrite failed',0) end
      return
    end
    if c.request~=request+1 then error('noncontiguous request; no history skipping',0) end
    if halted then return end
    if in_flight and c.action~='halt' then error('command callback still pending',0) end
    if c.action~='halt' and not native(c.boundary) then return end
    request,signature=c.request,sig
    request_context={action=c.action,boundary=c.boundary,command_key=c.command_key,expected_sim_time_us=c.expected_sim_time_us}
    if c.action=='halt' then halt('controller requested halt'); return end
    if c.action=='snapshot' then
      if pending then error('snapshot cannot replace an unapplied plan',0) end
      snapshot(c.expected_sim_time_us)
      if not publish('ready',true) then error('snapshot status write failed',0) end
    elseif c.action=='preview' then
      if (config.input_mode~='manual_depot_v1' and config.input_mode~='guided_suite_v1')
        or type(E.preview)~='function' then error('manual preview capability not enabled',0)end
      if pending then error('preview cannot replace an unapplied plan',0)end
      local peer,seq=c.command_key:match('^([ab]):([1-9]%d*)$');seq=E.integer(seq,1)
      if seq<=seen_sequence[peer] then error('preview command key was already consumed',0)end
      local before=snapshot(c.expected_sim_time_us)
      local preview=checked_plain(E.preview(c.command,c.command_key),32768)
      if snapshot(c.expected_sim_time_us)~=before then error('manual preview changed tracked world',0)end
      if not publish('previewed',true,{preview=preview})then error('preview acknowledgement write failed',0)end
    elseif c.action=='plan' then
      if pending then error('only one unapplied plan is permitted',0) end
      retained_receipt=nil -- Earlier command receipts remain in the controller journal.
      local peer,seq=c.command_key:match('^([ab]):([1-9]%d*)$'); seq=E.integer(seq,1)
      if seq<=seen_sequence[peer] then error('command key was already planned; no command replay',0) end
      local before=snapshot(c.expected_sim_time_us)
      local plan=E.plan(c.command,c.command_key,c.expected_sim_time_us)
      if plan.read_only~=nil and (plan.read_only~=true or config.input_mode~='guided_suite_v1'
        or c.command.op~='GUIDED_ACTION' or plan.native~=nil or type(E.finish_read_only)~='function') then
        error('invalid guided observation plan',0)
      end
      seen_sequence[peer]=seq
      pending={plan=plan,key=c.command_key,boundary=c.boundary,time=c.expected_sim_time_us,command=json.encode(c.command),before=before}
      if not publish('planned',true,plan.preview and {preview=checked_plain(plan.preview,32768)}or nil) then error('plan acknowledgement write failed',0) end
    elseif c.action=='apply' then
      local p=pending
      if not p or p.key~=c.command_key or p.boundary~=c.boundary or p.time~=c.expected_sim_time_us
        or p.command~=json.encode(c.command) then error('apply differs from the prepared plan',0) end
      if snapshot(c.expected_sim_time_us)~=p.before then error('tracked world changed between plan and apply',0) end
      pending=nil; in_flight=true; retained_receipt=nil
      -- Persist in-flight before handing ownership to the engine, including
      -- when sendCommand invokes its real callback synchronously in engine Lua.
      if not publish('in_flight',false) then error('in-flight write failed; command not sent',0) end
      if p.plan.read_only==true then
        -- A held-world observation is acknowledged explicitly; no native
        -- command or synthetic engine callback is used for an observation.
        local r=E.finish_read_only(p.plan)
        r.command_key=p.key; r.boundary=p.boundary; r.bindings=E.local_bindings()
        retained_receipt=checked_receipt(r)
        if retained_receipt.success~=true or type(retained_receipt.result.effect)~='table'
          or retained_receipt.result.effect.kind~='observation' then
          error('guided observation did not produce an explicit observation receipt',0)
        end
        awaiting_completion={plan=p}
        finish_completion()
        return
      end
      local callback_called=false
      api.cmd.sendCommand(p.plan.native,function(result,success)
        if callback_called then halt('engine callback invoked more than once'); return end
        callback_called=true
        local ok,receipt=pcall(function()
          local r=E.finish(p.plan,result,success)
          if type(r)~='table' then error('invalid engine completion receipt',0) end
          r.command_key=p.key; r.boundary=p.boundary; r.bindings=E.local_bindings()
          return checked_receipt(r)
        end)
        if not ok then halt(receipt); return end
        retained_receipt=receipt
        if halted then halt('completion observed after halt',{receipt=receipt}); return end
        if receipt.success~=true then halt('engine rejected command',{receipt=receipt}); return end
        awaiting_completion={plan=p}
        local completed,problem=pcall(finish_completion)
        if not completed then halt(problem) end
      end)
    else error('unsupported control action',0) end
  end
  local function update()
    if not enabled then return end
    local ok,err=pcall(function()
      if halted then write_status(); return end
      if not started and not start() then return end
      local waiting=awaiting_completion
      local raw=read('lua_control.json',MAX_BYTES); if not raw then return end
      local decoded,c=pcall(json.decode,raw)
      if not decoded then return end -- incomplete direct write; never advance seq
      validate_control(c); process(c,json.encode(c))
      -- Consume a queued controller halt before considering any delayed ACK.
      if waiting and waiting==awaiting_completion and not halted then finish_completion() end
    end)
    if not ok then halt(err) end
  end
  return {
    update=update,
    save=function() return {strict_probe_active=enabled and started or false,epoch=enabled and config.epoch or ''} end,
    load=function(state) if enabled and type(state)=='table' and state.strict_probe_active==true then saved_active=true end end,
  }
end
