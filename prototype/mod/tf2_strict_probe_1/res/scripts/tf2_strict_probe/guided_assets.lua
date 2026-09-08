-- Bounded action identities, shared with guided_catalog.py. Only our recipe
-- and references are shipped, never stock game resources or a private save.
return {
  contract='guided_suite_v1',
  line_name='TFCoop Rundgang Linie', renamed_line='Host und Freund - Linie',
  vehicle_name='Host und Freund - Bus',
  initial_color={0.1,0.5,0.9}, line_color={0.75,0.25,0.5},
  actions={
    'PAUSE','BUY_BUS','CREATE_LINE','ADD_STOP_A','ADD_STOP_B',
    'REMOVE_STOP_B','RESTORE_STOP_B',
    'RENAME_LINE','COLOR_LINE','RENAME_BUS','MAINTENANCE','ASSIGN_BUS',
    'RESUME','VERIFY_MOVEMENT','STOP_BUS','START_BUS','PAUSE',
    'REVERSE_STOPS','RESTORE_STOPS','LINE_RULES','REVERSE_BUS','RESUME',
    'SEND_DEPOT','VERIFY_DEPOT','SELL_BUS','DELETE_LINE',
  },
  roles={'a','b','a','b','a','b','a','b','a','b','a','b','a','b',
    'a','b','b','a','b','a','b','a','b','a','b','a'},
  required_makers={'setGameSpeed','buyVehicle','createLine','updateLine',
    'setName','setColor','setVehicleTargetMaintenanceState','setLine',
    'setUserStopped','reverseVehicle','sendToDepot','sellVehicle','deleteLine'},
  -- This is a list of contracts still absent, not successful capability tests.
  blocked_chapters={
    {id='rail_signal_train',missing={
      'fixed_track_station_depot_graph_and_signal_edge_identity',
      'multi_part_train_config_and_reverse_observation',
      'rail_path_reservations_and_departure_postconditions'}},
    {id='cargo',missing={'documented_stop_cargo_field_and_actual_cargo_observation'}},
    {id='terrain_and_demolition',missing={'terrain_and_dependent_removal_result_contract'}},
    {id='company_credit',missing={'actual_loan_command_and_journal_delta_contract'}},
  },
}
