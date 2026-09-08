"""Explicit observations test only the short proof contract; no game is run."""
import argparse
import copy
import unittest

from prototype.strict_sync import game_runner as driver
from prototype.strict_sync.build_profile import BUILD_ROUNDS, BuildProof, build_inputs
from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.short_build_profile import (
    SHORT_BUILD_CONTRACT, SHORT_BUILD_ROUNDS, SHORT_ENGINE_SEQUENCES,
    ShortBuildProof, short_build_inputs)
from prototype.tests.test_build_driver import BuildEngineFixture


def make_short_proof(*, missing_debit=False):
    engine = BuildEngineFixture(missing_debit=missing_debit)
    proof = ShortBuildProof()
    proof.observe(engine.snapshot(), frame=0)
    sequences = {"a": 0, "b": 0}
    for number in range(SHORT_BUILD_ROUNDS):
        for peer in ("a", "b"):
            for command in short_build_inputs(peer, number):
                sequences[peer] += 1
                key = f"{peer}:{sequences[peer]}"
                receipt = engine.apply(command, key)
                proof.observe(engine.snapshot(), frame=number, command=command,
                              command_key=key, receipt=receipt)
        engine.step(0 if engine.paused else 200000)
        proof.observe(engine.snapshot(), frame=number + 1)
    return proof


class ShortBuildProofTests(unittest.TestCase):
    def test_short_recipe_reuses_only_first_ten_commands_without_changing_reference(self):
        self.assertEqual(BUILD_ROUNDS, 240)
        sequence = {"a": 0, "b": 0}
        for number in range(SHORT_BUILD_ROUNDS):
            for peer in sequence:
                self.assertEqual(short_build_inputs(peer, number), build_inputs(peer, number))
                sequence[peer] += len(short_build_inputs(peer, number))
        self.assertEqual(sequence, SHORT_ENGINE_SEQUENCES)
        self.assertEqual(build_inputs("a", 80), [{"op": "SET_PAUSED", "value": True}])
        self.assertEqual(build_inputs("b", 100), [{"op": "SET_PAUSED", "value": False}])
        for number in (True, -1, 10, 240):
            with self.assertRaises(ProtocolError):
                short_build_inputs("a", number)

    def test_ready_scene_requires_callbacks_assignment_departure_and_purchase_not_metres(self):
        proof = make_short_proof()
        result = proof.finish(frame=10, step_us=200000)
        self.assertTrue(result["passed"])
        self.assertEqual(result["contract"], SHORT_BUILD_CONTRACT)
        self.assertEqual(result["elapsed_sim_time_us"], 200000)
        self.assertEqual(result["paused_steps"], 9)
        self.assertEqual(len(result["callback_outcomes"]), 10)
        self.assertEqual(result["engine_sequences"], {"a": 6, "b": 4})
        self.assertFalse(result["full_build_proof"])
        self.assertFalse(result["vehicle_displacement_verified"])
        self.assertFalse(result["pause_endurance_verified"])
        self.assertFalse(result["complete_world_verified"])
        with self.assertRaisesRegex(ProtocolError, "final verified boundary"):
            proof.observed.finish(frame=10, step_us=200000)
        result["callback_outcomes"][0]["receipt"]["success"] = False
        self.assertTrue(proof.finish(frame=10, step_us=200000)["callback_outcomes"][0]["receipt"]["success"])

    def test_ready_frame_alone_never_replaces_actual_scene_checks(self):
        mutations = [
            lambda s: s["probe"]["scene"].pop("road"),
            lambda s: s["probe"]["connectivity"].update(connected=False),
            lambda s: s["objects"].pop(),
            lambda s: s["probe"]["vehicle"].update(line="other"),
            lambda s: s["probe"]["line"].update(vehicles=[]),
            lambda s: s["probe"]["line"].update(stops=["b:2", "a:3"]),
            lambda s: s["probe"]["vehicle"].update(in_depot=True),
            lambda s: s["probe"]["vehicle"].update(no_path=True),
            lambda s: s["probe"]["vehicle"].update(position_mm=None),
            lambda s: s.update(paused=True),
            lambda s: s.update(sim_time_us=s["sim_time_us"] + 200000),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                proof = make_short_proof()
                mutation(proof.observed.last_snapshot)
                with self.assertRaises(ProtocolError):
                    proof.finish(frame=10, step_us=200000)
        with self.assertRaisesRegex(ProtocolError, "actual company debit"):
            make_short_proof(missing_debit=True).finish(frame=10, step_us=200000)

    def test_missing_failed_wrong_identity_or_wrong_world_callback_cannot_be_ready(self):
        command = {"op": "SET_PAUSED", "value": True}
        for case in ("missing", "failed", "key", "digest", "skip"):
            with self.subTest(case=case):
                engine = BuildEngineFixture()
                proof = ShortBuildProof()
                proof.observe(engine.snapshot(), frame=0)
                receipt = engine.apply(command, "a:1")
                if case == "missing": receipt = None
                elif case == "failed": receipt["success"] = False
                elif case == "digest": receipt["state_digest"] = "f" * 64
                with self.assertRaises(ProtocolError):
                    if case == "skip":
                        proof.observe(engine.snapshot(), frame=1)
                    else:
                        proof.observe(engine.snapshot(), frame=0, command=command,
                                      command_key="a:2" if case == "key" else "a:1", receipt=receipt)

    def test_driver_requires_explicit_short_manifest_and_keeps_old_round_contracts(self):
        fields = dict(profile="build_v2", rounds=10, timeout=15, delay_ms=0, paced_live_probe=True)
        setup = {"measurement_profile": "build_v2", "measurement_preparation": SHORT_BUILD_CONTRACT}
        self.assertEqual(driver.selected_profile(argparse.Namespace(**fields), setup), "build_v2")
        for changes in ({"rounds": 240}, {"rounds": 9}, {"delay_ms": 1}, {"timeout": 14.9},
                        {"live_probe": True}, {"stream_probe": True}, {"timing_probe": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                driver.selected_profile(argparse.Namespace(**{**fields, **changes}), setup)
        for prepared in ({"measurement_profile": "build_v2"},
                         {"measurement_profile": "build_v2", "measurement_preparation": "other"}):
            with self.assertRaises(ValueError):
                driver.selected_profile(argparse.Namespace(**fields), prepared)
        for old_mode in ("live_probe", "stream_probe", "timing_probe"):
            old = argparse.Namespace(profile="build_v2", rounds=240, timeout=15, delay_ms=0, **{old_mode: True})
            self.assertEqual(driver.selected_profile(old, {"measurement_profile": "build_v2"}), "build_v2")
            with self.assertRaises(ValueError):
                driver.selected_profile(old, setup)


if __name__ == "__main__":
    unittest.main()
