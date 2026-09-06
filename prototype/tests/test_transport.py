import asyncio
import struct
import unittest

from prototype.strict_sync.core import ProtocolError
from prototype.strict_sync.transport import authenticate_client, authenticate_server, receive, send


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_authenticated_real_tcp(self):
        finished = asyncio.get_running_loop().create_future()

        async def server_peer(reader, writer):
            try:
                identity = await authenticate_server(reader, writer, b"k" * 32, "epoch-1234")
                message = await receive(reader)
                await send(writer, {"echo": message, "identity": identity}, fragment=1)
                finished.set_result(True)
            except Exception as exc:
                finished.set_exception(exc)
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(server_peer, "127.0.0.1", 0)
        async with server:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
            await authenticate_client(reader, writer, b"k" * 32, "epoch-1234", "b")
            await send(writer, {"payload": "x" * 10000, "zero": 0}, fragment=3)
            result = await receive(reader)
            self.assertEqual(result["identity"], "b")
            self.assertEqual(len(result["echo"]["payload"]), 10000)
            await asyncio.wait_for(finished, 3)
            writer.close()
            await writer.wait_closed()

    async def test_wrong_secret_never_authenticates(self):
        rejected = asyncio.get_running_loop().create_future()

        async def server_peer(reader, writer):
            try:
                await authenticate_server(reader, writer, b"k" * 32, "epoch-1234")
                rejected.set_result(False)
            except ProtocolError:
                rejected.set_result(True)
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(server_peer, "127.0.0.1", 0)
        async with server:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
            with self.assertRaises(asyncio.IncompleteReadError):
                await authenticate_client(reader, writer, b"z" * 32, "epoch-1234", "a")
            self.assertTrue(await asyncio.wait_for(rejected, 3))
            writer.close()
            await writer.wait_closed()

    async def test_oversize_refused_before_body(self):
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack("!I", 65537))
        with self.assertRaises(ProtocolError):
            await receive(reader)

    async def test_partial_body_is_not_a_message(self):
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack("!I", 20) + b'{"kind":')
        reader.feed_eof()
        with self.assertRaises(asyncio.IncompleteReadError):
            await receive(reader)


if __name__ == "__main__":
    unittest.main()
