# Alpha5.3: native member lookup and Lua return arity

The Alpha5.2 host report stopped in round 1 at `a:2`, while reading the
construction transform: `build_engine.lua:25: bad argument #1 to 'type'
(value expected)`. The road callback bound construction entity 46746. Native
status recorded one pause permit, zero advance permits and unchanged simulation
time of 13,400 ms. Native fault, runtime fault and Win32 error were all zero.
The report is kept privately; no save or report archive is published.

The helper `field(value, key)` caught failed native member reads with `pcall`
but fell off the end of its function on failure. In Lua this returns **zero
values**, which is different from returning one `nil`. When that helper was the
only argument to `type`, the standard function received no argument at all.

The matrix reader checks for a `col` method before using its existing indexed
representation. A native object may reject this named lookup. A plain Lua table
would return `nil` instead, so the earlier table-shaped transform fixture did
not reproduce the failure. The same helper issue also affected the callback
reader's `tonumber(field(result, name))`: a missing optional result member could
abort before the alternative actual result member was inspected.

Alpha5.3 makes both strict-adapter field helpers explicitly return one `nil`
after a failed optional lookup. Required components, finite numeric values,
matrix entries and exact callback identities remain required. Missing data is
never replaced with an identity transform, zero, guessed entity or requested
construction recipe.

The [official type reference](https://wiki.transportfever2.com/api/modules/api.type.html#Class_Mat4f)
documents `Construction.transf` as `Mat4f`, including a column method and indexed
access. The failed report does not record the exact native transform class or
its index layout. This fix preserves the existing supported representations;
it does not claim the report proves a new one.

Regression fixtures now model native member-access errors and verify both the
successful alternate access paths and failure for mandatory unreadable data.
The exact old `type` failure is reproducible against the shipped Alpha5.2
reader. Test totals and the full file-mailbox integration result are recorded
in `../VERIFICATION.md`.

These are headless tests with explicit game API fixtures. A new actual TF2 run
on both PCs is still required; neither full-world determinism nor free building
is established by this correction.
