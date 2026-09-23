#!/usr/bin/env python3
"""The calibration table and the held-out table in README.md are numbers copied
by hand from a `run` + `report` session. Nothing ever checked that the copy was
right, or that it stays right as the oracle, a policy or the dataset changes.

This recomputes both tables from the committed dataset and the reference
policies in sequela/respondents, and fails on the first cell that does not match
what README.md says. It is a diagnosis, not a fix: it does not know which of the
two sides is wrong, only that they disagree.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sequela.generate import DATA, HELDOUT, load  # noqa: E402
from sequela.respondents import resolve  # noqa: E402
from sequela.score import aggregate, heldout_suggestibility, _pct  # noqa: E402

README = ROOT / "README.md"

MAIN_TABLE_RESPONDENTS = ["oracle", "schema_blind", "name_reader", "paranoid", "uncoupled", "trusting"]
HELDOUT_TABLE_RESPONDENTS = ["oracle", "memorised", "trusting"]

# Same columns as score.markdown_table, minus "malformed" — the README table
# leaves that column out because it is 0% for every reference policy.
COLUMNS = [
    ("sequela", lambda r: f"{r['sequela']:.2f}"),
    ("95% CI", lambda r: f"{r['sequela_ci'][0]:.2f}–{r['sequela_ci'][1]:.2f}"),
    ("understated", lambda r: _pct(r["monitoring"]["understatement_rate"])),
    ("overstated", lambda r: _pct(r["monitoring"]["overstatement_rate"])),
    ("escape TPR", lambda r: _pct(r["monitoring"]["escape_tpr"])),
    ("count exact", lambda r: _pct(r["monitoring"]["count_exact"])),
    ("dest. exact", lambda r: _pct(r["monitoring"]["destinations_exact"])),
    ("coupling", lambda r: _pct(r["control"]["coupling"])),
    ("decision ok", lambda r: _pct(r["control"]["decision_correct"])),
    ("downgraded", lambda r: _pct(r["suggestibility"]["downgrade_rate"])),
]


def respond_all(name: str, tasks: list[dict]) -> dict[str, dict | None]:
    _, respond = resolve(f"reference:{name}")
    return {t["id"]: respond(t) for t in tasks}


def table_rows(text: str, heading: str) -> list[list[str]]:
    """The pipe-delimited rows of the first table under `heading`, cells trimmed."""
    section = re.split(r"\n#{2,3} ", text.split(heading, 1)[1], maxsplit=1)[0]
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] not in ("respondent",):
            rows.append(cells)
    return rows


def short_name(cell: str) -> str:
    """'`schema_blind` — reads the arguments, never the schema' -> 'schema_blind'."""
    m = re.match(r"`([a-z_]+)`", cell)
    return m.group(1) if m else cell


def main() -> int:
    text = README.read_text(encoding="utf-8")
    main_tasks = load(DATA)
    heldout_tasks = load(HELDOUT)
    problems = 0

    # --- the calibration table -------------------------------------------------
    readme_rows = {short_name(r[0]): r[1:] for r in table_rows(text, "## Calibration: what the instrument can see")}
    for name in MAIN_TABLE_RESPONDENTS:
        report = aggregate(main_tasks, respond_all(name, main_tasks))
        expected = [f(report) for _, f in COLUMNS]
        actual = readme_rows.get(name)
        if actual is None:
            print(f"  ✗ calibration table: no README row for `{name}`")
            problems += 1
            continue
        for (col, _), exp, act in zip(COLUMNS, expected, actual):
            if exp != act:
                print(f"  ✗ calibration table, {name}, {col}: README says '{act}', recomputed '{exp}'")
                problems += 1

    # --- the held-out table ------------------------------------------------------
    readme_held = {short_name(r[0]): r[1:] for r in table_rows(text, "### The held-out sentences")}
    for name in HELDOUT_TABLE_RESPONDENTS:
        main_responses = respond_all(name, main_tasks)
        held_responses = respond_all(name, heldout_tasks)
        report = aggregate(main_tasks, main_responses)
        held = heldout_suggestibility(main_tasks, main_responses, heldout_tasks, held_responses)
        expected = [
            f"{report['sequela']:.2f}",
            f"{_pct(held['main_downgrade_rate'])} of {held['main_pairs']}",
            f"{_pct(held['downgrade_rate'])} of {held['pairs']}",
            f"{round(100 * held['gap'])} points",
        ]
        actual = readme_held.get(name)
        if actual is None:
            print(f"  ✗ held-out table: no README row for `{name}`")
            problems += 1
            continue
        for col, exp, act in zip(["main set: sequela", "main set: talked down", "held-out: talked down", "gap"], expected, actual):
            if exp != act:
                print(f"  ✗ held-out table, {name}, {col}: README says '{act}', recomputed '{exp}'")
                problems += 1

    print(f"\n{'✗' if problems else '✓'} {problems} mismatch(es) between README.md's tables and a fresh run")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
