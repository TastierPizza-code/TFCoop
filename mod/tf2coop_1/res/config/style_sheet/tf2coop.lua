local ssu = require 'stylesheetutil'
function data()
  local result = {}
  local add = ssu.makeAdder(result)
  local colors = { {96,165,250}, {244,114,182}, {52,211,153}, {251,191,36}, {167,139,250}, {251,146,60}, {34,211,238}, {248,113,113} }
  for i, c in ipairs(colors) do add('!tf2coop_color_' .. i, { color = { c[1]/255, c[2]/255, c[3]/255, 1 } }) end
  add('TF2CoopPanel', { padding = { 12, 16, 12, 16 } })
  return result
end
