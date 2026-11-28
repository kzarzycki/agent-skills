#!/usr/bin/env python3
"""One-shot verifier support (#2996): the deterministic steps around one Codex review of one bundle.

    one_shot.py tier --head SHA [--base SHA | --against REF] --policy gatekeeper.md --low-risk GLOB...   # gates only, or a review, and why
    one_shot.py plan --head SHA --verdicts FILE           # first pass, a delta pass (its base), or refused
    one_shot.py bundle --head SHA --spec FILE --policy gatekeeper.md [--base SHA | --against REF]
                       [--rules FILE] [--nearby-from-git] [--max-diff-bytes N]
    one_shot.py verdict --json FILE --head SHA --family F --pass N --report FILE [--calls N --credits X]
                       # FILE is a report `approvals.py report` reads, or FILE.question (exit 3) when a check was not run

The model only judges. The gate result is the gatekeeper's own `gate-record` lookup of the pass record origin holds
for the head's tree, plus the raw output of the gate's own steps, run by this script on the head's clean checkout (a CI
log is never taken: a job that reused the record ran nothing; never a file a caller gives). One range, the delta's or the PR's, gives the paths, the diff and the heading. The build inputs come from the gatekeeper's parse of the policy. Changed paths are git's own
(`diff --name-status -z -M -C`: a rename or copy gives both sides). A cut, or an input not given, is named in the bundle. Standard library, and the gatekeeper skill.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _installed import installed

GATEKEEPER = installed("gatekeeper")
sys.path.insert(0, str(GATEKEEPER))
import gatekeeper

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


def build_inputs(policy: str) -> list[str]:
    """The policy's `select.build_inputs`, as the gatekeeper parses them (a quoted glob loses its quotes)."""
    try:
        return list(
            gatekeeper.settings(gatekeeper.Policy(policy)).get("select", {}).get("build_inputs", [])
        )
    except gatekeeper.Refused as exc:
        raise Refused(f"the policy does not parse: {exc}") from None


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


def trusted_gate(head: str) -> tuple[int, str]:
    """The gatekeeper's `gate-record <head>`: exit 0 and the record it names when origin holds a pass of the gate on the
    head's tree, else the reason. No caller's file counts."""
    run = subprocess.run(
        [sys.executable, str(GATEKEEPER / "gatekeeper.py"), "gate-record", head],
        capture_output=True,
        text=True,
        check=False,
    )
    return run.returncode, (run.stdout + run.stderr).strip()


def run_gate(head: str, plan=None) -> str:
    """The raw output of the gate's own steps run on `head`'s checkout now, by the gatekeeper's own step runner
    (`ran_step`: the step's environment, `gate_env`, and the host gate slot) and its own cleanliness rule
    (`checkout_state`, taken before and after every step, as `run_steps` does). The output is bound to the head and
    to the gate the base's policy defines (`gate_plan`). A CI job that reused a record ran nothing, so no log fetched
    from one counts. A step that fails or changes the checkout is refused; a step that may not run here is named."""
    at, changes = gatekeeper.checkout_state()
    if at.strip() != head:
        raise Refused(f"the checkout is not at {head}: the gate runs on the head's own tree")
    if changes.strip():
        raise Refused(
            "the checkout has uncommitted changes: the gate output would not be the head's"
        )
    out = []
    with tempfile.TemporaryFile("w+") as sink:
        for step in plan if plan is not None else gatekeeper.gate_plan():
            if not gatekeeper.here(step):
                out.append(f"$ {step['command']}\n[not run in this session: where {step['where']}]")
                continue
            sink.seek(0)
            sink.truncate()
            code = gatekeeper.ran_step(step, Path.cwd(), sink)[0]
            sink.seek(0)
            out.append(f"$ {step['command']}\n{sink.read()}[exit {code}]")
            if code:
                raise Refused(f"the gate step `{step['command']}` fails on {head} (exit {code})")
            now, moved = gatekeeper.checkout_state()
            if now.strip() != head or moved.strip():
                raise Refused(
                    f"the gate step `{step['command']}` changed the checkout: its output is not the head's"
                )
    return "\n".join(out)


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
    paths: list[str],
    gate: tuple[int, str, str],
    inputs: list[str],
    nearby: dict[str, str] | None = None,
    rules: str | None = None,
    max_diff_bytes: int = 200_000,
    base: str | None = None,
    max_part_bytes: int = 20_000,
) -> str:
    """`gate` is (trusted_gate's exit, its record text, run_gate's raw output); `paths` is changed_paths' list."""
    if gate[0] != 0:
        raise Refused(f"no gate record on {head} (gate-record exit {gate[0]}): {gate[1]}")
    shown, cuts = cut("diff", diff, max_diff_bytes)
    if not gate[2].strip():
        raise Refused("no raw gate output for the head: the bundle needs the gate's own log")
    log, c = cut("gate log", gate[2], max_part_bytes)
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
        "## Gate record (the gatekeeper's gate-record lookup)",
        gate[1].strip(),
        "",
        "## Gate output (raw, run by this script on the head)",
        log.strip(),
    ]
    out += ["", "## Rules", rules_text.strip() or "none", "", "## Nearby code", *(near or ["none"])]
    out += ["", "## Diff", shown.strip(), ""]
    return "\n".join(out)


def gate_evidence(head: str) -> tuple[int, str, str]:
    """The trusted record first (a missing one is refused before any gate run), then the raw gate output."""
    code, record = trusted_gate(head)
    if code != 0:
        raise Refused(f"no gate record on {head} (gate-record exit {code}): {record}")
    return code, record, run_gate(head)


def _filled(*values: object) -> bool:
    return all(isinstance(v, str) and v.strip() for v in values)


def _unrun(item: object) -> str:
    if not isinstance(item, dict) or not _filled(item.get("check"), item.get("command")):
        raise Refused(
            "each `acceptance_not_run` item is {check, command[, mutation: {patch, undo, redo}]}: "
            "the lead builds the proof run from the question alone"
        )
    text = f"- {item['check']}\n  command: {item['command']}"
    if "mutation" in item:
        m = item["mutation"]
        if not isinstance(m, dict) or not _filled(*(m.get(k) for k in ("patch", "undo", "redo"))):
            raise Refused("a mutation not run needs its `patch` and the `undo` and `redo` commands")
        text += f"\n  mutation patch: {m['patch']}\n  undo: {m['undo']}\n  redo: {m['redo']}"
    return text


def verdict(
    review: dict,
    head: str,
    family: str,
    number: int,
    calls: int | None = None,
    credits: float | None = None,
) -> tuple[str | None, str | None]:
    """Map the rubric's JSON to (report, question). A report is what `approvals.py report` reads (findings as `### Fn (severity) path:line: title`,
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
        # a P0 or P1 states what it breaks and, from pass 2, where it came from (the gatekeeper's report parser reads them)
        fields = [
            f"{key}: {f[name]}"
            for key, name in (("Breaks", "breaks"), ("Path", "path"), ("Origin", "origin"))
            if f.get(name)
        ]
        rules = f"\nRules: {', '.join(f['rules'])}" if f.get("rules") else ""
        loc = f.get("location", "unknown:0")
        body.append(
            f"### F{i} ({kind}) {loc}: {f['priority']} {f['title']}\n{f.get('body', '')}{rules}"
            + "".join(f"\n{line}" for line in fields)
        )
    if review.get("acceptance_not_run"):
        # an ordinary run not made goes to the lead's proof run as `<report>.question`, never as an owner action; the
        # lead builds the proof brief from it alone, so each check names its exact command, and a mutation its patch
        # with the commands that undo and redo it
        steps = "\n".join(_unrun(x) for x in review["acceptance_not_run"])
        found = "\n".join(f"- {f['priority']} {f['title']}" for f in review.get("findings", []))
        return None, (
            f"Verifier: {family}, pass {number} could not run these checks on {head}:\n{steps}\n"
            + (f"\nFindings so far:\n{found}\n" if found else "")
            + "\nRun them in the proof run and send the output back.\n"
        )
    not_run = review.get("owner_only_not_run", [])
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
    if body:
        lines += ["## Findings", "", *body]
    if not_run:
        # a step only the owner can take, which the gatekeeper reads as the outstanding-proof line
        lines.append(
            "Not run: "
            + "; ".join(not_run)
            + ", owner action: "
            + review.get("owner_action", "the owner takes it")
        )
    lines += [
        f"Head: {head}",
        f"VERDICT: {counts['blocker']} blocker, {counts['major']} major, {counts['minor']} minor",
        f"SATISFIED: {'yes' if satisfied else 'no'}",
        f"Risk: {review.get('risk', 'high — not rated by the review')}",
    ]
    return "\n".join(lines) + "\n", None


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def read(path: str) -> str:
    return Path(path).read_text()


def diff_range(head: str, base: str | None, against: str) -> list[str]:
    """The one range a pass reviews: `base head` for a delta since the last verdict, else `against...head`. The paths, the
    diff and the heading all come from it."""
    return [base, head] if base else [f"{against}...{head}"]


def changed_paths(head: str, base: str | None = None, against: str = "origin/main") -> list[str]:
    """Every path the range changes, a rename's or copy's source as well as its destination (both sides are checked
    against the gate inputs), as git names them (NUL-separated, so a space or quote is no break)."""
    out = _git(
        "diff",
        "--name-status",
        "-z",
        "-M",
        "-C",
        "--find-copies-harder",
        *diff_range(head, base, against),
    ).split("\0")
    paths, i = [], 0
    while i < len(out) and out[i]:
        take = 2 if out[i][0] in "RC" else 1
        paths += out[i + 1 : i + 1 + take]
        i += 1 + take
    return paths


def range_diff(head: str, base: str | None, against: str) -> str:
    return _git("diff", "-M", "-C", "--find-copies-harder", *diff_range(head, base, against))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tier")
    t.add_argument("--head", required=True)
    t.add_argument("--base")
    t.add_argument("--against", default="origin/main")
    t.add_argument("--policy", required=True)
    t.add_argument("--low-risk", nargs="*", default=[])
    pl = sub.add_parser("plan")
    pl.add_argument("--head", required=True)
    pl.add_argument("--verdicts", required=True)
    b = sub.add_parser("bundle")
    for name in ("head", "spec", "policy"):
        b.add_argument(f"--{name}", required=True)
    b.add_argument("--against", default="origin/main")
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
    v.add_argument("--report", required=True)
    a = p.parse_args(argv)
    try:
        if a.cmd == "tier":
            print(
                json.dumps(
                    tier(
                        changed_paths(a.head, a.base, a.against),
                        a.low_risk,
                        build_inputs(read(a.policy)),
                    )
                )
            )
        elif a.cmd == "plan":
            print(json.dumps(plan(a.head, json.loads(read(a.verdicts)))))
        elif a.cmd == "bundle":
            diff = range_diff(a.head, a.base, a.against)
            paths = changed_paths(a.head, a.base, a.against)
            nearby = None
            if a.nearby_from_git:
                nearby = {}
                for path in paths:
                    try:
                        nearby[path] = _git("show", f"{a.head}:{path}")
                    except subprocess.CalledProcessError:
                        continue  # a deleted file has no head copy
            print(
                bundle(
                    a.head,
                    read(a.spec),
                    diff,
                    paths,
                    gate_evidence(a.head),
                    build_inputs(read(a.policy)),
                    nearby,
                    read(a.rules) if a.rules else None,
                    a.max_diff_bytes,
                    a.base,
                )
            )
        else:
            report, question = verdict(
                json.loads(read(a.json)), a.head, a.family, a.number, a.calls, a.credits
            )
            if report is None:
                Path(f"{a.report}.question").write_text(question or "")
                print(f"{a.report}.question")
                return 3
            Path(a.report).write_text(report)
            print(a.report)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
