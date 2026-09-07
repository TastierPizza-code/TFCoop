"""Sequential replay with explicit fixtures; this module never launches TF2."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from prototype.strict_sync import local_replay as runner
from prototype.strict_sync.build_profile import build_inputs
from prototype.strict_sync.core import Coordinator, digest
from prototype.tests.test_build_driver import BuildEngineFixture


class ReplayFixture(BuildEngineFixture):
    def __init__(self, *, fail_key=None, drift_key=None, close_error=False, missing_debit=False):
        super().__init__(missing_debit=missing_debit)
        self.frame = 0
        self.calls = []
        self.fail_key, self.drift_key, self.close_error = fail_key, drift_key, close_error

    def apply(self, command, key):
        self.calls.append(("apply", key, copy.deepcopy(command)))
        if key == self.fail_key:
            raise runner.ReplayError("fixture original API fault")
        result = super().apply(command, key)
        if key == self.drift_key:
            self.world["company"]["balance"] -= 1
            result["state_digest"] = self.state_digest
        return result

    def step(self, dt_us):
        self.calls.append(("step", dt_us))
        result = super().step(dt_us)
        self.frame += 1
        return result

    def close(self):
        super().close()
        if self.close_error:
            raise OSError("fixture close failure")


def prepare(root, name, epoch, manifest=None):
    session = root / name
    session.mkdir()
    baseline = root / "baseline.sav"
    if not baseline.exists():
        baseline.write_bytes(b"explicit fixture baseline, not a TF2 save")
        Path(str(baseline) + ".lua").write_bytes(b"fixture metadata")
    if manifest is None:
        manifest = {"protocol": 1, "backend": "tf2_controlled_measurement",
                    "complete_world_verified": False,
                    "config_semantics": {"enabled": True, "native_gate_required": True, "profile": "build_v2"},
                    "save": {"sav_sha256": runner._hash_file(baseline),
                             "sav_lua_sha256": runner._hash_file(Path(str(baseline) + ".lua"))},
                    "prototype_files": {}, "game_sha256": "f" * 64}
    (session / "probe_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (session / "probe_setup.json").write_text(json.dumps({"protocol": 1, "native_epoch": epoch,
        "manifest_digest": digest(manifest), "game_exe": "fixture-unused.exe"}), encoding="utf-8")
    return session, baseline


def records(directory):
    return runner._read_records(directory)[0]


class LocalReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # Durability is exercised by the real file-IPC test, not multiplied by all
        # deliberate malformed-input cases in this fixture unit suite.
        self.fsync = patch.object(runner.os, "fsync")
        self.fsync.start()
        self.addCleanup(self.fsync.stop)
        self.counter = 0

    def run_fixture(self, *, replay=None, engine=None, epoch=None, session=None, **kwargs):
        self.counter += 1
        epoch = epoch if epoch is not None else self.counter
        if session is None:
            session, baseline = prepare(self.root, f"session-{self.counter}", epoch)
        else:
            baseline = self.root / "baseline.sav"
        engine = engine if engine is not None else ReplayFixture()
        factory = Mock(return_value=engine)
        output = self.root / f"result-{self.counter}"
        result = runner.run_local_replay(session, epoch, output, baseline=baseline,
            replay=replay, engine_factory=factory, **kwargs)
        return result, output, engine, factory

    def good_record(self):
        result, output, engine, _ = self.run_fixture()
        self.assertTrue(result["passed"], result["reason"])
        return output, engine

    def rewrite(self, values, name="rewritten"):
        output = self.root / name
        output.mkdir()
        journal = runner._Journal(output / "journal.jsonl")
        for value in values:
            journal.append(value)
        journal.close()
        return output

    def test_full_record_and_replay_compare_all_actions_and_claim_only_observed_scope(self):
        source, first = self.good_record()
        result, output, second, factory = self.run_fixture(replay=source)
        self.assertTrue(result["passed"], result["reason"])
        self.assertTrue(result["replay_match"])
        self.assertFalse(result["live_network_tested"])
        self.assertFalse(result["complete_world_verified"])
        self.assertEqual(result["scope"], "sequential_real_engine_replay")
        self.assertEqual((result["completed_commands"], result["completed_rounds"], result["completed_actions"]),
                         (12, 240, 252))
        self.assertEqual(result["proof"]["elapsed_sim_time_us"], 42_200_000)
        self.assertEqual(first.calls, second.calls)
        self.assertEqual(sum(c == ("step", 0) for c in first.calls), 29)
        self.assertEqual(len(records(output)), 507)
        self.assertEqual(records(source)[1:], records(output)[1:])
        self.assertEqual(result["source_journal_sha256"], runner._hash_file(source / "journal.jsonl"))
        self.assertTrue(first.closed and second.closed)
        factory.assert_called_once()

    def test_command_union_has_exact_coordinator_origin_sequence_order(self):
        coordinator = Coordinator("fixture-epoch", "a" * 64, step_us=200000)
        own_sequences = {"a": 0, "b": 0}
        for number in range(240):
            coordinator.round = number
            coordinator._request_inputs()
            # Intentionally deliver b first; canonical plan must still sort a,b.
            for origin in ("b", "a"):
                values = []
                for command in build_inputs(origin, number):
                    values.append({"seq": coordinator._last_seq[origin] + 1, "command": command})
                coordinator._on_inputs(origin, {"commands": values})
            actual = list(runner._commands(number, own_sequences))
            self.assertEqual([{k: v for k, v in c.items() if k != "command_key"} for c in actual],
                             coordinator._commands)
        self.assertEqual(own_sequences, {"a": 7, "b": 5})

    def test_replay_rejects_changed_baseline_before_adapter_creation(self):
        source, _ = self.good_record()
        (self.root / "baseline.sav").write_bytes(b"different fixture world")
        # Preserve recorded manifest, as a real staged replay must.
        session, _ = prepare(self.root, "staged-replay", 2, records(source)[0]["manifest"])
        result, _, _, factory = self.run_fixture(replay=source, epoch=2, session=session)
        self.assertFalse(result["passed"])
        self.assertIn("baseline files differ", result["reason"])
        factory.assert_not_called()

    def test_replay_rejects_manifest_changes_and_reused_epoch_before_engine(self):
        source, _ = self.good_record()
        for name, epoch, change in (("changed-code", 2, True), ("reused-epoch", 1, False)):
            with self.subTest(name=name):
                manifest = copy.deepcopy(records(source)[0]["manifest"])
                if change:
                    manifest["prototype_files"]["mod/build_engine.lua"] = "a" * 64
                session, _ = prepare(self.root, name, epoch, manifest)
                result, _, _, factory = self.run_fixture(replay=source, epoch=epoch, session=session)
                self.assertFalse(result["passed"])
                factory.assert_not_called()

    def test_initial_actual_state_mismatch_is_checked_before_first_command(self):
        source, _ = self.good_record()
        engine = ReplayFixture()
        engine.world["company"]["balance"] += 1
        result, output, _, _ = self.run_fixture(replay=source, engine=engine)
        self.assertIn("initial actual snapshot differs", result["reason"])
        self.assertEqual(engine.calls, [])
        self.assertTrue(engine.closed)
        self.assertIsNone(result["last_verified_frame"])
        self.assertIsNone(records(output)[-1]["last_observation"])
        self.assertEqual([v["event"] for v in records(output)], ["header", "start", "failed"])

    def test_first_divergence_keeps_both_observation_and_request_and_stops(self):
        source, _ = self.good_record()
        result, output, engine, _ = self.run_fixture(replay=source, engine=ReplayFixture(drift_key="b:1"))
        self.assertFalse(result["passed"])
        self.assertIn("round 2 apply", result["reason"])
        self.assertEqual(result["completed_rounds"], 2)
        self.assertEqual(result["last_request"]["command_key"], "b:1")
        self.assertEqual(engine.calls[-1], ("apply", "b:1", {"op": "PROBE_DEPOT"}))
        rows = records(output)
        self.assertEqual(rows[-2]["event"], "applied")
        self.assertEqual(rows[-1]["event"], "failed")
        self.assertEqual(rows[-1]["last_observation_scope"], "historical_verified_boundary")
        self.assertNotEqual(rows[-1]["last_observation"]["state_digest"], rows[-2]["state_digest"])

    def test_original_api_error_survives_close_failure_and_command_never_retries(self):
        engine = ReplayFixture(fail_key="a:4", close_error=True)
        result, output, _, _ = self.run_fixture(engine=engine)
        self.assertIn("original API fault", result["reason"])
        self.assertIn("close failure", result["cleanup_failure"])
        self.assertEqual(sum(c[:2] == ("apply", "a:4") for c in engine.calls), 1)
        self.assertEqual(result["completed_rounds"], 5)
        self.assertEqual(records(output)[-2]["command_key"], "a:4")
        self.assertFalse(result["record_complete"])

    def test_failed_record_cannot_be_used_as_successful_replay_source(self):
        _, source, _, _ = self.run_fixture(engine=ReplayFixture(fail_key="a:4"))
        result, _, _, factory = self.run_fixture(replay=source)
        self.assertFalse(result["passed"])
        factory.assert_not_called()

    def test_rehashed_wrong_commands_sequence_boolean_frame_and_receipt_still_refuse(self):
        source, _ = self.good_record()
        mutations = [lambda r: r[2]["command"].update(value=False),
                     lambda r: r[2].update(seq=2, command_key="a:2"),
                     lambda r: r[2].update(frame=False),
                     lambda r: r[3]["receipt"].update(success=1),
                     lambda r: r[0].update(format=True),
                     lambda r: r[-1]["proof"].update(passed=False)]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                values = records(source)
                mutate(values)
                rewritten = self.rewrite(values, f"mutation-{index}")
                result, _, _, factory = self.run_fixture(replay=rewritten)
                self.assertFalse(result["passed"])
                factory.assert_not_called()

    def test_tampered_hash_truncation_trailing_records_and_oversize_are_bounded(self):
        source, _ = self.good_record()
        original = (source / "journal.jsonl").read_bytes()
        for index, data in enumerate((original[:-1], original.replace(b'"previous":"0', b'"previous":"1', 1),
                                      original + original[:original.index(b"\n") + 1], b"x" * (runner.LINE_LIMIT + 2))):
            with self.subTest(index=index):
                candidate = self.root / f"bad-{index}.jsonl"
                candidate.write_bytes(data)
                result, _, _, factory = self.run_fixture(replay=candidate)
                self.assertFalse(result["passed"])
                factory.assert_not_called()

    def test_json_duplicate_keys_float_and_nonfinite_cannot_enter_replay(self):
        for raw in (b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{"a":1e309}\n', b'{"a":1.0}\n'):
            with self.subTest(raw=raw), self.assertRaises(runner.ReplayError):
                runner._decode_line(raw)

    def test_engine_bootstrap_failure_is_reported_without_an_action(self):
        session, baseline = prepare(self.root, "session", 1)
        factory = Mock(side_effect=runner.ReplayError("fixture native startup failure"))
        result = runner.run_local_replay(session, 1, self.root / "out", baseline=baseline, engine_factory=factory)
        self.assertFalse(result["passed"])
        self.assertEqual(result["completed_actions"], 0)
        self.assertIn("native startup failure", result["reason"])

    def test_stop_between_actions_halts_before_next_send(self):
        engine = ReplayFixture()
        result, _, _, _ = self.run_fixture(engine=engine, stop_requested=lambda: len(engine.calls) >= 4)
        self.assertFalse(result["passed"])
        self.assertIn("stopped by caller", result["reason"])
        self.assertEqual(len(engine.calls), 4)
        self.assertTrue(engine.closed)

    def test_unproved_build_and_unfresh_frame_never_pass(self):
        for engine in (ReplayFixture(missing_debit=True), ReplayFixture()):
            if not engine.missing_debit:
                engine.frame = 1
            result, _, _, _ = self.run_fixture(engine=engine)
            self.assertFalse(result["passed"])
            self.assertTrue(engine.closed)

    def test_existing_output_is_preserved_and_no_adapter_is_opened(self):
        session, baseline = prepare(self.root, "session", 1)
        output = self.root / "out"
        output.mkdir()
        (output / "keep").write_text("existing evidence")
        factory = Mock()
        with self.assertRaises(FileExistsError):
            runner.run_local_replay(session, 1, output, baseline=baseline, engine_factory=factory)
        self.assertEqual((output / "keep").read_text(), "existing evidence")
        factory.assert_not_called()


class LocalReplayLuaIntegrationTests(unittest.TestCase):
    def test_two_sequential_lua_engines_record_and_replay_all_240_file_boundaries(self):
        from prototype.tests import test_build_mailbox_lua as fixtures
        from prototype.tests.test_engine_mailbox_lua import RUNTIMES
        if "lua53" not in RUNTIMES:
            self.skipTest("literal Lua 5.3 fixture runtime unavailable")

        class EpochWorker(fixtures.BuildLuaWorker):
            def __init__(self, directory, epoch, **kwargs):
                self.local_epoch = epoch
                super().__init__(directory, **kwargs)

            def native_status(self, **changes):
                super().native_status(epoch=int(self.local_epoch), **changes)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = None
            outcomes = []
            for index in range(2):
                epoch = str(700 + index)
                session, baseline = prepare(root, f"session-{index}", int(epoch))
                output = root / f"result-{index}"
                # Each new VM/worker is closed before the next is constructed.
                # The APIs/native clock remain explicit fixtures; file IPC and
                # the Lua adapter and Python EngineAdapter are production code.
                with patch.object(fixtures, "EPOCH", epoch):
                    worker = EpochWorker(session, epoch, offset=index * 10000)
                    try:
                        result = runner.run_local_replay(session, epoch, output,
                            baseline=baseline, replay=source, timeout_s=20)
                        self.assertTrue(result["passed"], result["reason"])
                        self.assertEqual(result["completed_rounds"], 240)
                        self.assertEqual(result["completed_commands"], 12)
                        self.assertEqual(result["last_verified_sim_time_us"], 55_600_000)
                        self.assertEqual(worker.observed_sends, 12)
                        outcomes.append(result)
                    finally:
                        worker.close()
                self.assertIsNone(worker.error)
                self.assertFalse(worker.thread.is_alive())
                source = output
            self.assertTrue(outcomes[0]["record_complete"])
            self.assertTrue(outcomes[1]["replay_match"])
            self.assertEqual(outcomes[0]["proof"], outcomes[1]["proof"])


if __name__ == "__main__":
    unittest.main()
