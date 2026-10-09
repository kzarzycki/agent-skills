#!/usr/bin/env python3
"""Approvals (engineering-loop): every step leaves proof on GitHub, and this checks it before the loop moves on.

    python3 scripts/approvals.py check <build|merge> [pr]  # one line per missing proof, exit 1; waiting: exit 3
    python3 scripts/approvals.py land <pr>                  # every merge proof, then ready and merge; exit 0, 1 or 3
    python3 scripts/approvals.py approve <spec|plan> <issue> --by owner   # on the owner's word
    python3 scripts/approvals.py verdict <pr> <report>      # post a verifier report as a PR review
    python3 scripts/approvals.py local-ci <pr>              # with `CI: none`: run `mise run check:all` on the PR head
    python3 scripts/approvals.py release <issue>            # parked or dropped: remove the assignee the loop added

Run anywhere in the checkout: it reads docs/agents/ at the checkout's root. The project's `mise run loop:approvals
<point> [pr]` task runs `check`, and its `loop:land <pr>` task, where it has one, runs `land`; the loop and CI call
those tasks.

`check build` needs every issue the PR closes to be free of `needs-owner`, with exactly one category, a component and
exactly one size (a `wayfinder:` ticket needs only `approved:spec` and no `needs-owner`), and its spec approved: the
owner's current record and `approved:spec`, unless loop.md's `spec: auto unless risk` covers it (below). A `## Plan`
comment needs the same where a `plan:` rule asks, and is due with a `Plan:` line in loop.md § Practice. Category,
component and size names are the loop's fixed set plus docs/agents/issue-tracker.md's (`label_names`): a category is
`kind:<name>`, a component `area:<name>`, whether the tracker file and loop.md's conditions name it bare or in full.
`check build` also refuses an issue assigned to anyone but its approver (the person who last added `approved:spec`,
or for a spec the policy approves the account running this), since an assignee says whose the issue is. When every
build proof holds, it assigns each issue no one holds to its approver, comments a record that the loop did, and gives
the PR its issues' assignees, reporting a refusal and carrying on. `release` removes an assignee that record names,
unless someone assigned them again after it, and keeps every other: a claim a person made stays.
A repo without docs/agents/loop.md has no rules: each issue needs only `approved:spec` and no `needs-owner`, with no
approval record. Without docs/agents/issue-tracker.md no label's shape is checked.
`check merge` adds the PR's, whose absence fails (exit 1): the `## Evidence` section of its body; the verifier's PR
reviews, a review counting only when its body starts `Verifier (<family>), pass <n>` (same-family included) and the
PR's author or the account running this posted it, since anyone can review a public repo: every one on the newest
pass's commit says `SATISFIED: yes` with 0 blocker and 0 major (each family's highest pass there), every model family
that posted a verifier review has one on that commit, since a mixed PR needs both verifiers clear, and that commit is
the head itself, since every commit after a verdict needs one of its own; no unresolved
review thread; and no review whose latest state is `CHANGES_REQUESTED`. Then it waits (exit 3, one line per wait; the approvals workflow maps it to a `pending`
status) for the newest run of the aggregate `check` on the head to be green, the one check it reads (with the line
`CI: none` in loop.md, a `local-ci` pass on the head instead), and, while the change is high risk, for the owner's
`approved:merge` label on the PR, added after the head was pushed and still present. High risk is `risk:high` on the
PR or an issue it names, a risk rule matching (below), or a review at the cap or later that left a core finding open
(`cap`, SKILL.md § The cap); when the gate infers it, `check merge` and `land` add `risk:high` to the PR, reporting a
failure to add it and carrying on. A push removes the label (the
approvals workflow does it on `synchronize`), so the label never covers a head the owner did not see; the push time is
GitHub's repository activity for the head branch. No PR yet, or every proof held: exit 0.
`land` is the one way an agent merges. It runs every proof of `check merge` and refuses (exit 1) before touching the
PR when one fails. A draft it marks ready, which starts CI, and exits 3, since a draft's skipped checks say nothing
about the ready PR: run it again. On a ready PR it reads the checks the base requires (its rulesets and branch
protection; a base requiring none requires every check on the head green). With every required check
green and the label where the change is high risk: `gh pr merge --squash --match-head-commit <head>`, exit 0. While only
required checks are pending and the repo allows auto-merge, the same with `--auto`, so GitHub merges once they pass,
exit 0. Otherwise (a red check, the label, no auto-merge, `CI: none` without a record) exit 3: run it again. A
merged PR: exit 0; a closed one: exit 1.
`local-ci` runs only on a clean checkout at the PR head, and records nothing if the check fails or changes the tree.
`verdict` posts a report in verifier.md's format as one PR review (event COMMENT, since GitHub refuses the others on
one's own PR) on the commit its `Head:` line names, refusing a report without that line or its
`Verifier: <family>, pass <n>` line: one inline comment per finding, moved to the nearest line of the diff when its
line is outside it and saying so, and in the review's body when its file is outside the diff.

An exact revert skips the spec and the verdict: a PR whose body has a line `Reverts #<n>` (GitHub's Revert button writes
`Reverts <owner>/<repo>#<n>`), where #n is a merged PR and, file for file as GitHub's diff of each shows them, the PR
removes what #n added and adds what #n removed (files, and each run of lines in order; line numbers and context may
differ), and every path either touches has at the PR's merge base the mode it had after #n and at its head the mode
it had before #n, absence included. A file GitHub shows no diff of (binary, too large, only renamed or moded) is never
exact. Its code returns to a state already specced and reviewed, so `check build` passes it and `check merge` asks
only for Evidence (what went wrong), no unresolved thread or review requesting changes, a green `check` and the
label where the change is high risk.
A `Reverts #<n>` PR that is not exact gets a line saying why, then every proof of any PR.

A spec or plan approval is a person's: a comment `approve --by owner` writes on the owner's word, which the gate
reads, plus the `approved:<point>` label for the board. No agent writes one, since an agent approving its own work
is no approval:

    Approved: spec
    By: owner
    Spec: as edited 2026-10-02 14:35:27 UTC      (plan: Plan:)

A spec or plan is named by its last edit as GitHub shows it in the edit history (`as written <time>` before any), so
a person can open the version approved. Every approval is a new comment: a re-approval says the spec or plan
changed, and `approve` minimizes as outdated each earlier record, which it supersedes.

loop.md § Approvals holds the owner's standing policy, one `- <point>: <text>` line each. `spec: auto unless risk`
approves by policy, with no record or label, the spec of an issue that is a bug, carries a `Found while #<n>` line in
its body (a follow-up an agent raised), or is a native sub-issue of an epic with the owner's current spec record and
`approved:spec`, opened by an account GitHub's collaborator permission gives admin, maintain or write. A high-risk one
is still built; its merge waits for the owner. `merge: auto unless risk` says the gates are the merge approval of a
change that is not high risk, which also holds without the line. Each `risk: <condition>` line is a risk rule, and
so is each `merge:` line with a condition in place of a policy, until the project rewrites it, and each `spec:`
condition beside `spec: auto unless risk` (without that line the owner approves every spec, so it holds no merge). A
`plan: <condition>` line asks for the owner's plan approval. A `bot: <login> <condition>` line, such as
`bot: dependabot[bot] path uv.lock or path package-lock.json`, lets that bot's PR merge without a verifier review
when every commit is the bot's (authors, and a committer that is the bot or no account) and each file it
changes, none renamed or copied, matches the condition on its path (exempt); without one, every PR needs the
review. A condition the gate can read is `always`, `size:L`
(`size:L or larger`, `size:L+`), `component <name>`, `category <name>` or `path <glob>` (bare, or in backticks for a
glob with a space or comma), joined by `or`, judged on the labels of the PR and its issues and the PR's files; a risk
condition the gate can't read matches, since nothing else would enforce it. A `plan:` rule never reads a path, and
any other words make it the loop's alone, since a plan comes before the change. The spec is the issue
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
BUG, EPIC = "kind:bug", "epic"
CATEGORIES = {BUG, "kind:enhancement", "kind:chore", "kind:documentation"}
# a component's label is `area:<name>` and a category's `kind:<name>`; the docs name them bare or in full (qualified)
PREFIXES = {"component": "area:", "category": "kind:"}
SIZE_ORDER = ["size:XS", "size:S", "size:M", "size:L", "size:XL"]
SIZES = set(SIZE_ORDER)
TRACKER, LOOP = Path("docs/agents/issue-tracker.md"), Path("docs/agents/loop.md")
POINTS = ("spec", "plan")
MERGE_LABEL = "approved:merge"
# a change's consequences, not its urgency (that is `priority:`): set by a person or at triage, or by the gate
RISK_LABEL = "risk:high"
# the collaborator permissions that can write; GitHub's `permission` field reads `maintain` as `write`
WRITE = {"admin", "maintain", "write"}
# a follow-up an agent raised: SKILL.md § Triage puts this line on every issue an agent files
FOUND_WHILE = re.compile(r"^[ \t>*-]*Found while[ \t]+#\d+", re.MULTILINE | re.IGNORECASE)
# check merge's exit while it waits for `check` or the owner; argparse's usage error is 2
WAITING = 3
# a verifier pass's PR review starts with this; same-family included, as `Verifier (claude, same-family), pass 2`
PASS = re.compile(r"Verifier \((.+?)\), pass (\d+)")
# The cap, the last pass the loop runs on its own (a core finding open after it goes to the owner), is defined once:
# its default in SKILL.md § The cap, a project's own in a loop.md line `cap: <n>`.
CAP_DEFAULT = re.compile(r"^The cap is (\d+) passes\b", re.MULTILINE)
CAP_LINE = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?`?cap:[ \t]*(\d+)`?[ \t]*(?:\([^)\n]*\))?[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
# any line setting the cap, so one CAP_LINE can't read fails closed instead of falling back to the default
CAP_ANY = re.compile(r"^[ \t]*(?:[-*][ \t]+)?`?cap:", re.MULTILINE | re.IGNORECASE)
NOTE = "id body createdAt lastEditedAt isMinimized viewerCanMinimize"
SPECCED = f"number body createdAt lastEditedAt labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}"
ASSIGNEES = "assignees(first: 10) { nodes { login } }"
# who added `approved:spec` (approver) and who was assigned when (release); ponytail: the newest 100 such events
EVENTS = """timelineItems(last: 100, itemTypes: [LABELED_EVENT, ASSIGNED_EVENT]) { nodes { __typename
  ... on LabeledEvent { createdAt actor { __typename login } label { name } }
  ... on AssignedEvent { createdAt assignee { ... on User { login } ... on Bot { login } } } } }"""
# an issue with its author and its native parent (an epic), which spec_policy() reads, its assignees and events
ISSUE = f"{SPECCED} author {{ login }} parent {{ {SPECCED} }} {ASSIGNEES} {EVENTS}"
# the first line of the record claim() leaves when it assigns an issue, which release() reads
ASSIGNED = "Assigned: @"
PULL = f"""number author {{ __typename login }} {ASSIGNEES} state isDraft body baseRefName baseRefOid headRefName headRefOid baseRepository {{ nameWithOwner }} labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}
  files(first: 100) {{ totalCount nodes {{ path changeType }} }} latestReviews(first: 100) {{ nodes {{ state author {{ login }} }} }}
  reviews(last: 100) {{ totalCount nodes {{ author {{ login }} state body commit {{ oid }} }} }}
  reviewThreads(first: 100) {{ totalCount nodes {{ isResolved }} }}
  authored: commits(first: 100) {{ totalCount nodes {{ commit {{ authors(first: 5) {{ totalCount nodes {{ user {{ login }} }} }} committer {{ user {{ login }} }} }} }} }}
  timelineItems(last: 100, itemTypes: [LABELED_EVENT, READY_FOR_REVIEW_EVENT]) {{ nodes {{ __typename
    ... on LabeledEvent {{ createdAt label {{ name }} }} ... on ReadyForReviewEvent {{ createdAt }} }} }}
  commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ contexts(first: 100) {{ totalCount nodes {{
    __typename ... on CheckRun {{ name status conclusion startedAt completedAt checkSuite {{ workflowRun {{ workflow {{ name }} }} }} }}
    ... on StatusContext {{ context state createdAt targetUrl }} }} }} }} }} }} }}
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
    r"|\b(component|category):?[ \t]*`?([\w./:-]+)`?|\bpath:?[ \t]*(?:`([^`]+)`|([^\s`,;]+))",
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
# the commit status the project's approvals workflow posts; its target is the Actions run that posted it
APPROVALS = "loop:approvals"
RUN = re.compile(r"/actions/runs/(\d+)")


def named(body: str) -> list[int]:
    """The issue numbers a PR body names after a closing keyword or `Part of` on the same line, in order, each once."""
    return list(dict.fromkeys(int(number) for number in CLOSING.findall(QUOTED.sub("", body))))


def section(text: str, heading: str) -> str:
    """The text under `## <heading>`, up to the next `## ` heading; empty when there is none."""
    found = re.search(
        rf"^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE
    )
    return found.group(1) if found else ""


def items(tracker: str, heading: str) -> dict[str, str]:
    """The first backticked name of each list item under `## <heading>`, with the text after it (`**`, `:` and the
    surrounding space dropped)."""
    return {
        name: text.strip()
        for name, text in re.findall(
            r"^[ \t]*[-*] [^`\n]*`([^`\n]+)`\**:?[ \t]*(.*)$",
            section(tracker, heading),
            re.MULTILINE,
        )
    }


def listed(tracker: str, heading: str) -> set[str]:
    """The first backticked name of each list item under `## <heading>`."""
    return set(items(tracker, heading))


def qualified(kind: str, name: str) -> str:
    """A component's or category's label: `billing` and `area:billing` both name `area:billing`."""
    prefix = PREFIXES[kind.lower()]
    return prefix + name.removeprefix(prefix)


def label_names(tracker: str) -> dict[str, set[str]]:
    """The loop's label rule: each kind's names, the loop's fixed set plus docs/agents/issue-tracker.md's, a
    component as `area:<name>` and a category as `kind:<name>`."""
    return {
        "category": CATEGORIES
        | {qualified("category", name) for name in listed(tracker, "Extra categories")},
        "component": {qualified("component", name) for name in listed(tracker, "Components")},
        "size": SIZES,
    }


def rules(loop: str) -> list[tuple[str, str]]:
    """loop.md § Approvals as (point, condition) pairs: `spec`, `plan`, `merge`, `risk` and `bot`."""
    return re.findall(
        r"^[ \t]*[-*] +(spec|plan|merge|risk|bot):[ \t]*(.+?)[ \t]*$",
        section(loop, "Approvals"),
        re.MULTILINE,
    )


def is_policy(condition: str) -> bool:
    """Whether a `spec:` or `merge:` line's text is the policy `auto unless risk`, not a condition."""
    return condition.strip(" .`").lower() == "auto unless risk"


def policy(loop: str | None, point: str) -> bool:
    """Whether loop.md § Approvals has the line `<point>: auto unless risk`."""
    return any(rule == point and is_policy(text) for rule, text in rules(loop or ""))


def risk_rules(loop: str | None) -> list[str]:
    """loop.md's risk conditions: each `risk:` line, and each `merge:` line that is no policy line, read as a `risk:`
    rule until the project rewrites it. A `spec:` condition counts only beside `spec: auto unless risk`: without
    that line the owner approves every spec already, so a legacy `spec: always` holds no merge."""
    legacy = ("risk", "merge", "spec") if policy(loop, "spec") else ("risk", "merge")
    return [text for rule, text in rules(loop or "") if rule in legacy and not is_policy(text)]


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
        size, larger, kind, name, quoted, bare = found.groups()
        glob = quoted or bare
        if size:
            index = SIZE_ORDER.index("size:" + size[5:].upper())
            hit = bool(
                labels & set(SIZE_ORDER[index:] if larger else SIZE_ORDER[index : index + 1])
            )
        elif kind:
            hit = qualified(kind, name) in labels
        elif glob:
            unread |= paths is None
            hit = any(fnmatch.fnmatch(path, glob) for path in paths or [])
        else:
            hit = True  # always
        if hit:
            return True
    return None if unread else False


def exempt(pull: dict[str, Any], loop: str | None) -> bool:
    """Whether the PR needs no verifier review: its author is a bot a loop.md `bot: <login> <condition>` line names,
    and every file it changes matches that line's condition on its path alone (lock and manifest files). GitHub's
    GraphQL spells a bot's login without the `[bot]` REST and the line write, so both compare without it; a person
    can't hold a bot's login, so the author's type is checked too. Every commit's authors must be the bot, and its
    committer the bot or no account (GitHub's web-flow committer on the bot's own commits), since a person's push
    or rebase of its branch is a change no verifier saw. A renamed or copied file refuses it, since GraphQL
    gives only the new path, which may hide code moved onto a lock file's name. No line, more files or commits than the gate reads, or
    a condition it can't read: no exemption."""
    author, files = pull.get("author") or {}, paths(pull)
    renamed = any(
        file.get("changeType") in ("RENAMED", "COPIED") for file in pull["files"]["nodes"]
    )
    if author.get("__typename") != "Bot" or not files or renamed:
        return False
    login = (author.get("login") or "").removesuffix("[bot]").lower()
    commits = pull.get("authored") or {}
    nodes = commits.get("nodes") or []
    if not nodes or (commits.get("totalCount") or 0) > len(nodes):
        return False
    for node in nodes:
        authors = node["commit"]["authors"]
        logins = [((a.get("user") or {}).get("login") or "") for a in authors["nodes"]]
        if not logins or (authors.get("totalCount") or 0) > len(logins):
            return False
        committer = ((node["commit"].get("committer") or {}).get("user") or {}).get("login")
        if committer is not None:
            logins.append(committer)
        if any(name.removesuffix("[bot]").lower() != login for name in logins):
            return False
    lines = [text.partition(" ") for rule, text in rules(loop or "") if rule == "bot"]
    return any(
        name.strip("`").removesuffix("[bot]").lower() == login
        and all(matches(condition, set(), [path]) is True for path in files)
        for name, _, condition in lines
    )


def owner_needed(point: str, loop_rules: list[tuple[str, str]], labels: set[str]) -> bool:
    return any(matches(condition, labels, None) for rule, condition in loop_rules if rule == point)


def paths(pull: dict[str, Any]) -> list[str] | None:
    """The files the PR changes; None past the one page of 100 the gate reads."""
    files = pull["files"]
    found = [file["path"] for file in files["nodes"]]
    return None if (files.get("totalCount") or 0) > len(found) else found


def risk(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> str | None:
    """Why the change is high risk, or None: `risk:high` on the PR or an issue it names; a risk rule (risk_rules)
    matching the labels of the PR and its issues and the PR's files, where a condition the gate can't read matches,
    since nothing else would enforce it; or a review at the cap left a core finding open (capped)."""
    marked = [f"PR #{pull['number']}"] * (RISK_LABEL in names(pull)) + [
        f"#{issue['number']}" for issue in issues if RISK_LABEL in names(issue)
    ]
    if marked:
        return f"`{RISK_LABEL}` is on {', '.join(marked)}"
    labels = names(pull).union(*(names(issue) for issue in issues))
    for condition in risk_rules(loop):
        hit = matches(condition, labels, paths(pull))
        if hit:
            return f"it matches a risk rule ({condition})"
        if hit is None:
            return f"a risk rule the gate can't judge holds until a person does ({condition})"
    limit = cap(loop)
    if capped(pull, limit):
        return f"a verifier review at the cap (pass {limit}) or later left a core finding open, so the owner decides"
    return None


def flag(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> list[str]:
    """Add `risk:high` to a high-risk PR that lacks it, so the board shows why it waits; a line when GitHub refuses,
    never a failure, since the merge already waits for the owner either way."""
    if RISK_LABEL in names(pull) or risk(pull, issues, loop) is None:
        return []
    try:
        label(pull["number"], RISK_LABEL, add=True)
    except subprocess.CalledProcessError as exc:
        return [
            f"PR #{pull['number']}: could not add `{RISK_LABEL}` ({(exc.stderr or '').strip() or exc}): add it by hand"
        ]
    return []


def claim(pull: dict[str, Any], issues: list[dict[str, Any]]) -> list[str]:
    """Building starts: assign each issue no one holds to its spec's approver, with a record that the loop did
    (release reads it), and give the PR its issues' assignees. The record comes first, so a refused comment leaves no
    assignment release would read as a person's. A line when GitHub refuses, never a failure, since an assignee says
    who the issue belongs to and gates nothing past `check build`."""
    found, held = [], set()
    for issue in issues:
        number, owners = issue["number"], assignees(issue)
        if not owners and (login := approver(issue)):
            try:
                comment(number, f"{ASSIGNED}{login}\nBy: loop\nPR: #{pull['number']}\n")
            except subprocess.CalledProcessError as exc:
                found.append(
                    f"#{number}: did not assign @{login}: could not record the claim ({(exc.stderr or '').strip() or exc})"
                )
                continue
            try:
                assign(number, login, add=True)
            except subprocess.CalledProcessError as exc:
                found.append(
                    f"#{number}: could not assign @{login} ({(exc.stderr or '').strip() or exc})"
                )
                continue
            owners = {login}
        held |= owners
    for login in sorted(held - assignees(pull)):
        try:
            assign(pull["number"], login, add=True)
        except subprocess.CalledProcessError as exc:
            found.append(
                f"PR #{pull['number']}: could not assign @{login} ({(exc.stderr or '').strip() or exc})"
            )
    return found


def assigned_by_loop(issue: dict[str, Any], login: str) -> bool:
    """Whether the loop's claim() made `login` the issue's assignee: its record names them, and the loop's own
    assignment, the first of them at or after the record, is the last; a later one is a person claiming it again.
    ponytail: when the assignment itself was refused, a person's later assignment reads as the loop's; claim()
    reported that refusal, and removing the approver on parking is undone by assigning them again."""
    recorded = [
        note["createdAt"]
        for note in notes(issue)
        if note["body"].strip().split("\n", 1)[0].strip() == f"{ASSIGNED}{login}"
    ]
    if not recorded:
        return False
    later = [
        event
        for event in events(issue, "AssignedEvent")
        if ((event.get("assignee") or {}).get("login") == login)
        and (event.get("createdAt") or "") >= max(recorded)  # ISO 8601 in UTC, so it orders as text
    ]
    return len(later) <= 1


def release(number: int) -> int:
    """Parked or dropped: remove each assignee the loop added (assigned_by_loop), and keep a claim a person made."""
    issue = issue_node(number)
    for login in sorted(assignees(issue)):
        if assigned_by_loop(issue, login):
            assign(number, login, add=False)
            print(f"#{number}: removed @{login}, whom the loop assigned")
        else:
            print(f"#{number}: kept @{login}, whose claim it is")
    return 0


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
    """Whether `by` approved `point` for this spec or plan."""
    return any(
        record.get("by") == by and record.get(key) == value for record in records(node, point)
    )


def approvals(where: str, node: dict[str, Any], point: str, value: str) -> list[str]:
    """One line per approval `point` lacks on `node`: the owner's record of this version, and the label."""
    found = []
    if not current(node, point, point, value, "owner"):
        stale = any(record.get("by") == "owner" for record in records(node, point))
        found.append(
            f"{where} has no `Approved: {point}` record by the owner"
            + (f" for its current {point}: the owner approves it again" if stale else "")
        )
    if f"approved:{point}" not in names(node):
        found.append(f"{where} lacks the `approved:{point}` label")
    return found


def spec_policy(issue: dict[str, Any]) -> bool:
    """Whether `spec: auto unless risk` approves the issue's spec: a bug; a follow-up an agent raised (a
    `Found while #n` line in its body); or a native sub-issue of an epic with the owner's current spec record and
    `approved:spec`, opened by someone with write access. An epic is never covered: the owner approves it."""
    if EPIC in names(issue):
        return False
    if BUG in names(issue) or FOUND_WHILE.search(QUOTED.sub("", issue.get("body") or "")):
        return True
    parent = issue.get("parent")
    if not parent or READY not in names(parent):
        return False
    if not current(parent, "spec", "spec", version(spec_holder(parent)), "owner"):
        return False
    login = (issue.get("author") or {}).get("login")
    return bool(login) and writer(login)


def assignees(node: dict[str, Any]) -> set[str]:
    return {user["login"] for user in (node.get("assignees") or {}).get("nodes", [])}


def events(node: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """The node's timeline events of `kind` (`LabeledEvent`, `AssignedEvent`), oldest first."""
    found = [
        event
        for event in (node.get("timelineItems") or {}).get("nodes", [])
        if event.get("__typename") == kind
    ]
    return sorted(found, key=lambda event: event.get("createdAt") or "")


def approver(issue: dict[str, Any]) -> str | None:
    """Who approved the issue's spec: the person who last added `approved:spec`, or, for a spec loop.md's policy
    approves (no label), the account running the loop, whose policy it is. None for a bot, since an agent is never an
    assignee."""
    added = [
        event
        for event in events(issue, "LabeledEvent")
        if (event.get("label") or {}).get("name") == READY
    ]
    if not added:
        return viewer()
    actor = added[-1].get("actor") or {}
    return actor.get("login") if actor.get("__typename") == "User" else None


def others(issue: dict[str, Any]) -> str | None:
    """A line when the issue is assigned to anyone but its spec's approver: an assignee is who the issue belongs to,
    so the loop never builds someone else's. None when it is assigned to no one or to the approver alone."""
    held = assignees(issue)
    if not held:
        return None
    login = approver(issue)
    if held <= {login}:
        return None
    who = ", ".join(f"@{name}" for name in sorted(held))
    return (
        f"#{issue['number']} is assigned to {who}, not to its approver {f'@{login}' if login else '(a person)'}"
        " alone: someone else's issue is theirs, so the loop leaves it"
    )


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
    `approved:spec` label; with it, the owner's record and the label, unless `spec: auto unless risk` covers it
    (spec_policy). A plan needs them where a `plan:` rule asks. What the merge waits for is waits()'s."""
    loop_rules, found = rules(loop or ""), []
    auto = policy(loop, "spec")
    for issue in issues:
        labels = names(issue)
        if point == "build" and (line := others(issue)):
            found.append(line)
        if any(label.startswith("wayfinder:") for label in labels):
            continue
        where = f"#{issue['number']}"
        if loop is None:
            if READY not in labels:
                found.append(f"{where} lacks the `{READY}` label")
            continue
        if not (auto and spec_policy(issue)):
            found += approvals(where, issue, "spec", version(spec_holder(issue)))
        plan = headed(issue, "## Plan")
        if plan is not None:
            if owner_needed("plan", loop_rules, labels):
                found += approvals(where, issue, "plan", version(plan))
        elif practice_plans(loop):
            found.append(f"{where} has no `## Plan` comment, and one is due")
    if point != "merge":
        return found
    where = f"PR #{pull['number']}"
    evidence = section(pull["body"] or "", "Evidence")
    if not evidence.strip():
        found.append(f"{where}: its body has no `## Evidence` section with content")
    if revert is None and not exempt(pull, loop):
        found += reviewed(where, pull)
    threads = pull["reviewThreads"]
    if (threads.get("totalCount") or 0) > len(threads["nodes"]):
        found.append(
            f"{where} has more than {len(threads['nodes'])} review threads: the gate reads one page"
        )
    elif unresolved := sum(not thread["isResolved"] for thread in threads["nodes"]):
        found.append(
            f"{where}: {unresolved} review thread(s) unresolved: fix and reply, or triage, then resolve (github.md, Review trail)"
        )
    found += [
        f"{where}: {(review.get('author') or {}).get('login', 'a reviewer')} requested changes: answer the review"
        for review in pull["latestReviews"]["nodes"]
        if review["state"] == "CHANGES_REQUESTED"
    ]
    return found


def passes(pull: dict[str, Any]) -> list[tuple[str, int, dict[str, str], str]] | str:
    """The verifier's PR reviews in order, each as its commit, pass number, `VERDICT:`/`SATISFIED:` lines and model
    family (`claude` in `Verifier (claude, same-family), pass 2`): a body
    starting `Verifier (<family>), pass <n>`, by the PR's author or the account running this, since anyone can review
    a public repo. A string names why none can be read."""
    reviews = pull["reviews"]
    if (reviews.get("totalCount") or 0) > len(reviews["nodes"]):
        return f"has more than {len(reviews['nodes'])} reviews: the gate reads one page"
    found = [review for review in reviews["nodes"] if PASS.match(review.get("body") or "")]
    trusted = {(pull.get("author") or {}).get("login"), viewer() if found else None} - {None}
    return [
        (
            ((review.get("commit") or {}).get("oid") or "").lower(),
            int(PASS.match(review["body"])[2]),
            {
                key.strip(): value.strip()
                for key, _, value in (line.partition(":") for line in review["body"].splitlines())
                if key.strip() in ("VERDICT", "SATISFIED")
            },
            PASS.match(review["body"])[1].split(",")[0].strip().lower(),
        )
        for review in found
        if (review.get("author") or {}).get("login") in trusted
    ]


def counts(lines: dict[str, str]) -> tuple[int, int] | None:
    """A verdict's blocker and major counts; None when its `VERDICT:` line lacks one."""
    found = [
        re.search(rf"(\d+)\s+{kind}s?\b", lines.get("VERDICT", "")) for kind in ("blocker", "major")
    ]
    return None if None in found else (int(found[0][1]), int(found[1][1]))


def held(lines: dict[str, str]) -> bool:
    """Whether a verdict is satisfied with no blocker or major open."""
    return lines.get("SATISFIED", "").lower().split()[:1] == ["yes"] and counts(lines) == (0, 0)


def cap(loop: str | None) -> int:
    """The project's cap: its loop.md `cap: <n>` line (a note in parentheses may follow), else SKILL.md's default. A
    `cap:` line it can't read is refused, since falling back would hold nothing at the project's cap."""
    found = CAP_LINE.search(loop or "")
    if found is None and CAP_ANY.search(loop or ""):
        raise Refused("loop.md has a `cap:` line that is not `cap: <n>`: write it as `- cap: <n>`")
    skill = Path(__file__).resolve().parents[1] / "SKILL.md"
    found = found or CAP_DEFAULT.search(skill.read_text())
    if found is None:
        raise Refused("SKILL.md § The cap names no default (`The cap is <n> passes`)")
    return int(found[1])


def capped(pull: dict[str, Any], limit: int) -> bool:
    """Whether a verifier review at the cap (pass `limit`) or later left a blocker or major open, or was not
    satisfied: the owner then decides between a fix with one scoped pass more and leaving the code untouched."""
    found = passes(pull)
    return not isinstance(found, str) and any(
        number >= limit and not held(lines) for _, number, lines, _ in found
    )


def reviewed(where: str, pull: dict[str, Any]) -> list[str]:
    """One line per reason the verifier's PR reviews (passes) let nothing land: the newest pass is not on the head,
    since every commit after a verdict needs one of its own; a model family that reviewed the PR has no review on
    that commit, since a mixed PR needs both verifiers clear and one family's verdict says nothing of the other's
    finding; or on that commit a family's highest pass (a later pass on the same commit supersedes an earlier one)
    is not satisfied, or has a blocker or a major open. A triage or comment is no verdict. An allow-listed bot's lock- or manifest-only PR
    needs none (exempt)."""
    verdicts = passes(pull)
    if isinstance(verdicts, str):
        return [f"{where} {verdicts}"]
    if not verdicts:
        return [f"{where}: no verifier review posted (approvals.py verdict)"]
    head = verdicts[-1][0]
    same, missing = [], []
    for family in dict.fromkeys(family for *_, family in verdicts):
        mine = [(n, lines) for commit, n, lines, f in verdicts if f == family and commit == head]
        if not mine:
            missing.append(family)
            continue
        last = max(number for number, _ in mine)
        same += [lines for number, lines in mine if number == last]
    if not head or any(counts(lines) is None or "SATISFIED" not in lines for lines in same):
        return [
            f"{where}: a verifier review lacks its commit, or a `VERDICT:` or `SATISFIED:` line (approvals.py verdict)"
        ]
    found = [
        f"{where}: the {family} verifier reviewed this PR but not {head}: every family that reviewed needs a"
        " satisfied review on the head"
        for family in missing
    ]
    if pull["headRefOid"].lower() != head:
        found.append(
            f"{where}: the newest verifier review is on {head}, not on the head {pull['headRefOid']}:"
            " every commit after a verdict needs a verdict of its own"
        )
    if any(lines["SATISFIED"].lower().split()[:1] != ["yes"] for lines in same):
        found.append(f"{where}: a verifier review on {head} is not satisfied: fix and verify again")
    pairs = [pair for pair in map(counts, same) if pair is not None]
    blocker, major = sum(pair[0] for pair in pairs), sum(pair[1] for pair in pairs)
    if blocker or major:
        found.append(
            f"{where}: the verifier reviews on {head} have {blocker} blocker and {major} major open: fix and verify again"
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
    """A line while the change is high risk (risk) and the owner's `approved:merge` label is not on the PR, added
    after the head's push. `pushed(pull)` is when the head was pushed (default: GitHub's repository activity)."""
    where, found = f"PR #{pull['number']}", []
    why = risk(pull, issues, loop)
    if why is None:
        return found
    if MERGE_LABEL not in names(pull):
        return [
            f"{where} waits for the owner's `{MERGE_LABEL}` label, since it is high risk: {why}"
        ]
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
) -> tuple[list[tuple[str, str]], int | None, set[str]]:
    """The state of the newest run of each check on the head the merge reads, as (name, state): `required` (None:
    the aggregate `check`, the one check `check merge` reads, since every other check is advisory or the ruleset's;
    empty: every check); how many checks GitHub returned when it holds more than that one page, else None; and the
    names whose only run is a draft's skip, which the ready PR's CI has not reached yet."""
    commits = pull["commits"]["nodes"]
    contexts = commits[0]["commit"]["statusCheckRollup"] if commits else None
    every = contexts["contexts"]["nodes"] if contexts else []
    more = (
        len(every)
        if contexts and (contexts["contexts"].get("totalCount") or 0) > len(every)
        else None
    )
    wanted = {"check"} if required is None else required
    # CI skips a draft, and GitHub counts the skipped run as passing: one completed before the newest ready-for-review
    # is the draft's and says nothing about the ready PR. A run that completed on the draft is the head's result.
    ready = max(
        (
            event["createdAt"]
            for event in pull["timelineItems"]["nodes"]
            if event.get("__typename") == "ReadyForReviewEvent"
        ),
        default="",
    )
    # A rerun, or a run cancelled by a newer one in its concurrency group, leaves several runs of one check on the
    # head; only the newest says whether it is green. One job name in two workflows is two checks.
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    drafts: set[str] = set()
    for node in every:
        name = node.get("name") or node.get("context")
        if wanted and name not in wanted:
            continue
        if node.get("conclusion") == "SKIPPED" and (node.get("completedAt") or "") < ready:
            drafts.add(name)
            continue
        run = (node.get("checkSuite") or {}).get("workflowRun") or {}
        key = ((run.get("workflow") or {}).get("name", ""), name)
        if key not in newest or started(node) >= started(newest[key]):
            newest[key] = node
    checks = [
        (name, node.get("conclusion") or node.get("state") or node.get("status"))
        for (_, name), node in newest.items()
    ]
    return checks, more, drafts - {name for name, _ in checks}


def ci(where: str, pull: dict[str, Any], required: set[str] | None = None) -> list[str]:
    """A line per check head_checks() reads that is not green on the head, or not there yet."""
    checks, more, drafts = head_checks(pull, required)
    wanted = {"check"} if required is None else required
    if wanted:
        missing = [f"`{name}`" for name in sorted(wanted - {name for name, _ in checks})]
    else:  # every check of none would pass a head CI has not reached yet, or one only the draft skipped
        missing = [f"`{name}`" for name in sorted(drafts)] or ([] if checks else ["check"])
    if more is not None and (missing or not wanted):
        return [f"{where} has more than {more} CI checks: the gate reads one page"]
    # ponytail: a job that skips for another reason in a workflow without `ready_for_review` never reruns, so it waits
    # for good; the line names the cause. Bound the wait by time since ready if a project hits it.
    late = " since the PR went ready (its workflow may lack the `ready_for_review` type)"
    return [
        f"{where}: no {name} on the head commit yet{late if name.strip('`') in drafts else ''}"
        for name in missing
    ] + [
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


def assign(number: int, login: str, add: bool) -> None:
    """Add or remove an assignee of an issue or PR; GitHub ignores an absent one."""
    gh(
        "api",
        *(() if add else ("-X", "DELETE")),
        f"repos/{{owner}}/{{repo}}/issues/{number}/assignees",
        "-f",
        f"assignees[]={login}",
        "--silent",
    )


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


def viewer() -> str | None:
    """The login of the account `gh` runs as; None for a token `GET /user` refuses, such as a workflow's installation
    token (`github.token`), where the PR's author, the shared account, is the one trusted."""
    try:
        return gh("api", "user", "--jq", ".login").strip()
    except subprocess.CalledProcessError:
        return None


def writer(login: str) -> bool:
    """Whether `login` can write to the repo, by GitHub's collaborator permission; an account GitHub refuses to look
    up can't. ponytail: a bot's GraphQL login lacks the `[bot]` REST needs, so a bot author fails closed; add the
    suffix when a project's bot opens sub-issues."""
    try:
        permission = gh(
            "api",
            f"repos/{{owner}}/{{repo}}/collaborators/{login}/permission",
            "--jq",
            ".permission",
        )
    except subprocess.CalledProcessError:
        return False
    return permission.strip() in WRITE


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
    after = flag(pull, issues, loop) if point == "merge" else [] if found else claim(pull, issues)
    for line in found + waiting + after:
        print(line)
    return 1 if found else WAITING if waiting else 0


def land(pr: int) -> int:
    """Every merge proof; a draft is then marked ready and waits (exit 3) for the CI that starts. A ready PR merges
    pinned to the head: at once when nothing waits, else auto-merge while only the base's required checks are pending
    and the repo allows it; exit 3 while anything else waits. When a red `loop:approvals` status is all that
    waits, its Actions run is rerun: exit 3."""
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
    for line in flag(pull, issues, loop):
        print(line)
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
    checks = head_checks(pull, required)[0]  # ran() already waits for a draft-only skip
    # a required check not on the head yet may be a draft's skipped run, which GitHub's auto-merge counts as passing
    pending = (
        not owner
        and not no_ci(loop)
        and required <= {name for name, _ in checks}
        and not RED.intersection(state for _, state in checks)
    )
    if pending and required and auto_merge_allowed():
        gh(*merge, "--auto")
        print(f"{where}: auto-merge on at {head}, once {', '.join(sorted(required))} pass")
        return 0
    red = [(name, state) for name, state in checks if state not in GREEN]
    statuses = [
        node
        for node in pull["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"]
        if node.get("__typename") == "StatusContext" and node.get("context") == APPROVALS
    ]
    # Resolving a review thread starts no workflow, so the FAILURE the approvals workflow posted while one was open
    # stays on the head. When every proof holds and that status is all that waits, run its workflow again.
    if (
        statuses
        and not owner
        and not no_ci(loop)
        and required <= {name for name, _ in checks}
        and [name for name, _ in red] == [APPROVALS]
        and red[0][1] in RED
    ):
        stale = f"{where}: every proof holds but `{APPROVALS}` is {red[0][1]} on the head commit"
        found = RUN.search(max(statuses, key=started).get("targetUrl") or "")
        if found is None:
            print(
                f"{stale}, and the status names no Actions run to rerun:"
                " rerun the workflow that posts it, then run land again"
            )
            return WAITING
        # gh resolves the id in this checkout's repo; a target naming another repo's run, or one that is gone, fails
        try:
            run = json.loads(gh("run", "view", found[1], "--json", "status,url"))
        except subprocess.CalledProcessError:
            run = None
        if run is None or not RUN.search(run.get("url") or ""):
            print(
                f"{stale}, and its target names no Actions run of this repo:"
                " rerun the workflow that posts it, then run land again"
            )
            return WAITING
        if run.get("status") != "completed":
            print(
                f"{stale}: its run {found[1]} is {run.get('status')}, so the status is not posted yet; run land again"
            )
            return WAITING
        # ponytail: a status forged to name another workflow's run reruns that run; whoever can post statuses
        # can rerun runs anyway. Pin the context to the approvals app in the ruleset to close it.
        gh("run", "rerun", found[1])
        print(
            f"{stale}: reran run {found[1]}, since resolving a review thread starts no workflow; run land again"
        )
        return WAITING
    for line in checking + owner:
        print(line)
    return WAITING


def approve(point: str, number: int) -> int:
    """Record the owner's approval of the issue's current spec or plan, on their word: the record, the label, and
    `needs-owner` removed. Every earlier record of the point is superseded and minimized."""
    issue = issue_node(number)
    holder = spec_holder(issue) if point == "spec" else headed(issue, "## Plan")
    if holder is None:
        raise Refused(f"#{number} has no `## Plan` comment to approve")
    value = version(holder)
    record = f"{point.capitalize()}: {value}\n"
    earlier = [
        (note, found) for note in notes(issue) if (found := parsed(note["body"], point)) is not None
    ]
    if any(found.get("by") == "owner" and found.get(point) != value for _, found in earlier):
        record += CHANGED[point]
    comment(number, f"Approved: {point}\nBy: owner\n{record}")
    for note, _ in earlier:
        if not note.get("isMinimized") and note.get("viewerCanMinimize"):
            minimize(note["id"])
    label(number, f"approved:{point}", add=True)
    label(number, NEEDS_OWNER, add=False)
    return 0


# a report's finding heading: `### <id> (<severity>) <path>:<line>: <title>`, the line a number or a range `<n>-<m>`
FINDING = re.compile(
    r"###[ \t]+(\S+)[ \t]+\((blocker|major|minor)\)[ \t]+`?([^\s`]+?):(\d+(?:-\d+)?)`?:?[ \t]+(.+?)[ \t]*",
    re.IGNORECASE,
)


def findings(text: str, report: Path) -> list[tuple[str, str, str, str, str, str]]:
    """Each finding of a report as (id, severity, path, line, title, body): its body up to the next heading of
    levels 1 to 3 or the closing `Head:`/`VERDICT:`/`SATISFIED:` lines, outside a code fence. A `### ` heading that
    is no finding is refused, since the review would leave it out without a word."""
    found: list[tuple[str, str, str, str, str, list[str]]] = []
    body: list[str] | None = None  # the open finding's lines
    fenced = False
    for line in text.splitlines():
        if re.match(r"[ \t>]*(```|~~~)", line):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,3} |(Head|VERDICT|SATISFIED):", line):
            body = None
            if line.startswith("### "):
                heading = FINDING.fullmatch(line.rstrip())
                if not heading:
                    raise Refused(
                        f"{report}: can't read the finding heading `{line.strip()}`: write it "
                        "`### <id> (<blocker|major|minor>) <path>:<line>: <title>`"
                    )
                name, severity, path, at, title = heading.groups()
                body = []
                found.append((name, severity.lower(), path, at, title, body))
            continue
        if body is not None:
            body.append(line)
    return [(*finding[:5], "\n".join(finding[5]).strip()) for finding in found]


def diff_lines(base: str, head: str) -> dict[str, list[int]]:
    """The lines a review at `head` can comment on, per file: the new side of GitHub's diff of base...head (added and
    context lines). ponytail: one compare, up to the 300 files it lists."""
    out = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/compare/{base}...{head}",
        "--jq",
        ".files[] | {filename, patch}",
    )
    found: dict[str, list[int]] = {}
    for entry in (json.loads(line) for line in out.splitlines()):
        lines, number = found.setdefault(entry["filename"], []), 0
        for line in (entry.get("patch") or "").split("\n"):
            hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if hunk:
                number = int(hunk.group(1))
            elif line[:1] in (" ", "+"):
                lines.append(number)
                number += 1
    return found


def post_review(pr: int, review: dict[str, Any]) -> None:
    gh(
        "api",
        f"repos/{{owner}}/{{repo}}/pulls/{pr}/reviews",
        "--input",
        "-",
        "--silent",
        data=json.dumps(review),
    )


def verdict(pr: int, report: Path) -> int:
    """Post a verifier report as a PR review on the commit it reviewed: one inline comment per finding, at the nearest
    line of the diff when its line is outside it, in the review's body when its file is."""
    text = read(report)
    lines = [line.strip() for line in text.splitlines()]
    verdicts = [line for line in lines if line.startswith("VERDICT:")]
    satisfied = [line for line in lines if line.startswith("SATISFIED:")]
    if not satisfied or not verdicts:
        raise Refused(f"{report} has no `VERDICT:` or `SATISFIED:` line: the report is unfinished")
    # the head the verifier reviewed, which a push since the review may have moved the PR's head past
    heads = [
        found[1] for line in lines if (found := re.fullmatch(r"Head:[ \t]*([0-9a-fA-F]{40})", line))
    ]
    if not heads:
        raise Refused(f"{report} has no `Head: <sha>` line naming the full commit it reviewed")
    passes = [
        found
        for line in lines
        if (found := re.fullmatch(r"Verifier:[ \t]*(.+),[ \t]*pass[ \t]+(\d+)", line))
    ]
    if not passes:
        raise Refused(f"{report} has no `Verifier: <family>, pass <n>` line")
    head, (family, number) = heads[-1].lower(), passes[-1].groups()
    heading = f"Verifier ({family}), pass {number}"
    diff = diff_lines(pull_request(pr)["baseRefOid"], head)
    comments, outside = [], []
    for name, severity, path, line, title, body in findings(text, report):
        said = f"**{heading} · {name}** ({severity}): {title}"
        if not diff.get(path):
            outside.append(f"- {said}, at `{path}:{line}`, a file outside the diff\n\n{body}")
            continue
        last = int(line.rpartition("-")[2])  # a range anchors at its last line
        at = min(diff[path], key=lambda candidate: abs(candidate - last))
        moved = (
            f"At `{path}:{line}`, outside the diff: placed at the nearest diff line.\n\n"
            if at != last
            else ""
        )
        comments.append(
            {"path": path, "line": at, "side": "RIGHT", "body": f"{said}\n\n{moved}{body}"}
        )
    summary = "\n\n".join(
        [f"{heading} on {head[:7]}.", *outside, f"{verdicts[-1]}\n{satisfied[-1]}"]
    )
    post_review(
        pr, {"commit_id": head, "event": "COMMENT", "body": summary + "\n", "comments": comments}
    )
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
    # an agent never approves: a record is a person's word, and the owner's policy in loop.md covers the rest
    approving.add_argument("--by", choices=("owner",), required=True)
    posting = commands.add_parser("verdict")
    posting.add_argument("pr", type=int)
    posting.add_argument("report", type=Path)
    recording = commands.add_parser("local-ci")
    recording.add_argument("pr", type=int)
    landing = commands.add_parser("land")
    landing.add_argument("pr", type=int)
    releasing = commands.add_parser("release")
    releasing.add_argument("issue", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return check(args.point, args.pr)
        if args.command == "approve":
            return approve(args.point, args.number)
        if args.command == "local-ci":
            return local_ci(args.pr)
        if args.command == "land":
            return land(args.pr)
        if args.command == "release":
            return release(args.issue)
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
