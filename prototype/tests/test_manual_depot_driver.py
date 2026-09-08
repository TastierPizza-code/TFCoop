"""Actual TCP/queue/driver flow with explicit engine models, never a TF2 run."""
import argparse
import asyncio
import copy
import json
import io
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from prototype.strict_sync import game_runner as driver, live_input, manual_depot_probe, runner
from prototype.strict_sync import stream_engine as stream_backend
from prototype.strict_sync.core import ProtocolError, digest
from prototype.strict_sync.manual_depot_input import validate_command
from prototype.tests.test_manual_depot_probe import depot
from prototype.strict_sync.short_build_profile import SHORT_BUILD_CONTRACT
from prototype.strict_sync.coalesced_progress import CoalescedProgress
from prototype.tests.test_engine_mailbox import native_bytes
from prototype.tests.test_live_driver import LiveEngineFixture, ModelClock
from prototype.tests.test_stream_driver import CachedBuildEngineFixture


class ManualDepotDriverTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, choose_inputs, *, fault="", duplicate_checkpoint=False, hold_final=False):
        asyncio.get_running_loop().set_debug(False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            epoch = "paced-live-driver-model"
            runs, sessions, inputs, queues = {}, {}, {}, {}
            for peer in ("a", "b"):
                runs[peer] = root / peer
                sessions[peer] = runs[peer] / "session"
                sessions[peer].mkdir(parents=True)
                for name in driver.PREPARED_FILES:
                    (sessions[peer] / name).write_text("explicit short preparation fixture")
                inputs[peer] = runs[peer] / "live-input.json"
                live_input.create(inputs[peer], epoch, peer)
                queues[peer] = live_input.InputWriter(inputs[peer], epoch, peer, command_validator=validate_command)
            fields = dict(epoch=epoch, timeout=15, rounds=10, profile="build_v2", delay_ms=0,
                          paced_live_probe=False, manual_depot_probe=True, live_probe=False, timing_probe=False, stream_probe=False)
            host_args = argparse.Namespace(**fields, bind="127.0.0.1", port=0,
                ready=runs["a"] / "host-ready.json", report=runs["a"] / "host-report.json")
            secret = b"paced-live-fixture-secret-32-bytes"
            stop = threading.Event()
            context = {"clock": ModelClock(), "queues": queues, "inputs": inputs,
                       "engines": {}, "wrappers": {}, "state": {}, "actions": [],
                       "final_waiting": threading.Event(), "release_final": threading.Event(),
                       "finish_armed": False}
            if not hold_final:
                context["release_final"].set()

            class ObservedCoordinator(manual_depot_probe.ManualDepotCoordinator):
                def receive(self, peer, message):
                    actions = super().receive(peer, message)
                    context["actions"].extend(copy.deepcopy(actions))
                    choose_inputs(self, actions, context)
                    if any(message["kind"] == "live_finish" for _, message in actions):
                        context["finish_armed"] = True
                    return actions

            class ClockedReplica(manual_depot_probe.ManualDepotReplica):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._pause_clock = lambda: 100.0 + context["clock"].pause_ms[self.peer] / 1000

            class Wrapper(LiveEngineFixture):
                def preview(self, command, key):
                    self.check_stop()
                    if not self.observations_fresh:
                        raise ProtocolError("preview before fresh model world")
                    site = command["site"]
                    allowed = str(site) not in self.engine.world["manual_depots"]
                    cost = 1000 + site if allowed else None
                    if fault == "divergent_preview" and self.engine.peer == "b" and allowed:
                        cost += 1
                    return {"allowed": allowed, "reason": "" if allowed else "site_occupied", "cost": cost,
                            "position_mm": [site * 100000, 100000, 10000], "rotation": command["rotation"],
                            "proposal_digest": digest(command), "state_digest": self.engine.state_digest}

                def apply_manual(self, command, key, preview):
                    self.check_stop()
                    if fault == "failed_callback" and self.engine.peer == "b":
                        raise ProtocolError("explicit model failed depot callback")
                    if not preview["allowed"] or self.preview(command, key) != preview:
                        raise ProtocolError("depot preview changed before model apply")
                    before = self.engine.world["company"]["balance"]
                    self.engine.world["company"]["balance"] -= preview["cost"]
                    self.engine.world["manual_depots"][str(command["site"])] = key
                    self.engine.world["objects"].append({"kind": "manual_depot", "logical_id": key,
                        "state": {"position_mm": preview["position_mm"], "rotation": command["rotation"]}})
                    self.engine.command_calls.append((self.frame, key, copy.deepcopy(command)))
                    self.engine.observe()
                    loan = self.engine.world["company"]["loan"]
                    return {"success": True, "state_digest": self.engine.state_digest,
                            "result": {**command, "logical_id": key, "cost": preview["cost"],
                                "balance_before": before, "balance_after": self.engine.world["company"]["balance"],
                                "loan_before": loan, "loan_after": loan, "position_mm": preview["position_mm"]}}

                def checkpoint(self):
                    if fault == "divergent_checkpoint" and self.engine.peer == "b" and self.frame == 60:
                        self.engine.world["company"]["balance"] += 1
                    return super().checkpoint()

            def coordinator_factory(*args, **kwargs):
                kwargs["clock"] = context["clock"].monotonic
                return ObservedCoordinator(*args, **kwargs)

            def make_engine(directory, *_args, **_kwargs):
                peer = Path(directory).parent.name
                value = CachedBuildEngineFixture(peer)
                value.missing_debit = fault == "missing_debit"
                value.world["manual_depots"] = {}
                value.observe()
                context["engines"][peer] = value
                return value

            def make_stream(engine, stop_requested=None):
                value = Wrapper(engine, stop_requested, context=context,
                                fault=fault if engine.peer == "b" else "")
                context["wrappers"][engine.peer] = value
                return value

            def lease_start(_exe, directory, **_kwargs):
                (directory / "native_status.txt").write_bytes(native_bytes(epoch=7, outer_calls=1))
                (directory / "lua_status.json").write_text(json.dumps({"protocol": 1, "epoch": "7",
                    "request": 0, "revision": 1, "status": "ready", "complete": True, "snapshot": {}}))
                return Mock()

            cached, duplicated = {}, set()
            real_send = runner.send
            async def observed_send(writer, message):
                if duplicate_checkpoint and message.get("kind") == "live_checkpoint":
                    cached.setdefault(id(writer), copy.deepcopy(message))
                await real_send(writer, message)
                if (duplicate_checkpoint and message.get("kind") == "live_advance"
                        and id(writer) in cached and id(writer) not in duplicated):
                    await real_send(writer, cached[id(writer)])
                    duplicated.add(id(writer))

            async def wait_for(predicate):
                deadline = asyncio.get_running_loop().time() + 30
                while not predicate():
                    if host.done():
                        result = json.loads(host_args.report.read_text())
                        self.fail("host ended before fixture condition: " + result.get("reason", ""))
                    if asyncio.get_running_loop().time() >= deadline:
                        self.fail("fixture condition timed out")
                    await asyncio.sleep(.005)

            host = asyncio.create_task(driver.host(host_args, secret, expected_manifest="a" * 64,
                capabilities=driver.measurement_capabilities(host_args), backend="explicit_model_only",
                startup_timeout=10, stop_requested=stop.is_set, step_us=200000,
                coordinator_factory=coordinator_factory))
            tasks = []
            try:
                await wait_for(host_args.ready.exists)
                port = json.loads(host_args.ready.read_text())["port"]
                with patch.object(driver, "ControllerGuard"), patch.object(driver, "game_is_running", return_value=False), \
                     patch.object(driver, "verify_payload"), patch.object(driver.LaunchLease, "create", side_effect=lease_start), \
                     patch.object(driver, "ManualDepotEngineAdapter", side_effect=make_engine), \
                     patch.object(driver, "ManualDepotReplica", ClockedReplica), \
                     patch.object(driver, "ManualDepotStreamEngine", side_effect=make_stream), \
                     patch.object(runner, "send", side_effect=observed_send), patch.object(driver.os, "fsync"):
                    for peer in ("a", "b"):
                        args = argparse.Namespace(**fields, peer=peer, inputs=None, live_input_file=inputs[peer],
                            host="127.0.0.1", port=port, startup_timeout=10, report=runs[peer] / "peer-report.json",
                            progress=runs[peer] / "peer-progress.json", stop_file=runs[peer] / "stop")
                        setup = {"game_exe": str(root / "fixture-game.exe"), "native_epoch": 7,
                                 "manifest_digest": "a" * 64, "measurement_profile": "build_v2",
                                 "measurement_preparation": SHORT_BUILD_CONTRACT, "measurement_input_mode": "manual_depot_v1"}
                        tasks.append(asyncio.create_task(driver.game_peer(args, secret, sessions[peer], setup)))
                    if hold_final:
                        await wait_for(context["final_waiting"].is_set)
                        self.assertFalse(host.done())
                        self.assertFalse(host_args.report.exists())
                        self.assertFalse(any((run / "peer-report.json").exists() for run in runs.values()))
                        context["release_final"].set()
                    codes = await asyncio.wait_for(asyncio.gather(*tasks), 45)
                    host_code = await asyncio.wait_for(host, 10)
            finally:
                context["release_final"].set()
                stop.set()
                for run in runs.values():
                    (run / "stop").write_text("fixture cleanup")
                pending = [task for task in [*tasks, host] if not task.done()]
                if pending:
                    _, unfinished = await asyncio.wait(pending, timeout=10)
                    for task in unfinished:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
            reports = {peer: json.loads((runs[peer] / "peer-report.json").read_text()) for peer in runs}
            journals = {peer: [json.loads(row) for row in (runs[peer] / "peer-journal.jsonl")
                              .read_text(encoding="utf-8").splitlines()] for peer in runs}
            context["duplicates"] = duplicated
            return codes, host_code, json.loads(host_args.report.read_text()), reports, journals, context

    @staticmethod
    def action(actions, kind):
        return next((item for _, item in actions if item["kind"] == kind), None)

    async def test_real_queues_tcp_callbacks_conflict_and_joint_final(self):
        def choose(_coordinator, actions, context):
            state, queues = context["state"], context["queues"]
            phase = state.get("phase", 0)
            advance, hold = self.action(actions, "live_advance"), self.action(actions, "live_hold")
            if phase == 0 and advance:
                queues["a"].submit(depot(1))
                state["phase"] = 1
            elif phase == 1 and advance:
                queues["b"].submit({"op": "SET_PAUSED", "value": True})
                state["phase"] = 2
            elif phase == 2 and hold:
                queues["b"].submit(depot(2, 90))
                state["phase"] = 3
            elif phase == 3 and hold:
                queues["b"].submit(depot(3, 180))
                queues["a"].submit(depot(3))
                state["phase"] = 4
            elif phase == 4 and hold:
                queues["a"].submit({"op": "SET_PAUSED", "value": False})
                state["phase"] = 5
            elif phase == 5 and advance:
                queues["b"].submit({"op": "END_TEST"})
                state["phase"] = 6
        codes, host_code, host, reports, journals, context = await self.run_fixture(choose, hold_final=True)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertTrue(host["coordinated_completed"])
        self.assertTrue(host["live"]["required_depot_interactions_met"])
        self.assertEqual(host["live"]["depot_coverage"]["occupied_site_rejections"], 1)
        self.assertEqual(len(host["live"]["depot_coverage"]["same_batch_shared_sites"]), 1)
        self.assertEqual(journals["a"], journals["b"])
        self.assertEqual(host["live"]["depot_records"], reports["a"]["live"]["depot_records"])
        self.assertEqual(host["live"]["depot_records"], reports["b"]["live"]["depot_records"])
        self.assertTrue(all(report["short_preparation"]["passed"] for report in reports.values()))
        self.assertTrue(all(report["build_proof"] is None for report in reports.values()))
        self.assertTrue(all(context["engines"][peer].closed for peer in reports))
        self.assertFalse(any(message["kind"] == "live_poll" for _, message in context["actions"]))
        self.assertEqual([row["event"] for row in journals["a"]].count("live_previewed"), 4)
        self.assertEqual([row["event"] for row in journals["a"]].count("live_rejected"), 1)
        for record in host["live"]["depot_records"]:
            before, after = record["before"], record["after"]
            self.assertEqual(before["frame"], after["frame"])
            self.assertEqual(before["sim_time_us"], after["sim_time_us"])
            self.assertEqual(before["paused"], after["paused"])
            if record["receipt"] is None:
                self.assertEqual(before, after)

    async def test_failed_or_different_engine_result_is_terminal_in_tcp_driver(self):
        for fault in ("divergent_preview", "failed_callback"):
            with self.subTest(fault=fault):
                def choose(_coordinator, actions, context):
                    if self.action(actions, "live_start"):
                        context["queues"]["a"].submit(depot(1))
                codes, host_code, host, reports, journals, context = await self.run_fixture(choose, fault=fault)
                self.assertEqual((codes, host_code), ([2, 2], 2))
                self.assertFalse(host["coordinated_completed"])
                self.assertEqual(host["frame"], 10)
                self.assertFalse(any(message["kind"] == "live_advance" for _, message in context["actions"]))
                self.assertTrue(all(context["engines"][peer].closed for peer in reports))
                self.assertTrue(all(report["short_preparation"]["passed"] for report in reports.values()))
                if fault == "divergent_preview":
                    self.assertTrue(all(not engine.world["manual_depots"] for engine in context["engines"].values()))


if __name__ == "__main__":
    unittest.main()

