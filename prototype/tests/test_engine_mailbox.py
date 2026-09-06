"""File IPC fault tests with fake mailbox writers; never load Transport Fever 2."""

import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from prototype.strict_sync.engine_mailbox import (
    EngineAdapter, MailboxBusy, MailboxError, NativeMailbox, NATIVE_REQUIRED,
    parse_native_status, _shared_read,
)


EPOCH = "18446744073709551614"


def atomic_write(path, raw):
    temp = path.parent / f"test-{uuid.uuid4().hex}.tmp"
    temp.write_bytes(raw)
    deadline = time.monotonic() + 1
    while True:
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.002)


def native_state(**changes):
    state = {name: 0 for name in NATIVE_REQUIRED}
    state.update(protocol=1, abi=3, native_step_us=200000, epoch=int(EPOCH), ready=1, initialized=1, armed=1,
                 probe_required=1)
    state.update(changes)
    return state


def native_bytes(**changes):
    return "".join(f"{k}={v}\n" for k, v in native_state(**changes).items()).encode("ascii")


def control(path):
    return dict(line.split("=", 1) for line in _shared_read(path, 4096).decode("ascii").splitlines())


def snapshot():
    return {"sim_time_us": 0, "paused": True, "company": {"balance": 10000, "loan": 0},
            "objects": [], "coverage": {"complete_world": False, "tracked_objects": True,
            "missing": [], "excluded": ["untracked entities", "internal engine state"]}}


class FakeGameMailboxes:
    """Writes protocol fixtures in another thread, not a model/game backend."""
    def __init__(self, directory, *, native_only_advance=False, mutate_plan=False,
                 lua_fault=None, wrong_canonical=False):
        self.directory = Path(directory)
        self.world = snapshot()
        self.native_only_advance = native_only_advance
        self.mutate_plan = mutate_plan
        self.lua_fault = lua_fault
        self.wrong_canonical = wrong_canonical
        self.native_seen = 0
        self.lua_seen = 0
        self.revision = 0
        self.applies = 0
        self.error = None
        self.commands = []
        self.stop_event = threading.Event()
        atomic_write(self.directory / "native_status.txt", native_bytes(outer_calls=1))
        self.write_lua(0, "ready")
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def write_lua(self, request, state, receipt=None):
        self.revision += 1
        canonical = copy.deepcopy(self.world)
        if self.wrong_canonical:
            canonical["company"]["balance"] += 1
        payload = {"protocol": 1, "epoch": EPOCH, "request": request, "revision": self.revision,
                   "status": state, "complete": True, "snapshot": copy.deepcopy(self.world),
                   "canonical_state_json": json.dumps(canonical, sort_keys=True, separators=(",", ":"))}
        if receipt is not None:
            payload["receipt"] = receipt
        atomic_write(self.directory / "lua_status.json", json.dumps(payload).encode("utf-8"))

    def run(self):
        try:
            while not self.stop_event.is_set():
                native_path = self.directory / "native_control.txt"
                if native_path.exists():
                    request = control(native_path)
                    number = int(request["request"])
                    if number != self.native_seen:
                        self.native_seen = number
                        self.commands.append(("native", request))
                        if request["action"] == "halt":
                            atomic_write(self.directory / "native_status.txt", native_bytes(
                                request_received=number, request_acknowledged=number, request_completed=number,
                                halted=1, ready=0))
                        else:
                            dt = int(request["dt_us"])
                            native_time = self.world["sim_time_us"] + dt
                            if not self.native_only_advance:
                                self.world["sim_time_us"] = native_time
                            atomic_write(self.directory / "native_status.txt", native_bytes(
                                request_received=number, request_acknowledged=number, request_completed=number,
                                completed_frame=int(request["frame"]), completed_dt_us=dt,
                                time_after_ms=native_time // 1000, outer_calls=10 + number))
                lua_path = self.directory / "lua_control.json"
                if lua_path.exists():
                    try:
                        request = json.loads(_shared_read(lua_path, 262144))
                    except (PermissionError, FileNotFoundError):
                        time.sleep(.001)
                        continue
                    number = request["request"]
                    if number != self.lua_seen:
                        self.lua_seen = number
                        self.commands.append(("lua", request))
                        action = request["action"]
                        if self.lua_fault is not None and self.lua_fault(self, request):
                            continue
                        if action == "halt":
                            self.write_lua(number, "halted")
                        elif action == "snapshot":
                            self.write_lua(number, "ready")
                        elif action == "plan":
                            if self.mutate_plan:
                                self.world["company"]["balance"] -= 1
                            self.write_lua(number, "planned")
                        elif action == "apply":
                            self.applies += 1
                            command, key = request["command"], request["command_key"]
                            success = command["op"] in ("DEPOT", "SET_PAUSED")
                            if command["op"] == "DEPOT":
                                self.world["company"]["balance"] -= 2000
                                self.world["objects"].append({"logical_id": key, "kind": "depot",
                                    "state": {"position": ["1.25", "2.5"]}})
                                self.world["objects"].sort(key=lambda obj: obj["logical_id"])
                            if command["op"] == "SET_PAUSED":
                                self.world["paused"] = command["value"]
                            receipt = {"command_key": key, "boundary": request["boundary"],
                                       "success": success, "result": {"logical_id": key},
                                       "bindings": {key: 87654}, "result_entity": 87654}
                            self.write_lua(number, "applied", receipt)
                time.sleep(0.001)
        except Exception as exc:
            self.error = exc

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=1)
        if self.error:
            raise self.error


class NativeMailboxTests(unittest.TestCase):
    def test_partial_status_never_acknowledges(self):
        complete = native_bytes()
        self.assertIsNone(parse_native_status(complete[:-1]))
        self.assertIsNone(parse_native_status(b"protocol=1\nepoch=12\n"))
        self.assertIsNone(parse_native_status(b"\xff\n"))
        self.assertEqual(parse_native_status(complete)["epoch"], int(EPOCH))

    def test_status_rejects_duplicate_integer_overflow_and_wrong_abi(self):
        for raw in [native_bytes() + b"epoch=1\n", native_bytes(abi=1),
                    native_bytes(ready=2), native_bytes(pending_dt_us=1),
                    native_bytes(epoch=1 << 64), native_bytes().replace(b"ready=1", b"ready=true"),
                    b"x" * 4097]:
            with self.subTest(raw=raw[:40]), self.assertRaises(MailboxError):
                parse_native_status(raw)

    def test_previous_abi_and_smaller_engine_quantum_are_rejected(self):
        legacy = native_bytes(abi=2).replace(b"native_step_us=200000\n", b"")
        for raw in (legacy, native_bytes(native_step_us=100000),
                    native_bytes(pending_dt_us=100000), native_bytes(completed_dt_us=100000)):
            with self.subTest(raw=raw[:60]), self.assertRaises(MailboxError):
                parse_native_status(raw)

    def test_smaller_native_permit_halts_without_emitting_an_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            atomic_write(path / "native_status.txt", native_bytes())
            mailbox = NativeMailbox(path, EPOCH)
            try:
                with self.assertRaisesRegex(MailboxError, "200000"):
                    mailbox.permit(1, 100000)
                self.assertTrue(mailbox.halted)
                command = control(path / "native_control.txt")
                self.assertEqual(command["action"], "halt")
                self.assertEqual(command["frame"], "0")
            finally:
                mailbox.close()

    def test_exclusive_session_owner_and_stale_controls_refuse_rejoin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            atomic_write(path / "native_status.txt", native_bytes())
            mailbox = NativeMailbox(path, EPOCH)
            try:
                with self.assertRaises(MailboxBusy):
                    NativeMailbox(path, EPOCH)
            finally:
                mailbox.close()
            with self.assertRaises(MailboxError):
                NativeMailbox(path, EPOCH)
            self.assertEqual(control(path / "native_control.txt")["action"], "halt")

    def test_received_and_partial_status_do_not_complete_a_permit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            atomic_write(path / "native_status.txt", native_bytes())
            mailbox = NativeMailbox(path, EPOCH, timeout_s=1, poll_s=.002)
            answer, errors = [], []
            def permit():
                try:
                    answer.append(mailbox.permit(1, 200000))
                except Exception as exc:
                    errors.append(exc)
            thread = threading.Thread(target=permit)
            thread.start()
            while not (path / "native_control.txt").exists():
                time.sleep(.001)
            atomic_write(path / "native_status.txt", native_bytes(request_received=1, request_acknowledged=1,
                         pending_state=2, pending_frame=1, pending_dt_us=200000))
            time.sleep(.02)
            self.assertTrue(thread.is_alive())
            with self.assertRaises(MailboxBusy):
                mailbox.permit(2, 200000)
            partial = native_bytes(request_received=1, request_acknowledged=1, request_completed=1,
                                   completed_frame=1, completed_dt_us=200000)
            (path / "native_status.txt").write_bytes(partial[:len(partial)//2])
            time.sleep(.02)
            self.assertTrue(thread.is_alive())
            atomic_write(path / "native_status.txt", partial)
            thread.join(1)
            self.assertFalse(errors)
            self.assertEqual(answer[0]["completed_frame"], 1)
            self.assertEqual(mailbox.permit(1, 200000), answer[0])
            self.assertEqual(control(path / "native_control.txt")["request"], "1")
            mailbox.close()

    def test_timeout_is_terminal_and_publishes_best_effort_halt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            atomic_write(path / "native_status.txt", native_bytes())
            mailbox = NativeMailbox(path, EPOCH, timeout_s=.04, poll_s=.002)
            with self.assertRaisesRegex(MailboxError, "timeout"):
                mailbox.permit(1, 200000)
            self.assertTrue(mailbox.halted)
            self.assertEqual(control(path / "native_control.txt")["action"], "halt")
            self.assertEqual(control(path / "native_control.txt")["request"], "2")
            self.assertEqual(control(path / "native_control.txt")["frame"], "0")
            with self.assertRaises(MailboxError):
                mailbox.permit(1, 200000)
            mailbox.close()

    def test_future_request_epoch_and_frame_mismatches_halt(self):
        for changes in [{"request_received": 2}, {"epoch": 1}, {"completed_frame": 2},
                        {"runtime_fault": 1}, {"completed_dt_us": 0}]:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                atomic_write(path / "native_status.txt", native_bytes())
                mailbox = NativeMailbox(path, EPOCH, timeout_s=1, poll_s=.001)
                errors = []
                def writer():
                    try:
                        while not (path / "native_control.txt").exists():
                            time.sleep(.001)
                        fields = dict(request_received=1, request_acknowledged=1, request_completed=1,
                                      completed_frame=1, completed_dt_us=200000)
                        atomic_write(path / "native_status.txt", native_bytes(**{**fields, **changes}))
                    except Exception as exc:
                        errors.append(exc)
                thread = threading.Thread(target=writer)
                thread.start()
                with self.assertRaises(MailboxError) as caught:
                    mailbox.permit(1, 200000)
                thread.join(1)
                self.assertFalse(errors)
                self.assertNotIn("timeout", str(caught.exception))
                self.assertTrue(mailbox.halted)
                mailbox.close()

    def test_foreign_pending_control_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            atomic_write(path / "native_status.txt", native_bytes())
            mailbox = NativeMailbox(path, EPOCH)
            foreign = b"another writer's pending request\n"
            (path / "native_control.txt").write_bytes(foreign)
            with self.assertRaisesRegex(MailboxError, "another writer"):
                mailbox.permit(1, 0)
            self.assertEqual((path / "native_control.txt").read_bytes(), foreign)
            self.assertTrue(mailbox.halted)
            mailbox.close()


class EngineMailboxTests(unittest.TestCase):
    def create(self, directory, *, timeout_s=.5, **fixture_options):
        fixture = FakeGameMailboxes(directory, **fixture_options)
        self.addCleanup(fixture.close)
        engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=timeout_s, poll_s=.001)
        self.addCleanup(engine.close)
        return engine, fixture

    def test_explicit_probe_opt_in_required_without_touching_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MailboxError, "probe_only"):
                EngineAdapter(directory, EPOCH)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_lua_failure_preserves_first_actual_proposal_detail(self):
        def fault(fixture, request):
            if request["action"] != "plan":
                return False
            fixture.revision += 1
            raw = {"protocol": 1, "epoch": EPOCH, "request": request["request"],
                   "revision": fixture.revision, "status": "halted", "complete": True,
                   "error": "PROBE_DEPOT: proposal collision\nfirst actual API detail\x00"}
            atomic_write(fixture.directory / "lua_status.json", json.dumps(raw).encode())
            return True
        with tempfile.TemporaryDirectory() as directory:
            engine, fixture = self.create(directory, lua_fault=fault)
            try:
                with self.assertRaisesRegex(MailboxError, "PROBE_DEPOT: proposal collision first actual API detail") as caught:
                    engine.apply({"op": "DEPOT"}, "a:1")
                self.assertNotIn("\x00", str(caught.exception))
                self.assertEqual(fixture.applies, 0)
            finally:
                # Stop the mailbox writer before its temporary directory is
                # removed, including while the final HALT is being consumed.
                engine.close()
                fixture.close()

    def test_missing_snapshot_coverage_reports_the_actual_getter_path(self):
        adapter = EngineAdapter.__new__(EngineAdapter)
        world = snapshot()
        world["coverage"]["missing"] = ["b:1:VEHICLE_DEPOT.state unavailable"]
        with self.assertRaisesRegex(MailboxError, "b:1:VEHICLE_DEPOT.state unavailable"):
            adapter._accept_snapshot({"snapshot": world})

    def test_real_snapshot_values_and_semantic_receipt_exclude_local_entity_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            engine, fixture = self.create(directory)
            try:
                self.assertEqual(engine.snapshot(), fixture.world)
                self.assertFalse(engine.coverage["complete_world"])
                self.assertNotIn("state_digest", engine.capabilities)
                before = engine.state_digest
                receipt = engine.apply({"op": "DEPOT"}, "a:1")
                self.assertTrue(receipt["success"])
                self.assertEqual(receipt["result"], {"logical_id": "a:1"})
                self.assertNotIn("87654", json.dumps(receipt))
                self.assertNotEqual(engine.state_digest, before)
                self.assertEqual(engine.snapshot()["company"]["balance"], 8000)
                self.assertEqual(engine.apply({"op": "DEPOT"}, "a:1"), receipt)
                self.assertEqual(fixture.applies, 1)
            finally:
                engine.close()
                fixture.close()

    def test_paused_and_running_steps_require_both_native_and_fresh_lua_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            engine, fixture = self.create(directory)
            try:
                initial = engine.state_digest
                self.assertEqual(engine.step(0)["sim_time_us"], 0)
                self.assertEqual(engine.state_digest, initial)
                engine.apply({"op": "SET_PAUSED", "value": False}, "a:1")
                self.assertFalse(engine.paused)
                receipt = engine.step(200000)
                self.assertEqual(receipt["sim_time_us"], 200000)
                self.assertEqual(engine.frame, 2)
                self.assertEqual(engine.snapshot()["sim_time_us"], fixture.world["sim_time_us"])
            finally:
                engine.close()
                fixture.close()

    def test_native_completion_alone_never_fabricates_lua_step_success(self):
        with tempfile.TemporaryDirectory() as directory:
            engine, fixture = self.create(directory, native_only_advance=True)
            try:
                engine.apply({"op": "SET_PAUSED", "value": False}, "a:1")
                with self.assertRaisesRegex(MailboxError, "native/Lua world time"):
                    engine.step(200000)
                self.assertEqual(engine.time_us, 0)
                self.assertTrue(engine.halted)
            finally:
                engine.close()
                fixture.close()

    def test_preparation_must_not_mutate_actual_world(self):
        with tempfile.TemporaryDirectory() as directory:
            engine, fixture = self.create(directory, mutate_plan=True)
            try:
                with self.assertRaisesRegex(MailboxError, "planning.*changed"):
                    engine.apply({"op": "DEPOT"}, "a:1")
                self.assertEqual(fixture.applies, 0)
                self.assertTrue(engine.halted)
            finally:
                engine.close()
                fixture.close()

    def test_conflicting_or_skipped_logical_sequence_cannot_execute(self):
        for key, command in [("a:3", {"op": "DEPOT"}), ("a:1", {"op": "SET_PAUSED", "value": False})]:
            with tempfile.TemporaryDirectory() as directory:
                engine, fixture = self.create(directory)
                try:
                    engine.apply({"op": "DEPOT"}, "a:1")
                    with self.assertRaises(MailboxError):
                        engine.apply(command, key)
                    self.assertEqual(fixture.applies, 1)
                finally:
                    engine.close()
                    fixture.close()

    def test_unsupported_command_returns_failure_and_halts_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            engine, fixture = self.create(directory)
            try:
                before = engine.snapshot()
                receipt = engine.apply({"op": "UNSUPPORTED"}, "a:1")
                self.assertFalse(receipt["success"])
                self.assertTrue(engine.halted)
                self.assertEqual(engine.snapshot(), before)
            finally:
                engine.close()
                fixture.close()

    def test_wrong_canonical_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = FakeGameMailboxes(directory, wrong_canonical=True)
            try:
                with self.assertRaisesRegex(MailboxError, "canonical state differs"):
                    EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=.2, poll_s=.001)
            finally:
                fixture.close()

    def test_partial_lua_status_is_not_a_current_ack(self):
        pending, observed_partial, allow = threading.Event(), threading.Event(), threading.Event()
        def fault(fixture, request):
            if request["action"] != "plan":
                return False
            (fixture.directory / "lua_status.json").write_bytes(b'{"protocol":1,"epoch":')
            pending.set()
            if not allow.wait(10):
                raise AssertionError("test did not release the partial Lua status")
            fixture.write_lua(request["request"], "planned")
            return True
        with tempfile.TemporaryDirectory() as directory:
            # This tests acknowledgement semantics, not subsecond disk/thread
            # scheduling during concurrent package builds. Keep the partial
            # write held until the reader has actually rejected it.
            engine, fixture = self.create(directory, lua_fault=fault, timeout_s=5)
            original_read = engine._read_lua
            def observe_read():
                result = original_read()
                if pending.is_set() and not allow.is_set() and result is None:
                    observed_partial.set()
                return result
            engine._read_lua = observe_read
            answers = []
            def apply():
                try:
                    answers.append(engine.apply({"op": "DEPOT"}, "a:1"))
                except Exception as exc:
                    answers.append(exc)
            thread = threading.Thread(target=apply)
            thread.start()
            try:
                self.assertTrue(pending.wait(5), "fixture never published the partial plan status")
                self.assertTrue(observed_partial.wait(5), "adapter never rejected the partial status")
                self.assertTrue(thread.is_alive())
                self.assertEqual(fixture.applies, 0)
                allow.set()
                thread.join(5)
                self.assertEqual(len(answers), 1)
                self.assertIsInstance(answers[0], dict)
                self.assertTrue(answers[0]["success"])
            finally:
                allow.set()
                thread.join(5)
                engine.close()
                fixture.close()

    def test_future_lua_ack_never_runs_apply(self):
        def fault(fixture, request):
            if request["action"] == "plan":
                fixture.write_lua(request["request"] + 1, "planned")
                return True
            return False
        with tempfile.TemporaryDirectory() as directory:
            engine, fixture = self.create(directory, lua_fault=fault)
            try:
                with self.assertRaisesRegex(MailboxError, "future request"):
                    engine.apply({"op": "DEPOT"}, "a:1")
                self.assertEqual(fixture.applies, 0)
            finally:
                engine.close()
                fixture.close()


if __name__ == "__main__":
    unittest.main()
