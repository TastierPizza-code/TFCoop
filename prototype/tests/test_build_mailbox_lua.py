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
from prototype.strict_sync.engine_mailbox import EngineAdapter
from prototype.strict_sync.replica import Replica
from prototype.tests.test_engine_mailbox import EPOCH, control
from prototype.tests.test_engine_mailbox_lua import ActualLuaWorker, MOD, RUNTIMES


class BuildLuaWorker(ActualLuaWorker):
    def __init__(self, directory, runtime="lua53", *, terrain_setup="", **options):
        self.terrain_setup = terrain_setup
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
            config = lua.execute((scripts / "config.lua").read_text("utf-8"))
            config.enabled, config.epoch, config.profile = True, EPOCH, "build_v1"
            config.mailbox_dir = self.directory.resolve().as_posix()
            config.initial_bindings = lua.table()
            modules = {"tf2_strict_probe/json": j, "tf2_strict_probe/config": config,
                       "tf2_strict_probe/build_assets": assets}
            lua.globals().require = lambda name: modules[name]
            modules["tf2_strict_probe/build_engine"] = lua.execute((scripts / "build_engine.lua").read_text("utf-8"))
            lua.execute("api.cmd.sendCommand=function(command,callback) callback(apply_command(command),true) end")
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
                while host.round < BUILD_ROUNDS:
                    self.assertTrue(queue, "protocol stopped without completion")
                    peer, message = queue.popleft()
                    replica = replicas[peer]
                    response = replica.receive(message)
                    if message["kind"] in ("apply", "step"):
                        proofs[peer].observe(replica.engine.snapshot(), frame=replica.frame,
                            command=message.get("command"), command_key=message.get("command_key"))
                        if replica.frame == BUILD_ROUNDS:
                            final_proofs[peer] = proofs[peer].finish(frame=BUILD_ROUNDS, step_us=200000)
                    if response is not None:
                        queue.extend(host.receive(peer, response))
                    self.assertFalse(host.halted, host.halt_reason)
                self.assertEqual(host.sim_time_us, 55_800_000)
                self.assertEqual(engines[0].snapshot(), engines[1].snapshot())
                self.assertEqual(final_proofs["a"], final_proofs["b"])
                self.assertTrue(final_proofs["a"]["passed"])
                self.assertLess(final_proofs["a"]["finances"]["balance_delta"], 0)
                self.assertEqual([w.observed_sends for w in workers], [11, 11])
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
