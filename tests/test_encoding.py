import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What a machine with a non-UTF-8 default looks like: ASCII here, a Windows code page there.
# The dataset holds non-ASCII on purpose (the held-out set has Cyrillic look-alikes), and its
# hash is pinned, so reading, writing and regenerating it must not depend on that default.
HOSTILE = {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}


def run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "sequela.run", *argv], cwd=ROOT, env=HOSTILE,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


class NonUtf8DefaultEncoding(unittest.TestCase):
    def test_the_environment_really_is_hostile(self):
        out = subprocess.run([sys.executable, "-c", "import locale; print(locale.getpreferredencoding(False))"],
                             env=HOSTILE, capture_output=True, text=True)
        self.assertNotIn("utf", out.stdout.lower(), "the test would prove nothing if the default were UTF-8")

    def test_check_reads_the_non_ascii_dataset(self):
        r = run("check")
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertIn("is current", r.stdout)

    def test_a_result_with_non_ascii_is_written_and_read_back(self):
        out = Path(tempfile.mkdtemp()) / "held.json"
        r = run("run", "reference:memorised", "--heldout", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        out.read_bytes().decode("utf-8")        # raises if what was written is not UTF-8
        r = run("report", str(out))
        self.assertEqual(r.returncode, 0, r.stderr[-300:])


if __name__ == "__main__":
    unittest.main()
