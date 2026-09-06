"""Asyncio TCP relay for shared cursors and previews over LAN or Hamachi.

The relay does not load a savegame, synchronize simulation, or execute build
commands. Authentication protects admission; TCP itself is not encrypted.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hmac
import inspect
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .protocol import (
    AuthenticationError, CAPABILITIES, COLORS, MAX_FRAME_BYTES, MAX_PLAYERS,
    PREVIEW_TTL, PROTOCOL_VERSION, ProtocolError, encode_frame, fields,
    make_proof, read_frame, validate_auth, validate_client_message,
    validate_manifest, validate_name, validate_presence, validate_snapshot,
)

DEFAULT_PORT = 34197
HANDSHAKE_TIMEOUT = 5.0
HEARTBEAT_INTERVAL = 1.0
HEARTBEAT_TIMEOUT = 8.0
SNAPSHOT_INTERVAL = 0.1
WRITE_TIMEOUT = 2.0
QUEUE_SIZE = 32
MAX_HANDSHAKES = 16
MAX_MESSAGES_PER_SECOND = 120


def _token(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError("a nonempty session token is required")
    return value


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(Exception, asyncio.CancelledError):
        await asyncio.wait_for(writer.wait_closed(), 1.0)


async def _write(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    writer.write(encode_frame(message))
    await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)


@dataclass
class _Peer:
    id: str
    name: str
    color: str
    writer: asyncio.StreamWriter
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))
    cursor: list | None = None
    preview: dict | None = None
    telemetry: dict | None = None
    presence_at: float = 0.0
    received_at: float = field(default_factory=time.monotonic)
    rate_at: float = field(default_factory=time.monotonic)
    rate_count: int = 0


class RelayServer:
    def __init__(self, token: str, manifest: dict[str, str],
                 host: str = "127.0.0.1", port: int = DEFAULT_PORT):
        self._token = _token(token)
        self.manifest = validate_manifest(manifest)
        self.host = host
        self.port = port
        self._server: asyncio.AbstractServer | None = None
        self._peers: dict[str, _Peer] = {}
        self._handlers: set[asyncio.Task] = set()
        self._ticker: asyncio.Task | None = None
        self._seq = 0
        self._closing = False

    @property
    def player_count(self) -> int:
        return len(self._peers)

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("relay already started")
        self._closing = False
        self._server = await asyncio.start_server(self._accepted, self.host,
                                                  self.port, limit=MAX_FRAME_BYTES)
        self.port = self._server.sockets[0].getsockname()[1]
        self._ticker = asyncio.create_task(self._tick(), name="coop-relay-snapshots")

    def _accepted(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._closing or len(self._handlers) >= MAX_HANDSHAKES + MAX_PLAYERS:
            writer.close()
            return
        task = asyncio.create_task(self._handle(reader, writer), name="coop-relay-peer")
        self._handlers.add(task)
        task.add_done_callback(self._handlers.discard)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer: _Peer | None = None
        sender: asyncio.Task | None = None
        try:
            writer.transport.set_write_buffer_limits(high=MAX_FRAME_BYTES, low=16384)
            nonce = secrets.token_hex(32)
            await _write(writer, {"type": "challenge", "version": PROTOCOL_VERSION, "nonce": nonce})
            request = await asyncio.wait_for(read_frame(reader), HANDSHAKE_TIMEOUT)
            name = validate_auth(request, self._token, nonce, self.manifest)
            if len(self._peers) >= MAX_PLAYERS:
                raise ProtocolError("session is full (maximum 4 players)")
            used_colors = {p.color for p in self._peers.values()}
            peer = _Peer(secrets.token_hex(8), name, next(c for c in COLORS if c not in used_colors), writer)
            # Reserve identity before awaiting, so simultaneous joins cannot exceed capacity.
            self._peers[peer.id] = peer
            await _write(writer, {"type": "welcome", "version": PROTOCOL_VERSION,
                                  "peer_id": peer.id, "name": name, "color": peer.color,
                                  "capabilities": list(CAPABILITIES),
                                  "server_proof": make_proof(self._token, nonce, "server:" + peer.id, self.manifest)})
            sender = asyncio.create_task(self._send(peer), name="coop-relay-send")
            self._broadcast()
            while not self._closing and peer.id in self._peers:
                message = validate_client_message(await asyncio.wait_for(read_frame(reader), HEARTBEAT_TIMEOUT))
                now = time.monotonic()
                if now - peer.rate_at >= 1.0:
                    peer.rate_at, peer.rate_count = now, 0
                peer.rate_count += 1
                if peer.rate_count > MAX_MESSAGES_PER_SECOND:
                    raise ProtocolError("message rate exceeded")
                peer.received_at = now
                if message["type"] == "presence":
                    value = message["presence"]
                    peer.cursor, peer.preview = value["cursor"], value["preview"]
                    peer.presence_at = now
                    if "telemetry" in value:
                        peer.telemetry = value["telemetry"]
                elif message["type"] == "telemetry":
                    peer.telemetry = message["telemetry"]
                # Ping is answered by the next periodic snapshot.
        except ProtocolError as exc:
            with contextlib.suppress(Exception):
                await _write(writer, {"type": "error", "message": str(exc)})
        except (EOFError, OSError, asyncio.TimeoutError, ConnectionError):
            pass
        finally:
            if peer is not None:
                self._drop(peer)
            if sender is not None:
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sender
            await _close_writer(writer)

    def _drop(self, peer: _Peer) -> None:
        self._peers.pop(peer.id, None)
        peer.writer.close()

    async def _send(self, peer: _Peer) -> None:
        try:
            while True:
                data = await peer.queue.get()
                peer.writer.write(data)
                await asyncio.wait_for(peer.writer.drain(), WRITE_TIMEOUT)
        except (OSError, asyncio.TimeoutError, ConnectionError):
            self._drop(peer)

    def _broadcast(self) -> None:
        now = time.monotonic()
        peers = []
        for peer in list(self._peers.values()):
            if now - peer.received_at > HEARTBEAT_TIMEOUT:
                self._drop(peer)
                continue
            active = now - peer.presence_at <= PREVIEW_TTL
            if not active:
                peer.preview = None
                peer.cursor = None
            peers.append({"id": peer.id, "name": peer.name, "color": peer.color,
                          "presence": {"cursor": peer.cursor, "preview": peer.preview},
                          "status": "active" if active else "idle", "telemetry": peer.telemetry})
        self._seq += 1
        data = encode_frame({"type": "snapshot", "seq": self._seq, "peers": peers,
                             "capabilities": list(CAPABILITIES)})
        for peer in list(self._peers.values()):
            try:
                peer.queue.put_nowait(data)
            except asyncio.QueueFull:
                self._drop(peer)

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(SNAPSHOT_INTERVAL)
            self._broadcast()

    async def close(self) -> None:
        self._closing = True
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._ticker is not None:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
            self._ticker = None
        for peer in list(self._peers.values()):
            self._drop(peer)
        handlers = list(self._handlers)
        for handler in handlers:
            handler.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)
        self._handlers.clear()


class RelayClient:
    """One connection, with independent snapshot reader and heartbeat tasks.

    The optional callback is synchronous and must be fast; it runs on this
    client's event loop. Use a thread-safe queue to communicate with a GUI.
    Calling connect() again after close/disconnect establishes a new identity.
    """

    def __init__(self, host: str, port: int, token: str, name: str,
                 manifest: dict[str, str], on_snapshot: Callable[[dict], None] | None = None):
        self.host, self.port = host, port
        self._token = _token(token)
        self.name = validate_name(name)
        self.manifest = validate_manifest(manifest)
        self.on_snapshot = on_snapshot
        self.peer_id: str | None = None
        self.color: str | None = None
        self.snapshot = {"type": "snapshot", "seq": 0, "peers": [], "capabilities": list(CAPABILITIES)}
        self.last_error: str | None = None
        self.connected = False
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._closed = asyncio.Event()
        self._closed.set()
        self._snapshot_at = 0.0

    async def connect(self) -> None:
        if self.connected or (self._read_task and not self._read_task.done()):
            raise RuntimeError("client is already connected")
        await self.close()
        self.last_error = None
        self.peer_id = None
        self.color = None
        self.snapshot = {"type": "snapshot", "seq": 0, "peers": [], "capabilities": list(CAPABILITIES)}
        try:
            await asyncio.wait_for(self._handshake(), HANDSHAKE_TIMEOUT)
        except BaseException:
            if self._writer:
                await _close_writer(self._writer)
            self._writer = None
            raise
        self.connected = True
        self._closed.clear()
        self._read_task = asyncio.create_task(self._read(), name="coop-client-read")
        self._heartbeat_task = asyncio.create_task(self._heartbeat(), name="coop-client-heartbeat")

    async def _handshake(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port, limit=MAX_FRAME_BYTES)
        self._writer.transport.set_write_buffer_limits(high=MAX_FRAME_BYTES, low=16384)
        challenge = await read_frame(self._reader)
        fields(challenge, {"type", "version", "nonce"})
        nonce = challenge["nonce"]
        if (challenge["type"] != "challenge" or type(challenge["version"]) is not int
                or challenge["version"] != PROTOCOL_VERSION or not isinstance(nonce, str)
                or not re.fullmatch("[0-9a-f]{64}", nonce)):
            raise ProtocolError("invalid server challenge")
        await _write(self._writer, {"type": "auth", "version": PROTOCOL_VERSION,
                                   "name": self.name, "manifest": self.manifest,
                                   "proof": make_proof(self._token, nonce, self.name, self.manifest)})
        welcome = await read_frame(self._reader)
        self._raise_server_error(welcome)
        fields(welcome, {"type", "version", "peer_id", "name", "color", "capabilities", "server_proof"})
        peer_id = welcome["peer_id"]
        if (welcome["type"] != "welcome" or type(welcome["version"]) is not int
                or welcome["version"] != PROTOCOL_VERSION or not isinstance(peer_id, str)
                or not re.fullmatch("[0-9a-f]{16}", peer_id) or welcome["name"] != self.name
                or welcome["color"] not in COLORS or welcome["capabilities"] != CAPABILITIES):
            raise ProtocolError("invalid server welcome")
        proof = welcome["server_proof"]
        if not isinstance(proof, str) or not re.fullmatch("[0-9a-f]{64}", proof) or not hmac.compare_digest(
                make_proof(self._token, nonce, "server:" + peer_id, self.manifest), proof):
            raise AuthenticationError("server authentication failed")
        self.peer_id, self.color = peer_id, welcome["color"]

    @staticmethod
    def _raise_server_error(message: dict) -> None:
        if message.get("type") == "error":
            fields(message, {"type", "message"})
            # Only emit safe bounded text, never an arbitrary object from a peer.
            text = message["message"]
            if not isinstance(text, str) or len(text) > 200 or any(ord(c) < 32 for c in text):
                raise ProtocolError("server rejected connection")
            if text == "authentication failed":
                raise AuthenticationError(text)
            raise ProtocolError(text)

    def _publish(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        if self.on_snapshot is not None:
            try:
                result = self.on_snapshot(copy.deepcopy(snapshot))
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    self.last_error = "on_snapshot must be a synchronous callback"
            except Exception:
                self.last_error = "snapshot callback failed"

    async def _read(self) -> None:
        try:
            while self.connected:
                message = await asyncio.wait_for(read_frame(self._reader), HEARTBEAT_TIMEOUT)
                self._raise_server_error(message)
                snapshot = validate_snapshot(message)
                if snapshot["seq"] <= self.snapshot["seq"]:
                    raise ProtocolError("snapshot sequence must increase")
                self._snapshot_at = time.monotonic()
                self._publish(snapshot)
        except ProtocolError as exc:
            self.last_error = str(exc)
        except (EOFError, OSError, asyncio.TimeoutError, ConnectionError):
            self.last_error = "relay disconnected"
        finally:
            self.connected = False
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
            if self._writer is not None:
                await _close_writer(self._writer)
            self._publish({"type": "snapshot", "seq": self.snapshot["seq"] + 1,
                           "peers": [], "capabilities": list(CAPABILITIES)})
            self._closed.set()

    async def _heartbeat(self) -> None:
        try:
            while self.connected:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if time.monotonic() - self._snapshot_at >= PREVIEW_TTL:
                    stale = copy.deepcopy(self.snapshot)
                    for peer in stale["peers"]:
                        peer["presence"] = {"cursor": None, "preview": None}
                        peer["status"] = "idle"
                    self._publish(stale)
                await self._send({"type": "ping"})
        except (OSError, asyncio.TimeoutError, ConnectionError):
            if self._writer is not None:
                self._writer.close()

    async def _send(self, message: dict) -> None:
        if not self.connected or self._writer is None:
            raise ConnectionError("relay is not connected")
        async with self._send_lock:
            await _write(self._writer, message)

    async def send_presence(self, presence: dict[str, Any]) -> None:
        await self._send({"type": "presence", "presence": validate_presence(presence)})

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def close(self) -> None:
        self.connected = False
        tasks = [t for t in (self._read_task, self._heartbeat_task)
                 if t is not None and t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._read_task = self._heartbeat_task = None
        if self._writer is not None:
            await _close_writer(self._writer)
            self._writer = None
        self._closed.set()
