local config=require 'tf2_api_audit/config'
local json=require 'tf2_api_audit/json'
local probe=require 'tf2_api_audit/probe'
function data()
  local done,updates,attempts,raw=false,0,0,nil
  local retry_wait=0
  local function failure(reason)
    return {format=1,mode='read_only_api_audit',request_id=probe.safe_text(config.request_id or ''),
      status='error',valid_snapshot=false,records=json.array(),limits={max_bytes=98304},
      truncated=false,error=probe.safe_text(reason)}
  end
  local function ready()
    local id=api.engine.util.getPlayer()
    return type(id)=='number'and id>=0 and api.engine.entityExists(id)and game.interface.getEntity(id)~=nil
  end
  local function write_once()
    attempts=attempts+1
    local path=config.output_file..'.part'
    local opened,f=pcall(io.open,path,'wb')
    if not opened or not f then return false end
    local ok,wrote=pcall(function()return f:write(raw)end)
    local closed,result=pcall(function()return f:close()end)
    if not ok or not wrote or not closed or not result then return false end
    local renamed,value=pcall(os.rename,path,config.output_file)
    return renamed and value~=nil and value~=false
  end
  return {update=function()
    if done or config.enabled~=true then return end
    if type(config.request_id)~='string'or not config.request_id:match('^[a-f0-9]+$')or #config.request_id~=32
      or type(config.output_file)~='string'or #config.output_file>4096
      or not (config.output_file:match('^%a:[/\\]')or config.output_file:match('^/'))
      or not config.output_file:match('%.json$')then done=true;return end
    -- Give a transient file lock time to clear. Retain the original raw
    -- observation throughout retries; do not sample a later game state.
    if retry_wait>0 then retry_wait=retry_wait-1;return end
    if not raw then
      updates=updates+1
      local ok,available=pcall(ready)
      if (not ok or not available)and updates<600 then return end
      local result
      if not ok or not available then result=failure('player/entity unavailable after 600 updates')
      else
        local collected,value=pcall(probe.collect,api,game,json,{request_id=config.request_id})
        result=collected and value or failure(value)
      end
      local encoded,value=pcall(json.encode,result)
      if not encoded or #value>98304 then value=json.encode(failure('diagnostic encoding failed'))end
      raw=value
    end
    if write_once()or attempts>=3 then done=true else retry_wait=30 end
  end,save=function()return {}end,load=function()end}
end
