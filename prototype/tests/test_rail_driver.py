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

from prototype.strict_sync import game_runner as driver, live_input, rail_probe, runner
from prototype.strict_sync import stream_engine as stream_backend
from prototype.strict_sync.core import ProtocolError, digest
from prototype.strict_sync.rail_input import validate_command
from prototype.strict_sync.rail_catalog import STEPS, get_step
from prototype.strict_sync.short_build_profile import SHORT_BUILD_CONTRACT
from prototype.strict_sync.coalesced_progress import CoalescedProgress
from prototype.tests.test_engine_mailbox import native_bytes
from prototype.tests.test_live_driver import LiveEngineFixture, ModelClock
from prototype.tests.test_stream_driver import CachedBuildEngineFixture


class RailDriverTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, choose_inputs, *, fault="", duplicate_checkpoint=False, hold_final=False):
        asyncio.get_running_loop().set_debug(False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            epoch = "rail-lifecycle-driver-model"
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
                          paced_live_probe=False, rail_probe=True, manual_depot_probe=False, live_probe=False, timing_probe=False, stream_probe=False)
            host_args = argparse.Namespace(**fields, bind="127.0.0.1", port=0,
                ready=runs["a"] / "host-ready.json", report=runs["a"] / "host-report.json")
            secret = b"guided-fixture-secret-32-bytes!!!"
            stop = threading.Event()
            context = {"clock": ModelClock(), "queues": queues, "inputs": inputs,
                       "engines": {}, "wrappers": {}, "state": {}, "actions": [],
                       "final_waiting": threading.Event(), "release_final": threading.Event(),
                       "finish_armed": False}
            if not hold_final:
                context["release_final"].set()

            class ObservedCoordinator(rail_probe.RailCoordinator):
                def receive(self, peer, message):
                    actions = super().receive(peer, message)
                    context["actions"].extend(copy.deepcopy(actions))
                    choose_inputs(self, actions, context)
                    if any(message["kind"] == "live_finish" for _, message in actions):
                        context["finish_armed"] = True
                    return actions

            class ClockedReplica(rail_probe.RailReplica):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._pause_clock = lambda: 100.0 + context["clock"].pause_ms[self.peer] / 1000

            class Wrapper(LiveEngineFixture):
                def preview_guided(self, command, key):
                    self.check_stop()
                    if not self.observations_fresh:
                        raise ProtocolError("guided preview before fresh model world")
                    step = get_step(command["step"])
                    observation = {"company": copy.deepcopy(self.engine.world["company"]),
                                   "expected": {"model_action": step["action"],
                                                "required_effect": step["action"]}}
                    if fault == "divergent_preview" and self.engine.peer == "b":
                        observation["expected"]["model_action"] = "different"
                    return {"allowed": True, "reason": "", "step": step["step"], "action": step["action"],
                            "state_digest": self.engine.state_digest, "observation": observation}

                def apply_guided(self, command, key, preview):
                    self.check_stop()
                    if fault == "failed_callback" and self.engine.peer == "b":
                        raise ProtocolError("explicit model failed guided callback")
                    if not preview["allowed"] or self.preview_guided(command, key) != preview:
                        raise ProtocolError("guided preview changed before model apply")
                    step = get_step(command["step"])
                    before = self.engine.world["company"]["balance"]
                    if not step["read_only"]:
                        self.engine.world["guided_last_action"] = step["action"]
                    if "pause" in step:
                        self.engine.world["paused"] = step["pause"]
                    if step["finance"] == "debit":
                        self.engine.world["company"]["balance"] -= 10000
                    if step["finance"] == "credit":
                        self.engine.world["company"]["balance"] += 5000
                    self.engine.command_calls.append((self.frame, key, copy.deepcopy(command)))
                    self.engine.observe()
                    loan = self.engine.world["company"]["loan"]
                    return {"success": True, "state_digest": self.engine.state_digest,
                            "result": {"op": "RAIL_ACTION", "step": step["step"], "action": step["action"],
                                "command_key": key, "effect": {"balance_before": before,
                                    "balance_after": self.engine.world["company"]["balance"],
                                    "loan_before": loan, "loan_after": loan,
                                    "observed": {"model_action": step["action"]},
                                    "kind": "observation" if step["read_only"] else "callback",
                                    "target": "model-target", "created": [], "removed": []}}}

            def coordinator_factory(*args, **kwargs):
                kwargs["clock"] = context["clock"].monotonic
                return ObservedCoordinator(*args, **kwargs)

            def make_engine(directory, *_args, **_kwargs):
                peer = Path(directory).parent.name
                value = CachedBuildEngineFixture(peer)
                value.missing_debit = fault == "missing_debit"
                value.world["guideds"] = {}
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
                     patch.object(driver, "RailEngineAdapter", side_effect=make_engine), \
                     patch.object(driver, "RailReplica", ClockedReplica), \
                     patch.object(driver, "RailStreamEngine", side_effect=make_stream), \
                     patch.object(runner, "send", side_effect=observed_send), patch.object(driver.os, "fsync"):
                    for peer in ("a", "b"):
                        args = argparse.Namespace(**fields, peer=peer, inputs=None, live_input_file=inputs[peer],
                            host="127.0.0.1", port=port, startup_timeout=10, report=runs[peer] / "peer-report.json",
                            progress=runs[peer] / "peer-progress.json", stop_file=runs[peer] / "stop")
                        setup = {"game_exe": str(root / "fixture-game.exe"), "native_epoch": 7,
                                 "manifest_digest": "a" * 64, "measurement_profile": "build_v2",
                                 "measurement_preparation": SHORT_BUILD_CONTRACT, "measurement_input_mode": "guided_rail_v1"}
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

    @staticmethod
    def choose_next(coordinator, actions, context):
        if not any(message["kind"] in ("live_advance", "live_hold") for _, message in actions):
            return
        guide = coordinator.guide_status()
        number = guide["step"]
        if guide["ready"] and context["state"].get("sent_step") != number:
            step = get_step(number)
            context["queues"][step["actor"]].submit(step["command"])
            context["state"]["sent_step"] = number

    async def test_real_tcp_queues_all_catalogue_actions_and_joint_final(self):
        codes, host_code, host, reports, journals, context = await self.run_fixture(self.choose_next, hold_final=True)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertTrue(host["coordinated_completed"])
        self.assertTrue(host["live"]["required_guided_interactions_met"])
        self.assertEqual(host["live"]["guided"]["completed_steps"], len(STEPS))
        self.assertEqual(journals["a"], journals["b"])
        for peer in ("a", "b"):
            self.assertTrue(reports[peer]["live"]["required_guided_interactions_met"])
            self.assertTrue(reports[peer]["short_preparation"]["passed"])
            actions = [command for _, _, command in context["engines"][peer].command_calls if command["op"] == "RAIL_ACTION"]
            self.assertEqual(actions, [step["command"] for step in STEPS])
        self.assertFalse(host["live"]["native_ui_input_capture"])

    async def test_divergent_engine_preview_halts_the_real_transport_before_application(self):
        codes, host_code, host, reports, journals, context = await self.run_fixture(self.choose_next, fault="divergent_preview")
        self.assertNotEqual((codes, host_code), ([0, 0], 0))
        self.assertFalse(host["coordinated_completed"])
        self.assertEqual(host["live"]["guided"]["completed_steps"], 0)
        for engine in context["engines"].values():
            self.assertFalse(any(command["op"] == "RAIL_ACTION" for _, _, command in engine.command_calls))

    async def test_cached_checkpoint_retransmission_does_not_add_effects_or_evidence(self):
        codes, host_code, host, reports, journals, context = await self.run_fixture(self.choose_next, duplicate_checkpoint=True)
        self.assertEqual((codes, host_code), ([0, 0], 0), host.get("reason"))
        self.assertEqual(len(context["duplicates"]), 2)
        self.assertEqual(journals["a"], journals["b"])
        self.assertEqual(len(host["live"]["guided_records"]), len(STEPS))


if __name__ == "__main__":
    unittest.main()
