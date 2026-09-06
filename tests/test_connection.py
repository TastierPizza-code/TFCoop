"""Real relay -> companion -> Lua mailbox pipeline, without any desktop window."""
import asyncio
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest

from coop.app import Connection
from coop.bridge import Mailbox
from coop.net import RelayClient


class CompanionTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_waits_for_inflight_write_and_serializes_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            started, release = threading.Event(), threading.Event()

            class SlowMailbox(Mailbox):
                slow = True

                def write_peers(self, snapshot):
                    if snapshot["connected"] and self.slow:
                        started.set()
                        release.wait(3)
                        self.slow = False
                    return super().write_peers(snapshot)

            connection = Connection(queue.Queue(), SlowMailbox(directory))
            config = {"role": "host", "name": "Host", "token": "test-token-1234567890", "port": 0, "bind": "127.0.0.1"}
            manifest = {"map_fingerprint": "map", "mod_fingerprint": "mod"}
            try:
                await asyncio.wrap_future(connection.connect(config, manifest))
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                disconnect = connection.disconnect()
                await asyncio.sleep(.05)
                self.assertFalse(disconnect.done())
                release.set()
                await asyncio.wrap_future(disconnect)
                snapshot = json.loads((Path(directory) / "peers.json").read_text())
                self.assertFalse(snapshot["connected"])
                old_disconnect = connection.disconnect()
                reconnect = connection.connect(config, manifest)
                await asyncio.wrap_future(old_disconnect)
                await asyncio.wrap_future(reconnect)
                self.assertTrue(connection.client.connected)
                self.assertEqual(connection.server.player_count, 1)
            finally:
                release.set()
                await asyncio.wrap_future(connection.disconnect())
                connection.loop.call_soon_threadsafe(connection.loop.stop)
                await asyncio.to_thread(connection.thread.join, 2)
                connection.loop.close()

    async def test_tcp_presence_reaches_game_mailbox_then_disappears(self):
        with tempfile.TemporaryDirectory() as directory:
            mailbox = Mailbox(directory)
            events = queue.Queue()
            connection = Connection(events, mailbox)
            peer = None
            try:
                manifest = {"map_fingerprint": "same-save", "mod_fingerprint": "same-mod"}
                await asyncio.wrap_future(connection.connect({"role": "host", "name": "Host", "token": "test-token-1234567890", "port": 0, "bind": "127.0.0.1"}, manifest))
                peer = RelayClient("127.0.0.1", connection.server.port, "test-token-1234567890", "Freund", manifest)
                await peer.connect()
                await peer.send_presence({"cursor": [10, 20, 30], "preview": {"kind": "street", "points": [[10, 20, 30], [20, 40, 30]]}})
                peers_file = Path(directory) / "peers.json"
                for _ in range(40):
                    await asyncio.sleep(.05)
                    snapshot = json.loads(peers_file.read_text(encoding="utf-8"))
                    remote = [p for p in snapshot["peers"] if p["id"] == peer.peer_id]
                    if remote and remote[0]["presence"]["cursor"] == [10, 20, 30]:
                        break
                else:
                    self.fail("Authenticated peer presence did not reach the game mailbox")
                self.assertTrue(snapshot["connected"])
                self.assertEqual(remote[0]["presence"]["preview"]["kind"], "street")
                await asyncio.wrap_future(connection.disconnect())
                final = json.loads(peers_file.read_text(encoding="utf-8"))
                self.assertFalse(final["connected"])
                self.assertEqual(final["peers"], [])
            finally:
                if peer:
                    await peer.close()
                await asyncio.wrap_future(connection.disconnect())
                connection.loop.call_soon_threadsafe(connection.loop.stop)
                await asyncio.to_thread(connection.thread.join, 2)
                connection.loop.close()
