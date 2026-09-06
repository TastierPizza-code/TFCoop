-- Enabling requires a fresh epoch and an explicitly prepared test save.
-- No game files are edited by the prototype build. There are no default assets.
return {
  enabled = false,
  epoch = "",
  mailbox_dir = "",
  native_gate_required = true,
  initial_bindings = {},
  -- Example shape only: { logical_id="seed:depot", kind="depot", entity=123 }
  -- Supported kinds: depot, vehicle, line, station_group, road.
  -- Set IDs only from the actual prepared save; never copy these example numbers.
}
