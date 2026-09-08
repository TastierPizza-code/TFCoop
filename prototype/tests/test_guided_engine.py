"""Production Lua/Python/file-IPC guided lifecycle using explicit game fixtures."""
from contextlib import contextmanager
import copy
from pathlib import Path
import tempfile
import time
import unittest

from prototype.strict_sync.guided_catalog import STEPS
from prototype.strict_sync.guided_engine import GuidedEngineAdapter, GuidedStreamEngine, VEHICLE_NAME_CONTRACT
from prototype.strict_sync.engine_mailbox import MailboxError
from prototype.strict_sync.short_build_profile import short_build_inputs, SHORT_BUILD_ROUNDS
from prototype.tests.test_build_mailbox_lua import BuildLuaWorker
from prototype.tests.test_engine_mailbox import control
from prototype.tests.test_engine_mailbox_lua import EPOCH, RUNTIMES


@unittest.skipUnless('lua53' in RUNTIMES, 'Lua 5.3 fixture runtime unavailable')
class GuidedEngineTests(unittest.TestCase):
    @contextmanager
    def fixture(self, *, timeout_s=3, **options):
        with tempfile.TemporaryDirectory() as directory:
            worker = BuildLuaWorker(Path(directory), input_mode='guided_suite_v1', **options)
            engine = None
            try:
                engine = GuidedEngineAdapter(directory, EPOCH, probe_only=True, timeout_s=timeout_s, poll_s=.002)
                yield worker, engine
            finally:
                if engine:
                    engine.close()
                worker.close()

    def prepare(self, engine):
        sequence = {'a': 0, 'b': 0}
        for number in range(SHORT_BUILD_ROUNDS):
            for actor in ('a', 'b'):
                for command in short_build_inputs(actor, number):
                    sequence[actor] += 1
                    engine.apply(command, f'{actor}:{sequence[actor]}')
            engine.step(0 if engine.paused else 200000)
        return sequence

    def test_literal_bridge_all_guided_steps_have_identical_actual_observations(self):
        raw_name_check = """
          local original=api.cmd.sendCommand
          local purchases=0
          api.cmd.sendCommand=function(command,callback)
            original(command,function(result,success)
              if command.op=='buy'then
                purchases=purchases+1
                assert(world[vehicle_id].NAME.name==guided_fixture_vehicle_name_prefix..' '..purchases,
                  'localized fixture purchase did not produce its distinct actual name')
              end
              callback(result,success)
            end)
          end
        """
        with self.fixture(manual_setup="guided_fixture_vehicle_name_prefix='Strassenfahrzeug'",
                          callback_setup=raw_name_check) as (wa, a), \
             self.fixture(offset=10000, manual_setup="guided_fixture_vehicle_name_prefix='Road vehicle'",
                          callback_setup=raw_name_check) as (wb, b):
            seq_a, seq_b = self.prepare(a), self.prepare(b)
            self.assertEqual(seq_a, seq_b)
            initial = a.snapshot()
            self.assertEqual(initial, b.snapshot())
            self.assertEqual(initial['probe']['guided_suite']['vehicle_name_contract'], VEHICLE_NAME_CONTRACT)
            self.assertTrue(all(item['state']['name'] == {'mode': 'automatic'}
                                for item in initial['objects'] if item['kind'] == 'vehicle'))
            for step in STEPS:
                command, actor = step['command'], step['actor']
                if step['read_only']:
                    for _ in range(2): a.step(200000); b.step(200000)
                key = f'{actor}:{seq_a[actor] + 1}'
                before = a.snapshot()
                pa, pb = a.preview_guided(command, key), b.preview_guided(command, key)
                self.assertEqual(pa, pb)
                self.assertTrue(pa['allowed'], step['action'])
                ra, rb = a.apply_guided(command, key, pa), b.apply_guided(command, key, pb)
                self.assertEqual(ra, rb, step['action'])
                self.assertEqual(a.snapshot(), b.snapshot())
                if step['action'] == 'BUY_BUS':
                    self.assertEqual(ra['result']['effect']['observed']['name'], {'mode': 'automatic'})
                elif step['action'] == 'RENAME_BUS':
                    self.assertEqual(ra['result']['effect']['observed']['name'],
                                     {'mode': 'explicit', 'value': pa['observation']['expected']['name']})
                seq_a[actor] += 1
                seq_b[actor] += 1
                if step['read_only']:
                    self.assertEqual(a.snapshot(), before)
                self.assertEqual(a.apply_guided(command, key, pa), ra)
            self.assertEqual(set(o['logical_id'] for o in a.snapshot()['objects']),
                             set(o['logical_id'] for o in initial['objects']))
            self.assertFalse(a.halted)
            self.assertFalse(b.halted)
            self.assertEqual(a.snapshot()['company']['balance'], initial['company']['balance'] - 100)

    def drive_before(self, engine, action):
        sequence = self.prepare(engine)
        for step in STEPS:
            key = f"{step['actor']}:{sequence[step['actor']] + 1}"
            if step['action'] == action:
                return step, key
            preview = engine.preview_guided(step['command'], key)
            engine.apply_guided(step['command'], key, preview)
            sequence[step['actor']] += 1
        self.fail('requested fault action absent from test catalogue')

    def test_stream_wrapper_pause_and_resume_leave_native_frontier_unchanged(self):
        with self.fixture() as (_, engine):
            seq = self.prepare(engine)
            stream = GuidedStreamEngine(engine)
            stream.checkpoint()
            for step in STEPS:
                if step['read_only']:
                    break
                key = f"{step['actor']}:{seq[step['actor']] + 1}"
                command = step['command']
                before = stream._boundary()
                preview = stream.preview_guided(command, key)
                stream.apply_guided(command, key, preview)
                self.assertEqual(stream.frame, before['frame'])
                self.assertEqual(stream.time_us, before['sim_time_us'])
                self.assertEqual(stream.paused, step.get('pause', before['paused']))
                self.assertTrue(stream.observations_fresh)
                seq[step['actor']] += 1

    def test_unapproved_preview_and_direct_apply_fail_before_native_send(self):
        with self.fixture() as (worker, engine):
            seq = self.prepare(engine)
            step = STEPS[0]
            key = 'a:7'
            preview = engine.preview_guided(step['command'], key)
            altered = copy.deepcopy(preview)
            altered['observation']['company']['balance'] += 1
            with self.assertRaisesRegex(MailboxError, 'fresh preflight differs'):
                engine.apply_guided(step['command'], key, altered)
            self.assertTrue(engine.halted)
            self.assertEqual(worker.completed_frame, 10)
        with self.fixture() as (_, engine):
            with self.assertRaisesRegex(MailboxError, 'separately approved preview'):
                engine.apply(STEPS[0]['command'], 'a:1')

    def test_false_callback_and_silent_failed_mutation_fail_stop(self):
        for body in ("callback(native_record({}), false)",
                     "callback(native_record({}), true)"):
            setup = """
                local original = api.cmd.sendCommand
                api.cmd.sendCommand=function(command, callback)
                  if command.op=='guided_name' then sent=sent+1; %s
                  else original(command, callback) end
                end
            """ % body
            with self.subTest(body=body), self.fixture(callback_setup=setup) as (worker, engine):
                seq = self.prepare(engine)
                for step in STEPS:
                    key = f"{step['actor']}:{seq[step['actor']] + 1}"
                    preview = engine.preview_guided(step['command'], key)
                    if step['action'] == 'RENAME_LINE':
                        before_frame = engine.frame
                        with self.assertRaises(MailboxError):
                            engine.apply_guided(step['command'], key, preview)
                        self.assertTrue(engine.halted)
                        self.assertEqual(worker.completed_frame, before_frame)
                        break
                    engine.apply_guided(step['command'], key, preview)
                    seq[step['actor']] += 1

    def test_rename_cannot_silently_mutate_another_guided_object(self):
        setup = """
          local original=api.cmd.sendCommand
          api.cmd.sendCommand=function(command, callback)
            if command.op=='guided_name' and world[command.entity].TRANSPORT_VEHICLE then
              local result=apply_command(command)
              for _,entity in pairs(world)do
                if entity.LINE and entity.NAME.name~='TF2 Coop Test Line' then entity.NAME.name='UNEXPECTED' end
              end
              callback(result,true)
            else original(command, callback)end
          end
        """
        with self.fixture(callback_setup=setup) as (_, engine):
            seq = self.prepare(engine)
            for step in STEPS:
                key = f"{step['actor']}:{seq[step['actor']] + 1}"
                preview = engine.preview_guided(step['command'], key)
                if step['action'] == 'RENAME_BUS':
                    with self.assertRaisesRegex(MailboxError, 'unrelated tracked object or property'):
                        engine.apply_guided(step['command'], key, preview)
                    self.assertTrue(engine.halted)
                    break
                engine.apply_guided(step['command'], key, preview)
                seq[step['actor']] += 1

    def test_automatic_and_explicit_names_still_guard_actual_local_mutation(self):
        cases = (
            ('preparation_vehicle', 'PAUSE',
             "command.op=='pause' and command.value==0 and vehicle_id~=nil"),
            ('guided_automatic_vehicle', 'CREATE_LINE',
             "command.op=='line' and (function()local n=0;for _,e in pairs(world)do if e.TRANSPORT_VEHICLE then n=n+1 end end;return n==2 end)()"),
            ('guided_explicit_vehicle', 'MAINTENANCE', "command.op=='guided_maintenance'"),
        )
        for label, action, condition in cases:
            setup = """
              local original=api.cmd.sendCommand
              api.cmd.sendCommand=function(command,callback)
                original(command,function(result,success)
                  if %s then world[vehicle_id].NAME.name='UNEXPECTED local rename' end
                  callback(result,success)
                end)
              end
            """ % condition
            # The existing synchronous failure audit reads more objects than a
            # normal callback. Allow it to publish the actual terminal status;
            # a Python mailbox timeout is not proof that this guard ran.
            with self.subTest(label=label), self.fixture(callback_setup=setup, timeout_s=15) as (worker, engine):
                step, key = self.drive_before(engine, action)
                preview = engine.preview_guided(step['command'], key)
                before_frame = engine.frame
                before = engine.snapshot()
                with self.assertRaisesRegex(MailboxError, 'vehicle name changed outside its approved rename'):
                    engine.apply_guided(step['command'], key, preview)
                status = worker.status()
                self.assertEqual(status['status'], 'halted')
                self.assertIn('vehicle name changed outside its approved rename', status['error'])
                self.assertEqual(status['snapshot'], before)
                self.assertNotIn('canonical_state_json', status)
                self.assertEqual(status['diagnostics']['snapshot_scope'], 'last_valid_before_failure')
                failure = status['diagnostics']['failure']
                self.assertEqual(failure['request_context']['command_key'], key)
                self.assertEqual(failure['request_context']['action'], 'apply')
                self.assertEqual(failure['callback']['command_key'], key)
                self.assertEqual(failure['callback']['success'], {'type': 'boolean', 'value': True})
                self.assertIsNone(worker.error)
                self.assertTrue(engine.halted)
                self.assertEqual(engine.frame, before_frame)
                time.sleep(.02)
                sends = worker.observed_sends
                with self.assertRaises(MailboxError):
                    engine.preview_guided(step['command'], key)
                time.sleep(.02)
                self.assertEqual(worker.observed_sends, sends)
                self.assertEqual(worker.completed_frame, before_frame)
                self.assertEqual(control(worker.directory / 'native_control.txt')['action'], 'halt')

    def test_explicit_rename_needs_success_real_readback_and_correct_vehicle(self):
        for label, body in (
            ('failed_callback', "callback(native_record({}),false)"),
            ('no_op_callback', "callback(native_record({}),true)"),
            ('wrong_vehicle', """
              for id,entity in pairs(world)do
                if entity.TRANSPORT_VEHICLE and id~=command.entity then
                  command.entity=id;break
                end
              end
              original(command,callback)
            """),
        ):
            setup = """
              local original=api.cmd.sendCommand
              api.cmd.sendCommand=function(command,callback)
                if command.op=='guided_name' and world[command.entity].TRANSPORT_VEHICLE then
                  %s
                else original(command,callback)end
              end
            """ % body
            with self.subTest(label=label), self.fixture(callback_setup=setup) as (_, engine):
                step, key = self.drive_before(engine, 'RENAME_BUS')
                preview = engine.preview_guided(step['command'], key)
                with self.assertRaises(MailboxError):
                    engine.apply_guided(step['command'], key, preview)
                self.assertTrue(engine.halted)
                self.assertTrue(all(item['state']['name'] == {'mode': 'automatic'}
                                    for item in engine.snapshot()['objects'] if item['kind'] == 'vehicle'))

    def test_snapshot_and_rename_receipt_require_semantic_name_contract(self):
        with self.fixture() as (_, engine):
            step, key = self.drive_before(engine, 'RENAME_BUS')
            before = engine.snapshot()
            for mutate in ('missing_contract', 'raw_name', 'automatic_with_value', 'explicit_without_text'):
                altered = copy.deepcopy(before)
                vehicle = next(item for item in altered['objects'] if item['kind'] == 'vehicle')
                if mutate == 'missing_contract':
                    altered['probe']['guided_suite'].pop('vehicle_name_contract')
                elif mutate == 'raw_name':
                    vehicle['state']['name'] = 'Road vehicle 1'
                elif mutate == 'automatic_with_value':
                    vehicle['state']['name'] = {'mode': 'automatic', 'value': 'ignored name'}
                else:
                    vehicle['state']['name'] = {'mode': 'explicit', 'value': 123}
                with self.subTest(mutate=mutate), self.assertRaises(MailboxError):
                    engine._registry(altered)
            preview = engine.preview_guided(step['command'], key)
            receipt = engine.apply_guided(step['command'], key, preview)
            altered = copy.deepcopy(preview)
            altered['observation']['expected']['name'] = 'Unrequested explicit text'
            with self.assertRaisesRegex(MailboxError, 'explicit vehicle rename differs'):
                engine._check_observation(step['command'], receipt['result']['effect'], before, engine.snapshot(), altered)


if __name__ == '__main__':
    unittest.main()
