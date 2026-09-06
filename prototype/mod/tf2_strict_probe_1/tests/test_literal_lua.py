"""Runs the literal production Lua files against bounded fake engine/IO surfaces.

These tests prove adapter behavior; they do not prove TF2's native APIs or game
determinism. Run: py -3.10 prototype/mod/tf2_strict_probe_1/tests/test_literal_lua.py
"""
from pathlib import Path
import importlib
import json
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tests/lua/.deps"))
MOD = HERE.parent
RUNTIME = None


class Harness:
    def __init__(self, enabled=True, offset=0, bindings=True, saved=False):
        self.lua = RUNTIME(unpack_returned_tuples=True)
        self.lua.globals().id_offset = offset
        self.lua.execute((HERE / "fake_engine.lua").read_text(encoding="utf-8"))
        self.j = self.lua.execute((MOD / "res/scripts/tf2_strict_probe/json.lua").read_text(encoding="utf-8"))
        config = self.lua.execute((MOD / "res/scripts/tf2_strict_probe/config.lua").read_text(encoding="utf-8"))
        self.config = config
        config.enabled, config.epoch, config.mailbox_dir = enabled, "77", "C:/probe"
        config.initial_bindings = self.lua.globals().bindings if bindings else self.lua.table()
        engine = self.lua.execute((MOD / "res/scripts/tf2_strict_probe/engine.lua").read_text(encoding="utf-8"))
        self.lua.globals().fixture_engine = engine
        self.lua.execute("""
            finish_calls=0
            local original_new=fixture_engine.new
            fixture_engine.new=function(...)
              local e=original_new(...); observed_engine=e
              local original_finish=e.finish
              e.finish=function(...) finish_calls=finish_calls+1; return original_finish(...) end
              return e
            end
        """)
        modules = {"tf2_strict_probe/json": self.j, "tf2_strict_probe/config": config, "tf2_strict_probe/engine": engine}
        self.lua.globals().require = lambda name: modules[name]
        self.lua.execute((MOD / "res/config/game_script/tf2_strict_probe.lua").read_text(encoding="utf-8"))
        self.script = self.lua.globals().data()
        if saved:
            self.script.load(self.table({"strict_probe_active": True}))
        self.n = 0

    def table(self, v):
        return self.j.decode(json.dumps(v, separators=(",", ":")))

    def update(self):
        self.script.update()
        return self.status()

    def status(self):
        raw = self.lua.globals().files["C:/probe/lua_status.json"]
        return json.loads(raw) if raw else None

    def request(self, action, command=None, key="a:1", expected=100_000_000, boundary="0", seq=None):
        self.n = self.n + 1 if seq is None else seq
        c = {"protocol": 1, "epoch": "77", "request": self.n, "action": action,
             "boundary": boundary, "expected_sim_time_us": expected}
        if command is not None:
            c.update(command_key=key, command=command)
        self.lua.globals().files["C:/probe/lua_control.json"] = json.dumps(c, separators=(",", ":"))
        return self.update()

    def complete(self, n=900, success=True, no_result=False):
        self.lua.globals().complete(len(self.lua.globals().sends), n, success, no_result)
        return self.status()

    def fail_native_reads(self, count=1, operation="open"):
        """Only the selected native read fails; no status or engine action is fabricated."""
        self.lua.globals().native_failures = count
        self.lua.globals().native_failure_operation = operation
        self.lua.execute("""
            local original=io.open
            io.open=function(path,mode)
              if path=='C:/probe/native_status.txt' and mode=='rb' and native_failures>0 then
                native_failures=native_failures-1
                if native_failure_operation=='open' then return nil,'Permission denied',13 end
                local f=original(path,mode)
                if native_failure_operation=='read' then
                  f.read=function() return nil,'Read denied',13 end
                elseif native_failure_operation=='close' then
                  f.close=function() return nil,'Close denied',13 end
                elseif native_failure_operation=='throw' then error('fixture open failure',0)
                end
                return f
              end
              return original(path,mode)
            end
        """)

    def run(self, command, key="a:1", n=900):
        assert self.request("plan", command, key)["status"] == "planned", self.status()
        assert self.request("apply", command, key)["status"] == "in_flight", self.status()
        return self.complete(n)


CTX = dict(checkTerrainAlignment=True, cleanupStreetGraph=False, gatherBuildings=False, gatherFields=False)
STOP = dict(station_group="seed:group", station=0, terminal=0, load_mode=0, min_wait="0", max_wait="180", alternative_terminals=[], waypoints=[])
LINE = dict(op="LINE_CREATE", name="Shared Route", color=["0.1", "0.2", "0.3"], waiting_time="180", stops=[STOP])
BUY = dict(op="VEHICLE_BUY", template="seed:vehicle", depot="seed:depot", purchase_time_ms=100000)
ROAD = dict(op="ROAD", points_mm=[[20000, 0, 0], [30000, 0, 0]], street="actual/fixture_street.lua", has_bus=False, tram_track_type=0, context=CTX, ignore_errors=False)
DEPOT = dict(op="DEPOT", template="seed:depot", transform=[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 40, 20, 0, 1], name="Shared Depot", context=CTX, ignore_errors=False)


class ProductionLuaTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        status = self.h.update()
        self.assertEqual(status["status"], "ready", status)
        self.assertFalse(status["snapshot"]["coverage"]["complete_world"])
        self.assertEqual(status["snapshot"]["coverage"]["missing"], [])

    def assert_halted(self, value):
        self.assertEqual(value["status"], "halted", value)

    def test_disabled_means_no_io_or_engine(self):
        h = Harness(enabled=False)
        self.assertIsNone(h.update())
        self.assertEqual(h.lua.globals().reads, 0)
        self.assertEqual(h.lua.globals().writes, 0)
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_first_request_already_present_is_not_skipped(self):
        h = Harness(bindings=False)
        s = h.request("snapshot")
        self.assertEqual(s["request"], 1)
        self.assertEqual(s["snapshot"]["objects"], [])

    def test_plan_apply_async_exactly_once(self):
        before = self.h.status()["canonical_state_json"]
        c = dict(op="SET_PAUSED", value=True)
        self.assertEqual(self.h.request("plan", c)["status"], "planned")
        self.assertEqual(len(self.h.lua.globals().sends), 0)
        self.assertEqual(self.h.status()["canonical_state_json"], before)
        self.assertEqual(self.h.request("apply", c)["status"], "in_flight")
        self.h.update()
        self.assertEqual(len(self.h.lua.globals().sends), 1)
        done = self.h.complete()
        self.assertEqual(done["status"], "applied")
        self.assertTrue(done["snapshot"]["paused"])
        self.assertEqual(done["receipt"]["result"], {"paused": True})
        self.assertEqual(self.h.update()["status"], "applied")
        self.assertEqual(len(self.h.lua.globals().sends), 1)

    def test_sync_callback_does_not_get_overwritten(self):
        self.h.lua.globals().sync_callback = True
        c = dict(op="SET_PAUSED", value=True)
        self.h.request("plan", c)
        self.assertEqual(self.h.request("apply", c)["status"], "applied")

    def test_changed_request_content_halts(self):
        c = dict(op="SET_PAUSED", value=True)
        self.h.request("plan", c)
        self.assert_halted(self.h.request("plan", dict(op="SET_PAUSED", value=False), seq=1))
        self.assertEqual(len(self.h.lua.globals().sends), 0)

    def test_gap_and_old_request_halt(self):
        self.assert_halted(self.h.request("snapshot", seq=2))
        h = Harness(); h.update(); h.request("snapshot"); h.request("snapshot")
        self.assert_halted(h.request("snapshot", seq=1))

    def test_command_key_cannot_be_replayed_with_new_request(self):
        c = dict(op="SET_PAUSED", value=True)
        self.assertEqual(self.h.run(c)["status"], "applied")
        self.assert_halted(self.h.request("plan", c))
        self.assertEqual(len(self.h.lua.globals().sends), 1)

    def test_wrong_apply_and_unplanned_apply_never_send(self):
        self.assert_halted(self.h.request("apply", DEPOT))
        h = Harness(); h.update(); h.request("plan", DEPOT)
        self.assert_halted(h.request("apply", dict(DEPOT, name="changed")))
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_time_and_money_drift_before_apply_halt(self):
        self.h.request("plan", BUY)
        self.h.lua.execute("now=now+0.1")
        self.assert_halted(self.h.request("apply", BUY))
        h = Harness(); h.update(); h.request("plan", BUY)
        h.lua.execute("company.balance=company.balance-1")
        self.assert_halted(h.request("apply", BUY))
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_real_callback_result_binds_new_entity_and_saved_vehicle_config(self):
        done = self.h.run(BUY, n=947)
        self.assertEqual(done["status"], "applied", done)
        self.assertEqual(done["receipt"]["bindings"]["a:1"], 947)
        self.assertEqual(done["receipt"]["result"], {"logical_id": "a:1"})
        objects = {v["logical_id"]: v["state"] for v in done["snapshot"]["objects"]}
        part = objects["a:1"]["config"]["vehicles"][0]
        self.assertTrue(part["reversed"])
        self.assertEqual(part["logo"], "saved_logo")
        self.assertEqual(part["loadConfig"], [2, 4])
        self.assertEqual(part["autoLoadConfig"], ["1", "0"])
        self.assertEqual(part["maintenanceState"], "0.75")
        self.assertEqual(part["purchaseTime"], "100000")
        self.assertEqual(done["snapshot"]["company"]["balance"], 4479819)

    def test_callback_failure_and_missing_result_halt_without_fallback(self):
        self.h.request("plan", BUY); self.h.request("apply", BUY)
        done = self.h.complete(success=False)
        self.assert_halted(done)
        self.assertFalse(done["receipt"]["success"])
        h = Harness(); h.update(); h.request("plan", BUY); h.request("apply", BUY)
        self.assert_halted(h.complete(no_result=True))
        self.assertNotIn("a:1", h.status()["diagnostics"]["bindings"])

    def test_callback_waits_for_native_read_then_finishes_once(self):
        for operation in ("open", "read", "close", "throw"):
            with self.subTest(operation=operation):
                h = Harness(); h.update()
                command = dict(op="SET_PAUSED", value=True)
                h.request("plan", command); h.request("apply", command)
                h.fail_native_reads(3, operation)
                waiting = h.complete()
                self.assertEqual(waiting["status"], "in_flight")
                self.assertFalse(waiting["complete"])
                self.assertTrue(waiting["receipt"]["success"])
                self.assertEqual(waiting["diagnostics"]["callback_phase"], "await_gate")
                issue = waiting["diagnostics"]["last_native_read_issue"]
                self.assertEqual(issue["operation"], "open" if operation == "throw" else operation)
                if operation != "throw":
                    self.assertEqual(issue["errno"], 13)
                raw = h.lua.globals().files["C:/probe/lua_status.json"]
                writes = h.lua.globals().writes
                for _ in range(2):
                    self.assertEqual(h.update(), waiting)
                    self.assertEqual(h.lua.globals().files["C:/probe/lua_status.json"], raw)
                    self.assertEqual(h.lua.globals().writes, writes)
                done = h.update()
                self.assertEqual(done["status"], "applied")
                self.assertTrue(done["complete"])
                self.assertTrue(done["snapshot"]["paused"])
                self.assertEqual(done["receipt"], waiting["receipt"])
                self.assertEqual(done["diagnostics"]["last_native_read_issue"]["count"], 3)
                self.assertEqual(h.lua.globals().finish_calls, 1)
                self.assertEqual(len(h.lua.globals().sends), 1)
                self.assertIsNone(h.lua.globals().files["C:/probe/native_control.txt"])

    def test_sync_callback_read_wait_is_not_retried_in_same_update(self):
        h = self.h
        h.lua.globals().sync_callback = True
        h.fail_native_reads(0)
        h.lua.execute("local send=api.cmd.sendCommand; api.cmd.sendCommand=function(...) native_failures=1; return send(...) end")
        command = dict(op="SET_PAUSED", value=True)
        h.request("plan", command)
        self.assertEqual(h.request("apply", command)["status"], "in_flight")
        self.assertEqual(h.update()["status"], "applied")
        self.assertEqual(h.lua.globals().finish_calls, 1)
        self.assertEqual(len(h.lua.globals().sends), 1)

    def test_callback_rejection_is_not_hidden_by_unreadable_gate(self):
        h = self.h
        h.request("plan", BUY); h.request("apply", BUY)
        h.fail_native_reads(20)
        done = h.complete(success=False)
        self.assert_halted(done)
        self.assertEqual(done["error"], "engine rejected command")
        self.assertFalse(done["receipt"]["success"])
        self.assertEqual(done["receipt"]["result"]["error"], "engine_rejected")
        self.assertEqual(h.lua.globals().native_failures, 20)
        self.assertEqual(h.lua.globals().finish_calls, 1)
        self.assertNotIn("canonical_state_json", done)

    def test_waiting_callback_native_conflicts_are_terminal_with_receipt(self):
        for changes in ({"fault": 2}, {"runtime_fault": 102}, {"halted": 1},
                        {"epoch": 78}, {"abi": 2}, {"pending_state": 1}, {"completed_frame": 1}):
            with self.subTest(changes=changes):
                h = Harness(); h.update()
                command = dict(op="SET_PAUSED", value=True)
                h.request("plan", command); h.request("apply", command)
                h.fail_native_reads()
                waiting = h.complete()
                h.lua.globals().native_status(0, h.table(changes))
                done = h.update()
                self.assert_halted(done)
                self.assertEqual(done["receipt"], waiting["receipt"])
                self.assertEqual(done["diagnostics"]["last_native_read_issue"]["kind"], "invalid")
                h.lua.globals().native_status(0)
                self.assertEqual(h.update(), done)
                self.assertEqual(h.lua.globals().finish_calls, 1)
                self.assertEqual(len(h.lua.globals().sends), 1)

    def test_waiting_callback_still_requires_time_and_pause_observation(self):
        for change, error in (("now=now+0.2", "observed simulation time differs"),
                              ("speed=1", "pause callback did not produce requested pause flag")):
            with self.subTest(change=change):
                h = Harness(); h.update()
                command = dict(op="SET_PAUSED", value=True)
                h.request("plan", command); h.request("apply", command)
                h.fail_native_reads(); receipt = h.complete()["receipt"]
                h.lua.execute(change)
                done = h.update()
                self.assert_halted(done)
                self.assertIn(error, done["error"])
                self.assertEqual(done["receipt"], receipt)
                self.assertNotIn("canonical_state_json", done)
                self.assertEqual(h.lua.globals().finish_calls, 1)

    def test_controller_halt_discards_waiting_completion_before_ack(self):
        h = self.h
        command = dict(op="SET_PAUSED", value=True)
        h.request("plan", command); h.request("apply", command)
        h.fail_native_reads(100)
        receipt = h.complete()["receipt"]
        stopped = h.request("halt")
        self.assert_halted(stopped)
        self.assertEqual(stopped["error"], "controller requested halt")
        self.assertEqual(stopped["receipt"], receipt)
        self.assertNotIn("callback_phase", stopped["diagnostics"])
        h.lua.globals().native_failures = 0
        self.assertEqual(h.update(), stopped)
        self.assertEqual(h.lua.globals().finish_calls, 1)
        self.assertEqual(len(h.lua.globals().sends), 1)

    def test_duplicate_callback_during_gate_wait_never_repeats_finish(self):
        h = self.h
        command = dict(op="SET_PAUSED", value=True)
        h.request("plan", command); h.request("apply", command)
        h.fail_native_reads(2)
        receipt = h.complete()["receipt"]
        stopped = h.complete()
        self.assert_halted(stopped)
        self.assertEqual(stopped["error"], "engine callback invoked more than once")
        self.assertEqual(stopped["receipt"], receipt)
        h.lua.globals().native_failures = 0
        self.assertEqual(h.update(), stopped)
        self.assertEqual(h.lua.globals().finish_calls, 1)
        self.assertEqual(len(h.lua.globals().sends), 1)

    def test_gate_wait_retries_incomplete_and_not_ready_status_without_ack(self):
        for kind in ("newline", "field", "ready"):
            with self.subTest(kind=kind):
                h = Harness(); h.update()
                command = dict(op="SET_PAUSED", value=True)
                h.request("plan", command); h.request("apply", command)
                files = h.lua.globals().files
                old = files["C:/probe/native_status.txt"]
                damaged = old[:-1] if kind == "newline" else old.replace("ready=1\n", "" if kind == "field" else "ready=0\n")
                files["C:/probe/native_status.txt"] = damaged
                waiting = h.complete()
                self.assertEqual(waiting["status"], "in_flight")
                self.assertFalse(waiting["complete"])
                self.assertEqual(h.update(), waiting)
                files["C:/probe/native_status.txt"] = old
                self.assertEqual(h.update()["status"], "applied")
                self.assertEqual(h.lua.globals().finish_calls, 1)

    def test_wait_status_write_failure_retries_without_sending_again(self):
        h = self.h
        command = dict(op="SET_PAUSED", value=True)
        h.request("plan", command); h.request("apply", command)
        h.fail_native_reads(3)
        h.lua.globals().write_fail = True
        h.complete()
        h.update()
        self.assertEqual(h.lua.globals().finish_calls, 1)
        h.lua.globals().write_fail = False
        waiting = h.update()
        self.assertEqual(waiting["status"], "in_flight")
        self.assertEqual(waiting["diagnostics"]["callback_phase"], "await_gate")
        self.assertEqual(h.update()["status"], "applied")
        self.assertEqual(len(h.lua.globals().sends), 1)

    def test_new_plan_does_not_retain_previous_command_receipt(self):
        h = self.h
        h.run(dict(op="SET_PAUSED", value=True))
        self.assertIn("receipt", h.status())
        h.request("plan", BUY, key="a:2")
        stopped = h.request("halt")
        self.assert_halted(stopped)
        self.assertNotIn("receipt", stopped)

    def test_future_work_while_callback_waits_halts_even_if_gate_is_unreadable(self):
        h = self.h
        command = dict(op="SET_PAUSED", value=True)
        h.request("plan", command); h.request("apply", command)
        h.fail_native_reads(10)
        receipt = h.complete()["receipt"]
        stopped = h.request("snapshot")
        self.assert_halted(stopped)
        self.assertEqual(stopped["error"], "command callback still pending")
        self.assertEqual(stopped["receipt"], receipt)
        h.lua.globals().native_failures = 0
        self.assertEqual(h.update(), stopped)
        self.assertEqual(h.lua.globals().finish_calls, 1)
        self.assertEqual(len(h.lua.globals().sends), 1)

    def test_receipt_requires_bounded_plain_integer_data(self):
        for returned in ("42", "{success='true',result={}}", "{success=true,result={cost=0.5}}",
                         "{success=true,result={opaque=function()end}}", "{success=true,result={text=string.rep('x',33000)}}"):
            with self.subTest(returned=returned):
                h = Harness(); h.update()
                h.lua.execute("observed_engine.finish=function() finish_calls=finish_calls+1; return " + returned + " end")
                command = dict(op="SET_PAUSED", value=True)
                h.request("plan", command); h.request("apply", command)
                stopped = h.complete()
                self.assert_halted(stopped)
                self.assertNotIn("receipt", stopped)
                self.assertNotIn("canonical_state_json", stopped)
                self.assertEqual(h.lua.globals().finish_calls, 1)

    def test_native_read_diagnostic_is_bounded_and_integer_only(self):
        h = self.h
        command = dict(op="SET_PAUSED", value=True)
        h.request("plan", command); h.request("apply", command)
        h.lua.execute("local original=io.open; io.open=function(path,mode) if path=='C:/probe/native_status.txt' then return nil,string.rep('x',300),0.5 end;return original(path,mode) end")
        issue = h.complete()["diagnostics"]["last_native_read_issue"]
        self.assertEqual(len(issue["error"]), 256)
        self.assertNotIn("errno", issue)

    def test_callback_diagnostics_are_optional_and_cannot_mask_rejection(self):
        for body, valid in (("return {success=false,error_state='construction rejected',result={cost='0.5'}}", True),
                            ("error('diagnostic unavailable',0)", False),
                            ("return {cost=0.5}", False),
                            ("return {detail=string.rep('x',17000)}", False)):
            with self.subTest(body=body):
                h = Harness(); h.update()
                h.config.profile = "build_v2"  # Exercise halt diagnostics with the same generic engine fixture.
                h.lua.execute("observed_engine.callback_diagnostics=function() " + body + " end")
                h.request("plan", BUY); h.request("apply", BUY)
                stopped = h.complete(success=False)
                self.assert_halted(stopped)
                self.assertEqual(stopped["error"], "engine rejected command")
                failure = stopped["diagnostics"]["failure"]
                if valid:
                    self.assertFalse(failure["callback"]["success"])
                    self.assertEqual(failure["callback"]["result"]["cost"], "0.5")
                else:
                    self.assertNotIn("callback", failure)
                    self.assertIn("callback_error", failure)

    def test_duplicate_callback_halts(self):
        self.h.run(dict(op="SET_PAUSED", value=True))
        self.assert_halted(self.h.complete())

    def test_controller_halt_during_callback_stays_halted(self):
        self.h.request("plan", BUY); self.h.request("apply", BUY)
        self.assert_halted(self.h.request("halt"))
        self.assert_halted(self.h.complete())
        self.assertEqual(self.h.status()["receipt"]["bindings"]["a:1"], 900)

    def test_native_fault_pending_or_wrong_epoch_refuse_execution(self):
        for changes in ({"halted": 1}, {"epoch": 78}, {"pending_state": 2}, {"win32_error": 0, "runtime_fault": 9}):
            h = Harness(); h.update(); h.request("plan", BUY)
            h.lua.globals().native_status(0, h.table(changes))
            self.assert_halted(h.request("apply", BUY))
            self.assertEqual(len(h.lua.globals().sends), 0)

    def test_old_abi_and_unsupported_native_step_halt_before_command(self):
        for changes in ({"abi": 2}, {"native_step_us": 100000}, {"native_step_us": 0},
                        {"native_step_us": 200001}):
            h = Harness(bindings=False)
            h.lua.globals().native_status(0, h.table(changes))
            self.assert_halted(h.update())
            self.assertEqual(len(h.lua.globals().sends), 0)

    def test_missing_native_step_declaration_halts_but_partial_file_never_acknowledges(self):
        h = Harness(bindings=False)
        files = h.lua.globals().files
        original = files["C:/probe/native_status.txt"]
        files["C:/probe/native_status.txt"] = original.replace("native_step_us=200000\n", "")
        self.assert_halted(h.update())
        self.assertEqual(len(h.lua.globals().sends), 0)
        h = Harness(bindings=False)
        files = h.lua.globals().files
        files["C:/probe/native_status.txt"] = files["C:/probe/native_status.txt"][:-1]
        self.assertIsNone(h.update())
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_snapshot_after_declared_200000_microsecond_boundary(self):
        h = Harness(bindings=False)
        h.lua.execute("now=0; speed=1")
        self.assertEqual(h.update()["snapshot"]["sim_time_us"], 0)
        h.lua.execute("now=0.2")
        h.lua.globals().native_status(1)
        observed = h.request("snapshot", expected=200000, boundary="1")
        self.assertEqual(observed["status"], "ready")
        self.assertEqual(observed["snapshot"]["sim_time_us"], 200000)
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_write_failure_before_send_never_dispatches(self):
        self.h.request("plan", BUY)
        self.h.lua.globals().write_fail = True
        self.h.request("apply", BUY)
        self.assertEqual(len(self.h.lua.globals().sends), 0)
        self.h.lua.globals().write_fail = False
        self.assert_halted(self.h.update())

    def test_completed_acknowledgement_stays_readable_during_duplicate_polling(self):
        receipt=self.h.request("snapshot")
        count=self.h.lua.globals().writes
        for _ in range(20):
            self.assertEqual(self.h.update(),receipt)
        self.assertEqual(self.h.lua.globals().writes,count)
        newer=self.h.request("snapshot")
        self.assertGreater(newer['revision'],receipt['revision'])
        self.assertGreater(self.h.lua.globals().writes,count)

    def test_partial_and_oversized_mailbox(self):
        self.h.lua.globals().files["C:/probe/lua_control.json"] = '{"protocol":1'
        self.assertEqual(self.h.update()["request"], 0)
        self.assertEqual(self.h.request("snapshot")["request"], 1)
        self.h.lua.globals().files["C:/probe/lua_control.json"] = " " * 262145
        self.assert_halted(self.h.update())

    def test_snapshot_detects_vehicle_state_route_config_and_position(self):
        for mutation in ("world[200].TRANSPORT_VEHICLE.userStopped=false", "world[200].TRANSPORT_VEHICLE.line=300", "world[200].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].part.reversed=false", "legacy[200].position={1,2,3}"):
            h = Harness(); before = h.update()["canonical_state_json"]
            h.lua.execute(mutation)
            after = h.request("snapshot")
            self.assertEqual(after["status"], "ready", after)
            self.assertNotEqual(before, after["canonical_state_json"])

    def test_raw_local_ids_do_not_affect_canonical_snapshot(self):
        h = Harness(offset=1000)
        other = h.update()
        self.assertEqual(self.h.status()["canonical_state_json"], other["canonical_state_json"])
        self.assertNotEqual(self.h.status()["diagnostics"], other["diagnostics"])

    def test_all_concrete_intents(self):
        for command in (DEPOT, LINE, dict(op="LINE_UPDATE", line="seed:line", waiting_time="30", stops=[STOP]), dict(op="VEHICLE_ASSIGN", vehicle="seed:vehicle", line="seed:line", stop_index=0)):
            h = Harness(); h.update()
            done = h.run(command)
            self.assertEqual(done["status"], "applied", done)

    def test_road_is_refused_before_execution_because_native_mapping_is_missing(self):
        done=self.h.request("plan", ROAD)
        self.assert_halted(done)
        self.assertIn("exact created road entity mapping is not implemented", done["error"])
        self.assertEqual(len(self.h.lua.globals().sends), 0)

    def test_missing_api_field_is_explicit_and_not_guessed(self):
        self.h.lua.execute("world[200].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].part.logo=nil")
        self.assert_halted(self.h.request("plan", BUY))
        self.assertIn("capability_missing", self.h.status()["error"])
        h = Harness(); h.update(); h.lua.execute("api.cmd.make.createLine=function()return{}end")
        self.assert_halted(h.request("plan", LINE))
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_zero_loaded_time_snapshot_and_pause_work(self):
        h = Harness(bindings=False); h.lua.execute("now=0")
        self.assertEqual(h.update()["snapshot"]["sim_time_us"], 0)
        c = dict(op="SET_PAUSED", value=True)
        self.assertEqual(h.request("plan", c, expected=0)["status"], "planned")
        h.request("apply", c, expected=0)
        self.assertEqual(h.complete()["status"], "applied")

    def test_saved_active_session_cannot_replay(self):
        h = Harness(saved=True)
        self.assert_halted(h.update())
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_unbound_reference_and_invalid_stop_do_not_guess(self):
        self.h.lua.execute("world[200].TRANSPORT_VEHICLE.line=999")
        self.assert_halted(self.h.request("snapshot"))
        h = Harness(); h.update()
        self.assert_halted(h.request("plan", dict(LINE, stops=[dict(STOP, terminal=50)])))
        self.assertEqual(len(h.lua.globals().sends), 0)

    def test_geometrically_identical_disconnected_nodes_are_detected(self):
        h = Harness()
        h.lua.execute("add_road(600,502,602,{x=10,y=0,z=0},{x=20,y=0,z=0});bindings[#bindings+1]={logical_id='seed:road2',kind='road',entity=600}")
        before = h.update()["canonical_state_json"]
        h.lua.execute("world[603]={BASE_NODE={position={x=10,y=0,z=0}}};world[600].BASE_EDGE.node0=603")
        after = h.request("snapshot")
        self.assertEqual(after["status"], "ready")
        self.assertNotEqual(before, after["canonical_state_json"])


if __name__ == "__main__":
    success = True
    for variant in ("lua51", "lua52", "lua53", "lua54"):
        RUNTIME = importlib.import_module("lupa." + variant).LuaRuntime
        print("\nProduction Lua adapter:", variant, flush=True)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProductionLuaTests)
        success = unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() and success
    raise SystemExit(0 if success else 1)
