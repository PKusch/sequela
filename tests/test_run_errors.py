import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sequela.run import main


def run_cli(*argv: str) -> tuple[int | str | None, str]:
    """Exit code (or exit message) and stderr for one command."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            return main(list(argv)), err.getvalue()
        except SystemExit as e:
            return e.code, err.getvalue()


class ResultFileMistakes(unittest.TestCase):
    """The commonest command-line mistakes end in one plain line, not a traceback."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def write(self, name: str, text: str) -> str:
        p = self.tmp / name
        p.write_text(text)
        return str(p)

    def test_a_missing_file_says_so(self):
        for cmd in ("score", "report"):
            code, _ = run_cli(cmd, str(self.tmp / "nope.json"))
            self.assertIsInstance(code, str, cmd)
            self.assertIn("no such result file", code)

    def test_json_that_is_not_a_result_says_what_a_result_has(self):
        for name, text in {"empty.json": "{}", "list.json": "[]", "other.json": '{"respondent": "x"}'}.items():
            code, _ = run_cli("report", self.write(name, text))
            self.assertIsInstance(code, str, name)
            self.assertIn("is not a sequela result file", code)
            self.assertIn("tasks_sha", code)

    def test_text_that_is_not_json_says_so(self):
        code, _ = run_cli("score", self.write("junk.json", "not json at all"))
        self.assertIsInstance(code, str)
        self.assertIn("could not be read as a result file", code)

    def test_a_real_result_still_works(self):
        out = self.tmp / "o.json"
        code, _ = run_cli("run", "reference:oracle", "--limit", "5", "--out", str(out))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text())["respondent"], "reference:oracle")
        code, _ = run_cli("report", str(out))
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
