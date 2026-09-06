import asyncio
import contextlib
import unittest
from unittest.mock import patch

import coop.net as net
from coop.net import RelayClient, RelayServer
from coop.protocol import AuthenticationError, ProtocolError, encode_frame, make_proof, read_frame


MANIFEST = {"map_fingerprint": "map-test", "mod_fingerprint": "mods-test"}
TOKEN = "test-secret-" + "b" * 48


async def eventually(predicate, timeout=3.0):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.015)
    await asyncio.wait_for(wait(), timeout)


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = RelayServer(TOKEN, MANIFEST, port=0)
        await self.server.start()
        self.clients = []
        self.writers = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        for writer in self.writers:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        await self.server.close()

    async def client(self, name="Friend", token=TOKEN, manifest=MANIFEST, **kwargs):
        client = RelayClient("127.0.0.1", self.server.port, token, name, manifest, **kwargs)
        self.clients.append(client)
        await client.connect()
        return client

    async def raw(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.port)
        self.writers.append(writer)
        challenge = await read_frame(reader)
        auth = {"type": "auth", "version": 1, "name": "Raw peer", "manifest": MANIFEST,
                "proof": make_proof(TOKEN, challenge["nonce"], "Raw peer", MANIFEST)}
        return reader, writer, auth

    async def read_type(self, reader, kind):
        async def find():
            while True:
                message = await read_frame(reader)
                if message["type"] == kind:
                    return message
        return await asyncio.wait_for(find(), 3)

    async def test_two_peers_presence_identity_order_and_disconnect(self):
        snapshots = []
        alice = await self.client("Alice", on_snapshot=snapshots.append)
        bob = await self.client("Böb")
        await eventually(lambda: len(alice.snapshot["peers"]) == 2)
        self.assertNotEqual(alice.color, bob.color)
        preview = {"kind": "street", "points": [[1, 2, 0], [4, 5, 0]]}
        await bob.send_presence({"cursor": [7, 8, 9], "preview": preview, "telemetry": {"money": 9876}})
        def bob_visible():
            return any(p["id"] == bob.peer_id and p["presence"]["preview"] == preview for p in alice.snapshot["peers"])
        await eventually(bob_visible)
        peer = next(p for p in alice.snapshot["peers"] if p["id"] == bob.peer_id)
        self.assertEqual(peer["name"], "Böb")
        self.assertEqual(peer["color"], bob.color)
        self.assertEqual(peer["presence"]["cursor"], [7, 8, 9])
        self.assertEqual(peer["telemetry"], {"money": 9876})
        seqs = [s["seq"] for s in snapshots]
        self.assertEqual(seqs, sorted(set(seqs)))
        await bob.close()
        await eventually(lambda: len(alice.snapshot["peers"]) == 1)
        self.assertEqual(bob.snapshot["peers"], [])

    async def test_authentication_and_manifest_mismatch_leave_no_ghosts(self):
        with self.assertRaises(AuthenticationError):
            await self.client(token="incorrect token")
        with self.assertRaisesRegex(ProtocolError, "manifest mismatch"):
            await self.client(manifest={**MANIFEST, "map_fingerprint": "another-save"})
        self.assertEqual(self.server.player_count, 0)
        valid = await self.client()
        self.assertTrue(valid.connected)

    async def test_fragmented_auth_and_presence_over_real_tcp(self):
        observer = await self.client("Observer")
        reader, writer, auth = await self.raw()
        for byte in encode_frame(auth):
            writer.write(bytes([byte]))
            await writer.drain()
            await asyncio.sleep(0)
        welcome = await self.read_type(reader, "welcome")
        frame = encode_frame({"type": "presence", "presence": {"cursor": [4, 5, 6], "preview": None}})
        for i in range(0, len(frame), 3):
            writer.write(frame[i:i+3])
            await writer.drain()
        await eventually(lambda: any(p["id"] == welcome["peer_id"] and p["presence"]["cursor"] == [4, 5, 6]
                                     for p in observer.snapshot["peers"]))

    async def test_nonce_replay_rejected(self):
        reader1, writer1, auth1 = await self.raw()
        reader2, writer2, _ = await self.raw()
        writer1.write(encode_frame(auth1))
        await writer1.drain()
        await self.read_type(reader1, "welcome")
        writer2.write(encode_frame(auth1))
        await writer2.drain()
        self.assertEqual((await self.read_type(reader2, "error"))["message"], "authentication failed")

    async def test_malformed_and_build_frames_disconnect_only_offender(self):
        observer = await self.client("Observer")
        for payload, reason in [(b'{broken}\n', "invalid JSON"),
                                (encode_frame({"type": "build", "road": "x"}), "unsupported capability"),
                                (b'x' * 65537 + b'\n', "64 KiB")]:
            reader, writer, auth = await self.raw()
            writer.write(encode_frame(auth))
            await writer.drain()
            await self.read_type(reader, "welcome")
            writer.write(payload)
            await writer.drain()
            self.assertIn(reason, (await self.read_type(reader, "error"))["message"])
            await eventually(lambda: self.server.player_count == 1)
        self.assertTrue(observer.connected)

    async def test_four_player_limit_and_reconnect_new_identity(self):
        clients = [await self.client(str(i)) for i in range(4)]
        with self.assertRaisesRegex(ProtocolError, "session is full"):
            await self.client("fifth")
        old_id = clients[0].peer_id
        await clients[0].close()
        await eventually(lambda: self.server.player_count == 3)
        await clients[0].connect()
        self.assertNotEqual(old_id, clients[0].peer_id)
        self.assertEqual(self.server.player_count, 4)

    async def test_previews_expire_despite_heartbeats(self):
        client = await self.client()
        await client.send_presence({"cursor": [1, 2, 3], "preview": {"kind": "track", "points": [[1, 2, 3]]}})
        await eventually(lambda: client.snapshot["peers"] and client.snapshot["peers"][0]["presence"]["preview"] is not None)
        await eventually(lambda: client.snapshot["peers"][0]["presence"]["preview"] is None, timeout=3)
        self.assertTrue(client.connected)
        self.assertEqual(client.snapshot["peers"][0]["status"], "idle")

    async def test_heartbeat_timeout_reclaims_peer(self):
        with patch.object(net, "HEARTBEAT_TIMEOUT", 0.25):
            reader, writer, auth = await self.raw()
            writer.write(encode_frame(auth))
            await writer.drain()
            await self.read_type(reader, "welcome")
            self.assertEqual(self.server.player_count, 1)
            await eventually(lambda: self.server.player_count == 0)

    async def test_slow_writer_has_bounded_queue_and_is_disconnected(self):
        observer = await self.client("Observer")
        reader, writer, auth = await self.raw()
        writer.write(encode_frame(auth))
        await writer.drain()
        welcome = await self.read_type(reader, "welcome")
        slow = self.server._peers[welcome["peer_id"]]
        self.assertEqual(slow.queue.maxsize, net.QUEUE_SIZE)
        async def blocked_drain():
            await asyncio.Event().wait()
        # Deterministic backpressure on one real TCP stream, independent of OS buffer size.
        slow.writer.drain = blocked_drain
        with patch.object(net, "WRITE_TIMEOUT", 0.15):
            await eventually(lambda: welcome["peer_id"] not in self.server._peers)
        self.assertTrue(observer.connected)
        await eventually(lambda: len(observer.snapshot["peers"]) == 1)

    async def test_server_shutdown_clears_client_state(self):
        client = await self.client()
        await eventually(lambda: len(client.snapshot["peers"]) == 1)
        await self.server.close()
        await asyncio.wait_for(client.wait_closed(), 2)
        self.assertFalse(client.connected)
        self.assertEqual(client.snapshot["peers"], [])


if __name__ == "__main__":
    unittest.main()
