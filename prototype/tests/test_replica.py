"""Validate every replica gate before allowing a model adapter call."""

import copy
import unittest

from prototype.strict_sync import CAPABILITIES, MAX_INT, Coordinator, ProtocolError, digest
from prototype.strict_sync.model import ModelEngine, scenario
from prototype.strict_sync.replica import Replica


EPOCH = "replica_test_0001"
MANIFEST = digest({"adapter": "replica-tests-v1"})
DEPOT = {"op": "DEPOT", "position_mm": [0, 0], "metadata": {"flag": True}}


def rehash(plan):
    plan["plan_hash"] = digest({key: value for key, value in plan.items()
                                if key not in ("kind", "plan_hash")})
    return plan


class Harness:
    def __init__(self, a=None, b=None, engine_a=None):
        self.c = Coordinator(EPOCH, MANIFEST, clock=lambda: 1.0)
        self.engines = {"a": engine_a or ModelEngine(100), "b": ModelEngine(9000)}
        batches = {"a": {0: [copy.deepcopy(DEPOT)]} if a is None else a,
                   "b": {} if b is None else b}
        self.replicas = {
            peer: Replica(peer, EPOCH, MANIFEST, CAPABILITIES, self.engines[peer],
                          lambda round_number, p=peer: copy.deepcopy(batches[p].get(round_number, [])))
            for peer in ("a", "b")
        }

    def initial_actions(self):
        assert self.c.receive("a", self.replicas["a"].hello()) == []
        return self.c.receive("b", self.replicas["b"].hello())

    def deliver(self, actions):
        following = []
        for peer, message in actions:
            reply = self.replicas[peer].receive(message)
            if reply is not None:
                following.extend(self.c.receive(peer, reply))
        return following

    def plans(self):
        return self.deliver(self.initial_actions())

    def ready(self):
        return self.deliver(self.plans())


class ReplicaGateTests(unittest.TestCase):
    def assert_refused_without_execution(self, h, message):
        engine = h.engines["a"]
        before, operations = engine.snapshot(), copy.deepcopy(engine.operations)
        with self.assertRaises(ProtocolError):
            h.replicas["a"].receive(message)
        self.assertTrue(h.replicas["a"].halted)
        self.assertEqual(engine.snapshot(), before)
        self.assertEqual(engine.operations, operations)

    def test_full_two_replica_scenario_preserves_world_and_identity(self):
        h = Harness(a=scenario("a"), b=scenario("b"))
        actions = h.initial_actions()
        while h.c.round < 14:
            self.assertTrue(actions)
            actions = h.deliver(actions)
            self.assertFalse(h.c.halted, h.c.halt_reason)
        self.assertEqual(h.engines["a"].snapshot(), h.engines["b"].snapshot())
        self.assertNotEqual(h.engines["a"].physical_ids, h.engines["b"].physical_ids)
        self.assertEqual(h.engines["a"].time_us, 800000)
        self.assertEqual(h.engines["a"].vehicles["a:5"]["line"], "a:3")
        self.assertEqual(h.engines["a"].lines["a:3"]["stops"], ["a:2", "seed:depot", "a:2"])

    def test_request_boolean_numeric_and_schema_substitutions_refused(self):
        for change in [{"frame": False}, {"sim_time_us": False}, {"paused": 1},
                       {"round": False}, {"max_commands": True}, {"extra": 1},
                       {"epoch": "some_other_epoch"}]:
            with self.subTest(change=change):
                h = Harness()
                request = h.initial_actions()[0][1]
                self.assert_refused_without_execution(h, {**request, **change})

    def test_wrong_plan_hash_and_prepared_fields_refused(self):
        for field, value in [("plan_hash", "0" * 64), ("frame", False), ("sim_time_us", False),
                             ("paused", 1), ("step_us", True), ("step_us", 0),
                             ("step_us", -1), ("step_us", 10_000_001),
                             ("step_us", 200000), ("manifest_digest", "0" * 64),
                             ("roster", ["b", "a"]), ("capabilities", [])]:
            with self.subTest(field=field, value=value):
                h = Harness()
                plan = h.plans()[0][1]
                plan[field] = value
                if field != "plan_hash":
                    rehash(plan)
                self.assert_refused_without_execution(h, plan)

    def test_nan_or_float_fixed_step_refused(self):
        for value in [float("nan"), float("inf"), 100000.0]:
            h = Harness()
            plan = h.plans()[0][1]
            plan["step_us"] = value
            self.assert_refused_without_execution(h, plan)

    def test_plan_cannot_change_local_body_from_bool_to_integer(self):
        h = Harness()
        plan = h.plans()[0][1]
        plan["commands"][0]["command"]["metadata"]["flag"] = 1
        self.assert_refused_without_execution(h, rehash(plan))

    def test_plan_cannot_omit_or_add_local_sealed_command(self):
        for mutate in [lambda plan: plan["commands"].clear(),
                       lambda plan: plan["commands"].append({"origin": "a", "seq": 2, "command": DEPOT})]:
            h = Harness()
            plan = h.plans()[0][1]
            mutate(plan)
            self.assert_refused_without_execution(h, rehash(plan))

    def test_plan_requires_origin_sequence_order_and_remote_contiguity(self):
        mutations = [
            lambda p: p["commands"].reverse(),
            lambda p: p["commands"][1].update(seq=2),
            lambda p: p["commands"][1].update(seq=True),
            lambda p: p["commands"][1].update(origin="c"),
            lambda p: p["commands"].append(copy.deepcopy(p["commands"][1])),
        ]
        for mutate in mutations:
            h = Harness(b={0: [copy.deepcopy(DEPOT)]})
            plan = h.plans()[0][1]
            mutate(plan)
            self.assert_refused_without_execution(h, rehash(plan))

    def test_remote_sequence_cannot_restart_on_next_round(self):
        h = Harness(a={}, b={0: [copy.deepcopy(DEPOT)], 1: [copy.deepcopy(DEPOT)]})
        actions = h.initial_actions()
        while h.c.round < 1:
            actions = h.deliver(actions)
        plans = h.deliver(actions)
        plan = plans[0][1]
        self.assertEqual(plan["commands"][0]["seq"], 2)
        plan["commands"][0]["seq"] = 1
        self.assert_refused_without_execution(h, rehash(plan))

    def test_apply_before_prepared_plan_never_reaches_adapter(self):
        h = Harness()
        plan = h.plans()[0][1]
        item = plan["commands"][0]
        message = {"kind": "apply", "epoch": EPOCH, "round": 0,
                   "plan_hash": plan["plan_hash"], "index": 0, "command_key": "a:1", **item}
        self.assert_refused_without_execution(h, message)

    def test_wrong_index_key_plan_sequence_and_body_refused_before_execution(self):
        changes = [{"index": 1}, {"index": False}, {"seq": True}, {"seq": 2},
                   {"command_key": "b:1"}, {"plan_hash": "0" * 64}, {"round": 1},
                   {"command": {**DEPOT, "metadata": {"flag": 1}}}, {"extra": 0}]
        for change in changes:
            h = Harness()
            action = h.ready()[0][1]
            self.assert_refused_without_execution(h, {**action, **change})

    def test_step_before_pending_command_is_refused(self):
        h = Harness()
        h.ready()
        message = {"kind": "step", "epoch": EPOCH, "round": 0, "plan_hash": h.c.plan_hash,
                   "frame": 1, "dt_us": 0, "sim_time_us": 0}
        self.assert_refused_without_execution(h, message)

    def test_step_before_plan_acceptance_is_refused_even_if_no_commands(self):
        h = Harness(a={})
        h.plans()
        message = {"kind": "step", "epoch": EPOCH, "round": 0, "plan_hash": h.c.plan_hash,
                   "frame": 1, "dt_us": 0, "sim_time_us": 0}
        self.assert_refused_without_execution(h, message)

    def test_invalid_paused_step_types_time_and_size_do_not_reach_adapter(self):
        changes = [{"dt_us": False}, {"frame": True}, {"sim_time_us": False},
                   {"dt_us": 100000, "sim_time_us": 100000}, {"frame": 2},
                   {"dt_us": 10_000_001}, {"dt_us": MAX_INT + 1}]
        for change in changes:
            h = Harness(a={})
            step = h.ready()[0][1]
            self.assert_refused_without_execution(h, {**step, **change})

    def test_exact_apply_duplicate_never_calls_adapter_twice(self):
        h = Harness()
        action = h.ready()[0][1]
        receipt = h.replicas["a"].receive(action)
        snapshot = h.engines["a"].snapshot()
        for _ in range(10):
            self.assertEqual(h.replicas["a"].receive(copy.deepcopy(action)), receipt)
        self.assertEqual(len(h.engines["a"].operations), 1)
        self.assertEqual(h.engines["a"].snapshot(), snapshot)

    def test_conflicting_duplicate_body_bool_integer_halts_without_second_call(self):
        h = Harness()
        action = h.ready()[0][1]
        h.replicas["a"].receive(action)
        altered = copy.deepcopy(action)
        altered["command"]["metadata"]["flag"] = 1
        self.assert_refused_without_execution(h, altered)

    def test_duplicate_step_never_advances_twice(self):
        h = Harness(a={0: [{"op": "SET_PAUSED", "value": False}]})
        step = h.deliver(h.ready())[0][1]
        receipt = h.replicas["a"].receive(step)
        self.assertEqual(h.engines["a"].time_us, 100000)
        self.assertEqual(h.replicas["a"].receive(step), receipt)
        self.assertEqual(h.engines["a"].time_us, 100000)

    def test_paused_commands_execute_but_time_and_step_world_stay_fixed(self):
        h = Harness()
        step_actions = h.deliver(h.ready())
        self.assertEqual(len(h.engines["a"].depots), 2)
        before = h.engines["a"].snapshot()
        h.deliver(step_actions)
        self.assertEqual(h.engines["a"].snapshot(), before)
        self.assertEqual(h.replicas["a"].frame, 1)

    def test_external_world_change_before_action_is_detected(self):
        h = Harness()
        action = h.ready()[0][1]
        h.engines["a"].money -= 1
        self.assert_refused_without_execution(h, action)

    def test_caller_cannot_modify_sealed_batch_or_cached_reply(self):
        h = Harness()
        requests = h.initial_actions()
        reply = h.replicas["a"].receive(requests[0][1])
        original = copy.deepcopy(reply)
        reply["commands"][0]["command"]["metadata"]["flag"] = 1
        self.assertEqual(h.replicas["a"].receive(requests[0][1]), original)
        self.assertEqual(h.replicas["a"].sealed, original["commands"])

    def test_halt_and_complete_are_terminal_and_identical_duplicates_idempotent(self):
        for kind in ["halt", "complete"]:
            h = Harness(a={})
            if kind == "halt":
                msg = {"kind": kind, "epoch": EPOCH, "round": 0, "reason": "peer lost"}
            else:
                engine = h.engines["a"]
                msg = {"kind": kind, "epoch": EPOCH, "round": 0, "frame": 0,
                       "state_digest": engine.state_digest, "sim_time_us": 0}
            self.assertIsNone(h.replicas["a"].receive(msg))
            self.assertIsNone(h.replicas["a"].receive(copy.deepcopy(msg)))
            with self.assertRaises(ProtocolError):
                h.replicas["a"].receive({**msg, "round": 1})


class BrokenAdapterTests(unittest.TestCase):
    def test_apply_cannot_advance_time_even_with_matching_receipt(self):
        class AdvancesTime(ModelEngine):
            def apply(self, command, command_key):
                receipt = super().apply(command, command_key)
                self.time_us += 1
                return {**receipt, "state_digest": self.state_digest}
        h = Harness(engine_a=AdvancesTime())
        action = h.ready()[0][1]
        with self.assertRaisesRegex(ProtocolError, "advanced simulation time"):
            h.replicas["a"].receive(action)
        self.assertTrue(h.replicas["a"].halted)

    def test_apply_cannot_change_pause_without_pause_command(self):
        class ChangesPause(ModelEngine):
            def apply(self, command, command_key):
                receipt = super().apply(command, command_key)
                self.paused = False
                return {**receipt, "state_digest": self.state_digest}
        h = Harness(engine_a=ChangesPause())
        action = h.ready()[0][1]
        with self.assertRaisesRegex(ProtocolError, "pause without"):
            h.replicas["a"].receive(action)
        self.assertTrue(h.replicas["a"].halted)

    def test_adapter_integer_success_is_rejected(self):
        class IntegerSuccess(ModelEngine):
            def apply(self, command, command_key):
                return {**super().apply(command, command_key), "success": 1}
        h = Harness(engine_a=IntegerSuccess())
        action = h.ready()[0][1]
        with self.assertRaises(ProtocolError):
            h.replicas["a"].receive(action)
        self.assertTrue(h.replicas["a"].halted)

    def test_adapter_failure_returns_receipt_and_closes_gate_immediately(self):
        h = Harness(a={0: [{"op": "UNSUPPORTED"}]})
        action = h.ready()[0][1]
        receipt = h.replicas["a"].receive(action)
        self.assertFalse(receipt["success"])
        self.assertTrue(h.replicas["a"].halted)
        with self.assertRaises(ProtocolError):
            h.replicas["a"].receive(action)

    def test_adapter_exception_closes_gate(self):
        class Explodes(ModelEngine):
            def apply(self, command, command_key):
                raise RuntimeError("adapter exploded")
        h = Harness(engine_a=Explodes())
        action = h.ready()[0][1]
        with self.assertRaisesRegex(ProtocolError, "adapter exploded"):
            h.replicas["a"].receive(action)
        self.assertTrue(h.replicas["a"].halted)

    def test_step_must_check_actual_time_not_only_adapter_report(self):
        class LiesAboutTime(ModelEngine):
            def step(self, dt_us):
                receipt = super().step(dt_us)
                self.time_us += 1
                return {**receipt, "state_digest": self.state_digest}
        h = Harness(a={}, engine_a=LiesAboutTime())
        step = h.ready()[0][1]
        with self.assertRaisesRegex(ProtocolError, "violated step permit"):
            h.replicas["a"].receive(step)
        self.assertTrue(h.replicas["a"].halted)

    def test_paused_step_cannot_change_money_without_time_progress(self):
        class PausedIncome(ModelEngine):
            def step(self, dt_us):
                receipt = super().step(dt_us)
                self.money += 1
                return {**receipt, "state_digest": self.state_digest}
        h = Harness(a={}, engine_a=PausedIncome())
        step = h.ready()[0][1]
        with self.assertRaisesRegex(ProtocolError, "paused step changed world"):
            h.replicas["a"].receive(step)
        self.assertTrue(h.replicas["a"].halted)

    def test_input_collector_cannot_mutate_world(self):
        h = Harness()
        request = h.initial_actions()[0][1]
        def collector(_):
            h.engines["a"].money -= 1
            return []
        h.replicas["a"].inputs = collector
        with self.assertRaisesRegex(ProtocolError, "outside a permitted"):
            h.replicas["a"].receive(request)
        self.assertTrue(h.replicas["a"].halted)
        self.assertEqual(h.engines["a"].operations, [])


if __name__ == "__main__":
    unittest.main()
