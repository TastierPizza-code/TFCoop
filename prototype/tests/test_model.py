import unittest

from prototype.strict_sync.model import ModelEngine, ModelError, scenario


class ModelTests(unittest.TestCase):
    def test_independent_entity_ids_and_paused_builds(self):
        engines = [ModelEngine(100), ModelEngine(9000)]
        seq = {"a": 0, "b": 0}
        for round_number in range(14):
            for peer in ("a", "b"):
                for command in scenario(peer).get(round_number, []):
                    seq[peer] += 1
                    receipts = [e.apply(command, f"{peer}:{seq[peer]}") for e in engines]
                    self.assertEqual(receipts[0], receipts[1])
                    self.assertTrue(receipts[0]["success"], receipts)
            for engine in engines:
                engine.step(0 if engine.paused else 100000)
            self.assertEqual(engines[0].snapshot(), engines[1].snapshot())
        self.assertNotEqual(engines[0].physical_ids, engines[1].physical_ids)
        self.assertEqual(engines[0].vehicles["seed:vehicle"]["line"], None)
        self.assertEqual(engines[0].vehicles["a:5"]["line"], "a:3")
        self.assertEqual(engines[0].lines["a:3"]["stops"], ["a:2", "seed:depot", "a:2"])
        self.assertEqual(engines[0].time_us, 800000)

    def test_failures_do_not_modify_world_or_allocate_ids(self):
        engine = ModelEngine()
        state, ids = engine.snapshot(), dict(engine.physical_ids)
        result = engine.apply({"op": "VEHICLE_BUY", "depot": "missing", "model": "x"}, "a:1")
        self.assertFalse(result["success"])
        self.assertEqual(engine.snapshot(), state)
        self.assertEqual(engine.physical_ids, ids)

    def test_duplicate_does_not_buy_twice(self):
        engine = ModelEngine()
        command = {"op": "VEHICLE_BUY", "depot": "seed:depot", "model": "x"}
        first = engine.apply(command, "a:1")
        self.assertEqual(engine.apply(command, "a:1"), first)
        self.assertEqual(len(engine.vehicles), 2)
        with self.assertRaises(ModelError):
            engine.apply({**command, "model": "y"}, "a:1")

    def test_digest_detects_non_geometric_changes(self):
        for field, value in (("cargo", 1), ("stopped", False), ("maintenance", 50), ("line", "x")):
            engine = ModelEngine()
            before = engine.state_digest
            engine.vehicles["seed:vehicle"][field] = value
            self.assertNotEqual(engine.state_digest, before)

    def test_unapproved_simulation_during_pause_refused(self):
        engine = ModelEngine()
        with self.assertRaises(ModelError):
            engine.step(100000)
        self.assertEqual(engine.time_us, 0)


if __name__ == "__main__":
    unittest.main()
