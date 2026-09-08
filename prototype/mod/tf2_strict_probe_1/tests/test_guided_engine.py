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
from prototype.strict_sync.guided_catalog import STEPS

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
        for name in ('json', 'build_assets', 'guided_assets', 'guided_engine'):
            self.modules['tf2_strict_probe/' + name] = self.lua.execute((SCRIPTS / (name + '.lua')).read_text('utf-8'))
        self.j = self.modules['tf2_strict_probe/json']
        self.lua.globals().assets = self.modules['tf2_strict_probe/build_assets']
        self.lua.globals().id_offset = offset
        for name in ('fake_build_engine.lua', 'fake_guided_engine.lua'):
            self.lua.execute((HERE / name).read_text('utf-8'))
        self.lua.execute(setup)
        module = self.lua.execute((SCRIPTS / 'build_engine.lua').read_text('utf-8'))
        self.e = module.new(self.j, self.table({'input_mode': 'guided_suite_v1'}))
        if initialize:
            self.e.bind_initial(self.table([]))
        self.sequence = {'a': 6, 'b': 4}

    def table(self, value):
        return self.j.decode(json.dumps(value))

    def snapshot(self):
        return json.loads(self.j.encode(self.e.snapshot()))

    def prelude(self):
        for key, command in PRELUDE:
            p = self.e.plan(self.table(command), key, round(self.lua.globals().now * 1e6))
            self.e.finish(p, self.lua.globals().apply_command(p.native), True)
        self.lua.globals().advance()

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


class GuidedLuaTests(unittest.TestCase):
    def test_catalogue_matches_literal_lua_actions_and_roles(self):
        h = Harness()
        asset = h.modules['tf2_strict_probe/guided_assets']
        self.assertEqual(list(asset.actions.values()), [s['action'] for s in STEPS])
        self.assertEqual(list(asset.roles.values()), [s['actor'] for s in STEPS])

    def test_full_lifecycle_two_different_native_id_ranges(self):
        a, b = Harness(), Harness(10000)
        a.prelude(); b.prelude()
        initial_keys = {obj['logical_id'] for obj in a.snapshot()['objects']}
        self.assertEqual(a.snapshot(), b.snapshot())
        for step in STEPS:
            if step['read_only']:
                for _ in range(2):
                    a.lua.globals().advance(); b.lua.globals().advance()
                    a.snapshot(); b.snapshot()
            before = a.snapshot()
            result_a, result_b = a.apply(step), b.apply(step)
            self.assertIsNotNone(result_a, step['action'])
            self.assertEqual(result_a, result_b)
            self.assertEqual(a.snapshot(), b.snapshot())
            if step['read_only']:
                self.assertEqual(before, a.snapshot())
                self.assertEqual(result_a['result']['effect']['kind'], 'observation')
            else:
                self.assertEqual(result_a['result']['effect']['kind'], 'callback')
        final = a.snapshot()
        self.assertEqual(final['probe']['guided_suite']['vehicle'], '')
        self.assertEqual(final['probe']['guided_suite']['line'], '')
        self.assertEqual({obj['logical_id'] for obj in final['objects']}, initial_keys)

    def test_not_ready_observation_sends_nothing_and_can_retry(self):
        h = Harness(); h.prelude()
        step = next(s for s in STEPS if s['action'] == 'VERIFY_MOVEMENT')
        for previous in STEPS[:step['step'] - 1]:
            h.apply(previous)
        before, sends = h.snapshot(), h.lua.globals().sent
        self.assertIsNone(h.apply(step))
        self.assertEqual(before, h.snapshot())
        self.assertEqual(sends, h.lua.globals().sent)
        h.lua.globals().advance()
        h.snapshot()
        self.assertIsNone(h.apply(step))
        h.lua.globals().advance()
        self.assertTrue(h.apply(step)['success'])
        self.assertEqual(sends, h.lua.globals().sent)

    def test_missing_capabilities_aggregate_without_sends(self):
        h = Harness(setup='api.cmd.make.updateLine=nil; api.cmd.make.sellVehicle=nil', initialize=False)
        with self.assertRaisesRegex(Exception, 'api.cmd.make.sellVehicle; api.cmd.make.updateLine'):
            h.e.bind_initial(h.table([]))
        self.assertEqual(h.lua.globals().sent, 0)

    def test_positive_speed_with_frozen_actual_position_is_not_movement_proof(self):
        h = Harness(); h.prelude()
        step = next(s for s in STEPS if s['action'] == 'VERIFY_MOVEMENT')
        for previous in STEPS[:step['step'] - 1]: h.apply(previous)
        h.lua.execute('''
          local advance_native=advance
          advance=function()
            advance_native()
            for id,e in pairs(world)do if e.TRANSPORT_VEHICLE and legacy[id]then
              legacy[id].position={x=123,y=456,z=10}
            end end
          end
        ''')
        for _ in range(3):
            h.lua.globals().advance()
            self.assertIsNone(h.apply(step))
        self.assertFalse(h.snapshot()['objects'][-1]['state'].get('guided_motion',{}).get('displacement_observed',False))

    def test_wrong_actor_stale_step_and_unknown_fields_fail_before_send(self):
        h = Harness(); h.prelude(); sends = h.lua.globals().sent
        for command, key in [({'op': 'GUIDED_ACTION', 'step': 1}, 'b:5'),
                             ({'op': 'GUIDED_ACTION', 'step': 2}, 'b:5'),
                             ({'op': 'GUIDED_ACTION', 'step': 1, 'entity': 100}, 'a:7')]:
            with self.assertRaises(Exception):
                h.e.preview(h.table(command), key)
        self.assertEqual(sends, h.lua.globals().sent)

    def test_successful_callback_cannot_hide_failed_actual_name_change(self):
        h = Harness(); h.prelude()
        step = next(s for s in STEPS if s['action'] == 'RENAME_LINE')
        for previous in STEPS[:step['step'] - 1]:
            h.apply(previous)
        h.lua.execute("local apply=apply_command; apply_command=function(c) if c.op=='guided_name' then sent=sent+1; return native_record({}) end; return apply(c) end")
        with self.assertRaisesRegex(Exception, 'name readback differs'):
            h.apply(step)

    def test_sale_requires_actual_entity_disappearance(self):
        h = Harness(); h.prelude()
        for step in STEPS:
            if step['action'] == 'SELL_BUS':
                h.lua.execute("local apply=apply_command; apply_command=function(c) if c.op=='guided_sell' then sent=sent+1; return native_record({}) end; return apply(c) end")
                with self.assertRaisesRegex(Exception, 'deleted entity still exists'):
                    h.apply(step)
                break
            if step['read_only']:
                for _ in range(2):
                    h.lua.globals().advance(); h.snapshot()
            h.apply(step)


if __name__ == '__main__':
    good = True
    for variant in ('lua51', 'lua52', 'lua53', 'lua54'):
        RUNTIME = importlib.import_module('lupa.' + variant).LuaRuntime
        print('Guided literal Lua:', variant, flush=True)
        good = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuidedLuaTests)).wasSuccessful() and good
    raise SystemExit(0 if good else 1)
