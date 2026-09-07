"""Bounded sequential single-engine recording/replay; never starts or installs TF2.

The caller owns the process/lease and verifies startup and the installed payload.
An injected adapter is a test seam, never a fallback for an unavailable game.
Matching observations cover the build recipe, not the complete world or a network.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

from .build_profile import BUILD_PROFILE, BUILD_ROUNDS, BuildProof, build_inputs
from .core import MAX_MESSAGE_BYTES, ROSTER, ProtocolError, canonical_json, decode_message, digest
from .engine_mailbox import ENGINE_STEP_US, LUA_LIMIT, EngineAdapter, _epoch, _json_bytes, _shared_read


SCOPE = "sequential_real_engine_replay"
LINE_LIMIT = 524288
JOURNAL_LIMIT = 80 * 1024 * 1024
RECORD_LIMIT = 520
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ZERO = "0" * 64


class ReplayError(ProtocolError):
    pass


def _require(condition, reason):
    if not condition:
        raise ReplayError(reason)


def _same(left, right):
    # Plain Python equality would incorrectly equate true with 1.
    return _json_bytes(left, limit=LINE_LIMIT) == _json_bytes(right, limit=LINE_LIMIT)


def _hash_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _document(path):
    raw = _shared_read(Path(path), MAX_MESSAGE_BYTES)
    return decode_message(raw)


def _identity(session, epoch, baseline):
    setup = _document(session / "probe_setup.json")
    manifest = _document(session / "probe_manifest.json")
    _require(setup.get("protocol") == 1 and type(setup.get("protocol")) is int,
             "invalid prepared session protocol")
    _require(_epoch(setup.get("native_epoch")) == epoch, "prepared native epoch mismatch")
    _require(digest(manifest) == setup.get("manifest_digest"), "prepared manifest digest mismatch")
    _require(manifest.get("protocol") == 1 and type(manifest.get("protocol")) is int
             and manifest.get("backend") == "tf2_controlled_measurement"
             and manifest.get("complete_world_verified") is False,
             "invalid controlled measurement manifest")
    _require(manifest.get("config_semantics", {}).get("profile") == BUILD_PROFILE,
             "local replay requires the staged build_v2 profile")
    expected = manifest.get("save")
    _require(type(expected) is dict and set(expected) == {"sav_sha256", "sav_lua_sha256"}
             and all(type(v) is str and _HEX.fullmatch(v) for v in expected.values()),
             "prepared baseline hashes unavailable")
    baseline = Path(baseline)
    _require(baseline.suffix.lower() == ".sav", "baseline must identify the freshly loaded .sav")
    actual = {"sav_sha256": _hash_file(baseline),
              "sav_lua_sha256": _hash_file(Path(str(baseline) + ".lua"))}
    _require(actual == expected, "fresh baseline files differ from the prepared manifest")
    return {"manifest": manifest, "manifest_digest": digest(manifest), "baseline": actual}


def _commands(number, sequences):
    # Exactly Coordinator._on_inputs order: roster first, then each origin's seq.
    for origin in ROSTER:
        for command in build_inputs(origin, number):
            sequences[origin] += 1
            yield {"origin": origin, "seq": sequences[origin],
                   "command_key": f"{origin}:{sequences[origin]}", "command": command}


def _state(snapshot, frame):
    _require(type(frame) is int and 0 <= frame <= BUILD_ROUNDS, "invalid observed frame")
    _require(type(snapshot) is dict and type(snapshot.get("sim_time_us")) is int
             and snapshot["sim_time_us"] >= 0 and type(snapshot.get("paused")) is bool,
             "invalid actual snapshot time/pause")
    raw = _json_bytes(snapshot, limit=LUA_LIMIT)
    coverage = snapshot.get("coverage")
    _require(type(coverage) is dict and type(coverage.get("complete_world")) is bool
             and coverage.get("tracked_objects") is True and coverage.get("missing") == [],
             "actual tracked snapshot coverage is incomplete")
    objects = snapshot.get("objects")
    _require(type(objects) is list, "actual tracked object states missing")
    keys = []
    for obj in objects:
        _require(type(obj) is dict and type(obj.get("logical_id")) is str and obj["logical_id"]
                 and type(obj.get("kind")) is str and obj["kind"] and type(obj.get("state")) is dict,
                 "invalid actual tracked object")
        keys.append(obj["logical_id"])
    _require(keys == sorted(set(keys)), "actual tracked objects must have sorted unique identities")
    return {"frame": frame, "sim_time_us": snapshot["sim_time_us"], "paused": snapshot["paused"],
            "state_digest": hashlib.sha256(raw).hexdigest(), "snapshot": copy.deepcopy(snapshot)}


def _observed(engine):
    value = _state(engine.snapshot(), engine.frame)
    _require(value["state_digest"] == engine.state_digest and value["sim_time_us"] == engine.time_us
             and value["paused"] is engine.paused, "adapter properties disagree with actual snapshot")
    return value


def _request(action, number, previous, **fields):
    return {"event": "request", "action": action, "round": number, "frame": previous["frame"],
            "sim_time_us": previous["sim_time_us"], "paused": previous["paused"],
            "pre_state_digest": previous["state_digest"], **fields}


def _validate_result(request, previous, receipt, after):
    _require(type(receipt) is dict, "engine receipt is not an object")
    canonical_json(receipt)
    _require(receipt.get("state_digest") == after["state_digest"], "receipt state digest mismatch")
    if request["action"] == "apply":
        _require(set(receipt) == {"success", "result", "state_digest"}
                 and type(receipt.get("success")) is bool and type(receipt.get("result")) is dict,
                 "invalid engine apply receipt")
        _require(receipt["success"] is True, "engine command rejected")
        _require(after["frame"] == previous["frame"] and after["sim_time_us"] == previous["sim_time_us"],
                 "engine command advanced frame or simulation time")
        command = request["command"]
        pause = command["value"] if command["op"] == "SET_PAUSED" else previous["paused"]
        _require(after["paused"] is pause, "engine command changed pause without authorization")
    else:
        _require(set(receipt) == {"state_digest", "sim_time_us"}
                 and type(receipt.get("sim_time_us")) is int
                 and receipt["sim_time_us"] == after["sim_time_us"], "invalid engine step receipt")
        _require(after["frame"] == previous["frame"] + 1
                 and after["sim_time_us"] == previous["sim_time_us"] + request["dt_us"]
                 and after["paused"] is previous["paused"], "engine violated step boundary")
        _require(request["dt_us"] != 0 or after["state_digest"] == previous["state_digest"],
                 "paused engine step changed the observed world")


def _proof_observe(proof, observed, request=None):
    applied = request is not None and request["action"] == "apply"
    proof.observe(observed["snapshot"], frame=observed["frame"],
                  command=request["command"] if applied else None,
                  command_key=request["command_key"] if applied else None)


class _Journal:
    def __init__(self, path):
        self.stream = path.open("xb")
        self.size, self.count, self.previous = 0, 0, _ZERO

    def append(self, record):
        body = {"index": self.count, "previous": self.previous, "record": record}
        sha = hashlib.sha256(_json_bytes(body, limit=LINE_LIMIT)).hexdigest()
        raw = _json_bytes({**body, "digest": sha}, limit=LINE_LIMIT) + b"\n"
        _require(self.count < RECORD_LIMIT and self.size + len(raw) <= JOURNAL_LIMIT,
                 "local replay journal limit exceeded")
        self.stream.write(raw)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.size, self.count, self.previous = self.size + len(raw), self.count + 1, sha

    def close(self):
        self.stream.close()


def _decode_line(raw):
    def pairs(items):
        value = {}
        for key, child in items:
            _require(key not in value, "duplicate replay JSON key")
            value[key] = child
        return value
    def bad_number(_):
        raise ReplayError("replay JSON requires integer or decimal-string numbers")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=bad_number, parse_float=bad_number)
        _require(type(value) is dict and _json_bytes(value, limit=LINE_LIMIT) + b"\n" == raw,
                 "replay line is not complete canonical JSON")
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReplayError("invalid or truncated replay JSON") from exc


def _read_records(source):
    path = Path(source)
    if path.is_dir():
        path = path / "journal.jsonl"
    values, previous, size, source_hash = [], _ZERO, 0, hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            raw = stream.readline(LINE_LIMIT + 2)
            if not raw:
                break
            size += len(raw)
            _require(len(raw) <= LINE_LIMIT + 1 and size <= JOURNAL_LIMIT and len(values) < RECORD_LIMIT,
                     "replay journal limit exceeded")
            source_hash.update(raw)
            envelope = _decode_line(raw)
            _require(set(envelope) == {"index", "previous", "record", "digest"}
                     and type(envelope["index"]) is int and envelope["index"] == len(values)
                     and envelope["previous"] == previous, "replay journal ordering/hash chain mismatch")
            body = {k: envelope[k] for k in ("index", "previous", "record")}
            _require(hashlib.sha256(_json_bytes(body, limit=LINE_LIMIT)).hexdigest() == envelope["digest"],
                     "replay journal digest mismatch")
            _require(type(envelope["record"]) is dict, "replay record must be an object")
            values.append(envelope["record"])
            previous = envelope["digest"]
    _require(len(values) >= 3, "replay requires a complete successful recording")
    return values, source_hash.hexdigest()


def _validate_recording(records, identity, epoch):
    header = records[0]
    expected = {"event": "header", "format": 1, "profile": BUILD_PROFILE, "scope": SCOPE,
                "live_network_tested": False, "complete_world_verified": False, "mode": "record",
                "rounds": BUILD_ROUNDS, "step_us": ENGINE_STEP_US, **identity}
    _require(set(header) == set(expected) | {"epoch"}, "invalid recording header fields")
    _require(_same(header, {**expected, "epoch": header["epoch"]}), "recorded manifest/baseline/profile mismatch")
    _require(_epoch(header["epoch"]) != epoch, "replay requires a fresh native epoch")
    initial = records[1]
    _require(type(initial.get("snapshot")) is dict, "recorded initial snapshot missing")
    previous = _state(initial["snapshot"], 0)
    _require(_same(initial, {"event": "start", "round": 0, **previous}), "invalid recorded initial boundary")
    proof = BuildProof()
    _proof_observe(proof, previous)
    sequences, cursor, actions = dict.fromkeys(ROSTER, 0), 2, []
    for number in range(BUILD_ROUNDS):
        commands = list(_commands(number, sequences))
        for fields in [*commands, None]:
            request = (_request("apply", number, previous, **fields) if fields is not None else
                       _request("step", number, previous, dt_us=0 if previous["paused"] else ENGINE_STEP_US))
            _require(cursor + 1 < len(records), "recording is incomplete before a required action")
            _require(_same(records[cursor], request), "recorded command stream differs from canonical build_v2 order")
            result = records[cursor + 1]
            observed = _state(result.get("snapshot"), request["frame"] + (fields is None))
            expected_result = {"event": "applied" if fields is not None else "stepped", "round": number,
                               "receipt": result.get("receipt"), **observed}
            _require(_same(result, expected_result), "invalid recorded action result fields")
            _validate_result(request, previous, result["receipt"], observed)
            _proof_observe(proof, observed, request)
            actions.append((copy.deepcopy(request), copy.deepcopy(result)))
            previous, cursor = observed, cursor + 2
    final = {"event": "completed", "frame": BUILD_ROUNDS,
             "proof": proof.finish(frame=BUILD_ROUNDS, step_us=ENGINE_STEP_US)}
    _require(cursor == len(records) - 1 and _same(records[cursor], final),
             "recording has no valid final build proof or has trailing records")
    return previous, actions


def run_local_replay(session, epoch, output, *, baseline, replay=None, engine_factory=EngineAdapter,
                     stop_requested=None, timeout_s=60.0, max_duration_s=900.0):
    """Run one fresh engine after caller startup; return a durable bounded verdict.

    ``replay`` reads a completed record directory or its journal.jsonl. Its entire
    command stream, hash chain, baseline and BuildProof are validated before the
    adapter is constructed. Both modes close the adapter on every exit. Creation
    of an existing output directory is refused rather than overwriting evidence.
    """
    _require(all(type(v) in (int, float) and math.isfinite(v) and 0 < v <= limit
                 for v, limit in ((timeout_s, 60), (max_duration_s, 3600))), "invalid bounded runner timeout")
    session, output, epoch = Path(session).resolve(), Path(output).absolute(), _epoch(epoch)
    _require(session.is_dir(), "prepared session directory missing")
    _require(output != session and session not in output.parents, "output must be outside the mailbox session")
    output.mkdir(parents=True, exist_ok=False)
    journal = _Journal(output / "journal.jsonl")
    engine, previous, proof_result, source_sha = None, None, None, None
    failure, cleanup_failure, request = "", "", None
    completed_actions, completed_rounds, completed_commands = 0, 0, 0
    started = time.monotonic()
    mode = "replay" if replay is not None else "record"
    proof = BuildProof()
    def check_stop():
        _require(not stop_requested or not stop_requested(), "local measurement stopped by caller")
        _require(time.monotonic() - started <= max_duration_s, "local measurement exceeded total deadline")
    try:
        check_stop()
        identity = _identity(session, epoch, baseline)
        golden, actions = None, None
        if replay is not None:
            golden, source_sha = _read_records(replay)
            _, actions = _validate_recording(golden, identity, epoch)
        journal.append({"event": "header", "format": 1, "profile": BUILD_PROFILE, "scope": SCOPE,
                        "live_network_tested": False, "complete_world_verified": False, "mode": mode,
                        "rounds": BUILD_ROUNDS, "step_us": ENGINE_STEP_US, "epoch": epoch, **identity})
        check_stop()
        engine = engine_factory(session, epoch, probe_only=True, timeout_s=timeout_s)
        candidate = _observed(engine)
        _require(candidate["frame"] == 0, "local measurement requires a freshly loaded initial frame zero")
        initial = {"event": "start", "round": 0, **candidate}
        journal.append(initial)
        if golden is not None:
            _require(_same(initial, golden[1]), "replay initial actual snapshot differs from recorded baseline")
        previous = candidate
        _proof_observe(proof, previous)
        sequences, action_index = dict.fromkeys(ROSTER, 0), 0
        for number in range(BUILD_ROUNDS):
            commands = list(_commands(number, sequences)) if actions is None else None
            while True:
                check_stop()
                if actions is None:
                    fields = commands.pop(0) if commands else None
                    request = (_request("apply", number, previous, **fields) if fields is not None else
                               _request("step", number, previous, dt_us=0 if previous["paused"] else ENGINE_STEP_US))
                else:
                    # Execute the recorded payload itself, never regenerated inputs.
                    request = copy.deepcopy(actions[action_index][0])
                journal.append(request)
                applied = request["action"] == "apply"
                receipt = (engine.apply(copy.deepcopy(request["command"]), request["command_key"]) if applied else
                           engine.step(request["dt_us"]))
                after = _observed(engine)
                result = {"event": "applied" if applied else "stepped", "round": number,
                          "receipt": copy.deepcopy(receipt), **after}
                journal.append(result)
                _validate_result(request, previous, receipt, after)
                if actions is not None:
                    _require(_same(result, actions[action_index][1]),
                             f"replay actual result/snapshot mismatch at round {number} {request['action']}")
                _proof_observe(proof, after, request)
                previous = after
                completed_actions += 1
                completed_commands += applied
                action_index += 1
                if not applied:
                    completed_rounds += 1
                    break
        proof_result = proof.finish(frame=previous["frame"], step_us=ENGINE_STEP_US)
        journal.append({"event": "completed", "frame": previous["frame"], "proof": proof_result})
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"[:2048]
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception as exc:
                cleanup_failure = f"{type(exc).__name__}: {exc}"[:1024]
                failure = failure or "engine close failed: " + cleanup_failure
        if failure:
            try:
                journal.append({"event": "failed", "reason": failure, "last_request": request,
                                "last_observation_scope": "historical_verified_boundary",
                                "last_observation": previous})
            except Exception as exc:
                cleanup_failure = cleanup_failure or f"failure journal write: {exc}"[:1024]
        try:
            journal.close()
        except Exception as exc:
            cleanup_failure = cleanup_failure or f"journal close: {exc}"[:1024]
            failure = failure or cleanup_failure
    verdict = {"format": 1, "scope": SCOPE, "mode": mode, "profile": BUILD_PROFILE,
               "live_network_tested": False, "complete_world_verified": False,
               "passed": not failure, "record_complete": not failure and mode == "record",
               "replay_match": not failure and mode == "replay", "reason": failure,
               "cleanup_failure": cleanup_failure, "completed_actions": completed_actions,
               "completed_commands": completed_commands, "completed_rounds": completed_rounds,
               "last_request": request if failure else None,
               "last_verified_frame": previous["frame"] if previous else None,
               "last_verified_sim_time_us": previous["sim_time_us"] if previous else None,
               "source_journal_sha256": source_sha, "journal_sha256": _hash_file(output / "journal.jsonl"),
               "proof": proof_result}
    with (output / "verdict.json").open("xb") as stream:
        stream.write(_json_bytes(verdict, limit=LINE_LIMIT) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return verdict


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--record", action="store_true")
    modes.add_argument("--replay", type=Path)
    args = parser.parse_args(argv)
    try:
        verdict = run_local_replay(args.session, args.epoch, args.output,
                                   baseline=args.baseline, replay=args.replay)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Local measurement refused: {exc}\n")
    print(json.dumps({key: verdict[key] for key in ("mode", "passed", "reason", "completed_rounds")},
                     ensure_ascii=False))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
