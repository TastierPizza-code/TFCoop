"""Cross-language integration: production Lua + Python adapter + real file IPC.

Only documented engine primitives and native boundary/clock writes are fixtures.
No fake Lua status JSON is supplied. One worker exclusively owns each Lua VM.
Transport Fever 2 is neither launched nor loaded by these tests.
"""

import importlib
import json
from pathlib import Path
import sys
import threading
import time
import unittest

from prototype.strict_sync.engine_mailbox import EngineAdapter, MailboxError, _shared_read
from prototype.tests.test_engine_mailbox import atomic_write, control, native_bytes, EPOCH


ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "prototype/mod/tf2_strict_probe_1"
sys.path.insert(0, str(ROOT / "tests/lua/.deps"))
RUNTIMES = {}
for _name in ("lua51", "lua52", "lua53", "lua54"):
    try:
        RUNTIMES[_name] = importlib.import_module("lupa." + _name).LuaRuntime
    except ImportError:
        pass


LINE = {"op": "LINE_CREATE", "name": "Gemeinsame Linie", "color": ["0.1", "0.2", "0.3"],
        "waiting_time": "180", "stops": []}


class ActualLuaWorker:
    def __init__(self, directory, runtime="lua53", *, offset=0, missing_capability=False,
                 missing_result=False, missing_company=False, withhold_callback=False):
        self.directory = Path(directory)
        self.runtime = runtime
        self.offset = offset
        self.missing_capability = missing_capability
        self.missing_result = missing_result
        self.missing_company = missing_company
        self.withhold_callback = withhold_callback
        self.clock_us = 0
        self.completed_frame = 0
        self.native_request = 0
        self.observed_sends = 0
        self.observed_speed = 0
        self.native_halted = False
        self.error = None
        self.stop_event = threading.Event()
        self.initialized = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        if not self.initialized.wait(3):
            raise AssertionError("Lua fixture failed to start")
        if self.error:
            raise self.error

    def native_status(self, **changes):
        # Includes every integration-sensitive extra field from production native IO.
        fields = dict(outer_calls=1 + self.completed_frame, time_before_ms=self.clock_us // 1000,
                      time_after_ms=self.clock_us // 1000, completed_frame=self.completed_frame,
                      request_received=self.native_request, request_acknowledged=self.native_request,
                      request_completed=self.native_request, win32_error=0, updated_ms=1234,
                      hold_calls=5, advance_permits=self.completed_frame, pause_permits=0,
                      completed_permits=self.completed_frame, first_speed_reads=1,
                      second_speed_reads=0, original_frame_time_us=200000)
        fields.update(changes)
        atomic_write(self.directory / "native_status.txt", native_bytes(**fields))

    def run(self):
        try:
            # All VM creation, use, callbacks, and destruction occur on this thread.
            lua = RUNTIMES[self.runtime](unpack_returned_tuples=True)
            real_io = lua.globals().io
            lua.globals().id_offset = self.offset
            lua.execute((MOD / "tests/fake_engine.lua").read_text("utf-8"))
            lua.globals().io = real_io  # Replace fixture's in-memory IO with real files.
            lua.execute("now=0; speed=0; sync_callback=true")
            j = lua.execute((MOD / "res/scripts/tf2_strict_probe/json.lua").read_text("utf-8"))
            config = lua.execute((MOD / "res/scripts/tf2_strict_probe/config.lua").read_text("utf-8"))
            config.enabled, config.epoch = True, EPOCH
            config.mailbox_dir = str(self.directory.resolve()).replace("\\", "/")
            config.initial_bindings = lua.table()  # Start with an actual empty tracked roster.
            if self.missing_capability:
                lua.execute("local original=api.cmd.make.createLine; api.cmd.make.createLine=function(...) "
                            "local c=original(...); c.resultEntity=nil; return c end")
            if self.missing_company:
                lua.execute("company.balance=nil")
            if self.missing_result:
                lua.execute("api.cmd.sendCommand=function(cmd,callback) sends[#sends+1]=cmd; "
                            "callbacks[#sends]=callback; complete(#sends,920+(id_offset or 0),true,true) end")
            if self.withhold_callback:
                lua.execute("sync_callback=false")
            module = lua.execute((MOD / "res/scripts/tf2_strict_probe/engine.lua").read_text("utf-8"))
            modules = {"tf2_strict_probe/json": j, "tf2_strict_probe/config": config,
                       "tf2_strict_probe/engine": module}
            lua.globals().require = lambda name: modules[name]
            lua.execute((MOD / "res/config/game_script/tf2_strict_probe.lua").read_text("utf-8"))
            script = lua.globals().data()
            self.native_status()
            script.update()
            self.initialized.set()
            while not self.stop_event.is_set():
                path = self.directory / "native_control.txt"
                if path.exists():
                    try:
                        request = control(path)
                    except (PermissionError, FileNotFoundError):
                        time.sleep(.001)
                        continue
                    number = int(request["request"])
                    if number != self.native_request:
                        if request["epoch"] != EPOCH:
                            raise AssertionError("native fixture received wrong epoch")
                        self.native_request = number
                        if request["action"] == "halt":
                            self.native_halted = True
                            self.native_status(halted=1, ready=0)
                        else:
                            if self.native_halted or int(request["frame"]) != self.completed_frame + 1:
                                raise AssertionError("native fixture received unauthorized frame")
                            dt = int(request["dt_us"])
                            if dt not in (0, 200000):
                                raise AssertionError("native fixture received wrong dt")
                            self.clock_us += dt
                            self.completed_frame += 1
                            lua.globals().now = self.clock_us / 1_000_000
                            self.native_status(completed_dt_us=dt)
                script.update()
                self.observed_sends = len(lua.globals().sends)
                self.observed_speed = lua.globals().speed
                time.sleep(.001)
            # Do not leak Lua proxies to a different Python thread.
            script, module, config, j, modules, real_io, lua = (None,) * 7
        except Exception as exc:
            self.error = exc
            self.initialized.set()

    def status(self):
        deadline = time.monotonic() + 1
        while True:
            try:
                return json.loads(_shared_read(self.directory / "lua_status.json", 262144))
            except (json.JSONDecodeError, PermissionError, FileNotFoundError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.001)

    def close(self):
        self.stop_event.set()
        self.thread.join(2)
        if self.thread.is_alive():
            raise AssertionError("Lua fixture thread did not stop")
        if self.error:
            raise self.error


@unittest.skipUnless(RUNTIMES, "Lupa test runtime unavailable")
class ProductionLuaFileIntegrationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.workers = []
        self.engines = []

    def tearDown(self):
        try:
            for engine in self.engines:
                engine.close()
            for worker in self.workers:
                worker.close()
        finally:
            self.temporary.cleanup()

    def start(self, runtime=None, **options):
        directory = self.directory / f"session-{len(self.workers)}"
        directory.mkdir()
        worker = ActualLuaWorker(directory, runtime or next(iter(RUNTIMES)), **options)
        self.workers.append(worker)
        return directory, worker

    def adapter(self, directory, timeout_s=1):
        engine = EngineAdapter(directory, EPOCH, probe_only=True, timeout_s=timeout_s, poll_s=.002)
        self.engines.append(engine)
        return engine

    def test_literal_lua_empty_start_pause_advance_and_zero_time_on_all_runtimes(self):
        for runtime in RUNTIMES:
            with self.subTest(runtime=runtime):
                directory, worker = self.start(runtime)
                engine = self.adapter(directory)
                self.assertEqual(engine.snapshot()["objects"], [])
                self.assertEqual(engine.snapshot()["company"]["balance"], 4480019)
                self.assertEqual(engine.time_us, 0)
                self.assertTrue(engine.paused)
                self.assertIn(b"win32_error=0\n", (directory / "native_status.txt").read_bytes())
                start_hash = engine.state_digest
                result = engine.apply({"op": "SET_PAUSED", "value": False}, "a:1")
                self.assertEqual(result["result"], {"paused": False})
                self.assertNotEqual(start_hash, engine.state_digest)
                self.assertEqual(engine.step(200000)["sim_time_us"], 200000)
                self.assertEqual(worker.clock_us, 200000)
                paused = engine.apply({"op": "SET_PAUSED", "value": True}, "a:2")
                self.assertEqual(paused["result"], {"paused": True})
                paused_hash = engine.state_digest
                self.assertEqual(engine.step(0)["sim_time_us"], 200000)
                self.assertEqual(paused_hash, engine.state_digest)
                self.assertEqual(engine.frame, 2)
                self.assertEqual(engine.apply({"op": "SET_PAUSED", "value": True}, "a:2"), paused)
                self.assertEqual(worker.status()["snapshot"]["sim_time_us"], 200000)
                self.assertFalse(engine.coverage["complete_world"])
                self.assertNotIn("state_digest", engine.capabilities)
                engine.close()
                worker.close()

    def test_production_lua_binds_exact_results_but_excludes_local_ids_from_shared_hash(self):
        receipts, hashes, local_entities = [], [], []
        for offset in (0, 10000):
            directory, worker = self.start(offset=offset)
            engine = self.adapter(directory)
            receipt = engine.apply(LINE, "a:1")
            receipts.append(receipt)
            hashes.append(engine.state_digest)
            status = worker.status()
            local_entities.append(status["receipt"]["result_entity"])
            self.assertEqual(receipt["result"], {"logical_id": "a:1"})
            self.assertEqual(engine.snapshot()["objects"][0]["logical_id"], "a:1")
            self.assertEqual(engine.snapshot()["objects"][0]["state"]["name"], "Gemeinsame Linie")
            engine.close()
            worker.close()
        self.assertNotEqual(local_entities[0], local_entities[1])
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(receipts[0], receipts[1])

    def test_missing_native_result_capability_refuses_before_engine_command(self):
        directory, worker = self.start(missing_capability=True)
        engine = self.adapter(directory)
        with self.assertRaises(MailboxError):
            engine.apply(LINE, "a:1")
        self.assertTrue(engine.halted)
        self.assertEqual(worker.observed_sends, 0)
        self.assertEqual(worker.status()["status"], "halted")
        self.assertEqual(control(directory / "native_control.txt")["action"], "halt")

    def test_callback_without_exact_result_id_halts_without_guessing_binding(self):
        directory, worker = self.start(missing_result=True)
        engine = self.adapter(directory)
        with self.assertRaises(MailboxError):
            engine.apply(LINE, "a:1")
        self.assertTrue(engine.halted)
        status = worker.status()
        self.assertEqual(status["status"], "halted")
        self.assertNotIn("a:1", status["diagnostics"]["bindings"])
        self.assertEqual(engine.frame, 0)
        self.assertEqual(control(directory / "native_control.txt")["frame"], "0")

    def test_missing_actual_company_data_cannot_fall_back_to_model_state(self):
        directory, worker = self.start(missing_company=True)
        with self.assertRaises(MailboxError):
            self.adapter(directory)
        self.assertEqual(worker.status()["status"], "halted")
        self.assertEqual(worker.observed_sends, 0)
        self.assertEqual(control(directory / "native_control.txt")["action"], "halt")

    def test_missing_real_callback_times_out_without_native_advancement(self):
        directory, worker = self.start(withhold_callback=True)
        engine = self.adapter(directory)
        engine.native.timeout_s = .2
        with self.assertRaisesRegex(MailboxError, "timeout"):
            engine.apply({"op": "SET_PAUSED", "value": False}, "a:1")
        self.assertTrue(engine.halted)
        self.assertEqual(worker.clock_us, 0)
        self.assertEqual(engine.frame, 0)
        self.assertEqual(control(directory / "native_control.txt")["action"], "halt")


if __name__ == "__main__":
    unittest.main()
