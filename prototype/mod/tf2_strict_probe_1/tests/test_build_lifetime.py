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
    def __init__(self, *, setup="", source=None, offset=0):
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
        self.e.bind_initial(self.table([]))


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
