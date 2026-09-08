"""Independent evolving protocol models; no TF2 or gameplay proof is claimed."""
import copy
import unittest

from prototype.strict_sync.core import CAPABILITIES, ProtocolError, digest
from prototype.strict_sync.guided_catalog import STEPS, get_step
from prototype.strict_sync.guided_input import validate_command
from prototype.strict_sync.guided_probe import GuidedCoordinator, GuidedReplica, GUIDED_CAPABILITY, schedule, STEP_US
from prototype.tests.test_paced_live_probe import ScriptedInputs, PacedLiveTests, EPOCH, MANIFEST
from prototype.tests.test_stream_probe import BaseWorldModel, StreamWorldModel


def action(step):
    return {"op": "GUIDED_ACTION", "step": step}


def fixture_inputs():
    result = {"a": {}, "b": {}}
    for step in STEPS:
        result[step["actor"]][step["step"] - 1] = [step["command"]]
    return result


def model_preview(engine, command, *, not_ready=False):
    step = get_step(command["step"])
    return {"allowed": not not_ready, "reason": "not_ready" if not_ready else "",
        "step": step["step"], "action": step["action"], "state_digest": engine.state_digest,
        "observation": {"company": {"balance": engine.world["balance"], "loan": 5000000},
                        "expected": {"model_step": step["step"]}}}


def model_apply(engine, command, key):
    step = get_step(command["step"])
    before = engine.world["balance"]
    if not step["read_only"]:
        engine.world["guide_step"] = step["step"]
    if "pause" in step:
        engine.world["paused"] = step["pause"]
    if step["action"] == "BUY_BUS":
        engine.world["balance"] -= 10000
    if step["action"] == "SELL_BUS":
        engine.world["balance"] += 5000
    engine.commands.append((key, copy.deepcopy(command)))
    engine.observed = copy.deepcopy(engine.world)
    return {"success": True, "state_digest": engine.state_digest,
        "result": {"op": "GUIDED_ACTION", "step": step["step"], "action": step["action"],
            "command_key": key, "effect": {"balance_before": before, "balance_after": engine.world["balance"],
                "loan_before": 5000000, "loan_after": 5000000,
                "observed": {"model_action": step["action"]},
                "kind": "observation" if step["read_only"] else "callback", "target": "model-target",
                "created": [], "removed": []}}}


class GuidedStreamModel(StreamWorldModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.previews = []
        self.not_ready = self.fail_apply = self.mutate_preview = False

    def preview_guided(self, command, key):
        self._stop()
        self.engine._fresh()
        if self.mutate_preview:
            self.engine.world["balance"] -= 1
            self.engine.observed = copy.deepcopy(self.engine.world)
        result = model_preview(self.engine, command, not_ready=self.not_ready)
        self.previews.append((copy.deepcopy(command), key, copy.deepcopy(result)))
        return result

    def apply_guided(self, command, key, preview):
        if self.fail_apply:
            raise ProtocolError("explicit model callback failed")
        if not preview["allowed"] or self.preview_guided(command, key) != preview:
            raise ProtocolError("explicit model preflight changed")
        receipt = model_apply(self.engine, command, key)
        if get_step(command["step"]).get("pause") is False:
            self.next_call_us = self.clock_us + STEP_US
        return receipt


class GuidedProbeTests(unittest.TestCase):
    exchange = PacedLiveTests.exchange
    until = PacedLiveTests.until
    complete = PacedLiveTests.complete

    def pair(self, inputs=None):
        inputs = inputs or {}
        caps = tuple(sorted((*CAPABILITIES, GUIDED_CAPABILITY)))
        c = GuidedCoordinator(EPOCH, MANIFEST, caps, step_us=STEP_US)
        engines = {peer: BaseWorldModel() for peer in ("a", "b")}
        for engine in engines.values():
            engine.world.update(frame=10, time=200000, balance=5000000, guide_step=0)
            engine.observed = copy.deepcopy(engine.world)
        sources = {peer: ScriptedInputs(inputs.get(peer, {})) for peer in engines}
        replicas = {peer: GuidedReplica(peer, EPOCH, MANIFEST, caps, engines[peer], lambda _: [],
            frame=10, step_us=STEP_US, stream_engine_factory=GuidedStreamModel,
            live_input_source=sources[peer]) for peer in engines}
        c.round = c.frame = 10
        c.sim_time_us, c.state_digest = engines["a"].time_us, engines["a"].state_digest
        for replica in replicas.values():
            replica.round = 10
            replica._pause_clock = lambda replica=replica: replica.stream_engine.clock_us / 1000000
        c._pause_clock = lambda: min(engine.stream.clock_us for engine in engines.values()) / 1000000
        return c, replicas, engines, sources

    def test_first_instruction_waits_for_both_start_receipts(self):
        c, replicas, _, _ = self.pair()
        for machine in (c, *replicas.values()):
            self.assertEqual(machine.guide_status()['phase'], 'waiting')
            self.assertFalse(machine.guide_status()['ready'])
        actions = c._request_inputs()
        self.assertTrue(c.live_progress()['started'])
        self.assertFalse(c.guide_status()['ready'])
        response_a = replicas['a'].receive(actions[0][1])
        self.assertFalse(replicas['a'].guide_status()['ready'])
        self.assertEqual(c.receive('a', response_a), [])
        self.assertFalse(c.guide_status()['ready'])
        response_b = replicas['b'].receive(actions[1][1])
        self.assertFalse(replicas['b'].guide_status()['ready'])
        following = c.receive('b', response_b)
        self.assertTrue(c.guide_status()['ready'])
        # The host's following authenticated operation certifies both receipts
        # to each replica; a replica's own local startup is insufficient.
        self.assertFalse(replicas['a'].guide_status()['ready'])
        replicas['a'].receive(following[0][1])
        self.assertTrue(replicas['a'].guide_status()['ready'])
        self.assertFalse(replicas['b'].guide_status()['ready'])

    def test_complete_catalogue_uses_actor_requests_and_identical_compared_effects(self):
        c, r, engines, sources = self.pair(fixture_inputs())
        self.until(c, r, c._request_inputs())
        self.complete(c, r)
        self.assertTrue(c.live_report()["required_guided_interactions_met"])
        self.assertEqual(c.guide_status()["completed_step_ids"], [s["id"] for s in STEPS])
        self.assertEqual(c.live_report()["guided_records"], r["a"].live_report()["guided_records"])
        self.assertEqual(c.live_report()["guided_records"], r["b"].live_report()["guided_records"])
        self.assertEqual(engines["a"].world, engines["b"].world)
        self.assertEqual(engines["a"].world["balance"], 4995000)
        self.assertEqual(len(engines["a"].commands), len(STEPS))
        self.assertEqual(c.guide_status()["phase"], "completed")
        self.assertFalse(c.live_report()["native_ui_input_capture"])
        self.assertFalse(c.live_report()["full_world_verified"])

    def test_step_does_not_advance_until_both_receipts_and_both_settlement_acks(self):
        c, r, engines, _ = self.pair({"a": {0: [action(1)]}})
        actions = self.until(c, r, c._request_inputs(), "live_apply")
        self.assertEqual(c.receive("a", r["a"].receive(actions[0][1])), [])
        self.assertEqual(c.guide_status()["step"], 1)
        self.assertEqual(c.guide_status()["completed_steps"], 0)
        settle = c.receive("b", r["b"].receive(actions[1][1]))
        self.assertEqual(settle[0][1]["kind"], "live_settle")
        first = r["a"].receive(settle[0][1])
        self.assertEqual(c.receive("a", first), [])
        self.assertEqual(c.guide_status()["step"], 1)
        self.assertEqual(r["a"].guide_status()["step"], 1)
        next_actions = c.receive("b", r["b"].receive(settle[1][1]))
        self.assertEqual(c.guide_status()["step"], 2)
        self.assertEqual(r["b"].guide_status()["step"], 1)
        r["a"].receive(next_actions[0][1])
        self.assertEqual(r["a"].guide_status()["step"], 2)
        self.assertEqual(len(engines["a"].commands), 1)

    def test_wrong_actor_future_and_duplicate_are_rejected_without_running_them(self):
        inputs = {"a": {0: [action(2), action(1), action(1)]}, "b": {0: [action(1)]}}
        c, r, engines, _ = self.pair(inputs)
        actions = self.until(c, r, c._request_inputs(), "live_settle")
        outcomes = actions[0][1]["outcomes"]
        self.assertEqual({o["reason"] for o in outcomes if o["status"] == "input_rejected"},
                         {"future_step", "duplicate_step", "wrong_actor"})
        self.exchange(c, r, actions)
        self.assertEqual(c.guide_status()["step"], 2)
        self.assertEqual([cmd for _, cmd in engines["a"].commands], [action(1)])
        self.assertEqual(engines["a"].world["balance"], 5000000)

    def test_stale_step_never_repeats_native_command(self):
        c, r, engines, _ = self.pair({"a": {0: [action(1)], 1: [action(1)]}})
        first = self.until(c, r, c._request_inputs(), "live_settle")
        second = self.until(c, r, self.exchange(c, r, first), "live_settle")
        self.assertEqual(second[0][1]["outcomes"][0]["reason"], "stale_step")
        self.exchange(c, r, second)
        self.assertEqual(c.guide_status()["step"], 2)
        self.assertEqual(len(engines["a"].commands), 1)

    def test_not_ready_is_read_only_and_can_retry_without_skipping_observation(self):
        verify = next(step["step"] for step in STEPS if step["action"] == "VERIFY_MOVEMENT")
        inputs = fixture_inputs()
        for peer in inputs:
            inputs[peer] = {cycle: value for cycle, value in inputs[peer].items() if cycle < verify}
        inputs["b"][verify] = [action(verify)]
        c, r, engines, _ = self.pair(inputs)
        actions = c._request_inputs()
        while actions and not (actions[0][1]["kind"] == "live_preview" and actions[0][1]["request"]["command"] == action(verify)):
            actions = self.exchange(c, r, actions)
        for engine in engines.values():
            engine.stream.not_ready = True
        rejected = self.until(c, r, actions, "live_settle")
        self.assertEqual(rejected[0][1]["outcomes"][0]["status"], "not_ready")
        self.assertEqual(c.guide_status()["step"], verify)
        actions = self.exchange(c, r, rejected)
        for engine in engines.values():
            engine.stream.not_ready = False
        retried = self.until(c, r, actions, "live_settle")
        self.exchange(c, r, retried)
        self.assertEqual(c.guide_status()["step"], verify + 1)
        self.assertEqual(sum(cmd == action(verify) for _, cmd in engines["a"].commands), 1)

    def test_bad_peer_preview_or_callback_halts_before_any_next_step(self):
        for kind in ("live_preview", "live_apply"):
            with self.subTest(kind=kind):
                c, r, engines, _ = self.pair({"a": {0: [action(1)]}})
                actions = self.until(c, r, c._request_inputs(), kind)
                a = r["a"].receive(actions[0][1])
                b = r["b"].receive(actions[1][1])
                if kind == "live_preview":
                    b["preview"]["observation"]["expected"]["model_step"] = 2
                else:
                    b["receipt"]["result"]["effect"]["observed"]["model_action"] = "different"
                self.assertEqual(c.receive("a", a), [])
                c.receive("b", b)
                self.assertTrue(c.halted)
                self.assertEqual(c.guide_status()["completed_steps"], 0)
                self.assertEqual(c.frame, 10)

    def test_retransmitted_actions_are_cached_even_after_settlement(self):
        c, r, engines, _ = self.pair({"a": {0: [action(1)]}})
        actions = self.until(c, r, c._request_inputs(), "live_apply")
        reply = r["a"].receive(actions[0][1])
        self.assertEqual(reply, r["a"].receive(actions[0][1]))
        self.assertEqual(len(engines["a"].commands), 1)
        c.receive("a", reply)
        settle = c.receive("b", r["b"].receive(actions[1][1]))
        continuation = self.exchange(c, r, settle)
        self.exchange(c, r, continuation)
        self.assertEqual(reply, r["a"].receive(actions[0][1]))
        self.assertEqual(len(engines["a"].commands), 1)

    def test_empty_guide_keeps_the_accepted_pacing_grants(self):
        fixture = PacedLiveTests()
        c, r, _, _ = self.pair()
        old, old_r, _, _ = fixture.pair()
        current_actions, old_actions = c._request_inputs(), old._request_inputs()
        for _ in range(65):
            self.assertEqual(current_actions[0][1]["kind"], old_actions[0][1]["kind"])
            if current_actions[0][1]["kind"] == "live_advance":
                self.assertEqual(current_actions[0][1]["steps"], old_actions[0][1]["steps"])
            current_actions = self.exchange(c, r, current_actions)
            old_actions = fixture.exchange(old, old_r, old_actions)
        self.assertEqual(schedule()["chunk_steps"], 2)
        self.assertEqual(schedule()["checkpoint_steps"], 50)

    def test_command_validation_excludes_coordinates_arbitrary_actions_and_bool_step(self):
        for command in ({"op": "GUIDED_ACTION", "step": True}, {"op": "GUIDED_ACTION", "step": 0},
                        {"op": "GUIDED_ACTION", "step": 1, "pos": [1, 2, 3]}, {"op": "SET_PAUSED", "value": True}):
            with self.subTest(command=command), self.assertRaises(ProtocolError):
                validate_command(command)


if __name__ == "__main__":
    unittest.main()
