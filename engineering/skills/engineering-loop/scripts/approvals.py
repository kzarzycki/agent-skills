#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Approvals (engineering-loop): every step leaves proof on GitHub, and this checks it before the loop moves on.

    uv run scripts/approvals.py check <build|merge> [pr]  # one line per missing proof, exit 1; waiting: exit 3
    uv run scripts/approvals.py check build --issue <n>   # before the PR exists: the issue's build proofs; exit 0 or 1
    uv run scripts/approvals.py check queue <pr> --head <sha>  # may that head enter a batching merge queue; exit 0 or 1
    uv run scripts/approvals.py batch <pr> --merge <sha> --batch <sha> --exit <n> --log <path>  # the queue's proof
    uv run scripts/approvals.py land <pr> [--wait]         # every merge proof, then ready and merge; exit 0, 1 or 3
    uv run scripts/approvals.py approve <spec|plan> <issue> --by owner   # on the owner's word
    uv run scripts/approvals.py delegate <pr>              # the delegated approver's approved:merge, feature branch only
    uv run scripts/approvals.py verdict <pr> <report>      # post a verifier report as a PR review
    uv run scripts/approvals.py report <report>            # check a verifier report as verdict reads it; posts nothing
    uv run scripts/approvals.py brief <pr> [--priorities <file>] [--proof <log>]...  # a verifier pass's brief
    uv run scripts/approvals.py local-ci <pr>              # with `ci: false`: run `mise run check:all` on the PR head
    uv run scripts/approvals.py local-ci --record          # the same on HEAD before review; `local-ci <pr>` reuses it
    uv run scripts/approvals.py release <issue>            # parked or dropped: remove the assignee the loop added

Run anywhere in the checkout: it reads docs/agents/ at the checkout's root. The project's `mise run loop:approvals
<point> [pr]` task runs `check`, and its `loop:land <pr>` task, where it has one, runs `land`; the loop and CI call
those tasks.

`check build` needs every issue the PR closes to be free of `needs-owner`, with exactly one category, a component and
exactly one size (a `wayfinder:` ticket needs only `approved:spec` and no `needs-owner`), and its spec approved: the
owner's current record and `approved:spec`, unless loop.md's `spec.auto` covers it
(below). A `## Plan` comment needs the same where the `plan` rule asks, and is due when loop.md's `practice` names a
`plan` skill. Category, component and size names are the loop's fixed set plus docs/agents/issue-tracker.md's
(`label_names`): a category is `kind:<name>`, a component `area:<name>`, whether the tracker file names it bare or in
full.
`check build` also refuses an issue assigned to anyone but its approver (the person who last added `approved:spec`,
or for a spec the policy approves the account running this), since an assignee says whose the issue is. When every
build proof holds, it assigns each issue no one holds to its approver, comments a record that the loop did, and gives
the PR its issues' assignees, reporting a refusal and carrying on. `release` removes an assignee that record names,
unless someone assigned them again after it, and keeps every other: a claim a person made stays.
A repo without docs/agents/loop.md has no rules: each issue needs only `approved:spec` and no `needs-owner`, with no
approval record. Without docs/agents/issue-tracker.md no label's shape is checked.
`check merge` adds the PR's, whose absence fails (exit 1): the `## Evidence` section of its body; the keyword linking
each issue, where loop.md has a `signoff` rule (below); the verifier's PR
reviews, a review counting only when its body starts `Verifier (<family>), pass <n>` (same-family included) and the
PR's author, the account running this or an account that can write to the repo posted it, since anyone can review a
public repo: every one on the newest
pass's commit says `SATISFIED: yes` with 0 blocker and 0 major, and that commit is the head itself, since every
commit after a verdict needs one of its own; no unresolved
review thread; and no review whose latest state is `CHANGES_REQUESTED`. Then it waits (exit 3, one line per wait; the approvals workflow maps it to a `pending`
status) for the newest run of each check the base branch requires, as `land` reads them, to be green on the head, or
of the aggregate `check` when it requires none (with
`ci: false` in loop.md, a `local-ci` pass on the head, its comment by the PR's author, the account running this or a
writer, instead), and, while the change is high risk, for the owner's
`approved:merge` label on the PR, added after the head was pushed and still present. High risk is `risk:high` on the
PR or an issue it names, a risk rule matching (below) unless under `spec.auto: true`, or a review at the cap or later not satisfied or
with a blocker or major open (`cap`, SKILL.md § The cap); when the gate infers it, `check merge` and `land` add `risk:high` to the PR, reporting a
failure to add it and carrying on. A push removes the label (the
approvals workflow does it on `synchronize`), so the label never covers a head the owner did not see; the push time is
GitHub's repository activity for the head branch. On a PR into a feature branch (any base but the repository's
default branch) the label may be the delegated approver's: `delegate <pr>` adds it, then a record (`Approved: merge`,
`By: delegate`), and refuses a PR into the default branch. There a label no newer than such a record is no approval,
since only the owner approves a merge to the default branch; and a PR from a branch into the default branch is high
risk while any PR merged into that branch carries `risk:high`, so a feature branch's merge waits for the owner.
Every proof held: exit 0. Before the PR exists, `check build` judges the issue `--issue <n>` names, else the one
the branch's name starts a segment with (`loop/329-fix`), the same way, and claims nothing; with neither it exits 1,
since a build needs an approved spec. `check merge` with no PR yet: exit 0.
With `opt_out: true` in loop.md, a person may keep their PRs out of the loop: `check merge` on a PR that
left no loop trail (no verifier review, no `Approved: spec` record or `approved:spec` on an issue it links, no
`Reverts #<n>` line, not an exempt bot PR) prints that it is outside the loop and exits 0, so the approvals
workflow posts success and its author merges it their usual way; `land` prints the same line and exits 1, so the
loop never merges it or turns auto-merge on for it. Risk rules and `risk:high` hold no such PR. `check build` is
unchanged. A spec a policy covers is no trail, since under `spec.auto: true` every issue is covered.
`land` is the one way an agent merges. It runs every proof of `check merge` and refuses (exit 1) before touching the
PR when one fails, or when GitHub's merge state says the head is behind a base that requires it up to date
(`BEHIND`) or conflicts with it (`DIRTY`): merge the base in, rerun the gates and get a verdict on the merge. While
GitHub has not computed that state yet (`UNKNOWN`) it neither marks ready nor merges: exit 3, run it again. A draft
it marks ready, which starts CI, and exits 3, since a draft's skipped checks say nothing about the ready PR: run it again. On a ready PR it reads the checks the base requires (its rulesets and branch
protection; a base requiring none requires every check on the head green). A private repo on GitHub's free plan
has neither, nor auto-merge: GitHub's 403 on its rules reads as none required, and `land` says GitHub enforces nothing
there, so its proofs are the only gate. With every required check
green and the label where the change is high risk: `gh pr merge --squash --match-head-commit <head>`, exit 0. While only
required checks are pending and the repo allows auto-merge, the same with `--auto`, so GitHub merges once they pass,
exit 0. Otherwise (a red check, the label, no auto-merge, `ci: false` without a record) exit 3: run it again. A
merged PR: exit 0; a closed one: exit 1.
With loop.md's `land` section (`signed_squash_to: <branch>`, `allowed_signers: <path>`), for a repo that trusts only
commits signed by its maintainers' keys (GitHub signs its own squash with GitHub's key), the same proofs and waits
hold, but where `land` would merge it squashes the PR in this checkout instead: one commit with the head's tree on the
base's tip, titled `<PR title> (#<pr>)`, signed with the checkout's SSH key (`gpg.format ssh`, `user.signingkey`) and
checked with `git verify-commit` against the allowed signers file. It pushes that commit to the PR's branch, pinned to
the head the gates checked, then fast-forwards the base to it, so GitHub shows the PR merged; exit 0. A base push
refused (the base moved meanwhile) puts the PR's branch back on its head, exit 1. It never turns
auto-merge on, since GitHub would sign that squash, and waits (exit 3) while checks are pending. It refuses (exit 1),
before touching the PR, a PR from another repository (its branch isn't ours to push), a base other than the section's,
auto-merge or the merge queue on, an `origin` that isn't the PR's repo, a checkout that signs nothing, or a missing
signers file; and at the merge a head that moved, a head that doesn't contain the base's tip (merge it in) and a
signature the file doesn't allow. Without the section nothing changes.
`land --wait` runs it again every 30 seconds, printing each new state, while what waits is GitHub's merge state or CI
on the head: a draft it marked ready, a required check pending with none red (with or without the label), or a `loop:approvals` run it reran,
once. With auto-merge on or the PR in a merge queue, whoever put it there, and after its own merge, which a base
requiring a merge queue queues, it waits for GitHub's merge (exit 0 only once the PR is merged) unless the owner's
label or a local-ci record holds it, which GitHub never supplies; auto-merge turned off, or the PR out of the queue,
without a merge is exit 1, and a red required check exit 3. Whatever CI won't clear exits 3 as without `--wait`, so the owner is asked only about
a head CI has passed, and so does a wait of 2 hours.
`local-ci` runs only on a clean checkout at the PR head, and records nothing if the check fails or changes the tree.
A pass also leaves a record keyed by commit under the git common dir (`approvals/local-ci/<sha>.json`: head, command,
exit, env, time, host), which every worktree sees and nothing commits; `local-ci --record` makes one on HEAD with no PR.
`env` holds the value, or null for unset, of each variable loop.md's `local_ci_env` names, since a
check that reads them may run a different tier under each. When the record for the PR's exact head holds exit 0, the
same command and the same env, `local-ci <pr>` posts the pass from it, naming its time, instead of running the
check again; a record without env is never reused. The host stays in the record: nothing `approvals.py` posts names
it, and posted text writes the home directory `~` (public), since a public board would show both. The posted comment names the env it ran under (`Env: A=1 B=x`, unset
names left out, or `Env: default`).
A project may land through a batching merge queue of its own (merge every waiting PR's head onto the base, run the
full gate once on the result, push the batch) instead of one `land` per PR. `check queue <pr> --head <sha>` exits 0
when that head may enter it: it is the PR's head, every proof of `check merge` holds but the CI wait, which the queue's
gate on the batch replaces, the head has its own `local-ci --record` pass under the current env (which `batch` needs) and,
with CI, the checks `check merge` waits for passed, and the change is not high risk and has no `approved:merge`, since the
owner's label covers one head landing alone: such a PR lands through `land`. After its gate the queue posts `batch` on
each PR it merged: a comment `Merge queue batch` naming the head, the PR's merge commit, the batch commit, the gate's
exit, the env and time of the head's own `local-ci --record` pass, and the log and its last lines; `batch` refuses a
head with no such pass under the current env. `check merge` takes that comment in place of the CI wait (either kind)
once it holds: the exit is 0, the head has its own green `local-ci --record` pass under the current env and the env
the comment names, since a batch gate never stands in for the head's, the merge commit's second parent is the head
(the head landed unchanged), its tree is what
`git merge-tree` makes of its parents (the queue resolved no conflict and added nothing), and the batch commit
contains it; a commit the checkout lacks is fetched from `origin` first. Only a comment by the account running this
or a writer counts, since anyone can comment on a public repo. A red, unproven or missing batch leaves the wait
exactly as it was: it adds no line of its own, so a PR evicted through another PR's red batch lands or re-queues at
the same head like any other. The proof is the verifier's
verdict and gate on the PR's own head plus the full gate on the batch that merged it.
With loop.md's `carry_over_main` section (`except: <globs>`), a merge of the base into a PR head H keeps H's proofs: a
head H' whose first parent is H, whose second is on the base (an ancestor of its tip), whose tree is what `git
merge-tree --write-tree` makes of the two (no conflict resolved, nothing added), and where the base's changes since
the merge base touch no file H's side changes and no path an `except` glob matches (fnmatch, as a rule's `paths`:
the project's merge-check configuration, such as lint, type, test and gate config and lockfiles). Then H's newest
verdict covers H' (`check merge` and `land`, the verifier's `Risk:` line included). It never carries a `local-ci`
record: H' runs its own gate, as CI would run on it. `check merge` and `land` print one line naming H, H' and the
predicate, or why the head carries nothing. A git error, a second merge base or any failed condition carries
nothing: the head needs its own verdict, as without the section, where `check merge` and `land` read no git for it.
`verdict` posts a report in verifier.md's format as one PR review (event COMMENT, since GitHub refuses the others on
one's own PR) on the commit its `Head:` line names, carrying any text after the pass number on its `Verifier:` line
(a qualifier, such as why the verifier shares the author's family) into the review's first line, refusing a report without that line or its
`Verifier: <family>, pass <n>` line or its `Risk:` line, a `### ` heading with a `(<severity>)` it can't read as a finding, or finding
headings that don't add up to the `VERDICT:` counts (any other `### ` heading is a sub-heading and posts nothing): one
inline comment per finding, moved to the nearest line of the diff when its
line is outside it and saying so, and in the review's body when its file is outside the diff.

An exact revert skips the spec and the verdict: a PR whose body has a line `Reverts #<n>` (GitHub's Revert button writes
`Reverts <owner>/<repo>#<n>`), where #n is a merged PR and, file for file as GitHub's diff of each shows them, the PR
removes what #n added and adds what #n removed (files, and each run of lines in order; line numbers and context may
differ), and every path either touches has at the PR's merge base the mode it had after #n and at its head the mode
it had before #n, absence included. A file GitHub shows no diff of (binary, too large, only renamed or moded) is never
exact. Its code returns to a state already specced and reviewed, so `check build` passes it and `check merge` asks
only for Evidence (what went wrong), no unresolved thread or review requesting changes, a green `check` and the
label where the change is high risk, which for a revert also means `risk:high` on an issue it names or on #n, or #n's
last verdict judging it high, since undoing a high-risk change changes as much as making it.
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

loop.md's settings block (SKILL.md § Settings), YAML, holds the owner's standing policy, checked against SCHEMA: a
section or key it doesn't know or a value of the wrong type is refused, naming the key, and so is a loop.md without
the block. `loop` holds `cap`, `ci`, `opt_out` and `local_ci_env`; `spec` holds `auto`.
`spec.auto` as a list approves by policy, with no record or label, the spec of an issue of each kind it names:
`bug`, labelled a bug; `follow-up`, carrying a `Found while #<n>` line in its body (a follow-up an agent raised);
`sub-issue`, a native sub-issue of an epic with the owner's current spec record and `approved:spec`, opened by an
account GitHub's collaborator permission gives admin, maintain or write. A high-risk one is still built; its merge
waits for the owner. `spec.auto: true` approves every spec the same
way, epics included, except one the risk rule matches on the labels of the issue and the PR and the PR's files (at
`check build` the files pushed so far), or one opened by an account without write access: those need the owner's
record and label, and `check` says why. Under `spec.auto: true` the risk rule holds the spec instead of the merge, since
the owner approved the change before it was built; `risk:high` and the cap still hold the merge. Without `auto`, or
with `false` or an empty list, the owner approves every spec, and the gates are the merge approval of a change that is not high risk.

A rule (`risk`, `plan`, `signoff`) is a section of terms, any one of which matches: `always: true`; `labels`,
label names matched exactly on the PR and its issues; `paths`, globs matched on the PR's files; and in `risk` alone
`verifier: true`. A list holds strings. The gate reads the keys, never the words of a rule, so a path or
label can never read as a term. Paths it can't judge, past the one page of files it reads, hold. The `plan` rule asks
for the owner's plan approval, and has no `paths`, since a plan comes before the change. A `bot.<login>` section,
such as `bot.dependabot[bot]` with `paths` uv.lock and **/package.json, lets that bot's PR merge without a verifier
review when every commit is the bot's (authors, and a committer that is the bot or no account) and each file it changes, none renamed or copied,
matches one of its paths (exempt); with `branch: renovate/` it names an updater opening PRs under a person's token by
its head branch instead, and a `verify` label refuses either; without one, every PR needs the review. The `signoff` rule says whose change the
owner signs off in use after it lands: `check merge` needs the PR to link each issue it matches, or whose spec has a
line `Sign-off: owner`, with `Implements #<n>`, which leaves it open for the sign-off, and every other issue with a
closing keyword (`Part of` suits both); without a `signoff` section no keyword is checked and `Implements` is a link like
`Part of`. `verifier` holds at the merge (under `spec.auto: true` too, since the verdict comes after the build) when the
verifier judges the change high: the highest pass on the head, by a trusted account (passes), says `Risk: high`, any
word but `low`, or has no `Risk:` line, and the hold quotes it. A head no review covers waits for its review instead; a
PR that needs none (exempt, an exact revert) has no judgment. A `risk:high` the gate added for that term comes with a
comment saying so, and the gate takes the label off once a later pass says `Risk: low`, unless it was added again
after that comment, which is a raise only the owner lowers. Paths in the same rule hold whatever the verifier says.
The spec is the issue body, or its last comment whose first line is `## Spec`, where a tool owns the body. A soft gate against a forgotten step, not a security boundary: the agent holds the same
credentials as the person. issue-tracker.md's components and extra categories are the keys of its settings block's
`components` and `categories` (tracker_settings). Reads and writes through `gh`. Stdlib, and PyYAML for the settings
block (SKILL.md § Settings says how it is delivered).
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import io
import itertools
import json
import os
import re
import socket
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # run as `python3 approvals.py` where PyYAML isn't installed
    sys.exit(
        f"{Path(sys.argv[0]).name} needs PyYAML: run it with `uv run {sys.argv[0]}`, which installs it"
    )

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
# the `By:` of the delegated approver's merge record (delegate), which owner_waits refuses on the default branch
DELEGATE = "delegate"
MERGE_LABEL = "approved:merge"
# a change's consequences, not its urgency (that is the tracker's priority): set by a person or at triage, or by the gate
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
# its default in SKILL.md § The cap, a project's own in loop.md's `cap` setting.
CAP_DEFAULT = re.compile(r"^The cap is (\d+) passes\b", re.MULTILINE)
NOTE = "id author { login } body createdAt lastEditedAt isMinimized viewerCanMinimize"
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
PULL = f"""id number title isCrossRepository author {{ __typename login }} {ASSIGNEES} state isDraft mergeStateStatus autoMergeRequest {{ enabledAt }} isInMergeQueue mergeQueueEntry {{ state enqueuedAt headCommit {{ checkSuites {{ totalCount }} }} }} body baseRefName baseRefOid headRefName headRefOid baseRepository {{ nameWithOwner defaultBranchRef {{ name }} }} labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}
  files(first: 100) {{ totalCount nodes {{ path changeType }} }} latestReviews(first: 100) {{ nodes {{ state author {{ login }} }} }}
  reviews(last: 100) {{ totalCount nodes {{ author {{ login }} state body commit {{ oid }} }} }}
  reviewThreads(first: 100) {{ totalCount nodes {{ isResolved }} }}
  authored: commits(first: 100) {{ totalCount nodes {{ commit {{ authors(first: 5) {{ totalCount nodes {{ user {{ login }} }} }} committer {{ user {{ login }} }} }} }} }}
  timelineItems(last: 100, itemTypes: [LABELED_EVENT, READY_FOR_REVIEW_EVENT]) {{ nodes {{ __typename
    ... on LabeledEvent {{ createdAt label {{ name }} }} ... on ReadyForReviewEvent {{ createdAt }} }} }}
  commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ contexts(first: 100) {{ totalCount nodes {{
    __typename ... on CheckRun {{ name status conclusion startedAt completedAt checkSuite {{ status workflowRun {{ workflow {{ name }} }} }} }}
    ... on StatusContext {{ context state createdAt targetUrl }} }} }} }} }} }} }}
  closingIssuesReferences(first: 50) {{ nodes {{ {ISSUE} }} }}"""
# GitHub's closing keywords, plus two links that leave the issue open: `Part of` for a spec the PR builds on but
# leaves unfinished, and `Implements` for one the owner signs off after landing (`signoff`). ponytail: same-repo `#n`
# only, add owner/repo#n and issue URLs when a PR here uses one.
CLOSING = re.compile(
    r"\b(?:(close[sd]?|fix(?:e[sd])?|resolve[sd]?)|(part[ \t]+of)|(implements)):?[ \t]+#(\d+)\b",
    re.IGNORECASE,
)
# a link's kind, in the order one wins when a body names an issue twice: GitHub closes on any closing keyword
CLOSES, IMPLEMENTS, PART = "closes", "implements", "part of"
# the spec's sign-off record, as a line of its own: `Sign-off: owner` or `Sign-off: none`
SIGNOFF = re.compile(
    r"^[ \t>*-]*\**Sign-off\**:?\**[ \t]*`?(owner|none)\b", re.MULTILINE | re.IGNORECASE
)
# code and comments: an example, not a closing line
QUOTED = re.compile(r"^[ \t>]*```.*?^[ \t>]*```|`[^`\n]*`|<!--.*?-->", re.DOTALL | re.MULTILINE)
# the first line of the comment flag() leaves when the verifier's `Risk:` line made it add `risk:high`, which says the
# label is the gate's to take off again when a later pass judges the risk low
FLAGGED = f"`{RISK_LABEL}` added by the gate"
# a revert's line, as GitHub's Revert button writes it or by hand; ponytail: one revert per PR, the first line counts.
REVERTS = re.compile(r"^[ \t]*Reverts[ \t]+([\w.-]+/[\w.-]+)?#(\d+)\b", re.MULTILINE)
CHECKED = "Local check passed"
# the first line of a merge queue's batch proof (batch), which queued() reads, and how much of the gate's log it shows
BATCHED = "Merge queue batch"
LOG_TAIL = 30
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
# land --wait: seconds between reads of the PR, and how long it waits in all before it exits 3
POLL, CEILING = 30, 2 * 60 * 60
# what land --wait polls for: CI on the head, GitHub's auto-merge, or its merge state
ON_CI, ON_MERGE = "CI on the head", "GitHub to merge it (auto-merge or the merge queue)"
ON_STATE = "GitHub to compute its merge state"
# GitHub sometimes builds a merge-group commit and never tells Actions: the entry then waits for the queue's own check
# timeout. ponytail: a fixed 10 minutes with no check suite; a loop.md setting if a project's CI is slower to start.
STUCK = 10 * 60
DEQUEUE = "mutation($id: ID!) { dequeuePullRequest(input: {id: $id}) { clientMutationId } }"
# GitHub's merge states that no wait clears: the head is behind a base that requires it up to date, or conflicts
STALE_BASE = {"BEHIND": "is behind", "DIRTY": "conflicts with"}
# how ci() ends its refusal of a head with more checks than the one page it reads, which no CI run clears
PAGED = "CI checks: the gate reads one page"


def links(body: str) -> dict[int, str]:
    """The issues a PR body names after a closing keyword, `Part of` or `Implements` on the same line, in order, each
    once, with the link's kind (CLOSES, PART, IMPLEMENTS); a closing keyword wins over the others, since GitHub closes
    the issue on it whatever else the body says, and `Implements` over `Part of`."""
    found: dict[int, str] = {}
    rank = (CLOSES, IMPLEMENTS, PART)
    for closes, part, implements, number in CLOSING.findall(QUOTED.sub("", body)):
        kind = CLOSES if closes else IMPLEMENTS if implements else PART
        previous = found.setdefault(int(number), kind)
        found[int(number)] = min(previous, kind, key=rank.index)
    return found


def named(body: str) -> list[int]:
    """The issue numbers a PR body links (links), in order, each once."""
    return list(links(body))


def section(text: str, heading: str) -> str:
    """The text under `## <heading>`, up to the next `## ` heading; empty when there is none."""
    found = re.search(
        rf"^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE
    )
    return found.group(1) if found else ""


def qualified(kind: str, name: str) -> str:
    """A component's or category's label: `billing` and `area:billing` both name `area:billing`."""
    prefix = PREFIXES[kind.lower()]
    return prefix + name.removeprefix(prefix)


def label_names(tracker: str) -> dict[str, set[str]]:
    """The loop's label rule: each kind's names, the loop's fixed set plus docs/agents/issue-tracker.md's, a
    component as `area:<name>` and a category as `kind:<name>`."""
    found = tracker_settings(tracker)
    return {
        "category": CATEGORIES
        | {qualified("category", name) for name in found.get("categories", {})},
        "component": {qualified("component", name) for name in found.get("components", {})},
        "size": SIZES,
    }


class Table(dict):
    """A settings section whose every key is required, such as `land`."""


# loop.md's settings (SKILL.md § Settings), one section each: each key's type, or a tuple of the values it allows.
# A list holds strings; `bot.<login>` is a section per bot.
STAGES = ("intent", "spec", "plan", "build", "review", "land")
# the specs `spec.auto` may name: an issue that is a bug, a follow-up an agent raised, a sub-issue of an approved epic
SPEC_KINDS = ("bug", "follow-up", "sub-issue")
SCHEMA: dict[str, dict[str, Any]] = {
    "loop": {
        "cap": int,
        "ci": bool,
        "opt_out": bool,
        "local_ci_env": list,
    },
    "spec": {"auto": SPEC_KINDS},
    "practice": dict.fromkeys(STAGES, str),
    "risk": {"always": bool, "labels": list, "paths": list, "verifier": bool},
    "plan": {"always": bool, "labels": list},
    "signoff": {"always": bool, "labels": list, "paths": list},
    "bot": {"paths": list, "branch": str},
    "land": Table(signed_squash_to=str, allowed_signers=str),
    "carry_over_main": Table({"except": list}),
}
# docs/agents/issue-tracker.md's settings: in each section every key is a name, its value a description or a new name
TRACKED: dict[str, Any] = dict.fromkeys(
    ("components", "categories", "labels", "renames", "board"), str
)
# the settings block: a docs/agents/ file's first fenced `yaml` block, under its `## Settings` heading
SETTINGS = re.compile(r"^```yaml[ \t]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)
KINDS = {bool: "true or false", int: "a whole number", list: "a list of strings", str: "a string"}


def block(text: str, file: str) -> dict[str, Any]:
    """The file's settings block, parsed as YAML; refused without one under `## Settings`, since a file still on the
    line form would otherwise lose its settings unnoticed, or when it is no YAML mapping. Only that section is
    searched, so a YAML example elsewhere in the prose is never read as the settings. A key set twice is refused,
    since YAML would keep the last one silently."""
    found = SETTINGS.search(section(text, "Settings"))
    if found is None:
        raise Refused(
            f"{file} has no ```yaml settings block under ## Settings: SKILL.md § Settings has its keys"
        )
    try:
        once(yaml.compose(found[1], Loader=yaml.SafeLoader), file)
        data = yaml.safe_load(found[1])
    except yaml.YAMLError as exc:
        raise Refused(f"{file}'s settings block is not YAML: {exc}") from None
    if data is None:  # an empty block: no settings
        return {}
    if not isinstance(data, dict):
        raise Refused(f"{file}'s settings block is not YAML sections of `key: value`, but {data!r}")
    return data


def once(node: Any, file: str, path: str = "") -> None:
    """Refuse a key set twice in the same section of the block's YAML node tree, naming it."""
    if isinstance(node, yaml.MappingNode):
        seen = set()
        for key, value in node.value:
            if key.value in seen:
                raise Refused(f"{file}'s `{path}{key.value}` is set twice")
            seen.add(key.value)
            once(value, file, f"{path}{key.value}.")


def sections(data: dict[str, Any], file: str) -> dict[str, dict[str, Any]]:
    """The block's sections, refusing a key outside one, since every setting belongs to a section. A section with no
    keys under it is empty."""
    for name, value in data.items():
        if value is None:
            data[name] = {}
        elif not isinstance(value, dict):
            raise Refused(f"{file} has a setting `{name}` outside a section")
    return data


def typed(section: dict[str, Any], schema: Any, name: str, file: str = "loop.md") -> dict[str, Any]:
    """A section's values checked against its schema (a map of keys, or one type for any key), refusing one that
    doesn't match it and naming the key, so a mistyped setting is never read as a rule nobody wrote. Types match
    exactly, which also refuses what YAML 1.1 reads as another type where a name was meant (`no` as false, `1.10` as
    a float), naming the key, since such a value is never the name written."""
    for key, value in section.items():
        where = f"`{name}.{key}`"
        if not isinstance(
            key, str
        ):  # `on:`, `no:` or `1.10:` as a name is read as a boolean or a number
            raise Refused(f"{file}'s {where} is no name: quote it")
        kind = schema.get(key) if isinstance(schema, dict) else schema
        if kind is None:
            raise Refused(f"{file} has an unknown setting {where}")
        if isinstance(kind, tuple):  # true, false, or a list naming some of the tuple's values
            if not (
                isinstance(value, bool)
                or isinstance(value, list)
                and all(isinstance(item, str) and item in kind for item in value)
            ):
                raise Refused(
                    f"{file}'s {where} must be true, false or a list of {', '.join(kind)}, not {value!r}"
                )
        # bool is an int to Python, so a type is matched exactly
        elif type(value) is not kind or (
            kind is list and not all(isinstance(item, str) for item in value)
        ):
            raise Refused(f"{file}'s {where} must be {KINDS[kind]}, not {value!r}")
        elif kind is str and isinstance(schema, dict) and not value:
            raise Refused(
                f"{file}'s {where} is empty"
            )  # a name's description may be empty, a path may not
    if isinstance(schema, Table) and (missing := [key for key in schema if key not in section]):
        raise Refused(f"{file}'s `{name}` lacks `{'`, `'.join(missing)}`")
    return section


def settings(loop: str | None) -> dict[str, Any]:
    """loop.md's settings block, checked against SCHEMA: `loop`'s keys at the top level, every other section under
    its name and `bot` a list of `{login, paths}`; {} without loop.md, which has no rules. A loop.md without the block
    is refused rather than read as one without rules, since a project still on the line form would otherwise lose its
    risk rules unnoticed."""
    if loop is None:
        return {}
    data: dict[str, Any] = {}
    for name, section in sections(block(loop, "loop.md"), "loop.md").items():
        if name == "bot":
            for login, bot in section.items():
                where = f"bot.{login}"
                if not isinstance(login, str):
                    raise Refused(f"loop.md's `{where}` is no name: quote it")
                if bot is None:  # a login with nothing under it
                    bot = {}
                if not isinstance(bot, dict):
                    raise Refused(f"loop.md's `{where}` must be a section holding `paths`")
                if "paths" not in bot:
                    raise Refused(f"loop.md's `{where}` lacks `paths`")
                data.setdefault("bot", []).append(
                    {"login": login, **typed(bot, SCHEMA["bot"], where)}
                )
        elif name == "loop":
            data.update(typed(section, SCHEMA["loop"], name))
        elif name in SCHEMA:
            data[name] = typed(section, SCHEMA[name], name)
        else:
            raise Refused(f"loop.md has an unknown settings section `{name}`")
    return data


def tracker_settings(tracker: str) -> dict[str, dict[str, str]]:
    """docs/agents/issue-tracker.md's settings block, checked against TRACKED: each section's names with their text.
    `components` and `categories` name a label bare (`billing`) or in full (`area:billing`)."""
    data = sections(block(tracker, "issue-tracker.md"), "issue-tracker.md")
    unknown = [name for name in data if name not in TRACKED]
    if unknown:
        raise Refused(f"issue-tracker.md has an unknown settings section `{unknown[0]}`")
    return {
        name: typed(section, TRACKED[name], name, "issue-tracker.md")
        for name, section in data.items()
    }


def spec_auto(loop: str | None) -> bool:
    """Whether loop.md's `spec.auto` is true, under which a risk rule holds the spec instead of the merge."""
    return settings(loop).get("spec", {}).get("auto") is True


def spec_kinds(loop: str | None) -> set[str]:
    """The kinds of spec loop.md's `spec.auto` list names (SPEC_KINDS), which the policy approves; empty when it
    is no list."""
    auto = settings(loop).get("spec", {}).get("auto")
    return set(auto) if isinstance(auto, list) else set()


def matches(terms: dict[str, Any], labels: set[str], paths: list[str] | None) -> str | bool | None:
    """The first term of a rule (`always`, a label, a path glob) that holds on labels and paths, as the gate quotes
    it; False when none does, None when only its paths could and the gate doesn't have them all (the loop judges it).
    The `verifier` term never holds here: ruled() adds the verifier's judgment."""
    if terms.get("always"):
        return "always"
    for label in terms.get("labels", []):
        if label in labels:
            return f"label `{label}`"
    for glob in terms.get("paths", []):
        if any(fnmatch.fnmatch(path, glob) for path in paths or []):
            return f"path `{glob}`"
    return None if paths is None and terms.get("paths") else False


def exempt(pull: dict[str, Any], loop: str | None) -> bool:
    """Whether the PR needs no verifier review: a `bot.<name>` section of loop.md names it, and every file it changes
    matches one of that section's `paths` (lock and manifest files). A section names a bot by its login, or, with
    `branch`, a head-branch prefix (`renovate/`), for an updater that opens its PRs under a person's token; then the
    head must be this repository's own branch, since a fork's PR may name any branch and only a writer pushes one
    here. GitHub's GraphQL spells a bot's login without the `bot` REST and the setting write, so both compare
    without it; a person can't hold a bot's login, so for a login the author's type is checked too. Every commit's
    authors must be the PR's author, and its committer the author or no account (GitHub's web-flow committer on a
    bot's or an API's commits), since another person's push or rebase of its branch is a change no verifier saw. A
    renamed or copied file refuses it, since GraphQL gives only the new path, which may hide code moved onto a lock
    file's name, and so does the label `verify`, which asks for the review (a major update). No entry, or more files
    or commits than the gate reads: no exemption."""
    author, files = pull.get("author") or {}, paths(pull)
    renamed = any(
        file.get("changeType") in ("RENAMED", "COPIED") for file in pull["files"]["nodes"]
    )
    labels = {label["name"] for label in pull["labels"]["nodes"]}
    if not files or renamed or "verify" in labels:
        return False
    login = (author.get("login") or "").removesuffix("[bot]").lower()
    commits = pull.get("authored") or {}
    nodes = commits.get("nodes") or []
    if not login or not nodes or (commits.get("totalCount") or 0) > len(nodes):
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

    def names(bot: dict[str, Any]) -> bool:
        if "branch" in bot:
            return not pull["isCrossRepository"] and pull["headRefName"].startswith(bot["branch"])
        return (
            author.get("__typename") == "Bot"
            and bot["login"].removesuffix("[bot]").lower() == login
        )

    return any(
        names(bot)
        and all(any(fnmatch.fnmatch(path, glob) for glob in bot["paths"]) for path in files)
        for bot in settings(loop).get("bot", [])
    )


def paths(pull: dict[str, Any]) -> list[str] | None:
    """The files the PR changes; None past the one page of 100 the gate reads."""
    files = pull["files"]
    found = [file["path"] for file in files["nodes"]]
    return None if (files.get("totalCount") or 0) > len(found) else found


def ruled(
    labels: set[str], files: list[str] | None, loop: str | None, judged: str | None = None
) -> str | None:
    """Why loop.md's `risk` rule holds on these labels and files, or None; paths the gate can't judge for want of the
    files hold, since nothing else would enforce them. `judged` is why the verifier holds the change high (judged()),
    which its `verifier` term reads; None where no verdict is read, such as a spec before the build."""
    terms = settings(loop).get("risk", {})
    hit = matches(terms, labels, files)
    if hit:
        return f"it matches a risk rule ({hit})"
    if hit is None:
        return "the gate can't read every file the PR changes, so the risk rule's `paths` hold until a person judges them"
    if judged and terms.get("verifier"):
        return f"it matches a risk rule (verifier): {judged}"
    return None


def judged(pull: dict[str, Any], loop: str | None = None) -> str | None:
    """Why the verifier holds the change high, or None: the highest pass on the head (passes), or on the commit whose
    proofs the head carries (carried), says `Risk: high`, any other word than `low`, or has no `Risk:` line; a mixed
    PR's two verifiers both must say `low`. A head no review covers is None, since reviewed() then refuses the merge,
    or the PR needs no review (exempt, an exact revert)."""
    found = passes(pull)
    if isinstance(found, str):
        return f"the gate can't read the verifier's `Risk:` line: PR #{pull['number']} {found}"
    head = pull["headRefOid"].lower()
    on_head = [(number, lines) for commit, number, lines in found if commit == head]
    if not on_head and found and isinstance(carry := carried(pull, loop), tuple):
        head = carry[0]
        on_head = [(number, lines) for commit, number, lines in found if commit == head]
    if not on_head:
        return None
    last = max(number for number, _ in on_head)
    for number, lines in on_head:
        said = lines.get("Risk")
        if number == last and not re.match(r"low\b", said or "", re.IGNORECASE):
            line = "has no `Risk:` line" if said is None else f"says `Risk: {said}`"
            return f"the verifier's pass {last} on {head[:7]} {line}"
    return None


def risk(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> str | None:
    """Why the change is high risk, or None: `risk:high` on the PR or an issue it names; a risk rule (ruled) on the
    labels of the PR and its issues, the PR's files and the verifier's `Risk:` line (judged), except under
    `spec.auto: true`, where the rule's other terms hold the spec instead (spec_hold) and the owner approved the change before it
    was built, while its `verifier` term still holds the merge; or a review at the cap was not satisfied or left a
    blocker or major open (capped). An exact revert's issues (gated's `named`) count as its issues here."""
    issues = issues + pull.get("named", [])
    marked = [f"PR #{pull['number']}"] * (RISK_LABEL in names(pull)) + [
        f"#{issue['number']}" for issue in issues if RISK_LABEL in names(issue)
    ]
    if not marked and default(pull) and not pull["isCrossRepository"]:
        # a feature branch's merge to the default branch carries every high-risk PR that landed in it
        marked = [
            f"#{n}, merged into {pull['headRefName']}" for n in merged_high(pull["headRefName"])
        ]
    if marked:
        return f"`{RISK_LABEL}` is on {', '.join(marked)}"
    if why := pull.get("reverted"):
        return why
    if not spec_auto(loop):
        labels = names(pull).union(*(names(issue) for issue in issues))
        if why := ruled(labels, paths(pull), loop, judged(pull, loop)):
            return why
    elif settings(loop).get("risk", {}).get("verifier"):
        # spec_hold() read the paths and labels before the build; the verdict comes after it, so it holds the merge
        if why := judged(pull, loop):
            return f"it matches a risk rule's `verifier` term: {why}"
    limit = cap(loop)
    if capped(pull, limit):
        return f"a verifier review at the cap (pass {limit}) or later was not satisfied or left a blocker or major open, so the owner decides"
    return None


def default(pull: dict[str, Any]) -> bool:
    """Whether the PR's base is its repository's default branch; any other base is a feature branch."""
    return pull["baseRefName"] == pull["baseRepository"]["defaultBranchRef"]["name"]


def merged_high(branch: str) -> list[int]:
    """The merged PRs into `branch` that carry `risk:high` (flag() adds it to each high-risk PR that lands)."""
    # ponytail: one page of 100; page when a feature branch takes more high-risk PRs than that
    found = gh(
        "pr",
        "list",
        "--base",
        branch,
        "--state",
        "merged",
        "--label",
        RISK_LABEL,
        "--limit",
        "100",
        "--json",
        "number",
        "--jq",
        ".[].number",
    )
    return [int(number) for number in found.split()]


def signoff(
    pull: dict[str, Any], issue: dict[str, Any], loop: str | None
) -> tuple[bool, str] | None:
    """Whether the owner signs the issue's change off in use after it lands, and why; None when loop.md has no
    `signoff` section, which leaves every link as it was. The rule is judged as the risk rule is (matches), on the
    labels of the PR and this issue and the PR's files, and paths it can't judge hold; with no term matching, the
    spec's own `Sign-off: owner` line asks for it. A spec's `Sign-off: none` never waives a matching rule, since the
    rule is the owner's standing word."""
    terms = settings(loop).get("signoff")
    if terms is None:
        return None
    hit = matches(terms, names(pull) | names(issue), paths(pull))
    if hit:
        return True, f"it matches a sign-off rule ({hit})"
    if hit is None:
        return (
            True,
            "the gate can't read every file the PR changes, so the sign-off rule's `paths` hold",
        )
    found = SIGNOFF.search(QUOTED.sub("", spec_holder(issue).get("body") or ""))
    if found and found[1].lower() == "owner":
        return True, "its spec says `Sign-off: owner`"
    return False, "no sign-off rule matches" + (
        " and its spec says `Sign-off: none`" if found else ""
    )


def linked(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> list[str]:
    """One line per issue the PR links with the wrong keyword for its sign-off (signoff): `Implements #n` when the
    owner signs the change off after landing, so the merge leaves the issue open for it, and a closing keyword
    otherwise, so nothing waits for a sign-off nobody asked for. `Part of` suits both, since the issue stays open
    anyway. An issue GitHub links without a body line closes on merge."""
    kinds, found = links(pull["body"] or ""), []
    for issue in issues:
        judged = signoff(pull, issue, loop)
        if judged is None or any(label.startswith("wayfinder:") for label in names(issue)):
            continue
        number, kind, (needed, why) = issue["number"], kinds.get(issue["number"], CLOSES), judged
        if needed and kind == CLOSES:
            found.append(
                f"#{number} waits for the owner's sign-off after landing, since {why}: the PR says"
                f" `Implements #{number}`, which leaves it open, not a closing keyword"
            )
        elif not needed and kind == IMPLEMENTS:
            found.append(
                f"#{number} needs no sign-off ({why}): the PR says `Closes #{number}`, since"
                " `Implements` would leave it open for a sign-off nobody asked for"
            )
    return found


def flag(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> list[str]:
    """Add `risk:high` to a high-risk PR that lacks it, so the board shows why it waits; a line when GitHub refuses,
    never a failure, since the merge already waits for the owner either way. Added for the verifier's `Risk:` line,
    it comes with a FLAGGED comment, and comes off once a later pass judges the risk low (unflag)."""
    if RISK_LABEL in names(pull):
        return unflag(pull, issues, loop)
    if (why := risk(pull, issues, loop)) is None:
        return []
    where = f"PR #{pull['number']}"
    try:
        label(pull["number"], RISK_LABEL, add=True)
    except subprocess.CalledProcessError as exc:
        return [
            f"{where}: could not add `{RISK_LABEL}` ({(exc.stderr or '').strip() or exc}): add it by hand"
        ]
    if (verdict := judged(pull, loop)) and verdict in why:
        try:
            comment(
                pull["number"],
                f"{FLAGGED}, since {why}. A later pass that says `Risk: low` takes it off.\n",
            )
        except subprocess.CalledProcessError as exc:
            return [
                f"{where}: could not comment why the gate added `{RISK_LABEL}`, so it stays until a person removes it ({exc})"
            ]
    return []


def unflag(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> list[str]:
    """Take off a `risk:high` the gate added for the verifier's `Risk:` line (FLAGGED) once nothing holds the change
    high without it, since the verifier re-judges a disputed risk. A label added after the gate's comment is a
    person's or the lead's raise, which only the owner lowers."""
    flagged = [note["createdAt"] for note in notes(pull) if note["body"].startswith(FLAGGED)]
    added = [
        event["createdAt"]
        for event in pull["timelineItems"]["nodes"]
        if (event.get("label") or {}).get("name") == RISK_LABEL
    ]
    if not flagged or max(added, default="") > max(flagged):
        return []
    unlabelled = {**pull, "labels": {"nodes": [{"name": n} for n in names(pull) - {RISK_LABEL}]}}
    if risk(unlabelled, issues, loop) is not None:
        return []
    where = f"PR #{pull['number']}"
    try:
        label(pull["number"], RISK_LABEL, add=False)
    except subprocess.CalledProcessError as exc:
        return [f"{where}: could not remove `{RISK_LABEL}` ({(exc.stderr or '').strip() or exc})"]
    pull["labels"] = unlabelled["labels"]
    return [
        f"{where}: removed the `{RISK_LABEL}` the gate added, since the verifier now judges the risk low"
    ]


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
    """The last comment whose first line is `heading`: `## Specification notes` is no `## Spec`.
    A leading `> 🤖 AI` line (github.md) is skipped, so an agent's marked comment is still found."""
    found = [
        note
        for note in notes(node)
        if re.sub(r"\A\s*> 🤖 AI[ \t]*\n\s*", "", note["body"]).strip().split("\n", 1)[0].rstrip()
        == heading
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


def spec_policy(issue: dict[str, Any], kinds: set[str]) -> bool:
    """Whether a kind `spec.auto` names (`kinds`) approves the issue's spec: `bug`, an issue labelled a bug;
    `follow-up`, one an agent raised (a `Found while #n` line in its body); `sub-issue`, a native sub-issue of an epic
    with the owner's current spec record and `approved:spec`, opened by someone with write access. An epic is never
    covered: the owner approves it."""
    if EPIC in names(issue):
        return False
    if "bug" in kinds and BUG in names(issue):
        return True
    if "follow-up" in kinds and FOUND_WHILE.search(QUOTED.sub("", issue.get("body") or "")):
        return True
    parent = issue.get("parent")
    if "sub-issue" not in kinds:
        return False
    if not parent or READY not in names(parent):
        return False
    if not current(parent, "spec", "spec", version(spec_holder(parent)), "owner"):
        return False
    login = (issue.get("author") or {}).get("login")
    return bool(login) and writer(login)


def spec_hold(pull: dict[str, Any], issue: dict[str, Any], loop: str | None) -> str | None:
    """Why `spec.auto: true` leaves the issue's spec to the owner, or None when the policy approves it: a risk rule (ruled)
    on the labels of the issue and the PR and the files pushed so far, so a file the spec didn't foresee still reaches
    the owner; or an author without write access, since anyone who can open an issue would otherwise have their own
    spec approved."""
    if why := ruled(names(issue) | names(pull), paths(pull), loop):
        return why
    login = (issue.get("author") or {}).get("login")
    if not (login and writer(login)):
        return f"its author {f'@{login}' if login else '(no account)'} can't write to the repo"
    return None


def holds(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> list[str]:
    """A line per issue whose spec `spec.auto: true` leaves to the owner (spec_hold), approved or not, so a gate run says
    why that spec needed them and its merge waits for no `approved:merge`."""
    if not spec_auto(loop):
        return []
    return [
        f"#{issue['number']}: its spec is the owner's to approve under `spec.auto: true`, since {why}"
        for issue in issues
        if not any(label.startswith("wayfinder:") for label in names(issue))
        and (why := spec_hold(pull, issue, loop))
    ]


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
    `approved:spec` label; with it, the owner's record and the label, unless a kind `spec.auto` names covers it
    (spec_policy) or `spec.auto: true` does (spec_hold). A plan needs them where the `plan` rule asks. What the merge
    waits for is waits()'s."""
    rule, found = settings(loop), []
    kinds, every = spec_kinds(loop), spec_auto(loop)
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
        if not (every and spec_hold(pull, issue, loop) is None or spec_policy(issue, kinds)):
            found += approvals(where, issue, "spec", version(spec_holder(issue)))
        plan = headed(issue, "## Plan")
        if plan is not None:
            if matches(rule.get("plan", {}), labels, None):
                found += approvals(where, issue, "plan", version(plan))
        elif "plan" in rule.get("practice", {}):
            found.append(f"{where} has no `## Plan` comment, and one is due")
    if point != "merge":
        return found
    where = f"PR #{pull['number']}"
    evidence = section(pull["body"] or "", "Evidence")
    if not evidence.strip():
        found.append(f"{where}: its body has no `## Evidence` section with content")
    if loop is not None:
        found += linked(pull, issues, loop)
    if revert is None and not exempt(pull, loop):
        found += reviewed(where, pull, loop)
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


def passes(pull: dict[str, Any]) -> list[tuple[str, int, dict[str, str]]] | str:
    """The verifier's PR reviews in order, each as its commit, pass number and `VERDICT:`/`SATISFIED:`/`Risk:` lines: a body
    starting `Verifier (<family>), pass <n>`, by the PR's author, the account running this or a writer (writer), since
    anyone can review a public repo, and a colleague (or their agent) verifying someone else's PR posts as themself.
    A string names why none can be read."""
    reviews = pull["reviews"]
    if (reviews.get("totalCount") or 0) > len(reviews["nodes"]):
        return f"has more than {len(reviews['nodes'])} reviews: the gate reads one page"
    found = [review for review in reviews["nodes"] if PASS.match(review.get("body") or "")]
    trusted = {(pull.get("author") or {}).get("login"), viewer() if found else None} - {None}
    others = {(review.get("author") or {}).get("login") for review in found} - trusted - {None}
    trusted |= {login for login in others if writer(login)}
    return [
        (
            ((review.get("commit") or {}).get("oid") or "").lower(),
            int(PASS.match(review["body"])[2]),
            {
                key.strip(): value.strip()
                for key, _, value in (line.partition(":") for line in review["body"].splitlines())
                if key.strip() in ("VERDICT", "SATISFIED", "Risk")
            },
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
    """The project's cap: loop.md's `cap` setting, else SKILL.md's default."""
    if (own := settings(loop).get("cap")) is not None:
        return own
    skill = Path(__file__).resolve().parents[1] / "SKILL.md"
    found = CAP_DEFAULT.search(skill.read_text())
    if found is None:
        raise Refused("SKILL.md § The cap names no default (`The cap is <n> passes`)")
    return int(found[1])


def capped(pull: dict[str, Any], limit: int) -> bool:
    """Whether a verifier review at the cap (pass `limit`) or later left a blocker or major open, or was not
    satisfied: the owner then decides between a fix with one scoped pass more and leaving the code untouched."""
    found = passes(pull)
    return not isinstance(found, str) and any(
        number >= limit and not held(lines) for _, number, lines in found
    )


def reviewed(where: str, pull: dict[str, Any], loop: str | None) -> list[str]:
    """One line per reason the verifier's PR reviews (passes) let nothing land: the newest pass is not on the head,
    since every commit after a verdict needs one of its own, unless the head carries that commit's proofs (carried,
    which prints a line either way where loop.md opts in), or on its commit the highest pass (a mixed PR's two
    verifiers share one, and a later pass on the same commit supersedes an earlier one) is not satisfied, or has a
    blocker or a major open. A triage or comment is no verdict. An allow-listed bot's lock- or manifest-only PR
    needs none (exempt)."""
    verdicts = passes(pull)
    if isinstance(verdicts, str):
        return [f"{where} {verdicts}"]
    if not verdicts:
        return [f"{where}: no verifier review posted (approvals.py verdict)"]
    head = verdicts[-1][0]
    on_head = [(number, lines) for commit, number, lines in verdicts if commit == head]
    last = max(number for number, _ in on_head)
    same = [lines for number, lines in on_head if number == last]
    if not head or any(counts(lines) is None or "SATISFIED" not in lines for lines in same):
        return [
            f"{where}: a verifier review lacks its commit, or a `VERDICT:` or `SATISFIED:` line (approvals.py verdict)"
        ]
    found = []
    if pull["headRefOid"].lower() != head and not carries(where, pull, loop, head):
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
    """One line per thing the merge waits for: ran()'s checks, and the owner's label (owner_waits)."""
    return ran(pull, loop) + owner_waits(pull, issues, loop, pushed)


def no_ci(loop: str | None) -> bool:
    return settings(loop).get("ci") is False


def opted_out(loop: str | None) -> bool:
    return settings(loop).get("opt_out", False)


def signed(loop: str | None) -> tuple[str, Path] | None:
    """loop.md's `land` section as (branch, signers), None without one."""
    land = settings(loop).get("land")
    return (land["signed_squash_to"], Path(land["allowed_signers"]).expanduser()) if land else None


def unsignable(pull: dict[str, Any], branch: str, signers: Path) -> str | None:
    """Why this checkout can't land the PR as a signed squash, checked before the PR is touched."""
    where = f"PR #{pull['number']}"
    if pull["isCrossRepository"]:
        return f"{where} comes from another repository: its branch isn't ours to push, push it to {pull['baseRepository']['nameWithOwner']} first"
    if pull["baseRefName"] != branch:
        return f"{where} targets {pull['baseRefName']}, but loop.md lands signed squashes only to {branch}"
    if pull["autoMergeRequest"] is not None or pull["isInMergeQueue"]:
        return f"{where}: auto-merge or the merge queue would merge it with GitHub's signature: turn it off"
    # the URL as configured, before any `insteadOf` rewrite
    origin = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=False
    )
    if github_repo(origin.stdout.strip()) != pull["baseRepository"]["nameWithOwner"].lower():
        return f"this checkout's `origin` is not {pull['baseRepository']['nameWithOwner']}, where {where} lives"
    config = subprocess.run(
        ["git", "config", "--get", "user.signingkey"], capture_output=True, text=True, check=False
    )
    gpg = subprocess.run(
        ["git", "config", "--get", "gpg.format"], capture_output=True, text=True, check=False
    )
    if not config.stdout.strip() or gpg.stdout.strip() != "ssh":
        return "this checkout signs no commits with an SSH key: set `gpg.format ssh` and `user.signingkey`"
    if not signers.is_file():
        return f"no allowed signers file at {signers}"
    return None


def signed_squash(pull: dict[str, Any], signers: Path) -> str:
    """Squash the PR's head onto its base here, signed with this checkout's key and checked against `signers`, then
    push it to the PR's branch and fast-forward the base to it: GitHub marks a PR merged once its head is in the
    base. The head must be the one the gates checked and contain the base's tip, so the squash undoes nothing."""
    pr, base, branch, head = (
        pull["number"],
        pull["baseRefName"],
        pull["headRefName"],
        pull["headRefOid"],
    )
    git("fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
    git(
        "fetch", "-q", "origin", f"refs/pull/{pr}/head"
    )  # alone: FETCH_HEAD names the first ref fetched
    if git("rev-parse", "FETCH_HEAD").strip() != head:
        raise Refused(f"PR #{pr}'s head moved past {head}: run land again")
    tip = git("rev-parse", f"refs/remotes/origin/{base}").strip()
    if subprocess.run(["git", "merge-base", "--is-ancestor", tip, head], check=False).returncode:
        raise Refused(
            f"PR #{pr} does not contain {base}'s head {tip}: merge origin/{base} in, rerun the gates, get a"
            " verdict on the merge (lead.md step 8), then land again"
        )
    tree = git("rev-parse", f"{head}^{{tree}}").strip()
    try:
        commit = git("commit-tree", "-S", "-p", tip, "-m", f"{pull['title']} (#{pr})", tree).strip()
        git("-c", f"gpg.ssh.allowedSignersFile={signers}", "verify-commit", commit)
    except subprocess.CalledProcessError as exc:
        raise Refused(
            f"PR #{pr}: the squash is not signed by a key in {signers}: {' '.join(exc.stderr.split())}"
        ) from exc
    # the PR's branch first, pinned to the head the gates checked: GitHub marks the PR merged only when its head is
    # already the PR's branch as the base reaches it (one atomic push of both leaves the PR closed instead)
    git(
        "push",
        "-q",
        f"--force-with-lease=refs/heads/{branch}:{head}",
        "origin",
        f"{commit}:refs/heads/{branch}",
    )
    try:
        git(
            "push",
            "-q",
            f"--force-with-lease=refs/heads/{base}:{tip}",
            "origin",
            f"{commit}:refs/heads/{base}",
        )
    except subprocess.CalledProcessError as exc:
        # a base that moved meanwhile, or refused the push: put the PR's branch back on the checked head, leased to
        # the squash so a push to the branch since then stays
        git(
            "push",
            "-q",
            f"--force-with-lease=refs/heads/{branch}:{commit}",
            "origin",
            f"{head}:refs/heads/{branch}",
        )
        raise Refused(
            f"PR #{pr}: {base} refused the squash, so {branch} is back at {head}: {' '.join(exc.stderr.split())}"
        ) from exc
    return commit


def outside(pull: dict[str, Any], loop: str | None) -> str | None:
    """Why the PR is outside the loop, or None when it left a loop trail or loop.md lacks `opt_out: true`. A trail
    is a verifier review (passes), an `Approved: spec` record or `approved:spec` on an issue it links, a `Reverts #<n>`
    line, or a bot PR loop.md exempts. A spec a policy covers is no trail: under `spec.auto: true` every issue is covered,
    so a person who opted out could never link one."""
    if not opted_out(loop):
        return None
    found = passes(pull)
    if (isinstance(found, str) or found) or exempt(pull, loop):
        return None
    if REVERTS.search(QUOTED.sub("", pull["body"] or "")):
        return None
    for issue in closing_issues(pull):
        if READY in names(issue) or records(issue, "spec"):
            return None
    return (
        f"PR #{pull['number']} is outside the loop (loop.md `opt_out: true`, no verifier review, spec approval,"
        " revert or bot exemption): its author merges it"
    )


def ran(pull: dict[str, Any], loop: str | None, required: set[str] | None = None) -> list[str]:
    """One line per check the merge waits for on the head: ci()'s `required` (None: the base branch's required checks but
    `loop:approvals`, or the aggregate `check` when that leaves none), or with `ci: false` a local-ci pass."""
    where = f"PR #{pull['number']}"
    if queued(pull) is None:
        return []
    if no_ci(loop):
        head = [CHECKED, f"Head: {pull['headRefOid']}"]
        if any(
            [line.strip() for line in note["body"].strip().splitlines()[:2]] == head
            and trusted(pull, note)
            for note in notes(pull)
        ):
            found = []
        else:
            found = [
                f"{where}: the project has no CI (loop.md `ci: false`), and no local check passed on the head (approvals.py local-ci)"
            ]
    else:
        if required is None:
            # the approvals status is check merge's own output: waiting for it never ends
            required = required_checks(pull["baseRefName"]) - {APPROVALS} or None
        found = ci(where, pull, required)
    return found


def queued(pull: dict[str, Any]) -> list[str] | None:
    """None when a merge queue's batch proof (batch) on the head, by the account running this or a writer, holds
    (unproven), standing in for the CI wait; else one line per such proof that holds nothing, for diagnosis only:
    ran() adds none of them, so a red batch never holds a merge the CI wait alone would let through."""
    where, head, found = f"PR #{pull['number']}", pull["headRefOid"].lower(), []
    for note in notes(pull):
        lines = note["body"].strip().splitlines()
        if not lines or lines[0].strip() != BATCHED:
            continue
        header = itertools.takewhile(
            str.strip, lines[1:]
        )  # the log's tail after the blank line names no field
        fields = {
            key.strip(): value.strip() for key, _, value in (line.partition(":") for line in header)
        }
        if fields.get("Head", "").lower() != head or not trusted(pull, note, author=False):
            continue
        if (why := unproven(head, fields)) is None:
            return None
        found.append(f"{where}: {why}")
    return found


def trusted(pull: dict[str, Any], note: dict[str, Any], author: bool = True) -> bool:
    """Whether a proof comment's author counts: the account running this, a writer (writer), and with `author` the
    PR's author, as passes() reads verifier reviews, since anyone can comment on a public repo."""
    login = (note.get("author") or {}).get("login")
    if login is None:
        return False
    if author and login == (pull.get("author") or {}).get("login"):
        return True
    return login == viewer() or writer(login)


def unproven(head: str, fields: dict[str, str]) -> str | None:
    """Why a batch proof's fields prove nothing about `head`, or None: its gate exited 0, the head has its own green
    local-ci pass under this environment, the one the proof names, since a batch gate never stands in for the head's,
    its merge commit's second parent is the head, so the head landed unchanged, its tree is the clean merge of its
    parents, so the queue resolved no conflict and added nothing, and the batch commit contains it."""
    merge, batch, code = (fields.get(key, "").lower() for key in ("Merge", "Batch", "Exit"))
    if code != "0":
        return f"the merge queue's gate on batch {batch} exited {code or 'with no exit code'}"
    if (record := reusable(head)) is None:
        return f"the head {head} has no green `local-ci --record` pass of its own under this environment, which a batch never stands in for"
    # the comment names the env as posted, its home written `~` (public)
    if (env := public(env_line(record["env"])[len("Env: ") :].strip())) != fields.get("Env"):
        return (
            f"batch {batch} names the head's gate env `{fields.get('Env', '')}`, its record `{env}`"
        )
    for kind, sha in (("merge", merge), ("batch", batch)):
        if not fetched(sha):
            return f"{kind} {sha} is not a commit origin has"
    parents = git("rev-list", "--parents", "-n", "1", merge).split()[1:]
    if len(parents) != 2 or parents[1] != head:
        return f"merge {merge} does not merge the head {head} as its second parent"
    clean = merged(*parents)
    if isinstance(clean, str) or clean[0] != git("rev-parse", f"{merge}^{{tree}}").strip():
        return f"merge {merge} is not the clean merge of its parents: the queue resolved or added something"
    if subprocess.run(["git", "merge-base", "--is-ancestor", merge, batch], check=False).returncode:
        return f"batch {batch} does not contain merge {merge}"
    return None


def merged(
    first: str, second: str, guard: list[str] | None = None, base: str = "the base"
) -> tuple[str, str] | str:
    """The tree `git merge-tree --write-tree` makes of commits `first` and `second`, so a merge with that tree resolved
    no conflict and added nothing, and their merge base; a string names why not. With `guard`, the globs of loop.md's
    `carry_over_main.except`, the proofs on `first` carry over to that merge only when `second`'s changes since the
    merge base (`base`'s) touch no file `first`'s changes touch, neither side's changes touch a file a glob matches
    (fnmatch on the full path, as a rule's `paths`), and the two have one merge base. `first` is the PR's head, so a
    why names its side as the PR's. Fail-closed: a git error is a why, never a carry."""
    try:
        clean = subprocess.run(
            ["git", "merge-tree", "--write-tree", first, second],
            capture_output=True,
            text=True,
            check=False,
        )
        if clean.returncode or not clean.stdout.split():
            return f"{first} and {second} conflict"
        tree = clean.stdout.split()[0]
        if guard is None:
            return tree, ""
        bases = git("merge-base", "--all", first, second).split()
        if len(bases) != 1:
            return f"{first} and {second} have {len(bases)} merge bases"
        # plumbing: porcelain `git diff` follows config (diff.relative, a submodule's `ignore = all`) that hides paths
        changed = [
            set(
                filter(
                    None,
                    git(
                        "diff-tree",
                        "-r",
                        "--name-only",
                        "--no-renames",
                        "--ignore-submodules=none",
                        "-z",
                        bases[0],
                        side,
                    ).split("\0"),
                )
            )
            for side in (first, second)
        ]
        if both := sorted(changed[0] & changed[1]):
            return f"{both[0]} changed on both sides since {bases[0]}"
        # the PR's own config change was gated only on the PR's code, never on what the base added since
        for side, paths in ((f"{base}'s", changed[1]), ("the PR's", changed[0])):
            if hit := sorted(
                path for path in paths if any(fnmatch.fnmatch(path, glob) for glob in guard)
            ):
                return f"{side} changes since {bases[0]} touch {hit[0]}, a `carry_over_main.except` path"
        return tree, bases[0]
    except (subprocess.CalledProcessError, OSError) as exc:
        return f"git failed reading the merge of {first} and {second}: {exc}"


def carry_line(what: str, head: str, second: str, since: str, base: str) -> str:
    """The line check merge and land print when `what` carries the proofs of `head` (carried, merged)."""
    return (
        f"{what} carries the proofs of {head}: it is the clean merge (git merge-tree) of {head} and {base}'s"
        f" {second}, whose changes since {since} touch none of the PR's files, and neither side touches a"
        " `carry_over_main.except` path"
    )


def carried(pull: dict[str, Any], loop: str | None) -> tuple[str, str] | str | None:
    """The commit whose verdict the PR's head carries, with carry_line(), where loop.md has
    `carry_over_main`: the head is a merge whose first parent is that commit and whose second is on the base (an
    ancestor of its tip), its tree is git merge-tree's of the two, and merged() finds the base's changes disjoint
    from the PR's and neither side's touching an except glob. A string names why it carries nothing; None without the setting, which
    then reads no git at all. ponytail: one merge deep; walk first parents when a PR merges main in twice unverified."""
    guard = settings(loop).get("carry_over_main")
    if guard is None:
        return None
    head, tip, base = pull["headRefOid"].lower(), pull["baseRefOid"].lower(), pull["baseRefName"]
    try:
        if not (fetched(head) and fetched(tip)):
            return f"the head or {base}'s head {tip} is not a commit origin has"
        parents = git("rev-list", "--parents", "-n", "1", head).split()[1:]
        if len(parents) != 2:
            return "it is no merge of two parents"
        first, second = parents
        on_base = ["git", "merge-base", "--is-ancestor", second, tip]
        if subprocess.run(on_base, capture_output=True, check=False).returncode:
            return f"its second parent {second} is not on {base}"
        found = merged(first, second, guard["except"], base)
        if isinstance(found, str):
            return found
        if found[0] != git("rev-parse", f"{head}^{{tree}}").strip():
            return f"{head}'s tree is not git merge-tree's of its parents: the merge resolved or added something"
    except (subprocess.CalledProcessError, OSError) as exc:
        return f"git failed reading {head}: {exc}"
    return first, carry_line(head, first, second, found[1], base)


def carries(where: str, pull: dict[str, Any], loop: str | None, verified: str) -> bool:
    """Whether the PR's head carries the proofs of `verified`, the newest verdict's commit (carried), printing the
    line that says so, or where loop.md opts in, why it carries nothing."""
    carry = carried(pull, loop)
    if carry is None:
        return False
    if isinstance(carry, tuple) and carry[0] != verified:
        carry = f"its first parent is {carry[0]}"
    if isinstance(carry, str):
        print(f"{where}: {pull['headRefOid']} carries nothing from {verified}: {carry}")
        return False
    print(f"{where}: {carry[1]}")
    return True


def fetched(sha: str) -> bool:
    """Whether `sha` names a commit here, fetching `origin` once when it doesn't yet."""
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
        return False
    have = ["git", "cat-file", "-e", f"{sha}^{{commit}}"]
    if subprocess.run(have, capture_output=True, check=False).returncode == 0:
        return True
    subprocess.run(["git", "fetch", "--quiet", "origin"], capture_output=True, check=False)
    return subprocess.run(have, capture_output=True, check=False).returncode == 0


def queueable(pull: dict[str, Any], head: str, tracker: str | None, loop: str | None) -> int:
    """check queue: exit 0 when `head` may enter a batching merge queue, else one line per reason and exit 1."""
    where, found = f"PR #{pull['number']}", []
    if pull["state"] != "OPEN":
        found.append(f"{where} is {pull['state'].lower()}: nothing to queue")
    if pull["headRefOid"].lower() != head.lower():
        found.append(
            f"{where}'s head is {pull['headRefOid']}, not {head}: queue the head the verifier reviewed"
        )
    if why := outside(pull, loop):
        found.append(why)
    missing, issues = gated("merge", pull, tracker, loop)
    found += missing
    if not no_ci(loop):
        found += ran(pull, loop)
    if reusable(head) is None:  # with CI too: batch refuses a head without one, so it may not enter
        found.append(
            f"{where}: no `local-ci --record` pass on {head} under this environment (approvals.py local-ci --record)"
        )
    if why := risk(pull, issues, loop):
        found.append(f"{where} is high risk ({why}): it lands alone through `land`")
    if MERGE_LABEL in names(pull):
        found.append(
            f"{where} has the owner's `{MERGE_LABEL}`, which covers its head alone: it lands through `land`"
        )
    for line in found:
        print(line)
    if found:
        return 1
    print(f"{where} may enter a merge queue at {head}")
    return 0


def batch(pr: int, merge: str, batch_sha: str, code: int, log: Path) -> int:
    """Post a merge queue's batch proof on PR `pr`, which queued() reads: the head (the merge's second parent), the
    merge, the batch, the gate's exit, the head's own local-ci pass and its env, the log, and the log's last LOG_TAIL
    lines. Refused for a head with no green pass of its own under this environment."""
    if not fetched(merge.lower()):
        raise Refused(f"merge {merge} is not a commit here or on origin")
    head = git("rev-parse", f"{merge}^2").strip()
    if (record := reusable(head)) is None:
        raise Refused(
            f"the head {head} has no green `local-ci --record` pass of its own under this environment: no batch proof without it"
        )
    try:
        tail = log.read_text(errors="replace").splitlines()[-LOG_TAIL:]
    except OSError:
        tail = []
    body = (
        f"{BATCHED}\nHead: {head}\nMerge: {merge}\nBatch: {batch_sha}\nExit: {code}\n{env_line(record['env'])}"
        f"Gated: {record['time']}\nLog: {log}\n"
    )
    if tail:
        body += (
            "\n<details><summary>The gate's last lines</summary>\n\n````\n"
            + "\n".join(tail)
            + "\n````\n</details>\n"
        )
    comment(pr, body)
    return 0


def owner_waits(
    pull: dict[str, Any],
    issues: list[dict[str, Any]],
    loop: str | None,
    pushed: Callable[[dict[str, Any]], str | None] | None = None,
) -> list[str]:
    """A line while the change is high risk (risk) and the owner's `approved:merge` label is not on the PR, added
    after the head's push; on a PR into the default branch, a label no newer than a delegated record (delegate) is
    the delegate's, not the owner's. `pushed(pull)` is when the head was pushed (default: GitHub's repository
    activity)."""
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
    elif default(pull) and any(
        (parsed(note["body"], "merge") or {}).get("by") == DELEGATE and note["createdAt"] >= added
        for note in notes(pull)
    ):
        found.append(
            f"{where}: `{MERGE_LABEL}` is the delegated approval, which covers a PR into a feature branch, not into"
            f" {pull['baseRefName']}: the owner removes it and adds it again"
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
    undone: tuple[dict[str, tuple[str, str]] | None, dict[str, tuple[str, str]] | None],
    undoing: tuple[dict[str, tuple[str, str]] | None, dict[str, tuple[str, str]] | None],
) -> list[str]:
    """Why `revert` does not undo #number, both as GitHub's REST API lists a PR's files; empty when it does. Each file
    must have the inverse status and the inverse runs of changed lines in order, while line numbers and context move
    with main. Every path either touches must have, in `undoing` (the revert's merge base and head trees), the modes
    it had in `undone` (#number's base and merge commit trees) the other way round, absence included. A tree GitHub
    truncated is None. Trees map a path to its (mode, blob): a revert that touches only #number's paths and whose
    trees hold #number's blobs the other way round is exact whatever its diff looks like, since a diff can pair the
    same change's lines another way (#351)."""
    why: list[str] = []
    before, after = undone
    base, head = undoing
    trees = None not in (before, after, base, head)

    def paths(entries: list[dict[str, Any]]) -> set[str]:
        return {
            entry[name]
            for entry in entries
            for name in ("filename", "previous_filename")
            if entry.get(name)
        }

    touched = paths(original) | paths(revert)
    if (
        trees
        and touched == paths(original)
        and all(base.get(p) == after.get(p) and head.get(p) == before.get(p) for p in touched)
    ):
        return why

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
    if not trees:
        why.append("GitHub truncates a tree it would compare file modes in")
    else:
        for path in sorted(touched):
            for theirs, ours, where, when in (
                (after, base, "at the merge base", "after"),
                (before, head, "at the head", "before"),
            ):
                mode, wanted = (ours.get(path, ("absent",))[0], theirs.get(path, ("absent",))[0])
                if mode != wanted:
                    why.append(f"`{path}` has mode {mode} {where}, and {wanted} {when} #{number}")
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
    the aggregate `check`, the one check `check merge` reads on a base that requires none, since every other check is
    advisory; empty: every check); how many checks GitHub returned when it holds more than that one page, else None; and the
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
    drafts: set[tuple[str, str]] = set()

    def skipped(node: dict[str, Any]) -> bool:
        return node.get("conclusion") == "SKIPPED" and (node.get("completedAt") or "") < ready

    # A workflow whose run since ready has finished never produces a name only its draft run had, such as a matrix
    # job's literal `matrix.part`, skipped before the matrix expanded. Only a finished run says so: a job that needs
    # another has no check run until it starts. A draft's skip is no such run, though GitHub may give it a
    # `startedAt` after its `completedAt`, and so after a ready right behind it.
    finished = {
        workflow(node)
        for node in every
        if not skipped(node)
        and started(node) >= ready
        and (node.get("checkSuite") or {}).get("status") == "COMPLETED"
    }
    for node in every:
        name = node.get("name") or node.get("context")
        if wanted and name not in wanted:
            continue
        if skipped(node):
            drafts.add((workflow(node), name))
            continue
        key = (workflow(node), name)
        if key not in newest or started(node) >= started(newest[key]):
            newest[key] = node
    checks = [
        (name, node.get("conclusion") or node.get("state") or node.get("status"))
        for (_, name), node in newest.items()
    ]
    # a draft skip is replaced only by its own workflow's run: a job of that name in another workflow says nothing
    return checks, more, {name for flow, name in drafts - newest.keys() if flow not in finished}


def ci(where: str, pull: dict[str, Any], required: set[str] | None = None) -> list[str]:
    """A line per check head_checks() reads that is not green on the head, or not there yet."""
    checks, more, drafts = head_checks(pull, required)
    wanted = {"check"} if required is None else required
    if wanted:
        missing = [f"`{name}`" for name in sorted(wanted - {name for name, _ in checks})]
    else:  # every check of none would pass a head CI has not reached yet, or one only the draft skipped
        missing = [f"`{name}`" for name in sorted(drafts)] or ([] if checks else ["check"])
    if more is not None and (missing or not wanted):
        return [f"{where} has more than {more} {PAGED}"]
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


def workflow(node: dict[str, Any]) -> str:
    """The name of the workflow a check run belongs to; empty for a status."""
    run = (node.get("checkSuite") or {}).get("workflowRun") or {}
    return (run.get("workflow") or {}).get("name", "")


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


# GitHub's answer to a rules read on a private repo of a free plan
PLAN_LIMIT = "Upgrade to GitHub Pro"


def required_checks(base: str) -> set[str]:
    """The checks the base branch requires, from its live rules: its rulesets' and its branch protection's. A private
    repo on GitHub's free plan has no rulesets: that 403 reads as none, and any other error raises."""
    try:
        rulesets = gh(
            "api",
            "--paginate",
            f"repos/{{owner}}/{{repo}}/rules/branches/{base}",
            "--jq",
            '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context',
        )
    except subprocess.CalledProcessError as error:
        if "(HTTP 403)" not in (error.stderr or "") or PLAN_LIMIT not in error.stderr:
            raise
        print(
            f"GitHub enforces no rules on {base} here (its plan has none): land's proofs are the only gate"
        )
        rulesets = ""
    protection = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/branches/{base}",
        "--jq",
        ".protection.required_status_checks.contexts // [] | .[]",
    )
    return set((rulesets + protection).split())


def auto_merge_allowed() -> bool:
    return gh("api", "repos/{owner}/{repo}", "--jq", ".allow_auto_merge").strip() == "true"


def tree(sha: str) -> dict[str, tuple[str, str]] | None:
    """The (mode, blob SHA) of every path in commit `sha`'s tree, from GitHub's trees API; None when GitHub truncates it.
    ponytail: one recursive read, up to GitHub's 100,000 entries; read each touched directory when a repo outgrows it."""
    found = json.loads(gh("api", f"repos/{{owner}}/{{repo}}/git/trees/{sha}?recursive=1"))
    if found["truncated"]:
        return None
    return {
        entry["path"]: (entry["mode"], entry["sha"])
        for entry in found["tree"]
        if entry["type"] != "tree"
    }


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
    """GitHub's closing references plus every `#n` after a closing keyword, `Part of` or `Implements` in the body: GitHub sometimes
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


def public(text: str) -> str:
    """`text` as posted: the home directory written `~`, since a path under it (a log's, a cache's) names the person
    whose machine posted it, and GitHub's edit history keeps a comment's first text for good."""
    home = str(Path.home()).rstrip("/")
    return re.sub(re.escape(home) + r"(?![\w.-])", "~", text) if home else text


def comment(number: int, body: str) -> None:
    gh(
        "api",
        f"repos/{{owner}}/{{repo}}/issues/{number}/comments",
        "-F",
        "body=@-",
        "--silent",
        data=public(body),
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
    token (`github.token`), where the PR's author and the repo's writers are the ones trusted (passes)."""
    try:
        return gh("api", "user", "--jq", ".login").strip()
    except subprocess.CalledProcessError:
        return None


def writer(login: str) -> bool:
    """Whether `login` can write to the repo, by GitHub's collaborator permission; an account GitHub refuses to look
    up can't. ponytail: a bot's GraphQL login lacks the `bot` REST needs, so a bot author fails closed; add the
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


# a remote URL's host and `owner/repo`: `scheme://[user@]host[:port]/owner/repo` or scp-like `[user@]host:owner/repo`,
# its path maybe led by extra slashes as gh allows, matched once trailing slashes and `.git` are cut (post_demo.sh
# parses it the same way)
REMOTE_URL = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]*@)?([^/:]+)(?::\d+)?[:/]/*([^/]+/[^/]+)", re.IGNORECASE
)


def github_repo(url: str) -> str | None:
    """The `owner/repo` a GitHub remote URL names, lowercased; None for another host."""
    found = REMOTE_URL.fullmatch(re.sub(r"(?:\.git)?/*$", "", url.rstrip("/")))
    return found[2].lower() if found and found[1].lower() == "github.com" else None


def one_repo() -> None:
    """Refuse a checkout whose remotes name several GitHub repos while none is gh's default (`gh repo set-default`,
    kept as `remote.<name>.gh-resolved`): gh then reads `{owner}/{repo}` and every `gh pr` as `upstream`, and a
    review or label lands on a repo nobody chose. Outside a checkout it passes, and gh says why it can't run."""
    remotes = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True, check=False)
    repos = sorted(
        {
            repo
            for line in remotes.stdout.splitlines()
            if len(fields := line.split()) > 1 and (repo := github_repo(fields[1]))
        }
    )
    chosen = subprocess.run(
        ["git", "config", "--get-regexp", r"^remote\..*\.gh-resolved$"],
        capture_output=True,
        check=False,
    )
    if len(repos) > 1 and chosen.returncode:
        raise Refused(
            f"this checkout's remotes name {', '.join(repos)} and gh has no default among them, so gh would pick one"
            " itself: run `gh repo set-default <owner>/<repo>` once, naming the repo the PRs live in"
        )


def project() -> tuple[str | None, str | None]:
    """The checkout's docs/agents/issue-tracker.md and loop.md, None for one it lacks: a repo without the loop's
    files has no rules, and its issues no label shape. Settings off their schema are refused here, before any proof
    is printed or any PR touched."""
    root = toplevel()
    tracker, loop = (
        read(root / path) if (root / path).exists() else None for path in (TRACKER, LOOP)
    )
    settings(loop)
    if tracker is not None:
        tracker_settings(tracker)
    return tracker, loop


def gated(
    point: str, pull: dict[str, Any], tracker: str | None, loop: str | None
) -> tuple[list[str], list[dict[str, Any]]]:
    """Every missing proof at `point`, and the issues the PR names (none for an exact revert, which needs no spec: risk()
    reads its issues from `named` and the reverted PR's risk from `reverted` instead)."""
    revert, found = reverts(pull)
    if revert:
        pull["named"], pull["reverted"] = closing_issues(pull), reverted(revert)
        return found + proofs(point, pull, [], loop, revert), []
    issues = closing_issues(pull)
    found += problems(issues, None if tracker is None else label_names(tracker))
    return found + proofs(point, pull, issues, loop, revert), issues


def reverted(number: int) -> str | None:
    """Why an exact revert of #number is high risk for what it reverts, or None: `risk:high` on #number, or #number's
    last verdict judging it high (judged), since undoing a high-risk change (or re-landing one, a revert of its
    revert) changes as much as making it."""
    original = pull_request(number)
    if RISK_LABEL in names(original):
        return f"`{RISK_LABEL}` is on #{number}, which it reverts"
    if why := judged(original):
        return f"it reverts #{number}, and {why}"
    return None


def check(point: str, pr: int | None, head: str | None = None, issue: int | None = None) -> int:
    tracker, loop = project()
    if issue is not None:
        return unbuilt(issue, tracker, loop)
    if pr is None and (pr := current_pr()) is None:
        if point == "build":
            if (issue := branch_issue()) is None:
                print(
                    "no PR for this branch yet, and its name holds no issue number: pass --issue <n>, since a build"
                    " needs an approved spec"
                )
                return 1
            return unbuilt(issue, tracker, loop)
        print("no PR for this branch yet: nothing to gate")
        return 0
    pull = pull_request(pr)
    if point == "queue" and head is not None:
        return queueable(pull, head, tracker, loop)
    if point == "merge" and (why := outside(pull, loop)):
        print(why)
        return 0
    found, issues = gated(point, pull, tracker, loop)
    # flag() first, since a `risk:high` it takes off no longer holds the merge
    after = flag(pull, issues, loop) if point == "merge" else [] if found else claim(pull, issues)
    waiting = waits(pull, issues, loop) if point == "merge" else []
    for line in holds(pull, issues, loop) + found + waiting + after:
        print(line)
    return 1 if found else WAITING if waiting else 0


def unopened() -> dict[str, Any]:
    """The PR `check build` judges an issue's spec beside before it exists: no labels, and the files the branch has
    changed since it left origin's default branch, as a PR's would be at `check build`; when git can't tell, more files
    than it lists (paths() None), so a `paths` risk rule holds rather than reading as unmatched."""
    try:
        base = git("rev-parse", "--abbrev-ref", "origin/HEAD").strip()
        # NUL-separated, since git quotes a non-ASCII name and a name may hold spaces
        found = git("diff", "--name-only", "-z", f"{base}...HEAD").split("\0")[:-1]
    except subprocess.CalledProcessError:
        return {"labels": {"nodes": []}, "files": {"nodes": [], "totalCount": 1}}
    return {"labels": {"nodes": []}, "files": {"nodes": [{"path": path} for path in found]}}


def unbuilt(number: int, tracker: str | None, loop: str | None) -> int:
    """check build on one issue before its PR exists: every build proof a PR's issues need (problems, proofs), judged
    on the issue and the files the branch changes so far (unopened); it claims nothing, since there is no PR to give
    the assignee."""
    issues, pull = [issue_node(number)], unopened()
    found = problems(issues, None if tracker is None else label_names(tracker))
    found += proofs("build", pull, issues, loop)
    for line in holds(pull, issues, loop) + found:
        print(line)
    if not found:
        print(f"#{number}: every build proof holds; no PR yet")
    return 1 if found else 0


def branch_issue() -> int | None:
    """The issue number the current branch's name starts a segment with (`loop/329-build-issue`), or None."""
    found = re.search(r"(?:^|/)(\d+)(?:-|$)", git("rev-parse", "--abbrev-ref", "HEAD").strip())
    return int(found[1]) if found else None


def land(pr: int, wait: bool = False) -> int:
    """landing() once, or with `wait` again every POLL seconds while it polls, printing what changed: until it
    ends, or exit 3 at CEILING."""
    if not wait:
        return landing(pr)[0]
    deadline, said, polled = time.monotonic() + CEILING, "", None
    reran: set[str] = set()
    while True:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code, polled = landing(pr, reran, polled == ON_MERGE)
        finally:
            # a background command's log: each state once, not every 30 seconds
            if out.getvalue() != said:
                print(out.getvalue(), end="", flush=True)
            said = out.getvalue()
        if polled is None:
            return code
        if time.monotonic() + POLL > deadline:
            print(
                f"PR #{pr}: land --wait stopped after {CEILING // 3600} hours, still waiting for {polled}"
            )
            return WAITING
        time.sleep(POLL)


def stuck(pull: dict[str, Any]) -> bool:
    """Whether the PR's merge-queue entry has waited STUCK seconds for checks with no check suite on its commit."""
    entry = pull.get("mergeQueueEntry") or {}
    if entry.get("state") != "AWAITING_CHECKS" or not entry.get("enqueuedAt"):
        return False
    suites = ((entry.get("headCommit") or {}).get("checkSuites") or {}).get("totalCount") or 0
    queued = datetime.fromisoformat(entry["enqueuedAt"].replace("Z", "+00:00")).timestamp()
    return not suites and time.time() - queued >= STUCK


def landing(
    pr: int, reran: set[str] | None = None, merging: bool = False
) -> tuple[int, str | None]:
    """Every merge proof; a draft is then marked ready and waits (exit 3) for the CI that starts. A ready PR merges
    pinned to the head: at once when nothing waits, else auto-merge while only the base's required checks are pending
    and the repo allows it; exit 3 while anything else waits. When a red `loop:approvals` status is all that
    waits, its Actions run is rerun: exit 3. A head behind its base, or in conflict, is refused first.
    With `reran` (land --wait), also what a wait would poll for (ON_CI, ON_MERGE, ON_STATE), else None: it ends
    here. Then auto-merge already on, or the merge queue, is watched rather than merged again, `merging` says this wait
    merged or turned auto-merge on, and each approvals run is rerun once."""
    tracker, loop = project()
    local = signed(loop)
    pull = pull_request(pr)
    where, head = f"PR #{pr}", pull["headRefOid"]
    watching = reran is not None
    if pull["state"] == "MERGED":
        print(f"{where} is merged")
        return 0, None
    if pull["state"] != "OPEN":
        raise Refused(f"{where} is closed: nothing to land")
    auto = pull["autoMergeRequest"] is not None or pull["isInMergeQueue"]
    if merging and not auto:
        # GitHub takes a PR out of the queue a moment before it reports the merge: read it once more first
        time.sleep(POLL)
        pull = pull_request(pr)
        if pull["state"] == "MERGED":
            print(f"{where} is merged")
            return 0, None
        auto = pull["autoMergeRequest"] is not None or pull["isInMergeQueue"]
    if merging and not auto:
        raise Refused(
            f"{where}: auto-merge was turned off, or the PR left the merge queue, without a merge"
        )
    if why := outside(pull, loop):
        # land is the loop's merge: auto-merge on a PR no verifier saw would merge it on CI alone
        raise Refused(why)
    # GitHub says this as a required check `expected`
    if stale := STALE_BASE.get(pull["mergeStateStatus"]):
        raise Refused(
            f"{where} {stale} {pull['baseRefName']}: merge origin/{pull['baseRefName']} in, rerun the gates, get a"
            " verdict on the merge (lead.md step 8), then land again"
        )
    found, issues = gated("merge", pull, tracker, loop)
    if found:  # never ready on a missing proof: ready starts CI and, with auto-merge, the merge
        for line in holds(pull, issues, loop) + found:
            print(line)
        return 1, None
    if local and (why := unsignable(pull, *local)):
        raise Refused(why)
    for line in flag(pull, issues, loop):
        print(line)
    required = required_checks(pull["baseRefName"])
    checking, owner = ran(pull, loop, required), owner_waits(pull, issues, loop)
    # ponytail: no --delete-branch, which also deletes the local branch a worktree has checked out; the repo's
    # delete_branch_on_merge removes the remote one. Add it when a repo lacks that setting.
    merge = ["pr", "merge", str(pr), "--squash", "--match-head-commit", head]
    checks = head_checks(pull, required)[0]  # ran() already waits for a draft-only skip
    red = [(name, state) for name, state in checks if state not in GREEN]
    # GitHub merges once the required checks pass; a red one it never merges past. The owner's label and a local-ci
    # record are no check of GitHub's, so either hold ends the wait below instead.
    if watching and auto and not owner and not (no_ci(loop) and checking):
        if not RED.intersection(state for _, state in red):
            if stuck(pull):
                try:
                    gh("api", "graphql", "-f", f"query={DEQUEUE}", "-f", f"id={pull['id']}")
                except subprocess.CalledProcessError as error:
                    print(
                        f"{where}: dequeueing its stuck merge-queue entry failed: {error.stderr.strip()}"
                    )
                    return WAITING, ON_MERGE
                # the next poll reads it open and unqueued and lands it again, every merge proof with it
                print(
                    f"{where}: its merge-queue entry waited {STUCK // 60} minutes for checks GitHub never started:"
                    " dequeued, to land it again"
                )
                return WAITING, ON_STATE
            print(
                f"{where}: {'in the merge queue' if pull['isInMergeQueue'] else 'auto-merge is on'} at {head}"
            )
            return WAITING, ON_MERGE
        for line in checking + owner:
            print(line)
        return WAITING, None
    # GitHub computes the merge state after a push or a base change; ready or merge before it may expose a head the
    # next read refuses as behind or in conflict
    if pull["mergeStateStatus"] == "UNKNOWN":
        print(f"{where}: GitHub hasn't computed whether it can merge yet: run land again")
        return WAITING, ON_STATE
    if pull["isDraft"]:
        # CI skips a draft, and a skipped check counts as green: a draft's checks say nothing about the ready PR
        gh("pr", "ready", str(pr))
        print(f"{where} is ready now: CI starts on ready, run land again")
        return WAITING, ON_CI
    if not checking + owner and local:
        commit = signed_squash(pull, local[1])
        print(f"{where} landed in {pull['baseRefName']} as {commit}, signed by a key in {local[1]}")
        return 0, None
    if not checking + owner:
        gh(*merge)
        print(f"{where} merges at {head}")
        # on a base that requires a merge queue, GitHub queues it instead: a wait follows it to MERGED
        return 0, ON_MERGE
    # a required check not on the head yet may be a draft's skipped run, which GitHub's auto-merge counts as passing
    pending = (
        not owner
        and not no_ci(loop)
        and required <= {name for name, _ in checks}
        and not RED.intersection(state for _, state in checks)
    )
    # GitHub's auto-merge would sign the squash with GitHub's key: a signed landing waits for the checks instead
    if pending and required and not local and auto_merge_allowed():
        gh(*merge, "--auto")
        print(f"{where}: auto-merge on at {head}, once {', '.join(sorted(required))} pass")
        return 0, ON_MERGE
    statuses = [
        node
        # a head no check ran on has a null rollup
        for node in (
            pull["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
            or {"contexts": {"nodes": []}}
        )["contexts"]["nodes"]
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
            return WAITING, None
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
            return WAITING, None
        if run.get("status") != "completed":
            print(
                f"{stale}: its run {found[1]} is {run.get('status')}, so the status is not posted yet; run land again"
            )
            return WAITING, ON_CI
        if reran is not None and found[1] in reran:
            print(f"{stale}, again after land --wait reran run {found[1]}: read its log")
            return WAITING, None
        # ponytail: a status forged to name another workflow's run reruns that run; whoever can post statuses
        # can rerun runs anyway. Pin the context to the approvals app in the ruleset to close it.
        gh("run", "rerun", found[1])
        if reran is not None:
            reran.add(found[1])
        print(
            f"{stale}: reran run {found[1]}, since resolving a review thread starts no workflow; run land again"
        )
        return WAITING, ON_CI
    for line in checking + owner:
        print(line)
    # CI may still clear what waits while a required check is pending and none is red; the owner is asked after it
    pending = (
        checking
        and not no_ci(loop)
        and not RED.intersection(state for _, state in red)
        and not any(line.endswith(PAGED) for line in checking)
    )
    return WAITING, ON_CI if pending else None


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


def delegate(number: int) -> int:
    """The delegated approver's `approved:merge` on a PR into a feature branch, under the owner's standing rule: the
    label, then the record that names it the delegate's, so owner_waits refuses it once the PR targets the default
    branch, whose merge only the owner approves. Into the default branch it is refused."""
    pull = pull_request(number)
    if default(pull):
        raise Refused(
            f"PR #{number} targets {pull['baseRefName']}, the default branch: only the owner approves its merge"
        )
    # the label first, so the record is never older than the label it names
    label(number, MERGE_LABEL, add=True)
    try:
        comment(number, f"Approved: merge\nBy: {DELEGATE}\n")
    except subprocess.CalledProcessError:
        # a label with no record reads as the owner's once the PR targets the default branch: take it off again
        label(number, MERGE_LABEL, add=False)
        raise
    return 0


# a report's finding heading: `### <id> (<severity>) <path>:<line>: <title>`, the line a number or a range `<n>-<m>`
FINDING = re.compile(
    r"###[ \t]+(\S+)[ \t]+\((blocker|major|minor)\)[ \t]+`?([^\s`]+?):(\d+(?:-\d+)?)`?:?[ \t]+(.+?)[ \t]*",
    re.IGNORECASE,
)
# a `### ` heading with a severity in parentheses is meant as a finding; any other is a sub-heading, and a finding written
# without one is caught by verdict()'s count check
SEVERITY = re.compile(r"\((blocker|major|minor)\)", re.IGNORECASE)
# the verdict's counts, which every finding heading must add up to
COUNTED = re.compile(r"VERDICT:[ \t]*(\d+) blockers?,[ \t]*(\d+) majors?,[ \t]*(\d+) minors?\b.*")


def findings(text: str, report: Path) -> list[tuple[str, str, str, str, str, str]]:
    """Each finding of a report as (id, severity, path, line, title, body): its body up to the next heading of
    levels 1 to 3 or the closing `Head:`/`VERDICT:`/`SATISFIED:` lines, outside a code fence. A `### ` heading with
    a `(<severity>)` that doesn't read as a finding is refused, since the review would leave it out without a word;
    any other is a sub-heading, which posts nothing."""
    found: list[tuple[str, str, str, str, str, list[str]]] = []
    body: list[str] | None = None  # the open finding's lines
    fenced = False
    for line in text.splitlines():
        if re.match(r"[ \t>]*(```|~~~)", line):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,3} |(Head|VERDICT|SATISFIED):", line):
            body = None
            if line.startswith("### ") and SEVERITY.search(line):
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
        # unescaped, so public() finds a non-ASCII home as GitHub will decode it
        data=public(json.dumps(review, ensure_ascii=False)),
    )


def parse_report(
    report: Path,
) -> tuple[str, str, list[tuple[str, str, str, str, str, str]], list[str], str]:
    """A verifier report as `verdict` posts it: its review heading, the head it reviewed, its findings, its closing
    `VERDICT:`, `SATISFIED:` and `Risk:` lines, and the qualifier its `Verifier:` line has after the pass number ('' for
    none). Refused, naming the fix, when `verdict` couldn't post it whole."""
    text = read(report)
    lines = [line.strip() for line in text.splitlines()]
    verdicts = [line for line in lines if line.startswith("VERDICT:")]
    satisfied = [line for line in lines if line.startswith("SATISFIED:")]
    if not satisfied or not verdicts:
        raise Refused(f"{report} has no `VERDICT:` or `SATISFIED:` line: the report is unfinished")
    judgments = [line for line in lines if re.match(r"Risk:[ \t]*\S", line)]
    if not judgments:
        raise Refused(f"{report} has no `Risk: low|high — <reason>` line: the report is unfinished")
    # the head the verifier reviewed, which a push since the review may have moved the PR's head past
    heads = [
        found[1] for line in lines if (found := re.fullmatch(r"Head:[ \t]*([0-9a-fA-F]{40})", line))
    ]
    if not heads:
        raise Refused(f"{report} has no `Head: <sha>` line naming the full commit it reviewed")
    passes = [
        found
        for line in lines
        # free text after the pass number is a qualifier the review's first line carries
        if (
            found := re.fullmatch(
                r"Verifier:[ \t]*(.+?),[ \t]*pass[ \t]+(\d+)\b[ \t]*[:,;]?[ \t]*(.*)", line
            )
        )
    ]
    if not passes:
        raise Refused(f"{report} has no `Verifier: <family>, pass <n>` line")
    counted = COUNTED.fullmatch(verdicts[-1])
    if not counted:
        raise Refused(f"{report}: write the verdict `VERDICT: <n> blocker, <n> major, <n> minor`")
    # a finding whose heading doesn't read as one would be left off the review without a word
    found = findings(text, report)
    tally = tuple(sum(f[1] == kind for f in found) for kind in ("blocker", "major", "minor"))
    if tally != tuple(map(int, counted.groups())):
        raise Refused(
            f"{report}: `{verdicts[-1]}` counts {sum(map(int, counted.groups()))} findings, but {len(found)} "
            f"headings read as one ({tally[0]} blocker, {tally[1]} major, {tally[2]} minor): write each "
            "`### <id> (<blocker|major|minor>) <path>:<line>: <title>`"
        )
    family, number, qualifier = passes[-1].groups()
    closing = [verdicts[-1], satisfied[-1], judgments[-1]]
    heading = f"Verifier ({family}), pass {number}"
    return heading, heads[-1].lower(), found, closing, qualifier


def report_check(report: Path) -> int:
    """Check a verifier report the way `verdict` reads it, posting nothing, so the verifier fixes it before replying."""
    parse_report(report)
    print(f"{report} reads as a verdict")
    return 0


def verdict(pr: int, report: Path) -> int:
    """Post a verifier report as a PR review on the commit it reviewed: one inline comment per finding, at the nearest
    line of the diff when its line is outside it, in the review's body when its file is."""
    heading, head, found, closing, qualifier = parse_report(report)
    diff = diff_lines(pull_request(pr)["baseRefOid"], head)
    comments, outside = [], []
    for name, severity, path, line, title, body in found:
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
    first = f"{heading} on {head[:7]}" + (f": {qualifier}" if qualifier else "") + "."
    summary = "\n\n".join([first, *outside, "\n".join(closing)])
    post_review(
        pr, {"commit_id": head, "event": "COMMENT", "body": summary + "\n", "comments": comments}
    )
    return 0


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


LOCAL_CI = ["mise", "run", "check:all"]


def recorded(head: str) -> Path:
    """Where a local-ci pass on `head` is recorded: the git common dir, which every worktree of the clone shares and no
    commit carries."""
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    return common / "approvals" / "local-ci" / f"{head}.json"


def run_local_ci(pr: int | None, head: str | None) -> dict[str, Any]:
    """Run `mise run check:all` on a clean checkout (at PR `pr`'s `head`, when given) and record the pass by commit; refuse a
    check off the head, on a changed tree, failing, or changing the tree, recording nothing."""

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
    if head and before[0] != head:
        raise Refused(
            f"the checkout is at {before[0]}, PR #{pr}'s head is {head}: push, or check out the head"
        )
    if before[1]:
        raise Refused(f"the tree has changes, so the check would not run on the head:\n{before[1]}")
    command, env = " ".join(LOCAL_CI), local_ci_env()
    code = subprocess.run(LOCAL_CI, check=False).returncode
    if code:
        raise Refused(f"{command} exited {code}: nothing recorded")
    if state() != before:
        raise Refused(
            f"{command} changed the checkout, so it did not run on the head as pushed:\n{state()[1]}"
        )
    record = {
        "head": before[0],
        "command": command,
        "exit": code,
        "env": env,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": socket.gethostname(),
    }
    where = recorded(before[0])
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(record, indent=2) + "\n")
    return record


def local_ci_env() -> dict[str, str | None]:
    """The value of each variable loop.md's `local_ci_env` names, None for one unset; {} without the setting."""
    names = settings(project()[1]).get("local_ci_env", [])
    if bad := [name for name in names if not re.fullmatch(r"[A-Za-z_]\w*", name)]:
        raise Refused(
            f"loop.md's setting `local_ci_env` names {bad[0]!r}, which is no variable name"
        )
    return {name: os.environ.get(name) for name in sorted(names)}


def env_line(env: dict[str, str | None]) -> str:
    """The comment's line naming the environment the check ran under; unset names are left out."""
    named = [f"{name}={value}" for name, value in env.items() if value is not None]
    return f"Env: {' '.join(named) or 'default'}\n"


def reusable(head: str) -> dict[str, Any] | None:
    """A recorded pass on exactly `head` with today's command and environment, or None. A record without `env` (0.23.1
    wrote none) never matches, since nothing says what tier it ran."""
    try:
        record = json.loads(recorded(head).read_text())
    except (OSError, ValueError):
        return None
    # the posting path reads time and host too: a record without them is a miss, not a crash
    if not isinstance(record, dict) or not all(
        isinstance(record.get(key), str) for key in ("time", "host")
    ):
        return None
    same = (record.get("head"), record.get("command"), record.get("exit"), record.get("env")) == (
        head,
        " ".join(LOCAL_CI),
        0,
        local_ci_env(),
    )
    return record if same else None


def local_ci(pr: int | None) -> int:
    """With a PR: post a pass on its head, from a recorded run on that head and command or from a run now. Without
    one: run the check on HEAD and record it, for `local-ci <pr>` to reuse."""
    if pr is None:
        record = run_local_ci(None, None)
        print(f"{CHECKED} on {record['head']}: recorded in {recorded(record['head'])}")
        return 0
    head = pull_request(pr)["headRefOid"]
    record = reusable(head)
    if record:
        source = f"From the recorded run at {record['time']}, not run again.\n"
    else:
        record = run_local_ci(pr, head)
        source = ""
    comment(
        pr,
        f"{CHECKED}\nHead: {head}\nCommand: {record['command']}\n{env_line(record['env'])}{source}",
    )
    return 0


def brief(pr: int, priorities: Path | None, proofs: list[Path]) -> int:
    """Print a verifier pass's brief (lead.md step 7) with its facts read from the PR, so none is a previous pass's: the
    verifier role, the base (the merge-base with the default branch), the head, the spec, the pass (one after the
    newest verdict review's) and its report path, from pass 2 the previous report and its head, then the priorities
    file as is and loop.md's `## Verifier brief`. A proof log whose first line isn't the head is refused, since the
    verifier counts a stale proof as missing and spends the pass on it."""
    _, loop = project()
    pull = pull_request(pr)
    head = pull["headRefOid"]
    if missing := [str(log) for log in proofs if not log.is_file()]:
        raise Refused(f"PR #{pr}: no proof log at {', '.join(missing)}")
    # byte for byte, as lead.md's `head -1 <log> | grep -qx <head>` compares: a trailing space or CR is another line
    if stale := [
        str(log) for log in proofs if log.read_bytes().split(b"\n", 1)[0] != head.encode()
    ]:
        raise Refused(
            f"PR #{pr}: stale proof, its first line isn't the head {head}: {', '.join(stale)}; rerun it"
        )
    reviewed = passes(pull)
    if isinstance(reviewed, str):
        raise Refused(f"PR #{pr} {reviewed}")
    number = max((n for _, n, _ in reviewed), default=0) + 1
    base = merge_base(pull["baseRepository"]["defaultBranchRef"]["name"], head)
    issues = sorted(
        {issue["number"] for issue in pull["closingIssuesReferences"]["nodes"]}
        | set(named(pull["body"] or ""))
    )
    role = os.path.relpath(Path(__file__).resolve().parents[1] / "verifier.md")
    lines = [
        f"Review PR #{pr} as the verifier, pass {number}, following {role}.",
        f"- Base: {base}",
        f"- Reviewed head: {head}",
        f"- Spec: {', '.join(f'#{n}' for n in issues) or 'none linked'}",
        f"- Report: tmp/loop/pr{pr}-v{number}.md",
    ]
    if reviewed:
        newest = next(commit for commit, n, _ in reversed(reviewed) if n == number - 1)
        lines.append(
            f"- Previous report: tmp/loop/pr{pr}-v{number - 1}.md, on {newest}: review the diff since that head and"
            " rerun its repros"
        )
    lines += [f"- Proof log: {log} (its first line is the head)" for log in proofs]
    if priorities is not None:
        lines += ["", "Priorities:", priorities.read_text().rstrip()]
    # as written, but for the blank lines around it: indentation may be a snippet's
    if (own := section(loop or "", "Verifier brief").strip("\n")).strip():
        lines += ["", own]
    print("\n".join(lines))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    checking = commands.add_parser("check")
    checking.add_argument("point", choices=("build", "merge", "queue"))
    checking.add_argument("pr", type=int, nargs="?")
    checking.add_argument("--head")
    checking.add_argument("--issue", type=int)
    batching = commands.add_parser("batch")
    batching.add_argument("pr", type=int)
    batching.add_argument("--merge", required=True)
    batching.add_argument("--batch", required=True)
    batching.add_argument("--exit", type=int, required=True)
    batching.add_argument("--log", type=Path, required=True)
    approving = commands.add_parser("approve")
    approving.add_argument("point", choices=POINTS)
    approving.add_argument("number", type=int)
    # an agent never approves: a record is a person's word, and the owner's policy in loop.md covers the rest
    approving.add_argument("--by", choices=("owner",), required=True)
    delegating = commands.add_parser("delegate")
    delegating.add_argument("pr", type=int)
    posting = commands.add_parser("verdict")
    posting.add_argument("pr", type=int)
    posting.add_argument("report", type=Path)
    reading = commands.add_parser("report")
    reading.add_argument("report", type=Path)
    recording = commands.add_parser("local-ci")
    recording.add_argument("pr", type=int, nargs="?")
    recording.add_argument("--record", action="store_true")
    merging = commands.add_parser("land")
    merging.add_argument("pr", type=int)
    merging.add_argument("--wait", action="store_true")
    briefing = commands.add_parser("brief")
    briefing.add_argument("pr", type=int)
    briefing.add_argument("--priorities", type=Path)
    briefing.add_argument("--proof", type=Path, action="append", default=[])
    releasing = commands.add_parser("release")
    releasing.add_argument("issue", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "report":  # reads a local file only, so no remote needs choosing
            return report_check(args.report)
        one_repo()
        if args.command == "check":
            if args.point == "queue" and (args.pr is None or args.head is None):
                raise Refused(
                    "check queue takes a PR number and --head <sha>, the head the queue would merge"
                )
            if args.point != "queue" and args.head is not None:
                raise Refused("--head goes with check queue only")
            if args.issue is not None and (args.point != "build" or args.pr is not None):
                raise Refused("--issue goes with check build and no PR number")
            return check(args.point, args.pr, args.head, args.issue)
        if args.command == "batch":
            return batch(args.pr, args.merge, args.batch, args.exit, args.log)
        if args.command == "approve":
            return approve(args.point, args.number)
        if args.command == "delegate":
            return delegate(args.pr)
        if args.command == "local-ci":
            if (args.pr is None) != args.record:
                raise Refused(
                    "local-ci takes a PR number, or --record to record a run on HEAD before one exists"
                )
            return local_ci(args.pr)
        if args.command == "land":
            return land(args.pr, args.wait)
        if args.command == "brief":
            return brief(args.pr, args.priorities, args.proof)
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
