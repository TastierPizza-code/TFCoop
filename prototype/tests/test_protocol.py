"""Adversarial protocol tests. These do not exercise the TF2 engine."""

import copy
import json
import unittest

from prototype.strict_sync import (
    CAPABILITIES, MAX_COMMANDS_PER_PEER, MAX_INT, Coordinator, ProtocolError,
    canonical_json, decode_message, digest, verify_plan,
)


EPOCH = "test_epoch_0001"
MANIFEST = digest({"adapter": "test", "version": 1})
START = digest({"world": "initial"})


class Harness:
    def __init__(self, paused=False, frame=0, sim_time_us=0):
        self.now = 1.0
        self.c = Coordinator(EPOCH, MANIFEST, clock=lambda: self.now, timeout_s=3)
        self.initial = dict(manifest_digest=MANIFEST, capabilities=list(CAPABILITIES),
                            state_digest=START, frame=frame, sim_time_us=sim_time_us,
                            paused=paused)

    def msg(self, kind, **fields):
        return dict(kind=kind, epoch=EPOCH, **fields)

    def send(self, peer, kind, **fields):
        return self.c.receive(peer, self.msg(kind, **fields))

    def start(self):
        assert self.send("a", "hello", **self.initial) == []
        return self.send("b", "hello", **self.initial)

    def plan(self, a=(), b=(), first="a"):
        batches = {"a": list(a), "b": list(b)}
        assert self.send(first, "inputs", round=self.c.round, commands=batches[first]) == []
        return self.send("b" if first == "a" else "a", "inputs", round=self.c.round,
                         commands=batches["b" if first == "a" else "a"])

    def prepare(self):
        fields = dict(round=self.c.round, plan_hash=self.c.plan_hash)
        assert self.send("a", "prepared", **fields) == []
        return self.send("b", "prepared", **fields)

    def applied(self, index, result=None, state=None):
        fields = dict(round=self.c.round, plan_hash=self.c.plan_hash, index=index,
                      success=True, result={} if result is None else result,
                      state_digest=state or digest({"command": index}))
        assert self.send("a", "applied", **fields) == []
        return self.send("b", "applied", **fields)

    def stepped(self, action, state=None):
        fields = dict(round=self.c.round, plan_hash=self.c.plan_hash,
                      frame=action["frame"], sim_time_us=action["sim_time_us"],
                      state_digest=state or digest({"frame": action["frame"]}))
        assert self.send("a", "stepped", **fields) == []
        return self.send("b", "stepped", **fields)


def command(seq, op="ROAD", **fields):
    return {"seq": seq, "command": {"op": op, **fields}}


class CanonicalJsonTests(unittest.TestCase):
    def test_map_order_is_canonical_but_array_order_matters(self):
        self.assertEqual(digest({"b": 2, "a": 1}), digest({"a": 1, "b": 2}))
        self.assertNotEqual(digest([1, 2]), digest([2, 1]))

    def test_bool_is_not_integer_in_canonical_results(self):
        self.assertNotEqual(canonical_json(True), canonical_json(1))

    def test_rejects_all_floats_nan_infinity_and_large_integer(self):
        for value in [1.0, float("nan"), float("inf"), -float("inf"),
                      MAX_INT + 1, -MAX_INT - 1]:
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                canonical_json({"value": value})
        self.assertEqual(json.loads(canonical_json(MAX_INT)), MAX_INT)

    def test_rejects_non_json_types_non_string_keys_and_surrogates(self):
        for value in [{1: "x"}, (1, 2), {1, 2}, b"x", "\ud800"]:
            with self.subTest(value=repr(value)), self.assertRaises(ProtocolError):
                canonical_json(value)

    def test_bounded_depth_nodes_and_bytes(self):
        deep = []
        for _ in range(14):
            deep = [deep]
        for value in [deep, [0] * 4097, "x" * 65537]:
            with self.assertRaises(ProtocolError):
                canonical_json(value)
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(ProtocolError):
            canonical_json(cyclic)

    def test_decode_rejects_duplicate_keys_float_and_nonobject(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                    b'{"a":1.0}', b'[]', b'\xff', b'{} trailing', b'{"x":{"a":1,"a":1}}']:
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                decode_message(raw)
        self.assertEqual(decode_message(b'{"x":1}'), {"x": 1})


class HandshakeTests(unittest.TestCase):
    def test_both_actual_states_required_before_inputs(self):
        h = Harness()
        self.assertEqual(h.send("a", "hello", **h.initial), [])
        self.assertEqual(h.c.phase, "hello")
        altered = {**h.initial, "state_digest": digest({"world": "other save"})}
        actions = h.send("b", "hello", **altered)
        self.assertTrue(h.c.halted)
        self.assertEqual([m["kind"] for _, m in actions], ["halt", "halt"])

    def test_manifest_capability_frame_time_and_pause_mismatches_halt(self):
        changes = [{"manifest_digest": "0" * 64}, {"capabilities": ["state_digest"]},
                   {"frame": 1}, {"sim_time_us": 1}, {"paused": True}]
        for change in changes:
            with self.subTest(change=change):
                h = Harness()
                h.send("a", "hello", **h.initial)
                h.send("b", "hello", **{**h.initial, **change})
                self.assertTrue(h.c.halted)

    def test_false_is_not_valid_frame_or_time(self):
        for name in ["frame", "sim_time_us"]:
            h = Harness()
            h.send("a", "hello", **{**h.initial, name: False})
            self.assertTrue(h.c.halted)

    def test_initial_pause_and_zero_time_are_valid(self):
        h = Harness(paused=True)
        self.assertEqual(h.start()[0][1]["kind"], "request_inputs")
        h.plan()
        action = h.prepare()[0][1]
        self.assertEqual(action["dt_us"], 0)
        self.assertEqual(action["sim_time_us"], 0)
        self.assertEqual(action["frame"], 1)

    def test_epoch_cannot_be_reassigned(self):
        h = Harness()
        with self.assertRaises(AttributeError):
            h.c.epoch = "another_epoch"

    def test_wrong_epoch_unknown_peer_and_unexpected_fields_halt(self):
        for peer, extras in [("c", {}), ("a", {"epoch": "other_epoch"}),
                             ("a", {"unrecognized": True})]:
            h = Harness()
            h.c.receive(peer, {**h.msg("hello", **h.initial), **extras})
            self.assertTrue(h.c.halted)


class RoundBarrierTests(unittest.TestCase):
    def test_even_empty_peer_batch_is_mandatory(self):
        h = Harness()
        h.start()
        self.assertEqual(h.send("a", "inputs", round=0, commands=[command(1)]), [])
        self.assertEqual(h.c.phase, "inputs")
        h.now = 4.0
        self.assertEqual(h.c.tick()[0][1]["kind"], "halt")
        self.assertEqual(h.c.round, 0)

    def test_plan_order_independent_of_peer_arrival(self):
        plans = []
        for first in ["a", "b"]:
            h = Harness()
            h.start()
            plan = h.plan([command(1), command(2)], [command(1)], first)[0][1]
            self.assertTrue(verify_plan(plan))
            plans.append(plan)
        self.assertEqual(plans[0], plans[1])
        self.assertEqual([(c["origin"], c["seq"]) for c in plans[0]["commands"]],
                         [("a", 1), ("a", 2), ("b", 1)])

    def test_plan_hash_covers_payload_start_state_and_fixed_step(self):
        h = Harness()
        h.start()
        plan = h.plan([command(1)])[0][1]
        for field, value in [("frame", 99), ("step_us", 1), ("epoch", "other_epoch"),
                             ("pre_state_digest", "0" * 64), ("commands", [])]:
            self.assertFalse(verify_plan({**plan, field: value}))

    def test_prepare_and_each_command_need_two_matching_receipts(self):
        h = Harness()
        h.start()
        h.plan([command(1), command(2)])
        self.assertEqual(h.c.phase, "prepared")
        first = h.prepare()[0][1]
        self.assertEqual(first["kind"], "apply")
        self.assertEqual(first["index"], 0)
        second = h.applied(0)[0][1]
        self.assertEqual(second["index"], 1)
        step = h.applied(1)[0][1]
        self.assertEqual(step["kind"], "step")
        self.assertEqual(h.c.round, 0)
        next_inputs = h.stepped(step)
        self.assertEqual(next_inputs[0][1]["kind"], "request_inputs")
        self.assertEqual(h.c.round, 1)
        self.assertEqual(h.c.frame, 1)
        self.assertEqual(h.c.sim_time_us, 100000)

    def test_concurrent_line_edits_have_identical_order_and_end_state(self):
        h = Harness()
        h.start()
        worlds = {"a": {"line": ["old"]}, "b": {"line": ["old"]}}
        h.plan([command(1, "LINE_UPDATE", stops=["A", "B"])],
               [command(1, "LINE_UPDATE", stops=["C"])], first="b")
        self.assertEqual(worlds["a"], {"line": ["old"]})
        actions = h.prepare()
        executed = {"a": [], "b": []}
        for index in range(2):
            for peer, action in actions:
                self.assertEqual(action["kind"], "apply")
                worlds[peer]["line"] = action["command"]["stops"]
                executed[peer].append(action["command_key"])
            self.assertEqual(worlds["a"], worlds["b"])
            actions = h.applied(index, result={"line": "shared"}, state=digest(worlds["a"]))
        self.assertEqual(executed, {"a": ["a:1", "b:1"], "b": ["a:1", "b:1"]})
        self.assertEqual(worlds["a"]["line"], ["C"])
        self.assertEqual(actions[0][1]["kind"], "step")

    def test_paused_round_still_builds_then_grants_zero_time_step(self):
        h = Harness(paused=True, sim_time_us=123000)
        h.start()
        h.plan([command(1, "DEPOT")])
        self.assertEqual(h.prepare()[0][1]["kind"], "apply")
        step = h.applied(0)[0][1]
        self.assertEqual((step["dt_us"], step["sim_time_us"]), (0, 123000))
        h.stepped(step)
        self.assertEqual(h.c.sim_time_us, 123000)

    def test_shared_pause_changes_only_after_joint_success_in_order(self):
        h = Harness()
        h.start()
        h.plan([command(1, "SET_PAUSED", value=True)],
               [command(1, "SET_PAUSED", value=False)])
        h.prepare()
        self.assertFalse(h.c.paused)
        h.applied(0)
        self.assertTrue(h.c.paused)
        step = h.applied(1)[0][1]
        self.assertFalse(h.c.paused)
        self.assertEqual(step["dt_us"], 100000)

    def test_pause_integer_and_extra_fields_are_rejected(self):
        for item in [command(1, "SET_PAUSED", value=1),
                     command(1, "SET_PAUSED", value=True, extra="ignored")]:
            h = Harness()
            h.start()
            h.send("a", "inputs", round=0, commands=[item])
            self.assertTrue(h.c.halted)

    def test_input_after_seal_conflicts_even_before_other_peer_arrives(self):
        h = Harness()
        h.start()
        h.send("a", "inputs", round=0, commands=[])
        h.send("a", "inputs", round=0, commands=[command(1)])
        self.assertTrue(h.c.halted)

    def test_sequence_bounds_and_count(self):
        for batch in [[command(0)], [command(True)], [command(2)],
                      [command(1), command(1)], [command(1), command(3)],
                      [command(i + 1) for i in range(MAX_COMMANDS_PER_PEER + 1)]]:
            with self.subTest(batch=batch):
                h = Harness()
                h.start()
                h.send("a", "inputs", round=0, commands=batch)
                self.assertTrue(h.c.halted)

    def test_sequences_continue_across_rounds(self):
        h = Harness()
        h.start()
        h.plan([command(1)])
        h.prepare()
        step = h.applied(0)[0][1]
        h.stepped(step)
        h.plan([command(2)], [command(1)])
        self.assertFalse(h.c.halted)
        self.assertEqual(h.prepare()[0][1]["command_key"], "a:2")


class FailureAndReplayTests(unittest.TestCase):
    def ready_apply(self):
        h = Harness()
        h.start()
        h.plan([command(1), command(2)])
        h.prepare()
        return h

    def receipt(self, h, **changes):
        return h.msg("applied", **{ "round": 0, "plan_hash": h.c.plan_hash,
            "index": 0, "success": True, "result": {"id": "a:1"},
            "state_digest": digest({"new": 1}), **changes})

    def test_result_and_digest_must_both_match(self):
        for changes in [{"result": {"id": "b:1"}}, {"state_digest": "0" * 64},
                        {"result": {"id": True}}]:
            h = self.ready_apply()
            h.c.receive("a", self.receipt(h))
            actions = h.c.receive("b", self.receipt(h, **changes))
            self.assertTrue(h.c.halted)
            self.assertEqual(actions[0][1]["kind"], "halt")
            self.assertEqual(h.c.frame, 0)

    def test_nested_result_bool_does_not_equal_integer(self):
        h = self.ready_apply()
        h.c.receive("a", self.receipt(h, result={"value": True}))
        h.c.receive("b", self.receipt(h, result={"value": 1}))
        self.assertTrue(h.c.halted)

    def test_unsuccessful_command_halts_without_second_receipt(self):
        h = self.ready_apply()
        h.c.receive("a", self.receipt(h, success=False))
        self.assertTrue(h.c.halted)
        self.assertEqual(h.c.round, 0)

    def test_wrong_index_round_plan_or_success_type_halts(self):
        for changes in [{"index": 1}, {"index": True}, {"round": 1},
                        {"plan_hash": "0" * 64}, {"success": 1}]:
            h = self.ready_apply()
            h.c.receive("a", self.receipt(h, **changes))
            self.assertTrue(h.c.halted)

    def test_apply_before_plan_acceptance_halts(self):
        h = Harness()
        h.start()
        h.plan([command(1)])
        h.c.receive("a", self.receipt(h))
        self.assertTrue(h.c.halted)

    def test_identical_duplicates_do_not_release_next_command(self):
        h = self.ready_apply()
        receipt = self.receipt(h)
        self.assertEqual(h.c.receive("a", receipt), [])
        for _ in range(20):
            self.assertEqual(h.c.receive("a", receipt), [])
        self.assertEqual(h.c.phase, "applied")
        actions = h.c.receive("b", receipt)
        self.assertEqual(actions[0][1]["index"], 1)
        self.assertEqual(h.c.receive("a", receipt), [])
        self.assertFalse(h.c.halted)

    def test_conflicting_old_duplicate_halts(self):
        h = self.ready_apply()
        receipt = self.receipt(h)
        h.c.receive("a", receipt)
        h.c.receive("b", receipt)
        h.c.receive("a", {**receipt, "result": {"changed": 1}})
        self.assertTrue(h.c.halted)

    def test_old_exact_acks_never_count_as_current_round(self):
        h = Harness()
        h.start()
        h.plan()
        old = h.msg("prepared", round=0, plan_hash=h.c.plan_hash)
        step = h.prepare()[0][1]
        h.stepped(step)
        h.plan()
        self.assertEqual(h.c.receive("a", old), [])
        self.assertEqual(h.c.receive("b", old), [])
        self.assertEqual(h.c.phase, "prepared")

    def test_bounded_history_old_ack_halts_after_eviction(self):
        h = Harness()
        h.start()
        old = None
        for _ in range(6):
            h.plan()
            if old is None:
                old = h.msg("prepared", round=0, plan_hash=h.c.plan_hash)
            step = h.prepare()[0][1]
            h.stepped(step)
        self.assertLess(len(h.c._seen), 40)
        h.c.receive("a", old)
        self.assertTrue(h.c.halted)

    def test_step_requires_expected_frame_time_and_matching_world(self):
        for changes in [{"frame": 2}, {"sim_time_us": 100001},
                        {"state_digest": "0" * 64}, {"frame": True}]:
            h = Harness()
            h.start()
            h.plan()
            step = h.prepare()[0][1]
            msg = h.msg("stepped", round=0, plan_hash=h.c.plan_hash,
                        frame=step["frame"], sim_time_us=step["sim_time_us"], state_digest=START)
            h.c.receive("a", msg)
            h.c.receive("b", {**msg, **changes})
            self.assertTrue(h.c.halted)
            self.assertEqual(h.c.round, 0)

    def test_timeout_duplicates_do_not_extend_deadline_and_halt_is_permanent(self):
        h = self.ready_apply()
        receipt = self.receipt(h)
        h.c.receive("a", receipt)
        h.now = 3.9
        h.c.receive("a", receipt)
        h.now = 4.0
        self.assertEqual(h.c.tick()[0][1]["kind"], "halt")
        self.assertEqual(h.c.receive("b", receipt), [])
        self.assertEqual(h.c.receive("a", h.msg("hello", **h.initial)), [])
        self.assertTrue(h.c.halted)

    def test_disconnect_halts_and_reconnect_cannot_resume(self):
        h = Harness()
        h.start()
        self.assertEqual(h.c.disconnect("b")[0][1]["kind"], "halt")
        self.assertEqual(h.c.receive("b", h.msg("hello", **h.initial)), [])
        self.assertEqual(h.c.tick(), [])
        self.assertTrue(h.c.halted)

    def test_backwards_clock_and_overflow_halt(self):
        h = Harness()
        h.now = 0.0
        h.c.tick()
        self.assertTrue(h.c.halted)
        for frame, sim_time in [(MAX_INT, 0), (0, MAX_INT)]:
            h = Harness(frame=frame, sim_time_us=sim_time)
            h.start()
            h.plan()
            h.prepare()
            self.assertTrue(h.c.halted)

    def test_caller_mutation_cannot_change_sealed_inputs_or_other_actions(self):
        h = Harness()
        h.start()
        batch = [command(1, "LINE_UPDATE", stops=["A", "B"])]
        h.send("a", "inputs", round=0, commands=batch)
        batch[0]["command"]["stops"].clear()
        plan_actions = h.send("b", "inputs", round=0, commands=[])
        plan_actions[0][1]["commands"].clear()
        self.assertEqual(len(plan_actions[1][1]["commands"]), 1)
        action = h.prepare()[0][1]
        self.assertEqual(action["command"]["stops"], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
