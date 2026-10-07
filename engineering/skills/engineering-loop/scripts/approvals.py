#!/usr/bin/env python3
"""Approvals (engineering-loop): every step leaves proof on GitHub, and this checks it before the loop moves on.

    python3 scripts/approvals.py check <build|merge> [pr]  # one line per missing proof, exit 1; no PR yet: exit 0
    python3 scripts/approvals.py approve <spec|plan|merge> <issue or pr> --by <coordinator|owner> [--triage <link>]
    python3 scripts/approvals.py verdict <pr> <report>      # post the verifier's verdict lines on the PR
    python3 scripts/approvals.py local-ci <pr>              # with `CI: none`: run `mise run check:all` on the PR head

Run from the repo root. The project's `mise run loop:approvals <point> [pr]` task runs `check`; the loop and CI call
that task. `gate.py` and `record-check` are the old names of this script and of `local-ci`, kept for one release.

`check build` needs every issue the PR closes to carry `approved:spec` and not `needs-owner`, with exactly one
category, a component and exactly one size (a `wayfinder:` ticket needs only `approved:spec` and no `needs-owner`), and its approvals: `spec`
always, `plan` when one is due (a `## Plan` comment, or a `Plan:` line in loop.md § Practice). Category, component and
size names are the loop's fixed set plus docs/agents/issue-tracker.md's (`label_names`).
`check merge` adds the PR's: the `## Evidence` section of its body, a posted verifier verdict, CI, and a `merge`
approval on the head commit, with its verdict. CI is the newest run of every check on the head green, unless the base
branch has a `required_status_checks` rule, which the merge queue enforces, or it runs inside GitHub Actions,
where each other check is its own status; with the line `CI: none` in loop.md, a `local-ci` pass on the head instead.
`local-ci` runs only on a clean checkout at the PR head, and records nothing if the check fails or changes the tree.

An exact revert skips the spec and the verdict: a PR whose body has a line `Reverts #<n>` (GitHub's Revert button writes
`Reverts <owner>/<repo>#<n>`), where #n is a merged PR and, file for file as GitHub's diff of each shows them, the PR
removes what #n added and adds what #n removed (files, and each run of lines in order; line numbers and context may
differ), and every path either touches has at the PR's merge base the mode it had after #n and at its head the mode
it had before #n, absence included. A file GitHub shows no diff of (binary, too large, only renamed or moded) is never
exact. Its code returns to a state already specced and reviewed, so `check build` passes it and `check merge` asks
only for Evidence (what went wrong), green CI, the merge approval and a person's approval where a merge rule holds by
path; `approve merge` records `Verdict: exact revert of #<n>`.
A `Reverts #<n>` PR that is not exact gets a line saying why, then every proof of any PR.

An approval is a comment `approve` writes, which the gate reads, plus the `approved:<point>` label for the board:

    Approved: spec
    By: coordinator
    Spec: as edited 2026-10-02 14:35:27 UTC      (plan: Plan:, merge: Head: <sha> and Verdict:)

A spec or plan is named by its last edit as GitHub shows it in the edit history (`as written <time>` before any), so
a person can open the version approved. Every approval is a new comment: a re-approval says the spec, plan or head
changed, and `approve` minimizes as outdated each earlier record it supersedes, keeping another approver's record of
the same version.

The coordinator approves every point. A rule in loop.md § Approvals, one `- <point>: <condition>` line each, adds a
person's approval (`By: owner`). Its label goes on last: the coordinator's approval removes the label and adds
`needs-owner`, so a person approves by adding the label, or by saying so in the session; then `approve --by owner`
writes their record, adds the label and removes `needs-owner`. A person who already approved the current spec, plan
or head keeps their label when the coordinator approves again on resuming. A condition the gate can read is `always`, `size:L`
(`size:L or larger`, `size:L+`), `component <name>`, `category <name>` or `path <glob>` in backticks, joined by `or`;
any other words make the rule the loop's alone, and so does a path on spec or plan, which come before the change. The spec is the issue body, or its last `## Spec` comment where a
tool owns the body. A soft gate against a forgotten step, not a security boundary: the agent holds the same
credentials as the person. issue-tracker.md's components and extra categories are the first backticked name of each
list item under `## Components` and `## Extra categories`. Reads and writes through `gh`. Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

# the ready state: an approved spec (board: Ready); waiting for the owner
READY, NEEDS_OWNER = "approved:spec", "needs-owner"
CATEGORIES = {"bug", "enhancement", "documentation", "chore"}
SIZE_ORDER = ["size:XS", "size:S", "size:M", "size:L", "size:XL"]
SIZES = set(SIZE_ORDER)
TRACKER, LOOP = Path("docs/agents/issue-tracker.md"), Path("docs/agents/loop.md")
POINTS = ("spec", "plan", "merge")
VERDICT = "Verifier verdict"
NOTE = "id body createdAt lastEditedAt isMinimized viewerCanMinimize"
ISSUE = f"number body createdAt lastEditedAt labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}"
PULL = f"""number body baseRefName baseRefOid headRefOid baseRepository {{ nameWithOwner }} labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}
  files(first: 100) {{ totalCount nodes {{ path }} }}
  commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ contexts(first: 100) {{ totalCount nodes {{
    __typename ... on CheckRun {{ name status conclusion startedAt checkSuite {{ workflowRun {{ workflow {{ name }} }} }} }}
    ... on StatusContext {{ context state createdAt }} }} }} }} }} }} }}
  closingIssuesReferences(first: 50) {{ nodes {{ {ISSUE} }} }}"""
# GitHub's closing keywords, plus `Part of` for a spec the PR builds on but leaves open; ponytail: same-repo `#n`
# only, add owner/repo#n and issue URLs when a PR here uses one.
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|part[ \t]+of):?[ \t]+#(\d+)\b", re.IGNORECASE
)
# code and comments: an example, not a closing line
QUOTED = re.compile(r"^[ \t>]*```.*?^[ \t>]*```|`[^`\n]*`|<!--.*?-->", re.DOTALL | re.MULTILINE)
CONDITION = re.compile(
    r"\balways\b|\b(size:(?:XS|S|M|L|XL))(\+|[ \t]+or[ \t]+larger\b)?"
    r"|\b(component|category):?[ \t]*`?([\w./:-]+)`?|\bpath:?[ \t]*`([^`]+)`",
    re.IGNORECASE,
)
# loop.md's opt-out: the line `CI: none`, as a list item or with a note in parentheses, nothing else on it.
NO_CI = r"^[ \t]*(?:[-*][ \t]+)?`?CI:[ \t]*none`?[ \t]*(?:\([^)\n]*\))?[ \t]*$"
# a revert's line, as GitHub's Revert button writes it or by hand; ponytail: one revert per PR, the first line counts.
REVERTS = re.compile(r"^[ \t]*Reverts[ \t]+([\w.-]+/[\w.-]+)?#(\d+)\b", re.MULTILINE)
CHECKED = "Local check passed"
CHANGED = {
    "spec": "The spec changed after the last approval, so it was checked again.\n",
    "plan": "The plan changed after the last approval, so it was checked again.\n",
    "merge": "The head moved after the last approval, so it was checked again.\n",
}
GREEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def named(body: str) -> list[int]:
    """The issue numbers a PR body names after a closing keyword or `Part of` on the same line, in order, each once."""
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


def label_names(tracker: str) -> dict[str, set[str]]:
    """The loop's label rule: each kind's names, the loop's fixed set plus docs/agents/issue-tracker.md's."""
    return {
        "category": CATEGORIES | listed(tracker, "Extra categories"),
        "component": listed(tracker, "Components"),
        "size": SIZES,
    }


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
    total = pull["files"].get("totalCount") or 0
    paths = [file["path"] for file in pull["files"]["nodes"]]
    if total > len(paths):  # past GraphQL's one page, e.g. a PR that commits synced agent files
        paths = pr_files(pull["number"])
    if total > len(paths):
        raise Refused(
            f"PR #{pull['number']} changes {total} files and GitHub lists {len(paths)}: "
            "the gate can't judge a path rule on the rest, so split the PR"
        )
    return paths


def version(holder: dict[str, Any]) -> str:
    """The issue or comment holding a spec or plan, named by its last edit, as GitHub's edit history shows it."""
    edited = holder.get("lastEditedAt")
    when = (edited or holder["createdAt"]).replace("T", " ").replace("Z", " UTC")
    return f"as edited {when}" if edited else f"as written {when}"


def names(node: dict[str, Any]) -> set[str]:
    return {label["name"] for label in node["labels"]["nodes"]}


def notes(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Its comments; refused past one page, where an approval or a spec could be among those not read."""
    comments = node["comments"]
    # ponytail: one page of 100; page with `before:` cursors when a spec or PR outgrows it.
    if (comments.get("totalCount") or 0) > len(comments["nodes"]):
        where = f"#{node['number']}"
        raise Refused(
            f"{where} has more than {len(comments['nodes'])} comments: the gate reads one page"
        )
    found: list[dict[str, Any]] = comments["nodes"]
    return found


def bodies(node: dict[str, Any]) -> list[str]:
    return [note["body"] for note in notes(node)]


def headed(node: dict[str, Any], heading: str) -> dict[str, Any] | None:
    """The last comment that starts with `heading`."""
    found = [note for note in notes(node) if note["body"].lstrip().startswith(heading)]
    return found[-1] if found else None


def spec_holder(issue: dict[str, Any]) -> dict[str, Any]:
    """The issue, or its last `## Spec` comment where a tool owns the body."""
    return headed(issue, "## Spec") or issue


def parsed(body: str, point: str) -> dict[str, str] | None:
    """An `Approved: <point>` comment's lower-cased `Key: value` lines; None for any other comment."""
    lines = body.strip().splitlines()
    if not lines or lines[0].strip() != f"Approved: {point}":
        return None
    return {
        key.strip().lower(): value.strip()
        for key, _, value in (line.partition(":") for line in lines[1:])
    }


def records(node: dict[str, Any], point: str) -> list[dict[str, str]]:
    """The approval records for `point` among a node's comments."""
    return [found for body in bodies(node) if (found := parsed(body, point)) is not None]


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


def problems(issues: list[dict[str, Any]], kinds: dict[str, set[str]]) -> list[str]:
    """One line per reason an issue the PR closes waits for the owner or lacks a label of `kinds` (label_names);
    empty when none does. A missing `approved:spec` is proofs()'s line."""
    if not issues:
        return [
            "the PR names no issue: it needs a `Closes #<spec>` or `Part of #<spec>` line for an approved spec"
        ]
    found = []
    for issue in issues:
        labels = names(issue)
        if NEEDS_OWNER in labels:
            found.append(f"#{issue['number']} waits for the owner ({NEEDS_OWNER})")
        if any(label.startswith("wayfinder:") for label in labels):
            # a wayfinder ticket settles a decision: its wayfinder: label is its category, it has no component or
            # size, and no approval records, so its state is the label alone
            if READY not in labels:
                found.append(f"#{issue['number']} lacks `{READY}`: spec it first")
            continue
        for kind in ("category", "size"):
            allowed = kinds[kind]
            if len(labels & allowed) != 1:
                found.append(
                    f"#{issue['number']} needs exactly one {kind} label ({', '.join(sorted(allowed))}), has {len(labels & allowed)}"
                )
        if not labels & kinds["component"]:
            found.append(
                f"#{issue['number']} needs a component label ({', '.join(sorted(kinds['component'])) or f'{TRACKER} lists none'})"
            )
    return found


def proofs(
    point: str,
    pull: dict[str, Any],
    issues: list[dict[str, Any]],
    loop: str,
    revert: int | None = None,
    requires_checks: Callable[[str], bool] | None = None,
) -> list[str]:
    """One line per approval or proof the PR and its issues lack at `point` (build or merge); an exact revert of
    #`revert` names no issue and needs no verdict. `requires_checks(base)` says whether the base branch's rules
    require status checks (default: GitHub's answer)."""
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
            version(spec_holder(issue)),
            owner_needed("spec", loop_rules, labels, None),
        )
        plan = headed(issue, "## Plan")
        if plan is not None:
            plan_owner = owner_needed("plan", loop_rules, labels, None)
            found += approvals(where, issue, "plan", "plan", version(plan), plan_owner)
        elif practice_plans(loop):
            found.append(f"{where} has no `## Plan` comment, and one is due")
    if point != "merge":
        return found
    where = f"PR #{pull['number']}"
    evidence = section(pull["body"] or "", "Evidence")
    if not evidence.strip():
        found.append(f"{where}: its body has no `## Evidence` section with content")
    if revert is None and not any(body.lstrip().startswith(VERDICT) for body in bodies(pull)):
        found.append(f"{where}: no verifier verdict posted (approvals.py verdict)")
    if re.search(NO_CI, loop, re.MULTILINE | re.IGNORECASE):
        if not any(
            [line.strip() for line in body.strip().splitlines()[:2]]
            == [CHECKED, f"Head: {pull['headRefOid']}"]
            for body in bodies(pull)
        ):
            found.append(
                f"{where}: the project has no CI (loop.md `CI: none`), and no local check passed on"
                " the head (approvals.py local-ci)"
            )
    elif os.environ.get("GITHUB_ACTIONS") != "true" and not (requires_checks or required_checks)(
        pull["baseRefName"]
    ):
        found += ci(where, pull)
    owner = owner_needed("merge", loop_rules, labelled(issues), merge_paths(pull, loop_rules))
    found += approvals(where, pull, "merge", "head", pull["headRefOid"], owner)
    return found


def labelled(issues: list[dict[str, Any]]) -> set[str]:
    """Every label on the issues: a merge rule holds when it holds for any of them."""
    return set().union(*(names(issue) for issue in issues))


def changed_lines(patch: str) -> list[tuple[list[str], list[str]]]:
    """Each run of changed lines in a file's patch, in order, as the lines it adds and the lines it removes; a context
    or `@@` line ends a run, and a line that ends without a newline is marked so."""
    runs: list[tuple[list[str], list[str]]] = []
    last: list[str] | None = None
    for line in patch.split("\n"):
        if line.startswith("\\") and last:  # `\ No newline at end of file`, about the line before
            last[-1] += "\n\\ no newline"
        elif line[:1] in ("+", "-"):
            if last is None:
                runs.append(([], []))
            last = runs[-1][0 if line[0] == "+" else 1]
            last.append(line[1:])
        else:
            last = None
    return runs


# the status a file has in the PR that undoes a change of that status
UNDONE = {"added": "removed", "removed": "added", "modified": "modified", "renamed": "renamed"}


def inexact(
    original: list[dict[str, Any]],
    revert: list[dict[str, Any]],
    number: int,
    undone: tuple[dict[str, str] | None, dict[str, str] | None],
    undoing: tuple[dict[str, str] | None, dict[str, str] | None],
) -> list[str]:
    """Why `revert` does not undo #number, both as GitHub's REST API lists a PR's files; empty when it does. Each file
    must have the inverse status and the inverse runs of changed lines in order, while line numbers and context move
    with main. Every path either touches must have, in `undoing` (the revert's merge base and head trees), the modes
    it had in `undone` (#number's base and merge commit trees) the other way round, absence included. A tree GitHub
    truncated is None."""
    why: list[str] = []

    def changes(entries: list[dict[str, Any]], inverted: bool) -> dict[tuple[str, str], Any]:
        found = {}
        for entry in entries:
            old, new = entry.get("previous_filename") or entry["filename"], entry["filename"]
            if (
                not entry.get("changes") or "patch" not in entry
            ):  # binary, too large, or only renamed or moded
                why.append(f"GitHub shows no diff of `{new}` to compare")
            runs = changed_lines(entry.get("patch") or "")
            status = entry.get("status", "")
            found[(new, old) if inverted else (old, new)] = (
                (UNDONE.get(status, f"no inverse of {status}"), [(r, a) for a, r in runs])
                if inverted
                else (status, runs)
            )
        return found

    def shown(old: str, new: str) -> str:
        return new if old == new else f"{old} -> {new}"

    expected, actual = changes(original, inverted=True), changes(revert, inverted=False)
    for key in sorted(expected.keys() | actual.keys()):
        if key not in actual:
            why.append(f"it leaves `{shown(key[1], key[0])}` as #{number} changed it")
        elif key not in expected:
            why.append(f"it changes `{shown(*key)}`, which #{number} did not")
        elif actual[key][0] != expected[key][0]:
            why.append(
                f"`{shown(*key)}` is {actual[key][0]}, and undoing #{number} needs {expected[key][0]}"
            )
        elif actual[key][1] != expected[key][1]:
            lines, undo = (
                Counter(
                    (sign, line) for run in runs for sign, side in zip("+-", run) for line in side
                )
                for runs in (actual[key][1], expected[key][1])
            )
            extra, missing = sum((lines - undo).values()), sum((undo - lines).values())
            why.append(
                f"`{shown(*key)}` has {extra} line(s) beyond the inverse of #{number}, {missing} missing"
                if extra or missing
                else f"`{shown(*key)}` changes the lines #{number} changed in another order"
            )
    before, after = undone
    base, head = undoing
    if None in (before, after, base, head):
        why.append("GitHub truncates a tree it would compare file modes in")
    else:
        touched = {
            entry[name]
            for entry in original + revert
            for name in ("filename", "previous_filename")
            if entry.get(name)
        }
        for path in sorted(touched):
            for theirs, ours, where, when in (
                (after, base, "at the merge base", "after"),
                (before, head, "at the head", "before"),
            ):
                if ours.get(path) != theirs.get(path):
                    why.append(
                        f"`{path}` has mode {ours.get(path, 'absent')} {where}, and"
                        f" {theirs.get(path, 'absent')} {when} #{number}"
                    )
    return why


def reverts(pull: dict[str, Any]) -> tuple[int | None, list[str]]:
    """The merged PR this one exactly reverts, or a line saying why its `Reverts #<n>` is no exact revert; (None, [])
    for a PR without one."""
    found = REVERTS.search(QUOTED.sub("", pull["body"] or ""))
    if not found:
        return None, []
    repo, number = found.group(1), int(found.group(2))
    base = pull["baseRepository"]["nameWithOwner"]
    if repo and repo.lower() != base.lower():
        why = [f"it names a PR of {repo}, and this is {base}"]
    elif not (original := merged_pull(number)):
        why = [f"#{number} is not a merged pull request"]
    else:
        changes, theirs = pr_changes(number), pr_changes(pull["number"])
        why = [
            f"GitHub lists {len(listed)} of {where}'s {total} files"
            for where, listed, total in (
                (f"#{number}", changes, original["changed_files"]),
                (f"PR #{pull['number']}", theirs, pull["files"].get("totalCount") or len(theirs)),
            )
            if len(listed) < total
        ] or inexact(
            changes,
            theirs,
            number,
            (tree(original["base"]["sha"]), tree(original["merge_commit_sha"])),
            (tree(merge_base(pull["baseRefOid"], pull["headRefOid"])), tree(pull["headRefOid"])),
        )
    if not why:
        return number, []
    return None, [
        f"PR #{pull['number']} is not an exact revert of #{number}: {'; '.join(why)}. It needs every proof of any PR"
    ]


def required_checks(base: str) -> bool:
    """Whether a ruleset on `base` has a `required_status_checks` rule: then the merge queue enforces the required
    checks, and a red advisory one must not block. ponytail: rulesets only; a classic branch protection's required
    checks leave this False, so the gate keeps reading every check, the stricter answer."""
    out = gh(
        "api", "--paginate", f"repos/{{owner}}/{{repo}}/rules/branches/{base}", "--jq", ".[].type"
    )
    return "required_status_checks" in out.split()


def ci(where: str, pull: dict[str, Any]) -> list[str]:
    """One line per CI check whose newest run on the head is not green; one when there is none."""
    commits = pull["commits"]["nodes"]
    contexts = commits[0]["commit"]["statusCheckRollup"] if commits else None
    nodes = contexts["contexts"]["nodes"] if contexts else []
    if not nodes:
        return [f"{where}: no CI check on the head commit"]
    if (contexts["contexts"].get("totalCount") or 0) > len(nodes):
        return [f"{where} has more than {len(nodes)} CI checks: the gate reads one page"]
    # A rerun, or a run cancelled by a newer one in its concurrency group, leaves several runs of one check on the
    # head; only the newest says whether it is green. One job name in two workflows is two checks.
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for node in nodes:
        run = (node.get("checkSuite") or {}).get("workflowRun") or {}
        key = ((run.get("workflow") or {}).get("name", ""), node.get("name") or node.get("context"))
        if key not in newest or started(node) >= started(newest[key]):
            newest[key] = node
    checks = [
        (name, node.get("conclusion") or node.get("state") or node.get("status"))
        for (_, name), node in newest.items()
    ]
    return [
        f"{where}: CI check `{name}` is {state} on the head commit"
        for name, state in checks
        if state not in GREEN
    ]


def started(node: dict[str, Any]) -> str:
    """When a check run started, or a status was set; ISO 8601, so it orders as text."""
    return node.get("startedAt") or node.get("createdAt") or ""


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


def pr_changes(number: int) -> list[dict[str, Any]]:
    """Every file a PR changes, with its patch, as GitHub's REST API pages them: up to 3000."""
    out = gh(
        "api",
        "--paginate",
        f"repos/{{owner}}/{{repo}}/pulls/{number}/files?per_page=100",
        "--jq",
        ".[]",
    )
    return [json.loads(line) for line in out.splitlines()]


def pr_files(number: int) -> list[str]:
    return [entry["filename"] for entry in pr_changes(number)]


def merged_pull(number: int) -> dict[str, Any] | None:
    """PR #number as GitHub's REST API returns it, when it was merged; None for an open or closed PR, or an issue."""
    try:
        found: dict[str, Any] = json.loads(gh("api", f"repos/{{owner}}/{{repo}}/pulls/{number}"))
    except subprocess.CalledProcessError as exc:
        if "Not Found" in exc.stderr:
            return None
        raise
    return found if found.get("merged") else None


def merge_base(base: str, head: str) -> str:
    """The commit GitHub diffs a PR's head against: where it branched from its base."""
    return gh(
        "api", f"repos/{{owner}}/{{repo}}/compare/{base}...{head}", "--jq", ".merge_base_commit.sha"
    ).strip()


def tree(sha: str) -> dict[str, str] | None:
    """The mode of every path in commit `sha`'s tree, from GitHub's trees API; None when GitHub truncates it.
    ponytail: one recursive read, up to GitHub's 100,000 entries; read each touched directory when a repo outgrows it."""
    found = json.loads(gh("api", f"repos/{{owner}}/{{repo}}/git/trees/{sha}?recursive=1"))
    if found["truncated"]:
        return None
    return {entry["path"]: entry["mode"] for entry in found["tree"] if entry["type"] != "tree"}


def issue_node(number: int) -> dict[str, Any]:
    node: dict[str, Any] = _graphql(_repository(f"issue(number: $n) {{ {ISSUE} }}"), n=number)[
        "issue"
    ]
    return node


def closing_issues(pull: dict[str, Any]) -> list[dict[str, Any]]:
    """GitHub's closing references plus every `#n` after a closing keyword or `Part of` in the body: GitHub sometimes
    never links a closing line, and has no API to set the link."""
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


def minimize(comment_id: str) -> None:
    """Collapse a comment on GitHub as outdated; it stays readable, and the gate still reads it."""
    gh(
        "api",
        "graphql",
        "-f",
        "query=mutation($id: ID!) { minimizeComment(input: {subjectId: $id, classifier: OUTDATED}) { clientMutationId } }",
        "-f",
        f"id={comment_id}",
        "--silent",
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
    revert, found = reverts(pull)
    issues = [] if revert else closing_issues(pull)
    if not revert:
        found += problems(issues, label_names(tracker))
    found += proofs(point, pull, issues, loop, revert)
    for line in found:
        print(line)
    return 1 if found else 0


def approve(point: str, number: int, by: str, triage: str | None) -> int:
    loop_rules = rules(read(LOOP))
    if point == "merge":
        pull = pull_request(number)
        revert, refused = reverts(pull)
        verdicts = [body for body in bodies(pull) if body.lstrip().startswith(VERDICT)]
        if not revert and not verdicts:
            raise Refused(
                "\n".join(
                    [
                        *refused,
                        f"PR #{number} has no verifier verdict: post it first (approvals.py verdict)",
                    ]
                )
            )
        verdict = (
            f"exact revert of #{revert}"
            if revert
            else "; ".join(
                line.strip()
                for line in verdicts[-1].splitlines()
                if line.strip().startswith(("VERDICT:", "SATISFIED:"))
            )
        )
        issues = [] if revert else closing_issues(pull)
        # an exact revert names no issue, so a person's approval is asked for on the PR itself
        node, targets, key, value = (
            pull,
            [issue["number"] for issue in issues] or [number],
            "head",
            pull["headRefOid"],
        )
        owner = owner_needed("merge", loop_rules, labelled(issues), merge_paths(pull, loop_rules))
        record = f"Head: {pull['headRefOid']}\nVerdict: {verdict}\n" + (
            f"Triage: {triage}\n" if triage else ""
        )
    else:
        issue = issue_node(number)
        holder = spec_holder(issue) if point == "spec" else headed(issue, "## Plan")
        if holder is None:
            raise Refused(f"#{number} has no `## Plan` comment to approve")
        node, targets, key, value = issue, [number], point, version(holder)
        owner = owner_needed(point, loop_rules, names(issue), None)
        record = f"{point.capitalize()}: {value}\n"
    earlier = [
        (note, found) for note in notes(node) if (found := parsed(note["body"], point)) is not None
    ]
    if any(found.get("by") == by and found.get(key) != value for _, found in earlier):
        record += CHANGED[point]
    comment(number, f"Approved: {point}\nBy: {by}\n{record}")
    # what this record supersedes: any earlier one but another approver's of the same version
    for note, found in earlier:
        superseded = found.get(key) != value or found.get("by") == by
        if superseded and not note.get("isMinimized") and note.get("viewerCanMinimize"):
            minimize(note["id"])
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


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


LOCAL_CI = ["mise", "run", "check:all"]


def local_ci(pr: int) -> int:
    """Run `mise run check:all` on a clean checkout at the PR head; post a record only when it passes untouched."""
    head = pull_request(pr)["headRefOid"]

    def state() -> tuple[str, str]:
        # untracked files and submodule edits listed whatever status.showUntrackedFiles or submodule.*.ignore say
        status = git("status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none")
        # status skips files whose index flag says so (assume-unchanged, set by core.ignoreStat; skip-worktree)
        hidden = [
            f"{line[2:]} (index flag hides its changes)\n"
            for line in git("ls-files", "-v").splitlines()
            if line[:1].islower() or line[:1] == "S"
        ]
        return git("rev-parse", "HEAD").strip(), status + "".join(hidden)

    before = state()
    if before[0] != head:
        raise Refused(
            f"the checkout is at {before[0]}, PR #{pr}'s head is {head}: push, or check out the head"
        )
    if before[1]:
        raise Refused(f"the tree has changes, so the check would not run on the head:\n{before[1]}")
    command = " ".join(LOCAL_CI)
    code = subprocess.run(LOCAL_CI, check=False).returncode
    if code:
        raise Refused(f"{command} exited {code}: nothing recorded")
    if state() != before:
        raise Refused(
            f"{command} changed the checkout, so it did not run on the head as pushed:\n{state()[1]}"
        )
    comment(pr, f"{CHECKED}\nHead: {head}\nCommand: {command}\n")
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
    recording = commands.add_parser("local-ci", aliases=["record-check"])
    recording.add_argument("pr", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return check(args.point, args.pr)
        if args.command == "approve":
            return approve(args.point, args.number, args.by, args.triage)
        if args.command in ("local-ci", "record-check"):
            return local_ci(args.pr)
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
