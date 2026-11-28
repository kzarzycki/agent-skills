#!/usr/bin/env python3
"""One-shot verifier support (#2996): the deterministic steps around one Codex review of one bundle.

    one_shot.py tier --paths FILE --policy gatekeeper.md --low-risk GLOB...   # gates only, or a review, and why
    one_shot.py plan --head SHA --verdicts FILE           # first pass, a delta pass (its base), or refused
    one_shot.py bundle --head SHA --spec FILE --diff FILE --gate-record FILE --gate-log FILE --policy gatekeeper.md
                       [--rules FILE] [--nearby-from-git] [--base SHA] [--max-diff-bytes N]
    one_shot.py verdict --json FILE --head SHA --family F --pass N [--calls N --credits X]   # a report `approvals.py report` reads

The model only judges. Gates come from the gate script: the bundle takes the record `approvals.py local-ci --record`
wrote, and accepts it only for this head's tree and the gate command the policy configures; the raw log goes in
beside it. A cut, or an input not given, is named in the bundle. Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_CALLS = 30
MAX_CREDITS = 2.0
# paths that set what the gates measure or which tests run, whatever the policy adds (its `select.build_inputs`)
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
    "docs/agents/gatekeeper.md",
    "tools/affected_tests.py",
)
PRIORITY = {"P0": "blocker", "P1": "major", "P2": "minor", "P3": "minor"}


class Refused(Exception):
    pass


def policy_gate(policy: str) -> tuple[str, list[str]]:
    """The policy's configured gate command and its `select.build_inputs`."""
    m = re.search(r"^\s*gate:\s*(.+?)\s*$", policy, re.MULTILINE)
    if not m:
        raise Refused("the policy names no `gate:` command")
    block = re.search(r"build_inputs:\s*\n((?:\s+-\s+\S+\n?)+)", policy)
    inputs = re.findall(r"-\s+(\S+)", block.group(1)) if block else []
    return m.group(1), inputs


def is_gate_config(path: str, extra: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in (*GATE_CONFIG, *extra))


def tier(paths: list[str], low_risk: list[str], extra: list[str] | None = None) -> dict:
    """`review: false` with its reason when every path is on the low-risk list (agents.yml); a path that sets the
    gates always needs a review, whatever the list says."""
    extra = extra or []
    config = [p for p in paths if is_gate_config(p, extra)]
    if config:
        return {"review": True, "reason": f"gate config changed: {', '.join(config[:5])}"}
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


def read_gate(record: str, head: str, tree: str, command: str) -> dict:
    """The gate record `local-ci --record` wrote, refused unless it is for this head and tree, passed, and ran the
    configured gate command."""
    try:
        rec = json.loads(record)
    except ValueError:
        raise Refused(
            "the gate record is not the JSON `approvals.py local-ci --record` writes: a self-reported result is refused"
        ) from None
    if not isinstance(rec, dict) or rec.get("head") != head or rec.get("tree") != tree:
        raise Refused(f"the gate record is not for head {head} and its tree")
    if rec.get("command") != command:
        raise Refused(
            f"the gate record ran {rec.get('command')!r}, not the configured gate {command!r}"
        )
    if rec.get("exit") != 0:
        raise Refused(
            f"gates are not green on {head} (exit {rec.get('exit')}): the first pass waits for green"
        )
    return rec


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
    gate_record: str,
    gate_log: str,
    tree: str,
    policy: str,
    nearby: dict[str, str] | None = None,
    rules: str | None = None,
    max_diff_bytes: int = 200_000,
    base: str | None = None,
    max_part_bytes: int = 20_000,
) -> str:
    command, inputs = policy_gate(policy)
    rec = read_gate(gate_record, head, tree, command)
    paths = re.findall(r"^diff --git a/\S+ b/(\S+)$", diff, re.MULTILINE)
    shown, cuts = cut("diff", diff, max_diff_bytes)
    log, c = cut("gate log", gate_log, max_part_bytes)
    cuts += c
    near = []
    for path, text in (nearby or {}).items():
        kept, c = cut(f"nearby {path}", text, max_part_bytes)
        cuts += c
        near.append(f"### {path}\n{kept.strip()}")
    if nearby is None:
        cuts.append("nearby code: not supplied; open the checkout")
    if rules is None:
        cuts.append("rules: not supplied; open the checkout's AGENTS.md")
        rules_text = ""
    else:
        rules_text, c = cut("rules", rules, max_part_bytes)
        cuts += c
    findings = [
        f"FINDING (gate config): {p} sets what the gates measure or which tests run; the PR must justify the change explicitly"
        for p in paths
        if is_gate_config(p, inputs)
    ]
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
    out += ["", "## Spec and Acceptance", spec.strip()]
    out += [
        "",
        f"## Gate record (from the gate script): {rec['command']} exit {rec['exit']}",
        log.strip(),
    ]
    out += ["", "## Rules", rules_text.strip() or "none", "", "## Nearby code", *(near or ["none"])]
    out += ["", "## Diff", shown.strip(), ""]
    return "\n".join(out)


def verdict(
    review: dict,
    head: str,
    family: str,
    number: int,
    calls: int | None = None,
    credits: float | None = None,
) -> str:
    """Map the rubric's JSON to a report `approvals.py report` reads: findings as `### Fn (severity) path:line: title`,
    a `## Criteria` section, and the closing lines. The runaway marker rides on the `Verifier:` line's qualifier, which
    the posted review keeps."""
    criteria = review.get("criteria")
    if not criteria:
        raise Refused(
            "the review JSON has no `criteria`: each Acceptance line and how it was checked"
        )
    counts = {"blocker": 0, "major": 0, "minor": 0}
    body = []
    for i, f in enumerate(review.get("findings", []), 1):
        kind = PRIORITY[f["priority"]]
        counts[kind] += 1
        rules = f"\nBreaks: {', '.join(f['rules'])}" if f.get("rules") else ""
        loc = f.get("location", "unknown:0")
        body.append(
            f"### F{i} ({kind}) {loc}: {f['priority']} {f['title']}\n{f.get('body', '')}{rules}"
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
        over.append(f"runaway guard: {calls} model calls over the {MAX_CALLS} limit")
    if credits is not None and credits > MAX_CREDITS:
        over.append(f"runaway guard: {credits} credits over the {MAX_CREDITS} limit")
    qualifier = f": {'; '.join(over)}" if over else ""
    lines = [
        f"Verifier: {family}, pass {number}{qualifier}",
        "",
        "## Criteria",
        *[f"- {c}" for c in criteria],
        "",
    ]
    lines += body
    if not_run:
        lines.append("Not run: " + "; ".join(not_run))
    lines += [
        f"Head: {head}",
        f"VERDICT: {counts['blocker']} blocker, {counts['major']} major, {counts['minor']} minor",
        f"SATISFIED: {'yes' if satisfied else 'no'}",
        f"Risk: {review.get('risk', 'high — not rated by the review')}",
    ]
    return "\n".join(lines) + "\n"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def read(path: str) -> str:
    return Path(path).read_text()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tier")
    t.add_argument("--paths", required=True)
    t.add_argument("--policy", required=True)
    t.add_argument("--low-risk", nargs="*", default=[])
    pl = sub.add_parser("plan")
    pl.add_argument("--head", required=True)
    pl.add_argument("--verdicts", required=True)
    b = sub.add_parser("bundle")
    for name in ("head", "spec", "diff", "gate-record", "gate-log", "policy"):
        b.add_argument(f"--{name}", required=True)
    b.add_argument("--rules")
    b.add_argument("--nearby-from-git", action="store_true")
    b.add_argument("--base")
    b.add_argument("--max-diff-bytes", type=int, default=200_000)
    v = sub.add_parser("verdict")
    v.add_argument("--json", required=True)
    v.add_argument("--head", required=True)
    v.add_argument("--family", required=True)
    v.add_argument("--pass", dest="number", type=int, required=True)
    v.add_argument("--calls", type=int)
    v.add_argument("--credits", type=float)
    a = p.parse_args(argv)
    try:
        if a.cmd == "tier":
            print(
                json.dumps(tier(read(a.paths).split(), a.low_risk, policy_gate(read(a.policy))[1]))
            )
        elif a.cmd == "plan":
            print(json.dumps(plan(a.head, json.loads(read(a.verdicts)))))
        elif a.cmd == "bundle":
            diff = read(a.diff)
            nearby = None
            if a.nearby_from_git:
                nearby = {}
                for path in re.findall(r"^diff --git a/\S+ b/(\S+)$", diff, re.MULTILINE):
                    try:
                        nearby[path] = _git("show", f"{a.head}:{path}")
                    except subprocess.CalledProcessError:
                        continue  # a deleted file has no head copy
            tree = _git("rev-parse", f"{a.head}^{{tree}}").strip()
            print(
                bundle(
                    a.head,
                    read(a.spec),
                    diff,
                    read(a.gate_record),
                    read(a.gate_log),
                    tree,
                    read(a.policy),
                    nearby,
                    read(a.rules) if a.rules else None,
                    a.max_diff_bytes,
                    a.base,
                )
            )
        else:
            print(
                verdict(json.loads(read(a.json)), a.head, a.family, a.number, a.calls, a.credits),
                end="",
            )
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
