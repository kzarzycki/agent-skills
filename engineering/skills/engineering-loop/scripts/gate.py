#!/usr/bin/env python3
"""Proof gate (engineering-loop): every step leaves proof on GitHub, and this checks it before the loop moves on.

    python3 scripts/gate.py check <build|merge> [pr]      # one line per missing proof, exit 1; no PR yet: exit 0
    python3 scripts/gate.py approve <spec|plan|merge> <issue or pr> --by <coordinator|owner> [--triage <link>]
    python3 scripts/gate.py verdict <pr> <report>          # post the verifier's verdict lines on the PR

Run from the repo root. The project's `mise run gate <point> [pr]` task runs `check`, then its own checks; the loop,
a pre-push hook and CI call that task.

`check build` needs every issue the PR closes to be `ready-for-agent`, not `needs-owner`, with exactly one category,
a component and exactly one size (a `wayfinder:` ticket needs only its state), and its approvals: `spec` always,
`plan` when one is due (a `## Plan` comment, or a `Plan:` line in loop.md § Practice).
`check merge` adds the PR's: the `## Evidence` section of its body, a posted verifier verdict, every CI check on the
head green (skipped inside GitHub Actions, where each other check is its own status and the gate job one of them),
and a `merge` approval on the head commit, with its verdict.

An approval is a comment `approve` writes, which the gate reads, plus the `approved:<point>` label for the board:

    Approved: spec
    By: coordinator
    Spec: <12 hex of sha256 of the spec>          (plan: Plan:, merge: Head: <sha> and Verdict:)

The coordinator approves every point. A rule in loop.md § Approvals, one `- <point>: <condition>` line each, adds a
person's approval (`By: owner`). Its label goes on last: the coordinator's approval removes the label and adds
`needs-owner`, so a person approves by adding the label, or by saying so in the session; then `approve --by owner`
writes their record, adds the label and removes `needs-owner`. A person who already approved the current spec, plan
or head keeps their label when the coordinator approves again on resuming. A condition the gate can read is `always`, `size:L`
(`size:L or larger`, `size:L+`), `component <name>`, `category <name>` or `path <glob>` in backticks, joined by `or`;
any other words make the rule the loop's alone, and so does a path on spec or plan, which come before the change. The spec is the issue body, or its last `## Spec` comment where a
tool owns the body. A soft gate against a forgotten step, not a security boundary: the agent holds the same
credentials as the person. Components and extra categories are the first backticked name of each list item under
`## Components` and `## Extra categories` in docs/agents/issue-tracker.md. Reads and writes through `gh`. Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

READY, NEEDS_OWNER = "ready-for-agent", "needs-owner"
CATEGORIES = {"bug", "enhancement", "documentation", "chore"}
SIZE_ORDER = ["size:XS", "size:S", "size:M", "size:L", "size:XL"]
SIZES = set(SIZE_ORDER)
TRACKER, LOOP = Path("docs/agents/issue-tracker.md"), Path("docs/agents/loop.md")
POINTS = ("spec", "plan", "merge")
VERDICT = "Verifier verdict"
ISSUE = "number body labels(first: 50) { nodes { name } } comments(last: 100) { totalCount nodes { body } }"
PULL = f"""number body headRefOid labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ body }} }}
  files(first: 100) {{ totalCount nodes {{ path }} }}
  commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ contexts(first: 100) {{ totalCount nodes {{
    __typename ... on CheckRun {{ name status conclusion }} ... on StatusContext {{ context state }} }} }} }} }} }} }}
  closingIssuesReferences(first: 50) {{ nodes {{ {ISSUE} }} }}"""
# GitHub's closing keywords; ponytail: same-repo `#n` only, add owner/repo#n and issue URLs when a PR here uses one.
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?[ \t]+#(\d+)\b", re.IGNORECASE)
# code and comments: an example, not a closing line
QUOTED = re.compile(r"^[ \t>]*```.*?^[ \t>]*```|`[^`\n]*`|<!--.*?-->", re.DOTALL | re.MULTILINE)
CONDITION = re.compile(
    r"\balways\b|\b(size:(?:XS|S|M|L|XL))(\+|[ \t]+or[ \t]+larger\b)?"
    r"|\b(component|category):?[ \t]*`?([\w./:-]+)`?|\bpath:?[ \t]*`([^`]+)`",
    re.IGNORECASE,
)
GREEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def named(body: str) -> list[int]:
    """The issue numbers a PR body names after a closing keyword on the same line, in order, each once."""
    return list(dict.fromkeys(int(number) for number in CLOSING.findall(QUOTED.sub("", body))))


def section(text: str, heading: str) -> str:
    """The text under `## <heading>`, up to the next `## ` heading; empty when there is none."""
    found = re.search(
        rf"^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE
    )
    return found.group(1) if found else ""


def listed(tracker: str, heading: str) -> set[str]:
    """The first backticked name of each list item under `## <heading>`."""
    return set(
        re.findall(r"^[ \t]*[-*] [^`\n]*`([^`\n]+)`", section(tracker, heading), re.MULTILINE)
    )


def rules(loop: str) -> list[tuple[str, str]]:
    """loop.md § Approvals as (point, condition) pairs."""
    return re.findall(
        r"^[ \t]*[-*] +(spec|plan|merge):[ \t]*(.+?)[ \t]*$",
        section(loop, "Approvals"),
        re.MULTILINE,
    )


def practice_plans(loop: str) -> bool:
    """Whether loop.md § Practice names a plan skill."""
    return (
        re.search(r"^[ \t]*(?:[-*] +)?`?Plan`?:[ \t]*\S", section(loop, "Practice"), re.MULTILINE)
        is not None
    )


def matches(condition: str, labels: set[str], paths: list[str] | None) -> bool | None:
    """Whether a rule's condition holds; None when it has words the gate can't read, or a path and no paths yet
    (the loop judges it)."""
    if re.sub(r"[,;]|\bor\b|\s", "", CONDITION.sub("", condition), flags=re.IGNORECASE):
        return None
    unread = False
    for found in CONDITION.finditer(condition):
        size, larger, kind, name, glob = found.groups()
        if size:
            index = SIZE_ORDER.index("size:" + size[5:].upper())
            hit = bool(
                labels & set(SIZE_ORDER[index:] if larger else SIZE_ORDER[index : index + 1])
            )
        elif kind:
            hit = name in labels
        elif glob:
            unread |= paths is None
            hit = any(fnmatch.fnmatch(path, glob) for path in paths or [])
        else:
            hit = True  # always
        if hit:
            return True
    return None if unread else False


def owner_needed(
    point: str, loop_rules: list[tuple[str, str]], labels: set[str], paths: list[str] | None
) -> bool:
    return any(matches(condition, labels, paths) for rule, condition in loop_rules if rule == point)


def merge_paths(pull: dict[str, Any], loop_rules: list[tuple[str, str]]) -> list[str]:
    """The PR's paths, read only when a merge rule has a path condition to judge."""
    if not any(
        found.group(5)
        for point, condition in loop_rules
        if point == "merge"
        for found in CONDITION.finditer(condition)
    ):
        return []
    files = pull["files"]
    # ponytail: one page of files; page them when a PR with a path rule outgrows it.
    if (files.get("totalCount") or 0) > len(files["nodes"]):
        raise Refused(
            f"PR #{pull['number']} has more than {len(files['nodes'])} changed files: "
            "the gate reads one page to judge a path rule, so split the PR"
        )
    return [file["path"] for file in files["nodes"]]


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").strip().encode()).hexdigest()[:12]


def names(node: dict[str, Any]) -> set[str]:
    return {label["name"] for label in node["labels"]["nodes"]}


def bodies(node: dict[str, Any]) -> list[str]:
    """Its comments; refused past one page, where an approval or a spec could be among those not read."""
    comments = node["comments"]
    # ponytail: one page of 100; page with `before:` cursors when a spec or PR outgrows it.
    if (comments.get("totalCount") or 0) > len(comments["nodes"]):
        where = f"#{node['number']}"
        raise Refused(
            f"{where} has more than {len(comments['nodes'])} comments: the gate reads one page"
        )
    return [comment["body"] for comment in comments["nodes"]]


def headed(node: dict[str, Any], heading: str) -> str | None:
    """The last comment that starts with `heading`."""
    found = [body for body in bodies(node) if body.lstrip().startswith(heading)]
    return found[-1] if found else None


def spec_of(issue: dict[str, Any]) -> str:
    return headed(issue, "## Spec") or issue["body"]


def records(node: dict[str, Any], point: str) -> list[dict[str, str]]:
    """The approval records for `point` among a node's comments, each as its lower-cased `Key: value` lines."""
    found = []
    for body in bodies(node):
        lines = body.strip().splitlines()
        if lines and lines[0].strip() == f"Approved: {point}":
            found.append(
                {
                    key.strip().lower(): value.strip()
                    for key, _, value in (line.partition(":") for line in lines[1:])
                }
            )
    return found


def current(node: dict[str, Any], point: str, key: str, value: str, by: str) -> bool:
    """Whether `by` approved `point` for this spec, plan or head; a merge record also carries its verdict."""
    return any(
        record.get("by") == by
        and record.get(key) == value
        and (point != "merge" or bool(record.get("verdict")))
        for record in records(node, point)
    )


def approvals(
    where: str, node: dict[str, Any], point: str, key: str, value: str, owner: bool
) -> list[str]:
    """One line per approval `point` lacks on `node`: the coordinator's, the owner's when a rule asks, the label."""
    found = []
    held = records(node, point)
    for by in ("coordinator", "owner") if owner else ("coordinator",):
        if not current(node, point, key, value, by):
            stale = any(record.get("by") == by for record in held)
            found.append(
                f"{where} has no `Approved: {point}` record by the {by}"
                + (f" for its current {key}: approve again" if stale else "")
            )
    if f"approved:{point}" not in names(node):
        found.append(f"{where} lacks the `approved:{point}` label")
    return found


def problems(
    issues: list[dict[str, Any]], components: set[str], categories: set[str] = CATEGORIES
) -> list[str]:
    """One line per reason an issue the PR closes skipped the spec state or a label; empty when none did."""
    if not issues:
        return [
            "the PR closes no issue: it needs a `Closes #<spec>` line for a ready-for-agent spec"
        ]
    found = []
    for issue in issues:
        labels = names(issue)
        if READY not in labels:
            found.append(f"#{issue['number']} is not {READY}: triage and spec it first")
        if NEEDS_OWNER in labels:
            found.append(f"#{issue['number']} waits for the owner ({NEEDS_OWNER})")
        if any(label.startswith("wayfinder:") for label in labels):
            continue  # a wayfinder ticket settles a decision: its wayfinder: label is its category, and it has no component or size
        for kind, allowed in (("category", categories), ("size", SIZES)):
            if len(labels & allowed) != 1:
                found.append(
                    f"#{issue['number']} needs exactly one {kind} label ({', '.join(sorted(allowed))}), has {len(labels & allowed)}"
                )
        if not labels & components:
            found.append(
                f"#{issue['number']} needs a component label ({', '.join(sorted(components)) or f'{TRACKER} lists none'})"
            )
    return found


def proofs(point: str, pull: dict[str, Any], issues: list[dict[str, Any]], loop: str) -> list[str]:
    """One line per approval or proof the PR and its issues lack at `point` (build or merge)."""
    loop_rules, found = rules(loop), []
    for issue in issues:
        labels = names(issue)
        if any(label.startswith("wayfinder:") for label in labels):
            continue
        where = f"#{issue['number']}"
        found += approvals(
            where,
            issue,
            "spec",
            "spec",
            fingerprint(spec_of(issue)),
            owner_needed("spec", loop_rules, labels, None),
        )
        plan = headed(issue, "## Plan")
        if plan is not None:
            plan_owner = owner_needed("plan", loop_rules, labels, None)
            found += approvals(where, issue, "plan", "plan", fingerprint(plan), plan_owner)
        elif practice_plans(loop):
            found.append(f"{where} has no `## Plan` comment, and one is due")
    if point != "merge":
        return found
    where = f"PR #{pull['number']}"
    if not section(pull["body"] or "", "Evidence").strip():
        found.append(f"{where}: its body has no `## Evidence` section with content")
    if not any(body.lstrip().startswith(VERDICT) for body in bodies(pull)):
        found.append(f"{where}: no verifier verdict posted (gate.py verdict)")
    if os.environ.get("GITHUB_ACTIONS") != "true":
        found += ci(where, pull)
    paths = merge_paths(pull, loop_rules)
    owner = any(owner_needed("merge", loop_rules, names(issue), paths) for issue in issues)
    found += approvals(where, pull, "merge", "head", pull["headRefOid"], owner)
    return found


def ci(where: str, pull: dict[str, Any]) -> list[str]:
    """One line per CI check on the head that is not green; one when there is none."""
    commits = pull["commits"]["nodes"]
    contexts = commits[0]["commit"]["statusCheckRollup"] if commits else None
    nodes = contexts["contexts"]["nodes"] if contexts else []
    if not nodes:
        return [f"{where}: no CI check on the head commit"]
    if (contexts["contexts"].get("totalCount") or 0) > len(nodes):
        return [f"{where} has more than {len(nodes)} CI checks: the gate reads one page"]
    checks = [
        (
            node.get("name") or node.get("context"),
            node.get("conclusion") or node.get("state") or node.get("status"),
        )
        for node in nodes
    ]
    return [
        f"{where}: CI check `{name}` is {state} on the head commit"
        for name, state in checks
        if state not in GREEN
    ]


def gh(*args: str, data: str | None = None) -> str:
    return subprocess.run(
        ["gh", *args], input=data, check=True, capture_output=True, text=True
    ).stdout


def _graphql(query: str, **fields: object) -> Any:
    args = [arg for key, value in fields.items() for arg in ("-F", f"{key}={value}")]
    # gh fills {owner} and {repo} from the current checkout
    out = gh(
        "api", "graphql", "-f", f"query={query}", "-F", "owner={owner}", "-F", "name={repo}", *args
    )
    return json.loads(out)["data"]["repository"]


def _repository(fields: str) -> str:
    return f"query($owner: String!, $name: String!, $n: Int!) {{ repository(owner: $owner, name: $name) {{ {fields} }} }}"


def pull_request(pr: int) -> dict[str, Any]:
    pull: dict[str, Any] = _graphql(_repository(f"pullRequest(number: $n) {{ {PULL} }}"), n=pr)[
        "pullRequest"
    ]
    return pull


def issue_node(number: int) -> dict[str, Any]:
    node: dict[str, Any] = _graphql(_repository(f"issue(number: $n) {{ {ISSUE} }}"), n=number)[
        "issue"
    ]
    return node


def closing_issues(pull: dict[str, Any]) -> list[dict[str, Any]]:
    """GitHub's closing references plus every `#n` after a closing keyword in the body: GitHub sometimes never
    links such a line, and has no API to set the link."""
    issues: list[dict[str, Any]] = pull["closingIssuesReferences"]["nodes"]
    unlinked = sorted(set(named(pull["body"] or "")) - {issue["number"] for issue in issues})
    if unlinked:  # a `#n` that is a pull request comes back empty and is dropped
        aliases = " ".join(
            f"i{n}: issueOrPullRequest(number: {n}) {{ ... on Issue {{ {ISSUE} }} }}"
            for n in unlinked
        )
        found = _graphql(
            f"query($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {aliases} }} }}"
        )
        issues = issues + [issue for issue in found.values() if issue]
    return issues


def label(number: int, name: str, add: bool) -> None:
    """Add (GitHub creates a missing label) or remove a label on an issue or PR; removing an absent one is fine."""
    path = f"repos/{{owner}}/{{repo}}/issues/{number}/labels"
    if add:
        gh("api", path, "-f", f"labels[]={name}", "--silent")
        return
    try:
        gh("api", "-X", "DELETE", f"{path}/{name}", "--silent")
    except subprocess.CalledProcessError as exc:
        if "Label does not exist" not in exc.stderr:
            raise


def comment(number: int, body: str) -> None:
    gh(
        "api",
        f"repos/{{owner}}/{{repo}}/issues/{number}/comments",
        "-F",
        "body=@-",
        "--silent",
        data=body,
    )


def current_pr() -> int | None:
    try:
        return int(gh("pr", "view", "--json", "number", "--jq", ".number"))
    except subprocess.CalledProcessError as exc:
        if "no pull requests found" in exc.stderr:
            return None
        raise


class Refused(Exception):
    """A reason to stop with exit 1, printed as is."""


def read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError as exc:
        raise Refused(f"{path}: {exc.strerror}: run from the repo root") from exc


def check(point: str, pr: int | None) -> int:
    tracker, loop = read(TRACKER), read(LOOP)
    if pr is None and (pr := current_pr()) is None:
        print("no PR for this branch yet: nothing to gate")
        return 0
    pull = pull_request(pr)
    issues = closing_issues(pull)
    found = problems(
        issues, listed(tracker, "Components"), CATEGORIES | listed(tracker, "Extra categories")
    )
    found += proofs(point, pull, issues, loop)
    for line in found:
        print(line)
    return 1 if found else 0


def approve(point: str, number: int, by: str, triage: str | None) -> int:
    loop_rules = rules(read(LOOP))
    if point == "merge":
        pull = pull_request(number)
        verdicts = [body for body in bodies(pull) if body.lstrip().startswith(VERDICT)]
        if not verdicts:
            raise Refused(f"PR #{number} has no verifier verdict: post it first (gate.py verdict)")
        verdict = "; ".join(
            line.strip()
            for line in verdicts[-1].splitlines()
            if line.strip().startswith(("VERDICT:", "SATISFIED:"))
        )
        issues, paths = closing_issues(pull), merge_paths(pull, loop_rules)
        node, targets, key, value = (
            pull,
            [issue["number"] for issue in issues],
            "head",
            pull["headRefOid"],
        )
        owner = any(owner_needed("merge", loop_rules, names(issue), paths) for issue in issues)
        record = f"Head: {pull['headRefOid']}\nVerdict: {verdict}\n" + (
            f"Triage: {triage}\n" if triage else ""
        )
    else:
        issue = issue_node(number)
        text = spec_of(issue) if point == "spec" else headed(issue, "## Plan")
        if text is None:
            raise Refused(f"#{number} has no `## Plan` comment to approve")
        node, targets, key, value = issue, [number], point, fingerprint(text)
        owner = owner_needed(point, loop_rules, names(issue), None)
        record = f"{point.capitalize()}: {value}\n"
    comment(number, f"Approved: {point}\nBy: {by}\n{record}")
    # a person who already approved this spec, plan or head keeps their label when the loop resumes
    if (
        by == "coordinator" and owner and not current(node, point, key, value, "owner")
    ):  # the label goes on last: a person adds it to approve
        label(number, f"approved:{point}", add=False)
        for target in targets:
            label(target, NEEDS_OWNER, add=True)
        print(
            f"a person must approve {point} too: {NEEDS_OWNER} added; stop until they add `approved:{point}`"
        )
        return 0
    label(number, f"approved:{point}", add=True)
    if by == "owner":
        for target in targets:
            label(target, NEEDS_OWNER, add=False)
    return 0


def verdict(pr: int, report: Path) -> int:
    lines = [line.strip() for line in read(report).splitlines()]
    verdicts = [line for line in lines if line.startswith("VERDICT:")]
    satisfied = [line for line in lines if line.startswith("SATISFIED:")]
    if not satisfied:
        raise Refused(f"{report} has no `SATISFIED:` line: the report is unfinished")
    head = pull_request(pr)["headRefOid"]
    comment(pr, "\n".join([VERDICT, f"Head: {head}", *verdicts[-1:], satisfied[-1]]) + "\n")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    checking = commands.add_parser("check")
    checking.add_argument("point", choices=("build", "merge"))
    checking.add_argument("pr", type=int, nargs="?")
    approving = commands.add_parser("approve")
    approving.add_argument("point", choices=POINTS)
    approving.add_argument("number", type=int)
    approving.add_argument("--by", choices=("coordinator", "owner"), required=True)
    approving.add_argument("--triage")
    posting = commands.add_parser("verdict")
    posting.add_argument("pr", type=int)
    posting.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return check(args.point, args.pr)
        if args.command == "approve":
            return approve(args.point, args.number, args.by, args.triage)
        return verdict(args.pr, args.report)
    except Refused as exc:
        print(exc)
        return 1
    except subprocess.CalledProcessError as exc:
        # gh's reason, e.g. a closing line that names a number with no issue
        print(exc.stderr.strip() or exc)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
