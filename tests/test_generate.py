import unittest
from collections import Counter

from sequela.generate import build, load
from sequela.oracle import SEVERITY_NAMES


class Dataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fresh = build()
        cls.committed = load()

    def test_committed_matches_catalogue(self):
        self.assertEqual(self.fresh, self.committed)

    def test_size(self):
        self.assertGreaterEqual(len(self.fresh), 250)

    def test_ids_unique(self):
        ids = [t["id"] for t in self.fresh]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_severity_level_present(self):
        c = Counter(t["truth"]["severity"] for t in self.fresh)
        for name in SEVERITY_NAMES:
            if name == "none":
                continue  # every catalogued tool has an effect
            self.assertGreaterEqual(c[name], 12, name)

    def test_injected_twin_has_identical_truth(self):
        by_id = {t["id"]: t for t in self.fresh}
        strip = lambda tr: {k: v for k, v in tr.items() if k != "signals"}
        n = 0
        for t in self.fresh:
            if t["condition"] != "injected":
                continue
            clean = by_id[t["pair"]]
            self.assertEqual(strip(clean["truth"]), strip(t["truth"]), t["id"])
            self.assertIn("instruction_shaped_argument", [s["code"] for s in t["truth"]["signals"]])
            self.assertNotIn("instruction_shaped_argument", [s["code"] for s in clean["truth"]["signals"]])
            n += 1
        self.assertGreaterEqual(n, 100)

    def test_all_recognised(self):
        self.assertTrue(all(t["truth"]["recognised"] for t in self.fresh))


if __name__ == "__main__":
    unittest.main()
