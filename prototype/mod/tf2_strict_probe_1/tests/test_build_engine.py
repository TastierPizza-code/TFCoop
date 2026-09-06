"""Literal bounded build adapter checks; fake native fields, no game process."""
from pathlib import Path
import importlib
import json
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'tests/lua/.deps'))
SCRIPTS = HERE.parent / 'res/scripts/tf2_strict_probe'
RUNTIME = None
COMMANDS = [('a:1', {'op':'SET_PAUSED','value':True}), ('a:2',{'op':'PROBE_ROAD'}),
 ('b:1',{'op':'PROBE_DEPOT'}), ('a:3',{'op':'PROBE_STOP','index':0}),
 ('b:2',{'op':'PROBE_STOP','index':1}), ('b:3',{'op':'PROBE_VEHICLE'}),
 ('a:4',{'op':'PROBE_LINE'}), ('b:4',{'op':'PROBE_ASSIGN'})]

class Harness:
    def __init__(self, offset=0, setup='', bind=True):
        self.lua=RUNTIME(unpack_returned_tuples=True)
        self.j=self.lua.execute((SCRIPTS/'json.lua').read_text())
        self.assets=self.lua.execute((SCRIPTS/'build_assets.lua').read_text())
        self.lua.globals().assets=self.assets
        self.lua.globals().id_offset=offset
        self.lua.execute((HERE/'fake_build_engine.lua').read_text())
        self.lua.execute(setup)
        self.lua.globals().require=lambda name: self.assets if name=='tf2_strict_probe/build_assets' else None
        self.module=self.lua.execute((SCRIPTS/'build_engine.lua').read_text())
        self.e=self.module.new(self.j)
        if bind:self.e.bind_initial(self.table([]))
    def table(self, value):return self.j.decode(json.dumps(value))
    def snapshot(self):return json.loads(self.j.encode(self.e.snapshot()))
    def plan(self,key,command):return self.e.plan(self.table(command),key,int(round(self.lua.globals().now*1_000_000)))
    def apply(self,key,command,no_result=False):
        before=self.snapshot()
        plan=self.plan(key,command)
        assert self.snapshot()==before, 'planning mutated observed world'
        result=self.lua.globals().apply_command(plan.native,no_result)
        self.e.finish(plan,result,True)
        return self.snapshot()
    def build(self):
        for key,cmd in COMMANDS:self.apply(key,cmd)
        return self.snapshot()

class BuildEngineTests(unittest.TestCase):
    def test_site_initialization_is_read_only_dry_and_bounded(self):
        h=Harness();s=h.snapshot()
        self.assertEqual(h.lua.globals().sent,0)
        self.assertEqual(s['objects'],[])
        self.assertEqual(s['probe']['site']['z_mm'],10000)
        self.assertEqual(s['probe']['site']['water_level'],'0')
        self.assertEqual(len(s['probe']['site']['height_samples']),169)
        self.assertEqual(len(s['probe']['terrain_height_samples']),25)

    def test_underwater_site_refuses_without_world_commands(self):
        with self.assertRaisesRegex(Exception,'build_site_unavailable'):
            Harness(setup='world[0].TERRAIN.waterLevel=20')

    def test_site_skips_observed_existing_road(self):
        h=Harness(setup='''
          world[20]={BASE_EDGE={}}
          api.engine.system.octreeSystem.findIntersectingEntities=function(box,fn)
            if box.min.x<0 and box.max.x>0 and box.min.y<0 and box.max.y>0 then fn(20) end
          end
        ''')
        self.assertNotEqual(h.snapshot()['probe']['site']['x_mm'],0)

    def test_site_finds_dry_land_beyond_old_central_search(self):
        setup='''
          api.engine.terrain.isValidCoordinate=function(p)return math.abs(p.x)<8192 and math.abs(p.y)<8192 end
          api.engine.terrain.getHeightAt=function(p)return p.x>4000 and 10 or 0 end
        '''
        a,b=Harness(setup=setup),Harness(offset=10000,setup=setup)
        self.assertGreater(a.snapshot()['probe']['site']['x_mm'],4_000_000)
        self.assertEqual(a.snapshot(),b.snapshot())
        self.assertLessEqual(a.e.site_diagnostics.examined,4225)
        self.assertEqual(a.lua.globals().sent,0)

    def test_gentle_slope_uses_observed_midpoint_with_bounded_alignment(self):
        h=Harness(setup='''
          api.engine.terrain.isValidCoordinate=function(p)return math.abs(p.x)<8192 and math.abs(p.y)<8192 end
          api.engine.terrain.getHeightAt=function(p)return 200+.02*p.x end
        ''')
        site=h.snapshot()['probe']['site']
        self.assertGreater(float(site['terrain_preparation']['sampled_span_m']),2)
        self.assertLessEqual(float(site['terrain_preparation']['sampled_span_m']),8)
        heights=list(map(float,site['height_samples']))
        self.assertAlmostEqual(site['z_mm']/1000,(min(heights)+max(heights))/2,places=3)
        self.assertEqual(h.e.site_diagnostics.examined,4225)
        self.assertEqual(h.lua.globals().sent,0)

    def test_steep_or_wet_map_reports_filters_and_never_dispatches(self):
        for terrain,reason in [('return 0','water'),('return 1000+.1*p.x','too_uneven')]:
            h=Harness(bind=False,setup='''
              api.engine.terrain.isValidCoordinate=function(p)return math.abs(p.x)<8192 and math.abs(p.y)<8192 end
              api.engine.terrain.getHeightAt=function(p) '''+terrain+''' end
            ''')
            with self.assertRaisesRegex(Exception,'build_site_unavailable: checked=4225'):
                h.e.bind_initial(h.table([]))
            self.assertEqual(h.e.site_diagnostics.rejected[reason],4225)
            self.assertEqual(h.lua.globals().sent,0)

    def test_refinement_rejects_wet_hole_between_coarse_samples(self):
        h=Harness(setup='''
          api.engine.terrain.isValidCoordinate=function(p)return math.abs(p.x)<8192 and math.abs(p.y)<8192 end
          api.engine.terrain.getHeightAt=function(p)
            if math.abs(p.x+133.333333)<1 and math.abs(p.y+133.333333)<1 then return 0 end
            return 10
          end
        ''')
        site=h.snapshot()['probe']['site']
        self.assertNotEqual((site['x_mm'],site['y_mm']),(0,0))
        self.assertGreaterEqual(h.e.site_diagnostics.rejected.water,1)

    def test_observed_terrain_change_enters_digest_without_changing_selected_site(self):
        h=Harness();before=h.snapshot()
        h.lua.execute('api.engine.terrain.getHeightAt=function()return 11 end')
        after=h.snapshot()
        self.assertEqual(before['probe']['site'],after['probe']['site'])
        self.assertNotEqual(before['probe']['terrain_height_samples'],after['probe']['terrain_height_samples'])

    def test_small_map_never_queries_outside_valid_coordinates(self):
        h=Harness(setup='''
          api.engine.terrain.isValidCoordinate=function(p)return math.abs(p.x)<256 and math.abs(p.y)<256 end
          api.engine.terrain.getHeightAt=function(p)
            assert(api.engine.terrain.isValidCoordinate(p),'queried outside terrain');return 10
          end
        ''')
        self.assertEqual(h.snapshot()['probe']['site']['x_mm'],0)

    def test_bad_coordinate_api_result_refuses_before_any_action(self):
        for value in ('nil',"'true'"):
            h=Harness(bind=False,setup='api.engine.terrain.isValidCoordinate=function()return '+value+' end')
            with self.assertRaisesRegex(Exception,'build boolean unavailable'):
                h.e.bind_initial(h.table([]))
            self.assertEqual(h.lua.globals().sent,0)

    def test_complete_scene_reads_callback_ids_native_matrix_and_copy_vectors(self):
        h=Harness();s=h.build()
        self.assertEqual(s['coverage']['missing'],[])
        self.assertTrue(s['probe']['connectivity']['connected'])
        self.assertEqual(s['probe']['scene'],dict(road='a:2',depot='b:1',stops=['a:3','b:2'],vehicle='b:3',line='a:4'))
        self.assertEqual(s['probe']['line']['vehicles'],['b:3'])
        self.assertEqual(s['probe']['line']['stops'],['a:3','b:2'])
        self.assertTrue(s['probe']['vehicle']['in_depot'])
        self.assertNotIn('position_mm',s['probe']['vehicle'])
        self.assertLess(s['company']['balance'],5_000_000)
        h.lua.globals().advance();s=h.snapshot()
        self.assertEqual(s['coverage']['missing'],[])
        self.assertEqual(s['probe']['vehicle']['state'],1)
        self.assertFalse(s['probe']['vehicle']['in_depot'])
        first=s['probe']['vehicle']['position_mm']
        h.lua.globals().advance();self.assertNotEqual(first,h.snapshot()['probe']['vehicle']['position_mm'])

    def test_equal_world_with_different_entity_ids_has_equal_digest_data(self):
        a,b=Harness(0),Harness(10000)
        self.assertEqual(a.build(),b.build())
        a.lua.globals().advance();b.lua.globals().advance()
        self.assertEqual(a.snapshot(),b.snapshot())

    def test_native_observed_params_preserve_nested_and_engine_added_values(self):
        h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        self.assertEqual(h.lua.eval('type(world[road_id].CONSTRUCTION.params)'), 'userdata')
        h.lua.execute('''
          world[road_id].CONSTRUCTION.params=native_params({seed=1,
            engine_added={flags={enabled=false},[12]='numeric key',['12']='string key'}})
        ''')
        before=h.snapshot();self.assertEqual(before['coverage']['missing'],[])
        params=before['objects'][0]['state']['params']
        added=next(item['value'] for item in params if item['key']=='engine_added')
        self.assertEqual({(i['key_type'],i['key']) for i in added},
                         {('number','12'),('string','12'),('string','flags')})
        h.lua.execute('world[road_id].CONSTRUCTION.params.engine_added.flags.enabled=true')
        self.assertNotEqual(before,h.snapshot())
        h.lua.execute("world[road_id].CONSTRUCTION.params.seed='1'")
        changed=h.snapshot()['objects'][0]['state']['params']
        self.assertEqual(next(i['value_type'] for i in changed if i['key']=='seed'),'string')
        self.assertNotEqual(params,changed)

    def test_plain_and_nested_native_params_have_same_canonical_data(self):
        h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        h.lua.execute("world[road_id].CONSTRUCTION.params={seed=1,nested={false,'x',3},empty={}}")
        plain=h.snapshot()
        for mode in ('pairs','members'):
            h.lua.execute("world[road_id].CONSTRUCTION.params=native_params({seed=1,nested={false,'x',3},empty={}},'"+mode+"')")
            self.assertEqual(plain,h.snapshot())

    def test_unreadable_or_partial_native_params_never_become_empty_proof(self):
        cases=[
          ("native_params({seed=1},'opaque')",'observed params $: userdata'),
          ("{seed=1,bad=function()end}",'unsupported value type function'),
        ]
        for value,reason in cases:
            h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().road_id=h.e.local_bindings()['a:2']
            h.lua.execute('world[road_id].CONSTRUCTION.params='+value)
            s=h.snapshot()
            self.assertTrue(any(reason in error for error in s['coverage']['missing']))
            self.assertEqual(s['objects'][0]['state'],{'unavailable':True})
        h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        h.lua.execute('''
          local p=native_params({seed=1});getmetatable(p).__pairs=function()
            local first=true;return function()
              if first then first=false;return 'seed',1 end;error('fixture iterator failed')
            end
          end
          world[road_id].CONSTRUCTION.params=p
        ''')
        s=h.snapshot()
        self.assertTrue(any('fixture iterator failed' in error for error in s['coverage']['missing']))
        self.assertEqual(s['objects'][0]['state'],{'unavailable':True})

    def test_native_params_cycles_width_and_member_failures_are_bounded(self):
        cases=[
          ("local p={};p.loop=p;world[road_id].CONSTRUCTION.params=native_params(p)",'cycle'),
          ("local p={};for i=1,257 do p[i]=i end;world[road_id].CONSTRUCTION.params=native_params(p)",'width exceeded'),
          ("local p=native_params({seed=1},'members');getmetatable(p).__index=function()error('unreadable')end;world[road_id].CONSTRUCTION.params=p",'member read failed'),
          ("local p=native_params({seed=1},'members');getmetatable(p).__members={'seed','seed'};world[road_id].CONSTRUCTION.params=p",'duplicate key'),
        ]
        for setup,reason in cases:
            h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().road_id=h.e.local_bindings()['a:2']
            h.lua.execute(setup)
            self.assertTrue(any(reason in error for error in h.snapshot()['coverage']['missing']),reason)

    def test_native_params_depth_total_nodes_and_text_have_finite_limits(self):
        cases=[
          ("local p={};local node=p;for i=1,12 do node.child={};node=node.child end;world[road_id].CONSTRUCTION.params=native_params(p)",'depth exceeded'),
          ("local p={};for i=1,50 do p[i]={};for j=1,100 do p[i][j]=j end end;world[road_id].CONSTRUCTION.params=native_params(p)",'node budget exceeded'),
          ("world[road_id].CONSTRUCTION.params=native_params({large=string.rep('x',1048577)})",'text budget exceeded'),
        ]
        for setup,reason in cases:
            h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().road_id=h.e.local_bindings()['a:2']
            h.lua.execute(setup)
            self.assertTrue(any(reason in error for error in h.snapshot()['coverage']['missing']),reason)

    def test_callback_output_need_not_exist_before_execution(self):
        h=Harness();h.build()  # Every fake maker omits all result fields.
        self.assertEqual(h.lua.globals().sent,8)

    def test_missing_actual_callback_identity_refuses(self):
        h=Harness()
        with self.assertRaisesRegex(Exception,'callback has no resultEntities'):
            h.apply('a:1',{'op':'PROBE_ROAD'},no_result=True)

    def test_station_group_may_share_authoritative_construction_entity(self):
        h=Harness()
        h.lua.execute('''
          local original=apply_command
          apply_command=function(cmd,no_result)
            local r=original(cmd,no_result)
            if cmd.op=='build' and cmd.proposal.constructionsToAdd[1].fileName==assets.stop_file then
              local id=r.resultEntities[1];local station=world[id].CONSTRUCTION.stations[1]
              local old=world[station].group;world[id].STATION_GROUP=world[old].STATION_GROUP
              world[station].group=id;world[old]=nil
            end
            return r
          end
        ''')
        s=h.build()
        self.assertEqual(s['coverage']['missing'],[])
        self.assertEqual(s['probe']['line']['stops'],['a:3','b:2'])
        self.assertEqual(h.e.local_bindings()['a:3'],h.e.local_bindings()['a:3:group'])

    def test_transient_departure_does_not_invent_world_position(self):
        h=Harness();h.build();h.lua.execute('world[vehicle_id].TRANSPORT_VEHICLE.state=1')
        s=h.snapshot()
        self.assertEqual(s['coverage']['missing'],[])
        self.assertFalse(s['probe']['vehicle']['world_position_present'])
        self.assertNotIn('position_mm',s['probe']['vehicle'])
        h.lua.globals().advance()
        self.assertIn('position_mm',h.snapshot()['probe']['vehicle'])

    def test_broken_copy_vector_writeback_refuses_before_buy(self):
        h=Harness()
        for key,command in COMMANDS[:5]:h.apply(key,command)
        h.lua.execute('''
          api.type.TransportVehiclePart.new=function()
            return setmetatable({},{__index=function(_,k)if k=='autoLoadConfig'then return{}end end,
              __newindex=function(self,k,v)if k~='autoLoadConfig'then rawset(self,k,v)end end})
          end
        ''')
        sent=h.lua.globals().sent
        with self.assertRaisesRegex(Exception,'one-compartment'):
            h.plan('b:3',{'op':'PROBE_VEHICLE'})
        self.assertEqual(h.lua.globals().sent,sent)

    def test_no_model_refuses_before_world_mutation(self):
        with self.assertRaisesRegex(Exception,'build_vehicle_model_unavailable'):
            Harness(setup='api.res.modelRep.find=function()return -1 end')

    def test_dependency_and_unexpected_fields_refuse_before_mutation(self):
        for command in ({'op':'PROBE_ASSIGN'},{'op':'PROBE_VEHICLE'}, {'op':'PROBE_ROAD','position':[0,0,0]}):
            h=Harness()
            with self.assertRaises(Exception):h.plan('a:1',command)
            self.assertEqual(h.lua.globals().sent,0)

    def test_stale_or_unknown_line_reference_is_unreadable(self):
        h=Harness();h.build();h.lua.execute('world[vehicle_id].TRANSPORT_VEHICLE.line=999999')
        self.assertTrue(h.snapshot()['coverage']['missing'])

    def test_disconnected_equal_coordinate_node_changes_actual_connectivity(self):
        h=Harness();before=h.build()
        h.lua.globals().depot_entity=h.e.local_bindings()['b:1']
        h.lua.execute('''
          local e=world[world[depot_entity].CONSTRUCTION.frozenEdges[1]].BASE_EDGE
          local id=fresh();world[id]={BASE_NODE={position=copy(world[e.node0].BASE_NODE.position)}};e.node0=id
        ''')
        after=h.snapshot()
        self.assertNotEqual(before,after)
        self.assertFalse(after['probe']['connectivity']['connected'])

if __name__=='__main__':
    ok=True
    for variant in ('lua51','lua52','lua53','lua54'):
        RUNTIME=importlib.import_module('lupa.'+variant).LuaRuntime
        print('Build adapter:',variant,flush=True)
        ok=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(BuildEngineTests)).wasSuccessful() and ok
    raise SystemExit(0 if ok else 1)
