local config=require 'tf2_api_audit/config'
local json=require 'tf2_api_audit/json'
local probe=require 'tf2_api_audit/probe'
function data()
  local done,updates,attempts,raw=false,0,0,nil
  local retry_wait,staged,load_seen,first_update,waiting=0,false,false,false,false
  local function public_error(value)
    local text=probe.safe_text(value):gsub('[%c]',' ')
    -- Native I/O and Lua errors can contain an absolute filename. Keep their
    -- final diagnostic clause, never the machine's path or a raw opaque value.
    if text:find('%a:[/\\]')or text:find('^[/\\]')then
      text=text:match(': ([^:]+)$')or 'path-bearing error'
    end
    return text
  end
  local function log(status,reason)
    if config.enabled~=true then return end
    local id=type(config.request_id)=='string'and config.request_id:match('^[a-f0-9]+$')
      and #config.request_id==32 and config.request_id or 'invalid'
    local message='TF2_API_AUDIT id='..id..' status='..status
    if reason~=nil then message=message..' failure='..public_error(reason)end
    pcall(print,message)
  end
  log('script_loaded')
  local function failure(reason)
    return {format=1,mode='read_only_api_audit',request_id=probe.safe_text(config.request_id or ''),
      status='error',valid_snapshot=false,records=json.array(),limits={max_bytes=98304},
      truncated=false,error=probe.safe_text(reason)}
  end
  local function ready()
    local id=api.engine.util.getPlayer()
    return type(id)=='number'and id>=0 and api.engine.entityExists(id)and game.interface.getEntity(id)~=nil
  end
  local function write_file(path,label)
    log(label..'_open')
    local opened,f,open_error=pcall(io.open,path,'wb')
    if not opened or not f then log(label..'_open_failed',opened and open_error or f);return false end
    local ok,wrote,write_error=pcall(function()return f:write(raw)end)
    local closed,result,close_error=pcall(function()return f:close()end)
    if not ok then log(label..'_write_threw',wrote)
    elseif not wrote then log(label..'_write_failed',write_error or 'write returned '..type(wrote))end
    if not closed then log(label..'_close_threw',result)
    elseif not result then log(label..'_close_failed',close_error or 'close returned '..type(result))end
    if not ok or not wrote or not closed or not result then return false end
    log(label..'_closed');return true
  end
  local function verify_final()
    local opened,f,open_error=pcall(io.open,config.output_file,'rb')
    if not opened or not f then log('final_readback_open_failed',opened and open_error or f);return false end
    local ok,read,read_error=pcall(function()return f:read(98305)end)
    local closed,result,close_error=pcall(function()return f:close()end)
    if not ok then log('final_readback_threw',read)
    elseif read~=raw then log('final_readback_mismatch',read_error or 'bytes differ from collected report')end
    if not closed then log('final_readback_close_threw',result)
    elseif not result then log('final_readback_close_failed',close_error or 'close returned '..type(result))end
    return ok and read==raw and closed and result~=nil and result~=false
  end
  local function write_once()
    attempts=attempts+1
    if not staged then
      if not write_file(config.output_file..'.part','staging')then return false end
      staged=true
    end
    -- Some game Lua environments cannot publish through os.rename. Retain a
    -- complete staging report for recovery, then write the final diagnostic.
    -- The launcher rejects partial JSON; this file is never a simulation ACK.
    return write_file(config.output_file,'final')and verify_final()
  end
  return {update=function()
    if done or config.enabled~=true then return end
    if not first_update then first_update=true;log('first_update')end
    if type(config.request_id)~='string'or not config.request_id:match('^[a-f0-9]+$')or #config.request_id~=32
      or type(config.output_file)~='string'or #config.output_file>4096
      or not (config.output_file:match('^%a:[/\\]')or config.output_file:match('^/'))
      or not config.output_file:match('%.json$')then done=true;log('invalid_configuration');return end
    -- Give a transient file lock time to clear. Retain the original raw
    -- observation throughout retries; do not sample a later game state.
    if retry_wait>0 then retry_wait=retry_wait-1;return end
    if not raw then
      updates=updates+1
      local ok,available=pcall(ready)
      if (not ok or not available)and updates<600 then
        if not waiting then waiting=true;log('waiting_for_player',not ok and available or nil)end
        return
      end
      local result
      if not ok or not available then result=failure('player/entity unavailable after 600 updates')
      else
        local collected,value=pcall(probe.collect,api,game,json,{request_id=config.request_id})
        result=collected and value or failure(value)
        if collected then log('collected')else log('collection_failed',value)end
      end
      local encoded,value=pcall(json.encode,result)
      if not encoded or #value>98304 then value=json.encode(failure('diagnostic encoding failed'))end
      raw=value
    end
    if write_once()then done=true;log('published')
    elseif attempts>=3 then done=true;log('write_attempts_exhausted')
    else retry_wait=30;log('write_retry_wait')end
  end,save=function()return {}end,load=function()
    if not load_seen then load_seen=true;log('load_callback')end
  end}
end
