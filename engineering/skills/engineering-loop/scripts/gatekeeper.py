#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Gatekeeper (engineering-loop): every step leaves proof on the forge, and this checks it before the loop moves on.

    uv run scripts/gatekeeper.py check <build|merge> [pr]  # one line per missing proof, exit 1; waiting: exit 3
    uv run scripts/gatekeeper.py check build --issue <n>   # before the PR exists: the issue's build proofs; exit 0 or 1
    uv run scripts/gatekeeper.py check queue <pr> --head <sha>  # may that head enter a batching merge queue; exit 0 or 1
    uv run scripts/gatekeeper.py batch <pr> --merge <sha> --batch <sha> --exit <n> --log <path>  # the queue's proof
    uv run scripts/gatekeeper.py land <pr> [--wait]         # every merge proof, then ready and merge; exit 0, 1 or 3
    uv run scripts/gatekeeper.py record approval <spec|plan> <issue> --by owner   # on the owner's word
    uv run scripts/gatekeeper.py delegate <pr>              # the delegated approver's approved:merge, feature branch only
    uv run scripts/gatekeeper.py record verdict <pr> <report>  # post a verifier report as a PR review
    uv run scripts/gatekeeper.py report [--json] <report>   # read a verifier report as verdict does; posts nothing
    uv run scripts/gatekeeper.py brief <pr> [--priorities <file>] [--proof <log>]...  # a verifier pass's brief
    uv run scripts/gatekeeper.py record checks [--all] <pr>  # run `checks.check` (`checks.all`) on the PR head, post it
    uv run scripts/gatekeeper.py record checks [--all]      # the same on HEAD before a PR; `record checks <pr>` reuses it
    uv run scripts/gatekeeper.py release <issue>            # parked or dropped: remove the assignee the loop added

Today's verbs stay for one release line, as does scripts/approvals.py, which runs this file: `approve` is `record
approval`, `verdict` is `record verdict`, and `local-ci <pr>` and `local-ci --record` are `record checks --all <pr>`
and `record checks --all`. Exit codes, for every verb: 0 allowed or done, 1 refused (one line per missing proof), 3
waiting (run it again).

Run anywhere in the checkout: it reads docs/agents/ at the checkout's root. The policy is gatekeeper.md's block under
`## Policy`; without that file, loop.md's block under `## Settings`, with a deprecation line on stderr, and with both a
policy in each is refused, naming both, since two sources of the bar would drift. "loop.md's" setting below means the
policy's, in whichever file holds it. The project's `mise run loop:approvals
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
A repo without docs/agents/gatekeeper.md or loop.md has no rules: each issue needs only `approved:spec` and no `needs-owner`, with no
approval record. Without docs/agents/issue-tracker.md no label's shape is checked.
`check merge` adds the PR's, whose absence fails (exit 1): the `## Evidence` section of its body; the keyword linking
each issue, where loop.md has a `signoff` rule (below); the verifier's PR
reviews, a review counting only when its body starts `Verifier (<family>), pass <n>` (same-family included) and the
PR's author, the account running this or an account that can write to the repo posted it, since anyone can review a
public repo: every one on the newest
pass's commit says `SATISFIED: yes` with 0 blocker and 0 major, and that commit is the head itself, since every
commit after a verdict needs one of its own; on a high-risk change (below), that pass came from the default tier, not
one whose heading names `mid` or `small` (a `Verifier model:` tier, verifier.md), since a lower tier's review is enough
only for a change it rates low; no unresolved
review thread; no review whose latest state is `CHANGES_REQUESTED`; and a newest `## Demo` comment, where a trusted
author posted one, that embeds its videos as user-attachments (`demo.sh`), which `check build` checks too. Then it waits (exit 3, one line per wait; the approvals workflow maps it to a `pending`
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
(`BEHIND`) or conflicts with it (`DIRTY`): merge the base in, rerun the gates and get a verdict on the merge. Behind a
base whose rules require a merge queue, or already in its queue, is no refusal, since the queue tests the PR on top of
the base and every entry ahead of it: approved PRs land at once, each queued without waiting for another's merge. While
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
`local-ci` runs the policy's `checks.all`, a shell command, else `mise run check:all`, only on a clean checkout at
the PR head, and records nothing if the check fails or changes the tree. `record checks` does the same with
`checks.check`, else `mise run check`, and with `--all` is `local-ci`; a record is reused only for the same command.
A pass also leaves a record keyed by commit under the git common dir (`approvals/local-ci/<sha>.json`: head, command,
exit, env, time, host), which every worktree sees and nothing commits; `local-ci --record` makes one on HEAD with no PR.
`env` holds the value, or null for unset, of each variable loop.md's `local_ci_env` names, since a
check that reads them may run a different tier under each. When the record for the PR's exact head holds exit 0, the
same command and the same env, `local-ci <pr>` posts the pass from it, naming its time, instead of running the
check again; a record without env is never reused. The host stays in the record: nothing `approvals.py` posts names
it, and posted text writes the home directory `~` (public), since a public board would show both. The posted comment names the env it ran under (`Env: A=1 B=x`, unset
names left out, or `Env: default`).
A project may land through a batching merge queue of its own (merge every waiting PR's head onto the base, run the
full gate once on the result, push the batch) instead of one `land` per PR, opting in with `batch_queue: true` under
loop.md's `loop`; without it `check queue` refuses and no batch proof counts, so a project that never set one up gets
no second way to satisfy the CI wait. `check queue <pr> --head <sha>` exits 0
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
Every comment and review `approvals.py` posts is checked first against a local deny list, the file the environment
variable `LOOP_DENY_LIST` names (denied): a line naming a listed term refuses the post before any call to GitHub.
`report --json` prints, as one JSON object, the facts of a report `verdict` would post: `head`, `counts` (`blocker`,
`major`, `minor`), `satisfied` (true for `SATISFIED: yes`), `risk` (`level` `low`, else `high` as the gate reads any
other word, and its `reason`), `findings` (each `id`, `severity`, `path`, `line`, `title`, `body`) and `question`,
the text of `<report>.question` beside it, else null; a report `verdict` would refuse is refused the same way, exit 1.
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
changed, and `approve` minimizes as outdated each earlier record, which it supersedes. With `owner: <login>` under
loop.md's `loop`, `check build`, `check merge` and `land` record an `approved:spec` (or `approved:plan`) label that
login added after the spec's (plan's) last edit as `approve --by owner` would, removing `needs-owner`, and say so: the
label is the owner's word. One they added before the last edit is named and changes nothing, nor does anyone else's.

The policy block (SKILL.md § Settings), YAML, holds the owner's standing policy, checked against SCHEMA: a
section or key it doesn't know or a value of the wrong type is refused, naming the key, and so is a file without
the block. `checks` holds `changed`, `check` and `all`, the project's check commands. `loop` holds `cap`, `ci`, `opt_out`, `local_ci_env`, `batch_queue` and `owner`; `spec` holds `auto`.
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
`components` and `categories` (tracker_settings).
It reads and writes the tracker, the forge and the evidence only through their ports (PORTS), each an adapter the
policy's `adapters` section names (`tracker`, `forge`, `evidence`), `github` for one it doesn't: github_adapter.py,
through `gh`. A name no adapter has is refused, naming it. The status the approvals workflow posts may be named
`loop:approvals` or `gatekeeper` (the template posts both for one release line): `check merge` never waits for
either, and `land` reruns either's run. Stdlib, and PyYAML for the settings block (SKILL.md § Settings says how it
is delivered).
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import functools
import importlib.util
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
from types import ModuleType
from typing import Any

try:
    import yaml
except ImportError:  # run as `python3 approvals.py` where PyYAML isn't installed
    sys.exit(
        f"{Path(sys.argv[0]).name} needs PyYAML: run it with `uv run {sys.argv[0]}`, which installs it"
    )


def sibling(name: str) -> ModuleType:
    """The module `<name>.py` beside this file, loaded by path, so two copies of the gatekeeper in one process (a
    project's and an installed one) each load their own and none is found on sys.path by accident."""
    spec = importlib.util.spec_from_file_location(
        f"{__name__}.{name}", Path(__file__).with_name(f"{name}.py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Ports: the gatekeeper reaches a tracker, a forge and an evidence store only through these operations, each a
# function of an adapter's `tracker`, `forge` or `evidence` (github_adapter.py's are the reference). An item is an issue
# or a PR, by number; reads return nodes shaped as github_adapter.py's ISSUE and PULL queries read them, and a failed
# call raises subprocess.CalledProcessError with the tool's reason as its stderr.
# ponytail: GitHub's node shapes are the data model; give the ports their own when a second adapter needs them.
PORTS = {
    # issue_node(n), issues(numbers) (those that are issues), comment(n, body), label(n, name, add), assign(n, login, add)
    "tracker": ("issue_node", "issues", "comment", "label", "assign"),
    # the PR and its head, files, merged PRs, required checks, merge settings, who may write, and the merge itself
    "forge": (
        "pull_request",  # (pr) -> the PR node, with its reviews, checks, comments and closing issues
        "current_pr",  # () -> the checkout's branch's PR number, or None
        "pr_changes",  # (pr) -> each file the PR changes, with its patch
        "merged_pull",  # (pr) -> the merged PR with its merge commit, or None
        "merge_base",  # (base, head) -> the commit the PR's diff starts from
        "diff_lines",  # (base, head) -> per file, the lines a review at head can comment on
        "tree",  # (sha) -> {path: (mode, blob)} of the commit, or None when too large
        "head_pushed",  # (pull) -> when the head was pushed to the PR's branch, or None
        "merged_labelled",  # (branch, name) -> the merged PRs into branch carrying the label
        "required_checks",  # (base) -> the checks the base requires
        "queue_required",  # (base) -> whether the base requires a merge queue
        "auto_merge_allowed",  # () -> whether the repo allows auto-merge
        "viewer",  # () -> the account running this, or None when the forge won't say
        "writer",  # (login) -> whether the account can write to the repo
        "repository",  # (remote URL) -> the `owner/repo` it names on this forge, or None
        "preflight",  # () -> why this checkout can't reach the forge, or None
        "ready",  # (pr) -> marks a draft ready
        "merge",  # (pr, head, auto=False) -> merges pinned to head, or turns auto-merge on
        "dequeue",  # (pr node id) -> takes the PR out of the merge queue
        "run",  # (run id) -> the CI run as {status, url}, or None
        "rerun",  # (run id) -> runs it again
    ),
    # approval records, check passes and batch proofs (record), an outdated record (supersede), a verdict (post_review);
    # they are read back among the item's comments and reviews
    "evidence": ("record", "supersede", "post_review"),
}
github = sibling("github_adapter")
ADAPTERS: dict[str, Any] = {"github": github}
# the adapter of each port: GitHub's, but while main() runs, the policy's `adapters` once a port is first called
GITHUB = {name: getattr(github, name) for name in PORTS}
using: dict[str, Any] | None = GITHUB


def adapters(policy: str | None) -> dict[str, Any]:
    """Each port's adapter, by the policy's `adapters` names (`github` for one it doesn't name); an unknown name, or an
    adapter lacking an operation of its port, is refused naming it."""
    named = settings(policy).get("adapters", {})
    chosen = {}
    for name, operations in PORTS.items():
        adapter = named.get(name, "github")
        if adapter not in ADAPTERS:
            raise Refused(
                f"{source(policy)}'s `adapters.{name}` names {adapter!r}, which no adapter implements:"
                f" {', '.join(sorted(ADAPTERS))}"
            )
        chosen[name] = getattr(ADAPTERS[adapter], name, None)
        if missing := [op for op in operations if not hasattr(chosen[name], op)]:
            raise Refused(f"the {adapter} adapter's {name} lacks {', '.join(missing)}")
    return chosen


def port(name: str) -> Any:
    global using
    if using is None:
        using = adapters(project()[1])
    return using[name]


def through(name: str, operation: str) -> Callable[..., Any]:
    """`operation` of port `name`, called on the adapter in use at the call."""
    return lambda *args, **kwargs: getattr(port(name), operation)(*args, **kwargs)


issue_node, issues_of = through("tracker", "issue_node"), through("tracker", "issues")
label, assign = through("tracker", "label"), through("tracker", "assign")
pull_request, current_pr = through("forge", "pull_request"), through("forge", "current_pr")
pr_changes, merged_pull = through("forge", "pr_changes"), through("forge", "merged_pull")
merge_base, diff_lines = through("forge", "merge_base"), through("forge", "diff_lines")
tree, head_pushed = through("forge", "tree"), through("forge", "head_pushed")
required_checks, queue_required = (
    through("forge", "required_checks"),
    through("forge", "queue_required"),
)
auto_merge_allowed = through("forge", "auto_merge_allowed")
viewer, writer, repository = (
    through("forge", "viewer"),
    through("forge", "writer"),
    through("forge", "repository"),
)
supersede = through("evidence", "supersede")

# the ready state: an approved spec (board: Ready); waiting for the owner
READY, NEEDS_OWNER = "approved:spec", "needs-owner"
BUG, EPIC = "kind:bug", "epic"
CATEGORIES = {BUG, "kind:enhancement", "kind:chore", "kind:documentation"}
# a component's label is `area:<name>` and a category's `kind:<name>`; the docs name them bare or in full (qualified)
PREFIXES = {"component": "area:", "category": "kind:"}
SIZE_ORDER = ["size:XS", "size:S", "size:M", "size:L", "size:XL"]
SIZES = set(SIZE_ORDER)
TRACKER, LOOP = Path("docs/agents/issue-tracker.md"), Path("docs/agents/loop.md")
# the gatekeeper's policy, under `## Policy`; loop.md's `## Settings` block is read without it, deprecated
POLICY = Path("docs/agents/gatekeeper.md")
POINTS = ("spec", "plan")
# the `By:` of the delegated approver's merge record (delegate), which owner_waits refuses on the default branch
DELEGATE = "delegate"
MERGE_LABEL = "approved:merge"
# a change's consequences, not its urgency (that is the tracker's priority): set by a person or at triage, or by the gate
RISK_LABEL = "risk:high"
# a follow-up an agent raised: SKILL.md § Triage puts this line on every issue an agent files
FOUND_WHILE = re.compile(r"^[ \t>*-]*Found while[ \t]+#\d+", re.MULTILINE | re.IGNORECASE)
# check merge's exit while it waits for `check` or the owner; argparse's usage error is 2
WAITING = 3
# a verifier pass's PR review starts with this; same-family included, as `Verifier (claude, same-family), pass 2`
PASS = re.compile(r"Verifier \((.+?)\), pass (\d+)")
# a tier below the default a `Verifier model:` line names, a word of its own after the signature in the review's
# family (`codex/terra-6.1/med mid`, verifier.md): a model id holding the word (`sol-mid-preview`) names no tier
LOWER_TIER = re.compile(r"(?<![^\s,])(mid|small)(?![^\s,])", re.IGNORECASE)
# The cap, the last pass the loop runs on its own (a core finding open after it goes to the owner), is defined once:
# its default in SKILL.md § The cap, a project's own in loop.md's `cap` setting.
CAP_DEFAULT = re.compile(r"^The cap is (\d+) passes\b", re.MULTILINE)
# the first line of the record claim() leaves when it assigns an issue, which release() reads
ASSIGNED = "Assigned: @"
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
# the gate's own status, posted under both names for one release line (the project template's workflow)
STATUSES = {APPROVALS, "gatekeeper"}
RUN = re.compile(r"/actions/runs/(\d+)")
# a URL in a `## Demo` comment; gh's --attach embeds a video as a bare user-attachments one, which plays inline
URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+")
ATTACHMENT = "https://github.com/user-attachments/"
# land --wait: seconds between reads of the PR, and how long it waits in all before it exits 3
POLL, CEILING = 30, 2 * 60 * 60
# what land --wait polls for: CI on the head, GitHub's auto-merge, or its merge state
ON_CI, ON_MERGE = "CI on the head", "GitHub to merge it (auto-merge or the merge queue)"
ON_STATE = "GitHub to compute its merge state"
# GitHub sometimes builds a merge-group commit and never tells Actions: the entry then waits for the queue's own check
# timeout. ponytail: a fixed 10 minutes with no check suite; a loop.md setting if a project's CI is slower to start.
STUCK = 10 * 60
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
        "batch_queue": bool,
        "owner": str,
    },
    "spec": {"auto": SPEC_KINDS},
    "practice": dict.fromkeys(STAGES, str),
    "risk": {"always": bool, "labels": list, "paths": list, "verifier": bool},
    "plan": {"always": bool, "labels": list},
    "signoff": {"always": bool, "labels": list, "paths": list},
    "bot": {"paths": list, "branch": str},
    "land": Table(signed_squash_to=str, allowed_signers=str),
    "carry_over_main": Table({"except": list}),
    # the project's check commands, each a shell command: `all` is what local-ci runs
    "checks": {"changed": str, "check": str, "all": str},
    # the adapter of each port (PORTS), `github` for one not named
    "adapters": {"tracker": str, "forge": str, "evidence": str},
}
# docs/agents/issue-tracker.md's settings: in each section every key is a name, its value a description or a new name
TRACKED: dict[str, Any] = dict.fromkeys(
    ("components", "categories", "labels", "renames", "board"), str
)
# the settings block: a docs/agents/ file's first fenced `yaml` block, under its `## Settings` (gatekeeper.md: `## Policy`)
# heading
SETTINGS = re.compile(r"^```yaml[ \t]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)
KINDS = {bool: "true or false", int: "a whole number", list: "a list of strings", str: "a string"}


class Policy(str):
    """docs/agents/gatekeeper.md's text, whose block settings() reads under `## Policy`; a plain str is loop.md's,
    read under `## Settings`."""


def source(policy: str | None) -> str:
    """The file the policy was read from, as its messages name it."""
    return "gatekeeper.md" if isinstance(policy, Policy) else "loop.md"


def block(text: str, file: str, heading: str = "Settings") -> dict[str, Any]:
    """The file's settings block, parsed as YAML; refused without one under `## <heading>`, since a file still on the
    line form would otherwise lose its settings unnoticed, or when it is no YAML mapping. Only that section is
    searched, so a YAML example elsewhere in the prose is never read as the settings. A key set twice is refused,
    since YAML would keep the last one silently."""
    found = SETTINGS.search(section(text, heading))
    if found is None:
        raise Refused(
            f"{file} has no ```yaml settings block under ## {heading}: SKILL.md § Settings has its keys"
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
    """The policy's block (gatekeeper.md's `## Policy`, a Policy, else loop.md's `## Settings`), checked against
    SCHEMA: `loop`'s keys at the top level, every other section under its name and `bot` a list of `{login, paths}`;
    {} without either file, which has no rules. A file without the block is refused rather than read as one without
    rules, since a project still on the line form would otherwise lose its risk rules unnoticed."""
    if loop is None:
        return {}
    file = source(loop)
    data: dict[str, Any] = {}
    parsed = block(loop, file, "Policy" if isinstance(loop, Policy) else "Settings")
    for name, section in sections(parsed, file).items():
        if name == "bot":
            for login, bot in section.items():
                where = f"bot.{login}"
                if not isinstance(login, str):
                    raise Refused(f"{file}'s `{where}` is no name: quote it")
                if bot is None:  # a login with nothing under it
                    bot = {}
                if not isinstance(bot, dict):
                    raise Refused(f"{file}'s `{where}` must be a section holding `paths`")
                if "paths" not in bot:
                    raise Refused(f"{file}'s `{where}` lacks `paths`")
                data.setdefault("bot", []).append(
                    {"login": login, **typed(bot, SCHEMA["bot"], where, file)}
                )
        elif name == "loop":
            data.update(typed(section, SCHEMA["loop"], name, file))
        elif name in SCHEMA:
            data[name] = typed(section, SCHEMA[name], name, file)
        else:
            raise Refused(f"{file} has an unknown settings section `{name}`")
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


def headed(
    node: dict[str, Any], heading: str, keep: Callable[[dict[str, Any]], bool] = lambda _note: True
) -> dict[str, Any] | None:
    """The last comment whose first line is `heading`, among those `keep` takes: `## Specification notes` is no
    `## Spec`. A leading `> 🤖 AI` line (github.md) is skipped, so an agent's marked comment is still found."""
    found = [
        note
        for note in notes(node)
        if re.sub(r"\A\s*> 🤖 AI[ \t]*\n\s*", "", note["body"]).strip().split("\n", 1)[0].rstrip()
        == heading
        and keep(note)
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


def demo_form(pull: dict[str, Any]) -> list[str]:
    """A line when the PR's newest `## Demo` comment by a trusted author, not minimized as outdated, links a video
    (a release asset, any URL but a user-attachments one) instead of embedding it, or embeds none; a PR with no
    demo has none. A stranger's demo neither holds nor clears the merge."""
    shown = lambda note: not note.get("isMinimized") and trusted(pull, note)
    demo = headed(pull, "## Demo", shown) if "comments" in pull else None
    if demo is None:
        return []
    urls = URL.findall(demo["body"])
    linked = [url for url in urls if not url.startswith(ATTACHMENT)]
    if not linked and urls:
        return []
    what = f"links {linked[0]}" if linked else "embeds no video"
    return [
        (
            f"PR #{pull['number']}: its `## Demo` comment {what}: post the demo with the demo skill's"
            " `scripts/demo.sh`, which embeds each video as an attachment that plays inline"
        )
    ]


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
    found += demo_form(pull)
    if point != "merge":
        return found
    where = f"PR #{pull['number']}"
    evidence = section(pull["body"] or "", "Evidence")
    if not evidence.strip():
        found.append(f"{where}: its body has no `## Evidence` section with content")
    if loop is not None:
        found += linked(pull, issues, loop)
    if revert is None and not exempt(pull, loop):
        verdicts = passes(pull)
        found += (unreviewed := reviewed(where, pull, loop, verdicts))
        # only on a verdict that would land, and tier first, since risk() reads the reviews again
        if not unreviewed and (tier := lower(verdicts)) and (why := risk(pull, issues, loop)):
            found.append(
                f"{where} is high risk ({why}), and its newest verdict came from a lower tier ({tier}): a"
                " default-tier verifier pass on the head first"
            )
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
    # the lines read, plus the heading's family, which names the verifier's tier when it ran below the default
    trusted = {(pull.get("author") or {}).get("login"), viewer() if found else None} - {None}
    others = {(review.get("author") or {}).get("login") for review in found} - trusted - {None}
    trusted |= {login for login in others if writer(login)}
    return [
        (
            ((review.get("commit") or {}).get("oid") or "").lower(),
            int(PASS.match(review["body"])[2]),
            {
                "Family": PASS.match(review["body"])[1],
                **{
                    key.strip(): value.strip()
                    for key, _, value in (
                        line.partition(":") for line in review["body"].splitlines()
                    )
                    if key.strip() in ("VERDICT", "SATISFIED", "Risk")
                },
            },
        )
        for review in found
        if (review.get("author") or {}).get("login") in trusted
    ]


def lower(verdicts: list[tuple[str, int, dict[str, str]]] | str) -> str | None:
    """The tier below the default (LOWER_TIER) the newest verifier pass names in its heading's family, the newest
    commit's highest pass (a mixed PR's two verifiers share one), or None: a heading naming no tier reads as the
    default, so verdicts written before tiers were named keep landing. `verdicts` is passes()'s."""
    if isinstance(verdicts, str) or not verdicts:
        return None
    head = verdicts[-1][0]
    on_head = [(number, lines) for commit, number, lines in verdicts if commit == head]
    last = max(number for number, _ in on_head)
    tiers = [
        found[1]
        for number, lines in on_head
        if number == last and (found := LOWER_TIER.search(lines["Family"]))
    ]
    return tiers[0].lower() if tiers else None


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


def reviewed(
    where: str,
    pull: dict[str, Any],
    loop: str | None,
    verdicts: list[tuple[str, int, dict[str, str]]] | str | None = None,
) -> list[str]:
    """One line per reason the verifier's PR reviews (passes) let nothing land: the newest pass is not on the head,
    since every commit after a verdict needs one of its own, unless the head carries that commit's proofs (carried,
    which prints a line either way where loop.md opts in), or on its commit the highest pass (a mixed PR's two
    verifiers share one, and a later pass on the same commit supersedes an earlier one) is not satisfied, or has a
    blocker or a major open. A triage or comment is no verdict. An allow-listed bot's lock- or manifest-only PR
    needs none (exempt). `verdicts` is passes()'s, when the caller has read it."""
    verdicts = passes(pull) if verdicts is None else verdicts
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


def batch_queue(loop: str | None) -> bool:
    """Whether loop.md opts into a batching merge queue (`batch_queue: true` under `loop`), without which no batch
    proof stands in for the CI wait: a project that never set one up gets no second way to satisfy it."""
    return settings(loop).get("batch_queue") is True


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
        return f"{where} targets {pull['baseRefName']}, but the policy lands signed squashes only to {branch}"
    if pull["autoMergeRequest"] is not None or pull["isInMergeQueue"]:
        return f"{where}: auto-merge or the merge queue would merge it with GitHub's signature: turn it off"
    # the URL as configured, before any `insteadOf` rewrite
    origin = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=False
    )
    if repository(origin.stdout.strip()) != pull["baseRepository"]["nameWithOwner"].lower():
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
        f"PR #{pull['number']} is outside the loop ({source(loop)} `opt_out: true`, no verifier review, spec approval,"
        " revert or bot exemption): its author merges it"
    )


def ran(pull: dict[str, Any], loop: str | None, required: set[str] | None = None) -> list[str]:
    """One line per check the merge waits for on the head: ci()'s `required` (None: the base branch's required checks but
    `loop:approvals`, or the aggregate `check` when that leaves none), or with `ci: false` a local-ci pass."""
    where = f"PR #{pull['number']}"
    if batch_queue(loop) and queued(pull) is None:
        return []
    if no_ci(loop):
        # the merge proof is the full check: a `record checks` pass of the lighter `checks.check` proves nothing here
        full = settings(loop).get("checks", {}).get("all", LOCAL_CI)
        head = [CHECKED, f"Head: {pull['headRefOid']}", f"Command: {full}"]
        if any(
            [line.strip() for line in note["body"].strip().splitlines()[:3]] == head
            and trusted(pull, note)
            for note in notes(pull)
        ):
            found = []
        else:
            found = [
                f"{where}: the project has no CI ({source(loop)} `ci: false`), and no local check passed on the head (approvals.py local-ci)"
            ]
    else:
        if required is None:
            # the approvals status is check merge's own output: waiting for it never ends
            required = required_checks(pull["baseRefName"]) - STATUSES or None
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
    if not batch_queue(loop):
        print(
            f"{where}: {source(loop)} doesn't opt into a batching merge queue (`batch_queue: true` under `loop`), so it lands"
            " through `land`"
        )
        return 1
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
    prove(pr, body)
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


# the environment variable naming the local deny list (denied), a file kept outside the repo
DENY_LIST = "LOOP_DENY_LIST"


def denied(text: str) -> None:
    """Refuse to post `text` when it names a term of the local deny list: the file `LOOP_DENY_LIST` names, one term per
    line (a name, a repo slug, a hostname; `#` starts a comment), matched ignoring case at word boundaries, since a
    public repo's comment keeps its first text in GitHub's edit history for good. Without the variable nothing is
    checked; a list it names that can't be read refuses, since an unread list would let every post through."""
    if not (where := os.environ.get(DENY_LIST)):
        return
    try:
        listed = Path(where).expanduser().read_text().splitlines()
    except OSError as exc:
        raise Refused(
            f"{DENY_LIST} names {where}, which can't be read ({exc.strerror}): nothing posted"
        ) from exc
    terms = [term for line in listed if (term := line.split("#", 1)[0].strip())]
    for number, line in enumerate(text.splitlines(), 1):
        for term in terms:
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", line, re.IGNORECASE):
                raise Refused(
                    f"refused to post: line {number} names `{term}` from the deny list ({DENY_LIST}); nothing posted"
                )


def texts(data: str) -> list[str]:
    """The text GitHub will publish from a post's `data`: every string a JSON payload holds, decoded (a review's body
    and its inline comments), else the data itself (a comment's body)."""
    try:
        found: list[Any] = [json.loads(data)]
    except ValueError:
        return [data]
    strings = []
    while found:
        value = found.pop()
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, dict | list):
            found.extend(value.values() if isinstance(value, dict) else value)
    return strings


def closing_issues(pull: dict[str, Any]) -> list[dict[str, Any]]:
    """GitHub's closing references plus every `#n` after a closing keyword, `Part of` or `Implements` in the body: GitHub sometimes
    never links a closing line, and has no API to set the link."""
    issues: list[dict[str, Any]] = pull["closingIssuesReferences"]["nodes"]
    unlinked = sorted(set(named(pull["body"] or "")) - {issue["number"] for issue in issues})
    return issues + issues_of(unlinked)


def public(text: str) -> str:
    """`text` as posted: the home directory written `~`, since a path under it (a log's, a cache's) names the person
    whose machine posted it, and GitHub's edit history keeps a comment's first text for good."""
    home = str(Path.home()).rstrip("/")
    return re.sub(re.escape(home) + r"(?![\w.-])", "~", text) if home else text


def posted(body: str) -> str:
    """`body` as posted (public), refused first when it names a term of the deny list."""
    body = public(body)
    for text in texts(body):
        denied(text)
    return body


def comment(number: int, body: str) -> None:
    """Comment on an issue or PR (tracker)."""
    port("tracker").comment(number, posted(body))


def prove(number: int, body: str) -> None:
    """Leave a proof on an issue or PR (evidence): an approval record, a check pass, a batch proof."""
    port("evidence").record(number, posted(body))


def post_review(pr: int, review: dict[str, Any]) -> None:
    """Post a verdict as a PR review (evidence), every text in it as posted."""
    # unescaped, so public() finds a non-ASCII home as GitHub will decode it
    port("evidence").post_review(pr, json.loads(posted(json.dumps(review, ensure_ascii=False))))


def one_repo() -> None:
    """Refuse a checkout that can't reach the forge (preflight)."""
    if why := port("forge").preflight():
        raise Refused(why)


def merged_high(branch: str) -> list[int]:
    """The merged PRs into `branch` that carry `risk:high` (flag() adds it to each high-risk PR that lands)."""
    return port("forge").merged_labelled(branch, RISK_LABEL)


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
    """The checkout's docs/agents/issue-tracker.md and its policy, None for one it lacks: a repo without the files has
    no rules, and its issues no label shape. The policy is gatekeeper.md's (a Policy), else loop.md's `## Settings`
    block, read with a deprecation line; a project with both is refused, since two sources of the bar would drift.
    Settings off their schema are refused here, before any proof is printed or any PR touched."""
    root = toplevel()
    tracker, loop, policy = (
        read(root / path) if (root / path).exists() else None for path in (TRACKER, LOOP, POLICY)
    )
    if policy is not None:
        if loop is not None and SETTINGS.search(section(loop, "Settings")):
            raise Refused(
                f"both {POLICY} and {LOOP}'s ## Settings hold a policy: keep it in {POLICY} alone"
            )
        loop = Policy(policy)
    elif loop is not None:
        deprecated()
    settings(loop)
    if tracker is not None:
        tracker_settings(tracker)
    return tracker, loop


@functools.cache
def deprecated() -> None:
    """One line per run, however often the policy is read."""
    print(
        f"{LOOP}'s ## Settings is deprecated: move the block to {POLICY} under ## Policy (SKILL.md § Settings)",
        file=sys.stderr,
    )


def adopted(issues: list[dict[str, Any]], loop: str | None) -> list[dict[str, Any]]:
    """The issues, each read again after recording an `approved:<point>` label the owner (loop.md's `owner`) added
    after the spec's or plan's last edit as their approval (approve), which also removes `needs-owner`, printing a line
    for each; a label the owner added before that edit gets a line saying so and changes nothing, nor does anyone
    else's. Without `owner` nothing is read, since only the owner's own label is their word."""
    owner = settings(loop).get("owner")
    if not owner:
        return issues
    found = []
    for issue in issues:
        number, recorded = issue["number"], False
        for point in POINTS:
            holder = spec_holder(issue) if point == "spec" else headed(issue, "## Plan")
            name = f"approved:{point}"
            if holder is None or name not in names(issue):
                continue
            value = version(holder)
            if current(issue, point, point, value, "owner"):
                continue
            added = [
                event
                for event in events(issue, "LabeledEvent")
                if (event.get("label") or {}).get("name") == name
            ]
            # GitHub logins are case-insensitive: `Octocat` in loop.md names the account `octocat`
            if (
                not added
                or (added[-1].get("actor") or {}).get("login", "").lower() != str(owner).lower()
            ):
                continue
            if added[-1]["createdAt"] <= (holder.get("lastEditedAt") or holder["createdAt"]):
                print(
                    f"#{number}: the owner's `{name}` was added before the {point}'s last edit ({value}): the"
                    " owner adds it again"
                )
                continue
            approve(point, number, value)
            recorded = True
            print(
                f"#{number}: recorded the owner's `{name}`, added after the {point}'s last edit, as their approval"
            )
        found.append(issue_node(number) if recorded else issue)
    return found


def gated(
    point: str, pull: dict[str, Any], tracker: str | None, loop: str | None
) -> tuple[list[str], list[dict[str, Any]]]:
    """Every missing proof at `point`, and the issues the PR names (none for an exact revert, which needs no spec: risk()
    reads its issues from `named` and the reverted PR's risk from `reverted` instead)."""
    revert, found = reverts(pull)
    if revert:
        pull["named"], pull["reverted"] = closing_issues(pull), reverted(revert)
        return found + proofs(point, pull, [], loop, revert), []
    issues = adopted(closing_issues(pull), loop)
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
    issues, pull = adopted([issue_node(number)], loop), unopened()
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
    waits, its Actions run is rerun: exit 3. A head in conflict with its base, or behind one that requires no
    merge queue while the PR is not in its queue, is refused first.
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
    # GitHub says this as a required check `expected`. A merge queue tests the PR on top of the base and every entry
    # ahead of it, so behind is no reason to stop there: PRs landing at once each stay queued as the others merge.
    stale = STALE_BASE.get(pull["mergeStateStatus"])
    if (
        stale
        and pull["mergeStateStatus"] == "BEHIND"
        and (pull["isInMergeQueue"] or queue_required(pull["baseRefName"]))
    ):
        stale = None
    if stale:
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
    checks = head_checks(pull, required)[0]  # ran() already waits for a draft-only skip
    red = [(name, state) for name, state in checks if state not in GREEN]
    # GitHub merges once the required checks pass; a red one it never merges past. The owner's label and a local-ci
    # record are no check of GitHub's, so either hold ends the wait below instead.
    if watching and auto and not owner and not (no_ci(loop) and checking):
        if not RED.intersection(state for _, state in red):
            if stuck(pull):
                try:
                    port("forge").dequeue(pull["id"])
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
        port("forge").ready(pr)
        print(f"{where} is ready now: CI starts on ready, run land again")
        return WAITING, ON_CI
    if not checking + owner and local:
        commit = signed_squash(pull, local[1])
        print(f"{where} landed in {pull['baseRefName']} as {commit}, signed by a key in {local[1]}")
        return 0, None
    if not checking + owner:
        port("forge").merge(pr, head)
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
        port("forge").merge(pr, head, auto=True)
        print(f"{where}: auto-merge on at {head}, once {', '.join(sorted(required))} pass")
        return 0, ON_MERGE
    statuses = [
        node
        # a head no check ran on has a null rollup
        for node in (
            pull["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
            or {"contexts": {"nodes": []}}
        )["contexts"]["nodes"]
        if node.get("__typename") == "StatusContext" and node.get("context") in STATUSES
    ]
    # Resolving a review thread starts no workflow, so the FAILURE the approvals workflow posted while one was open
    # stays on the head. When every proof holds and that status is all that waits, run its workflow again.
    if (
        statuses
        and not owner
        and not no_ci(loop)
        and required <= {name for name, _ in checks}
        and red
        and {name for name, _ in red} <= STATUSES
        and all(state in RED for _, state in red)
    ):
        said = " and ".join(f"`{name}` is {state}" for name, state in sorted(red))
        stale = f"{where}: every proof holds but {said} on the head commit"
        found = RUN.search(max(statuses, key=started).get("targetUrl") or "")
        if found is None:
            print(
                f"{stale}, and the status names no Actions run to rerun:"
                " rerun the workflow that posts it, then run land again"
            )
            return WAITING, None
        # gh resolves the id in this checkout's repo; a target naming another repo's run, or one that is gone, fails
        run = port("forge").run(found[1])
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
        port("forge").rerun(found[1])
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


def approve(point: str, number: int, seen: str | None = None) -> int:
    """Record the owner's approval of the issue's current spec or plan, on their word: the record, the label, and
    `needs-owner` removed. Every earlier record of the point is superseded and minimized. With `seen`, the version
    the owner's label was checked against (adopted), an edit since is refused: the label never covered it."""
    issue = issue_node(number)
    holder = spec_holder(issue) if point == "spec" else headed(issue, "## Plan")
    if holder is None:
        raise Refused(f"#{number} has no `## Plan` comment to approve")
    value = version(holder)
    if seen is not None and value != seen:
        raise Refused(
            f"#{number}: the {point} was edited ({value}) after the owner's `approved:{point}`: the owner adds it again"
        )
    record = f"{point.capitalize()}: {value}\n"
    earlier = [
        (note, found) for note in notes(issue) if (found := parsed(note["body"], point)) is not None
    ]
    if any(found.get("by") == "owner" and found.get(point) != value for _, found in earlier):
        record += CHANGED[point]
    prove(number, f"Approved: {point}\nBy: owner\n{record}")
    for note, _ in earlier:
        if not note.get("isMinimized") and note.get("viewerCanMinimize"):
            supersede(note["id"])
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
        prove(number, f"Approved: merge\nBy: {DELEGATE}\n")
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


def report_check(report: Path, as_json: bool = False) -> int:
    """Check a verifier report the way `verdict` reads it, posting nothing, so the verifier fixes it before replying;
    with `as_json`, print its facts (facts) instead of the line saying it reads."""
    parsed = parse_report(report)
    print(
        json.dumps(facts(report, *parsed), ensure_ascii=False)
        if as_json
        else f"{report} reads as a verdict"
    )
    return 0


def facts(
    report: Path,
    _heading: str,
    head: str,
    found: list[tuple[str, str, str, str, str, str]],
    closing: list[str],
    _qualifier: str,
) -> dict[str, Any]:
    """A parsed report's facts, read as the gate reads its review (held, judged): the head, the counts, whether it is
    satisfied, the risk (`low`, else `high`, as any other word or none reads) and its reason, each finding, and the
    question the verifier left beside it (`<report>.question`), or None."""
    verdict_line, satisfied, judgment = closing
    said = judgment.partition(":")[2].strip()
    low = re.match(r"low\b", said, re.IGNORECASE)
    question = report.with_name(report.name + ".question")
    return {
        "head": head,
        "counts": dict(
            zip(("blocker", "major", "minor"), map(int, COUNTED.fullmatch(verdict_line).groups()))
        ),
        "satisfied": satisfied.partition(":")[2].strip().lower().split()[:1] == ["yes"],
        "risk": {
            "level": "low" if low else "high",
            "reason": re.sub(r"^\S+\s*[—–:-]?\s*", "", said),
        },
        "findings": [
            dict(zip(("id", "severity", "path", "line", "title", "body"), finding))
            for finding in found
        ],
        "question": read(question) if question.is_file() else None,
    }


def verdict(pr: int, report: Path) -> int:
    """Post a verifier report as a PR review on the commit it reviewed: one inline comment per finding, at the nearest
    line of the diff when its line is outside it, in the review's body when its file is."""
    heading, head, found, closing, qualifier = parse_report(report)
    denied(report.read_text())  # before any read of GitHub, not only at the post
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


# the checks `record checks` runs without the policy's `checks.check`, and with --all (local-ci) its `checks.all`
CHECK, LOCAL_CI = "mise run check", "mise run check:all"


def local_ci_command() -> str:
    """The policy's `checks.all`, else LOCAL_CI: the command local-ci runs and records."""
    return settings(project()[1]).get("checks", {}).get("all", LOCAL_CI)


def check_command() -> str:
    """The policy's `checks.check`, else CHECK: the command `record checks` runs without --all."""
    return settings(project()[1]).get("checks", {}).get("check", CHECK)


def recorded(head: str) -> Path:
    """Where a local-ci pass on `head` is recorded: the git common dir, which every worktree of the clone shares and no
    commit carries."""
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    return common / "approvals" / "local-ci" / f"{head}.json"


def run_local_ci(pr: int | None, head: str | None, command: str | None = None) -> dict[str, Any]:
    """Run `command`, else the project's full check (local_ci_command), on a clean checkout (at PR `pr`'s `head`, when given) and record the pass by commit; refuse a
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
    command, env = command or local_ci_command(), local_ci_env()
    code = subprocess.run(command, shell=True, check=False).returncode
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
    """The value of each variable the policy's `local_ci_env` names, None for one unset; {} without the setting."""
    policy = project()[1]
    names = settings(policy).get("local_ci_env", [])
    if bad := [name for name in names if not re.fullmatch(r"[A-Za-z_]\w*", name)]:
        raise Refused(
            f"{source(policy)}'s setting `local_ci_env` names {bad[0]!r}, which is no variable name"
        )
    return {name: os.environ.get(name) for name in sorted(names)}


def env_line(env: dict[str, str | None]) -> str:
    """The comment's line naming the environment the check ran under; unset names are left out."""
    named = [f"{name}={value}" for name, value in env.items() if value is not None]
    return f"Env: {' '.join(named) or 'default'}\n"


def reusable(head: str, command: str | None = None) -> dict[str, Any] | None:
    """A recorded pass on exactly `head` with `command` (else today's local_ci_command) and environment, or None. A record without `env` (0.23.1
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
        command or local_ci_command(),
        0,
        local_ci_env(),
    )
    return record if same else None


def local_ci(pr: int | None, command: str | None = None) -> int:
    """With a PR: post a pass on its head, from a recorded run on that head and `command` (else local_ci_command) or
    from a run now. Without one: run the check on HEAD and record it, for `local-ci <pr>` to reuse."""
    if pr is None:
        record = run_local_ci(None, None, command)
        print(f"{CHECKED} on {record['head']}: recorded in {recorded(record['head'])}")
        return 0
    head = pull_request(pr)["headRefOid"]
    record = reusable(head, command)
    if record:
        source = f"From the recorded run at {record['time']}, not run again.\n"
    else:
        record = run_local_ci(pr, head, command)
        source = ""
    prove(
        pr,
        f"{CHECKED}\nHead: {head}\nCommand: {record['command']}\n{env_line(record['env'])}{source}",
    )
    return 0


def brief(pr: int, priorities: Path | None, proofs: list[Path]) -> int:
    """Print a verifier pass's brief (lead.md step 7) with its facts read from the PR, so none is a previous pass's: the
    verifier role, the base (the merge-base with the default branch), the head, the spec, the pass (one after the
    newest verdict review's) and its report path, from pass 2 the previous report and its head, then the priorities
    file as is and loop.md's `## Verifier brief`, read from loop.md where the policy is gatekeeper.md's. A proof log whose first line isn't the head is refused, since the
    verifier counts a stale proof as missing and spends the pass on it."""
    _, loop = project()
    if isinstance(loop, Policy):
        loop = read(toplevel() / LOOP) if (toplevel() / LOOP).exists() else None
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
    recording = commands.add_parser("record").add_subparsers(dest="proof", required=True)
    # today's verbs, each the same as its `record` form, for one release line
    for approving in (commands.add_parser("approve"), recording.add_parser("approval")):
        approving.add_argument("point", choices=POINTS)
        approving.add_argument("number", type=int)
        # an agent never approves: a record is a person's word, and the owner's policy in loop.md covers the rest
        approving.add_argument("--by", choices=("owner",), required=True)
    for posting in (commands.add_parser("verdict"), recording.add_parser("verdict")):
        posting.add_argument("pr", type=int)
        posting.add_argument("report", type=Path)
    checking = recording.add_parser("checks")
    checking.add_argument("pr", type=int, nargs="?")
    checking.add_argument("--all", action="store_true")
    delegating = commands.add_parser("delegate")
    delegating.add_argument("pr", type=int)
    reading = commands.add_parser("report")
    reading.add_argument("report", type=Path)
    reading.add_argument("--json", action="store_true")
    local = commands.add_parser("local-ci")
    local.add_argument("pr", type=int, nargs="?")
    local.add_argument("--record", action="store_true")
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
    global using
    using = None  # the policy's adapters, read at the first port call
    try:
        if args.command == "report":  # reads a local file only, so no remote needs choosing
            return report_check(args.report, args.json)
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
        if args.command == "record" and args.proof == "checks":
            return local_ci(args.pr, local_ci_command() if args.all else check_command())
        if args.command == "approve" or args.command == "record" and args.proof == "approval":
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
    finally:
        using = GITHUB


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
