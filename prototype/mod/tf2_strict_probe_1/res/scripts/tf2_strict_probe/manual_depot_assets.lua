-- Bounded manual placement sites relative to the established test scene.
-- The installed stock depot's road, collider and terrain-alignment geometry
-- fit inside this 45 m clearance box for all four quarter-turn rotations.
return {
  contract='manual_depot_v1',
  sites={{-90,-100},{90,-100},{-90,90},{90,90}},
  rotations={[0]={1,0,0,1},[90]={0,1,-1,0},[180]={-1,0,0,-1},[270]={0,-1,1,0}},
  half_extent=45,
  max_height_span=8,
  max_placements=4,
}
