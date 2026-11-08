import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DocsQuoteTheRealTestCount(unittest.TestCase):
    """README.md and WRITEUP.md quote how many tests there are. They were fixed
    by hand after every new test and fell behind more than once."""

    def test_every_quoted_count_matches_the_suite(self):
        # a fresh loader, so counting does not disturb the run that is counting
        n = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests")).countTestCases()
        for name in ("README.md", "WRITEUP.md"):
            quoted = [int(x) for x in re.findall(r"\b(\d+) tests\b", (ROOT / name).read_text(encoding="utf-8"))]
            self.assertTrue(quoted, f"{name} quotes no test count")
            self.assertEqual(set(quoted), {n}, f"{name} quotes {quoted}; the suite has {n}")


if __name__ == "__main__":
    unittest.main()
