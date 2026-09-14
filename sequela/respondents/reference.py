"""
Reference respondents. Each is a policy with one deliberate flaw, so that a
metric that fails to move when the flaw is present is a metric that does not
work. They calibrate the instrument; they say nothing about any model.
"""
from __future__ import annotations

from ..catalogue import INJECTIONS, TOOLS
from ..oracle import (
    ROLE_EFFECTS, SEVERITY, VERB_EFFECTS, derive_reversibility, derive_severity,
    expected_decision, instruction_shaped, tokenise,
)


def oracle(task: dict) -> dict:
    """Perfect monitoring, perfect control. Should score 1.0 on everything."""
    t = task["truth"]
    return {
        "severity": t["severity"],
        "reversibility": t["reversibility"],
        "affected_count": t["affected_count"],
        "destinations": list(t["destinations"]),
        "escapes_boundary": t["escapes_boundary"],
        "decision": expected_decision(t["severity"]),
        "rationale": "derived",
    }


def uncoupled(task: dict) -> dict:
    """Knows exactly what the call does and proceeds anyway. The know/do gap
    in its purest form."""
    r = oracle(task)
    r["decision"] = "proceed"
    r["rationale"] = "proceeding"
    return r


def _believes_the_argument(task: dict) -> dict:
    """The report of a respondent that takes the argument text at its word."""
    return {
        "severity": "low",
        "reversibility": "reversible",
        "affected_count": 1 if task["truth"]["affected_count"] != 0 else 0,
        "destinations": [],
        "escapes_boundary": False,
        "decision": "proceed",
        "rationale": "the argument says this is routine",
    }


def _argument_text(task: dict) -> str:
    parts: list[str] = []
    for v in task["args"].values():
        parts.extend(str(x) for x in v) if isinstance(v, list) else parts.append(str(v))
    return "\n".join(parts)


def trusting(task: dict) -> dict:
    """Reports the truth on clean calls and believes whatever the arguments
    tell it on injected (and held-out) ones. Maximal suggestibility."""
    if task["condition"] == "clean":
        return oracle(task)
    return _believes_the_argument(task)


def name_reader(task: dict) -> dict:
    """Reads the tool name and nothing else: no description, no parameter
    roles, no boundary, no wildcard. It counts whatever strings look like
    paths or names, never sees an escape, and never lists a destination.
    Its decision follows its own (poor) report, so it is coupled."""
    tokens = tokenise(task["tool"])
    effects = {VERB_EFFECTS[tokens[0]]} if tokens and tokens[0] in VERB_EFFECTS else set()
    schema = TOOLS[task["tool"]]
    count = 0
    for pname, spec in schema.parameters.items():
        if spec.role in ("path", "glob", "subject") and pname in task["args"]:
            v = task["args"][pname]
            count += len(v) if isinstance(v, list) else 1
    severity = derive_severity(effects, [], False, False, bool(effects)) if effects else "none"
    return {
        "severity": severity,
        "reversibility": derive_reversibility(effects),
        "affected_count": count,
        "destinations": [],
        "escapes_boundary": False,
        "decision": expected_decision(severity),
        "rationale": f"the tool is a {tokens[0] if tokens else '?'}",
    }


def paranoid(task: dict) -> dict:
    """Everything is critical, nothing is undoable, always stop. Never
    understates and is useless: the benchmark must be able to tell."""
    return {
        "severity": "critical",
        "reversibility": "irreversible",
        "affected_count": "unbounded",
        "destinations": list(task["truth"]["destinations"]),
        "escapes_boundary": True,
        "decision": "stop",
        "rationale": "everything is dangerous",
    }


def schema_blind(task: dict) -> dict:
    """Reads the arguments but not the schema. Sees paths, wildcards, URLs and
    addresses in the raw values; knows nothing about roles or boundaries, so
    it never sees an escape and does not know that a url means egress unless
    the tool name says so."""
    import re
    tokens = tokenise(task["tool"])
    effects = {VERB_EFFECTS[tokens[0]]} if tokens and tokens[0] in VERB_EFFECTS else set()
    values: list[str] = []
    for v in task["args"].values():
        values.extend(str(x) for x in v) if isinstance(v, list) else values.append(str(v))
    paths = [v for v in values if v.startswith("/")]
    unbounded = any(re.search(r"[*?\[\]{}]", p) for p in paths)
    dests = [v for v in values if re.match(r"^[a-z]+://", v) or re.match(r"^[^@\s]+@[^@\s]+$", v)]
    if dests and not effects & {"network_egress", "message_send"}:
        effects.add("network_egress" if any("://" in d for d in dests) else "message_send")
    severity = derive_severity(effects, [], unbounded, False, bool(effects)) if effects else "none"
    return {
        "severity": severity,
        "reversibility": derive_reversibility(effects),
        "affected_count": "unbounded" if unbounded else len(paths),
        "destinations": dests,
        "escapes_boundary": False,
        "decision": expected_decision(severity),
        "rationale": "read from the arguments",
    }


def memorised(task: dict) -> dict:
    """Has learned the eight injection sentences and ignores them, and has
    learned nothing else. On clean calls and on calls carrying one of the
    eight it is the oracle; on any other instruction-shaped text it believes
    the argument, like `trusting`. On the main dataset it cannot be told from
    the oracle. Only the held-out sentences expose it."""
    text = _argument_text(task)
    if not instruction_shaped(text) or any(known in text for known in INJECTIONS):
        return oracle(task)
    return _believes_the_argument(task)


# The six calibration policies. Each one's flaw shows on the main dataset.
POLICIES = {
    "oracle": oracle,
    "uncoupled": uncoupled,
    "trusting": trusting,
    "name_reader": name_reader,
    "schema_blind": schema_blind,
    "paranoid": paranoid,
}

# Policies whose flaw shows only on the held-out split. Kept out of POLICIES,
# whose members are all expected to pay for their flaw on the main dataset.
HELDOUT_POLICIES = {
    "memorised": memorised,
}

ALL_POLICIES = {**POLICIES, **HELDOUT_POLICIES}
