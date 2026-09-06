"""Whole build profile through production Lua script, Python and real file IPC.

The game API and native clock are explicit fixtures. No game is started.
"""
from collections import deque
import json
from pathlib import Path
import threading
import time
import unittest

from prototype.strict_sync.build_profile import BuildProof, BUILD_ROUNDS, build_inputs
from prototype.strict_sync.core import Coordinator
from prototype.strict_sync.engine_mailbox import EngineAdapter, MailboxError
from prototype.strict_sync.replica import Replica
from prototype.tests.test_engine_mailbox import EPOCH, control
from prototype.tests.test_engine_mailbox_lua import ActualLuaWorker, MOD, RUNTIMES


class BuildLuaWorker(ActualLuaWorker):
    def __init__(self, directory, runtime="lua53", *, terrain_setup="", audit_failure=False,
                 callback_read_failures=0, callback_setup="", **options):
        self.terrain_setup = terrain_setup
        self.audit_failure = audit_failure
        self.callback_read_failures = callback_read_failures
        self.callback_setup = callback_setup
        super().__init__(directory, runtime=runtime, **options)

    def run(self):
        try:
            lua = RUNTIMES[self.runtime](unpack_returned_tuples=True)
            scripts = MOD / "res/scripts/tf2_strict_probe"
            j = lua.execute((scripts / "json.lua").read_text("utf-8"))
            assets = lua.execute((scripts / "build_assets.lua").read_text("utf-8"))
            lua.globals().assets, lua.globals().id_offset = assets, self.offset
            lua.execute((MOD / "tests/fake_build_engine.lua").read_text("utf-8"))
            lua.execute(self.terrain_setup)
            lua.globals().callback_read_failures = self.callback_read_failures
            lua.execute("""
                local original_open,original_apply=io.open,apply_command
                local missing_reads=0
                apply_command=function(command)
                  local result=original_apply(command)
                  missing_reads=callback_read_failures
                  return result
                end
                io.open=function(path,mode)
                  if mode=='rb' and path:match('/native_status%.txt$') and missing_reads>0 then
                    missing_reads=missing_reads-1
                    return nil,'fixture: transient file access denied',13
                  end
                  return original_open(path,mode)
                end
            """)
            config = lua.execute((scripts / "config.lua").read_text("utf-8"))
            config.enabled, config.epoch, config.profile = True, EPOCH, "build_v2"
            config.mailbox_dir = self.directory.resolve().as_posix()
            config.initial_bindings = lua.table()
            modules = {"tf2_strict_probe/json": j, "tf2_strict_probe/config": config,
                       "tf2_strict_probe/build_assets": assets,
                       "tf2_strict_probe/api_audit": lua.execute((scripts / "api_audit.lua").read_text("utf-8"))}
            if self.audit_failure:
                modules["tf2_strict_probe/api_audit"] = lua.execute(
                    "return {collect=function() error('fixture unavailable collector',0) end}")
            lua.globals().require = lambda name: modules[name]
            modules["tf2_strict_probe/build_engine"] = lua.execute((scripts / "build_engine.lua").read_text("utf-8"))
            lua.execute("api.cmd.sendCommand=function(command,callback) callback(apply_command(command),true) end")
            lua.execute(self.callback_setup)
            lua.execute((MOD / "res/config/game_script/tf2_strict_probe.lua").read_text("utf-8"))
            script = lua.globals().data()
            self.clock_us = 13_400_000
            self.native_status()
            script.update()
            self.initialized.set()
            while not self.stop_event.is_set():
                if (self.directory / "native_control.txt").exists():
                    try:
                        request = control(self.directory / "native_control.txt")
                    except (PermissionError, FileNotFoundError):
                        time.sleep(.001)
                        continue
                    number = int(request["request"])
                    if number != self.native_request:
                        if request["epoch"] != EPOCH:
                            raise AssertionError("wrong fixture native epoch")
                        self.native_request = number
                        if request["action"] == "halt":
                            self.native_halted = True
                            self.native_status(halted=1, ready=0)
                        else:
                            dt = int(request["dt_us"])
                            if self.native_halted or int(request["frame"]) != self.completed_frame + 1 or dt not in (0, 200000):
                                raise AssertionError("unauthorized fixture step")
                            if dt == 200000:
                                lua.globals().advance()
                            self.clock_us += dt
                            self.completed_frame += 1
                            lua.globals().now = self.clock_us / 1_000_000
                            self.native_status(completed_dt_us=dt)
                script.update()
                self.observed_sends = int(lua.globals().sent)
                time.sleep(.001)
            script, modules, config, assets, j, lua = (None,) * 6
        except Exception as exc:
            self.error = exc
            self.initialized.set()


@unittest.skipUnless("lua53" in RUNTIMES, "Lua 5.3 fixture runtime unavailable")
class FullBuildFileIntegrationTests(unittest.TestCase):
    def test_invalid_incidence_plan_halts_before_connect_send_or_time_release(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker = BuildLuaWorker(directory, terrain_setup="""
                local original=api.engine.system.streetSystem.getNode2StreetEdgeMap
                api.engine.system.streetSystem.getNode2StreetEdgeMap=function()
                  local m=original();local first
                  for _,entity in pairs(m[roadends[3]])do first=entity;break end
                  m[roadends[3]]=native_entity_collection({tostring(first)})
                  return m
                end
            """)
            engine = None
            try:
                engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                for key, command in (("a:1", {"op": "SET_PAUSED", "value": True}),
                                     ("a:2", {"op": "PROBE_ROAD"}), ("b:1", {"op": "PROBE_DEPOT"}),
                                     ("a:3", {"op": "PROBE_STOP", "index": 0}),
                                     ("b:2", {"op": "PROBE_STOP", "index": 1})):
                    engine.apply(command, key)
                previous = engine.snapshot()
                with self.assertRaisesRegex(MailboxError, "street incidence entity value unavailable"):
                    engine.apply({"op": "PROBE_CONNECT"}, "a:4")
                status = worker.status()
                self.assertEqual(status["status"], "halted")
                self.assertEqual(status["diagnostics"]["failure"]["request_context"]["action"], "plan")
                self.assertEqual(status["snapshot"], previous)
                self.assertNotIn("canonical_state_json", status)
                self.assertFalse(any(key.startswith("a:4") for key in status["diagnostics"]["bindings"]))
                time.sleep(.02)
                self.assertEqual(worker.observed_sends, 5)
                self.assertEqual(worker.completed_frame, 0)
                self.assertEqual(engine.time_us, 13400000)
                self.assertEqual(control(directory / "native_control.txt")["action"], "halt")
            finally:
                if engine is not None:
                    engine.close()
                worker.close()

    def test_depot_rejection_keeps_actual_callback_details_even_when_gate_cannot_be_read(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker = BuildLuaWorker(directory, callback_setup="""
                local original_send=api.cmd.sendCommand
                api.cmd.sendCommand=function(command,callback)
                  if command.op=='build' and command.proposal.constructionsToAdd[1].fileName==assets.depot_file then
                    sent=sent+1
                    local original_open=io.open
                    io.open=function(path,mode)
                      if mode=='rb' and path:match('/native_status%.txt$') then return nil,'fixture access denied',13 end
                      return original_open(path,mode)
                    end
                    callback(native_params({resultProposalData={errorState={
                      fixture_reason='collision supplied by test API',fixture_cost=10000.5
                    }}}),false)
                    return
                  end
                  return original_send(command,callback)
                end
            """)
            engine = None
            try:
                engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                engine.apply({"op": "SET_PAUSED", "value": True}, "a:1")
                engine.apply({"op": "PROBE_ROAD"}, "a:2")
                previous = engine.snapshot()
                with self.assertRaisesRegex(MailboxError, "Lua adapter reported error/halt: engine rejected command"):
                    engine.apply({"op": "PROBE_DEPOT"}, "b:1")
                status = worker.status()
                self.assertFalse(status["receipt"]["success"])
                self.assertEqual(status["receipt"]["command_key"], "b:1")
                diagnostic = status["diagnostics"]["failure"]["callback"]
                self.assertEqual(diagnostic["success"], {"type": "boolean", "value": False})
                fields = {item["path"]: item for item in diagnostic["records"]}
                prefix = "result.resultProposalData.errorState."
                self.assertEqual(fields[prefix + "fixture_reason"]["value"], "collision supplied by test API")
                self.assertEqual(fields[prefix + "fixture_cost"]["value"], "10000.5")
                self.assertEqual(status["snapshot"], previous)
                self.assertNotIn("b:1", status["diagnostics"]["bindings"])
                self.assertEqual(engine.frame, 0)
                time.sleep(.02)
                self.assertEqual(worker.observed_sends, 3)
            finally:
                if engine is not None:
                    engine.close()
                worker.close()

    def test_transient_callback_gate_reads_recover_without_replaying_command_or_advancing_time(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker = BuildLuaWorker(directory, callback_read_failures=4)
            engine = None
            try:
                engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                result = engine.apply({"op": "SET_PAUSED", "value": True}, "a:1")
                self.assertTrue(result["success"])
                self.assertEqual(engine.frame, 0)
                self.assertEqual(engine.time_us, 13400000)
                status = worker.status()
                self.assertEqual(status["status"], "applied")
                self.assertEqual(status["diagnostics"]["last_native_read_issue"]["errno"], 13)
                self.assertEqual(status["diagnostics"]["last_native_read_issue"]["count"], 4)
                time.sleep(.02)
                self.assertEqual(worker.observed_sends, 1)
                self.assertEqual(worker.completed_frame, 0)
                engine.step(0)
                self.assertEqual(engine.frame, 1)
                self.assertEqual(engine.time_us, 13400000)
            finally:
                if engine is not None:
                    engine.close()
                worker.close()

    def test_persistent_callback_gate_read_failure_times_out_without_step_or_resend(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker = BuildLuaWorker(directory, callback_read_failures=1000000)
            engine = None
            try:
                engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                engine.native.timeout_s = .15
                with self.assertRaisesRegex(MailboxError, "timeout"):
                    engine.apply({"op": "SET_PAUSED", "value": True}, "a:1")
                self.assertTrue(engine.halted)
                self.assertEqual(engine.frame, 0)
                self.assertEqual(worker.completed_frame, 0)
                time.sleep(.02)
                self.assertEqual(worker.observed_sends, 1)
                self.assertEqual(control(directory / "native_control.txt")["action"], "halt")
                status = worker.status()
                self.assertEqual(status["status"], "halted")
                self.assertTrue(status["receipt"]["success"])
                self.assertEqual(status["receipt"]["command_key"], "a:1")
            finally:
                if engine is not None:
                    engine.close()
                worker.close()

    def test_failed_build_captures_independent_fields_and_never_acknowledges_bad_snapshot(self):
        import tempfile
        for runtime in RUNTIMES:
            with self.subTest(runtime=runtime), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                worker = BuildLuaWorker(directory, runtime=runtime, terrain_setup="""
                    local original=apply_command
                    apply_command=function(command)
                      local result=original(command)
                      for _,object in pairs(world) do
                        if object.CONSTRUCTION then
                          object.CONSTRUCTION.timeBuild=0/0
                          object.CONSTRUCTION.transf=nil
                          object.CONSTRUCTION.frozenEdges=nil
                        end
                      end
                      return result
                    end
                """)
                engine = None
                try:
                    engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                    engine.apply({"op": "SET_PAUSED", "value": True}, "a:1")
                    previous = engine.snapshot()
                    with self.assertRaisesRegex(MailboxError, "Lua adapter reported error/halt: capability_missing"):
                        engine.apply({"op": "PROBE_ROAD"}, "a:2")
                    status = worker.status()
                    self.assertEqual(status["status"], "halted")
                    self.assertNotIn("canonical_state_json", status)
                    self.assertEqual(status["snapshot"], previous)
                    self.assertEqual(status["diagnostics"]["snapshot_scope"], "last_valid_before_failure")
                    failure = status["diagnostics"]["failure"]
                    self.assertFalse(failure["valid_snapshot"])
                    self.assertFalse(failure["failed_observation"]["valid_snapshot"])
                    self.assertTrue(failure["failed_observation"]["missing"])
                    self.assertEqual(failure["request_context"]["command_key"], "a:2")
                    self.assertTrue(failure["api_audit"]["written"])
                    self.assertEqual(failure["api_audit"]["file"], "lua_api_audit.json")
                    report = json.loads((directory / "lua_api_audit.json").read_bytes())
                    self.assertEqual(report["status"], "completed")
                    self.assertFalse(report["valid_snapshot"])
                    fields = {item["path"]: item for item in report["records"]}
                    self.assertIn("bindings.a:2.CONSTRUCTION.timeBuild", fields)
                    self.assertIn("bindings.a:2.CONSTRUCTION.transf", fields)
                    self.assertIn("bindings.a:2.CONSTRUCTION.frozenEdges", fields)
                    self.assertEqual(engine.frame, 0)
                    self.assertEqual(worker.completed_frame, 0)
                    self.assertEqual(control(directory / "native_control.txt")["action"], "halt")
                    self.assertLessEqual((directory / "lua_status.json").stat().st_size, 262144)
                    time.sleep(.02)
                    self.assertEqual(worker.status(), status)
                    self.assertEqual(worker.observed_sends, 2)
                finally:
                    if engine is not None:
                        engine.close()
                    worker.close()

    def test_raw_collector_failure_preserves_original_halt_without_world_steps(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker = BuildLuaWorker(directory, audit_failure=True, terrain_setup="world[0].TERRAIN.waterLevel=20")
            try:
                with self.assertRaisesRegex(MailboxError, "Lua adapter reported error/halt: build_site_unavailable"):
                    EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=3, poll_s=.002)
                status = worker.status()
                self.assertIn("API collector failed", status["diagnostics"]["failure"]["audit_error"])
                self.assertNotIn("api_audit", status["diagnostics"]["failure"])
                self.assertFalse((directory / "lua_api_audit.json").exists())
                self.assertEqual(worker.completed_frame, 0)
                self.assertEqual(worker.observed_sends, 0)
            finally:
                worker.close()

    def test_rejected_vehicle_receipt_still_reports_exact_new_entity_without_binding_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            worker = BuildLuaWorker(directory, terrain_setup="""
                local original=apply_command
                apply_command=function(command)
                  local result=original(command)
                  for _,object in pairs(world) do
                    if object.TRANSPORT_VEHICLE then object.TRANSPORT_VEHICLE.carrier=99 end
                  end
                  return result
                end
            """)
            engine = None
            try:
                engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=5, poll_s=.002)
                commands = [("a:1", {"op": "SET_PAUSED", "value": True}),
                            ("a:2", {"op": "PROBE_ROAD"}), ("b:1", {"op": "PROBE_DEPOT"}),
                            ("a:3", {"op": "PROBE_STOP", "index": 0}),
                            ("b:2", {"op": "PROBE_STOP", "index": 1}),
                            ("a:4", {"op": "PROBE_CONNECT"})]
                for key, command in commands:
                    engine.apply(command, key)
                with self.assertRaisesRegex(MailboxError, "bought vehicle differs from requested recipe"):
                    engine.apply({"op": "PROBE_VEHICLE"}, "b:3")
                status = worker.status()
                self.assertNotIn("b:3", status["diagnostics"]["bindings"])
                self.assertNotIn("b:3", {item["logical_id"] for item in engine.snapshot()["objects"]})
                report = json.loads((directory / "lua_api_audit.json").read_bytes())
                fields = {item["path"]: item for item in report["records"]}
                carrier = fields["bindings.callback:b:3.TRANSPORT_VEHICLE.carrier"]
                self.assertEqual(carrier["value"], 99)
                self.assertEqual(engine.frame, 0)
                self.assertFalse(report["valid_snapshot"])
            finally:
                if engine is not None:
                    engine.close()
                worker.close()

    def test_failed_site_publishes_rejection_counts_before_any_game_command(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            worker = BuildLuaWorker(Path(temporary), terrain_setup="world[0].TERRAIN.waterLevel=20")
            try:
                status = worker.status()
                self.assertEqual(status["status"], "halted")
                self.assertEqual(status["request"], 0)
                self.assertIn("checked=4225", status["error"])
                self.assertEqual(status["diagnostics"]["site_search"]["rejected"]["water"], 4225)
                self.assertEqual(worker.observed_sends, 0)
            finally:
                worker.close()

    def test_two_literal_lua_peers_complete_scene_and_all_240_boundaries(self):
        import tempfile
        workers, engines = [], []
        with tempfile.TemporaryDirectory() as temporary:
            try:
                replicas, proofs = {}, {}
                epoch, manifest = "literal-build-epoch", "a" * 64
                for index, peer in enumerate(("a", "b")):
                    directory = Path(temporary) / peer
                    directory.mkdir()
                    worker = BuildLuaWorker(directory, runtime="lua53", offset=10000 * index)
                    workers.append(worker)
                    engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=30, poll_s=.002)
                    engines.append(engine)
                    proofs[peer] = BuildProof()
                    proofs[peer].observe(engine.snapshot(), frame=0)
                    replicas[peer] = Replica(peer, epoch, manifest, engine.capabilities, engine,
                        lambda number, owner=peer: build_inputs(owner, number), step_us=200000)
                host = Coordinator(epoch, manifest, engines[0].capabilities, step_us=200000, timeout_s=30)
                queue = deque()
                for peer, replica in replicas.items():
                    queue.extend(host.receive(peer, replica.hello()))
                final_proofs = {}
                disconnected, connected = set(), set()
                while host.round < BUILD_ROUNDS:
                    self.assertTrue(queue, "protocol stopped without completion")
                    peer, message = queue.popleft()
                    replica = replicas[peer]
                    response = replica.receive(message)
                    if message["kind"] in ("apply", "step"):
                        observed = replica.engine.snapshot()
                        command = message.get("command", {})
                        if command.get("op") == "PROBE_STOP" and command.get("index") == 1:
                            self.assertFalse(observed["probe"]["connectivity"]["connected"])
                            self.assertNotIn("connectors", observed["probe"]["scene"])
                            disconnected.add(peer)
                        if command.get("op") == "PROBE_CONNECT":
                            self.assertEqual(observed["probe"]["scene"]["connectors"], "a:4")
                            self.assertTrue(observed["probe"]["connectivity"]["connected"])
                            links = [obj for obj in observed["objects"] if obj["kind"] == "connector"]
                            self.assertEqual([obj["logical_id"] for obj in links],
                                             [f"a:4:link:{i}" for i in range(1, 4)])
                            self.assertTrue(all(isinstance(obj["state"], dict) and
                                                "node0" in obj["state"] and "node1" in obj["state"]
                                                for obj in links))
                            connected.add(peer)
                        proofs[peer].observe(observed, frame=replica.frame,
                            command=message.get("command"), command_key=message.get("command_key"))
                        if replica.frame == BUILD_ROUNDS:
                            final_proofs[peer] = proofs[peer].finish(frame=BUILD_ROUNDS, step_us=200000)
                    if response is not None:
                        queue.extend(host.receive(peer, response))
                    self.assertFalse(host.halted, host.halt_reason)
                self.assertEqual(host.sim_time_us, 55_600_000)
                self.assertEqual(disconnected, {"a", "b"})
                self.assertEqual(connected, {"a", "b"})
                self.assertEqual(engines[0].snapshot(), engines[1].snapshot())
                self.assertEqual(final_proofs["a"], final_proofs["b"])
                self.assertTrue(final_proofs["a"]["passed"])
                self.assertLess(final_proofs["a"]["finances"]["balance_delta"], 0)
                self.assertEqual([w.observed_sends for w in workers], [12, 12])
                for replica in replicas.values():
                    replica.receive({"kind": "complete", "epoch": epoch, "round": BUILD_ROUNDS,
                        "frame": BUILD_ROUNDS, "sim_time_us": host.sim_time_us, "state_digest": host.state_digest})
                    self.assertTrue(replica.finished)
            finally:
                for engine in engines:
                    engine.close()
                for worker in workers:
                    worker.close()


if __name__ == "__main__":
    unittest.main()
