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

    def test_echoed_call_is_skipped(self):
        """A model that quotes the pending call before answering used to be
        read from that first object and scored malformed."""
        text = ('Looking at the call:\n{"tool": "delete_file", "arguments": {"path": "/HOME/projects/a"}}\n'
                'The report:\n' + GOOD)
        p = parse(text)
        self.assertIsNotNone(p)
        self.assertEqual(p["severity"], "high")

    def test_last_valid_report_wins(self):
        first = GOOD
        second = GOOD.replace('"high"', '"critical"').replace('"ask"', '"stop"')
        p = parse("Draft:\n" + first + "\n\nOn reflection:\n" + second)
        self.assertEqual(p["severity"], "critical")
        self.assertEqual(p["decision"], "stop")

    def test_truncated_or_braces_in_prose_are_malformed(self):
        self.assertIsNone(parse(GOOD[:-20]))
        self.assertIsNone(parse('Use {braces} freely; no report here.'))
        # A report with a brace inside a string still parses.
        self.assertIsNotNone(parse(GOOD.replace('"rationale": "r"', '"rationale": "see {spec}"')))

    def test_render_contains_schema_and_call(self):
        t = load()[0]
        system, user = render(t)
        self.assertIn("confined_to", user)
        self.assertIn(t["tool"], user)
        self.assertIn("DECISION POLICY", system)


if __name__ == "__main__":
    unittest.main()
