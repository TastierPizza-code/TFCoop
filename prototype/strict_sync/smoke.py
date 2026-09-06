"""Run coordinator and two independent model replicas in hidden child processes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

from .runner import write_report


ROOT = Path(__file__).resolve().parents[2]


def run_case(directory: Path, name: str, options=(), expect_round=None):
    work = directory / name
    work.mkdir()
    key = work / "session.key"
    key.write_text(secrets.token_hex(32), encoding="ascii")
    epoch = secrets.token_hex(16)
    processes = []
    streams = []
    base = [sys.executable, "-m", "prototype.strict_sync.runner"]
    shared = ["--epoch", epoch, "--key-file", str(key)]

    def start(role, arguments):
        stream = (work / f"{role}.log").open("w", encoding="utf-8")
        streams.append(stream)
        process = subprocess.Popen(base + arguments + shared, cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        processes.append(process)
        return process

    try:
        ready = work / "ready.json"
        host = start("host", ["host", "--report", str(work / "host.json"), "--ready", str(ready),
                              "--timeout", "1.5"])
        deadline = time.monotonic() + 8
        port = None
        while time.monotonic() < deadline and host.poll() is None:
            try:
                port = json.loads(ready.read_text())["port"]
                break
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.02)
        if not port:
            raise AssertionError("coordinator did not become ready: " + (work / "host.log").read_text())
        start("a", ["peer", "--peer", "a", "--port", str(port), "--report", str(work / "a.json")])
        start("b", ["peer", "--peer", "b", "--port", str(port), "--report", str(work / "b.json"), *options])
        deadline = time.monotonic() + 25
        for process in processes:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        reports = {role: json.loads((work / f"{role}.json").read_text(encoding="utf-8"))
                   for role in ("host", "a", "b")}
        h, a, b = reports["host"], reports["a"], reports["b"]
        diagnostic = {role: {k: report.get(k) for k in ("halted", "reason", "round", "frame", "finished")}
                      for role, report in reports.items()}
        if expect_round is None:
            assert all(p.returncode == 0 for p in processes), diagnostic
            assert not h["halted"] and a["finished"] and b["finished"], reports
            assert h["round"] == a["round"] == b["round"] == 14, reports
            assert h["state_digest"] == a["state_digest"] == b["state_digest"], reports
            assert a["world"] == b["world"], reports
            assert a["physical_ids"] != b["physical_ids"], reports
            assert a["world"]["time_us"] == 800000, reports
            assert a["world"]["vehicles"]["seed:vehicle"]["line"] is None, reports
            assert a["world"]["vehicles"]["a:5"]["line"] == "a:3", reports
        else:
            assert h["halted"] and h["round"] == expect_round, reports
            assert not a["finished"] and not b["finished"], reports
            assert a["frame"] <= expect_round and b["frame"] <= expect_round, reports
            assert not any(x["kind"] == "step" and x["round"] >= expect_round for x in h["actions"]), reports
        return {"case": name, "passed": True, "round": h["round"], "halted": h["halted"],
                "reason": h["reason"], "state_digest": h["state_digest"]}
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        for stream in streams:
            stream.close()
        key.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="tf2-strict-probe-"))
    output.mkdir(parents=True, exist_ok=True)
    cases = [("baseline", (), None),
             ("delayed_fragmented_duplicates", ("--delay-ms", "60", "--fragment", "7", "--duplicate"), None),
             ("disconnect", ("--fault", "disconnect"), 3),
             ("missing_batch_timeout", ("--fault", "stall"), 3),
             ("money_divergence", ("--fault", "money"), 2),
             ("route_divergence", ("--fault", "route"), 3),
             ("different_initial_world", ("--fault", "initial"), 0)]
    if args.quick:
        cases = cases[:1]
    results = []
    for name, options, expect in cases:
        result = run_case(output, name, options, expect)
        results.append(result)
        print(json.dumps(result), flush=True)
    report = {"backend": "contract_model_only", "game_started": False,
              "cases": results, "passed": all(r["passed"] for r in results)}
    write_report(output / "summary.json", report)
    print(str(output / "summary.json"), flush=True)


if __name__ == "__main__":
    main()
