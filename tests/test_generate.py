import unittest
from collections import Counter

import re

from sequela.catalogue import INJECTIONS, TOOLS
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

    def test_arguments_stay_inside_what_the_oracle_can_see(self):
        """The oracle is lexical: it does not decode percent escapes, follow
        symlinks, resolve display names or compare IDN look-alikes. The truth
        line is only verifiable by construction if no task argument uses any
        of those forms, so this pins that none does."""
        bare_address = re.compile(r"^[^@\s<>]+@[^@\s<>]+$")
        for t in self.fresh:
            schema = TOOLS[t["tool"]]
            for pname, spec in schema.parameters.items():
                if not spec.role or pname not in t["args"]:
                    continue
                raw = t["args"][pname]
                for v in (raw if isinstance(raw, list) else [raw]):
                    v = str(v)
                    self.assertTrue(v.isascii(), (t["id"], pname, v))
                    self.assertNotIn("%", v, (t["id"], pname))
                    self.assertNotIn("\\", v, (t["id"], pname))
                    self.assertNotIn("xn--", v.lower(), (t["id"], pname))
                    if spec.role == "recipient" and spec.confined_to:
                        # Where a domain boundary applies, the recipient must be a
                        # bare address; a channel like '#deploys' only appears
                        # on tools with no boundary to compare it against.
                        self.assertRegex(v, bare_address, (t["id"], pname))
                    elif spec.role == "recipient":
                        self.assertNotRegex(v, r"[<>\s]", (t["id"], pname))

    def test_every_injection_sentence_is_used_equally(self):
        """Eight phrasings, rotated: each gets the same share, so a per-sentence
        number is computed over the same n as every other."""
        c = Counter(t["injection"] for t in self.fresh if t["condition"] == "injected")
        self.assertEqual(set(c), set(INJECTIONS))
        self.assertEqual(len(set(c.values())), 1, c)


if __name__ == "__main__":
    unittest.main()
