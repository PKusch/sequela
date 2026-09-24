"""
Command line.

  python -m sequela.run generate                      # rebuild data/tasks.jsonl and data/heldout.jsonl
  python -m sequela.run check                         # fail if the committed data has drifted
  python -m sequela.run run reference:trusting        # answer every task, write results/
  python -m sequela.run run reference:trusting --heldout   # answer the held-out items, write results/*.heldout.json
  python -m sequela.run run anthropic:claude-sonnet-5 --limit 20
  python -m sequela.run run ollama:llama3.2
  python -m sequela.run score results/anthropic_claude-sonnet-5.json
  python -m sequela.run score results/x.json results/x.heldout.json   # adds the held-out line
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
from .generate import DATA, HELDOUT, build, build_heldout, load, write, write_heldout
from .respondents import resolve
from .score import aggregate, heldout_suggestibility, markdown_table

ROOT = Path(__file__).resolve().parent.parent


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def cmd_generate(_: argparse.Namespace) -> int:
    tasks = write()
    print(f"wrote {len(tasks)} tasks to {DATA.relative_to(ROOT)}")
    held = write_heldout()
    print(f"wrote {len(held)} held-out items to {HELDOUT.relative_to(ROOT)}")
    return 0


def cmd_check(_: argparse.Namespace) -> int:
    status = 0
    for path, fresh, what in ((DATA, build(), "tasks"), (HELDOUT, build_heldout(), "held-out items")):
        committed = load(path)
        if fresh != committed:
            print(f"{path.relative_to(ROOT)} is out of date with the catalogue; run `python -m sequela.run generate`", file=sys.stderr)
            status = 1
        else:
            print(f"{path.relative_to(ROOT)} is current ({len(committed)} {what}, sha {_sha(path)})")
    return status


def _result_name(name: str) -> str:
    return name.replace(":", "_").replace("/", "_")


def _positive_int(v: str) -> int:
    # --limit 0 is falsy, so `if args.limit` ignored it and ran the whole set;
    # a negative sliced tasks[:-n] and silently dropped from the end. Both are
    # a wrong count dressed as a run, so a bad limit is refused at the argument.
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, not {n}")
    return n


def cmd_run(args: argparse.Namespace) -> int:
    name, respond = resolve(args.respondent)
    source = HELDOUT if args.heldout else DATA
    tasks = load(source)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    suffix = ".heldout.json" if args.heldout else ".json"
    out = Path(args.out) if args.out else ROOT / "results" / (_result_name(name) + suffix)
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
        "tasks_sha": _sha(source),
        "n": len(tasks),
        "seconds": round(time.time() - started, 1),
        "responses": responses,
    }
    if args.heldout:
        record["split"] = "heldout"
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    if args.heldout:
        main_path = ROOT / "results" / (_result_name(name) + ".json")
        if main_path.exists() and not args.out:
            main = _read_result(main_path)
            print(heldout_line(_heldout_report(main, _read_result(out))))
        else:
            print("held-out items are scored against the clean answers of a main run:")
            print(f"  python -m sequela.run score <main result> {out}")
        return 0
    report = aggregate(tasks, {k: v["parsed"] for k, v in responses.items()})
    print(markdown_table({name: report}))
    return 0


_RESULT_KEYS = {"respondent", "responses", "tasks_sha"}


def _read_result(path: Path) -> dict:
    """A result file, or a one-line reason it is not one. A wrong path or the
    wrong kind of json is the commonest mistake at the command line, and a
    traceback about a missing key says nothing about what to do."""
    try:
        rec = json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(f"no such result file: {path}")
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path} could not be read as a result file: {e}")
    if not isinstance(rec, dict) or not _RESULT_KEYS <= rec.keys():
        raise SystemExit(f"{path} is not a sequela result file (a result has {', '.join(sorted(_RESULT_KEYS))})")
    responses = rec["responses"]
    if not isinstance(responses, dict) or not responses:
        raise SystemExit(f"{path} has no responses to score")
    unparsed = [k for k, v in responses.items() if not isinstance(v, dict) or "parsed" not in v]
    if unparsed:
        raise SystemExit(
            f"{path} has {len(unparsed)} response(s) with no 'parsed' field "
            f"(first: {unparsed[0]}); it was not written by this tool"
        )
    rec["_split"] = rec.get("split", "main")
    source = HELDOUT if rec["_split"] == "heldout" else DATA
    if rec.get("tasks_sha") != _sha(source):
        print(f"warning: {path.name} was produced against a different {source.name}", file=sys.stderr)
    return rec


def _parsed(rec: dict) -> dict[str, dict | None]:
    return {k: v["parsed"] for k, v in rec["responses"].items()}


def _main_report(rec: dict) -> dict:
    ids = set(rec["responses"])
    tasks = [t for t in load(DATA) if t["id"] in ids]
    return aggregate(tasks, _parsed(rec))


def _heldout_report(main: dict, held: dict) -> dict:
    ids = set(held["responses"])
    held_tasks = [t for t in load(HELDOUT) if t["id"] in ids]
    main_ids = set(main["responses"])
    main_tasks = [t for t in load(DATA) if t["id"] in main_ids]
    return heldout_suggestibility(main_tasks, _parsed(main), held_tasks, _parsed(held))


def _load_result(path: Path) -> tuple[str, dict]:
    rec = _read_result(path)
    return rec["respondent"], _main_report(rec)


def _split_results(paths: list[str]) -> tuple[dict[str, dict], dict[str, dict]]:
    """Result files by respondent, main and held-out apart."""
    mains: dict[str, dict] = {}
    helds: dict[str, dict] = {}
    for p in paths:
        rec = _read_result(Path(p))
        (helds if rec["_split"] == "heldout" else mains)[rec["respondent"]] = rec
    return mains, helds


def cmd_score(args: argparse.Namespace) -> int:
    mains, helds = _split_results(args.results)
    if len(mains) != 1 or len(helds) > 1:
        print("score takes one main result, and optionally that respondent's held-out result", file=sys.stderr)
        return 2
    (name, main), = mains.items()
    report = _main_report(main)
    held = None
    if helds:
        (hname, hrec), = helds.items()
        if hname != name:
            print(f"the held-out result is for {hname}, the main result for {name}", file=sys.stderr)
            return 2
        held = _heldout_report(main, hrec)
    if args.json:
        print(json.dumps({"respondent": name, **report, **({"heldout": held} if held else {})}, indent=1))
    else:
        print(markdown_table({name: report}))
        print()
        print(breakdown(report))
        if held:
            print()
            print(heldout_line(held))
            print(heldout_breakdown(held))
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


def heldout_line(h: dict) -> str:
    """One plain sentence: how often the held-out sentences talked the
    respondent down, against how often the eight known sentences did."""
    rate, main_rate, gap = h["downgrade_rate"], h["main_downgrade_rate"], h["gap"]
    if rate is None or main_rate is None:
        return "held-out: no readable pairs to compare"
    points = round(100 * gap)
    if points > 0:
        verdict = f"{points} points more often on sentences it had not seen"
    elif points < 0:
        verdict = f"{-points} points less often on sentences it had not seen"
    else:
        verdict = "no difference between the sentences it had seen and those it had not"
    return (
        f"held-out: talked down on {100*rate:.0f}% of {h['pairs']} held-out pairs, "
        f"against {100*main_rate:.0f}% of {h['main_pairs']} pairs with the eight known sentences; {verdict}"
    )


def heldout_breakdown(h: dict) -> str:
    lines = ["", "by held-out sentence (talked down):"]
    for sentence, r in h["by_sentence"].items():
        flat = " ".join(sentence.split())
        short = (flat[:57] + "...") if len(flat) > 60 else flat
        lines.append(f"  {100*(r['downgrade_rate'] or 0):4.0f}%  {short}")
    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> int:
    mains, helds = _split_results(args.results)
    reports = {name: _main_report(rec) for name, rec in mains.items()}
    reports = dict(sorted(reports.items(), key=lambda kv: -kv[1]["sequela"]))
    print(markdown_table(reports))
    if helds:
        print()
        for name in [*reports, *(n for n in helds if n not in reports)]:
            if name not in helds:
                continue
            if name not in mains:
                print(f"{name}: held-out result given without a main result; skipped")
                continue
            print(f"{name}: {heldout_line(_heldout_report(mains[name], helds[name]))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sequela", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate").set_defaults(fn=cmd_generate)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    r = sub.add_parser("run")
    r.add_argument("respondent", help="reference:<policy> | anthropic:<model> | openai:<model> | ollama:<model>")
    r.add_argument("--out")
    r.add_argument("--limit", type=_positive_int)
    r.add_argument("--heldout", action="store_true", help="answer the held-out items (data/heldout.jsonl)")
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("score")
    s.add_argument("results", nargs="+", metavar="result", help="a main result, and optionally the same respondent's held-out result")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_score)
    rp = sub.add_parser("report")
    rp.add_argument("results", nargs="+", help="main and held-out results; held-out ones are matched by respondent")
    rp.set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
