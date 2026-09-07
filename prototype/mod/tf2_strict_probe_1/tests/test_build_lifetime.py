"""Real Lua __gc/borrowed-view regressions; no Transport Fever 2 is started.

The observed game failure does not establish its native ownership contract. This
fixture models a component owning child views, then forces real garbage collection
at child access. It contains no field-specific failure flag. Published tests use
the current adapter; --source optionally compares an independently supplied old
adapter without making a private dist/.publish directory a test dependency.
"""
from pathlib import Path
import argparse
import importlib
import importlib.util
import json
import sys
import unittest


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "res/scripts/tf2_strict_probe"
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tests/lua/.deps"))
_spec = importlib.util.spec_from_file_location("_build_lifetime_base", HERE / "test_build_engine.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
RUNTIME = None
SOURCE = SCRIPTS / "build_engine.lua"


TF2_UNPACK_FIXTURE = r'''
-- TF2 res/scripts/init.lua accepts only t and discards optional slice bounds.
-- Lua 5.1 calls the same original primitive through its global unpack name.
local unpackhelper
unpackhelper=function(t,i)
  if t[i]==nil then return end
  return t[i],unpackhelper(t,i+1)
end
local oldunpack=table.unpack or unpack
table.unpack=function(t)
  if type(t)=='userdata'then return unpackhelper(t,1)end
  return oldunpack(t)
end
'''


BORROWED_FIXTURE = r'''
-- __gc runs on genuine closed file userdata, never on a table approximation.
-- Only these test proxies model ownership. Shared fake_engine remains untouched.
collectgarbage('stop')
lifetime={created=0,finalized=0,live=0,peak=0,reads=0,invalid_reads=0}
local function complex(value)return type(value)=='table'or type(value)=='userdata'end
local function alive(state)
  if not state.alive then return false end
  for _,ancestor in ipairs(state.parents)do if not ancestor.alive then return false end end
  return true
end
local proxy
proxy=function(value,parents)
  if not complex(value)then return value end
  local state={alive=true,parents=parents or {}}
  lifetime.created=lifetime.created+1;lifetime.live=lifetime.live+1
  lifetime.peak=math.max(lifetime.peak,lifetime.live)
  local object=assert(io.tmpfile());assert(object:close())
  local function child(value)
    if not complex(value)then return value end
    local chain={state};for _,ancestor in ipairs(state.parents)do chain[#chain+1]=ancestor end
    -- The chain stores liveness flags only, never the parent userdata itself.
    return proxy(value,chain)
  end
  local function checked()
    lifetime.reads=lifetime.reads+1
    collectgarbage('collect')
    if not alive(state)then lifetime.invalid_reads=lifetime.invalid_reads+1;return false end
    return true
  end
  local mt={
    __index=function(_,key)
      if not checked()then return nil end
      return child(value[key])
    end,
    __len=function()
      -- A normal ordered view: no forced collection between a valid length and
      -- return. Its first element access is a later genuine GC safe point.
      if not alive(state)then return 0 end
      return #value
    end,
    __gc=function()
      if state.alive then state.alive=false;lifetime.live=lifetime.live-1;lifetime.finalized=lifetime.finalized+1 end
    end,
  }
  mt.__pairs=function()
    local iterator,iterator_state,control=pairs(value)
    return function(_,last)
      if not checked()then return nil end
      local key,entry=iterator(iterator_state,last)
      return key,child(entry)
    end,nil,control
  end
  mt.pairs=mt.__pairs
  debug.setmetatable(object,mt)
  return object
end
borrowed_root=function(value)return proxy(value)end
local original_get=api.engine.getComponent
api.engine.getComponent=function(id,kind)
  return borrowed_root(original_get(id,kind))
end
function lifetime_collect()
  collectgarbage('collect');collectgarbage('collect')
  return lifetime.live
end
'''


class LifetimeHarness(_base.Harness):
    def __init__(self, *, setup="", source=None, offset=0, bind=True):
        self.lua = RUNTIME(unpack_returned_tuples=True)
        self.j = self.lua.execute((SCRIPTS / "json.lua").read_text(encoding="utf-8"))
        self.assets = self.lua.execute((SCRIPTS / "build_assets.lua").read_text(encoding="utf-8"))
        self.lua.globals().assets = self.assets
        self.lua.globals().id_offset = offset
        self.lua.execute((HERE / "fake_build_engine.lua").read_text(encoding="utf-8"))
        self.lua.execute(BORROWED_FIXTURE)
        self.lua.execute(setup)
        self.lua.globals().require = lambda name: self.assets if name == "tf2_strict_probe/build_assets" else None
        self.module = self.lua.execute(Path(source or SOURCE).read_text(encoding="utf-8"))
        self.e = self.module.new(self.j)
        if bind:
            self.e.bind_initial(self.table([]))

    def returns(self, fn, *args):
        # Count actual Lua results, including zero results and trailing nils,
        # without using the runtime's overridden table.unpack in the assertion.
        capture = self.lua.eval("function(fn, ...) local function pack(...) return {n=select('#', ...), ...} end return pack(fn(...)) end")
        return capture(fn, *args)


class BuildLifetimeTests(unittest.TestCase):
    def assert_released(self, h):
        self.assertEqual(h.lua.globals().lifetime_collect(), 0, "operation retained a native owner after returning")
        stats = h.lua.globals().lifetime
        self.assertEqual(stats.created, stats.finalized)

    def assert_readable(self, snapshot):
        self.assertEqual(snapshot["coverage"]["missing"], [])

    def test_fixture_uses_genuine_userdata_and_parent_finalization_invalidates_unowned_child(self):
        h = LifetimeHarness()
        h.lua.execute("owner=borrowed_root({values={11,22}});child=owner.values")
        self.assertEqual(h.lua.eval("type(owner)"), "userdata")
        self.assertEqual(h.lua.eval("type(child)"), "userdata")
        self.assertEqual(h.lua.eval("#child"), 2)
        self.assertEqual(h.lua.eval("child[1]"), 11)
        self.assertEqual(h.lua.eval("child[2]"), 22)
        h.lua.execute("owner=nil;collectgarbage('collect')")
        self.assertIsNone(h.lua.eval("child[1]"))
        self.assertGreater(h.lua.globals().lifetime.invalid_reads, 0)
        h.lua.execute("child=nil")
        self.assert_released(h)

    def test_grandchild_retains_no_hidden_strong_owner_reference(self):
        h = LifetimeHarness()
        h.lua.execute("owner=borrowed_root({items={{x=37}}});items=owner.items;part=items[1]")
        self.assertEqual(h.lua.eval("part.x"), 37)
        h.lua.execute("items=nil;collectgarbage('collect')")
        self.assertIsNone(h.lua.eval("part.x"))
        self.assertEqual(h.lua.eval("type(owner)"), "userdata")
        h.lua.execute("part=nil;owner=nil")
        self.assert_released(h)

    def test_snapshot_keeps_temporary_construction_owner_through_array_conversion(self):
        h = LifetimeHarness()
        for key, command in _base.COMMANDS[:2]:
            snapshot = h.apply(key, command)
        self.assert_readable(snapshot)
        road = next(obj for obj in snapshot["objects"] if obj["logical_id"] == "a:2")
        self.assertEqual(len(road["state"]["roads"]), 3)
        self.assertEqual(h.lua.globals().lifetime.invalid_reads, 0)
        self.assertGreater(h.lua.globals().lifetime.finalized, 0)
        self.assert_released(h)

    def test_nested_plan_snapshot_and_full_build_keep_all_borrowed_component_views(self):
        h = LifetimeHarness()
        snapshot = h.build()
        self.assert_readable(snapshot)
        self.assertTrue(snapshot["probe"]["connectivity"]["connected"])
        self.assertEqual(snapshot["probe"]["line"]["vehicles"], ["b:3"])
        self.assertEqual(h.lua.globals().sent, 9)
        self.assertEqual(h.lua.globals().lifetime.invalid_reads, 0)
        self.assert_released(h)

    def test_vehicle_config_position_and_line_color_views_survive_until_plain_snapshot(self):
        h = LifetimeHarness()
        h.build()
        h.lua.globals().advance()
        first = h.snapshot()
        h.lua.globals().advance()
        second = h.snapshot()
        self.assert_readable(first)
        self.assert_readable(second)
        self.assertFalse(second["probe"]["vehicle"]["in_depot"])
        self.assertNotEqual(first["probe"]["vehicle"]["position_mm"], second["probe"]["vehicle"]["position_mm"])
        self.assertEqual(h.lua.globals().lifetime.invalid_reads, 0)
        self.assert_released(h)

    def test_caught_snapshot_failure_releases_owners_and_preserves_first_error(self):
        h = LifetimeHarness()
        h.apply(*_base.COMMANDS[0]);h.apply(*_base.COMMANDS[1])
        h.lua.execute("world[junction].BASE_NODE.position=nil")
        snapshot = h.snapshot()
        self.assertTrue(snapshot["coverage"]["missing"])
        self.assertTrue(any("position" in value for value in snapshot["coverage"]["missing"]))
        self.assertEqual(h.lua.globals().sent, 2)
        self.assert_released(h)

    def test_thrown_plan_failure_releases_outer_and_nested_owners(self):
        h = LifetimeHarness()
        for key, command in _base.COMMANDS[:5]:
            h.apply(key, command)
        h.lua.execute("api.engine.system.streetSystem.getNode2StreetEdgeMap=function()error('fixture collection read failure',0)end")
        with self.assertRaisesRegex(Exception, "fixture collection read failure"):
            h.plan(*_base.COMMANDS[5])
        self.assertEqual(h.lua.globals().sent, 5)
        self.assert_released(h)

    def test_repeated_successful_operations_do_not_accumulate_native_owners(self):
        h = LifetimeHarness()
        h.build()
        expected = h.snapshot()
        for _ in range(4):
            self.assertEqual(h.snapshot(), expected)
            self.assert_released(h)
        # This is an owner-lifetime bound, not a platform-dependent heap-byte
        # benchmark. The scope must not retain previous calls' native objects.
        self.assertLess(h.lua.globals().lifetime.peak, 2048)
        self.assertEqual(h.lua.globals().lifetime.invalid_reads, 0)

    def test_tf2_unpack_fixture_ignores_slice_bounds_for_tables_and_userdata(self):
        h = LifetimeHarness(setup=TF2_UNPACK_FIXTURE)
        self.assertEqual(h.lua.eval("table.unpack({17,29,41},2,2)"), (17, 29, 41))
        h.lua.execute("fixture_values=borrowed_root({17,29,41})")
        self.assertEqual(h.lua.eval("table.unpack(fixture_values,2,2)"), (17, 29, 41))
        h.lua.execute("fixture_values=nil")
        self.assert_released(h)

    def test_tf2_unpack_override_preserves_full_build_snapshots_and_exact_return_counts(self):
        ordinary = LifetimeHarness(bind=False)
        overridden = LifetimeHarness(setup=TF2_UNPACK_FIXTURE, bind=False)
        for h in (ordinary, overridden):
            self.assertEqual(h.returns(h.e.bind_initial, h.table([]))["n"], 0)
            initial = h.returns(h.e.snapshot)
            self.assertEqual(initial["n"], 1)
            self.assertIsInstance(json.loads(h.j.encode(initial[1])), dict)
            self.assert_released(h)
        self.assertEqual(ordinary.snapshot(), overridden.snapshot())
        for key, command in _base.COMMANDS:
            receipts = []
            for h in (ordinary, overridden):
                before = h.snapshot()
                planned = h.returns(h.e.plan, h.table(command), key,
                                    int(round(h.lua.globals().now * 1_000_000)))
                self.assertEqual(planned["n"], 1)
                plan = planned[1]
                self.assertEqual(plan.key, key)
                self.assertEqual(json.loads(h.j.encode(plan.command)), command)
                self.assertEqual(h.snapshot(), before, "planning changed the observed world")
                result = h.lua.globals().apply_command(plan.native, False)
                finished = h.returns(h.e.finish, plan, result, True)
                self.assertEqual(finished["n"], 1)
                receipt = json.loads(h.j.encode(finished[1]))
                self.assertIs(receipt["success"], True)
                receipts.append(receipt)
                self.assert_readable(h.snapshot())
                self.assertEqual(h.lua.globals().lifetime.invalid_reads, 0)
                self.assert_released(h)
            self.assertEqual(receipts[0], receipts[1])
            self.assertEqual(ordinary.snapshot(), overridden.snapshot())
        self.assertEqual(overridden.lua.globals().sent, 9)
        self.assertTrue(overridden.snapshot()["probe"]["connectivity"]["connected"])
        for _ in range(2):
            ordinary.lua.globals().advance()
            overridden.lua.globals().advance()
            self.assertEqual(ordinary.snapshot(), overridden.snapshot())
            self.assert_released(overridden)

    def test_tf2_unpack_override_preserves_rejected_callback_result(self):
        h = LifetimeHarness(setup=TF2_UNPACK_FIXTURE)
        before = h.snapshot()
        plan = h.plan(*_base.COMMANDS[0])
        finished = h.returns(h.e.finish, plan, h.table({}), False)
        self.assertEqual(finished["n"], 1)
        self.assertEqual(json.loads(h.j.encode(finished[1])),
                         {"success": False, "result": {"error": "engine_rejected", "op": "SET_PAUSED"}})
        self.assertEqual(h.snapshot(), before)
        self.assertEqual(h.lua.globals().sent, 0)
        self.assert_released(h)

    def test_tf2_unpack_override_caught_snapshot_failure_releases_owners_and_recovers(self):
        h = LifetimeHarness(setup=TF2_UNPACK_FIXTURE)
        for key, command in _base.COMMANDS[:2]:
            h.apply(key, command)
        before = h.snapshot()
        h.lua.execute("fixture_position=world[junction].BASE_NODE.position;world[junction].BASE_NODE.position=nil")
        snapshot = h.snapshot()
        self.assertTrue(any("position" in value for value in snapshot["coverage"]["missing"]))
        self.assert_released(h)
        h.lua.execute("world[junction].BASE_NODE.position=fixture_position;fixture_position=nil")
        self.assertEqual(h.snapshot(), before)
        self.assertEqual(h.lua.globals().sent, 2)
        self.assert_released(h)

    def test_tf2_unpack_override_thrown_nested_plan_failure_releases_owners_and_recovers(self):
        h = LifetimeHarness(setup=TF2_UNPACK_FIXTURE)
        for key, command in _base.COMMANDS[:6]:
            h.apply(key, command)
        # Vehicle planning calls E.snapshot inside the outer owner scope. Fail
        # after its component traversal, when that snapshot reads the company.
        h.lua.execute("fixture_get_entity=game.interface.getEntity;game.interface.getEntity=function(id)if id==api.engine.util.getPlayer()then error('fixture nested company read failure',0)end;return fixture_get_entity(id)end")
        with self.assertRaisesRegex(Exception, "fixture nested company read failure"):
            h.plan(*_base.COMMANDS[6])
        self.assertEqual(h.lua.globals().sent, 6)
        self.assert_released(h)
        h.lua.execute("game.interface.getEntity=fixture_get_entity;fixture_get_entity=nil")
        for key, command in _base.COMMANDS[6:]:
            h.apply(key, command)
        self.assertTrue(h.snapshot()["probe"]["connectivity"]["connected"])
        self.assertEqual(h.lua.globals().lifetime.invalid_reads, 0)
        self.assert_released(h)


def main(argv=None):
    global RUNTIME, SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE,
                        help="Optional separate adapter file for a negative old-version comparison.")
    parser.add_argument("--runtime", choices=("lua51", "lua52", "lua53", "lua54"), action="append")
    args = parser.parse_args(argv)
    SOURCE = args.source
    total, failed = 0, False
    for name in args.runtime or ("lua51", "lua52", "lua53", "lua54"):
        try:
            RUNTIME = importlib.import_module("lupa." + name).LuaRuntime
        except ImportError:
            print(name + ": unavailable", flush=True)
            continue
        print(name + ": " + str(SOURCE), flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(BuildLifetimeTests))
        total += result.testsRun
        failed = failed or not result.wasSuccessful()
    print(f"total={total} passed={not failed and total > 0}", flush=True)
    return 0 if total and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
