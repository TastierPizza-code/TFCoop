"""Bounded authenticated TCP for the prototype. No file-tail or UDP loss fallback.

HMAC authenticates the handshake; use a trusted LAN/Hamachi for remote tests.
This is not an encrypted transport and does not connect to Steam services.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import struct

from .core import MAX_MESSAGE_BYTES, ProtocolError, canonical_json, decode_message


async def send(writer, message, *, fragment=0):
    payload = canonical_json(message)
    wire = struct.pack("!I", len(payload)) + payload
    size = fragment if fragment > 0 else len(wire)
    for offset in range(0, len(wire), size):
        writer.write(wire[offset:offset + size])
        await writer.drain()


async def receive(reader):
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 1 <= size <= MAX_MESSAGE_BYTES:
        raise ProtocolError("invalid frame length")
    return decode_message(await reader.readexactly(size))


def proof(secret, side, epoch, nonce, peer):
    return hmac.new(secret, canonical_json([side, epoch, nonce, peer]), hashlib.sha256).hexdigest()


async def authenticate_server(reader, writer, secret, epoch):
    nonce = secrets.token_hex(32)
    await send(writer, {"kind": "challenge", "epoch": epoch, "nonce": nonce})
    response = await receive(reader)
    if set(response) != {"kind", "peer", "proof"} or response.get("kind") != "authenticate":
        raise ProtocolError("invalid authentication response")
    peer = response.get("peer")
    if peer not in ("a", "b") or not isinstance(response.get("proof"), str):
        raise ProtocolError("invalid authentication identity")
    if not hmac.compare_digest(response["proof"], proof(secret, "client", epoch, nonce, peer)):
        raise ProtocolError("authentication failed")
    await send(writer, {"kind": "authenticated", "proof": proof(secret, "server", epoch, nonce, peer)})
    return peer


async def authenticate_client(reader, writer, secret, epoch, peer):
    message = await receive(reader)
    if (set(message) != {"kind", "epoch", "nonce"} or message.get("kind") != "challenge"
            or message.get("epoch") != epoch or not isinstance(message.get("nonce"), str)
            or len(message["nonce"]) != 64):
        raise ProtocolError("invalid server challenge")
    nonce = message["nonce"]
    await send(writer, {"kind": "authenticate", "peer": peer,
                        "proof": proof(secret, "client", epoch, nonce, peer)})
    response = await receive(reader)
    if (set(response) != {"kind", "proof"} or response.get("kind") != "authenticated"
            or not isinstance(response.get("proof"), str)
            or not hmac.compare_digest(response["proof"], proof(secret, "server", epoch, nonce, peer))):
        raise ProtocolError("server authentication failed")
