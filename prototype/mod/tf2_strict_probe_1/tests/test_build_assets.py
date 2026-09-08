"""Headless scene geometry checks against this PC's literal installed TF2 assets.

Runs Lua asset functions only. Does not load the game engine, write game files,
start the game, or assert that the engine accepted any build. The stock-resource
checks skip explicitly on machines without the named installation.
"""
from pathlib import Path
import importlib
import os
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'tests/lua/.deps'))
MOD = HERE.parent
GAME_RES = Path(os.environ.get('TF2_TEST_GAME_RES', r'X:\SteamLibrary\steamapps\common\Transport Fever 2\res'))


class SceneAssetTests(unittest.TestCase):
    def setUp(self):
        if not (GAME_RES / 'construction/construction.zip').is_file():
            self.skipTest('installed stock TF2 construction archive unavailable')
        self.lua = RUNTIME(unpack_returned_tuples=True)
        self.lua.globals().asset_path = (GAME_RES / 'scripts/?.lua').as_posix()
        self.lua.execute('package.path=asset_path')
        # Only stock pure-Lua helpers, before init.lua defines engine bindings.
        self.lua.execute((GAME_RES / 'scripts/init.lua').read_text(encoding='utf-8').split('api = {}')[0])
        self.lua.execute('_=function(s) return s end')
        self.assets = self.lua.execute((MOD / 'res/scripts/tf2_strict_probe/build_assets.lua').read_text(encoding='utf-8'))
        self.lua.globals().assets = self.assets

    def stock(self, relative, archive='construction/construction.zip'):
        with zipfile.ZipFile(GAME_RES / archive) as source:
            self.lua.execute(source.read(relative).decode('utf-8'))
        return self.lua.globals().data()

    def road(self):
        self.lua.execute((MOD / 'res/construction/tf2_strict_probe/road_test.con').read_text(encoding='utf-8'))
        return self.lua.globals().data().updateFn(self.assets.road_params)

    @staticmethod
    def vec(value):
        return tuple(value[i] for i in range(1, len(value) + 1))

    @classmethod
    def alignment_vertices(cls, alignment):
        """Read both documented face and literal stock triangle layouts."""
        for key in ('faces', 'triangles'):
            values = alignment[key]
            if values is None:
                continue
            for _, polygon in values.items():
                if isinstance(polygon[1], (int, float)):
                    yield cls.vec(polygon)
                else:
                    for _, vertex in polygon.items():
                        yield cls.vec(vertex)

    def station(self):
        self.lua.globals().station_con = self.stock(self.assets.stop_file)
        self.lua.globals().passenger = self.stock('station/street/passenger_platform.module')
        self.lua.globals().entrance = self.stock('station/street/entrance_exit.module')
        # Same ordered stock module call contract as ConstructWithModules in
        # base_config.lua, with unchanged stock functions and recipe params.
        self.lua.execute('''
          local p=assets.stop_params
          station_result=station_con.updateFn(p)
          local r=station_result
          local ids={};for id in pairs(p.modules)do ids[#ids+1]=id end;table.sort(ids)
          local transf=require 'transf';local vec3=require 'vec3';local modulesutil=require 'modulesutil'
          for _,id in ipairs(ids)do
            local slot;for _,s in ipairs(r.slots)do if s.id==id then slot=s end end
            assert(slot,'recipe module has no actual stock slot')
            local mod=p.modules[id].name:find('passenger') and passenger or entrance
            local function add(name,t,tag)
              r.models[#r.models+1]={id=name,transf=transf.mul(slot.transf,t or transf.scale(vec3.new(1,1,1))),tag=tag or '__module_'..id}
              return #r.models
            end
            mod.updateFn(r,slot.transf,'__module_'..id,id,add,p)
            modulesutil.addCosts(r,p.modules[id])
          end
          r.terminateConstructionHook()
        ''')
        return self.lua.globals().station_result

    def test_recipe_modules_are_exact_stock_minimum_1850_template(self):
        station = self.stock(self.assets.stop_file)
        params = self.lua.table_from(dict(seed=1, year=1850, paramX=0, paramY=0, tramTrack=0,
                                          templateIndex=0, length=0, platL=1, platR=1))
        generated = dict(station.createTemplateFn(params).items())
        explicit = {key: value.name for key, value in self.assets.stop_params.modules.items()}
        self.assertEqual(generated, explicit)
        for _, value in self.assets.stop_params.modules.items():
            module = self.stock(value.name)
            self.assertEqual(value.metadata.price, module.cost.price)
            self.assertEqual(value.metadata.passenger, module.metadata.passenger)

    def test_literal_station_connector_and_passenger_terminals(self):
        result = self.station()
        self.assertEqual(len(result.stations), 1)
        self.assertEqual(result.stations[1].tag, 1)
        self.assertEqual(self.vec(result.stations[1].terminals), (0, 1))
        self.assertEqual(len(result.terminalGroups), 2)
        self.assertEqual(result.cost, 49000)
        self.assertEqual(len(result.edgeLists), 1)
        edge = result.edgeLists[1]
        self.assertEqual(edge.params.type, 'street_station/entrance_old.lua')
        self.assertEqual(self.vec(edge.snapNodes), (1,))
        connector = self.vec(edge.edges[2][1])
        self.assertEqual(connector, (0, -35, 0, 1))
        connector = connector[:3]
        for i in (1, 2):
            xx, yx, xy, yy = self.vec(self.assets.stop_rotations[i])
            x, y, z = self.vec(self.assets.stop_offsets[i])
            actual = (x + xx * connector[0] + xy * connector[1],
                      y + yx * connector[0] + yy * connector[1], z + connector[2])
            self.assertEqual(actual, ((-100 if i==1 else 100),0,0))
            road = self.vec(self.assets.road_endpoints[i])
            self.assertEqual(abs(actual[0]-road[0]),self.assets.connect_gap)
            self.assertEqual(actual[1:],road[1:])
            self.assertEqual(self.vec(self.assets.stop_snap),connector)

    def test_literal_depot_connector_leaves_explicit_twenty_metre_link(self):
        depot = self.stock(self.assets.depot_file)
        result = depot.updateFn(self.assets.depot_params)
        self.assertEqual(depot.type, 'STREET_DEPOT')
        self.assertEqual(len(result.edgeLists), 1)
        edge = result.edgeLists[1]
        self.assertEqual(self.vec(edge.snapNodes), (1,))
        connector = self.vec(edge.edges[2][1])
        self.assertEqual(connector, (0, -30.4153, 0))
        offset = self.vec(self.assets.depot_offset)
        actual=tuple(offset[i]+connector[i] for i in range(3))
        self.assertEqual(self.vec(self.assets.depot_snap),connector)
        self.assertEqual(self.assets.connect_gap,20)
        for got, expected in zip(actual, (0,60,0)):
            self.assertAlmostEqual(got, expected, places=9)
        self.assertAlmostEqual(actual[1]-self.assets.road_endpoints[3][2],self.assets.connect_gap,places=9)

    def test_manual_depot_sites_cover_literal_rotated_stock_clearance(self):
        manual = self.lua.execute((MOD / 'res/scripts/tf2_strict_probe/manual_depot_assets.lua').read_text(encoding='utf-8'))
        result = self.stock(self.assets.depot_file).updateFn(self.assets.depot_params)
        points = [vertex for _, alignment in result.terrainAlignmentLists.items()
                  for vertex in self.alignment_vertices(alignment)]
        for _, collider in result.colliders.items():
            self.assertEqual(collider.type, 'POINT_CLOUD')
            points.extend(self.vec(point) for _, point in collider.params.points.items())
        for _, edges in result.edgeLists.items():
            points.extend(self.vec(edge[1]) for _, edge in edges.edges.items())
        self.assertGreater(len(points), 100)
        self.assertEqual(set(manual.rotations.keys()), {0, 90, 180, 270})
        for _, rotation in manual.rotations.items():
            xx, yx, xy, yy = self.vec(rotation)
            for x, y, *_ in points:
                self.assertLessEqual(abs(xx*x+xy*y), manual.half_extent)
                self.assertLessEqual(abs(yx*x+yy*y), manual.half_extent)
        for _, offset in manual.sites.items():
            self.assertLessEqual(abs(offset[1])+manual.half_extent, self.assets.half_extent)
            self.assertLessEqual(abs(offset[2])+manual.half_extent, self.assets.half_extent)

    def test_owned_road_graph_has_three_branches_and_no_free_nodes(self):
        result = self.road()
        self.assertEqual(len(result.edgeLists), 1)
        edge = result.edgeLists[1]
        self.assertEqual(edge.params.type, self.assets.street_type)
        self.assertTrue((GAME_RES / 'config/street' / self.assets.street_type).is_file())
        self.assertEqual(len(edge.edges), 6)
        self.assertEqual(len(edge.freeNodes), 0)
        self.assertEqual(self.vec(edge.snapNodes), (0, 3, 5))
        degrees = {}
        for i in range(1, 7):
            position = self.vec(edge.edges[i][1])
            degrees[position] = degrees.get(position, 0) + 1
        self.assertEqual(degrees.pop(self.vec(self.assets.road_junction)), 3)
        self.assertEqual(degrees, {self.vec(endpoint): 1 for _, endpoint in self.assets.road_endpoints.items()})

    def test_pad_covers_actual_stock_alignment_faces_with_margin(self):
        pad = self.road().terrainAlignmentLists[1]
        vertices = list(self.alignment_vertices(pad))
        self.assertEqual(len(vertices), 4)
        x_min, x_max = min(v[0] for v in vertices), max(v[0] for v in vertices)
        y_min, y_max = min(v[1] for v in vertices), max(v[1] for v in vertices)
        station = self.station()
        depot = self.stock(self.assets.depot_file).updateFn(self.assets.depot_params)
        placements = [(depot, self.vec(self.assets.depot_offset), (1, 0, 0, 1))]
        placements += [(station, self.vec(self.assets.stop_offsets[i]), self.vec(self.assets.stop_rotations[i])) for i in (1, 2)]
        observed = []
        for result, offset, rotation in placements:
            xx, yx, xy, yy = rotation
            for _, alignment in result.terrainAlignmentLists.items():
                points = list(self.alignment_vertices(alignment))
                self.assertTrue(points, 'stock alignment has no tested geometry')
                for vertex in points:
                    x = offset[0] + xx * vertex[0] + xy * vertex[1]
                    y = offset[1] + yx * vertex[0] + yy * vertex[1]
                    observed.append((x, y))
                    self.assertGreaterEqual(x, x_min + 10)
                    self.assertLessEqual(x, x_max - 10)
                    self.assertGreaterEqual(y, y_min + 10)
                    self.assertLessEqual(y, y_max - 10)
                    # A flat pad must not contradict a stock terrain rule.
                    z = offset[2] + vertex[2]
                    if alignment.type == 'EQUAL':
                        self.assertAlmostEqual(z, 0)
                    elif alignment.type == 'GREATER':
                        self.assertLessEqual(z, 0)
                    elif alignment.type == 'LESS':
                        self.assertGreaterEqual(z, 0)
                    else:
                        self.fail('unverified stock terrain alignment policy')
        self.assertEqual(min(p[0] for p in observed), -150)
        self.assertEqual(max(p[0] for p in observed), 150)
        self.assertAlmostEqual(max(p[1] for p in observed), 125.23644)

    def test_pad_covers_road_width_and_leaves_checked_earthwork_margin(self):
        road = self.road()
        self.assertEqual(len(road.terrainAlignmentLists), 1)
        pad = road.terrainAlignmentLists[1]
        self.assertEqual(pad.type, 'EQUAL')
        self.assertFalse(pad.optional)
        vertices = list(self.alignment_vertices(pad))
        self.assertEqual({v[2] for v in vertices}, {0})
        self.assertEqual(pad.slopeLow, 0.6)
        self.assertEqual(pad.slopeHigh, 0.6)
        x_min, x_max = min(v[0] for v in vertices), max(v[0] for v in vertices)
        y_min, y_max = min(v[1] for v in vertices), max(v[1] for v in vertices)
        self.lua.execute((GAME_RES / 'config/street' / self.assets.street_type).read_text(encoding='utf-8'))
        street = self.lua.globals().data()
        road_half_width = street.streetWidth / 2 + street.sidewalkWidth
        for _, edge in road.edgeLists[1].edges.items():
            x, y, _ = self.vec(edge[1])
            self.assertGreaterEqual(x - road_half_width, x_min)
            self.assertLessEqual(x + road_half_width, x_max)
            self.assertGreaterEqual(y - road_half_width, y_min)
            self.assertLessEqual(y + road_half_width, y_max)
        margin = self.assets.half_extent - max(abs(c) for v in vertices for c in v[:2])
        self.assertGreaterEqual(margin, 10)
        max_sampled_cut_fill = self.assets.max_height_span / 2
        self.assertLess(max_sampled_cut_fill / pad.slopeLow, margin)
        self.assertEqual(self.assets.id, 'road-depot-service-v3')
        self.assertEqual(self.assets.half_extent,180)
        self.assertEqual((x_min,x_max,y_min,y_max),(-160,160,-40,140))
        self.assertEqual(self.assets.connection_tolerance,0.01)
        self.assertEqual(self.assets.preferred_height_span, 2)
        self.assertEqual(self.assets.max_height_span, 8)

    def test_stock_vehicle_is_1850_road_passenger_single_load_config(self):
        names = self.vec(self.assets.vehicle_models)
        self.assertEqual(len(names), 3)
        self.assertIn(self.assets.vehicle_model, names)
        for name in names:
            with self.subTest(model=name):
                vehicle = self.stock('model/' + name, 'models/model.zip')
                meta = vehicle.metadata
                self.assertLessEqual(meta.availability.yearFrom, 1850)
                self.assertGreaterEqual(meta.availability.yearTo, 1850)
                self.assertEqual(meta.transportVehicle.carrier, 'ROAD')
                compartments = meta.transportVehicle.compartmentsList
                self.assertEqual(len(compartments), 1)
                self.assertEqual(len(compartments[1].loadConfigs), 1)
                self.assertEqual(compartments[1].loadConfigs[1].cargoEntries[1].type, 'PASSENGERS')
        self.assertEqual(self.vec(self.assets.vehicle_load_config), (0,))
        self.assertEqual(self.vec(self.assets.vehicle_auto_load_config), (1,))
        self.assertEqual(self.vec(self.assets.vehicle_groups), (1,))


if __name__ == '__main__':
    success = True
    for version in ('lua51', 'lua52', 'lua53', 'lua54'):
        RUNTIME = importlib.import_module('lupa.' + version).LuaRuntime
        outcome = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(SceneAssetTests))
        print(version, 'stock asset checks:', outcome.testsRun, 'skipped:', len(outcome.skipped))
        success = outcome.wasSuccessful() and success
    raise SystemExit(0 if success else 1)
