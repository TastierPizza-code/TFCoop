-- Authored bounded recipe; stock resources are referenced, never redistributed.
local A={contract='guided_rail_v1',name_contract='observed_vehicle_name_v1',
  station='station/rail/modular_station/modular_station.con',depot='depot/train_depot_era_a.con',
  track='standard.lua',signal='railroad/signal_path_a.mdl',waypoint='railroad/signal_waypoint.mdl',
  locomotive='vehicle/train/d1_3_v2.mdl',coach='vehicle/waggon/d1_spanischb_v2.mdl',
  train_name='Host und Freund - Zug',line_name='TFCoop T2 Bahnlinie',
  actions={'PAUSE','BUILD_STATION_A','BUILD_STATION_B','BUILD_RAIL_DEPOT','CONNECT_RAIL',
    'ADD_SIGNAL_A','ADD_SIGNAL_B','ADD_WAYPOINT','VERIFY_RAIL_GRAPH','BUY_TRAIN','CREATE_LINE',
    'ADD_STOP_A','ADD_STOP_B','RENAME_TRAIN','TRAIN_MAINTENANCE','ASSIGN_TRAIN','RESUME',
    'VERIFY_TRAIN_MOVEMENT','STOP_TRAIN','START_TRAIN','REVERSE_TRAIN','SEND_DEPOT','VERIFY_DEPOT',
    'PAUSE','REPLACE_TRAIN','CLONE_TRAIN','SELL_CLONE','SELL_TRAIN','DELETE_LINE','REMOVE_WAYPOINT',
    'REMOVE_SIGNAL_A','REMOVE_SIGNAL_B','REMOVE_CONNECTORS','REMOVE_RAIL_DEPOT','REMOVE_STATION_B',
    'REMOVE_STATION_A','RESUME'},
  offsets={station_a={0,-160,0},station_b={0,160,0},depot={145,-100,0}},
  -- Exact module slots produced by the installed stock template for year1850,
  -- templateIndex0, tracks0, length0, trackType0, catenary0 (80m, one track).
  station_modules={
    [3400020]='station/rail/modular_station/main_building_1_era_a.module',
    [7400000]='station/rail/modular_station/platform_passenger_era_a.module',
    [7400010]='station/rail/modular_station/platform_passenger_era_a.module',
    [8401000]='station/rail/modular_station/platform_track.module',
    [8401010]='station/rail/modular_station/platform_track.module',
    [10800000]='station/rail/modular_station/addon_platform_passenger_stairs_era_a.module',
    [10400000]='station/rail/modular_station/platform_passenger_roof_era_a.module',
    [10400010]='station/rail/modular_station/platform_passenger_roof_era_a.module'},
  excluded={'signal_animation_color_meaning','arbitrary_rail_reservations','cargo_contents',
    'native_ui_commands','free_building','localized_automatic_vehicle_text'},
}
return A
