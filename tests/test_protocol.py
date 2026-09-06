import asyncio
import math
import unittest

from coop.protocol import (
    AuthenticationError, MAX_FRAME_BYTES, ProtocolError, encode_frame, make_proof,
    read_frame, validate_auth, validate_client_message, validate_manifest,
    validate_presence, validate_preview,
)


MANIFEST = {"map_fingerprint": "map-sha256", "mod_fingerprint": "mods-sha256"}
TOKEN = "test-secret-" + "a" * 48


class ProtocolTests(unittest.TestCase):
    def test_preview_and_telemetry_are_diagnostics_only(self):
        data = {"cursor": [0, 2.5, -3], "preview": {"kind": "street", "points": [[0, 0, 0], [1, 2, 3]]},
                "telemetry": {"money": 1234, "paused": True}}
        self.assertEqual(validate_presence(data), data)
        for kind in ("street", "track", "construction", "bulldozer"):
            self.assertEqual(validate_preview({"kind": kind, "points": [[0, 0, 0]]})["kind"], kind)
        with self.assertRaisesRegex(ProtocolError, "unsupported capability"):
            validate_client_message({"type": "build", "command": "street"})

    def test_reject_unbounded_invalid_or_spoofed_presence(self):
        invalid = [
            {"cursor": [0, 1], "preview": None},
            {"cursor": [True, 1, 2], "preview": None},
            {"cursor": [math.nan, 1, 2], "preview": None},
            {"cursor": [math.inf, 1, 2], "preview": None},
            {"cursor": [10**1000, 1, 2], "preview": None},
            {"cursor": None, "preview": None, "name": "Imposter"},
            {"cursor": None, "preview": None, "telemetry": {"money": True}},
            {"cursor": None, "preview": {"kind": "road", "points": [[0, 0, 0]] * 129}},
            {"cursor": None, "preview": {"kind": "road", "points": []}},
            {"cursor": None, "preview": {"kind": "execute", "points": [[0, 0, 0]]}},
        ]
        for value in invalid:
            with self.subTest(value=str(value)[:100]), self.assertRaises(ProtocolError):
                validate_presence(value)

    def test_auth_binds_nonce_identity_and_manifest(self):
        nonce = "a" * 64
        auth = {"type": "auth", "version": 1, "name": "Friend", "manifest": MANIFEST,
                "proof": make_proof(TOKEN, nonce, "Friend", MANIFEST)}
        self.assertEqual(validate_auth(auth, TOKEN, nonce, MANIFEST), "Friend")
        with self.assertRaises(AuthenticationError):
            validate_auth(auth, TOKEN, "b" * 64, MANIFEST)
        with self.assertRaises(AuthenticationError):
            validate_auth({**auth, "name": "Imposter"}, TOKEN, nonce, MANIFEST)
        with self.assertRaisesRegex(ProtocolError, "manifest mismatch"):
            validate_auth(auth, TOKEN, nonce, {**MANIFEST, "map_fingerprint": "other-map"})
        with self.assertRaises(ProtocolError):
            validate_manifest({"map_fingerprint": "missing mods"})

    def test_frame_encoding_boundaries(self):
        self.assertLessEqual(len(encode_frame({"data": "x" * (MAX_FRAME_BYTES - 12)})), MAX_FRAME_BYTES)
        with self.assertRaises(ProtocolError):
            encode_frame({"data": "x" * MAX_FRAME_BYTES})
        with self.assertRaises(ProtocolError):
            encode_frame({"data": math.nan})


class FrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_unicode_frame(self):
        reader = asyncio.StreamReader(limit=MAX_FRAME_BYTES)
        task = asyncio.create_task(read_frame(reader))
        data = encode_frame({"name": "Mira und Jörg 🚂"})
        for byte in data:
            reader.feed_data(bytes([byte]))
            await asyncio.sleep(0)
        self.assertEqual(await task, {"name": "Mira und Jörg 🚂"})

    async def test_malformed_frames(self):
        for data in (b'{"a":1,"a":2}\n', b'{"x":NaN}\n', b'[]\n', b'\xff\n',
                     b'{invalid}\n', b'{}', b'x' * (MAX_FRAME_BYTES + 1) + b'\n'):
            with self.subTest(data=data[:50]):
                reader = asyncio.StreamReader(limit=MAX_FRAME_BYTES)
                reader.feed_data(data)
                reader.feed_eof()
                with self.assertRaises(ProtocolError):
                    await read_frame(reader)


if __name__ == "__main__":
    unittest.main()
