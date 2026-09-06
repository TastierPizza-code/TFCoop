-- Fixed, versioned automatic test scene. Stock resources are referenced only;
-- the package contains no copied game models or construction implementations.
local function module(name, metadata)
  return {name=name, metadata=metadata, variant=0, updateScript={fileName='',params={}}}
end

return {
  id='road-depot-service-v3',
  road_file='tf2_strict_probe/road_test.con',
  depot_file='depot/road_depot_era_a.con',
  stop_file='station/street/modular_terminal.con',
  vehicle_model='vehicle/bus/usa/horse_carriage_v2.mdl',
  -- Selection must be made and compared by both peers before the first build.
  -- A repository index is evidence of a loaded resource, not GUI visibility.
  vehicle_models={
    'vehicle/bus/postkutsche_v2.mdl',
    'vehicle/bus/usa/horse_carriage_v2.mdl',
    'vehicle/bus/asia/troika_v2.mdl',
  },
  street_type='standard/town_medium_old.lua',
  road_params={seed=1},
  depot_params={seed=1,year=1850,paramX=0,paramY=0},
  -- These slots are produced by the stock 1850 template with platL=platR=1
  -- and length=0. The template itself is not needed when building explicitly.
  stop_params={seed=1,year=1850,paramX=0,paramY=0,tramTrack=0,modules={
    [20009900]=module('station/street/passenger_platform.module',{passenger=true,price=12000}),
    [20010000]=module('station/street/passenger_platform.module',{passenger=true,price=12000}),
    [20015503]=module('station/street/entrance_exit.module',{price=25000}),
  }},
  -- Script construction placement does not perform the UI's nodes2snap weld.
  -- Keep distinct outer nodes, then join their observed IDs with normal edges.
  depot_offset={0,90.4153,0},
  stop_offsets={{-135,0,0},{135,0,0}},
  depot_snap={0,-30.4153,0},
  stop_snap={0,-35,0},
  connect_gap=20,
  connection_tolerance=0.01,
  -- Rotation columns (xx,yx,xy,yy): +90 degrees and -90 degrees exactly.
  stop_rotations={{0,1,-1,0},{0,-1,1,0}},
  road_endpoints={{-80,0,0},{80,0,0},{0,40,0}},
  road_junction={0,0,0},
  half_extent=180,
  preferred_height_span=2,
  max_height_span=8,
  vehicle_load_config={0},
  vehicle_auto_load_config={1},
  vehicle_groups={1},
}
