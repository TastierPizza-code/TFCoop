"""Passive raw-shape diagnostics on literal Lua 5.1-5.4, never a game process."""
from pathlib import Path
import importlib
import json
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'tests/lua/.deps'))
SCRIPTS = HERE.parent / 'res/scripts/tf2_api_audit'
RUNTIME = None

class Harness:
    def __init__(self, setup=''):
        self.lua = RUNTIME(unpack_returned_tuples=True)
        self.j = self.lua.execute((SCRIPTS/'json.lua').read_text(encoding='utf-8'))
        self.lua.execute((HERE/'fake_api.lua').read_text(encoding='utf-8'))
        self.lua.execute('logs={};print=function(value)logs[#logs+1]=value end')
        self.p = self.lua.execute((SCRIPTS/'probe.lua').read_text(encoding='utf-8'))
        self.lua.execute(setup)
    def collect(self, options=None):
        opt=self.j.decode(json.dumps(options or {'request_id':'a'*32}))
        self.report=self.p.collect(self.lua.globals().api,self.lua.globals().game,self.j,opt)
        self.raw=self.j.encode(self.report)
        return json.loads(self.raw)
    def script(self, path, enabled=True, broken=False):
        cfg=self.j.decode(json.dumps({'enabled':enabled,'request_id':'a'*32,'output_file':str(path).replace('\\','/')}))
        probe=self.p
        if broken:
            self.lua.globals().audit=self.p
            probe=self.lua.execute("return {safe_text=audit.safe_text, collect=function()error('broken 0xDEADBEEF',0)end}")
        modules={'tf2_api_audit/config':cfg,'tf2_api_audit/json':self.j,'tf2_api_audit/probe':probe}
        self.lua.globals().require=lambda key:modules[key]
        self.lua.execute((HERE.parent/'res/config/game_script/tf2_api_audit.lua').read_text(encoding='utf-8'))
        return self.lua.globals().data()

def rows(report, path):
    return [r for r in report['records'] if r['path']==path]

class ProbeTests(unittest.TestCase):
    def test_literal_native_shapes_and_all_independent_bad_leaves(self):
        h=Harness(); report=h.collect({'request_id':'b'*32,'bindings':{'road':1}})
        self.assertEqual(h.lua.eval('type(transform)'), 'userdata')
        self.assertFalse(report['valid_snapshot'])
        self.assertEqual(report['format'],1)
        self.assertEqual(report['mode'],'read_only_api_audit')
        self.assertEqual(report['request_id'],'b'*32)
        p='bindings.road.CONSTRUCTION'
        self.assertEqual(rows(report,p+'.params.bad')[0]['access'],'throws')
        self.assertEqual(rows(report,p+'.params.valid')[0]['value'],3)
        self.assertEqual(rows(report,p+'.transf.col')[0]['access'],'throws')
        self.assertEqual(rows(report,p+'.transf.1')[0]['type'],'userdata')
        self.assertEqual(rows(report,p+'.transf.1.x')[0]['value'],1)
        self.assertEqual(rows(report,p+'.transf.16')[0]['access'],'throws')
        self.assertEqual(rows(report,p+'.timeBuild')[0]['numeric']['value'],13400)
        self.assertNotIn('0x123456',h.raw)
        self.assertEqual(h.lua.globals().sent,0)
        self.assertEqual(h.lua.globals().col_called,0)

    def test_missing_numeric_fields_never_coerce_to_valid_numbers(self):
        h=Harness("""
          world[1].CONSTRUCTION=native({params={},transf={},timeBuild='not a number'},
            {fileName='bad filename',frozenNodes='bad nodes'})
        """)
        report=h.collect({'bindings':{'road':1}});p='bindings.road.CONSTRUCTION'
        for name in ('fileName','frozenNodes'):
            self.assertEqual(rows(report,p+'.'+name)[0]['access'],'throws')
        self.assertEqual(rows(report,p+'.transf.1')[0]['access'],'nil')
        number=rows(report,p+'.timeBuild')[0]['numeric']
        self.assertFalse(number['finite']);self.assertFalse(number['safe_integer'])
        self.assertEqual(number['conversion'],'nil')
        self.assertFalse(report['valid_snapshot'])

    def test_nan_infinity_integer_range_and_utf8_never_break_json(self):
        h=Harness("""
          world[1].CONSTRUCTION=native({fileName=string.char(255)..string.rep('ä',300),params={a=0/0,b=math.huge,c=9007199254740992},transf={},timeBuild=-math.huge})
        """)
        r=h.collect({'bindings':{'road':1}});p='bindings.road.CONSTRUCTION'
        self.assertEqual(rows(r,p+'.timeBuild')[0]['value_text'],'-Infinity')
        self.assertEqual(rows(r,p+'.params.a')[0]['value_text'],'NaN')
        self.assertEqual(rows(r,p+'.params.b')[0]['value_text'],'+Infinity')
        self.assertFalse(rows(r,p+'.params.c')[0]['numeric']['safe_integer'])
        self.assertTrue(rows(r,p+'.fileName')[0]['value_truncated'])
        self.assertLessEqual(len(h.raw.encode()),98304)

    def test_world_sampling_captures_live_vehicle_and_constructor_defaults_separately(self):
        h=Harness();r=h.collect()
        self.assertEqual(r['status'],'completed')
        self.assertEqual(rows(r,'entities.TRANSPORT_VEHICLE.1.TRANSPORT_VEHICLE.stopIndex')[0]['value'],0)
        self.assertEqual(rows(r,'entities.MOVE_PATH.1.MOVE_PATH.dyn.pathPos.pos01')[0]['value'],.3)
        for name in ('Mat4f','Vec2f','Vec3f','Vec4f','VehiclePart','TransportVehiclePart','TransportVehicleConfig','Line','Line.Stop'):
            self.assertTrue(rows(r,'constructor.'+name),name)
            self.assertEqual(rows(r,'constructor.'+name)[0]['origin'],'constructor')
        self.assertEqual(h.lua.globals().sent,0)
        self.assertEqual(h.lua.globals().col_called,0)

    def test_sampling_max_two_and_enumeration_failure_isolated(self):
        h=Harness("""
          for id=20,1000 do world[id]={NAME=native({name='object'})}end
          local original=api.engine.forEachEntityWithComponent
          api.engine.forEachEntityWithComponent=function(fn,k)
            if k=='CONSTRUCTION'then error('enumeration failed',0)end
            return original(fn,k)
          end
        """)
        r=h.collect()
        self.assertEqual(rows(r,'entities.CONSTRUCTION.@enumeration')[0]['access'],'throws')
        self.assertEqual(len([x for x in r['records'] if x['path'].endswith('.NAME.name')]),2)
        self.assertTrue(rows(r,'entities.TERRAIN.1.TERRAIN.waterLevel'))

    def test_cycles_depth_and_byte_limit_are_explicit(self):
        h=Harness("""
          local x={};x.self=x;world[1].CONSTRUCTION=native({params=x,transf={},timeBuild=3,fileName='a'})
          for i=20,80 do world[i]={CONSTRUCTION=world[1].CONSTRUCTION}end
        """)
        bindings={('name'+str(i))*12:i for i in range(20,32)}
        r=h.collect({'bindings':bindings})
        self.assertTrue(r['truncated'])
        self.assertGreater(r['limits']['dropped_records'],0)
        self.assertLessEqual(len(h.raw.encode('utf-8')),98304)
        self.assertFalse(r['valid_snapshot'])

    def test_all_scene_bindings_and_callback_candidate_fit_binding_limit(self):
        h=Harness("for id=20,40 do world[id]={NAME=native({name='tracked'})}end")
        bindings={'object'+str(i):i for i in range(20,35)}
        r=h.collect({'bindings':bindings})
        self.assertEqual(r['limits']['max_bindings'],16)
        for name in bindings:
            self.assertTrue(rows(r,'bindings.'+name+'.NAME.name'),name)
        self.assertFalse(r['valid_snapshot'])
        self.assertLessEqual(len(h.raw.encode()),98304)

    def test_userdata_throwing_every_leaf_produces_report_not_snapshot(self):
        h=Harness("""
          world[1].CONSTRUCTION=native({})
          api.type.Mat4f.new=function()error('constructor unavailable',0)end
        """)
        r=h.collect({'bindings':{'road':1}})
        self.assertEqual(rows(r,'constructor.Mat4f')[0]['access'],'throws')
        for key in ('params','transf','timeBuild','fileName','frozenNodes','frozenEdges','depots','stations'):
            self.assertEqual(rows(r,'bindings.road.CONSTRUCTION.'+key)[0]['access'],'throws')
        self.assertEqual(r['status'],'completed')
        self.assertFalse(r['valid_snapshot'])

    def test_full_two_sample_world_retains_first_matrix_and_road_at_byte_cap(self):
        h=Harness('local copy={};for id,value in pairs(world)do copy[id+1000]=value end;for id,value in pairs(copy)do world[id]=value end')
        r=h.collect()
        self.assertTrue(r['truncated']);self.assertGreater(r['limits']['dropped_records'],0)
        self.assertLessEqual(len(h.raw.encode()),98304)
        for prefix in ('constructor.Mat4f','entities.CONSTRUCTION.1.CONSTRUCTION.transf'):
            for i in range(17):
                self.assertTrue(rows(r,prefix+'.'+str(i)),prefix+'.'+str(i))
            self.assertTrue(rows(r,prefix+'.1.x'))
        self.assertTrue(rows(r,'entities.CONSTRUCTION.1.CONSTRUCTION.timeBuild'))
        for suffix in ('type','typeIndex','node0','node1','tangent0.x','tangent1.z'):
            self.assertTrue(rows(r,'entities.BASE_EDGE.1.BASE_EDGE.'+suffix),suffix)

    def test_disabled_script_does_not_read_world_or_write(self):
        h=Harness()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path,enabled=False)
            for _ in range(1000):script.update()
            self.assertFalse(path.exists());self.assertEqual(h.lua.globals().gets,0)
            self.assertEqual(h.lua.globals().sent,0)
            self.assertEqual(len(h.lua.globals().logs),0)

    def test_script_waits_for_loaded_player_then_writes_exactly_once(self):
        h=Harness('player_ready=false')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path)
            for _ in range(10):script.update()
            self.assertFalse(path.exists())
            h.lua.execute('player_ready=true');script.update()
            raw=path.read_bytes();self.assertLessEqual(len(raw),98304)
            r=json.loads(raw);self.assertEqual(r['request_id'],'a'*32)
            self.assertEqual(r['status'],'completed');self.assertFalse(r['valid_snapshot'])
            gets=h.lua.globals().gets;path.unlink()
            for _ in range(10):script.update()
            self.assertFalse(path.exists());self.assertEqual(h.lua.globals().gets,gets)
            self.assertEqual(Path(str(path)+'.part').read_bytes(),raw)
            self.assertEqual(h.lua.globals().sent,0)

    def test_script_fatal_error_is_bounded_report_without_pointer(self):
        h=Harness()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path,broken=True);script.update()
            r=json.loads(path.read_text());self.assertEqual(r['status'],'error')
            self.assertEqual(r['records'],[]);self.assertFalse(r['valid_snapshot'])
            self.assertNotIn('0xDEADBEEF',r['error'])

    def test_failed_writes_stop_after_three_without_recollecting(self):
        h=Harness()
        with tempfile.TemporaryDirectory() as td:
            script=h.script(Path(td)/'missing'/'report.json')
            h.lua.execute('open_count=0;local old=io.open;io.open=function(...)open_count=open_count+1;return old(...)end')
            script.update();gets=h.lua.globals().gets
            for _ in range(30):script.update()
            self.assertEqual(h.lua.globals().open_count,1)
            script.update()
            self.assertEqual(h.lua.globals().open_count,2)
            for _ in range(100):script.update()
            self.assertEqual(h.lua.globals().open_count,3)
            self.assertEqual(h.lua.globals().gets,gets)

    def test_transient_write_lock_retries_after_thirty_updates_then_succeeds(self):
        h=Harness()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path)
            h.lua.execute('''
              open_count=0;local old=io.open
              io.open=function(path,mode)
                if mode=='wb'and path:match('%.part$')then
                  open_count=open_count+1
                  if open_count<3 then return nil,'temporary sharing violation' end
                end
                return old(path,mode)
              end
            ''')
            script.update();gets=h.lua.globals().gets
            for attempt in (1,2):
                for _ in range(30):script.update()
                self.assertEqual(h.lua.globals().open_count,attempt)
                self.assertFalse(path.exists())
                script.update()
                self.assertEqual(h.lua.globals().open_count,attempt+1)
            report=json.loads(path.read_text())
            self.assertEqual(report['status'],'completed')
            self.assertEqual(report['request_id'],'a'*32)
            self.assertEqual(h.lua.globals().gets,gets)
            for _ in range(100):script.update()
            self.assertEqual(h.lua.globals().open_count,3)
            self.assertEqual(h.lua.globals().gets,gets)

    def test_publication_succeeds_without_rename_and_logs_bounded_stages(self):
        h=Harness('os.rename=nil;player_ready=false')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path)
            script.load(None);script.load(None)
            for _ in range(10):script.update()
            h.lua.execute('player_ready=true');script.update()
            self.assertEqual(path.read_bytes(),Path(str(path)+'.part').read_bytes())
            lines=list(h.lua.globals().logs.values())
            self.assertTrue(any('status=published' in line for line in lines))
            for stage in ('script_loaded','load_callback','first_update','waiting_for_player','collected','staging_closed','final_closed'):
                self.assertEqual(sum('status='+stage in line for line in lines),1,stage)
            self.assertTrue(all(str(path) not in line and td not in line for line in lines))
            self.assertEqual(h.lua.globals().sent,0)

    def test_partial_final_write_is_detected_and_retried_from_original_staging(self):
        h=Harness()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path)
            h.lua.execute('''
              partial_count=0;staging_writes=0;local old=io.open
              io.open=function(path,mode)
                local f,err=old(path,mode)
                if mode=='wb'and path:match('%.part$')then staging_writes=staging_writes+1 end
                if f and mode=='wb'and path:match('%.json$')then
                  partial_count=partial_count+1
                  if partial_count==1 then return {
                    write=function(_,raw)return f:write(raw:sub(1,31))end,
                    close=function()return f:close()end}end
                end
                return f,err
              end
            ''')
            script.update();gets=h.lua.globals().gets
            with self.assertRaises(json.JSONDecodeError):json.loads(path.read_bytes())
            staged=Path(str(path)+'.part').read_bytes()
            self.assertEqual(json.loads(staged)['status'],'completed')
            self.assertTrue(any('status=final_readback_mismatch' in line for line in h.lua.globals().logs.values()))
            for _ in range(31):script.update()
            self.assertEqual(path.read_bytes(),staged)
            self.assertEqual(h.lua.globals().staging_writes,1)
            self.assertEqual(h.lua.globals().gets,gets)

    def test_writer_throw_logs_no_private_path_or_opaque_pointer(self):
        h=Harness()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path)
            h.lua.execute('io.open=function(path)error(path..": permission denied 0xAB1234",0)end')
            script.update()
            text='\n'.join(h.lua.globals().logs.values())
            self.assertIn('staging_open_failed',text)
            self.assertIn('permission denied [address]',text)
            self.assertNotIn(td,text);self.assertNotIn('0xAB1234',text)

    def test_explicit_close_failure_is_logged_and_never_published(self):
        h=Harness()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path)
            h.lua.execute('''
              close_count=0;local old=io.open
              io.open=function(path,mode)
                local f,err=old(path,mode)
                if f and mode=='wb'then return {
                  write=function(_,raw)return f:write(raw)end,
                  close=function()f:close();close_count=close_count+1;return false,'close failed'end}end
                return f,err
              end
            ''')
            for _ in range(100):script.update()
            self.assertFalse(path.exists())
            self.assertEqual(h.lua.globals().close_count,3)
            text='\n'.join(h.lua.globals().logs.values())
            self.assertIn('status=staging_close_failed failure=close failed',text)
            self.assertIn('status=write_attempts_exhausted',text)
            self.assertNotIn('status=published',text)

    def test_readiness_timeout_writes_one_error_and_stops(self):
        h=Harness('player_ready=false')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json';script=h.script(path)
            for _ in range(599):script.update()
            self.assertFalse(path.exists());script.update()
            r=json.loads(path.read_text());self.assertEqual(r['status'],'error')
            self.assertEqual(h.lua.globals().gets,0)

if __name__=='__main__':
    success=True
    for variant in ('lua51','lua52','lua53','lua54'):
        RUNTIME=importlib.import_module('lupa.'+variant).LuaRuntime
        print('Passive API audit:',variant,flush=True)
        success=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProbeTests)).wasSuccessful() and success
    raise SystemExit(0 if success else 1)
