"""Production T2 Lua/Python/file IPC against explicit game and native fixtures.

No game process is launched. Actual in-game railway behavior still needs the
separate two-PC test; passing this module validates the adapter boundary only.
"""
from contextlib import contextmanager
import copy
from pathlib import Path
import tempfile
import unittest

from prototype.strict_sync.rail_catalog import STEPS
from prototype.strict_sync.rail_engine import RailEngineAdapter, RailStreamEngine
from prototype.strict_sync.engine_mailbox import MailboxError
from prototype.strict_sync.short_build_profile import short_build_inputs, SHORT_BUILD_ROUNDS
from prototype.tests.test_build_mailbox_lua import BuildLuaWorker
from prototype.tests.test_engine_mailbox_lua import EPOCH, RUNTIMES


@unittest.skipUnless("lua53" in RUNTIMES, "Lua 5.3 fixture runtime unavailable")
class RailEngineTests(unittest.TestCase):
    @contextmanager
    def fixture(self, **options):
        with tempfile.TemporaryDirectory() as directory:
            worker = BuildLuaWorker(Path(directory), input_mode="guided_rail_v1", **options)
            engine = None
            try:
                engine = RailEngineAdapter(directory, EPOCH, probe_only=True, timeout_s=4, poll_s=.002)
                yield worker, engine
            finally:
                if engine:
                    engine.close()
                worker.close()

    def prepare(self, engine):
        sequence = {"a": 0, "b": 0}
        for number in range(SHORT_BUILD_ROUNDS):
            for actor in ("a", "b"):
                for command in short_build_inputs(actor, number):
                    sequence[actor] += 1
                    engine.apply(command, f"{actor}:{sequence[actor]}")
            engine.step(0 if engine.paused else 200000)
        return sequence

    def drive_before(self, engine, action):
        sequence = self.prepare(engine)
        for step in STEPS:
            key = f"{step['actor']}:{sequence[step['actor']] + 1}"
            if step["action"] == action:
                return step, key, sequence
            preview = engine.preview_guided(step["command"], key)
            if step["read_only"] and not preview["allowed"]:
                self.assertFalse(engine.paused)
                engine.step(200000)
                engine.step(200000)
                preview = engine.preview_guided(step["command"], key)
            self.assertTrue(preview["allowed"], step["action"])
            engine.apply_guided(step["command"], key, preview)
            sequence[step["actor"]] += 1
        self.fail("requested railway action absent from catalogue")

    def test_all_37_actions_cross_literal_lua_and_two_real_mailboxes(self):
        with self.fixture() as (_, a), self.fixture(offset=10000) as (_, b):
            sa, sb = self.prepare(a), self.prepare(b)
            self.assertEqual(sa, sb)
            self.assertEqual(a.snapshot(), b.snapshot())
            initial = a.snapshot()
            effects = []
            for step in STEPS:
                key = f"{step['actor']}:{sa[step['actor']] + 1}"
                pa, pb = a.preview_guided(step["command"], key), b.preview_guided(step["command"], key)
                self.assertEqual(pa, pb, step["action"])
                if step["read_only"] and not pa["allowed"]:
                    self.assertEqual(pa["reason"], "not_ready")
                    self.assertFalse(a.paused)
                    for _ in range(2):
                        a.step(200000)
                        b.step(200000)
                    pa, pb = a.preview_guided(step["command"], key), b.preview_guided(step["command"], key)
                self.assertEqual(pa, pb, step["action"])
                self.assertTrue(pa["allowed"], step["action"])
                before = a.snapshot()
                frontier = (a.frame, a.time_us)
                ra, rb = a.apply_guided(step["command"], key, pa), b.apply_guided(step["command"], key, pb)
                self.assertEqual(ra, rb, step["action"])
                self.assertEqual(a.snapshot(), b.snapshot(), step["action"])
                self.assertEqual((a.frame, a.time_us), frontier, step["action"])
                self.assertEqual((b.frame, b.time_us), frontier, step["action"])
                effects.append(ra["result"]["effect"])
                effect, after = effects[-1], a.snapshot()
                self.assertEqual(effect["balance_before"], before["company"]["balance"])
                self.assertEqual(effect["balance_after"], after["company"]["balance"])
                quote = pa["observation"]["expected"].get("cost")
                if quote is not None:
                    self.assertEqual(effect["balance_before"] - effect["balance_after"], quote, step["action"])
                old_ids = {obj["logical_id"] for obj in before["objects"]}
                new_ids = {obj["logical_id"] for obj in after["objects"]}
                self.assertEqual(set(effect["created"]), new_ids - old_ids)
                self.assertEqual(set(effect["removed"]), old_ids - new_ids)
                for obj in after["objects"]:
                    if obj["kind"] == "rail_train":
                        cfg = obj["state"]["config"]
                        self.assertEqual(sum(cfg["groups"]), len(cfg["vehicles"]))
                        self.assertTrue(all(type(part["model"]) is str and part["model"].endswith(".mdl")
                                            for part in cfg["vehicles"]))
                if step["action"] in ("BUY_TRAIN", "REPLACE_TRAIN", "CLONE_TRAIN"):
                    self.assertEqual([part["model"] for part in effect["observed"]["config"]["vehicles"]],
                                     pa["observation"]["expected"]["models"])
                if step["read_only"]:
                    self.assertEqual(a.snapshot(), before)
                    self.assertEqual(effects[-1]["kind"], "observation")
                self.assertEqual(a.apply_guided(step["command"], key, pa), ra)
                sa[step["actor"]] += 1
                sb[step["actor"]] += 1
            registry = a.snapshot()["probe"]["rail_suite"]
            self.assertTrue(all(registry[field] == "" for field in ("train", "clone", "line", "station_a", "station_b",
                "depot", "connectors", "signal_a", "signal_b", "waypoint")))
            self.assertEqual({obj["logical_id"] for obj in a.snapshot()["objects"]},
                             {obj["logical_id"] for obj in initial["objects"]})
            self.assertEqual(sum(effect["kind"] == "observation" for effect in effects), 3)
            self.assertFalse(a.halted)
            self.assertFalse(b.halted)

    def test_readiness_retry_does_not_consume_command_identity_or_mutate_world(self):
        with self.fixture() as (_, engine):
            step, key, seq = self.drive_before(engine, "VERIFY_TRAIN_MOVEMENT")
            before, number = engine.snapshot(), engine._last_seq[step["actor"]]
            preview = engine.preview_guided(step["command"], key)
            self.assertFalse(preview["allowed"])
            self.assertEqual(preview["reason"], "not_ready")
            self.assertEqual(engine.snapshot(), before)
            self.assertEqual(engine._last_seq[step["actor"]], number)
            engine.step(200000)
            engine.step(200000)
            preview = engine.preview_guided(step["command"], key)
            self.assertTrue(preview["allowed"])
            actual = engine.snapshot()
            receipt = engine.apply_guided(step["command"], key, preview)
            self.assertEqual(receipt["result"]["effect"]["kind"], "observation")
            self.assertEqual(engine.snapshot(), actual)
            self.assertEqual(engine._last_seq[step["actor"]], number + 1)

    def test_direct_apply_and_changed_approved_preview_stop_before_application(self):
        with self.fixture() as (_, engine):
            self.prepare(engine)
            with self.assertRaisesRegex(MailboxError, "separately approved preview"):
                engine.apply(STEPS[0]["command"], "a:7")
            self.assertTrue(engine.halted)
        with self.fixture() as (worker, engine):
            self.prepare(engine)
            command, key = STEPS[0]["command"], "a:7"
            preview = engine.preview_guided(command, key)
            altered = copy.deepcopy(preview)
            altered["observation"]["expected"]["unapproved_extra"] = True
            with self.assertRaisesRegex(MailboxError, "fresh preflight differs"):
                engine.apply_guided(command, key, altered)
            self.assertTrue(engine.halted)
            self.assertEqual(worker.completed_frame, 10)

    def test_stream_wrapper_preserves_native_frontier_through_paused_rail_construction(self):
        with self.fixture() as (_, engine):
            sequence = self.prepare(engine)
            stream = RailStreamEngine(engine)
            stream.checkpoint()
            for step in STEPS:
                if step["action"] == "VERIFY_TRAIN_MOVEMENT":
                    break
                key = f"{step['actor']}:{sequence[step['actor']] + 1}"
                before = stream._boundary()
                preview = stream.preview_guided(step["command"], key)
                stream.apply_guided(step["command"], key, preview)
                self.assertEqual(stream.frame, before["frame"])
                self.assertEqual(stream.time_us, before["sim_time_us"])
                self.assertEqual(stream.paused, step.get("pause", before["paused"]))
                self.assertTrue(stream.observations_fresh)
                sequence[step["actor"]] += 1


if __name__ == "__main__":
    unittest.main()
