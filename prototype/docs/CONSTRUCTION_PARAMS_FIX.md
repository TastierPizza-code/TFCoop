# Observed construction parameters: Alpha5.1 stop and reader fix

The reported Alpha5.1 test stopped after the road construction callback because
the snapshot reader accepted only ordinary Lua tables. TF2 exposes construction
parameters through native containers as well. The corrected reader enumerates
their actual values and retains them in the shared state comparison.

## Evidence from the supplied report

Source: `TF2-Alpha5.1-Bericht-a-20260906-213105.zip`, supplied by the host on
2026-09-06. The package contains the host's coordinated action log and local
Lua/native status; it does not contain a complete construction snapshot after
the failure.

- Site search v2 succeeded. It examined 4,225 candidates, selected candidate
  603 at x=3,011 m, y=-2,510 m, and measured a 2.583335876 m height span.
- The host dispatched road command `a:2` to both peers in round 1. The local
  successful construction callback bound it to entity 46746.
- Snapshot conversion failed with
  `capability_missing: a:2:nonplain observed params`.
- The host then dispatched halt to both peers. Native status recorded one
  completed pause permit, zero advance permits, and unchanged simulation time
  13,400 ms. Runtime fault and Win32 error were zero. One status-file replacement
  retry had recovered from Windows error 5.

The failing guard did not record the exact rejected Lua type or nested path.
Native userdata is the supported API representation missing from that guard;
the report alone does not prove the precise native container class. Successful
callback identity confirms creation, but the interrupted read does not prove
that the resulting road, terrain and charges matched on both PCs.

## API basis and implementation

The official [Construction component reference](https://wiki.transportfever2.com/api/modules/api.type.html#Construction)
describes `params` as the parameters passed to the construction's `updateFn`.
The installed game's `res/scripts/serialize.lua` (userdata branch, lines 95–137)
demonstrates two supported enumeration contracts: `pairs` for native containers
and a native metatable `__members` list for members accessible by name.

`build_engine.lua` now reads plain tables and native userdata recursively through
those contracts. Native and plain containers with the same contents produce
the same canonical state. All observed fields, including engine-added nested
parameters, are retained. Numeric and string keys remain distinct; scalar type
tags also distinguish a numeric value from an identically formatted string.
Numbers retain the existing finite-value and 17-significant-digit encoding.

The traversal is bounded to depth 10, 256 entries per container, 4,096 visited
values, and 1 MiB of key/value text. Cycles, duplicate keys, unsupported values,
unreadable members and iterator failures make the snapshot unavailable and halt
the measurement. An iterator that fails after producing some entries cannot
silently fall back to another representation or produce a partial successful
snapshot. No native pointer text, requested recipe, empty default, or legacy
entity lookup substitutes for unreadable parameters.

## Validation

`py -3.10 prototype/mod/tf2_strict_probe_1/tests/test_build_engine.py` passes
26 cases under each of Lua 5.1, 5.2, 5.3 and 5.4: 104 checks, zero skips.
The fixture creates genuine userdata with private metatables using already
closed temporary handles; it does not override Lua's `type`. Every construction
callback now stores nested userdata parameters by default, so the full build
scene tests exercise the missing API shape. Additional cases cover member-list
containers, mixed numeric/string keys, engine-added fields, scalar type changes,
opaque userdata, a partially failing iterator, unreadable members, cycles and
the depth, width, aggregate node and text limits.

Loading the shipped Alpha5.1 reader against the genuine-userdata fixture
reproduces exactly `a:2:nonplain observed params`; the corrected reader passes.
`py -3.10 -m unittest prototype.tests.test_build_mailbox_lua -q` also passes both
tests in 156.664 seconds. Its two literal Lua peers complete all 240 shared
boundaries through the real file mailbox, with different local entity IDs,
nested userdata construction parameters and matching final movement proof.

These are literal production Lua tests with explicit game API fixtures. They
do not replace the next real two-PC TF2 run or establish complete-world
determinism.
