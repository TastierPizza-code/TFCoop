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


class GuidedLuaTests(unittest.TestCase):
    def test_native_callable_tables_pass_without_invoking_any_command_maker(self):
        h = Harness()
        self.assertTrue(h.lua.eval("type(api.cmd.make.buyVehicle)=='table' and type(getmetatable(api.cmd.make.buyVehicle).__call)=='function'"))
        self.assertEqual(h.lua.globals().command_factory_calls, 0)
        self.assertEqual(h.lua.globals().sent, 0)
        self.assertTrue(h.snapshot()['probe']['guided_suite']['capabilities']['ready'])

    def test_ordinary_lua_functions_remain_supported(self):
        h = Harness(setup='for name,fn in pairs(command_factory_functions)do api.cmd.make[name]=fn end')
        self.assertTrue(h.snapshot()['probe']['guided_suite']['capabilities']['ready'])
        self.assertEqual(h.lua.globals().sent, 0)

    def test_callable_userdata_and_constructor_tables_use_the_same_check(self):
        h = Harness(setup='''
          local fn=command_factory_functions.setGameSpeed
          local value=native_record({})
          getmetatable(value).__call=function(_,...)return fn(...)end
          api.cmd.make.setGameSpeed=value
          for _,owner in ipairs({api.type.VehiclePart,api.type.TransportVehiclePart,
            api.type.TransportVehicleConfig,api.type.Line,api.type.Vec3f,api.type.Line.Stop})do
            local new=owner.new
            owner.new=setmetatable({},{__call=function(_,...)return new(...)end})
          end
        ''')
        self.assertEqual(h.lua.globals().command_factory_calls, 0)
        self.assertEqual(h.lua.globals().sent, 0)
        h.prelude()
        self.assertTrue(h.apply(STEPS[0])['success'])

    def test_every_noncallable_factory_is_rejected_without_invocation(self):
        malformed = ('{}', '{__call=function()error("must not invoke")end}',
                     'setmetatable({},{__call=false})',
                     'setmetatable({},{__index=function()return function()end end})',
                     'setmetatable({},{__call=function()error("must not invoke")end,__metatable=false})')
        for maker in ('buyVehicle', 'createLine', 'deleteLine', 'reverseVehicle', 'sellVehicle',
                      'sendToDepot', 'setColor', 'setGameSpeed', 'setLine', 'setName',
                      'setUserStopped', 'setVehicleTargetMaintenanceState', 'updateLine'):
            for value in malformed:
                with self.subTest(maker=maker, value=value):
                    h = Harness(setup=f'api.cmd.make.{maker}={value}', initialize=False)
                    with self.assertRaisesRegex(Exception, f'api.cmd.make.{maker}'):
                        h.e.bind_initial(h.table([]))
                    self.assertEqual(h.lua.globals().command_factory_calls, 0)
                    self.assertEqual(h.lua.globals().sent, 0)

    def test_catalogue_matches_literal_lua_actions_and_roles(self):
        h = Harness()
        asset = h.modules['tf2_strict_probe/guided_assets']
        self.assertEqual(list(asset.actions.values()), [s['action'] for s in STEPS])
        self.assertEqual(list(asset.roles.values()), [s['actor'] for s in STEPS])

    def test_full_lifecycle_two_different_native_id_ranges(self):
        a = Harness(setup="guided_fixture_vehicle_name_prefix='Strassenfahrzeug'")
        b = Harness(10000, setup="guided_fixture_vehicle_name_prefix='Road vehicle'")
        self.assertEqual(a.prelude(), b.prelude())
        self.assertEqual(a.lua.globals().world[a.e.bindings['b:3'].entity].NAME.name, 'Strassenfahrzeug 1')
        self.assertEqual(b.lua.globals().world[b.e.bindings['b:3'].entity].NAME.name, 'Road vehicle 1')
        self.assertEqual(a.snapshot()['probe']['guided_suite']['vehicle_name_contract'], 'observed_vehicle_name_v1')
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
            if step['action'] == 'BUY_BUS':
                for h, raw in ((a, 'Strassenfahrzeug 2'), (b, 'Road vehicle 2')):
                    key = h.snapshot()['probe']['guided_suite']['vehicle']
                    self.assertEqual(h.lua.globals().world[h.e.bindings[key].entity].NAME.name, raw)
                    state = next(x['state'] for x in h.snapshot()['objects'] if x['logical_id'] == key)
                    self.assertEqual(state['name'], {'mode': 'automatic'})
            elif step['action'] == 'RENAME_BUS':
                for h in (a, b):
                    key = h.snapshot()['probe']['guided_suite']['vehicle']
                    actual = h.lua.globals().world[h.e.bindings[key].entity].NAME.name
                    self.assertEqual(actual, 'Host und Freund - Bus')
                    state = next(x['state'] for x in h.snapshot()['objects'] if x['logical_id'] == key)
                    self.assertEqual(state['name'], {'mode': 'explicit', 'value': actual})
            if step['read_only']:
                self.assertEqual(before, a.snapshot())
                self.assertEqual(result_a['result']['effect']['kind'], 'observation')
            else:
                self.assertEqual(result_a['result']['effect']['kind'], 'callback')
        final = a.snapshot()
        self.assertEqual(final['probe']['guided_suite']['vehicle'], '')
        self.assertEqual(final['probe']['guided_suite']['line'], '')
        self.assertEqual({obj['logical_id'] for obj in final['objects']}, initial_keys)

    def test_automatic_vehicle_names_are_locally_guarded_without_lazy_reenrollment(self):
        for guided_bus in (False, True):
            with self.subTest(guided_bus=guided_bus):
                h = Harness(); h.prelude()
                if guided_bus:
                    for step in STEPS[:2]: h.apply(step)
                    key = h.snapshot()['probe']['guided_suite']['vehicle']
                else:
                    key = 'b:3'
                h.lua.globals().world[h.e.bindings[key].entity].NAME.name = 'Unexpected edit'
                sends = h.lua.globals().sent
                for _ in range(2):
                    snap = h.snapshot()
                    self.assertTrue(any('vehicle name changed outside its approved rename' in error
                                        for error in snap['coverage']['missing']))
                with self.assertRaisesRegex(Exception, 'tracked observation unavailable: .*vehicle name changed outside its approved rename'):
                    h.apply(STEPS[2] if guided_bus else STEPS[0])
                self.assertEqual(h.lua.globals().sent, sends)

    def test_explicit_vehicle_name_is_still_guarded(self):
        h = Harness(); h.prelude()
        rename = next(s for s in STEPS if s['action'] == 'RENAME_BUS')
        for step in STEPS[:rename['step']]: h.apply(step)
        key = h.snapshot()['probe']['guided_suite']['vehicle']
        h.lua.globals().world[h.e.bindings[key].entity].NAME.name = 'Unexpected edit'
        self.assertTrue(any('vehicle name changed outside its approved rename' in error
                            for error in h.snapshot()['coverage']['missing']))
        with self.assertRaisesRegex(Exception, 'tracked observation unavailable: .*vehicle name changed outside its approved rename'):
            h.apply(STEPS[rename['step']])

    def test_missing_observation_reason_is_bounded_and_sanitized(self):
        h = Harness(); h.prelude()
        h.lua.globals().fixture_engine = h.e
        h.lua.execute('''
          fixture_engine.snapshot=function()
            return {coverage={missing={'guard at 0xDEADBEEF'..string.char(0,10,195,164)..string.rep('x',2000)}}}
          end
        ''')
        with self.assertRaises(Exception) as raised:
            h.e.preview(h.table(STEPS[0]['command']), 'a:7')
        message = str(raised.exception).split('\nstack traceback:', 1)[0]
        self.assertIn('guard at [address]????', message)
        self.assertNotIn('0xDEADBEEF', message)
        self.assertNotIn('\x00', message)
        self.assertLessEqual(len(message), len('guided suite: tracked observation unavailable: ') + 768)

    def test_vehicle_name_witness_cannot_follow_a_rebound_native_identity(self):
        h = Harness(); h.prelude()
        prior = h.e.bindings['b:3'].entity
        substitute = prior + 10000
        h.lua.globals().world[substitute] = h.lua.globals().world[prior]
        h.e.bindings['b:3'].entity = substitute
        self.assertTrue(any('vehicle name witness absent or stale' in error
                            for error in h.snapshot()['coverage']['missing']))

    def test_unknown_tracked_vehicle_does_not_enroll_during_observation(self):
        h = Harness(); h.prelude()
        h.e.bindings['a:99'] = h.table({'kind': 'vehicle', 'entity': h.e.bindings['b:3'].entity})
        for _ in range(2):
            self.assertTrue(any('vehicle name witness absent or stale' in error
                                for error in h.snapshot()['coverage']['missing']))

    def test_failed_rename_callback_cannot_confirm_explicit_name(self):
        h = Harness(); h.prelude()
        step = next(s for s in STEPS if s['action'] == 'RENAME_BUS')
        for prior in STEPS[:step['step'] - 1]: h.apply(prior)
        command = h.table(step['command'])
        key = f"{step['actor']}:{h.sequence[step['actor']] + 1}"
        plan = h.e.plan(command, key, round(h.lua.globals().now * 1e6))
        result = h.lua.globals().apply_command(plan.native)
        receipt = json.loads(h.j.encode(h.e.finish(plan, result, False)))
        self.assertFalse(receipt['success'])
        self.assertTrue(any('vehicle name changed outside its approved rename' in error
                            for error in h.snapshot()['coverage']['missing']))

    def test_missing_or_nontext_vehicle_name_cannot_become_an_automatic_default(self):
        for value in ('nil', '17'):
            with self.subTest(value=value):
                h = Harness(setup='''
                  local apply=apply_command
                  apply_command=function(c)
                    local result=apply(c)
                    if c.op=='buy'then world[vehicle_id].NAME.name=''' + value + ''' end
                    return result
                  end
                ''')
                with self.assertRaisesRegex(Exception, 'NAME.name|missing build field'):
                    h.prelude()

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
        self.assertEqual(h.lua.globals().command_factory_calls, 0)
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
        for action in ('RENAME_LINE', 'RENAME_BUS'):
            with self.subTest(action=action):
                h = Harness(); h.prelude()
                step = next(s for s in STEPS if s['action'] == action)
                for previous in STEPS[:step['step'] - 1]:
                    h.apply(previous)
                h.lua.execute("local apply=apply_command; apply_command=function(c) if c.op=='guided_name' then sent=sent+1; return native_record({}) end; return apply(c) end")
                with self.assertRaisesRegex(Exception, 'name readback differs'):
                    h.apply(step)
                if action == 'RENAME_BUS':
                    key = h.snapshot()['probe']['guided_suite']['vehicle']
                    state = next(x['state'] for x in h.snapshot()['objects'] if x['logical_id'] == key)
                    self.assertEqual(state['name'], {'mode': 'automatic'})

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
