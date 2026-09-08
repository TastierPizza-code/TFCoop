-- Explicit ProposalData field-shape fixture, not an actual game preflight.
manual_preflight_calls=0
api.engine.util.proposal={makeProposalData=function(proposal,context)
  manual_preflight_calls=manual_preflight_calls+1
  assert(#proposal.constructionsToAdd==1 and #proposal.constructionsToRemove==0)
  assert(#proposal.streetProposal.edgesToAdd==0 and context.checkTerrainAlignment==true)
  local construction=proposal.constructionsToAdd[1]
  assert(construction.fileName==assets.depot_file and construction.playerEntity==1)
  if manual_proposal_hook then manual_proposal_hook(proposal,context,manual_preflight_calls)end
  if manual_bad_schema then return native_record({errorState=native_record({critical=false})})end
  return native_record({errorState=native_record({critical=manual_critical==true,messages=manual_messages or {}}),
    costs=manual_cost or 10000})
end}
local original_octree=api.engine.system.octreeSystem.findIntersectingEntities
api.engine.system.octreeSystem.findIntersectingEntities=function(box,callback)
  original_octree(box,callback)
  if manual_occupied and math.abs(box.max.x-box.min.x-90)<.001 then
    world[900000]={CONSTRUCTION={}}
    callback(900000)
  end
end
