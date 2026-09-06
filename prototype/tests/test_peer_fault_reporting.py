"""Fatal diagnostics use authenticated TCP without becoming world receipts."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.engine_mailbox import MailboxError, NativeMailbox, native_fault_detail
from prototype.strict_sync.runner import host, peer_error_message, validate_peer_error
from prototype.strict_sync.transport import authenticate_client, receive, send
from prototype.tests.test_engine_mailbox import native_bytes


EPOCH = "diagnostic-epoch"


class FaultDetailTests(unittest.TestCase):
    def test_native_fault_keeps_original_codes_and_request_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "native_status.txt").write_bytes(native_bytes(epoch=7, halted=1,
                runtime_fault=102, win32_error=5, io_operation=7, request_received=7,
                request_completed=7, completed_frame=7))
            with self.assertRaises(MailboxError) as failure:
                NativeMailbox(root, 7, timeout_s=.1)
            for expected in ("fault=0", "runtime_fault=102", "win32_error=5",
                             "io_operation=7", "request_received=7", "completed_frame=7"):
                self.assertIn(expected, str(failure.exception))
            self.assertIn("io_operation=0", native_fault_detail({"runtime_fault": 102}))

    def test_local_detail_is_bounded_and_one_line(self):
        message = peer_error_message(EPOCH, 6, 7, MailboxError("x\n\t\x00\x7f" * 1000))
        self.assertLessEqual(len(message["detail"]), 384)
        self.assertEqual(validate_peer_error(message, EPOCH), message)

    def test_malformed_diagnostics_are_rejected(self):
        message = peer_error_message(EPOCH, 6, 7, MailboxError("native status failed"))
        invalid = [dict(message, epoch="stale-epoch"), dict(message, peer="b"),
                   dict(message, round=True), dict(message, round=-1),
                   dict(message, frame=1.5), dict(message, frame=1 << 53),
                   dict(message, error_type=""), dict(message, error_type="a:b"),
                   dict(message, detail=""), dict(message, detail="x" * 385),
                   dict(message, detail="injected\nline"), dict(message, detail=13)]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ProtocolError):
                validate_peer_error(candidate, EPOCH)


class DiagnosticTransportTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, message=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = argparse.Namespace(epoch=EPOCH, timeout=.5, rounds=3, bind="127.0.0.1", port=0,
                                      ready=root / "ready.json", report=root / "report.json")
            secret = b"x" * 32
            task = asyncio.create_task(host(args, secret, expected_manifest="a" * 64))
            writer = None
            try:
                while not args.ready.exists():
                    if task.done():
                        await task
                    await asyncio.sleep(.005)
                reader, writer = await asyncio.open_connection("127.0.0.1", json.loads(args.ready.read_text())["port"])
                await authenticate_client(reader, writer, secret, EPOCH, "a")
                if message is not None:
                    await send(writer, message)
                    terminal = await asyncio.wait_for(receive(reader), 1)
                    self.assertEqual(terminal["kind"], "halt")
                else:
                    writer.close()
                    await writer.wait_closed()
                self.assertEqual(await asyncio.wait_for(task, 2), 2)
                report = json.loads(args.report.read_text())
                self.assertFalse(report["coordinated_completed"])
                self.assertFalse(any(action["kind"] == "step" for action in report["actions"]))
                return report
            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_valid_fault_halts_with_original_reason(self):
        report = await self.invoke(peer_error_message(EPOCH, 0, 0,
            MailboxError("native gate halted: runtime_fault=102, win32_error=5")))
        self.assertIn("peer a: MailboxError: native gate halted", report["reason"])
        self.assertEqual(report["peer_error"]["peer"], "a")

    async def test_wrong_epoch_diagnostic_halts_as_protocol_error(self):
        report = await self.invoke(peer_error_message("stale-epoch", 0, 0, MailboxError("untrusted detail")))
        self.assertIsNone(report["peer_error"])
        self.assertIn("invalid peer_error envelope/epoch", report["reason"])
        self.assertNotIn("untrusted detail", report["reason"])

    async def test_disconnect_without_diagnostic_remains_fallback(self):
        report = await self.invoke()
        self.assertEqual(report["reason"], "peer a: IncompleteReadError")
        self.assertIsNone(report["peer_error"])


if __name__ == "__main__":
    unittest.main()
