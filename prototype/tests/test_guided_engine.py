"""Production Lua/Python/file-IPC guided lifecycle using explicit game fixtures."""
from contextlib import contextmanager
import copy
from pathlib import Path
import tempfile
import unittest

from prototype.strict_sync.guided_catalog import STEPS
from prototype.strict_sync.guided_engine import GuidedEngineAdapter, GuidedStreamEngine
from prototype.strict_sync.engine_mailbox import MailboxError
from prototype.strict_sync.short_build_profile import short_build_inputs, SHORT_BUILD_ROUNDS
from prototype.tests.test_build_mailbox_lua import BuildLuaWorker
from prototype.tests.test_engine_mailbox_lua import EPOCH, RUNTIMES


@unittest.skipUnless('lua53' in RUNTIMES, 'Lua 5.3 fixture runtime unavailable')
class GuidedEngineTests(unittest.TestCase):
    @contextmanager
    def fixture(self, **options):
        with tempfile.TemporaryDirectory() as directory:
            worker = BuildLuaWorker(Path(directory), input_mode='guided_suite_v1', **options)
            engine = None
            try:
                engine = GuidedEngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
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
        with self.fixture() as (wa, a), self.fixture(offset=10000) as (wb, b):
            seq_a, seq_b = self.prepare(a), self.prepare(b)
            self.assertEqual(seq_a, seq_b)
            initial = a.snapshot()
            self.assertEqual(initial, b.snapshot())
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


if __name__ == '__main__':
    unittest.main()
