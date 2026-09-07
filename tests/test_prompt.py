import unittest

from sequela.prompt import parse, render
from sequela.generate import load

GOOD = '{"severity": "high", "reversibility": "irreversible", "affected_count": 2, "destinations": ["https://x.example/a"], "escapes_boundary": false, "decision": "ask", "rationale": "r"}'


class Parse(unittest.TestCase):
    def test_plain(self):
        p = parse(GOOD)
        self.assertEqual(p["severity"], "high")
        self.assertEqual(p["affected_count"], 2)

    def test_fenced_and_prose(self):
        p = parse("Here you go:\n```json\n" + GOOD + "\n```\nHope that helps.")
        self.assertEqual(p["decision"], "ask")

    def test_unbounded_and_case(self):
        p = parse('{"severity": "Critical", "reversibility": "IRREVERSIBLE", "affected_count": "unbounded", "destinations": [], "escapes_boundary": "true", "decision": "Stop"}')
        self.assertEqual(p["affected_count"], "unbounded")
        self.assertTrue(p["escapes_boundary"])
        self.assertEqual(p["decision"], "stop")

    def test_garbage(self):
        self.assertIsNone(parse("I would rather not."))
        self.assertIsNone(parse('{"severity": "enormous", "reversibility": "reversible", "affected_count": 1, "destinations": [], "escapes_boundary": false, "decision": "ask"}'))
        self.assertIsNone(parse('{"severity": "low", "reversibility": "reversible", "affected_count": "some", "destinations": [], "escapes_boundary": false, "decision": "ask"}'))

    def test_render_contains_schema_and_call(self):
        t = load()[0]
        system, user = render(t)
        self.assertIn("confined_to", user)
        self.assertIn(t["tool"], user)
        self.assertIn("DECISION POLICY", system)


if __name__ == "__main__":
    unittest.main()
