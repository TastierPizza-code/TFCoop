"""Real file queue tests; no game, native permit or desktop interaction."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from prototype.strict_sync import live_input as live
from prototype.strict_sync.core import ProtocolError


EPOCH = "live-input-test-epoch"


def pause(value=True):
    return {"op": "SET_PAUSED", "value": value}


class LiveInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "live-input.json"
        live.create(self.path, EPOCH, "a")

    def document(self):
        return json.loads(self.path.read_bytes())

    def write_document(self, document):
        self.path.write_text(json.dumps(document), encoding="utf-8")

    def test_fresh_creation_does_not_overwrite_history_or_another_run(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        writer.submit(pause())
        original = self.path.read_bytes()
        for epoch, peer in [(EPOCH, "a"), ("different-epoch", "b")]:
            with self.assertRaises(FileExistsError):
                live.create(self.path, epoch, peer)
            self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_name(self.path.name + ".writer-lock").exists())

    def test_batches_keep_every_request_in_order_without_reexecution(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        for index in range(19):
            self.assertEqual(writer.submit(pause(index % 2 == 0)), index + 1)
        reader = live.InputReader(self.path, EPOCH, "a")
        batches = [reader.take(), reader.take(), reader.take(), reader.take()]
        self.assertEqual([len(batch) for batch in batches], [8, 8, 3, 0])
        self.assertEqual([request["seq"] for batch in batches for request in batch], list(range(1, 20)))
        self.assertEqual(len(self.document()["requests"]), 19)
        self.assertEqual(writer.submit(pause(False)), 20)
        self.assertEqual(reader.take(), [{"seq": 20, "command": pause(False)}])
        self.assertEqual(reader.take(), [])

    def test_bounded_history_applies_backpressure_without_consuming_sequence(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        for index in range(live.MAX_REQUESTS):
            self.assertEqual(writer.submit(pause()), index + 1)
        original = self.path.read_bytes()
        with self.assertRaises(live.InputFull):
            writer.submit(pause(False))
        self.assertEqual(self.path.read_bytes(), original)
        reader = live.InputReader(self.path, EPOCH, "a")
        collected = []
        for _ in range(live.MAX_REQUESTS // live.MAX_BATCH + 1):
            collected.extend(reader.take())
        self.assertEqual(len(collected), live.MAX_REQUESTS)
        self.assertLess(len(original), live.MAX_BYTES)

    def test_end_is_last_and_preserves_earlier_requests(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        writer.submit(pause())
        self.assertEqual(writer.submit({"op": "END_TEST"}), 2)
        before = self.path.read_bytes()
        for command in [pause(False), {"op": "END_TEST"}]:
            with self.assertRaises(live.InputError):
                writer.submit(command)
            self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(live.InputReader(self.path, EPOCH, "a").take(), [
            {"seq": 1, "command": pause()}, {"seq": 2, "command": {"op": "END_TEST"}}])
        document = self.document()
        document["requests"].append({"seq": 3, "command": pause(False)})
        self.write_document(document)
        with self.assertRaises(live.InputError):
            live.InputReader(self.path, EPOCH, "a")

    def test_unsupported_or_coerced_commands_never_change_history(self):
        class DerivedDict(dict):
            pass
        class DerivedString(str):
            pass
        commands = [None, [], {}, {"op": "BUILD"}, {"op": "SET_PAUSED"},
                    {"op": "SET_PAUSED", "value": 1}, {"op": "SET_PAUSED", "value": 0},
                    {"op": "SET_PAUSED", "value": "true"}, {"op": "SET_PAUSED", "value": None},
                    {"op": "SET_PAUSED", "value": True, "extra": False},
                    {"op": "END_TEST", "value": True}, DerivedDict(pause()),
                    {"op": DerivedString("END_TEST")}]
        writer = live.InputWriter(self.path, EPOCH, "a")
        original = self.path.read_bytes()
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaises(ProtocolError):
                    writer.submit(command)
                self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(writer.submit(pause()), 1)

    def test_identity_is_validated_before_any_requests_are_read(self):
        for factory in [live.InputReader, live.InputWriter]:
            for epoch, peer in [("other-epoch", "a"), (EPOCH, "b"), (1, "a"),
                                ("short", "a"), (EPOCH, "c"), (EPOCH, 1)]:
                with self.subTest(factory=factory.__name__, epoch=epoch, peer=peer):
                    with self.assertRaises(live.InputError):
                        factory(self.path, epoch, peer)
        document = self.document()
        document["epoch"] = "other-epoch"
        self.write_document(document)
        with self.assertRaises(live.InputError):
            live.InputReader(self.path, EPOCH, "a")

    def test_invalid_json_and_noncontiguous_history_are_rejected(self):
        valid = self.document()
        bad_documents = [dict(valid, protocol=True), dict(valid, extra=1), dict(valid, requests={}),
                         dict(valid, requests=[{"seq": True, "command": pause()}]),
                         dict(valid, requests=[{"seq": 2, "command": pause()}]),
                         dict(valid, requests=[{"seq": 1, "command": pause()}, {"seq": 1, "command": pause()}]),
                         dict(valid, requests=[{"seq": 1, "command": pause(), "extra": 0}]),
                         dict(valid, requests=[{"seq": 1, "command": {"op": "SET_PAUSED", "value": 1.0}}])]
        for document in bad_documents:
            with self.subTest(document=document):
                self.write_document(document)
                with self.assertRaises(ProtocolError):
                    live.InputReader(self.path, EPOCH, "a")
        raw_cases = [b"{", b"\xff", b"{" + b" " * live.MAX_BYTES,
                     b'{"protocol":1,"protocol":1}', b'{"requests":NaN}']
        for raw in raw_cases:
            self.path.write_bytes(raw)
            with self.assertRaises(ProtocolError):
                live.InputReader(self.path, EPOCH, "a")

    def test_reader_detects_mutation_and_truncation_of_sealed_and_backlogged_prefix(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        for _ in range(10):
            writer.submit(pause())
        valid = self.document()
        for mutation in ["sealed", "backlogged", "truncate", "identity"]:
            with self.subTest(mutation=mutation):
                self.write_document(valid)
                reader = live.InputReader(self.path, EPOCH, "a")
                self.assertEqual(len(reader.take()), 8)
                document = self.document()
                if mutation == "truncate":
                    document["requests"].pop()
                elif mutation == "identity":
                    document["peer"] = "b"
                else:
                    document["requests"][0 if mutation == "sealed" else 9]["command"]["value"] = False
                self.write_document(document)
                with self.assertRaises(live.InputError):
                    reader.take()
                self.write_document(valid)
                self.assertEqual([r["seq"] for r in reader.take()], [9, 10])

    def test_writer_rejects_changed_prefix_instead_of_reusing_an_old_id(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        writer.submit(pause())
        accepted = self.path.read_bytes()
        for mutation in ["truncate", "command"]:
            self.path.write_bytes(accepted)
            document = self.document()
            if mutation == "truncate":
                document["requests"] = []
            else:
                document["requests"][0]["command"] = pause(False)
            self.write_document(document)
            changed = self.path.read_bytes()
            with self.assertRaises(live.InputError):
                writer.submit(pause(False))
            self.assertEqual(self.path.read_bytes(), changed)
        self.path.write_bytes(accepted)
        self.assertEqual(writer.submit(pause(False)), 2)

    def test_returned_and_submitted_objects_cannot_mutate_stored_requests(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        command = pause()
        writer.submit(command)
        command["value"] = False
        reader = live.InputReader(self.path, EPOCH, "a")
        returned = reader.take()
        returned[0]["command"]["value"] = False
        self.assertTrue(self.document()["requests"][0]["command"]["value"])
        self.assertEqual(reader.take(), [])

    def test_failed_atomic_replace_keeps_file_sequence_and_reader_position(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        reader = live.InputReader(self.path, EPOCH, "a")
        before = self.path.read_bytes()
        with mock.patch.object(live.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                writer.submit(pause())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(reader.take(), [])
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        self.assertEqual(writer.submit(pause(False)), 1)
        self.assertEqual(reader.take(), [{"seq": 1, "command": pause(False)}])

    def test_os_exclusive_guard_rejects_a_second_process_without_consuming_id(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        code = ("from pathlib import Path; from prototype.strict_sync.live_input import InputWriter, InputBusy; "
                "import sys\ntry:\n InputWriter(Path(sys.argv[1]),sys.argv[2],'a').submit({'op':'SET_PAUSED','value':False})\n"
                "except InputBusy:\n sys.exit(0)\nelse:\n sys.exit(9)\n")
        with live._write_guard(self.path):
            result = subprocess.run([sys.executable, "-B", "-c", code, str(self.path), EPOCH],
                                    cwd=Path(__file__).resolve().parents[2], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(self.document()["requests"], [])
        self.assertEqual(writer.submit(pause()), 1)

    def test_sequential_writers_cannot_assign_duplicate_sequence(self):
        first = live.InputWriter(self.path, EPOCH, "a")
        second = live.InputWriter(self.path, EPOCH, "a")
        self.assertEqual(first.submit(pause()), 1)
        self.assertEqual(second.submit(pause(False)), 2)
        self.assertEqual(first.submit(pause()), 3)

    def test_atomic_publication_is_readable_during_real_concurrent_appends(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        reader = live.InputReader(self.path, EPOCH, "a")
        done = threading.Event()
        def write():
            try:
                for index in range(40):
                    writer.submit(pause(index % 2 == 0))
            finally:
                done.set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(write)
            collected = []
            while not done.is_set():
                collected.extend(reader.take())
            future.result(timeout=10)
        while batch := reader.take():
            collected.extend(batch)
        self.assertEqual([request["seq"] for request in collected], list(range(1, 41)))

    def test_windows_sharing_errors_retry_but_nonsharing_errors_do_not(self):
        writer = live.InputWriter(self.path, EPOCH, "a")
        sharing = OSError("sharing violation")
        sharing.winerror = 32
        original = live.os.replace
        with mock.patch.object(live.os, "replace", side_effect=[sharing, None]) as replace:
            # The mock's final success must actually publish the queue.
            def operation(source, destination):
                if replace.call_count == 1:
                    raise sharing
                return original(source, destination)
            replace.side_effect = operation
            self.assertEqual(writer.submit(pause()), 1)
            self.assertEqual(replace.call_count, 2)
        reader = live.InputReader(self.path, EPOCH, "a")
        with mock.patch.object(live, "_shared_read", side_effect=[sharing, self.path.read_bytes()]) as read:
            self.assertEqual(reader.take()[0]["seq"], 1)
            self.assertEqual(read.call_count, 2)
        with mock.patch.object(live, "_shared_read", side_effect=FileNotFoundError("missing")) as read:
            with self.assertRaises(FileNotFoundError):
                reader.take()
            self.assertEqual(read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
