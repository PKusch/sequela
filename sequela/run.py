"""
Command line.

  python -m sequela.run generate                      # rebuild data/tasks.jsonl
  python -m sequela.run check                         # fail if the committed data has drifted
  python -m sequela.run run reference:trusting        # answer every task, write results/
  python -m sequela.run run anthropic:claude-sonnet-5 --limit 20
  python -m sequela.run run ollama:llama3.2
  python -m sequela.run score results/anthropic_claude-sonnet-5.json
  python -m sequela.run report results/reference/*.json   # comparison table
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .generate import DATA, build, load, write
from .respondents import resolve
from .score import aggregate, markdown_table

ROOT = Path(__file__).resolve().parent.parent


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def cmd_generate(_: argparse.Namespace) -> int:
    tasks = write()
    print(f"wrote {len(tasks)} tasks to {DATA.relative_to(ROOT)}")
    return 0


def cmd_check(_: argparse.Namespace) -> int:
    fresh = build()
    committed = load()
    if fresh != committed:
        print("data/tasks.jsonl is out of date with the catalogue; run `python -m sequela.run generate`", file=sys.stderr)
        return 1
    print(f"data/tasks.jsonl is current ({len(committed)} tasks, sha {_sha(DATA)})")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    name, respond = resolve(args.respondent)
    tasks = load()
    if args.limit:
        tasks = tasks[: args.limit]
    out = Path(args.out) if args.out else ROOT / "results" / (name.replace(":", "_").replace("/", "_") + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    responses: dict[str, dict] = {}
    started = time.time()
    for i, t in enumerate(tasks, 1):
        t0 = time.time()
        parsed = respond(t)
        responses[t["id"]] = {
            "parsed": parsed,
            "raw": getattr(respond, "last_raw", None),
            "ms": int(1000 * (time.time() - t0)),
        }
        if args.verbose or i % 25 == 0 or i == len(tasks):
            print(f"  {i}/{len(tasks)} {t['id']} -> {parsed['severity'] + '/' + parsed['decision'] if parsed else 'MALFORMED'}", file=sys.stderr)
    record = {
        "sequela_version": __version__,
        "respondent": name,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tasks_sha": _sha(DATA),
        "n": len(tasks),
        "seconds": round(time.time() - started, 1),
        "responses": responses,
    }
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    report = aggregate(tasks, {k: v["parsed"] for k, v in responses.items()})
    print(markdown_table({name: report}))
    return 0


def _load_result(path: Path) -> tuple[str, dict]:
    rec = json.loads(path.read_text())
    tasks = load()
    if rec.get("tasks_sha") != _sha(DATA):
        print(f"warning: {path.name} was produced against a different tasks.jsonl", file=sys.stderr)
    ids = set(rec["responses"])
    tasks = [t for t in tasks if t["id"] in ids]
    return rec["respondent"], aggregate(tasks, {k: v["parsed"] for k, v in rec["responses"].items()})


def cmd_score(args: argparse.Namespace) -> int:
    name, report = _load_result(Path(args.result))
    if args.json:
        print(json.dumps({"respondent": name, **report}, indent=1))
    else:
        print(markdown_table({name: report}))
        print()
        print(breakdown(report))
    return 0


def breakdown(report: dict) -> str:
    """The parts behind the one number, as plain text: what the interval
    means, where the understatement sits by family, and whether any one
    injection sentence does more than the others."""
    lo, hi = report["sequela_ci"]
    lines = [
        f"score {report['sequela']:.2f}, and on these {report['n']} items anything between {lo:.2f} and {hi:.2f} is the same score",
        "",
        "by family (understated / decision correct):",
    ]
    for fam, r in report["by_family"].items():
        u = r["understatement_rate"]; d = r["decision_correct"]
        lines.append(f"  {fam:<20} n={r['n']:<3} {100*u:5.0f}% / {100*d:5.0f}%")
    if report["by_injection"]:
        lines += ["", "by injection sentence (understated / talked down):"]
        for sentence, r in report["by_injection"].items():
            u = r["understatement_rate"]; dg = r["downgrade_rate"]
            short = (sentence[:57] + "...") if len(sentence) > 60 else sentence
            lines.append(f"  {100*u:4.0f}% / {100*(dg or 0):4.0f}%  {short}")
    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> int:
    reports = {}
    for p in args.results:
        name, rep = _load_result(Path(p))
        reports[name] = rep
    reports = dict(sorted(reports.items(), key=lambda kv: -kv[1]["sequela"]))
    print(markdown_table(reports))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sequela", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate").set_defaults(fn=cmd_generate)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    r = sub.add_parser("run")
    r.add_argument("respondent", help="reference:<policy> | anthropic:<model> | openai:<model> | ollama:<model>")
    r.add_argument("--out")
    r.add_argument("--limit", type=int)
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("score")
    s.add_argument("result")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_score)
    rp = sub.add_parser("report")
    rp.add_argument("results", nargs="+")
    rp.set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
