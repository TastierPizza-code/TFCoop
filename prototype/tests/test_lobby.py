"""Real loopback presence connections, independent of simulation and UI."""

import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from prototype.strict_sync import lobby
from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.transport import authenticate_client, receive, send


class LobbyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.key = self.directory / "secret.key"
        self.secret = b"only-a-local-test-secret-0123456789"
        self.key.write_bytes(self.secret)
        self.tasks = []
        self.writers = []

    async def asyncTearDown(self):
        for writer in self.writers:
            writer.close()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.temporary.cleanup()

    def args(self, role, port=0, **changes):
        return SimpleNamespace(role=role, host="127.0.0.1", bind="127.0.0.1", port=port,
                               epoch="lobby_test_epoch", manifest=changes.pop("manifest", "a" * 64),
                               key_file=self.key, progress=self.directory / f"{role}.json",
                               stop_file=self.directory / f"{role}.stop", timeout=2, **changes)

    def start(self, args):
        task = asyncio.create_task(lobby.run(args))
        self.tasks.append(task)
        return task

    async def status(self, args, state, timeout=2):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            try:
                value = json.loads(args.progress.read_text("utf-8"))
                if value["state"] == state:
                    return value
            except (FileNotFoundError, json.JSONDecodeError, PermissionError):
                pass
            await asyncio.sleep(.01)
        self.fail(f"lobby {args.role} did not become {state}: " +
                  (args.progress.read_text("utf-8") if args.progress.exists() else "missing"))

    async def host(self):
        args = self.args("a")
        task = self.start(args)
        value = await self.status(args, "waiting_peer")
        return args, task, value["port"]

    async def manual_friend(self, host, port, manifest=None):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        self.writers.append(writer)
        await authenticate_client(reader, writer, self.secret, host.epoch, "b")
        fields = dict(epoch=host.epoch, manifest=manifest or host.manifest, peer="b")
        await send(writer, {"kind": "lobby_hello", **fields})
        ready = await receive(reader)
        self.assertEqual(ready["kind"], "lobby_ready")
        await send(writer, {"kind": "lobby_ready", **fields})
        connected = await receive(reader)
        self.assertEqual(connected["kind"], "lobby_connected")
        return reader, writer

    async def test_peers_connect_before_game_and_stop_gracefully(self):
        a, host_task, port = await self.host()
        b = self.args("b", port)
        friend_task = self.start(b)
        await self.status(a, "connected")
        report = await self.status(b, "connected")
        self.assertEqual(report["manifest"], a.manifest)
        self.assertNotIn(self.secret.decode(), b.progress.read_text("utf-8"))
        a.stop_file.touch()
        self.assertEqual(await asyncio.wait_for(host_task, 2), 0)
        self.assertEqual(await asyncio.wait_for(friend_task, 2), 0)
        await self.status(a, "stopped")
        await self.status(b, "stopped")

    async def test_authenticated_manifest_mismatch_halts_both(self):
        a, host_task, port = await self.host()
        b = self.args("b", port, manifest="b" * 64)
        friend_task = self.start(b)
        self.assertEqual(await asyncio.wait_for(host_task, 2), 2)
        self.assertEqual(await asyncio.wait_for(friend_task, 2), 2)
        await self.status(a, "halted")
        await self.status(b, "halted")

    async def test_unauthenticated_bad_secret_does_not_consume_host_slot(self):
        a, host_task, port = await self.host()
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        self.writers.append(writer)
        with self.assertRaises((ProtocolError, asyncio.IncompleteReadError)):
            await authenticate_client(reader, writer, b"wrong-secret-012345678901234567890123", a.epoch, "b")
        writer.close()
        await self.status(a, "waiting_peer")
        self.assertFalse(host_task.done())
        b = self.args("b", port)
        friend_task = self.start(b)
        await self.status(a, "connected")
        await self.status(b, "connected")
        b.stop_file.touch()
        self.assertEqual(await asyncio.wait_for(friend_task, 2), 0)
        self.assertEqual(await asyncio.wait_for(host_task, 2), 0)

    async def test_authenticated_disconnect_is_terminal_without_rejoin(self):
        a, host_task, port = await self.host()
        _, writer = await self.manual_friend(a, port)
        await self.status(a, "connected")
        writer.close()
        self.assertEqual(await asyncio.wait_for(host_task, 2), 2)
        await self.status(a, "halted")
        with self.assertRaises(OSError):
            await asyncio.open_connection("127.0.0.1", port)

    async def test_missing_heartbeat_halts_without_simulation_activity(self):
        with patch.object(lobby, "HEARTBEAT_TIMEOUT", .25), patch.object(lobby, "HEARTBEAT_INTERVAL", .05):
            a, host_task, port = await self.host()
            await self.manual_friend(a, port)
            self.assertEqual(await asyncio.wait_for(host_task, 2), 2)
            report = await self.status(a, "halted")
            self.assertIn("heartbeat timeout", report["reason"])

    async def test_simulation_command_is_not_accepted_by_presence_channel(self):
        a, host_task, port = await self.host()
        _, writer = await self.manual_friend(a, port)
        await send(writer, {"kind": "apply", "epoch": a.epoch, "manifest": a.manifest,
                            "command": {"op": "ROAD"}})
        self.assertEqual(await asyncio.wait_for(host_task, 2), 2)
        await self.status(a, "halted")

    async def test_friend_retries_connection_refusal_until_host_is_available(self):
        temporary_server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        port = temporary_server.sockets[0].getsockname()[1]
        temporary_server.close()
        await temporary_server.wait_closed()
        b = self.args("b", port)
        friend_task = self.start(b)
        await self.status(b, "waiting_peer")
        await asyncio.sleep(.1)
        self.assertFalse(friend_task.done())
        a = self.args("a", port)
        host_task = self.start(a)
        await self.status(a, "connected")
        await self.status(b, "connected")
        b.stop_file.touch()
        self.assertEqual(await asyncio.wait_for(friend_task, 2), 0)
        self.assertEqual(await asyncio.wait_for(host_task, 2), 0)

    async def test_stop_before_peer_prevents_connection_and_existing_progress_refuses_restart(self):
        a, host_task, _ = await self.host()
        a.stop_file.touch()
        self.assertEqual(await asyncio.wait_for(host_task, 2), 0)
        with self.assertRaises(FileExistsError):
            await lobby.run(a)


if __name__ == "__main__":
    unittest.main()
