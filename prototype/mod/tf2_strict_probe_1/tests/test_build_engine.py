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
 ('b:2',{'op':'PROBE_STOP','index':1}), ('a:4',{'op':'PROBE_CONNECT'}), ('b:3',{'op':'PROBE_VEHICLE'}),
 ('a:5',{'op':'PROBE_LINE'}), ('b:4',{'op':'PROBE_ASSIGN'})]

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
            if math.abs(p.x+150)<1 and math.abs(p.y+150)<1 then return 0 end
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
        self.assertEqual(s['probe']['scene'],dict(road='a:2',depot='b:1',stops=['a:3','b:2'],vehicle='b:3',line='a:5',connectors='a:4'))
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

    def disconnected_scene(self,offset=0):
        h=Harness(offset)
        for key,command in COMMANDS[:5]:h.apply(key,command)
        return h

    def assert_no_connector_binding(self,h):
        self.assertIsNone(h.e.scene.connectors)
        self.assertFalse(any(str(key).startswith('a:4') for key,_ in h.e.local_bindings().items()))

    def change_incidence(self,h,body):
        """Replace one owned endpoint collection; keep its real edge values."""
        h.lua.execute('''
          local get=api.engine.system.streetSystem.getNode2StreetEdgeMap
          api.engine.system.streetSystem.getNode2StreetEdgeMap=function()
            local m=get();local values={}
            for _,id in pairs(m[roadends[3]])do values[#values+1]=id end
            local collection=native_incidence(values);local mt=getmetatable(collection)
            incidence_iterator_calls=0;incidence_length_calls=0
        '''+body+'''
            m[roadends[3]]=collection;return m
          end
        ''')

    def assert_incidence_plan_refuses_unchanged(self,h,reason=None):
        before=h.snapshot();bindings=h.j.encode(h.e.local_bindings())
        sent,nextid,money=h.lua.globals().sent,h.lua.globals().nextid,h.lua.globals().money
        with self.assertRaises(Exception) as caught:h.plan('a:4',{'op':'PROBE_CONNECT'})
        if reason:self.assertIn(reason,str(caught.exception))
        self.assert_no_connector_binding(h)
        self.assertEqual(h.snapshot(),before)
        self.assertEqual(h.j.encode(h.e.local_bindings()),bindings)
        self.assertEqual((h.lua.globals().sent,h.lua.globals().nextid,h.lua.globals().money),(sent,nextid,money))

    def test_native_incidence_has_length_and_values_but_no_positional_index_before_and_after_connect(self):
        h=self.disconnected_scene()
        inspect=h.lua.eval('''function()
          local m=api.engine.system.streetSystem.getNode2StreetEdgeMap();local out={}
          for _,node in ipairs({roadends[1],roadends[2],roadends[3],depot_outer,stop_outer[1],stop_outer[2]})do
            local c=m[node];local n=0
            assert(type(c)=='userdata'and c[1]==nil,'fixture must reproduce native nonindexed shape')
            for key,id in pairs(c)do
              assert(type(key)=='string'and type(id)=='number'and world[id].BASE_EDGE)
              n=n+1
            end
            assert(n==#c);out[#out+1]=n
          end
          return out
        end''')
        self.assertEqual([inspect()[i] for i in range(1,7)],[1]*6)
        h.apply('a:4',{'op':'PROBE_CONNECT'})
        self.assertEqual([inspect()[i] for i in range(1,7)],[2]*6)
        self.assertTrue(h.snapshot()['probe']['connectivity']['connected'])

    def test_incidence_iteration_order_does_not_change_connection_identity_or_snapshot(self):
        a,b=self.disconnected_scene(),self.disconnected_scene(offset=10000)
        b.lua.globals().incidence_reverse=True
        self.assertEqual(a.apply('a:4',{'op':'PROBE_CONNECT'}),b.apply('a:4',{'op':'PROBE_CONNECT'}))
        self.assertEqual(a.snapshot()['coverage']['missing'],[])

    def test_plain_incidence_sequences_remain_supported_alongside_native_collections(self):
        h=self.disconnected_scene();self.change_incidence(h,'collection=values')
        self.assertTrue(h.apply('a:4',{'op':'PROBE_CONNECT'})['probe']['connectivity']['connected'])

    def test_incidence_scalar_containers_and_invalid_lengths_refuse_without_world_mutation(self):
        for value in ('17',"'not a collection'",'function()end'):
            with self.subTest(container=value):
                h=self.disconnected_scene();self.change_incidence(h,'collection='+value)
                self.assert_incidence_plan_refuses_unchanged(h,'container unavailable')
        for value in ('nil',"'1'",'true','-1','.5','17','0/0','math.huge'):
            with self.subTest(length=value):
                h=self.disconnected_scene()
                self.change_incidence(h,'mt.__len=function()return '+value+' end; mt.__pairs=function()incidence_iterator_calls=incidence_iterator_calls+1;error("must not enumerate invalid length")end')
                self.assert_incidence_plan_refuses_unchanged(h,'a:4.before[')
                self.assertEqual(h.lua.globals().incidence_iterator_calls,0)

    def test_incidence_requires_numeric_entity_values_and_never_substitutes_valid_keys(self):
        for value in ('nil','true','false','tostring(values[1])','0','-1','1.5','2147483648','0/0','math.huge',"native_params({},'opaque')"):
            with self.subTest(value=value):
                h=self.disconnected_scene()
                self.change_incidence(h,'''mt.__pairs=function()return function()
                  incidence_iterator_calls=incidence_iterator_calls+1
                  if incidence_iterator_calls==1 then return values[1],'''+value+''' end
                end end''')
                self.assert_incidence_plan_refuses_unchanged(h,'a:4.before[')
                self.assertEqual(h.lua.globals().incidence_iterator_calls,1)

    def test_incidence_iterator_creation_and_step_exceptions_fail_closed(self):
        for body,reason in (
            ("mt.__pairs=function()error('fixture iterator creation failed',0)end",'iterator unavailable'),
            ("mt.__pairs=function()return 42 end",'iteration failed'),
            ("mt.__pairs=function()return function()error('fixture iterator step failed',0)end end",'iteration failed'),
            ('''mt.__pairs=function()return function()
              incidence_iterator_calls=incidence_iterator_calls+1
              if incidence_iterator_calls==1 then return 'slot',values[1]end
              error('fixture iterator failed after partial observation',0)
            end end''','iteration failed')):
            with self.subTest(reason=reason,body=body):
                h=self.disconnected_scene();self.change_incidence(h,body)
                self.assert_incidence_plan_refuses_unchanged(h,reason)

    def test_incidence_length_and_terminal_key_must_match_complete_iteration(self):
        for body,reason,calls in (
            ('''mt.__len=function()return 2 end
              mt.__pairs=function()return function()
                incidence_iterator_calls=incidence_iterator_calls+1
                if incidence_iterator_calls==1 then return 'slot',values[1]end
              end end''','count mismatch',2),
            ('''mt.__pairs=function()return function()
                incidence_iterator_calls=incidence_iterator_calls+1;return nil,values[1]
              end end''','terminal value without key',1),
            ('''mt.__pairs=function()return function()
                incidence_iterator_calls=incidence_iterator_calls+1;return incidence_iterator_calls,values[1]
              end end''','exceeded declared length',2)):
            with self.subTest(reason=reason):
                h=self.disconnected_scene();self.change_incidence(h,body)
                self.assert_incidence_plan_refuses_unchanged(h,reason)
                self.assertEqual(h.lua.globals().incidence_iterator_calls,calls)

    def test_incidence_duplicate_entities_are_not_a_second_graph_edge(self):
        h=self.disconnected_scene()
        self.change_incidence(h,'''mt.__len=function()return 2 end
          mt.__pairs=function()return function()
            incidence_iterator_calls=incidence_iterator_calls+1
            if incidence_iterator_calls<=2 then return incidence_iterator_calls,values[1]end
          end end''')
        self.assert_incidence_plan_refuses_unchanged(h,'duplicate incident street edge')
        self.assertEqual(h.lua.globals().incidence_iterator_calls,2)

    def test_incidence_never_ending_iterator_stops_after_sixteen_values_and_one_end_check(self):
        h=self.disconnected_scene()
        h.lua.execute('''
          local m=api.engine.system.streetSystem.getNode2StreetEdgeMap();local prototype
          for _,id in pairs(m[roadends[3]])do prototype=world[id]end
          for i=1,15 do world[fresh()]=copy(prototype)end
        ''')
        self.change_incidence(h,'''assert(#values==16)
          mt.__pairs=function()return function()
            incidence_iterator_calls=incidence_iterator_calls+1
            return incidence_iterator_calls,values[(incidence_iterator_calls-1)%16+1]
          end end''')
        self.assert_incidence_plan_refuses_unchanged(h,'exceeded declared length')
        self.assertEqual(h.lua.globals().incidence_iterator_calls,17)

    def test_incidence_final_length_is_rechecked_and_cannot_disappear_or_change(self):
        for finish,reason in (('return 2','length changed during iteration'),
                              ("error('fixture final length failed',0)",'length read failed')):
            with self.subTest(finish=finish):
                h=self.disconnected_scene()
                self.change_incidence(h,'''mt.__len=function()
                  incidence_length_calls=incidence_length_calls+1
                  if incidence_length_calls==1 then return 1 end
                '''+finish+' end')
                self.assert_incidence_plan_refuses_unchanged(h,reason)
                self.assertEqual(h.lua.globals().incidence_length_calls,2)

    def test_post_connect_partial_incidence_read_never_publishes_partial_bindings(self):
        h=self.disconnected_scene();bindings=h.j.encode(h.e.local_bindings())
        plan=h.plan('a:4',{'op':'PROBE_CONNECT'});result=h.lua.globals().apply_command(plan.native,False)
        self.change_incidence(h,'''assert(#values==2)
          mt.__pairs=function()return function()
            incidence_iterator_calls=incidence_iterator_calls+1
            if incidence_iterator_calls==1 then return 'first',values[1]end
            error('fixture second post-connect incidence failed',0)
          end end''')
        with self.assertRaisesRegex(Exception,'iteration failed'):h.e.finish(plan,result,True)
        self.assert_no_connector_binding(h)
        self.assertEqual(h.j.encode(h.e.local_bindings()),bindings)
        self.assertEqual(h.lua.globals().sent,6)

    def test_ordered_callback_arrays_do_not_accept_unindexed_incidence_shape(self):
        h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
        h.lua.globals().apply_command(plan.native,False)
        result=h.lua.eval('native_record({resultEntities=native_incidence(connector_ids)})')
        with self.assertRaisesRegex(Exception,'build array hole at connector.resultEntities'):
            h.e.finish(plan,result,True)
        self.assert_no_connector_binding(h)

    def change_line_membership(self,h,body):
        h.lua.execute('''
          local get=api.engine.system.transportVehicleSystem.getLineVehicles
          api.engine.system.transportVehicleSystem.getLineVehicles=function(id)
            local values={};for _,entity in pairs(get(id))do values[#values+1]=entity end
            local collection=native_entity_collection(values);local mt=getmetatable(collection)
            membership_calls=0
        '''+body+'''return collection end''')

    def assert_unreadable_line_membership(self,h,reason=None):
        sent,money,now=h.lua.globals().sent,h.lua.globals().money,h.lua.globals().now
        bindings=h.j.encode(h.e.local_bindings());snapshot=h.snapshot()
        errors='\n'.join(snapshot['coverage']['missing'])
        self.assertIn('a:5',errors)
        if reason:self.assertIn(reason,errors)
        line=next(obj for obj in snapshot['objects'] if obj['logical_id']=='a:5')
        self.assertEqual(line['state'],{'unavailable':True})
        self.assertNotIn('line',snapshot['probe'])
        self.assertEqual(h.j.encode(h.e.local_bindings()),bindings)
        self.assertEqual((h.lua.globals().sent,h.lua.globals().money,h.lua.globals().now),(sent,money,now))

    def test_line_membership_uses_native_values_for_empty_and_assigned_line(self):
        h=Harness()
        for key,command in COMMANDS[:8]:h.apply(key,command)
        self.assertEqual(h.snapshot()['probe']['line']['vehicles'],[])
        h.apply(*COMMANDS[8])
        h.lua.globals().line_id=h.e.local_bindings()['a:5']
        self.assertTrue(h.lua.eval('''(function()
          local c=api.engine.system.transportVehicleSystem.getLineVehicles(line_id)
          assert(type(c)=='userdata'and #c==1 and c[1]==nil)
          local n=0;for key,value in pairs(c)do
            assert(type(key)=='string'and value==vehicle_id);n=n+1
          end;return n==1
        end)()'''))
        self.assertEqual(h.snapshot()['probe']['line']['vehicles'],['b:3'])
        self.assertEqual(h.snapshot()['coverage']['missing'],[])

    def test_line_membership_empty_observation_never_invents_assigned_vehicle(self):
        h=Harness();before=h.build()
        self.change_line_membership(h,'collection=native_entity_collection({});')
        after=h.snapshot()
        self.assertEqual(after['probe']['line']['vehicles'],[])
        self.assertEqual(after['probe']['vehicle']['line'],'a:5')
        self.assertEqual(after['coverage']['missing'],[])
        self.assertNotEqual(before,after)

    def test_line_membership_rejects_invalid_values_even_with_valid_entity_keys(self):
        for value in ('nil','false','tostring(values[1])','-1','0','1.5','2147483648','999999','0/0','math.huge'):
            with self.subTest(value=value):
                h=Harness();h.build()
                self.change_line_membership(h,'''mt.__pairs=function()return function()
                  membership_calls=membership_calls+1
                  if membership_calls==1 then return values[1],'''+value+''' end
                end end;''')
                self.assert_unreadable_line_membership(h,'build entity missing' if value=='999999' else 'getLineVehicles')
                self.assertEqual(h.lua.globals().membership_calls,1)

    def test_line_membership_enforces_one_vehicle_limit_and_valid_container_length(self):
        for change in ('collection=false;',"collection='invalid';",'collection=17;',
                       'mt.__len=function()return 2 end;',"mt.__len=function()return '1' end;",
                       'mt.__len=function()return -.5 end;',"mt.__len=function()error('fixture membership length failed',0)end;"):
            with self.subTest(change=change):
                h=Harness();h.build();self.change_line_membership(h,change)
                self.assert_unreadable_line_membership(h,'getLineVehicles')

    def test_line_membership_partial_duplicate_and_throwing_iterations_are_not_valid_snapshots(self):
        for body,reason in (
            ("mt.__pairs=function()error('fixture pairs failure',0)end;",'iterator unavailable'),
            ('mt.__pairs=function()return function()return nil end end;','count mismatch'),
            ('''mt.__pairs=function()return function()
              membership_calls=membership_calls+1
              if membership_calls==1 then return 'slot',values[1]end
              error('fixture second membership read failed',0)
            end end;''','iteration failed'),
            ('''mt.__pairs=function()return function()
              membership_calls=membership_calls+1;return membership_calls,values[1]
            end end;''','exceeded declared length')):
            with self.subTest(reason=reason):
                h=Harness();h.build();self.change_line_membership(h,body)
                self.assert_unreadable_line_membership(h,reason)
                self.assertLessEqual(h.lua.globals().membership_calls,2)

    def test_stock_constructions_keep_distinct_ports_until_explicit_link_command(self):
        h=self.disconnected_scene();before=h.snapshot()
        self.assertFalse(before['probe']['connectivity']['connected'])
        self.assertFalse(h.lua.eval('depot_outer==roadends[3]'))
        self.assertFalse(h.lua.eval('stop_outer[1]==roadends[1]or stop_outer[2]==roadends[2]'))
        positions=h.lua.eval('''function()
          local out={}
          for _,pair in ipairs({{roadends[1],stop_outer[1]},{roadends[2],stop_outer[2]},{roadends[3],depot_outer}})do
            local a,b=world[pair[1]].BASE_NODE.position,world[pair[2]].BASE_NODE.position
            out[#out+1]=math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2)
          end
          return out
        end''')()
        self.assertEqual([positions[i] for i in range(1,4)],[20,20,20])
        with self.assertRaises(Exception):h.plan('b:3',{'op':'PROBE_VEHICLE'})
        self.assertEqual(h.snapshot(),before)
        self.assertEqual(h.lua.globals().sent,5)

    def test_connector_plan_uses_existing_node_ids_and_real_empty_callback_result(self):
        h=self.disconnected_scene();before=h.snapshot()
        plan=h.plan('a:4',{'op':'PROBE_CONNECT'});sp=plan.native.proposal.streetProposal
        self.assertEqual(h.snapshot(),before)
        self.assertEqual(len(plan.native.proposal.constructionsToAdd),0)
        for name in ('nodesToAdd','nodesToRemove','edgesToRemove','edgeObjectsToAdd','edgeObjectsToRemove'):
            self.assertEqual(len(sp[name]),0,name)
        self.assertEqual(len(sp.edgesToAdd),3)
        actual={frozenset((edge.comp.node0,edge.comp.node1)) for _,edge in sp.edgesToAdd.items()}
        g=h.lua.globals()
        expected={frozenset((g.roadends[i],g.stop_outer[i])) for i in (1,2)}
        expected.add(frozenset((g.roadends[3],g.depot_outer)))
        self.assertEqual(actual,expected)
        self.assertEqual(sorted(edge.entity for _,edge in sp.edgesToAdd.items()),[-3,-2,-1])
        result=h.lua.globals().apply_command(plan.native,False)
        self.assertEqual(len(result.resultEntities),0)
        receipt=h.e.finish(plan,result,True)
        self.assertTrue(receipt.success)
        after=h.snapshot()
        self.assertEqual(after['probe']['profile'],'build_v2')
        self.assertEqual(after['probe']['scene']['connectors'],'a:4')
        self.assertTrue(after['probe']['connectivity']['connected'])
        self.assertEqual(len([x for x in after['objects'] if x['kind']=='connector']),3)
        self.assertEqual(after['coverage']['missing'],[])
        h.plan('b:3',{'op':'PROBE_VEHICLE'})

    def test_false_connector_callback_does_not_confirm_an_existing_graph_change(self):
        h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
        result=h.lua.globals().apply_command(plan.native,False)
        receipt=h.e.finish(plan,result,False)
        self.assertEqual(json.loads(h.j.encode(receipt)),{'success':False,'result':{'error':'engine_rejected','op':'PROBE_CONNECT'}})
        self.assert_no_connector_binding(h)
        with self.assertRaises(Exception):h.plan('b:3',{'op':'PROBE_VEHICLE'})

    def test_success_without_new_connector_edges_never_confirms_or_allows_buy(self):
        h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
        with self.assertRaises(Exception):h.e.finish(plan,h.lua.eval('native_record({resultEntities={}})'),True)
        self.assert_no_connector_binding(h)
        self.assertFalse(h.snapshot()['probe']['connectivity']['connected'])
        with self.assertRaises(Exception):h.plan('b:3',{'op':'PROBE_VEHICLE'})

    def test_partial_wrong_or_ambiguous_connector_graph_is_rejected_atomically(self):
        cases=[
          'world[connector_ids[2]]=nil',
          'world[connector_ids[1]].BASE_EDGE.node1=roadends[3]',
          'world[fresh()]=copy(world[connector_ids[1]])',
          'world[connector_ids[1]].BASE_EDGE_STREET.streetType=999',
          'world[connector_ids[1]].BASE_EDGE.tangent0.x=world[connector_ids[1]].BASE_EDGE.tangent0.x+.5',
          'world[connector_ids[1]].BASE_EDGE.typeIndex=0',
        ]
        for change in cases:
            with self.subTest(change=change):
                h=self.disconnected_scene();verified=h.j.encode(h.e.local_bindings())
                plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
                result=h.lua.globals().apply_command(plan.native,False);h.lua.execute(change)
                with self.assertRaises(Exception):h.e.finish(plan,result,True)
                self.assert_no_connector_binding(h)
                self.assertEqual(h.j.encode(h.e.local_bindings()),verified)
                with self.assertRaises(Exception):h.plan('b:3',{'op':'PROBE_VEHICLE'})

    def test_connector_graph_witness_requires_unchanged_existing_edges(self):
        h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
        result=h.lua.globals().apply_command(plan.native,False)
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        h.lua.execute('world[world[road_id].CONSTRUCTION.frozenEdges[1]].BASE_EDGE.tangent0.x=777')
        with self.assertRaises(Exception):h.e.finish(plan,result,True)
        self.assert_no_connector_binding(h)

    def test_nonempty_connector_callback_ids_must_match_unique_observed_new_edges(self):
        for supplied in ('{connector_ids[1],connector_ids[2],999999}',
                         '{connector_ids[1],connector_ids[2],connector_ids[2]}',
                         '{connector_ids[1],connector_ids[2]}'):
            h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
            h.lua.globals().apply_command(plan.native,False)
            result=h.lua.eval('native_record({resultEntities='+supplied+'})')
            with self.assertRaises(Exception):h.e.finish(plan,result,True)
            self.assert_no_connector_binding(h)

    def test_connector_result_identity_vector_read_errors_are_not_observed_empty(self):
        h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
        h.lua.globals().apply_command(plan.native,False)
        with self.assertRaises(Exception):h.e.finish(plan,h.lua.eval('native_record({})'),True)
        self.assert_no_connector_binding(h)

    def test_connector_plan_rejects_missing_throwing_or_malformed_incidence_data(self):
        cases=[
          "api.engine.system.streetSystem.getNode2StreetEdgeMap=function()return nil end",
          "api.engine.system.streetSystem.getNode2StreetEdgeMap=function()error(native_params({},'opaque'),0)end",
          "local get=api.engine.system.streetSystem.getNode2StreetEdgeMap;api.engine.system.streetSystem.getNode2StreetEdgeMap=function()local m=get();m[roadends[3]]=nil;return m end",
          "local get=api.engine.system.streetSystem.getNode2StreetEdgeMap;api.engine.system.streetSystem.getNode2StreetEdgeMap=function()local m=get();m[roadends[3]]=false;return m end",
          "local get=api.engine.system.streetSystem.getNode2StreetEdgeMap;api.engine.system.streetSystem.getNode2StreetEdgeMap=function()local m=get();m[roadends[3]]={};return m end",
          "local get=api.engine.system.streetSystem.getNode2StreetEdgeMap;api.engine.system.streetSystem.getNode2StreetEdgeMap=function()local m=get();m[roadends[3]]=native_params({},'opaque');getmetatable(m[roadends[3]]).__len=function()error('native vector length failed')end;return m end",
        ]
        for change in cases:
            h=self.disconnected_scene();before=h.snapshot();h.lua.execute(change)
            with self.assertRaises(Exception):h.plan('a:4',{'op':'PROBE_CONNECT'})
            self.assert_no_connector_binding(h)
            self.assertEqual(h.snapshot(),before)
            self.assertEqual(h.lua.globals().sent,5)

    def test_connector_finish_does_not_treat_failed_incidence_read_as_empty(self):
        h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
        result=h.lua.globals().apply_command(plan.native,False)
        h.lua.execute("api.engine.system.streetSystem.getNode2StreetEdgeMap=function()error('map refresh failed')end")
        with self.assertRaisesRegex(Exception,'map refresh failed'):h.e.finish(plan,result,True)
        self.assert_no_connector_binding(h)

    def test_connector_using_foreign_node_at_equal_coordinates_is_not_confirmed(self):
        h=self.disconnected_scene();plan=h.plan('a:4',{'op':'PROBE_CONNECT'})
        result=h.lua.globals().apply_command(plan.native,False)
        h.lua.execute('''
          local e=world[connector_ids[1]].BASE_EDGE
          local foreign=fresh();world[foreign]={BASE_NODE={position=copy(world[e.node1].BASE_NODE.position)}}
          e.node1=foreign
        ''')
        with self.assertRaises(Exception):h.e.finish(plan,result,True)
        self.assert_no_connector_binding(h)

    def test_connector_plan_rejects_missing_or_mismatched_street_resource(self):
        for change in ('api.res.streetTypeRep.find=function()return -1 end',
                       "api.res.streetTypeRep.getName=function()return 'unrequested.lua' end"):
            h=self.disconnected_scene();h.lua.execute(change)
            with self.assertRaises(Exception):h.plan('a:4',{'op':'PROBE_CONNECT'})
            self.assert_no_connector_binding(h)
            self.assertEqual(h.lua.globals().sent,5)

    def test_disconnected_equal_coordinate_ports_are_not_the_same_node_identity(self):
        h=self.disconnected_scene()
        h.lua.execute('''
          world[depot_outer].BASE_NODE.position=copy(world[roadends[3]].BASE_NODE.position)
          for i=1,2 do world[stop_outer[i]].BASE_NODE.position=copy(world[roadends[i]].BASE_NODE.position)end
        ''')
        self.assertFalse(h.snapshot()['probe']['connectivity']['connected'])
        with self.assertRaises(Exception):h.plan('a:4',{'op':'PROBE_CONNECT'})
        with self.assertRaises(Exception):h.plan('b:3',{'op':'PROBE_VEHICLE'})

    def test_observed_nil_construction_timestamp_is_explicit_coverage(self):
        h=Harness();s=h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        self.assertEqual(h.lua.eval('type(world[road_id].CONSTRUCTION)'), 'userdata')
        self.assertIsNone(h.lua.eval('world[road_id].CONSTRUCTION.timeBuild'))
        self.assertEqual(s['objects'][0]['state']['time_build'],{'available':False})
        self.assertEqual(s['coverage']['observed_unavailable'],['a:2.CONSTRUCTION.timeBuild'])
        self.assertEqual(s['coverage']['missing'],[])

    def test_zero_and_present_timestamp_values_differ_from_absence_and_each_other(self):
        h=Harness();absent=h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        h.lua.execute('world[road_id].CONSTRUCTION.timeBuild=0')
        zero=h.snapshot()
        self.assertEqual(zero['objects'][0]['state']['time_build'],{'available':True,'value':'0'})
        self.assertEqual(zero['coverage']['observed_unavailable'],[])
        h.lua.execute('world[road_id].CONSTRUCTION.timeBuild=13400')
        present=h.snapshot()
        self.assertEqual(present['objects'][0]['state']['time_build'],{'available':True,'value':'13400'})
        self.assertNotEqual(absent,zero);self.assertNotEqual(zero,present)
        h.lua.execute('world[road_id].CONSTRUCTION.timeBuild=13401')
        self.assertNotEqual(present,h.snapshot())

    def test_present_invalid_timestamp_still_refuses_with_field_and_lua_type(self):
        for value,kind in [("'invalid'",'string'),('0/0','number'),('math.huge','number'),('false','boolean'),("native_params({},'opaque')",'userdata')]:
            h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().road_id=h.e.local_bindings()['a:2']
            h.lua.execute('world[road_id].CONSTRUCTION.timeBuild='+value)
            s=h.snapshot();errors='\n'.join(s['coverage']['missing'])
            self.assertIn('a:2.CONSTRUCTION.timeBuild',errors)
            self.assertIn('Lua type='+kind,errors)
            self.assertEqual(s['objects'][0]['state'],{'unavailable':True})
            self.assertNotIn('0x',errors)

    def test_timestamp_getter_exception_is_not_recorded_as_observed_absence(self):
        for error in ("'timestamp getter failed'","native_params({},'opaque')"):
            h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().road_id=h.e.local_bindings()['a:2']
            h.lua.execute('''
              local mt=getmetatable(world[road_id].CONSTRUCTION);local original=mt.__index
              mt.__index=function(self,key)if key=='timeBuild'then error('''+error+''',0)end;return original(self,key)end
            ''')
            s=h.snapshot();errors='\n'.join(s['coverage']['missing'])
            self.assertIn('getter threw at a:2.CONSTRUCTION.timeBuild',errors)
            self.assertNotIn('a:2.CONSTRUCTION.timeBuild',s['coverage']['observed_unavailable'])
            self.assertEqual(s['objects'][0]['state'],{'unavailable':True})
            self.assertNotIn('userdata:',errors)

    def test_absent_timestamp_does_not_relax_matrix_or_road_numeric_fields(self):
        cases=[("world[road_id].CONSTRUCTION.transf[7]='bad'",'CONSTRUCTION.transf[7]','string'),
               ('world[edge_id].BASE_EDGE_STREET.streetType=nil','BASE_EDGE_STREET.streetType','nil'),
               ('world[edge_id].BASE_EDGE.typeIndex=false','BASE_EDGE.typeIndex','boolean'),
               ('world[edge_id].BASE_EDGE.tangent0.x=0/0','BASE_EDGE.tangent0.x','number')]
        for setup,path,kind in cases:
            h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().road_id=h.e.local_bindings()['a:2']
            h.lua.execute('edge_id=world[road_id].CONSTRUCTION.frozenEdges[1];'+setup)
            errors='\n'.join(h.snapshot()['coverage']['missing'])
            self.assertIn(path,errors);self.assertIn('Lua type='+kind,errors)

    def test_documented_automatic_load_minus_one_is_preserved_and_minus_two_refused(self):
        h=Harness();before=h.build()
        h.lua.execute('world[vehicle_id].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].part.loadConfig={-1}')
        after=h.snapshot();self.assertEqual(after['coverage']['missing'],[])
        vehicle=next(x['state'] for x in after['objects'] if x['kind']=='vehicle')
        self.assertEqual(vehicle['config']['vehicles'][0]['load_config'],[-1])
        self.assertNotEqual(before,after)
        h.lua.execute('world[vehicle_id].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].part.loadConfig={-2}')
        errors='\n'.join(h.snapshot()['coverage']['missing'])
        self.assertIn('part.loadConfig[1]',errors);self.assertIn('Lua type=number',errors)

    def test_unassigned_stop_index_absence_and_actual_zero_are_distinct(self):
        h=Harness()
        for key,command in COMMANDS[:7]:h.apply(key,command)
        absent=h.snapshot();self.assertEqual(absent['coverage']['missing'],[])
        vehicle=next(x['state'] for x in absent['objects'] if x['kind']=='vehicle')
        self.assertEqual(vehicle['stop_index'],{'available':False})
        self.assertIn('b:3.TRANSPORT_VEHICLE.stopIndex',absent['coverage']['observed_unavailable'])
        h.lua.execute('world[vehicle_id].TRANSPORT_VEHICLE.stopIndex=0')
        zero=h.snapshot();vehicle=next(x['state'] for x in zero['objects'] if x['kind']=='vehicle')
        self.assertEqual(vehicle['stop_index'],{'available':True,'value':0})
        self.assertNotEqual(absent,zero)

    def test_assigned_stop_index_remains_required_integer_and_getter_errors_fail(self):
        for value in ('nil',"'invalid'",'0/0','-.5','-1'):
            h=Harness();h.build();h.lua.execute('world[vehicle_id].TRANSPORT_VEHICLE.stopIndex='+value)
            errors='\n'.join(h.snapshot()['coverage']['missing'])
            self.assertIn('b:3.TRANSPORT_VEHICLE.stopIndex',errors)
        h=Harness()
        for key,command in COMMANDS[:7]:h.apply(key,command)
        h.lua.execute("setmetatable(world[vehicle_id].TRANSPORT_VEHICLE,{__index=function(_,k)if k=='stopIndex'then error('bad stop getter')end end})")
        self.assertIn('getter threw at b:3.TRANSPORT_VEHICLE.stopIndex','\n'.join(h.snapshot()['coverage']['missing']))

    def test_vehicle_depot_line_move_and_config_numeric_errors_name_actual_field(self):
        cases=[
          ('world[depot_id].VEHICLE_DEPOT.stateTime=nil','VEHICLE_DEPOT.stateTime','nil'),
          ("world[line_id].LINE.stops[1].maxWaitingTime='bad'",'LINE.stops[1].maxWaitingTime','string'),
          ('world[vehicle_id].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].maintenanceState=false','transportVehicleConfig.vehicles[1].maintenanceState','boolean'),
          ("world[vehicle_id].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].part.color={x='bad',y=0,z=0}",'part.color.x','string'),
          ('world[vehicle_id].TRANSPORT_VEHICLE.transportVehicleConfig.vehicleGroups={0}','transportVehicleConfig.vehicleGroups[1]','number'),
          ('advance();world[vehicle_id].MOVE_PATH.dyn.pathPos.pos01=math.huge','MOVE_PATH.dyn.pathPos.pos01','number'),
        ]
        for setup,path,kind in cases:
            h=Harness();h.build()
            h.lua.globals().depot_id=h.e.local_bindings()['b:1:depot']
            h.lua.globals().line_id=h.e.local_bindings()['a:5']
            h.lua.execute(setup)
            errors='\n'.join(h.snapshot()['coverage']['missing'])
            self.assertIn(path,errors);self.assertIn('Lua type='+kind,errors)

    def test_company_and_simulation_numeric_errors_include_paths(self):
        for setup,path,kind in [('money=false','company.balance','boolean'),("now='bad'",'game.interface.getGameTime.time','string'),('speed=nil','game.interface.getGameSpeed','nil')]:
            h=Harness();h.lua.execute(setup)
            with self.assertRaisesRegex(Exception,path.replace('.','\\.')+r'.*Lua type='+kind):h.snapshot()

    def test_native_indexed_transform_missing_col_member_is_a_supported_read(self):
        h=Harness();s=h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        self.assertEqual(h.lua.eval('type(world[road_id].CONSTRUCTION.transf)'), 'userdata')
        self.assertFalse(h.lua.eval("pcall(function()return world[road_id].CONSTRUCTION.transf.col end)")[0])
        self.assertEqual(s['coverage']['missing'],[])
        self.assertEqual(s['objects'][0]['state']['transform'],
                         ['1','0','0','0','0','1','0','0','0','0','1','0','0','0','10','1'])

    def test_native_column_method_and_plain_indexed_transform_match_native_array(self):
        h=Harness();expected=h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        h.lua.execute('''
          world[road_id].CONSTRUCTION.transf=api.type.Mat4f.new(
            api.type.Vec4f.new(1,0,0,0),api.type.Vec4f.new(0,1,0,0),
            api.type.Vec4f.new(0,0,1,0),api.type.Vec4f.new(0,0,10,1))
        ''')
        self.assertEqual(h.lua.eval('type(world[road_id].CONSTRUCTION.transf)'), 'userdata')
        self.assertEqual(expected,h.snapshot())
        h.lua.execute('world[road_id].CONSTRUCTION.transf={1,0,0,0,0,1,0,0,0,0,1,0,0,0,10,1}')
        self.assertEqual(expected,h.snapshot())

    def test_unreadable_mandatory_transform_value_still_invalidates_snapshot(self):
        for setup in ('world[road_id].CONSTRUCTION.transf[7]=nil',
                      "world[road_id].CONSTRUCTION.transf=native_params({},'opaque')"):
            h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().road_id=h.e.local_bindings()['a:2']
            h.lua.execute(setup)
            s=h.snapshot()
            self.assertTrue(s['coverage']['missing'])
            self.assertEqual(s['objects'][0]['state'],{'unavailable':True})
            self.assertNotIn('bad argument #1', '\n'.join(s['coverage']['missing']))

    def test_column_method_failure_cannot_fall_back_to_invented_matrix(self):
        h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
        h.lua.globals().road_id=h.e.local_bindings()['a:2']
        h.lua.execute('''
          world[road_id].CONSTRUCTION.transf={col=function()error('actual column getter failed')end,
            1,0,0,0,0,1,0,0,0,0,1,0,0,0,10,1}
        ''')
        s=h.snapshot()
        self.assertTrue(any('actual column getter failed' in item for item in s['coverage']['missing']))
        self.assertEqual(s['objects'][0]['state'],{'unavailable':True})

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
        self.assertEqual(h.lua.globals().sent,9)

    def test_rejected_vehicle_recipe_retains_exact_callback_id_only_for_diagnosis(self):
        h=Harness()
        for key,command in COMMANDS[:6]:h.apply(key,command)
        before=h.snapshot();verified=json.loads(h.j.encode(h.e.local_bindings()))
        plan=h.plan('b:3',{'op':'PROBE_VEHICLE'})
        result=h.lua.globals().apply_command(plan.native,False)
        exact_id=h.lua.globals().vehicle_id
        h.lua.execute("world[vehicle_id].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].maintenanceState='bad'")
        with self.assertRaisesRegex(Exception,'maintenanceState'):
            h.e.finish(plan,result,True)
        self.assertEqual(json.loads(h.j.encode(h.e.local_bindings())),verified)
        self.assertIsNone(h.e.local_bindings()['b:3'])
        self.assertIsNone(h.e.scene.vehicle)
        diagnostic=json.loads(h.j.encode(h.e.diagnostic_bindings()))
        self.assertEqual(diagnostic,dict(verified,**{'callback:b:3':exact_id}))
        self.assertEqual(len(diagnostic),len(verified)+1)
        self.assertLessEqual(len(diagnostic),15)
        # The pre-existing tracked objects are unchanged by a diagnostic entry.
        self.assertEqual(before['objects'],h.snapshot()['objects'])
        h.e.finish(plan,h.table({}),False)
        self.assertEqual(json.loads(h.j.encode(h.e.diagnostic_bindings())),verified)

    def test_successful_finish_has_no_duplicate_diagnostic_callback_binding(self):
        h=Harness();h.build()
        self.assertEqual(h.j.encode(h.e.diagnostic_bindings()),h.j.encode(h.e.local_bindings()))
        self.assertNotIn('callback:',h.j.encode(h.e.diagnostic_bindings()))

    def test_ambiguous_or_nonexistent_callback_is_not_a_diagnostic_candidate(self):
        h=Harness()
        for key,command in COMMANDS[:6]:h.apply(key,command)
        plan=h.plan('b:3',{'op':'PROBE_VEHICLE'})
        result=h.lua.globals().apply_command(plan.native,False)
        actual=h.lua.globals().vehicle_id
        for supplied,reason in [({'resultEntity':actual,'resultVehicleEntity':actual+1},'ambiguous callback'),
                                ({'resultVehicleEntity':actual+1000},'build entity missing')]:
            with self.assertRaisesRegex(Exception,reason):h.e.finish(plan,h.table(supplied),True)
            self.assertIsNone(h.e.local_bindings()['b:3'])
            self.assertNotIn('callback:',h.j.encode(h.e.diagnostic_bindings()))

    def test_native_callback_missing_unused_member_preserves_authoritative_id(self):
        h=Harness()
        h.lua.execute('''
          local original=apply_command
          apply_command=function(cmd,no_result)
            local result=original(cmd,no_result)
            assert(type(result)=='userdata')
            if cmd.op=='buy'then
              assert(not pcall(function()return result.resultEntity end))
              assert(result.resultVehicleEntity>0)
            elseif cmd.op=='line'then
              assert(result.resultEntity>0)
              assert(not pcall(function()return result.resultVehicleEntity end))
            end
            return result
          end
        ''')
        s=h.build()
        self.assertEqual(s['coverage']['missing'],[])
        self.assertEqual(s['probe']['scene']['vehicle'],'b:3')
        self.assertEqual(s['probe']['scene']['line'],'a:5')

    def test_callback_without_any_readable_identity_does_not_bind_a_guess(self):
        h=Harness()
        for key,command in COMMANDS[:6]:h.apply(key,command)
        plan=h.plan('b:3',{'op':'PROBE_VEHICLE'})
        h.lua.globals().apply_command(plan.native,False)
        result=h.lua.eval('native_record({})')
        with self.assertRaisesRegex(Exception,'successful build callback lacks exact entity'):
            h.e.finish(plan,result,True)
        self.assertIsNone(h.e.local_bindings()['b:3'])
        self.assertNotIn('vehicle',h.snapshot()['probe']['scene'])

    def test_rejected_native_callback_preserves_observed_error_state_separately(self):
        for mode in ('members','pairs'):
            h=Harness();before=h.snapshot();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
            h.lua.globals().callback_mode=mode
            h.lua.execute('''
              callback_method_calls=0
              local state=native_params({code=17,possible=false,detail={distance=1.25},
                message='Bau nicht möglich',method=function()callback_method_calls=callback_method_calls+1 end},callback_mode)
              callback=native_record({resultEntities={7,8},resultVehicleEntity=-1,resultEntity=0,
                resultProposalData=native_params({errorState=state,cost=10000},callback_mode)})
              assert(type(callback)=='userdata' and type(state)=='userdata')
            ''')
            receipt=h.e.finish(plan,h.lua.globals().callback,False)
            self.assertEqual(json.loads(h.j.encode(receipt)),{'success':False,'result':{'error':'engine_rejected','op':'PROBE_ROAD'}})
            report=json.loads(h.j.encode(h.e.callback_diagnostics()))
            self.assertEqual((report['command_key'],report['op']),('a:2','PROBE_ROAD'))
            self.assertEqual(report['success'],{'type':'boolean','value':False})
            self.assertEqual(report['result_type'],'userdata')
            self.assertFalse(report['valid_snapshot'])
            rows={r['path']:r for r in report['records']};prefix='result.resultProposalData.errorState'
            self.assertEqual(rows[prefix]['type'],'userdata')
            self.assertEqual(rows[prefix+'.code']['value'],'17')
            self.assertEqual(rows[prefix+'.detail.distance']['value'],'1.25')
            self.assertEqual(rows[prefix+'.possible']['value'],False)
            self.assertEqual(rows[prefix+'.message']['value'],'Bau nicht möglich')
            self.assertEqual(rows[prefix+'.method']['type'],'function')
            self.assertNotIn('value',rows[prefix+'.method'])
            self.assertEqual(rows['result.resultEntities.1']['value'],'7')
            self.assertEqual(rows['result.resultVehicleEntity']['value'],'-1')
            self.assertEqual(h.lua.globals().callback_method_calls,0)
            self.assertEqual(h.snapshot(),before)
            self.assertEqual(h.j.encode(h.e.local_bindings()),'{}')
            self.assertEqual(h.j.encode(h.e.diagnostic_bindings()),'{}')
            self.assertEqual(h.lua.globals().sent,0)

    def test_callback_diagnostics_distinguish_nil_and_throwing_native_members(self):
        h=Harness();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
        h.lua.execute('''
          opaque_error=native_params({},'opaque')
          getmetatable(opaque_error).__tostring=function()error('opaque tostring must not run')end
          local state=native_params({broken=17,message='observed rejection'},'members')
          local state_read=getmetatable(state).__index
          getmetatable(state).__index=function(self,key)
            if key=='broken'then error('getter rejected field at 0xAABBCC',0)end
            return state_read(self,key)
          end
          callback=native_params({},'opaque')
          local proposal=native_params({errorState=state},'members')
          getmetatable(callback).__index=function(_,key)
            if key=='resultEntity'then error(opaque_error,0)end
            if key=='resultProposalData'then return proposal end
            return nil
          end
        ''')
        receipt=h.e.finish(plan,h.lua.globals().callback,False)
        self.assertFalse(receipt.success)
        raw=h.j.encode(h.e.callback_diagnostics());rows={r['path']:r for r in json.loads(raw)['records']}
        self.assertEqual(rows['result.resultEntities']['access'],'nil')
        self.assertEqual(rows['result.resultEntities']['type'],'nil')
        self.assertEqual(rows['result.resultEntity']['access'],'throws')
        self.assertEqual(rows['result.resultEntity']['error_type'],'userdata')
        self.assertEqual(rows['result.resultEntity']['error'],'error value has Lua type=userdata')
        prefix='result.resultProposalData.errorState'
        self.assertEqual(rows[prefix+'.broken']['access'],'throws')
        self.assertEqual(rows[prefix+'.message']['value'],'observed rejection')
        self.assertIn('[address]',rows[prefix+'.broken']['error'])
        self.assertNotIn('0xAABBCC',raw)

    def test_callback_diagnostic_numbers_are_strings_including_nonfinite_values(self):
        h=Harness();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
        result=h.lua.eval("native_params({resultProposalData={errorState={nan=0/0,positive=math.huge,negative=-math.huge,integer=17,fraction=1.25,flag=false}}},'members')")
        h.e.finish(plan,result,False)
        raw=h.j.encode(h.e.callback_diagnostics());report=json.loads(raw,parse_constant=lambda s:self.fail('invalid JSON number '+s))
        rows={r['path']:r for r in report['records']};prefix='result.resultProposalData.errorState.'
        for key,value in [('nan','NaN'),('positive','+Infinity'),('negative','-Infinity'),('integer','17'),('fraction','1.25')]:
            self.assertEqual(rows[prefix+key]['type'],'number')
            self.assertEqual(rows[prefix+key]['value'],value)
        for row in report['records']:
            if row['type']=='number':self.assertIsInstance(row['value'],str)
        self.assertFalse(rows[prefix+'flag']['value'])

    def test_callback_diagnostics_bound_broad_native_payload_and_retain_header(self):
        h=Harness();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
        h.lua.execute('''
          local state={}
          for i=1,20 do
            local child={};state[string.rep('key',60)..i]=child
            for j=1,20 do child[string.rep('leaf',45)..j]=string.rep('payload',1000)end
          end
          callback=native_params({resultProposalData={errorState=state}},'members')
        ''')
        h.e.finish(plan,h.lua.globals().callback,False)
        raw=h.j.encode(h.e.callback_diagnostics());report=json.loads(raw)
        self.assertLessEqual(len(raw.encode('utf-8')),16384)
        self.assertLessEqual(len(report['records']),128)
        self.assertTrue(report['truncated'])
        self.assertGreater(report['limits']['dropped_records'],0)
        self.assertEqual(report['success'],{'type':'boolean','value':False})
        self.assertEqual((report['command_key'],report['op']),('a:2','PROBE_ROAD'))
        paths={r['path'] for r in report['records']}
        for name in ('resultEntities','resultVehicleEntity','resultEntity','resultProposalData'):
            self.assertIn('result.'+name,paths)
        for row in report['records']:
            for value in row.values():
                if isinstance(value,str):self.assertLessEqual(len(value.encode('utf-8')),256)

    def test_callback_diagnostics_bound_cycles_depth_and_unknown_native_iteration(self):
        h=Harness();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
        h.lua.execute('''
          local state={deep={one={two={hidden='too deep'}}}};state.cycle=state
          state.opaque=native_params({},'opaque')
          callback=native_params({resultProposalData={errorState=state}},'members')
        ''')
        h.e.finish(plan,h.lua.globals().callback,False)
        report=json.loads(h.j.encode(h.e.callback_diagnostics()))
        rows={r['path']:r for r in report['records']};prefix='result.resultProposalData.errorState'
        self.assertTrue(report['truncated'])
        self.assertTrue(rows[prefix+'.cycle.@cycle']['value'])
        self.assertEqual(rows[prefix+'.opaque.@enumeration']['access'],'throws')
        self.assertNotIn(prefix+'.deep.one.two.hidden',rows)

    def test_callback_text_is_valid_utf8_bounded_and_opaque_addresses_are_removed(self):
        h=Harness();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
        h.lua.execute('''
          local state=native_params({invalid='Grüße '..string.char(255,192,175,237,160,128,244,144,128,128)..' 0xABCDEF',
            control='line'..string.char(0,1,10)..'end',boundary=string.rep('x',255)..'ä'},'members')
          local read=getmetatable(state).__index
          getmetatable(state).__members[4]='broken'
          getmetatable(state).__index=function(self,key)
            if key=='broken'then error('error '..string.char(255)..' 0x123ABC',0)end
            return read(self,key)
          end
          callback=native_params({resultProposalData={errorState=state}},'members')
        ''')
        h.e.finish(plan,h.lua.globals().callback,False)
        raw=h.j.encode(h.e.callback_diagnostics());report=json.loads(raw)
        rows={r['path']:r for r in report['records']};prefix='result.resultProposalData.errorState.'
        self.assertTrue(rows[prefix+'invalid']['value'].startswith('Grüße '))
        self.assertIn('?',rows[prefix+'invalid']['value'])
        self.assertIn('[address]',rows[prefix+'invalid']['value'])
        self.assertEqual(rows[prefix+'control']['value'],'line\x00\x01\nend')
        self.assertEqual(rows[prefix+'boundary']['value'],'x'*255)
        self.assertEqual(rows[prefix+'broken']['error'],'error ? [address]')
        self.assertNotIn('0xABCDEF',raw)
        self.assertNotIn('0x123ABC',raw)
        self.assertTrue(report['truncated'])

    def test_callback_diagnostics_are_collected_once_and_replaced_per_callback(self):
        h=Harness();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
        self.assertIsNone(h.e.callback_diagnostics())
        h.lua.execute('''
          callback_reads=0;callback=native_params({},'opaque')
          getmetatable(callback).__index=function()
            callback_reads=callback_reads+1;return nil
          end
        ''')
        h.e.finish(plan,h.lua.globals().callback,False)
        raw=h.j.encode(h.e.callback_diagnostics())
        self.assertEqual(h.lua.globals().callback_reads,4)
        self.assertEqual(raw,h.j.encode(h.e.callback_diagnostics()))
        self.assertEqual(h.lua.globals().callback_reads,4)
        other=h.plan('b:1',{'op':'SET_PAUSED','value':True})
        receipt=h.e.finish(other,h.table({}),True)
        report=json.loads(h.j.encode(h.e.callback_diagnostics()))
        self.assertEqual(report['command_key'],'b:1')
        self.assertEqual(report['success'],{'type':'boolean','value':True})
        self.assertEqual(json.loads(h.j.encode(receipt)),{'success':True,'result':{'paused':True}})
        self.assertNotIn('callback_diagnostics',h.j.encode(receipt))

    def test_new_valid_plan_clears_previous_callback_and_unverified_candidate_before_failure(self):
        h=Harness();h.apply('a:2',{'op':'PROBE_ROAD'})
        self.assertIsNotNone(h.e.callback_diagnostics())
        with self.assertRaises(Exception):h.plan('b:3',{'op':'PROBE_VEHICLE'})
        self.assertIsNone(h.e.callback_diagnostics())
        h=self.disconnected_scene();h.apply('a:4',{'op':'PROBE_CONNECT'})
        plan=h.plan('b:3',{'op':'PROBE_VEHICLE'})
        result=h.lua.globals().apply_command(plan.native,False)
        h.lua.execute("world[vehicle_id].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].maintenanceState='invalid'")
        with self.assertRaises(Exception):h.e.finish(plan,result,True)
        self.assertIsNotNone(h.e.callback_diagnostics())
        self.assertIsNotNone(h.e.diagnostic_bindings()['callback:b:3'])
        with self.assertRaises(Exception):h.plan('a:5',{'op':'PROBE_LINE'})
        self.assertIsNone(h.e.callback_diagnostics())
        self.assertEqual(h.j.encode(h.e.diagnostic_bindings()),h.j.encode(h.e.local_bindings()))

    def test_callback_capture_failure_retains_header_and_original_finish_decision(self):
        h=Harness();plan=h.plan('a:2',{'op':'PROBE_ROAD'})
        encode=h.j.encode
        h.j.encode=h.lua.eval("function()error('diagnostic encoder unavailable',0)end")
        receipt=h.e.finish(plan,h.table({}),False)
        h.j.encode=encode
        self.assertEqual(json.loads(encode(receipt)),{'success':False,'result':{'error':'engine_rejected','op':'PROBE_ROAD'}})
        report=json.loads(encode(h.e.callback_diagnostics()))
        self.assertTrue(report['capture_failed'])
        self.assertTrue(report['truncated'])
        self.assertEqual(report['records'],[])
        self.assertEqual(report['success'],{'type':'boolean','value':False})
        self.assertEqual((report['command_key'],report['op']),('a:2','PROBE_ROAD'))
        self.assertEqual(h.j.encode(h.e.local_bindings()),'{}')
        result=h.lua.globals().apply_command(plan.native,False)
        h.j.encode=h.lua.eval("function()error('diagnostic encoder unavailable',0)end")
        receipt=h.e.finish(plan,result,True)
        h.j.encode=encode
        self.assertTrue(receipt.success)
        self.assertEqual(receipt.result.logical_id,'a:2')
        self.assertEqual(h.e.local_bindings()['a:2'],receipt.result_entity)
        report=json.loads(encode(h.e.callback_diagnostics()))
        self.assertTrue(report['capture_failed'])
        self.assertEqual(report['success'],{'type':'boolean','value':True})
        self.assertEqual(h.snapshot()['coverage']['missing'],[])

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
            if cmd.op=='build' and cmd.proposal.constructionsToAdd[1] and cmd.proposal.constructionsToAdd[1].fileName==assets.stop_file then
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
        for key,command in COMMANDS[:6]:h.apply(key,command)
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

    def test_invalid_native_line_reference_reports_field_path_and_remains_strict(self):
        for value,kind in [("native_params({},'opaque')",'userdata'),('false','boolean'),('-2','number'),('1.5','number')]:
            h=Harness();h.build();h.lua.execute('world[vehicle_id].TRANSPORT_VEHICLE.line='+value)
            errors='\n'.join(h.snapshot()['coverage']['missing'])
            self.assertIn('b:3.TRANSPORT_VEHICLE.line',errors)
            self.assertIn('Lua type='+kind,errors)
            self.assertNotIn('bad argument',errors)

    def test_disconnected_equal_coordinate_node_changes_actual_connectivity(self):
        h=Harness();before=h.build()
        h.lua.globals().depot_entity=h.e.local_bindings()['b:1']
        h.lua.execute('''
          local e=world[world[depot_entity].CONSTRUCTION.frozenEdges[1]].BASE_EDGE
          local id=fresh();world[id]={BASE_NODE={position=copy(world[e.node1].BASE_NODE.position)}};e.node1=id
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
