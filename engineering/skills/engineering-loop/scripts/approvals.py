#!/usr/bin/env python3
"""Approvals (engineering-loop): every step leaves proof on GitHub, and this checks it before the loop moves on.

    python3 scripts/approvals.py check <build|merge> [pr]  # one line per missing proof, exit 1; waiting: exit 3
    python3 scripts/approvals.py land <pr>                  # every merge proof, then ready and merge; exit 0, 1 or 3
    python3 scripts/approvals.py approve <spec|plan> <issue> --by <coordinator|owner>
    python3 scripts/approvals.py verdict <pr> <report>      # post the verifier's verdict lines on the PR
    python3 scripts/approvals.py local-ci <pr>              # with `CI: none`: run `mise run check:all` on the PR head

Run anywhere in the checkout: it reads docs/agents/ at the checkout's root. The project's `mise run loop:approvals
<point> [pr]` task runs `check`, and its `loop:land <pr>` task, where it has one, runs `land`; the loop and CI call
those tasks.
`gate.py` and `record-check` are the old names of this script and of `local-ci`, kept for one release.

`check build` needs every issue the PR closes to carry `approved:spec` and not `needs-owner`, with exactly one
category, a component and exactly one size (a `wayfinder:` ticket needs only `approved:spec` and no `needs-owner`), and its approvals: `spec`
always, `plan` when one is due (a `## Plan` comment, or a `Plan:` line in loop.md § Practice). Category, component and
size names are the loop's fixed set plus docs/agents/issue-tracker.md's (`label_names`).
A repo without docs/agents/loop.md has no rules: each issue needs only `approved:spec` and no `needs-owner`, with no
approval record. Without docs/agents/issue-tracker.md no label's shape is checked.
`check merge` adds the PR's, whose absence fails (exit 1): the `## Evidence` section of its body; the newest verifier
verdict saying `SATISFIED: yes` with 0 blocker and 0 major, on the head, or on an earlier head where no commit since
changes a file the PR changes (at that head or now; only a merge of main came in); and no review whose latest state
is `CHANGES_REQUESTED`. Then it waits (exit 3, one line per wait; the approvals workflow maps it to a `pending`
status) for the newest run of the aggregate `check` on the head to be green, the one check it reads (with the line
`CI: none` in loop.md, a `local-ci` pass on the head instead), and, where a `merge:` rule asks, for the owner's
`approved:merge` label on the PR, added after the head was pushed and still present. A push removes the label (the
approvals workflow does it on `synchronize`), so the label never covers a head the owner did not see; the push time is
GitHub's repository activity for the head branch. No PR yet, or every proof held: exit 0.
`land` is the one way an agent merges. It runs every proof of `check merge` and refuses (exit 1) before touching the
PR when one fails. A draft it marks ready, which starts CI, and exits 3, since a draft's skipped checks say nothing
about the ready PR: run it again. On a ready PR it reads the checks the base requires (its rulesets and branch
protection; a base requiring none requires every check on the head green). With every required check
green and the label where a rule asks: `gh pr merge --squash --match-head-commit <head>`, exit 0. While only
required checks are pending and the repo allows auto-merge, the same with `--auto`, so GitHub merges once they pass,
exit 0. Otherwise (a red check, the label, no auto-merge, `CI: none` without a record) exit 3: run it again. A
merged PR: exit 0; a closed one: exit 1.
`local-ci` runs only on a clean checkout at the PR head, and records nothing if the check fails or changes the tree.

An exact revert skips the spec and the verdict: a PR whose body has a line `Reverts #<n>` (GitHub's Revert button writes
`Reverts <owner>/<repo>#<n>`), where #n is a merged PR and, file for file as GitHub's diff of each shows them, the PR
removes what #n added and adds what #n removed (files, and each run of lines in order; line numbers and context may
differ), and every path either touches has at the PR's merge base the mode it had after #n and at its head the mode
it had before #n, absence included. A file GitHub shows no diff of (binary, too large, only renamed or moded) is never
exact. Its code returns to a state already specced and reviewed, so `check build` passes it and `check merge` asks
only for Evidence (what went wrong), no review requesting changes, a green `check` and the label where a rule asks.
A `Reverts #<n>` PR that is not exact gets a line saying why, then every proof of any PR.

A spec or plan approval is a comment `approve` writes, which the gate reads, plus the `approved:<point>` label for
the board:

    Approved: spec
    By: coordinator
    Spec: as edited 2026-10-02 14:35:27 UTC      (plan: Plan:)

A spec or plan is named by its last edit as GitHub shows it in the edit history (`as written <time>` before any), so
a person can open the version approved. Every approval is a new comment: a re-approval says the spec or plan
changed, and `approve` minimizes as outdated each earlier record it supersedes, keeping another approver's record of
the same version.

The coordinator approves spec and plan. A rule in loop.md § Approvals, one `- <spec|plan|merge>: <condition>` line
each, adds a person's approval. For a spec or plan (`By: owner`) its label goes on last: the coordinator's approval
removes the label and adds `needs-owner`, so a person approves by adding the label, or by saying so in the session;
then `approve --by owner` writes their record, adds the label and removes `needs-owner`. A person who already approved
the current spec or plan keeps their label when the coordinator approves again on resuming. A condition the gate can
read is `always`, `size:L` (`size:L or larger`, `size:L+`), `component <name>`, `category <name>` or `path <glob>`,
joined by `or`. For a spec or plan any other words, or a `path`, make the rule the loop's alone, since a spec or plan
comes before the change. A `merge:` rule asks for the owner's `approved:merge` on the labels of the PR and its issues
and the PR's files; a `merge:` condition the gate can't read asks for it too, since nothing else would enforce it.
Without a matching `merge:` rule the gates are the merge approval. The spec is the issue
body, or its last comment whose first line is `## Spec`, where a tool owns the body. A soft gate against a forgotten step, not a security boundary: the agent holds the same
credentials as the person. issue-tracker.md's components and extra categories are the first backticked name of each
list item under `## Components` and `## Extra categories`. Reads and writes through `gh`. Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
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
POINTS = ("spec", "plan")
MERGE_LABEL = "approved:merge"
# check merge's exit while it waits for `check` or the owner; argparse's usage error is 2
WAITING = 3
VERDICT = "Verifier verdict"
NOTE = "id body createdAt lastEditedAt isMinimized viewerCanMinimize"
ISSUE = f"number body createdAt lastEditedAt labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}"
PULL = f"""number state isDraft body baseRefName baseRefOid headRefName headRefOid baseRepository {{ nameWithOwner }} labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}
  files(first: 100) {{ totalCount nodes {{ path }} }} latestReviews(first: 100) {{ nodes {{ state author {{ login }} }} }}
  timelineItems(last: 100, itemTypes: [LABELED_EVENT]) {{ nodes {{ ... on LabeledEvent {{ createdAt label {{ name }} }} }} }}
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
}
GREEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}
# a finished check run or a set status that is not green: it turns green only when run again, never by waiting
RED = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE"}


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
    """loop.md § Approvals as (point, condition) pairs: `spec`, `plan` and `merge`."""
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


def owner_needed(point: str, loop_rules: list[tuple[str, str]], labels: set[str]) -> bool:
    return any(matches(condition, labels, None) for rule, condition in loop_rules if rule == point)


def paths(pull: dict[str, Any]) -> list[str] | None:
    """The files the PR changes; None past the one page of 100 the gate reads."""
    files = pull["files"]
    found = [file["path"] for file in files["nodes"]]
    return None if (files.get("totalCount") or 0) > len(found) else found


def merge_asked(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> bool:
    """Whether a `merge:` rule asks for the owner's `approved:merge` label, on the labels of the PR and its issues
    and on the PR's files. A condition the gate can't read asks for it, since nothing else would enforce it."""
    labels = names(pull).union(*(names(issue) for issue in issues))
    return any(
        matches(condition, labels, paths(pull)) is not False
        for rule, condition in rules(loop or "")
        if rule == "merge"
    )


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
    """The last comment whose first line is `heading`: `## Specification notes` is no `## Spec`."""
    found = [
        note for note in notes(node) if note["body"].strip().split("\n", 1)[0].rstrip() == heading
    ]
    return found[-1] if found else None


def spec_holder(issue: dict[str, Any]) -> dict[str, Any]:
    """The issue, or its last `## Spec` comment where a tool owns the body."""
    return headed(issue, "## Spec") or issue


def parsed(body: str, heading: str) -> dict[str, str] | None:
    """The lower-cased `Key: value` lines of a comment whose first line is `heading` (`Approved: <point>`, or
    `Verifier verdict`); None for any other comment."""
    lines = body.strip().splitlines()
    if not lines or lines[0].strip() != heading:
        return None
    return {
        key.strip().lower(): value.strip()
        for key, _, value in (line.partition(":") for line in lines[1:])
    }


def records(node: dict[str, Any], point: str) -> list[dict[str, str]]:
    """The approval records for `point` among a node's comments."""
    return [
        found for body in bodies(node) if (found := parsed(body, f"Approved: {point}")) is not None
    ]


def current(node: dict[str, Any], point: str, key: str, value: str, by: str) -> bool:
    """Whether `by` approved `point` for this spec or plan."""
    return any(
        record.get("by") == by and record.get(key) == value for record in records(node, point)
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


def problems(issues: list[dict[str, Any]], kinds: dict[str, set[str]] | None) -> list[str]:
    """One line per reason an issue the PR closes waits for the owner or lacks a label of `kinds` (label_names;
    None, without docs/agents/issue-tracker.md, checks no label's shape); empty when none does. A missing
    `approved:spec` is proofs()'s line."""
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
        if kinds is None:
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
    loop: str | None,
    revert: int | None = None,
) -> list[str]:
    """One line per approval or proof the PR and its issues lack at `point` (build or merge); an exact revert of
    #`revert` names no issue and needs no verdict. Without docs/agents/loop.md (`loop` None) an issue needs only the
    `approved:spec` label. What the merge waits for is waits()'s."""
    loop_rules, found = rules(loop or ""), []
    for issue in issues:
        labels = names(issue)
        if any(label.startswith("wayfinder:") for label in labels):
            continue
        where = f"#{issue['number']}"
        if loop is None:
            if READY not in labels:
                found.append(f"{where} lacks the `{READY}` label")
            continue
        found += approvals(
            where,
            issue,
            "spec",
            "spec",
            version(spec_holder(issue)),
            owner_needed("spec", loop_rules, labels),
        )
        plan = headed(issue, "## Plan")
        if plan is not None:
            plan_owner = owner_needed("plan", loop_rules, labels)
            found += approvals(where, issue, "plan", "plan", version(plan), plan_owner)
        elif practice_plans(loop):
            found.append(f"{where} has no `## Plan` comment, and one is due")
    if point != "merge":
        return found
    where = f"PR #{pull['number']}"
    evidence = section(pull["body"] or "", "Evidence")
    if not evidence.strip():
        found.append(f"{where}: its body has no `## Evidence` section with content")
    if revert is None:
        found += reviewed(where, pull)
    found += [
        f"{where}: {(review.get('author') or {}).get('login', 'a reviewer')} requested changes: answer the review"
        for review in pull["latestReviews"]["nodes"]
        if review["state"] == "CHANGES_REQUESTED"
    ]
    return found


def reviewed(where: str, pull: dict[str, Any]) -> list[str]:
    """One line per reason the newest verifier verdict lets nothing land: it is not satisfied, a blocker or a major
    is open, or it is on an older head and the commits since change a file the PR changes (touched_since). A head
    that only took in main's changes to other files needs no further pass (coordinator.md step 8)."""
    verdicts = [found for body in bodies(pull) if (found := parsed(body, VERDICT)) is not None]
    if not verdicts:
        return [f"{where}: no verifier verdict posted (approvals.py verdict)"]
    newest = verdicts[-1]
    head = newest.get("head", "").lower()
    counts = [
        re.search(rf"(\d+)\s+{kind}s?\b", newest.get("verdict", ""))
        for kind in ("blocker", "major")
    ]
    if not re.fullmatch(r"[0-9a-f]{7,40}", head) or None in counts or "satisfied" not in newest:
        return [
            f"{where}: the newest verifier verdict lacks a `Head:`, `VERDICT:` or `SATISFIED:` line (approvals.py verdict)"
        ]
    found = []
    if newest["satisfied"].lower().split()[:1] != ["yes"]:
        found.append(f"{where}: the newest verifier verdict is not satisfied: fix and verify again")
    blocker, major = (int(count.group(1)) for count in counts if count)
    if blocker or major:
        found.append(
            f"{where}: the newest verifier verdict has {blocker} blocker and {major} major open: fix and verify again"
        )
    if not pull["headRefOid"].lower().startswith(head):
        since = touched_since(pull, head)
        if since is None:
            found.append(
                f"{where}: the newest verifier verdict is on {head}, and GitHub can't compare it with the head: verify the head"
            )
        elif since:
            changed = ", ".join(f"`{path}`" for path in since)
            found.append(
                f"{where}: the newest verifier verdict is on {head}, and later commits change {changed}: verify the change since"
            )
    return found


def waits(
    pull: dict[str, Any],
    issues: list[dict[str, Any]],
    loop: str | None,
    pushed: Callable[[dict[str, Any]], str | None] | None = None,
) -> list[str]:
    """One line per thing the merge waits for: ran()'s aggregate `check`, and the owner's label (owner_waits)."""
    return ran(pull, loop) + owner_waits(pull, issues, loop, pushed)


def no_ci(loop: str | None) -> bool:
    return re.search(NO_CI, loop or "", re.MULTILINE | re.IGNORECASE) is not None


def ran(pull: dict[str, Any], loop: str | None, required: set[str] | None = None) -> list[str]:
    """One line per check the merge waits for on the head: ci()'s `required` (None: the aggregate `check`), or with
    `CI: none` a local-ci pass."""
    where = f"PR #{pull['number']}"
    if no_ci(loop):
        head = [CHECKED, f"Head: {pull['headRefOid']}"]
        if any(
            [line.strip() for line in body.strip().splitlines()[:2]] == head
            for body in bodies(pull)
        ):
            found = []
        else:
            found = [
                f"{where}: the project has no CI (loop.md `CI: none`), and no local check passed on the head (approvals.py local-ci)"
            ]
    else:
        found = ci(where, pull, required)
    return found


def owner_waits(
    pull: dict[str, Any],
    issues: list[dict[str, Any]],
    loop: str | None,
    pushed: Callable[[dict[str, Any]], str | None] | None = None,
) -> list[str]:
    """A line while a `merge:` rule asks (merge_asked) and the owner's `approved:merge` label is not on the PR, added
    after the head's push. `pushed(pull)` is when the head was pushed (default: GitHub's repository activity)."""
    where, found = f"PR #{pull['number']}", []
    if not merge_asked(pull, issues, loop):
        return found
    if MERGE_LABEL not in names(pull):
        return found + [f"{where} waits for the owner's `{MERGE_LABEL}` label"]
    added = max(
        (
            event["createdAt"]
            for event in pull["timelineItems"]["nodes"]
            if (event.get("label") or {}).get("name") == MERGE_LABEL
        ),
        default="",
    )
    when = (pushed or head_pushed)(pull)
    if when is None:
        found.append(
            f"{where}: GitHub lists no push of the head {pull['headRefOid']}, so `{MERGE_LABEL}` can't be dated after it"
        )
    elif added <= when:  # ISO 8601 in UTC, so it orders as text
        found.append(
            f"{where}: `{MERGE_LABEL}` was added before the head was pushed: the owner adds it again"
        )
    return found


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


def head_checks(
    pull: dict[str, Any], required: set[str] | None
) -> tuple[list[tuple[str, str]], int | None]:
    """The state of the newest run of each check on the head the merge reads, as (name, state): `required` (None:
    the aggregate `check`, the one check `check merge` reads, since every other check is advisory or the ruleset's;
    empty: every check); and how many checks GitHub returned when it holds more than that one page, else None."""
    commits = pull["commits"]["nodes"]
    contexts = commits[0]["commit"]["statusCheckRollup"] if commits else None
    every = contexts["contexts"]["nodes"] if contexts else []
    more = (
        len(every)
        if contexts and (contexts["contexts"].get("totalCount") or 0) > len(every)
        else None
    )
    wanted = {"check"} if required is None else required
    # A rerun, or a run cancelled by a newer one in its concurrency group, leaves several runs of one check on the
    # head; only the newest says whether it is green. One job name in two workflows is two checks.
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for node in every:
        name = node.get("name") or node.get("context")
        if wanted and name not in wanted:
            continue
        run = (node.get("checkSuite") or {}).get("workflowRun") or {}
        key = ((run.get("workflow") or {}).get("name", ""), name)
        if key not in newest or started(node) >= started(newest[key]):
            newest[key] = node
    return [
        (name, node.get("conclusion") or node.get("state") or node.get("status"))
        for (_, name), node in newest.items()
    ], more


def ci(where: str, pull: dict[str, Any], required: set[str] | None = None) -> list[str]:
    """A line per check head_checks() reads that is not green on the head, or not there yet."""
    checks, more = head_checks(pull, required)
    wanted = {"check"} if required is None else required
    if wanted:
        missing = [f"`{name}`" for name in sorted(wanted - {name for name, _ in checks})]
    else:  # every check of none would pass a head CI has not reached yet
        missing = [] if checks else ["check"]
    if more is not None and (missing or not wanted):
        return [f"{where} has more than {more} CI checks: the gate reads one page"]
    return [f"{where}: no {name} on the head commit yet" for name in missing] + [
        f"{where}: `{name}` is {state} on the head commit"
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


def compared(base: str, head: str) -> set[str] | None:
    """The paths GitHub's compare of `base...head` changes, a rename by both names; None at the 300 files it lists.
    ponytail: one compare; read the commits' own files when a PR outgrows it."""
    out = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/compare/{base}...{head}",
        "--jq",
        "(.files | length), (.files[] | .filename, .previous_filename // empty)",
    ).splitlines()
    return None if int(out[0]) >= 300 else set(out[1:])


def touched_since(pull: dict[str, Any], reviewed: str) -> list[str] | None:
    """The files the PR changes, at `reviewed` or at its head, that the commits after `reviewed` change, sorted; None
    when GitHub can't say (a commit it no longer has, or more files than it lists)."""
    now = paths(pull)
    try:
        then = compared(pull["baseRefOid"], reviewed)
        later = compared(reviewed, pull["headRefOid"])
    except subprocess.CalledProcessError:
        return None
    if now is None or then is None or later is None:
        return None
    return sorted((then | set(now)) & later)


def required_checks(base: str) -> set[str]:
    """The checks the base branch requires, from its live rules: its rulesets' and its branch protection's."""
    rulesets = gh(
        "api",
        "--paginate",
        f"repos/{{owner}}/{{repo}}/rules/branches/{base}",
        "--jq",
        '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context',
    )
    protection = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/branches/{base}",
        "--jq",
        ".protection.required_status_checks.contexts // [] | .[]",
    )
    return set((rulesets + protection).split())


def auto_merge_allowed() -> bool:
    return gh("api", "repos/{owner}/{repo}", "--jq", ".allow_auto_merge").strip() == "true"


def tree(sha: str) -> dict[str, str] | None:
    """The mode of every path in commit `sha`'s tree, from GitHub's trees API; None when GitHub truncates it.
    ponytail: one recursive read, up to GitHub's 100,000 entries; read each touched directory when a repo outgrows it."""
    found = json.loads(gh("api", f"repos/{{owner}}/{{repo}}/git/trees/{sha}?recursive=1"))
    if found["truncated"]:
        return None
    return {entry["path"]: entry["mode"] for entry in found["tree"] if entry["type"] != "tree"}


def head_pushed(pull: dict[str, Any]) -> str | None:
    """When the head commit was last pushed to the PR's branch, from GitHub's repository activity (pushes, force
    pushes, the branch's creation); None when it lists none. ponytail: the newest 100 activities of a same-repo branch;
    page further, or read a fork's, when a PR here needs it."""
    out = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/activity?ref=refs/heads/{pull['headRefName']}&per_page=100",
        "--jq",
        f'[.[] | select(.after == "{pull["headRefOid"]}") | .timestamp] | first // ""',
    ).strip()
    return out or None


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
        raise Refused(f"{path}: {exc.strerror}") from exc


def toplevel() -> Path:
    """The checkout's root, so a run from a subdirectory reads the same files."""
    try:
        return Path(git("rev-parse", "--show-toplevel").strip())
    except subprocess.CalledProcessError as exc:
        raise Refused("not in a git checkout: run from the repo's checkout") from exc


def project() -> tuple[str | None, str | None]:
    """The checkout's docs/agents/issue-tracker.md and loop.md, None for one it lacks: a repo without the loop's
    files has no rules, and its issues no label shape."""
    root = toplevel()
    tracker, loop = (
        read(root / path) if (root / path).exists() else None for path in (TRACKER, LOOP)
    )
    return tracker, loop


def gated(
    point: str, pull: dict[str, Any], tracker: str | None, loop: str | None
) -> tuple[list[str], list[dict[str, Any]]]:
    """Every missing proof at `point`, and the issues the PR names (none for an exact revert)."""
    revert, found = reverts(pull)
    issues = [] if revert else closing_issues(pull)
    if not revert:
        found += problems(issues, None if tracker is None else label_names(tracker))
    return found + proofs(point, pull, issues, loop, revert), issues


def check(point: str, pr: int | None) -> int:
    tracker, loop = project()
    if pr is None and (pr := current_pr()) is None:
        print("no PR for this branch yet: nothing to gate")
        return 0
    pull = pull_request(pr)
    found, issues = gated(point, pull, tracker, loop)
    waiting = waits(pull, issues, loop) if point == "merge" else []
    for line in found + waiting:
        print(line)
    return 1 if found else WAITING if waiting else 0


def land(pr: int) -> int:
    """Every merge proof; a draft is then marked ready and waits (exit 3) for the CI that starts. A ready PR merges
    pinned to the head: at once when nothing waits, else auto-merge while only the base's required checks are pending
    and the repo allows it; exit 3 while anything else waits."""
    tracker, loop = project()
    pull = pull_request(pr)
    where, head = f"PR #{pr}", pull["headRefOid"]
    if pull["state"] == "MERGED":
        print(f"{where} is merged")
        return 0
    if pull["state"] != "OPEN":
        raise Refused(f"{where} is closed: nothing to land")
    found, issues = gated("merge", pull, tracker, loop)
    if found:  # never ready on a missing proof: ready starts CI and, with auto-merge, the merge
        for line in found:
            print(line)
        return 1
    if pull["isDraft"]:
        # CI skips a draft, and a skipped check counts as green: a draft's checks say nothing about the ready PR
        gh("pr", "ready", str(pr))
        print(f"{where} is ready now: CI starts on ready, run land again")
        return WAITING
    required = required_checks(pull["baseRefName"])
    checking, owner = ran(pull, loop, required), owner_waits(pull, issues, loop)
    # ponytail: no --delete-branch, which also deletes the local branch a worktree has checked out; the repo's
    # delete_branch_on_merge removes the remote one. Add it when a repo lacks that setting.
    merge = ["pr", "merge", str(pr), "--squash", "--match-head-commit", head]
    if not checking + owner:
        gh(*merge)
        print(f"{where} merges at {head}")
        return 0
    states = [state for _, state in head_checks(pull, required)[0]]
    pending = not owner and not no_ci(loop) and not RED.intersection(states)
    if pending and required and auto_merge_allowed():
        gh(*merge, "--auto")
        print(f"{where}: auto-merge on at {head}, once {', '.join(sorted(required))} pass")
        return 0
    for line in checking + owner:
        print(line)
    return WAITING


def approve(point: str, number: int, by: str) -> int:
    loop_rules = rules(project()[1] or "")
    issue = issue_node(number)
    holder = spec_holder(issue) if point == "spec" else headed(issue, "## Plan")
    if holder is None:
        raise Refused(f"#{number} has no `## Plan` comment to approve")
    value = version(holder)
    owner = owner_needed(point, loop_rules, names(issue))
    record = f"{point.capitalize()}: {value}\n"
    earlier = [
        (note, found)
        for note in notes(issue)
        if (found := parsed(note["body"], f"Approved: {point}")) is not None
    ]
    if any(found.get("by") == by and found.get(point) != value for _, found in earlier):
        record += CHANGED[point]
    comment(number, f"Approved: {point}\nBy: {by}\n{record}")
    # what this record supersedes: any earlier one but another approver's of the same version
    for note, found in earlier:
        superseded = found.get(point) != value or found.get("by") == by
        if superseded and not note.get("isMinimized") and note.get("viewerCanMinimize"):
            minimize(note["id"])
    # a person who already approved this spec or plan keeps their label when the loop resumes
    if (
        by == "coordinator" and owner and not current(issue, point, point, value, "owner")
    ):  # the label goes on last: a person adds it to approve
        label(number, f"approved:{point}", add=False)
        label(number, NEEDS_OWNER, add=True)
        print(
            f"a person must approve {point} too: {NEEDS_OWNER} added; stop until they add `approved:{point}`"
        )
        return 0
    label(number, f"approved:{point}", add=True)
    if by == "owner":
        label(number, NEEDS_OWNER, add=False)
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
    posting = commands.add_parser("verdict")
    posting.add_argument("pr", type=int)
    posting.add_argument("report", type=Path)
    recording = commands.add_parser("local-ci", aliases=["record-check"])
    recording.add_argument("pr", type=int)
    landing = commands.add_parser("land")
    landing.add_argument("pr", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return check(args.point, args.pr)
        if args.command == "approve":
            return approve(args.point, args.number, args.by)
        if args.command in ("local-ci", "record-check"):
            return local_ci(args.pr)
        if args.command == "land":
            return land(args.pr)
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
