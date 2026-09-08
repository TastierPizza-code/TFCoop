"""Production Lua and Python through real file IPC; the game API is a fixture."""
from contextlib import contextmanager
import copy
from pathlib import Path
import tempfile
import unittest

from prototype.strict_sync.engine_mailbox import EngineAdapter, MailboxError
from prototype.strict_sync.manual_depot_engine import ManualDepotEngineAdapter, ManualDepotStreamEngine
from prototype.strict_sync.short_build_profile import short_build_inputs, SHORT_BUILD_ROUNDS
from prototype.tests.test_build_mailbox_lua import BuildLuaWorker
from prototype.tests.test_engine_mailbox_lua import EPOCH, RUNTIMES


BUILD = {"op": "BUILD_DEPOT", "site": 1, "rotation": 0}


@unittest.skipUnless("lua53" in RUNTIMES, "Lua 5.3 fixture runtime unavailable")
class ManualDepotEngineTests(unittest.TestCase):
    @contextmanager
    def fixture(self, **options):
        with tempfile.TemporaryDirectory() as directory:
            worker = BuildLuaWorker(Path(directory), input_mode="manual_depot_v1", **options)
            engine = None
            try:
                engine = ManualDepotEngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                yield worker, engine
            finally:
                if engine:
                    engine.close()
                worker.close()

    def test_preview_is_read_only_then_actual_callback_adds_bound_depot_and_cost(self):
        with self.fixture() as (worker, engine):
            before = engine.snapshot()
            preview = engine.preview(BUILD, "a:1")
            self.assertTrue(preview["allowed"])
            self.assertEqual(preview["cost"], 10000)
            self.assertEqual(engine.snapshot(), before)
            self.assertEqual(worker.observed_sends, 0)
            receipt = engine.apply_manual(BUILD, "a:1", preview)
            self.assertEqual(receipt["result"]["cost"], 10000)
            self.assertEqual(engine.snapshot()["company"]["balance"], before["company"]["balance"] - 10000)
            self.assertEqual({o["logical_id"] for o in engine.snapshot()["objects"]}, {"a:1", "a:1:depot"})
            self.assertEqual(engine.frame, 0)
            self.assertEqual(engine.time_us, before["sim_time_us"])

    def test_all_quarter_turns_and_two_independent_identity_maps_match(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), self.fixture() as (_, left), self.fixture(offset=9000) as (_, right):
                command = {**BUILD, "rotation": rotation}
                pa, pb = left.preview(command, "b:1"), right.preview(command, "b:1")
                self.assertEqual(pa, pb)
                ra, rb = left.apply_manual(command, "b:1", pa), right.apply_manual(command, "b:1", pb)
                self.assertEqual(ra, rb)
                self.assertEqual(left.snapshot(), right.snapshot())

    def test_two_sites_repeated_conflict_and_duplicate_apply_do_not_mutate_twice(self):
        with self.fixture() as (worker, engine):
            first = engine.preview(BUILD, "a:1")
            receipt = engine.apply_manual(BUILD, "a:1", first)
            after = engine.snapshot()
            self.assertEqual(engine.apply_manual(BUILD, "a:1", first), receipt)
            self.assertEqual(engine.snapshot(), after)
            rejected = engine.preview({**BUILD, "rotation": 90}, "b:1")
            self.assertFalse(rejected["allowed"])
            self.assertEqual(rejected["reason"], "site_occupied")
            self.assertEqual(engine.snapshot(), after)
            second = {**BUILD, "site": 2, "rotation": 90}
            preview = engine.preview(second, "b:1")
            engine.apply_manual(second, "b:1", preview)
            self.assertEqual(len(engine.snapshot()["probe"]["manual_depot"]["placements"]), 2)
            self.assertEqual(worker.status()["diagnostics"]["bindings"].keys(), {"a:1", "a:1:depot", "b:1", "b:1:depot"})

    def test_observed_collision_and_engine_rejection_remain_nonmutating(self):
        for setup, reason in (("manual_occupied=true", "site_occupied"),
                              ("manual_critical=true", "engine_rejected"),
                              ("manual_messages={'fixture collision'}", "engine_rejected"),
                              ("manual_cost=6000000", "insufficient_funds")):
            with self.subTest(reason=reason), self.fixture(manual_setup=setup) as (worker, engine):
                before = engine.snapshot()
                preview = engine.preview(BUILD, "a:1")
                self.assertFalse(preview["allowed"])
                self.assertEqual(preview["reason"], reason)
                self.assertEqual(engine.snapshot(), before)
                self.assertEqual(worker.observed_sends, 0)
                self.assertFalse(engine.halted)

    def test_unknown_preflight_api_shape_halts_before_send_or_permit(self):
        with self.fixture(manual_setup="manual_bad_schema=true") as (worker, engine):
            with self.assertRaises(MailboxError):
                engine.preview(BUILD, "a:1")
            self.assertTrue(engine.halted)
            self.assertEqual(worker.observed_sends, 0)
            self.assertEqual(worker.completed_frame, 0)
            preflight = worker.status()["diagnostics"]["failure"]["preflight"]
            self.assertEqual(preflight["context"], "read_only_proposal_preflight")
            self.assertFalse(preflight["valid_snapshot"])

    def test_native_zero_key_message_is_not_misread_as_an_empty_error_list(self):
        with self.fixture(manual_setup="manual_messages=native_params({[0]='collision'},'pairs')") as (worker, engine):
            preview = engine.preview(BUILD, "a:1")
            self.assertFalse(preview["allowed"])
            self.assertEqual(preview["reason"], "engine_rejected")
            self.assertEqual(worker.observed_sends, 0)

    def test_nil_error_state_or_unreadable_native_messages_and_noninteger_cost_halt(self):
        for setup in (
            "api.engine.util.proposal.makeProposalData=function()return native_record({costs=10000})end",
            "manual_messages=native_params({},'opaque')",
            "manual_cost=10000.5",
            "manual_cost=-10000",
        ):
            with self.subTest(setup=setup), self.fixture(manual_setup=setup) as (worker, engine):
                with self.assertRaises(MailboxError):
                    engine.preview(BUILD, "a:1")
                self.assertTrue(engine.halted)
                self.assertEqual(worker.observed_sends, 0)
                self.assertEqual(worker.completed_frame, 0)

    def test_changed_preflight_between_joint_approval_and_apply_halts_without_send(self):
        with self.fixture(manual_setup="manual_proposal_hook=function(p,c,n) if n>=2 then manual_cost=10001 end end") as (worker, engine):
            preview = engine.preview(BUILD, "a:1")
            with self.assertRaisesRegex(MailboxError, "fresh preflight differs"):
                engine.apply_manual(BUILD, "a:1", preview)
            self.assertEqual(worker.observed_sends, 0)

    def test_wrong_actual_cost_or_pose_halts_after_callback_without_next_permit(self):
        for changed in ("money=money-1", "world[id].CONSTRUCTION.transf={1,0,0,0,0,1,0,0,0,0,1,0,1,2,10,1}"):
            setup = """
                local original=apply_command
                apply_command=function(cmd)
                  local result=original(cmd)
                  if cmd.op=='build' then
                    local id=result.resultEntities[1]
                    %s
                  end
                  return result
                end
            """ % changed
            with self.subTest(changed=changed), self.fixture(callback_setup=setup) as (worker, engine):
                preview = engine.preview(BUILD, "a:1")
                with self.assertRaises(MailboxError):
                    engine.apply_manual(BUILD, "a:1", preview)
                self.assertTrue(engine.halted)
                self.assertEqual(worker.completed_frame, 0)

    def test_loaded_reference_configuration_does_not_enable_manual_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = BuildLuaWorker(Path(directory))
            try:
                with self.assertRaisesRegex(MailboxError, "lacks the manual depot contract"):
                    ManualDepotEngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                self.assertEqual(worker.observed_sends, 0)
            finally:
                worker.close()

    def test_unapproved_generic_apply_is_terminal_without_send(self):
        with self.fixture() as (worker, engine):
            with self.assertRaises(MailboxError):
                engine.apply(BUILD, "a:1")
            self.assertTrue(engine.halted)
            self.assertEqual(worker.observed_sends, 0)

    def test_existing_short_scene_survives_new_depots_paused_and_running(self):
        with self.fixture() as (_, engine):
            sequences = {"a": 0, "b": 0}
            for number in range(SHORT_BUILD_ROUNDS):
                for peer in ("a", "b"):
                    for command in short_build_inputs(peer, number):
                        sequences[peer] += 1
                        engine.apply(command, f"{peer}:{sequences[peer]}")
                engine.step(0 if engine.paused else 200000)
            stream = ManualDepotStreamEngine(engine)
            stream.checkpoint()
            before_scene = copy.deepcopy(engine.snapshot()["probe"]["scene"])
            first = stream.preview(BUILD, "a:7")
            stream.apply_manual(BUILD, "a:7", first)
            stream.apply({"op": "SET_PAUSED", "value": True}, "b:5")
            second = {**BUILD, "site": 2, "rotation": 180}
            preview = stream.preview(second, "b:6")
            stream.apply_manual(second, "b:6", preview)
            self.assertEqual(engine.snapshot()["probe"]["scene"], before_scene)
            self.assertTrue(engine.snapshot()["probe"]["connectivity"]["connected"])
            self.assertTrue(engine.paused)
            self.assertEqual(engine.frame, SHORT_BUILD_ROUNDS)


if __name__ == "__main__":
    unittest.main()
