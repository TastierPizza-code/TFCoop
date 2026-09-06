"""Headless TCP contract experiment. This CLI never opens or modifies TF2.

Run ``py -3.10 -m prototype.strict_sync.smoke`` for isolated multi-process tests.
This CLI deliberately uses only the model backend. The separate game_runner CLI
requires an explicitly prepared controlled engine measurement session.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import time

from .core import CAPABILITIES, Coordinator, ProtocolError, digest, _integer
from .model import ModelEngine, scenario
from .replica import Replica
from .transport import authenticate_client, authenticate_server, receive, send


MODEL_CAPABILITIES = tuple(sorted((*CAPABILITIES, "contract_model_only")))
PEER_ERROR_LIMIT = 384


def peer_error_message(epoch, round_number, frame, error):
    """Diagnostic only: no world receipt, reconnect, or further permit implied."""
    plain = "".join(char if ord(char) >= 32 and ord(char) != 127 else " " for char in str(error))
    detail = " ".join(plain.split())[:PEER_ERROR_LIMIT] or "unspecified local failure"
    return {"kind": "peer_error", "epoch": epoch, "round": round_number,
            "frame": frame, "error_type": type(error).__name__[:64], "detail": detail}


def validate_peer_error(message, epoch):
    if (set(message) != {"kind", "epoch", "round", "frame", "error_type", "detail"}
            or message.get("kind") != "peer_error" or message.get("epoch") != epoch):
        raise ProtocolError("invalid peer_error envelope/epoch")
    _integer(message["round"], "peer_error round")
    _integer(message["frame"], "peer_error frame")
    if (type(message["error_type"]) is not str
            or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", message["error_type"]) is None
            or type(message["detail"]) is not str or not 1 <= len(message["detail"]) <= PEER_ERROR_LIMIT
            or any(ord(char) < 32 or ord(char) == 127 for char in message["detail"])):
        raise ProtocolError("invalid peer_error diagnostic")
    return dict(message)


def manifest():
    source = Path(__file__).parent
    return digest({"backend": "contract-fixture-v1-not-tf2", "files": {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in ("core.py", "model.py", "replica.py", "runner.py", "transport.py")}})


def write_report(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)


async def host(args, secret, *, expected_manifest=None, capabilities=MODEL_CAPABILITIES,
               backend="contract_model_only", startup_timeout=None, progress=None,
               stop_requested=None, step_us=100000):
    # A manually loaded game may take minutes. Keep the protocol's ordinary
    # per-phase clock stopped until both initial worlds have joined.
    started = time.monotonic()
    running_started = None
    def protocol_clock():
        if startup_timeout is None:
            return time.monotonic()
        # Subtract first: (started + now) - origin can round below started
        # when a coarse monotonic clock returns origin again on the next read.
        return started if running_started is None else started + (time.monotonic() - running_started)
    coordinator = Coordinator(args.epoch, expected_manifest or manifest(), capabilities,
                              timeout_s=args.timeout, clock=protocol_clock, step_us=step_us)
    connections = {}
    used_peers = set()
    done = asyncio.Event()
    state_lock = asyncio.Lock()
    tasks = set()
    log = []
    peer_error = None

    def publish(state, reason=""):
        if progress:
            progress(state, reason=reason, round=coordinator.round, frame=coordinator.frame,
                     peers=sorted(connections), coordinated_completed=(state == "completed"),
                     completion_scope="both_engine_receipts" if state == "completed" else None)

    async def dispatch(actions):
        nonlocal running_started
        if done.is_set():
            return
        if coordinator.phase != "hello" and running_started is None:
            running_started = time.monotonic()
        if not coordinator.halted and coordinator.round >= args.rounds and coordinator.phase == "inputs":
            actions = [(peer, {"kind": "complete", "epoch": args.epoch,
                                "round": coordinator.round, "frame": coordinator.frame,
                                "sim_time_us": coordinator.sim_time_us,
                                "state_digest": coordinator.state_digest}) for peer in ("a", "b")]
        failures = []
        for peer, message in actions:
            log.append({"peer": peer, "kind": message["kind"],
                        "round": message.get("round"), "index": message.get("index"),
                        "elapsed_ms": int((time.monotonic() - started) * 1000)})
            writer = connections.get(peer)
            if writer:
                try:
                    await asyncio.wait_for(send(writer, message), timeout=args.timeout)
                except (OSError, asyncio.TimeoutError):
                    failures.append(peer)
        if failures and not coordinator.halted:
            await dispatch(coordinator.disconnect(failures[0], "send failed"))
        if coordinator.halted or (actions and actions[0][1]["kind"] == "complete"):
            done.set()
            publish("halted" if coordinator.halted else "completed", coordinator.halt_reason)
        else:
            publish("waiting_peer" if coordinator.phase == "hello" else "running")

    async def client(reader, writer):
        nonlocal peer_error
        task = asyncio.current_task()
        tasks.add(task)
        peer = None
        accepted = False
        try:
            peer = await asyncio.wait_for(authenticate_server(reader, writer, secret, args.epoch),
                                          timeout=min(args.timeout, 3.0))
            if peer in used_peers or done.is_set():
                raise ProtocolError("peer already joined; no reconnect")
            used_peers.add(peer)
            connections[peer] = writer
            accepted = True
            while not done.is_set():
                message = await receive(reader)
                async with state_lock:
                    if not done.is_set():
                        if message.get("kind") == "peer_error":
                            diagnostic = validate_peer_error(message, args.epoch)
                            peer_error = {"peer": peer, **diagnostic}
                            await dispatch(coordinator.disconnect(peer,
                                f"{diagnostic['error_type']}: {diagnostic['detail']}"))
                        else:
                            await dispatch(coordinator.receive(peer, message))
        except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError, ProtocolError) as exc:
            if accepted:
                async with state_lock:
                    if not done.is_set():
                        detail = str(exc)[:PEER_ERROR_LIMIT] if isinstance(exc, ProtocolError) else ""
                        await dispatch(coordinator.disconnect(peer,
                            f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__))
        finally:
            if accepted:
                connections.pop(peer, None)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            tasks.discard(task)

    server = await asyncio.start_server(client, args.bind, args.port, limit=65540, backlog=4)
    port = server.sockets[0].getsockname()[1]
    write_report(args.ready, {"port": port, "epoch": args.epoch, "backend": backend})
    publish("waiting_peer")

    async def watchdog():
        while not done.is_set():
            await asyncio.sleep(0.025)
            async with state_lock:
                if stop_requested and stop_requested():
                    await dispatch(coordinator.halt("measurement stopped by local user"))
                elif (startup_timeout is not None and coordinator.phase == "hello"
                      and time.monotonic() - started >= startup_timeout):
                    await dispatch(coordinator.halt("startup timeout waiting for both loaded worlds"))
                else:
                    await dispatch(coordinator.tick())

    watcher = asyncio.create_task(watchdog())
    try:
        await done.wait()
        # Every complete/halt was drained before done. No further engine permits.
        await asyncio.sleep(0.05)
    finally:
        server.close()
        await server.wait_closed()
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        remaining = list(tasks)
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
        write_report(args.report, {"backend": backend, "halted": coordinator.halted,
                                   "reason": coordinator.halt_reason, "round": coordinator.round,
                                   "peer_error": peer_error,
                                   "frame": coordinator.frame, "sim_time_us": coordinator.sim_time_us,
                                   "state_digest": coordinator.state_digest, "actions": log,
                                   "coordinated_completed": not coordinator.halted and done.is_set(),
                                   "completion_scope": "both_engine_receipts" if not coordinator.halted and done.is_set() else None})
    return 0 if not coordinator.halted else 2


async def peer(args, secret):
    engine = ModelEngine(100 if args.peer == "a" else 9000, fault=args.fault)
    if args.fault == "initial":
        engine.money -= 1
    inputs = scenario(args.peer)
    replica = Replica(args.peer, args.epoch, manifest(), MODEL_CAPABILITIES, engine,
                      lambda number: inputs.get(number, []))
    writer = None
    log = []
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(args.host, args.port), args.timeout)
        await asyncio.wait_for(authenticate_client(reader, writer, secret, args.epoch, args.peer), args.timeout)
        await send(writer, replica.hello(), fragment=args.fragment)
        while not replica.halted and not replica.finished:
            message = await asyncio.wait_for(receive(reader), args.timeout)
            before = engine.time_us
            if (message.get("kind") == "request_inputs" and message.get("round") == args.stop_round
                    and args.fault in ("disconnect", "stall")):
                if args.fault == "stall":
                    # Network still receives the host's halt; simulation never advances.
                    message = await asyncio.wait_for(receive(reader), args.timeout)
                else:
                    replica.halted, replica.reason = True, "injected disconnect"
                    break
            if args.delay_ms:
                await asyncio.sleep(args.delay_ms / 1000)
            response = replica.receive(message)
            log.append({"kind": message["kind"], "round": message.get("round"),
                        "time_before_us": before, "time_after_us": engine.time_us,
                        "state_digest": engine.state_digest})
            if response is not None:
                await send(writer, response, fragment=args.fragment)
                if args.duplicate:
                    await send(writer, response, fragment=args.fragment)
    except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError, ProtocolError) as exc:
        replica.halted, replica.reason = True, f"{type(exc).__name__}: {exc}"
    finally:
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        write_report(args.report, {"backend": "contract_model_only", "peer": args.peer,
                                   "finished": replica.finished, "halted": replica.halted,
                                   "reason": replica.reason, "round": replica.round, "frame": replica.frame,
                                   "state_digest": engine.state_digest, "world": engine.snapshot(),
                                   "physical_ids": engine.physical_ids,
                                   "operations": engine.operations, "actions": log})
    return 0 if replica.finished else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("host", "peer"))
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ready")
    parser.add_argument("--rounds", type=int, default=14)
    parser.add_argument("--peer", choices=("a", "b"))
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--fragment", type=int, default=0)
    parser.add_argument("--duplicate", action="store_true")
    parser.add_argument("--fault", choices=("", "initial", "money", "route", "disconnect", "stall"), default="")
    parser.add_argument("--stop-round", type=int, default=3)
    args = parser.parse_args()
    if not 0 < args.timeout <= 3600 or not 1 <= args.rounds <= 10000:
        parser.error("invalid timeout or round count")
    if not 0 <= args.port <= 65535 or not 0 <= args.delay_ms <= 10000 or not 0 <= args.fragment <= 65536:
        parser.error("invalid port, delay or fragment")
    if args.mode == "host" and not args.ready:
        parser.error("host requires --ready")
    if args.mode == "peer" and (not args.peer or not args.port):
        parser.error("peer requires --peer and --port")
    secret = args.key_file.read_bytes().strip()
    if not 32 <= len(secret) <= 128:
        parser.error("key file must contain 32..128 bytes")
    return asyncio.run(host(args, secret) if args.mode == "host" else peer(args, secret))


if __name__ == "__main__":
    raise SystemExit(main())
