"""Authenticated presence before game load; never accepts simulation commands.

This independent connection reports the second human's presence only. A connected
lobby is not proof of matching loaded game state or working engine lockstep.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import uuid

from .core import MAX_INT, ProtocolError, canonical_json
from .transport import authenticate_client, authenticate_server, receive, send


HEARTBEAT_INTERVAL = 1.0
HEARTBEAT_TIMEOUT = 5.0
POLL_INTERVAL = .1


class Progress:
    def __init__(self, args):
        self.args = args
        self.path = Path(args.progress)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x", encoding="utf-8"):
            pass  # Claim a fresh file; no implicit resume of an old lobby.
        self.state = "waiting_peer"
        self.port = args.port

    def write(self, state, reason=""):
        value = {"protocol": 1, "state": state, "reason": str(reason)[:512],
                 "role": self.args.role, "epoch": self.args.epoch, "manifest": self.args.manifest,
                 "port": self.port, "updated_ms": int(time.time() * 1000)}
        raw = canonical_json(value)
        temp = self.path.parent / ("." + self.path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("xb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            deadline = time.monotonic() + 1
            while True:
                try:
                    os.replace(temp, self.path)
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.005)
            self.state = state
        finally:
            temp.unlink(missing_ok=True)


def _message(args, kind, **fields):
    return {"kind": kind, "epoch": args.epoch, "manifest": args.manifest, **fields}


def _validate(args, message, kind, fields=()):
    if (set(message) != {"kind", "epoch", "manifest", *fields}
            or message.get("kind") != kind or message.get("epoch") != args.epoch
            or message.get("manifest") != args.manifest):
        raise ProtocolError("lobby message/epoch/manifest mismatch")


async def _close(writer):
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass


async def _terminal(writer, args, kind, reason):
    try:
        await asyncio.wait_for(send(writer, _message(args, kind, reason=str(reason)[:512])), 1)
    except (OSError, asyncio.TimeoutError):
        pass


async def _connected(args, reader, writer, progress):
    progress.write("connected")
    next_send = time.monotonic()
    last_received = time.monotonic()
    sent, received_sequence = 0, 0
    pending = asyncio.create_task(receive(reader))
    try:
        while True:
            if Path(args.stop_file).exists():
                await _terminal(writer, args, "lobby_stop", "local stop requested")
                progress.write("stopped", "local stop requested")
                return 0
            now = time.monotonic()
            if now - last_received >= HEARTBEAT_TIMEOUT:
                raise ProtocolError("lobby heartbeat timeout")
            if now >= next_send:
                sent += 1
                if sent > MAX_INT:
                    raise ProtocolError("lobby heartbeat sequence exhausted")
                await asyncio.wait_for(send(writer, _message(args, "lobby_ping", sequence=sent)), HEARTBEAT_TIMEOUT)
                next_send = now + HEARTBEAT_INTERVAL
            done, _ = await asyncio.wait({pending}, timeout=POLL_INTERVAL)
            if not done:
                continue
            message = pending.result()
            kind = message.get("kind")
            if kind in ("lobby_stop", "lobby_halt"):
                _validate(args, message, kind, ("reason",))
                if type(message["reason"]) is not str or len(message["reason"]) > 512:
                    raise ProtocolError("invalid remote lobby reason")
                progress.write("stopped" if kind == "lobby_stop" else "halted", message["reason"])
                return 0 if kind == "lobby_stop" else 2
            _validate(args, message, "lobby_ping", ("sequence",))
            if type(message["sequence"]) is not int or message["sequence"] != received_sequence + 1:
                raise ProtocolError("invalid lobby heartbeat sequence")
            received_sequence = message["sequence"]
            last_received = time.monotonic()
            progress.write("connected")
            pending = asyncio.create_task(receive(reader))
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


async def _host(args, secret, progress):
    done = asyncio.Event()
    tasks = set()
    accepted = False
    outcome = 2
    async def connection(reader, writer):
        nonlocal accepted, outcome
        task = asyncio.current_task()
        if len(tasks) >= 4 or done.is_set():
            await _close(writer)
            return
        tasks.add(task)
        trusted = False
        try:
            peer = await asyncio.wait_for(authenticate_server(reader, writer, secret, args.epoch), HEARTBEAT_TIMEOUT)
            if peer != "b" or accepted:
                return
            trusted, accepted = True, True
            hello = await asyncio.wait_for(receive(reader), HEARTBEAT_TIMEOUT)
            _validate(args, hello, "lobby_hello", ("peer",))
            if hello["peer"] != "b":
                raise ProtocolError("lobby requires the friend role b")
            await send(writer, _message(args, "lobby_ready", peer="a"))
            ready = await asyncio.wait_for(receive(reader), HEARTBEAT_TIMEOUT)
            _validate(args, ready, "lobby_ready", ("peer",))
            if ready["peer"] != "b":
                raise ProtocolError("wrong ready peer")
            await send(writer, _message(args, "lobby_connected", peer="a"))
            outcome = await _connected(args, reader, writer, progress)
            done.set()
        except Exception as exc:
            if trusted:
                reason = f"{type(exc).__name__}: {exc}"
                await _terminal(writer, args, "lobby_halt", reason)
                progress.write("halted", reason)
                outcome = 2
                done.set()
            # Unauthenticated probes do not consume the real friend's slot.
        finally:
            await _close(writer)
            tasks.discard(task)
            if trusted and not done.is_set():
                outcome = 2
                done.set()
    server = await asyncio.start_server(connection, args.bind, args.port, backlog=4)
    progress.port = server.sockets[0].getsockname()[1]
    progress.write("waiting_peer")
    deadline = time.monotonic() + args.timeout
    waiter = asyncio.create_task(done.wait())
    try:
        while not done.is_set():
            if Path(args.stop_file).exists() and not accepted:
                progress.write("stopped", "local stop requested")
                outcome = 0
                done.set()
                break
            if not accepted and time.monotonic() >= deadline:
                progress.write("halted", "waiting for friend timed out")
                outcome = 2
                done.set()
                break
            await asyncio.wait({waiter}, timeout=POLL_INTERVAL)
        return outcome
    finally:
        server.close()
        await server.wait_closed()
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _friend(args, secret, progress):
    progress.write("waiting_peer")
    deadline = time.monotonic() + args.timeout
    writer = None
    try:
        while writer is None:
            if Path(args.stop_file).exists():
                progress.write("stopped", "local stop requested")
                return 0
            if time.monotonic() >= deadline:
                raise ProtocolError("connecting to host timed out")
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(args.host, args.port), 1)
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
                await asyncio.sleep(min(.2, max(.01, deadline - time.monotonic())))
        await asyncio.wait_for(authenticate_client(reader, writer, secret, args.epoch, "b"), HEARTBEAT_TIMEOUT)
        await send(writer, _message(args, "lobby_hello", peer="b"))
        ready = await asyncio.wait_for(receive(reader), HEARTBEAT_TIMEOUT)
        _validate(args, ready, "lobby_ready", ("peer",))
        if ready["peer"] != "a":
            raise ProtocolError("lobby host must be role a")
        await send(writer, _message(args, "lobby_ready", peer="b"))
        connected = await asyncio.wait_for(receive(reader), HEARTBEAT_TIMEOUT)
        _validate(args, connected, "lobby_connected", ("peer",))
        if connected["peer"] != "a":
            raise ProtocolError("wrong connected host")
        return await _connected(args, reader, writer, progress)
    except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError, ProtocolError) as exc:
        progress.write("halted", f"{type(exc).__name__}: {exc}")
        return 2
    finally:
        if writer is not None:
            await _close(writer)


async def run(args):
    secret = Path(args.key_file).read_bytes().strip()
    if not 32 <= len(secret) <= 128:
        raise ValueError("lobby key must contain 32..128 bytes")
    progress = Progress(args)
    try:
        return await (_host(args, secret, progress) if args.role == "a" else _friend(args, secret, progress))
    except (OSError, asyncio.TimeoutError, ProtocolError) as exc:
        progress.write("halted", f"{type(exc).__name__}: {exc}")
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("a", "b"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=34208)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    if (not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", args.epoch)
            or not re.fullmatch(r"[0-9a-f]{64}", args.manifest)
            or not 1 <= args.port <= 65535 or not 0 < args.timeout <= 3600):
        parser.error("invalid lobby epoch/manifest/port/timeout")
    try:
        ipaddress.IPv4Address(args.host)
        ipaddress.IPv4Address(args.bind)
    except ipaddress.AddressValueError:
        parser.error("host and bind require IPv4 addresses")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
