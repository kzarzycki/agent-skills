#!/usr/bin/env python3
"""One-shot verifier support (#2996): the deterministic steps around one Codex review of one bundle.

    one_shot.py tier --paths FILE --low-risk GLOB...      # gates only, or a model review, and why
    one_shot.py plan --head SHA --verdicts FILE           # first pass, a delta pass (its base), or refused
    one_shot.py bundle --head SHA --spec FILE --diff FILE --gate FILE [--max-diff-bytes N] [--base SHA]
    one_shot.py verdict --json FILE --head SHA [--calls N --credits X]   # the review's JSON as a report

The model only judges. Gates come from the gate script: a gate file is taken only with its first line
`GATE head=<sha> exit=<n> cmd=<command>` for this head, written by that script, never a lead's summary.
A cut in the bundle names what was cut. Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

MAX_CALLS = 30
MAX_CREDITS = 2.0
# a path that sets what the gates measure: a change to one always gets a finding
GATE_CONFIG = (
    "mise.toml",
    "pyproject.toml",
    "conftest.py",
    "*/conftest.py",
    ".github/workflows/*",
    "tox.ini",
    "setup.cfg",
    ".coveragerc",
    "ruff.toml",
    ".mergify.yml",
    "*/gatekeeper.md",
)
PRIORITY = {"P0": "blocker", "P1": "major", "P2": "minor", "P3": "minor"}


class Refused(Exception):
    pass


def tier(paths: list[str], low_risk: list[str]) -> dict:
    """`review: false` with its reason when every path is on the low-risk list (from agents.yml), else a review."""
    outside = [p for p in paths if not any(fnmatch.fnmatch(p, g) for g in low_risk)]
    if paths and not outside:
        return {
            "review": False,
            "reason": f"gates only: all {len(paths)} paths match the low-risk list, so no model review was needed",
        }
    return {
        "review": True,
        "reason": f"{len(outside)} path(s) outside the low-risk list: {', '.join(outside[:5])}",
    }


def plan(head: str, verdicts: list[dict]) -> dict:
    """`verdicts` are earlier passes, oldest first, each `{"head": sha}`. A head already reviewed is refused."""
    if any(v["head"] == head for v in verdicts):
        raise Refused(f"head {head} already has a verdict: one pass per head")
    if not verdicts:
        return {"pass": 1, "base": None, "scope": "full"}
    return {
        "pass": len(verdicts) + 1,
        "base": verdicts[-1]["head"],
        "scope": "delta since the last verdict",
    }


def gate_config_findings(paths: list[str]) -> list[str]:
    hit = [p for p in paths if any(fnmatch.fnmatch(p, g) for g in GATE_CONFIG)]
    return [
        f"FINDING (gate config): {p} sets what the gates measure; the PR must justify the change explicitly"
        for p in hit
    ]


def read_gate(text: str, head: str) -> str:
    """The raw gate output, refused unless the gate script wrote its header for this head."""
    first = text.partition("\n")[0]
    m = re.fullmatch(r"GATE head=(\S+) exit=(\d+) cmd=(.+)", first.strip())
    if not m:
        raise Refused(
            "gate output has no `GATE head=<sha> exit=<n> cmd=<command>` first line: a self-reported result is refused"
        )
    if m.group(1) != head:
        raise Refused(f"gate output is for head {m.group(1)}, not {head}")
    if m.group(2) != "0":
        raise Refused(
            f"gates are not green on {head} (exit {m.group(2)}): the first pass waits for green"
        )
    return text


def cut(name: str, text: str, limit: int) -> tuple[str, list[str]]:
    data = text.encode()
    if len(data) <= limit:
        return text, []
    kept = data[:limit].decode(errors="ignore")
    return kept, [f"{name}: cut at {limit} of {len(data)} bytes; open the checkout for the rest"]


def bundle(
    head: str,
    spec: str,
    diff: str,
    gate: str,
    max_diff_bytes: int = 200_000,
    base: str | None = None,
) -> str:
    gate_text = read_gate(gate, head)
    paths = re.findall(r"^diff --git a/\S+ b/(\S+)$", diff, re.MULTILINE)
    shown, cuts = cut("diff", diff, max_diff_bytes)
    findings = gate_config_findings(paths)
    out = [
        f"# Review bundle for head {head}",
        f"Scope: {'delta since ' + base if base else 'full change'}",
    ]
    out += [
        "",
        "## Cuts",
        *(cuts or ["none"]),
        "",
        "## Findings already known",
        *(findings or ["none"]),
    ]
    out += [
        "",
        "## Spec and Acceptance",
        spec.strip(),
        "",
        "## Gate output (raw, from the gate script)",
        gate_text.strip(),
    ]
    out += ["", "## Diff", shown.strip(), ""]
    return "\n".join(out)


def verdict(review: dict, head: str, calls: int | None = None, credits: float | None = None) -> str:
    """Map the rubric's JSON (findings with P0-P3, overall verdict, acceptance lines not run) to the report lines."""
    counts = {"blocker": 0, "major": 0, "minor": 0}
    body = []
    for f in review.get("findings", []):
        kind = PRIORITY[f["priority"]]
        counts[kind] += 1
        rules = f" (breaks: {', '.join(f['rules'])})" if f.get("rules") else ""
        body.append(
            f"### {f['priority']} {f['title']}{rules}\n{f.get('location', '')}\n{f.get('body', '')}"
        )
    not_run = review.get("acceptance_not_run", [])
    satisfied = (
        review.get("overall_correctness") == "patch is correct"
        and not counts["blocker"]
        and not counts["major"]
        and not not_run
    )
    over = []
    if calls is not None and calls > MAX_CALLS:
        over.append(f"{calls} model calls over the {MAX_CALLS} limit")
    if credits is not None and credits > MAX_CREDITS:
        over.append(f"{credits} credits over the {MAX_CREDITS} limit")
    lines = [f"Head: {head}", *body]
    if not_run:
        lines.append("Not run: " + "; ".join(not_run))
    if over:
        lines.append("Runaway guard: " + "; ".join(over) + " (marked, not stopped)")
    lines += [
        f"VERDICT: {counts['blocker']} blocker, {counts['major']} major, {counts['minor']} minor",
        f"SATISFIED: {'yes' if satisfied else 'no'}",
        f"Risk: {review.get('risk', 'high — not rated by the review')}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tier")
    t.add_argument("--paths", required=True)
    t.add_argument("--low-risk", nargs="*", default=[])
    pl = sub.add_parser("plan")
    pl.add_argument("--head", required=True)
    pl.add_argument("--verdicts", required=True)
    b = sub.add_parser("bundle")
    b.add_argument("--head", required=True)
    b.add_argument("--spec", required=True)
    b.add_argument("--diff", required=True)
    b.add_argument("--gate", required=True)
    b.add_argument("--base")
    b.add_argument("--max-diff-bytes", type=int, default=200_000)
    v = sub.add_parser("verdict")
    v.add_argument("--json", required=True)
    v.add_argument("--head", required=True)
    v.add_argument("--calls", type=int)
    v.add_argument("--credits", type=float)
    a = p.parse_args(argv)
    try:
        if a.cmd == "tier":
            print(json.dumps(tier(Path(a.paths).read_text().split(), a.low_risk)))
        elif a.cmd == "plan":
            print(json.dumps(plan(a.head, json.loads(Path(a.verdicts).read_text()))))
        elif a.cmd == "bundle":
            print(
                bundle(
                    a.head,
                    Path(a.spec).read_text(),
                    Path(a.diff).read_text(),
                    Path(a.gate).read_text(),
                    a.max_diff_bytes,
                    a.base,
                )
            )
        else:
            print(verdict(json.loads(Path(a.json).read_text()), a.head, a.calls, a.credits), end="")
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
