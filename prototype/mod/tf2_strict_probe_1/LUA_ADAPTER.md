# Controlled Lua adapter — experimental, disabled by default

This is a bounded engine integration test. It does not capture or cancel stock UI
commands, provide free building, synchronize the entire world, install itself, or
start the game. The separate native step gate owns simulation advancement. The
only clock-setting command here is an explicit, jointly committed `SET_PAUSED`.

## Activation and baseline

The Alpha5.8 launcher explicitly selects `profile="build_v2"`. This selects
`build_engine.lua`, a separate fixed recipe adapter with no manually supplied
bindings. It creates a custom `STREET_CONSTRUCTION`, stock depot and two stock
passenger stops, explicitly connects their separated endpoints, buys an available
1850 passenger vehicle, creates a line and assigns the vehicle. Construction and
vehicle identities come from actual callback results and authoritative component
children. Connection edges are verified by an exact incident-graph difference
at the six known endpoint IDs, since ordinary street callbacks can return no IDs.
Every intended pair needs exactly one new matching edge; all old incident edges
must be unchanged. All three results are validated before committing bindings.
Native incidence collections are enumerated through their actual iterator rather
than assumed to be 1-indexed arrays. Count, finite integer entity values,
uniqueness and endpoint checks remain mandatory; ordered arrays keep their
existing readers. The unordered `getLineVehicles` membership query uses the same
bounded reader (at most one test vehicle), matching local upstream value-iteration
usage. Its concrete native container type has not yet been observed in this test.
The real Alpha5.7 run confirmed the four constructions during
pause but stopped in connection planning before dispatch; no vehicle was bought.
StationGroup/Construction identity aliases
are allowed when confirmed by the station-group API. The observed shared node
graph must connect all constructions before purchase. Vehicle configurations
use read/modify/write for copied vector properties and verify the result.

Site selection reads actual water level and terrain samples and rejects occupied
or unsuitable footprints before mutation. The recipe, chosen assets and site
join the initial snapshot. Transient missing world-position data is explicit;
the final Python proof still requires actual departure and movement. See
`BUILD_TEST.md` in the portable package for the schedule and proof limits.
This new construction flow has not yet passed a real TF2 two-player run.

The following generic adapter details describe `time_v1` or the legacy omitted
profile; the generic `ROAD` operation remains unsupported.

`res/scripts/tf2_strict_probe/config.lua` is local configuration and is excluded
from shared code hashes. It requires `enabled=true`, a fresh positive uint64
decimal-string `epoch`, an absolute `mailbox_dir`, `native_gate_required=true`,
and `initial_bindings`. Source defaults are disabled, empty epoch/path/bindings.

Bindings are an array of `{logical_id,kind,entity}` from the actual prepared save.
Kinds are `depot`, `vehicle`, `line`, `station_group`, and `road`. A depot must
contain exactly one actual `VEHICLE_DEPOT` child, automatically bound as
`<logical_id>:depot:1`. No numeric example ID or asset is a usable default.
Parked vehicles must be explicitly bound; spatial enumeration is not used.
Empty bindings provide the company/time observation probe.

An active session stored into a save cannot silently resume: its save marker
causes a halt. A fresh baseline and epoch are required. Startup waits for native
ABI 3, explicit `native_step_us=200000`, the same local epoch,
armed/initialized/ready, completed boundary `0`, no pending permit, and no fault.
The native controller permits exactly 200000 microseconds (200 milliseconds)
per advancing boundary, or zero for a paused boundary. ABI 2 and missing or
different step declarations halt before command dispatch. Partial native status
files without their final newline are never acknowledged. Startup publishes
request `0` with the actual loaded time and snapshot. An already present request
`1` is processed normally.

## Mailbox protocol 1

The exclusive controller writes `lua_control.json`; engine-state `update`
processes it. The adapter writes `lua_status.json`. Each file is bounded at
262144 bytes. A tracked snapshot is bounded at 100000 bytes so its canonical
copy and surrounding status fit. JSON is parsed as data, never evaluated.
Reads of partial JSON wait for a complete document without advancing sequence.
The native status file `native_status.txt` is independently bounded at 4096 bytes.

Alpha5.1 leaves each successfully published Lua status revision untouched while
polling the same command again. This avoids repeatedly truncating a larger
acknowledgement file while Python reads it. A new revision is always written;
unsuccessful publication remains retryable in the terminal halted state. The
in-flight publication still must succeed before the engine command is sent.

Control fields:

```json
{"protocol":1,"epoch":"77","request":1,"action":"snapshot","boundary":"0","expected_sim_time_us":100000000}
```

Actions are `snapshot`, `plan`, `apply`, and terminal `halt`. Plan/apply also
require `command_key` (`a:<positive sequence>` or `b:<positive sequence>`) and
`command`. `request` is contiguous and starts at 1. `boundary` is a uint64 decimal
string; time is an exact-range JSON integer. The controller must not issue native
permits while a plan/application is outstanding. Native status is checked again
before every new operation and after real completion.

Plan validates current time, readable tracked coverage, and a complete native
command but does not send it. Apply must match the prepared key, command,
boundary, time, and full tracked snapshot. At most one plan/callback is pending.
An `in_flight` status must be successfully written before `sendCommand` runs.
Actual engine callbacks may be synchronous or asynchronous. Only that callback
can produce `applied`; success without its required exact entity ID halts.
No fake success callback is invoked. A callback after halt is recorded without
resuming the session. Duplicate callbacks, sequence gaps, changed duplicates,
and previously planned command keys halt. Per-peer sequence watermarks bound
deduplication memory rather than retaining an unbounded command history.

Status contains protocol/epoch/request/revision/status/complete, `snapshot`,
`canonical_state_json`, and local diagnostic bindings. Applied receipts contain
`command_key`, `boundary`, actual `success`, and shared logical `result`.
Creation results are `{logical_id:command_key}`, updates `{target:logical_id}`,
and pause results `{paused:boolean}`. Actual numeric `result_entity` and
`bindings` are diagnostics only; the Python adapter excludes them from shared
receipt and state hashes.

## Intents and actual support

| Intent | Required command fields | Status |
|---|---|---|
| `SET_PAUSED` | `value` boolean | Implemented with actual pause callback and observed pause flag. |
| `DEPOT` | bound `template`, explicit 16-value rigid affine `transform`, `name`, `context`, `ignore_errors` | Clones actual source construction file and parameters; requires one returned construction and one actual depot child. No automatic connecting road is constructed. |
| `LINE_CREATE` | `name`, 3-value unit `color`, `waiting_time`, `stops` | Uses the documented exact result entity; missing getter/result halts. |
| `LINE_UPDATE` | bound `line`, `waiting_time`, `stops` | Sends the full controlled stop configuration. |
| `VEHICLE_BUY` | bound vehicle `template`, bound construction `depot`, explicit `purchase_time_ms` | Copies actual models, reversal, color, logo, load configuration, groups, maintenance values, and auto-load values. Purchase time must equal current positive simulation milliseconds. Depot/template carriers must agree. |
| `VEHICLE_ASSIGN` | bound `vehicle`, bound `line`, explicit `stop_index` | Validates actual line length before dispatch. |
| `ROAD` | Reserved schema: `points_mm`, `street`, `has_bus`, `tram_track_type`, `context`, `ignore_errors` | **Not implemented: PLAN returns `capability_missing` before constructing/sending a command.** |

`context` requires explicit booleans `checkTerrainAlignment`,
`cleanupStreetGraph`, `gatherBuildings`, and `gatherFields`; player is the actual
current company. Stop fields are `station_group`, zero-based `station` and
`terminal`, `load_mode` 0–2, `min_wait`, `max_wait`, `alternative_terminals`, and
`waypoints`. The latter two must be empty; station/terminal bounds come from
actual components. Decimal parameters can be exact decimal strings. No street,
depot, vehicle model, transform, stop, or template is selected automatically.

ROAD is deliberately unavailable: upstream
`upstream/tpf2-multiplayer/mod/mp_lockstep_1/res/config/game_script/lockstep.lua:628`
records a measured empty `resultEntities` vector for street/track builds and
falls back to endpoint geometry. An exact native created-edge result mapping
has not been implemented here. Matching geometry would reintroduce ambiguity.

## Snapshot scope and remaining integration work

The digest covers actual company balance/loan and simulation microseconds,
observed pause, all explicitly tracked objects, route/stop definitions and
membership, vehicle stopped/state/depot/line/target-terminal/timers/capacities,
complete tracked vehicle-part configuration, observed vehicle position,
construction parameters/transform/name/build time/depot animation, and tracked
street geometry/properties. Canonical road-node symbols preserve actual node
sharing: identical coordinates with separate nodes produce different snapshots.
Local entity/resource indices do not enter the canonical snapshot. Noninteger
engine numbers are preserved as 17-digit decimal strings rather than rounded.

`coverage.complete_world` is always false. Cargo contents, reservations, terrain,
RNG, untracked objects/connectivity, station internals, and extended line cargo
policy are explicitly excluded. Missing requested component data halts instead
of substituting zero/empty values. Limits include 64 logical bindings, 4 vehicle
parts/groups, 32 stops, and bounded construction data. The initial controlled
construction snapshot supports frozen street edges; other construction graphs
can report missing capability.

Stock UI intent capture/cancellation, authoritative road result mapping,
complete world/RNG serialization, and proof that paused maintenance cannot
change excluded world state are **not implemented**. The native gate still
allows maintenance; this mod assumes one exclusive controller and no concurrent
ordinary building actions. The first actual native probe held the game for 206
updates but crashed on its first 100-millisecond advance with the engine's
`dt >= .2f` assertion. ABI 3 consequently requires 200 milliseconds. That change
still needs an actual successful game run. Readable native getters and callback
behavior must still be observed on the fingerprinted game build; unavailable
surfaces fail closed.

## Evidence and verification

The [official command API](https://wiki.transportfever2.com/api/modules/api.cmd.html)
documents execution/callback timing differences between engine and GUI states.
The [official type API](https://wiki.transportfever2.com/api/modules/api.type.html)
documents CreateLine and BuyVehicle result IDs, construction results, vehicle
configuration, station terminals, and depot/vehicle components. Local upstream
execution paths substantiate construction name/player fields, matrix indexing,
vehicle configuration setters, company reads, and simulation-time reads. The
empty road result above takes precedence over a fake engine fixture.

Run the literal production Lua tests from the repository root:

```powershell
py -3.10 prototype/mod/tf2_strict_probe_1/tests/test_literal_lua.py
```

28 scenarios pass on Lua 5.1, 5.2, 5.3, and 5.4: 112 executions. They cover native
status checks, old ABI and invalid/missing step rejection, partial native files,
200-millisecond boundaries, zero-time startup, no history skipping, exact-once dispatch,
sync/async callbacks, actual entity binding, callback loss/failure, template
preservation, tracked drift, topology ambiguity, missing fields, bounded IO,
write failures, disabled operation, saved-session replay, and ROAD refusal.
`tests/fake_engine.lua` is test-only. These tests prove adapter behavior under
the declared API contract; they do not establish engine determinism or usable
free-building multiplayer.
