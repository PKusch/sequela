import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sequela.run import DATA, _sha, main


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

    def test_a_result_with_a_response_missing_parsed_says_so(self):
        sha = _sha(DATA)
        bad = json.dumps({"respondent": "x", "tasks_sha": sha, "responses": {"t1": {"raw": "h"}}})
        for cmd in ("score", "report"):
            code, _ = run_cli(cmd, self.write(f"{cmd}-noparsed.json", bad))
            self.assertIsInstance(code, str, cmd)
            self.assertIn("no 'parsed' field", code)

    def test_a_result_with_no_responses_says_so(self):
        sha = _sha(DATA)
        for shape in ("{}", "[]"):
            body = json.dumps({"respondent": "x", "tasks_sha": sha, "responses": json.loads(shape)})
            code, _ = run_cli("report", self.write(f"empty-{shape[0]}.json", body))
            self.assertIsInstance(code, str, shape)
            self.assertIn("no responses to score", code)

    def test_a_non_positive_limit_is_refused(self):
        # --limit 0 was falsy and ran the whole set; a negative sliced from the end.
        for bad in ("0", "-5"):
            code, err = run_cli("run", "reference:oracle", "--limit", bad)
            self.assertEqual(code, 2, bad)
            self.assertIn("at least 1", err)

    def test_a_bad_output_path_is_refused_before_any_task_is_answered(self):
        # the result is written last, so a bad --out used to surface only after the
        # whole run: against a hosted model, a run paid for and thrown away
        import sequela.run as run
        calls = []
        real = run.resolve
        run.resolve = lambda name: ("counting", lambda task: calls.append(task["id"]))
        try:
            code, _ = run_cli("run", "x:y", "--limit", "3", "--out", str(self.tmp))
        finally:
            run.resolve = real
        self.assertIsInstance(code, str)
        self.assertIn("is a directory", code)
        self.assertEqual(calls, [], "no task was answered")

    def test_a_model_kind_with_no_model_name_is_refused(self):
        for spec in ("ollama:", "openai:", "ollama:  "):
            code, _ = run_cli("run", spec, "--limit", "1", "--out", str(self.tmp / "x.json"))
            self.assertIsInstance(code, str, spec)
            self.assertIn("name a model", code)
            self.assertFalse((self.tmp / "x.json").exists())

    def test_a_run_whose_first_call_cannot_reach_the_model_stops_and_writes_nothing(self):
        from unittest import mock
        def unreachable(task):
            unreachable.last_raw = "error: <urlopen error [Errno 61] Connection refused>"
            return None
        out = self.tmp / "x.json"
        with mock.patch("sequela.run.resolve", return_value=("ollama:gemma3", unreachable)):
            code, _ = run_cli("run", "ollama:gemma3", "--limit", "3", "--out", str(out))
        self.assertIsInstance(code, str)
        self.assertIn("the first call to ollama:gemma3 failed", code)
        self.assertFalse(out.exists())

    def test_an_unreadable_answer_from_a_reachable_model_still_counts_against_it(self):
        from unittest import mock
        def rambling(task):
            rambling.last_raw = "I would rather not say."
            return None
        out = self.tmp / "x.json"
        with mock.patch("sequela.run.resolve", return_value=("ollama:gemma3", rambling)):
            code, _ = run_cli("run", "ollama:gemma3", "--limit", "2", "--out", str(out))
        self.assertEqual(code, 0)
        self.assertTrue(out.exists())

    def test_report_with_only_held_out_results_says_so(self):
        code, err = run_cli("report", "results/local/ollama_gemma3_12b.heldout.json")
        self.assertEqual(code, 2)
        self.assertIn("needs at least one main result", err)

    def test_a_result_saved_with_a_byte_order_mark_is_read(self):
        # Notepad and Excel add one when they save; it used to read as "not JSON".
        p = self.tmp / "bom.json"
        p.write_bytes(b"\xef\xbb\xbf" + Path("results/local/ollama_gemma3.json").read_bytes())
        code, err = run_cli("score", str(p))
        self.assertEqual(code, 0, err)

    def test_a_copy_without_the_dataset_says_where_to_run_it(self):
        from unittest import mock
        with mock.patch("sequela.run.DATA", self.tmp / "data" / "tasks.jsonl"):
            code, err = run_cli("check")
        self.assertEqual(code, 2)
        self.assertIn("run it from a clone of the repository", err)

    def test_the_readme_check_reads_a_live_result_saved_with_a_byte_order_mark(self):
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location("crn", "scripts/check_readme_numbers.py")
        crn = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(crn)
        (self.tmp / "x.json").write_bytes(b"\xef\xbb\xbf" + Path("results/local/ollama_gemma3.json").read_bytes())
        with mock.patch.object(crn, "LOCAL_RESULTS", self.tmp):
            self.assertIn("ollama:gemma3", crn.local_results())

    def test_a_real_result_still_works(self):
        out = self.tmp / "o.json"
        code, _ = run_cli("run", "reference:oracle", "--limit", "5", "--out", str(out))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text())["respondent"], "reference:oracle")
        code, _ = run_cli("report", str(out))
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
