"""Persistent preferences, real TCP fresh negotiation and launcher ownership."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
import zipfile

from prototype.strict_sync import lobby, launcher_session as workflow, test_pairing as pairing
from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.live_input import InputReader
from prototype.strict_sync.transport import authenticate_client, authenticate_server, receive, send
from prototype.tests import test_lobby as lobby_fixtures, test_launcher_session as launcher_fixtures


class ProfileTests(unittest.TestCase):
    def test_private_profile_is_canonical_and_independent_of_launcher_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertIsNone(pairing.load_profile(root))
            code = pairing.new_code()
            settings = root / "launcher.json"
            settings.write_text('{"game_dir":"unchanged"}')
            saved = pairing.save_profile(root, host=" 25.1.2.3 ", code=code.lower(), role="b")
            for _ in range(3):
                self.assertEqual(pairing.load_profile(root), saved)
                settings.write_text('{"game_dir":"updated","last_run":"restored"}')
            self.assertEqual(saved["host"], "25.1.2.3")
            self.assertEqual(saved["code"], code)
            self.assertEqual(saved["role"], "b")
            self.assertEqual(set(path.name for path in root.iterdir()), {"launcher.json", pairing.PROFILE_NAME})

    def test_invalid_profile_is_never_silently_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / pairing.PROFILE_NAME
            for raw in ('{', '{"schema":true}', 'x' * (pairing.PROFILE_LIMIT + 1)):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    pairing.load_profile(temporary)
                self.assertEqual(path.read_text(), raw)
            for host, code, role in (("0.0.0.0", pairing.new_code(), "a"),
                                     ("127.0.0.1", "short", "a"),
                                     ("127.0.0.1", pairing.new_code(), "c")):
                with self.assertRaises(ValueError):
                    pairing.save_profile(temporary, host=host, code=code, role=role)


class FreshLobbyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = lobby_fixtures.LobbyTests.asyncSetUp
    asyncTearDown = lobby_fixtures.LobbyTests.asyncTearDown
    start = lobby_fixtures.LobbyTests.start
    status = lobby_fixtures.LobbyTests.status
    host = lobby_fixtures.LobbyTests.host

    def args(self, role, port=0, **changes):
        return lobby_fixtures.LobbyTests.args(self, role, port, local_run=uuid.uuid4().hex, **changes)

    async def connect_pair(self):
        a, host_task, port = await self.host()
        b = self.args("b", port)
        friend_task = self.start(b)
        first = await self.status(a, "connected")
        second = await self.status(b, "connected")
        return a, b, host_task, friend_task, first, second

    async def test_same_private_pairing_gets_new_epoch_and_key_on_each_fresh_run(self):
        epochs, keys = set(), set()
        for index in range(2):
            self.directory = self.directory / str(index)
            self.directory.mkdir()
            a, b, host_task, friend_task, first, second = await self.connect_pair()
            self.assertEqual(first["epoch"], second["epoch"])
            self.assertNotEqual(first["epoch"], a.epoch)
            self.assertEqual(pairing.validate_connection(self.secret, first, role="a", local_run=a.local_run,
                                                         manifest=a.manifest), first["epoch"])
            self.assertEqual(pairing.validate_connection(self.secret, second, role="b", local_run=b.local_run,
                                                         manifest=b.manifest), first["epoch"])
            epoch = first["epoch"]
            key = pairing.game_secret(self.secret, epoch, a.manifest)
            self.assertNotIn(epoch, epochs)
            self.assertNotIn(key, keys)
            self.assertNotEqual(key, self.secret)
            epochs.add(epoch)
            keys.add(key)
            raw = a.progress.read_text() + b.progress.read_text()
            self.assertNotIn(self.secret.decode(), raw)
            self.assertNotIn(a.epoch, raw)
            self.assertNotIn("127.0.0.1", raw)
            a.stop_file.touch()
            self.assertEqual(await asyncio.wait_for(host_task, 2), 0)
            self.assertEqual(await asyncio.wait_for(friend_task, 2), 0)

    test_authenticated_manifest_mismatch_halts_both = lobby_fixtures.LobbyTests.test_authenticated_manifest_mismatch_halts_both
    test_unauthenticated_bad_secret_does_not_consume_host_slot = lobby_fixtures.LobbyTests.test_unauthenticated_bad_secret_does_not_consume_host_slot
    test_friend_retries_connection_refusal_until_host_is_available = lobby_fixtures.LobbyTests.test_friend_retries_connection_refusal_until_host_is_available
    test_stop_before_peer_prevents_connection_and_existing_progress_refuses_restart = lobby_fixtures.LobbyTests.test_stop_before_peer_prevents_connection_and_existing_progress_refuses_restart

    async def test_authenticated_disconnect_is_terminal_and_no_reconnect(self):
        a, host_task, port = await self.host()
        b = self.args("b", port)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        self.writers.append(writer)
        await authenticate_client(reader, writer, self.secret, a.epoch, "b")
        await lobby._friend_negotiate(b, self.secret, reader, writer)
        await self.status(a, "connected")
        writer.close()
        await writer.wait_closed()
        self.assertEqual(await asyncio.wait_for(host_task, 2), 2)
        state = await self.status(a, "halted")
        with self.assertRaises(OSError):
            await asyncio.open_connection("127.0.0.1", state["port"])

    async def test_forged_or_previous_run_offer_never_connects_friend(self):
        for kind in ("stale", "forged", "old_commit"):
            self.directory = self.directory / kind
            self.directory.mkdir()
            async def malicious(reader, writer):
                try:
                    await authenticate_server(reader, writer, self.secret, "lobby_test_epoch")
                    hello = await receive(reader)
                    fields = {"host_run": uuid.uuid4().hex, "friend_run": hello["local_run"],
                              "epoch": uuid.uuid4().hex, "manifest": "a" * 64}
                    if kind == "stale":
                        fields["friend_run"] = uuid.uuid4().hex
                    offer = pairing.signed_message(self.secret, "pairing_offer", **fields)
                    if kind == "forged":
                        offer["proof"] = "0" * 64
                    await send(writer, offer)
                    if kind == "old_commit":
                        await receive(reader)
                        fields["epoch"] = uuid.uuid4().hex
                        await send(writer, pairing.signed_message(self.secret, "pairing_commit", **fields))
                finally:
                    writer.close()
            server = await asyncio.start_server(malicious, "127.0.0.1", 0)
            try:
                b = self.args("b", server.sockets[0].getsockname()[1])
                friend_task = self.start(b)
                self.assertEqual(await asyncio.wait_for(friend_task, 2), 2)
                state = await self.status(b, "halted")
                self.assertFalse(state["epoch"])
                self.assertFalse(state["run_proof"])
            finally:
                server.close()
                await server.wait_closed()

    async def test_host_rejects_previous_ack_even_with_valid_pairing_key(self):
        a, host_task, port = await self.host()
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        self.writers.append(writer)
        await authenticate_client(reader, writer, self.secret, a.epoch, "b")
        await send(writer, pairing.signed_message(self.secret, "pairing_hello", local_run=uuid.uuid4().hex,
                                                   manifest=a.manifest))
        offer = await receive(reader)
        fields = {key: offer[key] for key in lobby.RUN_FIELDS}
        fields["epoch"] = uuid.uuid4().hex
        await send(writer, pairing.signed_message(self.secret, "pairing_accept", **fields))
        self.assertEqual(await asyncio.wait_for(host_task, 2), 2)
        state = await self.status(a, "halted")
        self.assertFalse(state["epoch"])


class FreshLauncherTests(unittest.TestCase):
    setUp = launcher_fixtures.LauncherSessionTests.setUp
    fake_spawn = launcher_fixtures.LauncherSessionTests.fake_spawn
    host_ready = launcher_fixtures.LauncherSessionTests.host_ready

    def fresh(self, role="a"):
        self.run = replace(self.run, role=role, epoch="", pairing_epoch="b" * 32,
                           local_run=uuid.uuid4().hex, test_mode=workflow.PACED_LIVE_MODE)
        self.secret = b"1" * 64
        (self.run.directory / "pairing.key").write_bytes(self.secret)
        return workflow.SessionController(self.run, spawn=self.spawn)

    def connected(self, **changes):
        value = {"protocol": 2, "state": "connected", "role": self.run.role,
                 "local_run": self.run.local_run, "epoch": "c" * 32, "manifest": self.run.manifest}
        value.update(changes)
        value["run_proof"] = pairing.connection_receipt(self.secret, role=value["role"], local_run=value["local_run"],
                                                        epoch=value["epoch"], manifest=value["manifest"])
        workflow.write_json(self.run_dir / "lobby-progress.json", value)
        return value

    def test_no_game_worker_or_queue_until_negotiated_then_host_ready_controls_peer(self):
        controller = self.fresh()
        controller.start()
        self.assertEqual(set(controller.children), {"lobby"})
        self.assertFalse(self.run.live_input_path.exists())
        self.assertFalse((self.run.directory / "session.key").exists())
        with self.assertRaises(ValueError):
            controller._game_args("host")
        connected = self.connected()
        controller.poll()
        self.assertEqual(set(controller.children), {"lobby", "host"})
        self.assertEqual(self.run.epoch, connected["epoch"])
        self.assertEqual(InputReader(self.run.live_input_path, self.run.epoch, "a").take(), [])
        self.assertEqual((self.run.directory / "session.key").read_bytes(),
                         pairing.game_secret(self.secret, self.run.epoch, self.run.manifest))
        self.host_ready()
        controller.poll()
        controller.poll()
        self.assertEqual(set(controller.children), {"lobby", "host", "peer"})
        self.assertEqual(self.spawn.call_count, 3)
        for command, _, _ in self.spawned[1:]:
            self.assertEqual(command[command.index("--epoch") + 1], self.run.epoch)
            self.assertNotIn(self.run.pairing_epoch, command)

    def test_friend_activates_queue_and_game_peer_after_authentication(self):
        controller = self.fresh("b")
        controller.start()
        self.connected()
        result = controller.poll()
        self.assertTrue(result["peer_started"])
        self.assertEqual(set(controller.children), {"lobby", "peer"})

    def test_prepared_run_is_consumed_even_if_only_lobby_has_started(self):
        controller = self.fresh()
        controller.start()
        with self.assertRaises(FileExistsError):
            workflow.SessionController(self.run, spawn=self.spawn).start()
        self.assertEqual(self.spawn.call_count, 1)

    def test_signed_but_stale_local_run_cannot_create_workers_or_queue(self):
        controller = self.fresh()
        controller.start()
        self.connected(local_run="d" * 32)
        result = controller.poll()
        self.assertTrue(result["failure"])
        self.assertTrue(result["stopping"])
        self.assertEqual(set(controller.children), {"lobby"})
        self.assertFalse(self.run.live_input_path.exists())
        self.assertFalse((self.run.directory / "session.key").exists())

    def test_lobby_exit_prevents_late_connection_receipt_from_starting_workers(self):
        controller = self.fresh()
        controller.start()
        self.connected()
        controller.children["lobby"].returncode = 2
        result = controller.poll()
        self.assertTrue(result["failure"])
        self.assertEqual(set(controller.children), {"lobby"})

    def test_changed_epoch_after_connection_is_terminal(self):
        controller = self.fresh("b")
        controller.start()
        self.connected()
        controller.poll()
        self.connected(epoch="d" * 32)
        result = controller.poll()
        self.assertTrue(result["failure"])
        self.assertTrue(result["stopping"])

    def test_diagnostic_archive_excludes_private_profile_keys_and_redacts_socket_addresses(self):
        self.fresh()
        pairing.save_profile(self.run.directory, host=self.run.host, code=pairing.new_code(), role="a")
        (self.run.directory / "peer.log").write_text("socket connection refused at ('25.1.2.3', 34207)\n"
                                                    "C:/logs/25.1.2.3.log\n" +
                                                    json.dumps({"filename": "C:\\logs\\25.1.2.3\\error.log"}))
        destination = self.root / "report.zip"
        workflow.export_diagnostics(self.run, destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertNotIn("pairing.key", archive.namelist())
            self.assertNotIn(pairing.PROFILE_NAME, archive.namelist())
            self.assertNotIn(self.run.host.encode(), archive.read("peer.log"))
            self.assertIn(b"34207", archive.read("peer.log"))


if __name__ == "__main__":
    unittest.main()
