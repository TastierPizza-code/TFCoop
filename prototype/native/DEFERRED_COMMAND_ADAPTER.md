# Deferred native commands: implemented adapter, pending game wiring

This is a separate prototype. It changes no Alpha files, installs no DLL, starts
no game, and installs no hook. Native queue tests use an explicitly fake engine.

## Implemented

`DeferredCommandQueue` retains the complete native command, completion function,
and fifth `CommandList::Add` argument. It moves ownership before the intercepted
caller's stack can expire. Commands are submitted only after a protocol grant,
in consecutive global order, at the exact granted boundary. Boundary **zero** is
valid. A game pause does not become a future-time prerequisite.

The adapter calls the original Add with the original completion function. It
never calls a completion function early, fabricates a successful result, or
guesses a new entity from the world. Add return means **submitted**. Only a real
apply observer can call `report_applied`; its actual entity is then exposed by
`take_result`. Failure halts the queue. A reentrant completion cannot recycle a
slot before Add returns.

The capacity is 32 outstanding commands, including commands waiting for their
actual result. Every rejection halts the queue and leaves the caller's objects
and return storage untouched. This is **not** permission to fall through to
ordinary local execution. In an active co-op session, the future hook must keep
the simulation halted and surface the failed admission.

No implicit recovery executes old commands after a connection loss. Destroying
retained objects without calling their UI callbacks is allowed only after the
world has detached. Call `shutdown(true)` on the original producer thread before
destroying the queue while game code is still available. The queue destructor
does not guess this lifetime; if the owner violates the shutdown contract it
leaks remaining native objects instead of calling game code on a wrong thread or
after unload. Commands already submitted are owned by the game, including their
callbacks, and the world must drain/destroy those during its own detachment.

## New static evidence against the installed executable

Build 35924, SHA256
`782b904a8f7bbdac1f7a18528f1a5c778691e5aa3087c37c351bf6912585175c`,
PE timestamp `0x675abcc6`, image size `0x046ce000`. All following addresses are
RVAs. The executable was read and disassembled headlessly; no live memory was
changed and none of these addresses was called in the game.

| Evidence | Address | Consequence |
|---|---|---|
| Add copies `r9` to `rbx`, then reads `[rbx+0x38]` | `0x9d2a30`, `0x9d2ac6`, `0x9d2b79` | `r9` is a 64-byte MSVC `std::function`, not necessarily its implementation object. |
| For inline function storage, Add calls vtable slot 1 to move, slot 4 to destroy the old inline object; for heap storage it transfers the implementation pointer | `0x9d2b82..0x9d2bb8` | Both representations must be retained correctly. |
| Buy's callback allocator requests `0x60` bytes and returns its heap implementation | `0x73ed22..0x73edb8` | It cannot be interpreted as the road tool's inline lambda. |
| Buy stores that pointer at `[rbp+0x240]`, then supplies `r9=[rbp+0x208]` | `0x74fd11`, `0x74fd92` | The old hook's direct `r9`-as-vtable assumption explains its failed callback dispatch. |
| Buy callback vtable slots | `0x30440d0` | Copy `0x751d30`, Move `0x7546c0`, DoCall `0x753820`, Type `0x754c60`, Delete `0x752400`. |
| Buy DoCall forwards to `0x748250`; that function checks payload tag 13 and reads the actual result field | `0x753820`, `0x748286..0x748296` | The callback needs the actual executed command, including payload `+0x38`. Correcting the pointer alone does not justify firing it before execution. |
| Add appends a command with a helper that transfers pointers and zeros source fields | `0x9d2aa6..0x9d2ab1`, helper `0x9d03e0..0x9d0446` | Command is a 56-byte move-owned object, not network-serializable bytes. |
| Add destroys its consumed command argument | `0x9d2ad6..0x9d2ad9`, `0x9d2c8d..0x9d2c90` | Native destroy helper is `0x9d0510`. Caller ownership must match Add's by-value ABI. |
| Fifth argument is transferred into command `+0x20/+0x28`; source pair is zeroed and weak count uses control block `+0xc`, vtable slot 1 on final release | `0x9d2a4b..0x9d2a95`, `0x9d2b0d..0x9d2b1e` | It is a separate 16-byte weak ownership pair and cannot be discarded. |
| Result handle constructor allocates a 16-byte weak pair and stores its pointer in the out slot; destructor null-checks that pointer | `0x2357860`, `0x23578d0`, `0x2357910` | Out slot itself is 8 bytes; null is safe only for call sites that discard it. |
| Add returns the caller's out-storage address | `0x9d2ccc` | A future suppressing relay must return the out address in RAX, not blindly `xor eax,eax`. |
| Road and Buy immediately destroy the temporary out handle | road return `0x459eb7`, buy `0x74fda9` | A discarded empty handle is a candidate for these sites, not evidence for all 82 Add callers. |

`bind_build_35924_abi` supplies real move/destroy/Add operations only when the
caller supplies a verified exact image fingerprint and local PE/instruction
anchors match. Merely binding this table still executes no native helper. All
queue readiness gates remain separately closed by default.

The optional binding calls Add's original entry. If a later adapter hooks that
entry, it must replace this call with a verified original trampoline or a proven
recursion-bypass path. Blindly installing the hook and using this entry binding
would re-capture its own replay.

## Admission and pump contract

1. Validate complete **semantic** intent while the original native arguments are
   still alive. Persist/accept that intent in the active session. Never transmit
   native pointers or raw C++ objects.
2. Verify the exact caller's discarded-result contract, readable/writable source
   layouts, the actual producer thread, and current epoch before `capture`.
   Capture IDs must increase within an epoch and remain unique after completion.
3. On `accepted`, suppress the original Add and return its out-storage address.
   On any refusal, the surrounding hook must fail closed; this adapter does not
   invent a safe return/callback contract for an unsupported UI operation.
4. A host protocol grant provides global order and boundary. All commands in that
   order, including reconstructed remote commands, must pass through this queue;
   an order gap is not skipped. Network code calls `grant`, never native Add.
5. Pump `drain` on the **same verified thread that produces Add calls**, while a
   simulation gate holds the exact boundary. Wall-clock timeouts never grant
   simulation progress. The pump must continue in pause and cannot depend on a
   blocked simulation callback that never runs while paused.
6. Observe real completion, extract success and semantic entity identity while
   the returned command is valid, and call `report_applied`. Bind peer identities
   to that command's exact result. Further UI actions produced by a completion
   callback must become new protocol intents too.
7. Compare all peer results before releasing the next simulation boundary. This
   queue's local `applied` status is not a global commit result.

The static Add body has no evident general-purpose lock around its vector append.
Its UI callers and the simulation apply side are distinct paths. Consequently
the producer-thread pump is a mandatory **unverified** gate, not an assumption
that Add can be called from the network thread or from any SimStep hook.

## Action coverage and remaining gates

| Action | Current source evidence | Remaining pre-apply work |
|---|---|---|
| Roads/rail | `slice_hook.cpp` captures geometry at factory and has successful historical cancel tests. | Validate complete proposal/context roundtrip, safe true-result UI completion, producer pump, step gate and complete-state two-PC test. |
| Depot/construction | Native caller `0x419f62` remains optimistic at `slice_hook.cpp:2255`; Lua reads filename, transform and params from the already-created entity around `lockstep.lua:2686`, `6903..7003`. | Pre-apply full construction params/context decode. For a limited feasibility experiment, a custom known semantic depot intent can bypass this unresolved stock UI capture path. |
| Buy vehicle | Native config arguments are available; callback ownership layout is now statically resolved. | Complete config fields, exact dependency mapping, callback lifetime during UI close and result observation must be demonstrated live. Do not enable legacy `strict_buy`. |
| Create/update line | Native factories and line structures exist; current Lua capture often reads back the local result. | Serialize full pre-apply data, hold/rebase edits while an earlier edit is pending, bind only the true create result, and verify line UI lifetime. |

No action is declared ready for user multiplayer solely because these queue tests
pass. Missing gates are: actual interception + safe failure response; complete
serialization; correct producer-thread maintenance pump; native completion
observer; proven step gating around real apply; complete-state comparison across
two independently running game instances. These require further integration and
controlled in-game tests, not another optimistic replay flag.

## Tests

Compiled with MSVC x64, C++17, `/W4 /WX /wd4324` (intentional aligned-storage
padding). `deferred_command_test.cpp` passes 20 scenarios with fake native objects:
inline and heap callback ownership across caller stack expiry, no early callback,
all four readiness gates, all four source admission gates, ordered grants and
out-of-order completion, exact boundary zero, wrong thread, late boundary,
capacity exhaustion without source mutation, application failure, duplicate ID,
unexpected Add return storage, reentrant completion without premature reuse,
overlapping native input storage, and contradictory order/boundary grants before
either command is submitted.

The fake engine verifies generic ownership and scheduling. It does not prove
native helper execution, UI behavior, construction fidelity, or real game
determinism. The existing Alpha implementation and installation are unchanged.
