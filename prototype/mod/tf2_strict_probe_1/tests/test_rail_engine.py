"""Literal production Lua suite against explicit native primitive fixtures.

Headless field/lifetime/identity checks, not evidence of actual TF2 behavior.
"""
import importlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests/lua/.deps'))
from prototype.strict_sync.rail_catalog import STEPS

SCRIPTS = HERE.parent / 'res/scripts/tf2_strict_probe'
RUNTIME = None
PRELUDE = [('a:1', {'op': 'SET_PAUSED', 'value': True}), ('a:2', {'op': 'PROBE_ROAD'}),
 ('b:1', {'op': 'PROBE_DEPOT'}), ('a:3', {'op': 'PROBE_STOP', 'index': 0}),
 ('b:2', {'op': 'PROBE_STOP', 'index': 1}), ('a:4', {'op': 'PROBE_CONNECT'}),
 ('b:3', {'op': 'PROBE_VEHICLE'}), ('a:5', {'op': 'PROBE_LINE'}),
 ('b:4', {'op': 'PROBE_ASSIGN'}), ('a:6', {'op': 'SET_PAUSED', 'value': False})]


class Harness:
    def __init__(self, offset=0, setup='', initialize=True):
        self.lua = RUNTIME(unpack_returned_tuples=True)
        self.modules = {}
        self.lua.globals().require = lambda name: self.modules[name]
        for name in ('json', 'build_assets', 'guided_assets', 'guided_engine', 'rail_assets', 'rail_engine'):
            self.modules['tf2_strict_probe/' + name] = self.lua.execute((SCRIPTS / (name + '.lua')).read_text('utf-8'))
        self.j = self.modules['tf2_strict_probe/json']
        self.lua.globals().rail_assets = self.modules['tf2_strict_probe/rail_assets']
        self.lua.globals().assets = self.modules['tf2_strict_probe/build_assets']
        self.lua.globals().id_offset = offset
        for name in ('fake_build_engine.lua', 'fake_guided_engine.lua', 'fake_rail_engine.lua'):
            self.lua.execute((HERE / name).read_text('utf-8'))
        self.lua.execute(setup)
        module = self.lua.execute((SCRIPTS / 'build_engine.lua').read_text('utf-8'))
        self.e = module.new(self.j, self.table({'input_mode': 'guided_rail_v1'}))
        if initialize:
            self.e.bind_initial(self.table([]))
        self.sequence = {'a': 6, 'b': 4}

    def table(self, value):
        return self.j.decode(json.dumps(value))

    def snapshot(self):
        return json.loads(self.j.encode(self.e.snapshot()))

    def prelude(self):
        observed = []
        for key, command in PRELUDE:
            p = self.e.plan(self.table(command), key, round(self.lua.globals().now * 1e6))
            self.e.finish(p, self.lua.globals().apply_command(p.native), True)
            observed.append(self.snapshot())
        self.lua.globals().advance()
        return observed

    def apply(self, step):
        actor = step['actor']
        key = f'{actor}:{self.sequence[actor] + 1}'
        command = self.table(step['command'])
        before = self.snapshot()
        preview = json.loads(self.j.encode(self.e.preview(command, key)))
        assert self.snapshot() == before
        if not preview['allowed']:
            return None
        plan = self.e.plan(command, key, round(self.lua.globals().now * 1e6))
        assert self.snapshot() == before
        if plan.read_only:
            value = self.e.finish_read_only(plan)
        else:
            value = self.e.finish(plan, self.lua.globals().apply_command(plan.native), True)
        self.sequence[actor] += 1
        return json.loads(self.j.encode(value))


class RailLuaTests(unittest.TestCase):
    def ready(self, **kwargs):
        h = Harness(**kwargs); h.prelude(); return h

    def through(self, h, action, occurrence=1):
        for step in STEPS:
            if step['action'] == action:
                occurrence -= 1
                if occurrence == 0: return step
            if step['read_only']:
                for _ in range(2): h.lua.globals().advance(); h.snapshot()
            self.assertIsNotNone(h.apply(step), step['action'])
        self.fail('action absent')

    def test_complete_recipe_two_locales_native_id_spaces_and_replacement_generations(self):
        for replacement in (False, True):
            runs = []
            for offset, prefix in ((0, 'Strassenfahrzeug'), (4000, 'Road vehicle')):
                h = self.ready(offset=offset, setup=f"guided_fixture_vehicle_name_prefix='{prefix}'; rail_fixture_station_name_prefix='{prefix}'; rail_fixture_replace_new_identity={'true' if replacement else 'false'}")
                initial = h.snapshot()['objects']; results = []
                for step in STEPS:
                    if step['read_only']:
                        for _ in range(2): h.lua.globals().advance(); h.snapshot()
                    result = h.apply(step); self.assertIsNotNone(result, step['action'])
                    self.assertTrue(result['success']); snap = h.snapshot(); self.assertFalse(snap['coverage']['missing'])
                    self.assertLess(len(json.dumps(result, separators=(',', ':')).encode()), 16384)
                    self.assertLess(len(json.dumps(snap, separators=(',', ':')).encode()), 100000)
                    results.append((result, snap))
                self.assertEqual([o['logical_id'] for o in h.snapshot()['objects']], [o['logical_id'] for o in initial])
                self.assertEqual(h.snapshot()['probe']['rail_suite']['train'], '')
                runs.append(results)
            self.assertEqual(runs[0], runs[1])

    def test_stock_informed_asymmetric_ports_and_one_marker_per_edge(self):
        h = self.ready(); step = self.through(h, 'VERIFY_RAIL_GRAPH')
        snap = h.snapshot(); registry = snap['probe']['rail_suite']
        network = next(o['state'] for o in snap['objects'] if o['logical_id'] == registry['connectors'])
        self.assertEqual([a['slot'] for a in network['arms']], ['a', 'b', 'depot'])
        self.assertTrue(all(len(a['objects']) == 1 for a in network['arms']))
        self.assertEqual(float(network['arms'][1]['position0'][1]) - float(network['arms'][0]['position0'][1]), 240)
        self.assertIsNotNone(h.apply(step))

    def test_constructor_preflight_never_sends_native_command(self):
        h = Harness()
        self.assertEqual(h.lua.globals().sent, 0)
        self.assertEqual(h.lua.globals().command_factory_calls, 0)
        self.assertTrue(h.snapshot()['probe']['rail_suite']['capabilities']['ready'])

    def test_other_mode_cannot_start_t1_action_in_rail_session(self):
        h=self.ready(); before=h.snapshot(); sent=h.lua.globals().sent
        for function in (h.e.preview,h.e.plan):
            with self.assertRaises(Exception):
                function(h.table({'op':'GUIDED_ACTION','step':1}),'a:7',round(h.lua.globals().now*1e6))
        self.assertEqual(h.snapshot(),before); self.assertEqual(h.lua.globals().sent,sent)

    def test_failed_callback_cannot_register_construction(self):
        h = self.ready(); step = self.through(h, 'BUILD_STATION_A')
        command=h.table(step['command']); key='b:5'; before=h.snapshot()
        plan=h.e.plan(command,key,round(h.lua.globals().now*1e6))
        result=json.loads(h.j.encode(h.e.finish(plan,h.table({}),False)))
        self.assertFalse(result['success']); self.assertEqual(before,h.snapshot())

    def test_actual_wrong_parameters_and_name_fail_before_registration(self):
        for mutation in ("world[n].CONSTRUCTION.params.year=1900", "world[n].NAME.name='wrong'"):
            h=self.ready(); step=self.through(h,'BUILD_STATION_A')
            h.lua.execute("local original=apply_command; apply_command=function(c) local r=original(c); if c.op=='build' then for n,w in pairs(world) do if w.CONSTRUCTION and w.CONSTRUCTION.fileName==rail_assets.station then "+mutation+" end end end; return r end")
            with self.assertRaisesRegex(Exception,'built rail (parameter|name)'): h.apply(step)
            self.assertEqual(h.snapshot()['probe']['rail_suite']['station_a'],'')

    def test_fresh_preflight_failure_sends_nothing_and_does_not_advance(self):
        h=self.ready(); step=self.through(h,'BUILD_STATION_A'); before=h.snapshot(); sent=h.lua.globals().sent
        h.lua.execute('rail_fixture_preflight_critical=true')
        with self.assertRaisesRegex(Exception,'fresh rail proposal rejected'): h.apply(step)
        self.assertEqual(h.lua.globals().sent,sent); self.assertEqual(h.snapshot(),before)

    def test_unexpected_marker_model_and_edge_changes_fail_closed(self):
        for mutation in ("w.MODEL_INSTANCE_LIST.fatInstances[1].modelId=24", "w.SIGNAL_LIST.signals[1].edgePr[1].entity=1"):
            h=self.ready(); step=self.through(h,'ADD_SIGNAL_A')
            h.lua.execute("local original=apply_command; apply_command=function(c) local r=original(c); for n,w in pairs(world) do if w.SIGNAL_LIST then "+mutation+" end end; return r end")
            with self.assertRaisesRegex(Exception,'marker model differs|signal edge identity differs'): h.apply(step)

    def test_marker_rebuild_cannot_change_shape_or_leave_old_generation(self):
        h=self.ready(); step=self.through(h,'ADD_SIGNAL_A')
        h.lua.execute("local original=apply_command; apply_command=function(c) local r=original(c); for n,w in pairs(world) do if w.BASE_EDGE_TRACK and #w.BASE_EDGE.objects>0 then w.BASE_EDGE.tangent0.x=w.BASE_EDGE.tangent0.x+1 end end; return r end")
        with self.assertRaisesRegex(Exception,'changed connector geometry'): h.apply(step)

    def test_same_time_observations_cannot_invent_movement(self):
        h=self.ready(); step=self.through(h,'VERIFY_TRAIN_MOVEMENT')
        h.lua.globals().advance(); first=h.snapshot()
        for _ in range(3):
            self.assertEqual(h.snapshot(),first); self.assertIsNone(h.apply(step))
        h.lua.globals().advance(); h.snapshot(); self.assertIsNotNone(h.apply(step))

    def test_name_guard_is_bound_to_successful_purchase_not_lazily_reset(self):
        h=self.ready(); step=self.through(h,'CREATE_LINE')
        h.lua.execute("world[rail_last_train].NAME.name='unexpected'")
        with self.assertRaisesRegex(Exception,'vehicle name changed outside its approved rename'): h.apply(step)
        self.assertTrue(h.snapshot()['coverage']['missing'])

    def test_explicit_rename_and_replacement_preserve_actual_name(self):
        h=self.ready(); step=self.through(h,'RENAME_TRAIN')
        h.lua.execute("local original=apply_command; apply_command=function(c) if c.op=='guided_name' then return native_record({}) end; return original(c) end")
        with self.assertRaisesRegex(Exception,'name readback differs'): h.apply(step)
        for offset in (0, 1000):
            h=self.ready(offset=offset,setup='rail_fixture_replace_new_identity=true'); step=self.through(h,'REPLACE_TRAIN')
            h.lua.execute("local original=apply_command; apply_command=function(c) local r=original(c); if c.op=='rail_replace' then for n,w in pairs(world) do if w.TRANSPORT_VEHICLE and w.TRANSPORT_VEHICLE.carrier==1 then w.NAME.name='wrong' end end end; return r end")
            with self.assertRaisesRegex(Exception,'replacement changed confirmed vehicle name'): h.apply(step)

    def test_demolition_requires_actual_absence(self):
        h=self.ready(); step=self.through(h,'REMOVE_CONNECTORS')
        h.lua.execute("local original=apply_command; apply_command=function(c) if c.op=='build' and #c.proposal.streetProposal.nodesToRemove>0 then sent=sent+1; return native_record({resultEntities={}}) end; return original(c) end")
        with self.assertRaisesRegex(Exception,'removed connector edge still exists'): h.apply(step)


if __name__ == '__main__':
    good = True
    for variant in ('lua51', 'lua52', 'lua53', 'lua54'):
        RUNTIME = importlib.import_module('lupa.' + variant).LuaRuntime
        print('Rail literal Lua:', variant, flush=True)
        good = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(RailLuaTests)).wasSuccessful() and good
    raise SystemExit(0 if good else 1)


