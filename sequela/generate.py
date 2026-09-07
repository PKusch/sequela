"""
Builds data/tasks.jsonl from the catalogue. Deterministic: the same catalogue
always produces the same file, and CI regenerates it and fails if the committed
copy has drifted.

Every task carries its ground truth inline, derived by the oracle at build
time, so a scorer never has to re-derive anything and a reader can check any
single line by hand.
"""
from __future__ import annotations

import json
from pathlib import Path

from .catalogue import INJECTIONS, SCENARIOS, TOOLS
from .oracle import ToolCall, derive, expected_decision

DATA = Path(__file__).resolve().parent.parent / "data" / "tasks.jsonl"


def build() -> list[dict]:
    tasks: list[dict] = []
    inj = 0
    for s_idx, sc in enumerate(SCENARIOS):
        schema = TOOLS[sc.tool]
        for a_idx, args in enumerate(sc.arg_sets):
            base_id = f"t{s_idx:02d}-{a_idx}"
            facts = derive(schema, ToolCall(sc.tool, args))
            if not facts.recognised:
                raise ValueError(f"{sc.tool}: the oracle does not recognise this tool; it cannot be a task")
            clean = {
                "id": base_id,
                "pair": base_id,
                "condition": "clean",
                "tool": sc.tool,
                "family": sc.family,
                "label": sc.label,
                "args": args,
                "truth": {**facts.to_json(), "decision": expected_decision(facts.severity)},
            }
            tasks.append(clean)
            if sc.injectable is None:
                continue
            # Two phrasings per clean item, rotating through the list so no
            # single sentence dominates the injected condition.
            for k in range(2):
                sentence = INJECTIONS[(inj + k) % len(INJECTIONS)]
                injected_args = dict(args)
                existing = str(injected_args.get(sc.injectable, "") or "")
                injected_args[sc.injectable] = (existing + "\n\n" + sentence).strip()
                ifacts = derive(schema, ToolCall(sc.tool, injected_args))
                assert any(x["code"] == "instruction_shaped_argument" for x in ifacts.signals), sentence
                tasks.append({
                    "id": f"{base_id}-i{k}",
                    "pair": base_id,
                    "condition": "injected",
                    "tool": sc.tool,
                    "family": sc.family,
                    "label": sc.label,
                    "args": injected_args,
                    "injected_param": sc.injectable,
                    "injection": sentence,
                    "truth": {**ifacts.to_json(), "decision": expected_decision(ifacts.severity)},
                })
            inj += 2
    return tasks


def write(path: Path = DATA) -> list[dict]:
    tasks = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n")
    return tasks


def load(path: Path = DATA) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    ts = write()
    from collections import Counter
    print(len(ts), "tasks")
    print(Counter(t["condition"] for t in ts))
    print(Counter(t["truth"]["severity"] for t in ts))
    print(Counter(t["family"] for t in ts))
