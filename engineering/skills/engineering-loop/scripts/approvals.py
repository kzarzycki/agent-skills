#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Approvals (engineering-loop): every step leaves proof on GitHub, and this checks it before the loop moves on.

    uv run scripts/approvals.py check <build|merge> [pr]  # one line per missing proof, exit 1; waiting: exit 3
    uv run scripts/approvals.py check build --issue <n>   # before the PR exists: the issue's build proofs; exit 0 or 1
    uv run scripts/approvals.py check queue <pr> --head <sha>  # deprecated: may that head enter a project's own queue
    uv run scripts/approvals.py batch <pr> --merge <sha> --batch <sha> --exit <n> --log <path>  # deprecated: its proof
    uv run scripts/approvals.py land [<pr>] [--wait]       # land every landable PR as one gated batch; exit 0, 1 or 3
    uv run scripts/approvals.py approve <spec|plan> <issue> --by owner   # on the owner's word
    uv run scripts/approvals.py approve merge <pr> --head <sha> --by owner [--withdraw]  # the owner's go on that head
    uv run scripts/approvals.py delegate <pr>              # the delegated approver's approved:merge, feature branch only
    uv run scripts/approvals.py verdict <pr> <report>      # post a verifier report as a PR review
    uv run scripts/approvals.py report <report>            # check a verifier report as verdict reads it; posts nothing
    uv run scripts/approvals.py brief <pr> [--priorities <file>] [--proof <log>]...  # a verifier pass's brief
    uv run scripts/approvals.py local-ci <pr>              # with `ci: false`: run `mise run check:all` on the PR head
    uv run scripts/approvals.py local-ci --record          # the same on HEAD, the gate before each push; reused by tree
    uv run scripts/approvals.py local-ci --status <head>   # the detached run on a head: running (exit 3), passed, failed
    uv run scripts/approvals.py local-ci --record --head-proof  # the same under the caller's tier: loop.md's head proof
    uv run scripts/approvals.py release <issue>            # parked or dropped: remove the assignee the loop added

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
or for a spec the policy approves the account running this), since an assignee says whose the issue is; and, with a
PR, an issue another open PR closes too (a closing keyword, or `Implements` under a `signoff` rule), naming that PR
and its branch, since each build runs its own verifier, gate and queue. When every build proof holds, it assigns each issue no one holds to its approver, comments a record that the loop did, and gives
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
`ci: false` in loop.md, a `local-ci` pass on the head's tree under today's gate command, read as `local-ci` reads
it below, instead; its comment is the trace, never the proof), and, while the change is high risk, for the owner's
go on that head: the newest commit status `owner` on the head commit by the account running this or a writer is
green, and the PR holds the owner's record (`Approved: merge`, `By: owner`, `Head: <sha>`) naming that head.
`approve merge <pr> --head <sha> --by owner` posts both on the owner's word, the record's every word the script
writes, refusing a head other than the one named, which is the one the owner was shown; `--withdraw` posts a newer
failing status and a `Withdrawn: merge` record and removes the `approved:merge` label. A status belongs to one
commit, so no push carries the go to a head the owner didn't see. Into the default branch that is the only go: a
label is anyone's with triage rights, the delegated approver's included, so `approved:merge` there is no go, nor is
an `owner` status an older gate wrote from the label (marked as from it). On a change that is not high risk the
label means nothing. High risk is `risk:high` on the
PR or an issue it names, a risk rule matching (below) unless under `spec.auto: true`, or a review at the cap or later not satisfied or
with a blocker or major open (`cap`, SKILL.md § The cap); when the gate infers it, `check merge` and `land` add `risk:high` to the PR, reporting a
failure to add it and carrying on. On a PR into a feature branch (any base but the repository's default branch)
`approved:merge` added after the head was pushed is a go too, the push time being GitHub's repository activity for
the head branch; a label added before the push is no go, and the approvals workflow removes it on `synchronize`. There
the label may be the delegated approver's: `delegate <pr>` adds it, then a record (`Approved: merge`,
`By: delegate`), and refuses a PR into the default branch, whose merge only the owner approves. A PR from a branch
into the default branch is high risk while any PR merged into that branch carries `risk:high`, so a feature
branch's merge waits for the owner.
Every proof held: exit 0. Before the PR exists, `check build` judges the issue `--issue <n>` names, else the one
the branch's name starts a segment with (`loop/329-fix`), the same way, and claims nothing; with neither it exits 1,
since a build needs an approved spec. `check merge` with no PR yet: exit 0.
With `opt_out: true` in loop.md, a person may keep their PRs out of the loop: `check merge` on a PR that
left no loop trail (no verifier review, no `Approved: spec` record or `approved:spec` on an issue it links, no
`Reverts #<n>` line, not an exempt bot PR) prints that it is outside the loop and exits 0, so the approvals
workflow posts success and its author merges it their usual way; `land` never takes it into a batch, and named,
prints the same line and exits 1, so the loop never merges it. Risk rules and `risk:high` hold no such PR. `check build` is
unchanged. A spec a policy covers is no trail, since under `spec.auto: true` every issue is covered.
`land [<pr>]` is the one way an agent merges. It lands every landable PR into one base, the named PR's or else the
repository's default branch, as one batch:
1. It takes the landing lock: it pushes a commit with no parent (the base's tree, titled `landing lock`, with its pid
and a random value, so two lands in the same second never make the same commit and both push it) to
`refs/loop/landing` on `origin`, which refuses a second such push while the ref is there, as no fast-forward, so two
hosts never land at once; a ref outside `refs/heads/` starts no workflow. The lock's commit date is its age. Held by
another: exit 3, naming its age. One older than 2 hours is stale, left by a land that died: it is deleted and taken. The
lock is released at the end whatever happened, but only while it is still ours, so a stale one broken and taken by
another land stays theirs.
2. The candidates, oldest PR first, are every open PR into the base from this repository, not a draft, that holds every
proof of `check merge` but its CI wait, is not outside the loop (`opt_out`, below), has the owner's go where it is high
risk, and has the checks the base requires on GitHub (`required_checks`, but `loop:approvals`, which is check merge's
own output) green on its head. Under `ci: false` the head needs no `local-ci` pass of its own: the gate on the batch is
the proof. With loop.md's `head_proof`, the head also carries its head proof (below), else it is no candidate and `land`
names the command that records it. `land <pr>` on a draft marks it ready first, never on a missing proof, since ready starts CI; while the
checks that starts are required, it waits (exit 3). A named PR that is no candidate says why: a missing proof exits 1,
a wait for the owner or a pending required check 3, a red required check 1.
3. In a temporary worktree of `origin/<base>` under the git common dir, removed after, it first runs loop.md's
`pre_land`, where set, for each candidate: a command parsed as `gate` is, run there at the base's tip with `LAND_HEAD`
(the PR's head) and `LAND_BASE` (that tip) set, so the base's tree holds the check and a PR never changes what judges
it. A non-zero exit leaves that PR out of this batch, with a comment, once per head, holding the check's output; it is
not red, so it is neither evicted nor turned back to draft. Then it merges each candidate's head
(`git merge --no-ff`). A PR that conflicts is skipped, with a comment, once per head, saying it conflicts with the base
plus the PRs merged before it, so it needs the base merged in.
4. It gates the result's tree. A pass is reused when the gate command passed on that tree before (reusable, below):
this clone's record, or a `gate` status on a candidate's head with that same tree, so one PR already up to date with
the base runs no gate. GitHub's required checks never stand in for it, since the pass is then published as the gate
command's. Otherwise it runs the gate there as `local-ci` does (below), its log under the git common dir, and records
the pass by tree; a gate that leaves the worktree changed is red, since it no longer ran on the batch as merged.
5. Green: it merges each PR through GitHub in that order, pinned to its head (`gh pr merge --squash
--match-head-commit`). A merge GitHub refuses, or leaves unmerged (a base requiring a merge queue only queues it, to
merge later on a tree no gate saw), stops there: that PR and those after it wait for the next land. Then it fetches
and compares the base's tree with the gated tree. Equal: the pass is published as the `gate` status on the new tip.
Different, because a refusal left only part of the batch on the base or someone merged by hand meanwhile: it says
which, gates the tip, and publishes only a pass. Each PR landed gets one comment, `Landed`, then `Base:` the new tip,
`Tree:` the tree it landed (the base with it and the PRs before it merged), `Gate:` the command, `run` or `reused`,
and the tree it passed on, and `Batch:` the PRs landed together.
6. Red: it lands one PR at a time instead, each merged onto the last green commit and gated alone. A PR red alone is
gated once more (green then is a flake, and it lands), then evicted: back to draft, so later batches leave it out until
`land <pr>` marks it ready again, and a comment holding its log's last 30 lines. When the first PR alone is red twice,
the bare base is gated: red, the run stops (exit 1) and evicts nobody, since every PR would fail on that base.
With loop.md's `machine_exit` (78, say), a gate run in steps 4 and 6 exiting with it is the machine's fault, not the
tree's: it runs once more on the same tree, and a second such exit stops the run (exit 1), landing nothing, evicting
nobody and posting nothing, and prints the log's last 30 lines: fix the machine, then land again.
Exit 0 when the named PR merged, or with no PR named when nothing landable failed; 1 for a refusal, a conflict, an
eviction, a merge GitHub refused or a red base; 3 while it waits. `land --wait` runs it again every 30 seconds while it
waits on the lock or on CI, printing each new state once, for up to 2 hours, then exits 3; a wait for the owner ends it
at once, since only the owner clears it.
With loop.md's `land` section (`signed_squash_to: <branch>`, `allowed_signers: <path>`), for a repo that trusts only
commits signed by its maintainers' keys (GitHub signs its own squash with GitHub's key), the batch is the same, but each
PR lands as a squash made in this checkout instead: one commit holding the tree it lands, on the base's tip the
batch was merged onto (or the squash before it), so each commit holds its own PR's change, titled `<PR title> (#<pr>)`, signed with the checkout's SSH key
(`gpg.format ssh`, `user.signingkey`) and checked with `git verify-commit` against the allowed signers file. It pushes
that commit to the PR's branch, pinned to the head the gates checked, then fast-forwards the base to it, so GitHub shows
the PR merged. A base that moved since the batch was merged is refused, since the squash would drop what landed
meanwhile; a base push refused puts the PR's branch back on its head. It is no candidate when it comes from another
repository (its branch isn't ours to push), targets a base other than the section's, has auto-merge or the merge queue
on (GitHub would sign that squash), or when `origin` isn't the PR's repo, the checkout signs nothing or the signers file
is missing. Without the section nothing changes.
`check queue`, `batch` and loop.md's `batch_queue`, `carry_over_main` and `ci` work as below for one more release, each
printing one `deprecated:` line on stderr, so a project's own queue keeps running until it adopts `land`.
`local-ci` runs only on a clean checkout at the PR head, and records nothing if the check fails or changes the tree.
The check is the gate: loop.md's `gate` under `loop` (default `mise run check:all`), variables it sets in front of
its command included (`GATE_UI_TESTS=0 mise run check:all`), one command run with no shell, so an operator
such as `&&` is refused. It runs with every name loop.md's `local_ci_env` lists
removed from the environment unless the command sets it, so a host's ambient tier never changes what ran and the
command alone says what a pass proves. A pass also leaves a record keyed by tree and command under the git common dir
(`approvals/local-ci/<tree>-<key>.json`: head, tree, command, exit, env, time, host, `head` being the commit it ran
on, `env` the variables the command sets, `<key>` a digest of the command), which every worktree sees and nothing
commits; `local-ci --record` makes one on HEAD with no PR. On a checkout with changes `--record` runs the check, records
nothing and exits with the check's code, so it is the gate while iterating too and its clean green run, the last one,
records itself.
Unless it already leads its own session, `local-ci` starts itself again in a new one, stdin from /dev/null, and follows
it, exiting with its exit code: a caller killed with its process group (a harness capping a background command) leaves
the check running, and it still records its pass or failure. Beside the records it writes `<head>.log` (its output),
`<head>.pid` (its pid and start time, so a pid the system has given another process reads as gone) and, once it
ends, `<head>.exit` (its exit code), keyed by the commit it started on. A `local-ci` on a head whose run is still going
follows that run instead of starting another (after it, one with other arguments runs its own), and `local-ci --status
<head>` says whether it is running (exit 3), passed (0, only when a pass on the head's tree is recorded) or failed (1,
naming the exit), with the log's path. The run's stderr goes to the same log, so a caller prints the check's stderr and
a refusal (`exited N: nothing recorded`) on its stdout. Stopping the caller, Ctrl-C included, leaves the run going:
`kill -- -<pid>`, with the pid `<head>.pid` holds, stops its process group.
Every pass this clone holds, run or reused, is published as a commit status on the head it covers:
success, context `gate`, description `Tree <tree> on <commit's first 12>: <command>` (the command's digest, `sha256 <key>`, when
it doesn't fit GitHub's 140 characters), since `gh`'s token can write a status where a check run needs a GitHub App.
GitHub refusing it (a commit not pushed yet) or unreachable is said and changes nothing else: the record stays local,
and a later `local-ci` publishes it. A pass is reusable for a commit when this clone's record for its tree holds exit
0 under today's command, or when a `gate` status on that commit itself names its tree and today's command, posted by
the account running this or a writer, since anyone who can only open a PR must never publish a pass; so any host
reuses it, and adding a name to `local_ci_env` keeps every pass. `local-ci <pr>`, `local-ci --record`, `land`, `check
queue`, `batch` and `check merge` read it the same way; the posted comment then says it was reused by tree from the
pass recorded on that commit, and when, instead of running the check again. A refusal for a missing pass names each
other command the tree passed under, from this clone's records and the head's statuses, and today's. The host stays
in the record: nothing `approvals.py` posts names it, and posted text writes the home directory `~` (public), since a
public board would show both. The posted comment names the gate's command and the variables it sets (`Env: A=1`, or
`Env: default`).
With loop.md's `head_proof` under `loop` (`status: <context>`, `env: [<names>]`), each head proves itself under a tier
the lead picks, which the batch gate's fixed tier doesn't. `local-ci --record --head-proof` runs the gate as `--record`
does, but takes each `env` name the caller's environment sets from it instead of clearing it, over the gate line's own
assignment of that name, so the command it records names the value (`GATE_UI_TESTS=smoke mise run check:all`). It
publishes the pass as the commit status `<context>` instead of `gate`, described `Tree <tree> on <commit's first 12>:
<name>=<value> ...` for the `env` names it ran with (`default` for none), so the verifier reads the tier off the head.
`land` reads it as it reads `gate`: a green status of that context on the head commit itself, naming the head's tree,
by the account running this or a writer. A status on an older head never counts, since a status belongs to one commit.
Which tier a change needs is the project's rule; `land` checks only that a head proof exists.
Deprecated: a project may land through a batching merge queue of its own (merge every waiting PR's head onto the base, run the
full gate once on the result, push the batch) instead of one `land` per PR, opting in with `batch_queue: true` under
loop.md's `loop`; without it `check queue` refuses and no batch proof counts, so a project that never set one up gets
no second way to satisfy the CI wait. `check queue <pr> --head <sha>` exits 0
when that head may enter it: it is the PR's head, every proof of `check merge` holds but the CI wait, which the queue's
gate on the batch replaces, the head has its own `local-ci --record` pass under the current env (which `batch` needs) and,
with CI, the checks `check merge` waits for passed, and a high-risk change has the owner's go on that head
(owner_waits, as `check merge` and `land` read it), which the queue checks again before it merges it. After its gate the queue posts `batch` on
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
Deprecated: with loop.md's `carry_over_main` section (`except: <globs>`), merges of the base into a PR head H keep H's proofs:
each commit from the head H' down its first-parent line to H is a merge whose second parent is on the base (an
ancestor of its tip), whose tree is what `git merge-tree --write-tree` makes of its parents (no conflict resolved,
nothing added), and where the base's changes since the merge base touch no file the PR's side changes and no path an
`except` glob matches (fnmatch, as a rule's `paths`: the project's merge-check configuration, such as lint, type,
test and gate config and lockfiles). So a PR commit after H, new, edited or rebased, carries nothing. Then H's newest
verdict covers H' (`check merge`, `check queue` and `land`, the verifier's `Risk:` line included). It never carries
a `local-ci` record: H' runs its own gate, as CI would run on it. `check merge` and `land` print one line per merge
naming it, its first parent and the predicate, or why the head carries nothing. A git error, a second merge base or
any failed condition carries nothing: the head needs its own verdict, as without the section, where `check merge` and `land` read no git for it.
Every comment and review `approvals.py` posts is checked first against a local deny list, the file the environment
variable `LOOP_DENY_LIST` names (denied): a line naming a listed term refuses the post before any call to GitHub.
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
the block. `loop` holds `cap`, `ci`, `opt_out`, `gate`, `local_ci_env`, `batch_queue`, `owner`, `machine_exit`,
`pre_land` and `head_proof`; `spec` holds `auto`.
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
import fcntl
import fnmatch
import functools
import hashlib
import io
import itertools
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
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
# the gatekeeper's policy, under `## Policy`; loop.md's `## Settings` block is read without it, deprecated
POLICY = Path("docs/agents/gatekeeper.md")
POINTS = ("spec", "plan")
# the `By:` of the delegated approver's merge record (delegate), which owner_waits refuses on the default branch
DELEGATE = "delegate"
MERGE_LABEL = "approved:merge"
# the owner's go on a high-risk head, a commit status on that one commit (approve merge), so no push carries it over
OWNER_GO = "owner"
# how an OWNER_GO status the gate once turned from the `approved:merge` label ends: no go, since the label can be a
# delegate's
LABELLED = f"from their `{MERGE_LABEL}` label"
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
# a tier below the default a `Verifier model:` line names, a word of its own after the signature in the review's
# family (`codex/terra-6.1/med mid`, verifier.md): a model id holding the word (`sol-mid-preview`) names no tier
LOWER_TIER = re.compile(r"(?<![^\s,])(mid|small)(?![^\s,])", re.IGNORECASE)
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
PULL = f"""id number title isCrossRepository author {{ __typename login }} {ASSIGNEES} state isDraft autoMergeRequest {{ enabledAt }} isInMergeQueue body baseRefName baseRefOid headRefName headRefOid baseRepository {{ nameWithOwner defaultBranchRef {{ name }} }} labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}
  files(first: 100) {{ totalCount nodes {{ path changeType }} }} latestReviews(first: 100) {{ nodes {{ state author {{ login }} }} }}
  reviews(last: 100) {{ totalCount nodes {{ author {{ login }} state body commit {{ oid }} }} }}
  reviewThreads(first: 100) {{ totalCount nodes {{ isResolved }} }}
  authored: commits(first: 100) {{ totalCount nodes {{ commit {{ authors(first: 5) {{ totalCount nodes {{ user {{ login }} }} }} committer {{ user {{ login }} }} }} }} }}
  timelineItems(last: 100, itemTypes: [LABELED_EVENT, READY_FOR_REVIEW_EVENT]) {{ nodes {{ __typename
    ... on LabeledEvent {{ createdAt label {{ name }} }} ... on ReadyForReviewEvent {{ createdAt }} }} }}
  commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ contexts(first: 100) {{ totalCount nodes {{
    __typename ... on CheckRun {{ name status conclusion startedAt completedAt checkSuite {{ status workflowRun {{ workflow {{ name }} }} }} }}
    ... on StatusContext {{ context state createdAt targetUrl }} }} }} }} }} }} }}
  closingIssuesReferences(first: 50) {{ nodes {{ repository {{ nameWithOwner }} {ISSUE} }} }}"""
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
# a gate pass published as a commit status: its context, and its description (described): tree, commit, command
PUBLISHED = "gate"
PASSED = re.compile(r"Tree ([0-9a-f]{40,64}) on ([0-9a-f]{7,64}): (.+)")
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
# the commit status the project's approvals workflow posts
APPROVALS = "loop:approvals"
# a URL in a `## Demo` comment; gh's --attach embeds a video as a bare user-attachments one, which plays inline
URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+")
ATTACHMENT = "https://github.com/user-attachments/"
# land --wait: seconds between tries, and how long it waits in all before it exits 3; a landing lock older than the
# ceiling is stale
POLL, CEILING = 30, 2 * 60 * 60
# the landing lock: a ref outside refs/heads/, so pushing it starts no workflow
LOCK = "refs/loop/landing"
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
        "gate": str,
        "batch_queue": bool,
        "owner": str,
        "machine_exit": int,
        "pre_land": str,
        "head_proof": Table(status=str, env=list),
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
        if isinstance(kind, dict):  # a section within the section, such as `loop.head_proof`
            if not isinstance(value, dict):
                raise Refused(f"{file}'s {where} must be a section holding `{'`, `'.join(kind)}`")
            typed(value, kind, f"{name}.{key}", file)
        elif isinstance(kind, tuple):  # true, false, or a list naming some of the tuple's values
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
            for key in ("batch_queue", "ci"):
                if key in section:
                    deprecated(key)
        elif name in SCHEMA:
            data[name] = typed(section, SCHEMA[name], name, file)
            if name == "carry_over_main":
                deprecated(name)
        else:
            raise Refused(f"{file} has an unknown settings section `{name}`")
    return data


DEPRECATED: set[str] = set()


def deprecated(name: str) -> None:
    """Say once per run, on stderr, that a command or setting goes in the next release: a project's own queue keeps
    working until it adopts the batch `land`."""
    if name not in DEPRECATED:
        DEPRECATED.add(name)
        print(
            f"deprecated: {name} goes in the next release; land batches every landable PR (#650)",
            file=sys.stderr,
        )


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
    if not on_head and found and isinstance(carry := carried(pull, loop, found[-1][0]), tuple):
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


def closed(pull: dict[str, Any], repo: str, loop: str | None) -> set[int]:
    """The issues of `repo` a PR finishes: GitHub's closing references there and each `#n` after a closing keyword,
    plus `Implements` where loop.md has a `signoff` rule, which leaves the issue open only for the owner's sign-off.
    `Part of` builds on an issue without finishing it, so two PRs may share one. A reference to another repo's issue
    is a different issue, whatever its number; a body's `#n` is always `repo`'s (CLOSING)."""
    kinds = {CLOSES, IMPLEMENTS} if "signoff" in settings(loop) else {CLOSES}
    named = {n for n, kind in links(pull.get("body") or "").items() if kind in kinds}
    return named | {
        issue["number"]
        for issue in pull["closingIssuesReferences"]["nodes"]
        if issue["repository"]["nameWithOwner"].lower() == repo.lower()
    }


# how many open PRs duplicates() reads, in one call; a list that long may have left one out
OPEN_LIMIT = 1000


def open_pulls() -> list[dict[str, Any]]:
    """The repo's open PRs, up to OPEN_LIMIT, each with its number, branch, base, whether it is a draft, body and closing references (each naming its
    issue's repo as `nameWithOwner`, as the PR query does), in one call."""
    found = json.loads(
        gh(
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            str(OPEN_LIMIT),
            "--json",
            "number,headRefName,baseRefName,isDraft,body,closingIssuesReferences",
        )
    )
    for other in found:
        nodes = other["closingIssuesReferences"]
        for issue in nodes:
            where = issue["repository"]
            issue["repository"] = {"nameWithOwner": f"{where['owner']['login']}/{where['name']}"}
        other["closingIssuesReferences"] = {"nodes": nodes}
    return found


def duplicates(pull: dict[str, Any], loop: str | None) -> list[str]:
    """One line per issue the PR finishes (closed) that another open PR finishes too, naming that PR and its branch:
    two builds of one issue each run a verifier, a gate and the queue, and one of them is thrown away. A list as long
    as OPEN_LIMIT may have left that PR out, so it refuses rather than pass on a partial comparison."""
    repo = pull["baseRepository"]["nameWithOwner"]
    mine = closed(pull, repo, loop)
    if not mine:
        return []
    found = open_pulls()
    if len(found) >= OPEN_LIMIT:
        return [
            (
                f"the duplicate-build check reads at most {OPEN_LIMIT} open PRs and this repo has at least that many,"
                " so it could not see every open PR: close stale PRs, or check by hand that no other open PR closes"
                f" {', '.join(f'#{n}' for n in sorted(mine))}"
            )
        ]
    return [
        f"#{number} is also closed by open PR #{other['number']} (branch `{other['headRefName']}`): one build per"
        " issue, so close one of the PRs, or link it with `Part of`"
        for other in found
        if other["number"] != pull["number"]
        for number in sorted(mine & closed(other, repo, loop))
    ]


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
    if (
        point == "build" and "number" in pull
    ):  # before the PR exists (unopened) there is nothing to compare
        found += duplicates(pull, loop)
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
    """One line per thing the merge waits for: ran()'s checks, and the owner's go (owner_waits)."""
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


def signed_squash(pull: dict[str, Any], signers: Path, onto: tuple[str, str] | None = None) -> str:
    """Squash the PR's head onto its base here, signed with this checkout's key and checked against `signers`, then
    push it to the PR's branch and fast-forward the base to it: GitHub marks a PR merged once its head is in the
    base. The head must be the one the gates checked and contain the base's tip, so the squash undoes nothing; with
    `onto` (a commit and a tree, from land's batch), the base's tip must be that commit and the squash holds that
    tree, the merge of the head the batch gated."""
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
    if onto is not None:
        if tip != onto[0]:
            raise Refused(
                f"PR #{pr}: {base} moved to {tip} since the batch was merged onto {onto[0]}: land again"
            )
        tree = onto[1]
    elif subprocess.run(["git", "merge-base", "--is-ancestor", tip, head], check=False).returncode:
        raise Refused(
            f"PR #{pr} does not contain {base}'s head {tip}: merge origin/{base} in, rerun the gates, get a"
            " verdict on the merge (lead.md step 8), then land again"
        )
    else:
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
    `loop:approvals`, or the aggregate `check` when that leaves none), or with `ci: false` a local-ci pass on the head's
    tree under today's gate command (reusable)."""
    where = f"PR #{pull['number']}"
    if batch_queue(loop) and queued(pull) is None:
        return []
    if no_ci(loop):
        # the proof is the pass itself (reusable), never the `Local check passed` comment, which anyone who can
        # comment may write and which says nothing about today's gate command
        found = (
            []
            if reusable(pull["headRefOid"])
            else [
                (
                    f"{where}: the project has no CI ({source(loop)} `ci: false`), and no local check passed on the head"
                    f" (approvals.py local-ci){elsewhere(pull['headRefOid'])}"
                )
            ]
        )
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
    local-ci pass under the gate command, the env the proof names, since a batch gate never stands in for the head's,
    its merge commit's second parent is the head, so the head landed unchanged, its tree is the clean merge of its
    parents, so the queue resolved no conflict and added nothing, and the batch commit contains it."""
    merge, batch, code = (fields.get(key, "").lower() for key in ("Merge", "Batch", "Exit"))
    if code != "0":
        return f"the merge queue's gate on batch {batch} exited {code or 'with no exit code'}"
    if (record := reusable(head)) is None:
        return (
            f"the head {head} has no green `local-ci --record` pass of its own under the gate command, which a batch"
            f" never stands in for{elsewhere(head)}"
        )
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


def carried(
    pull: dict[str, Any], loop: str | None, verified: str
) -> tuple[str, list[str]] | str | None:
    """`verified` with one carry_line() per merge, oldest first, when the PR's head carries the verdict on
    `verified`, the newest verdict's commit, where loop.md has `carry_over_main`: from the head, each commit on its
    first-parent line down to `verified` is a merge whose second parent is on the base (an ancestor of its tip), whose
    tree is git merge-tree's of its parents, and where merged() finds the base's changes disjoint from the PR's and
    neither side's touching an except glob. So a PR commit after `verified` (new, edited or rebased) carries nothing.
    A string names why it carries nothing; None without the setting, which then reads no git at all."""
    guard = settings(loop).get("carry_over_main")
    if guard is None:
        return None
    head, tip, base = pull["headRefOid"].lower(), pull["baseRefOid"].lower(), pull["baseRefName"]
    commit, lines = head, []
    try:
        if not (fetched(head) and fetched(tip)):
            return f"the head or {base}'s head {tip} is not a commit origin has"
        while commit != verified:
            it, its = ("it", "its") if commit == head else (commit, f"{commit}'s")
            parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
            if len(parents) != 2:
                return f"{it} is no merge of two parents"
            first, second = parents
            on_base = ["git", "merge-base", "--is-ancestor", second, tip]
            if subprocess.run(on_base, capture_output=True, check=False).returncode:
                return f"{its} second parent {second} is not on {base}"
            found = merged(first, second, guard["except"], base)
            if isinstance(found, str):
                return found
            if found[0] != git("rev-parse", f"{commit}^{{tree}}").strip():
                return f"{commit}'s tree is not git merge-tree's of its parents: the merge resolved or added something"
            lines.insert(0, carry_line(commit, first, second, found[1], base))
            commit = first
    except (subprocess.CalledProcessError, OSError) as exc:
        return f"git failed reading {commit}: {exc}"
    return verified, lines


def carries(where: str, pull: dict[str, Any], loop: str | None, verified: str) -> bool:
    """Whether the PR's head carries the proofs of `verified`, the newest verdict's commit (carried), printing the
    lines that say so, or where loop.md opts in, why it carries nothing."""
    carry = carried(pull, loop, verified)
    if carry is None:
        return False
    if isinstance(carry, str):
        print(f"{where}: {pull['headRefOid']} carries nothing from {verified}: {carry}")
        return False
    for line in carry[1]:
        print(f"{where}: {line}")
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
            f"{where}: no `local-ci --record` pass on {head} under the gate command (approvals.py local-ci --record)"
            f"{elsewhere(head)}"
        )
    # the queue re-runs this before it merges the head, and check merge reads the owner's go on the landed head again
    found += owner_waits(pull, issues, loop)
    for line in found:
        print(line)
    if found:
        return 1
    print(f"{where} may enter a merge queue at {head}")
    return 0


def batch(pr: int, merge: str, batch_sha: str, code: int, log: Path) -> int:
    """Post a merge queue's batch proof on PR `pr`, which queued() reads: the head (the merge's second parent), the
    merge, the batch, the gate's exit, the head's own local-ci pass and its env, the log, and the log's last LOG_TAIL
    lines. Refused for a head with no green pass of its own under the gate command."""
    if not fetched(merge.lower()):
        raise Refused(f"merge {merge} is not a commit here or on origin")
    head = git("rev-parse", f"{merge}^2").strip()
    if (record := reusable(head)) is None:
        raise Refused(
            f"the head {head} has no green `local-ci --record` pass of its own under the gate command: no batch proof"
            f" without it{elsewhere(head)}"
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
    """A line while the change is high risk (risk) and the owner's go is not on the head (owned). Into the default
    branch only that go counts, since a delegate acting through the owner's account adds a label no differently from
    the owner; into a feature branch the `approved:merge` label, added after the head's push, counts too, the
    owner's or the delegate's (delegate). `pushed(pull)` is when the head was pushed (default: GitHub's repository
    activity)."""
    where, found = f"PR #{pull['number']}", []
    why = risk(pull, issues, loop)
    if why is None or owned(pull):
        return found
    command = f"`approve merge {pull['number']} --head {pull['headRefOid']} --by owner`"
    if default(pull):
        return [
            (
                f"{where} waits for the owner's go on its head ({command}; into {pull['baseRefName']} `{MERGE_LABEL}`"
                f" is no go), since it is high risk: {why}"
            )
        ]
    if MERGE_LABEL not in names(pull):
        return [
            (
                f"{where} waits for the owner's go on its head ({command}, or `{MERGE_LABEL}`), since it is high"
                f" risk: {why}"
            )
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


def owned(pull: dict[str, Any]) -> bool:
    """Whether the owner's go (go) is on the PR's head: the newest `owner` status there by the account running this
    or a writer (a status is the repo's to write) is green, so a later one the owner withdrew it with wins, and the
    PR holds the `Approved: merge` record by the owner naming that head. A status once turned from the label
    (LABELLED) is no go. GitHub unreachable: no go."""
    try:
        found = statuses(pull["headRefOid"])
    except (subprocess.CalledProcessError, OSError, ValueError):
        return False
    for status in found:  # newest first
        login = (status.get("creator") or {}).get("login")
        if (
            status.get("context") != OWNER_GO
            or login is None
            or not (login == viewer() or writer(login))
        ):
            continue
        return (
            status.get("state") == "success"
            and not (status.get("description") or "").endswith(LABELLED)
            and current(pull, "merge", "head", pull["headRefOid"], "owner")
        )
    return False


def go(number: int, head: str, withdraw: bool = False) -> int:
    """approve merge: the owner's go on `head`, the PR's head they were shown, on their word: the status OWNER_GO on
    that commit and a record naming it; with `withdraw`, a newer failing status and record that take it back. The
    script writes every word, so no agent's description of the change travels with it. A head that moved is refused,
    since the owner saw the one they were asked about."""
    pull = pull_request(number)
    if pull["state"] != "OPEN":
        raise Refused(f"PR #{number} is {pull['state'].lower()}: nothing to approve")
    if pull["headRefOid"].lower() != head.lower():
        raise Refused(
            f"PR #{number}'s head is {pull['headRefOid']}, not {head}: ask the owner about the head it has now"
        )
    head = pull["headRefOid"]
    if withdraw:
        # the label off too, since into a feature branch it is a go of its own
        label(number, MERGE_LABEL, add=False)
        post_status(head, OWNER_GO, f"The owner withdrew their go on {head[:12]}", state="failure")
        comment(number, f"Withdrawn: merge\nBy: owner\nHead: {head}\n")
        print(f"PR #{number}: the owner's go on {head} is withdrawn")
        return 0
    post_status(head, OWNER_GO, f"The owner's go on {head[:12]}")
    comment(number, f"Approved: merge\nBy: owner\nHead: {head}\n")
    print(f"PR #{number}: the owner's go is on {head}")
    return 0


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


def gh(*args: str, data: str | None = None) -> str:
    if data is not None:  # every comment and review approvals.py posts goes as `data`
        for text in texts(data):
            denied(text)
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
    repo on GitHub's free plan has no rulesets: that 403 reads as none, and any other error raises. A base whose rules
    require GitHub's merge queue is refused: GitHub would merge each PR later, on a tree land never gated."""
    try:
        rulesets = gh(
            "api",
            "--paginate",
            f"repos/{{owner}}/{{repo}}/rules/branches/{base}",
            "--jq",
            '.[] | if .type == "merge_queue" then ":merge_queue"'
            ' elif .type == "required_status_checks" then .parameters.required_status_checks[].context else empty end',
        )
    except subprocess.CalledProcessError as error:
        if "(HTTP 403)" not in (error.stderr or "") or PLAN_LIMIT not in error.stderr:
            raise
        print(
            f"GitHub enforces no rules on {base} here (its plan has none): land's proofs are the only gate"
        )
        rulesets = ""
    if ":merge_queue" in rulesets.split():
        raise Refused(
            f"{base}'s rules require GitHub's merge queue, which would merge each PR later on a tree land never gated:"
            " drop it from the ruleset (SKILL.md, Adopting the loop)"
        )
    protection = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/branches/{base}",
        "--jq",
        ".protection.required_status_checks.contexts // [] | .[]",
    )
    return set((rulesets + protection).split())


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
    """`text` as posted: the home directory written `~` and the temp dir `<tmp>`, pytest's `pytest-of-<user>/pytest-<n>`
    under it included, since a path under either (a log's, a cache's, a failing test's) names the person whose machine
    posted it, and GitHub's edit history keeps a comment's first text for good."""
    # the longest temp dir first and home last, since a temp dir can sit under /tmp or under home
    # ponytail: this process's temp dir and /tmp; another TMPDIR's paths stay, with only the account name masked
    tmps = {tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir()), "/tmp"}
    for tmp in sorted(filter(None, (t.rstrip("/") for t in tmps)), key=len, reverse=True):
        text = re.sub(
            r"(?<![\w.~-])" + re.escape(tmp) + r"(?:/pytest-of-[^/\s]+(?:/pytest-\w+)?)?(?![\w.-])",
            "<tmp>",
            text,
        )
    if home := str(Path.home()).rstrip("/"):
        text = re.sub(re.escape(home) + r"(?![\w.-])", "~", text)
    return re.sub(r"pytest-of-[^/\s]+", "pytest-of-<user>", text)


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


class MachineFault(Refused):
    """The gate exited with loop.md's `machine_exit` twice on one tree in `land`: the machine isn't ready."""


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
        moved()
    settings(loop)
    if tracker is not None:
        tracker_settings(tracker)
    return tracker, loop


@functools.cache
def moved() -> None:
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


def land(pr: int | None, wait: bool = False) -> int:
    """landing() once, or with `wait` again every POLL seconds while it waits on something time clears, printing each
    new state once: until it ends, or exit 3 at CEILING."""
    if not wait:
        return landing(pr)[0]
    deadline, said = time.monotonic() + CEILING, ""
    while True:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code, again = landing(pr)
        finally:
            # a background command's log: each state once, not every 30 seconds; a held lock's age is no new state
            if (state := re.sub(r"\d+ minutes? ago", "", out.getvalue())) != said:
                print(out.getvalue(), end="", flush=True)
            said = state
        if not again:
            return code
        if time.monotonic() + POLL > deadline:
            print(f"land --wait stopped after {CEILING // 3600} hours, still waiting")
            return WAITING
        time.sleep(POLL)


def landing(pr: int | None) -> tuple[int, bool]:
    """Land every landable PR into the base (PR `pr`'s, else the default branch) as one gated batch, under the landing
    lock; the exit, and whether a wait would end it (lock, CI on a head), so land --wait runs it again."""
    tracker, loop = project()
    named = None if pr is None else pull_request(pr)
    if named is not None:
        if named["state"] == "MERGED":
            print(f"PR #{pr} is merged")
            return 0, False
        if named["state"] != "OPEN":
            raise Refused(f"PR #{pr} is closed: nothing to land")
    base = (
        named["baseRefName"]
        if named
        else gh(
            "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"
        ).strip()
    )
    ours = locked(base)
    if ours is None:
        return WAITING, True
    try:
        return batched(named, base, tracker, loop)
    finally:
        # only while it is still ours: a lock broken as stale and taken by another land stays theirs
        released = subprocess.run(
            [
                "git",
                "push",
                "-q",
                "--no-verify",
                f"--force-with-lease={LOCK}:{ours}",
                "origin",
                f":{LOCK}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if released.returncode:
            print(f"the landing lock {LOCK} was not released: {' '.join(released.stderr.split())}")


def locked(base: str) -> str | None:
    """Take the landing lock: push a parentless commit of the base's tree to LOCK, which origin refuses as no
    fast-forward while another is there, so any host sees it. Its commit date is its age; one older than CEILING is
    stale, deleted and taken. Our commit, or None after saying who holds it since when."""
    git("fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
    # pid and a random value: two lands in the same second, under one identity, would otherwise build one commit,
    # and the second push of it would succeed as a no-op
    ours = git(
        "commit-tree",
        "-m",
        f"landing lock\n\npid {os.getpid()}, nonce {os.urandom(8).hex()}",
        f"refs/remotes/origin/{base}^{{tree}}",
    ).strip()
    for _ in range(2):
        pushed = subprocess.run(
            ["git", "push", "-q", "--no-verify", "origin", f"{ours}:{LOCK}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if not pushed.returncode:
            return ours
        held = git("ls-remote", "origin", LOCK).split()
        if not held:
            raise Refused(
                f"origin refused the landing lock {LOCK}: {' '.join(pushed.stderr.split())}"
            )
        try:
            git("fetch", "-q", "origin", LOCK)
            taken = int(git("log", "-1", "--format=%ct", held[0]).strip())
        except subprocess.CalledProcessError:  # released meanwhile: push again
            continue
        age = int(time.time()) - taken
        if age <= CEILING:
            print(
                f"another land holds the landing lock {LOCK}, taken {age // 60} minutes ago"
                f" ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(taken))}): land --wait waits for it"
            )
            return None
        print(
            f"the landing lock {LOCK} is {age // 3600} hours old, past {CEILING // 3600} hours: broken as stale"
        )
        subprocess.run(
            [
                "git",
                "push",
                "-q",
                "--no-verify",
                f"--force-with-lease={LOCK}:{held[0]}",
                "origin",
                f":{LOCK}",
            ],
            capture_output=True,
            check=False,
        )
    print(
        f"another land took the landing lock {LOCK} as this one broke it: land --wait waits for it"
    )
    return None


def landable(
    pull: dict[str, Any], tracker: str | None, loop: str | None, required: set[str]
) -> tuple[int, bool] | None:
    """None when the PR is a candidate for the batch: every merge proof (gated, the head's own CI or local-ci pass
    aside, since the batch's gate is the proof), no owner wait, the base's required checks green on its head, and a
    signed squash possible where loop.md asks for one. Else, after printing why, the exit it means for a named PR and
    whether a wait would clear it. A draft (only a named PR is read as one) is marked ready first."""
    where, local = f"PR #{pull['number']}", signed(loop)
    if pull["isCrossRepository"]:
        print(f"{where} comes from another repository: land merges only branches of this one")
        return 1, False
    if why := outside(pull, loop):
        # land is the loop's merge: a PR no verifier saw merges its author's way
        print(why)
        return 1, False
    found, issues = gated("merge", pull, tracker, loop)
    if found:  # never ready on a missing proof: ready starts CI
        for line in holds(pull, issues, loop) + found:
            print(line)
        return 1, False
    if (proof := head_proof(loop)) and not proved(pull["headRefOid"], proof["status"]):
        names = f", with the tier set in {', '.join(proof['env'])}" if proof["env"] else ""
        print(
            f"{where}: its head {pull['headRefOid']} has no green `{proof['status']}` status for its tree (loop.md"
            f" `head_proof`): run `approvals.py local-ci --record --head-proof` on a clean checkout of it{names}"
        )
        return 1, False
    if local and (why := unsignable(pull, *local)):
        print(why)
        return 1, False
    for line in flag(pull, issues, loop):
        print(line)
    if pull["isDraft"]:
        # CI skips a draft, and a skipped check counts as green: a draft's checks say nothing about the ready PR
        gh("pr", "ready", str(pull["number"]))
        print(f"{where} is ready now")
        if required:
            print(f"{where}: CI starts on ready, so its required checks are pending")
            return WAITING, True
    if required and (lines := ci(where, pull, required)):
        for line in lines:
            print(line)
        red = {state for _, state in head_checks(pull, required)[0]} & RED
        return (1, False) if red or any(line.endswith(PAGED) for line in lines) else (WAITING, True)
    # after CI, so the owner is never asked about a head CI could still reject
    if owner := owner_waits(pull, issues, loop):
        for line in owner:
            print(line)
        return WAITING, False  # the owner is asked, not polled
    return None


def batched(
    named: dict[str, Any] | None, base: str, tracker: str | None, loop: str | None
) -> tuple[int, bool]:
    """Under the lock: merge every candidate's head onto `base` locally, oldest PR first, gate the result's tree once
    (or reuse a pass on it), and merge each through GitHub in that order; a red batch lands one PR at a time."""
    # `loop:approvals` is check merge's own status, on the proofs land reads itself
    required = required_checks(base) - {APPROVALS}
    waits: dict[int, tuple[int, bool]] = {}
    candidates = []
    listed = {
        other["number"]
        for other in open_pulls()
        if other["baseRefName"] == base and not other["isDraft"]
    } | ({named["number"]} if named else set())
    for number in sorted(listed):
        pull = named if named and number == named["number"] else pull_request(number)
        if (why := landable(pull, tracker, loop, required)) is None:
            candidates.append(pull)
        else:
            waits[number] = why
    failed: set[int] = set()
    # each PR to land, the tree it lands, the tree gated with it, and how that passed
    landed: list[tuple[dict[str, Any], str, str, str]] = []
    if candidates:
        with batch_tree(base) as work:
            tip = run_in(work, "rev-parse", "HEAD")
            candidates = [pull for pull in candidates if pre_landed(pull, base, work, loop, failed)]
            landed = merge_batch(candidates, base, work, failed)
            if landed:
                merges(landed, base, tip, work, loop, failed)
    number = named["number"] if named else None
    if number is not None:
        if number in waits:
            return waits[number]
        return (
            (0, False)
            if any(pull["number"] == number for pull, *_ in landed) and number not in failed
            else (1, False)
        )
    if failed:
        return 1, False
    return (WAITING, True) if any(again for _, again in waits.values()) else (0, False)


@contextlib.contextmanager
def batch_tree(base: str) -> Any:
    """A detached worktree of origin's `base` under the git common dir, removed after; its gate logs stay beside it.
    Under the common dir rather than the system's temp dir, so a tool that trusts the clone's path trusts it too."""
    root = (
        Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
        / "approvals"
        / "landing"
    )
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=root))
    git("worktree", "add", "-q", "--detach", str(work), f"refs/remotes/origin/{base}")
    try:
        yield work
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(work)], capture_output=True, check=False
        )
        shutil.rmtree(work, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], capture_output=True, check=False)


def merge_batch(
    candidates: list[dict[str, Any]], base: str, work: Path, failed: set[int]
) -> list[tuple[dict[str, Any], str, str, str]]:
    """Merge the candidates onto the base in `work` and gate the result; red: one PR at a time on the last green
    commit, a PR red alone gated once more, then evicted, and when the first one is red twice the bare base gated,
    which red ends the run evicting nobody. Each PR to land, with the tree it lands (the base with it and the PRs
    before it merged), the tree gated with it, and how."""
    tip = run_in(work, "rev-parse", "HEAD")
    merged: list[dict[str, Any]] = []
    trees: list[str] = []
    for pull in candidates:
        if merged_onto(pull, work, base, [other["number"] for other in merged], failed):
            merged.append(pull)
            trees.append(run_in(work, "rev-parse", "HEAD^{tree}"))
    if not merged:
        return []
    tree, how = gate_batch(work, merged)
    if how:
        return [(pull, own, tree, how) for pull, own in zip(merged, trees, strict=True)]
    numbers = ", ".join(f"#{pull['number']}" for pull in merged)
    print(f"the batch of {numbers} is red: one PR at a time")
    green, landed, base_green = tip, [], False
    for pull in merged:
        reset(work, green)
        if not merged_onto(pull, work, base, [p["number"] for p, *_ in landed], failed):
            continue
        tree, how = gate_batch(work, [pull])
        if not how:
            print(
                f"PR #{pull['number']} is red alone on {green}: once more, in case it was a flake"
            )
            tree, how = gate_batch(work, [pull])
        if how:
            green = run_in(work, "rev-parse", "HEAD")
            landed.append((pull, tree, tree, how))
            continue
        if green == tip and not base_green:
            reset(work, tip)
            if not gate_batch(work, [])[1]:
                print(
                    f"{base} itself is red at {tip}: nothing lands and nobody is evicted until it is fixed"
                )
                failed.add(pull["number"])
                return []
            base_green = True
        evict(pull, base, green, work.parent / f"{tree}.log")
        failed.add(pull["number"])
    return landed


def run_in(work: Path, *args: str) -> str:
    return git("-C", str(work), "-c", "commit.gpgsign=false", *args).strip()


def reset(work: Path, commit: str) -> None:
    """`work` at `commit` with nothing a red gate left behind but ignored files, such as caches, so the next gate's
    tree is the commit's."""
    run_in(work, "reset", "-q", "--hard", commit)
    run_in(work, "clean", "-fdq")


CONFLICTS = "Conflicts in the landing batch"
PRE_LAND = "Refused by the pre-land check"
EVICTED = "Evicted from the landing batch"


def merged_onto(
    pull: dict[str, Any], work: Path, base: str, before: list[int], failed: set[int]
) -> bool:
    """Merge the PR's head into `work` (`git merge --no-ff`); a conflict is aborted and said once per head on the PR,
    since it needs the base merged in. `before` names the PRs merged ahead of it."""
    where, head = f"PR #{pull['number']}", pull["headRefOid"]
    if not fetched(head):
        print(f"{where}: its head {head} is not on origin: push it, then land again")
        failed.add(pull["number"])
        return False
    try:
        run_in(work, "merge", "-q", "--no-ff", "--no-edit", head)
        return True
    except subprocess.CalledProcessError:
        subprocess.run(
            ["git", "-C", str(work), "merge", "--abort"], capture_output=True, check=False
        )
    failed.add(pull["number"])
    ahead = f" plus {', '.join(f'#{n}' for n in before)} merged before it" if before else ""
    print(f"{where} conflicts with {base}{ahead}: skipped")
    if not any(
        note["body"].startswith(CONFLICTS) and f"Head: {head}" in note["body"]
        for note in notes(pull)
    ):
        comment(
            pull["number"],
            f"{CONFLICTS}\nHead: {head}\n\nIt conflicts with {base}{ahead}: merge origin/{base} in, rerun the gates,"
            " get a verdict on the merge (lead.md step 8), then land again.\n",
        )
    return False


def pre_landed(
    pull: dict[str, Any], base: str, work: Path, loop: str | None, failed: set[int]
) -> bool:
    """Whether loop.md's `pre_land` passes the PR, True without one. It runs in `work` at the base's tip, with
    LAND_HEAD and LAND_BASE set, so the base's tree holds the check that judges a PR, never the PR's own. Non-zero
    leaves the PR out of this batch with its output said once per head on the PR; it isn't red, so it stays ready."""
    if not (written := settings(loop).get("pre_land")):
        return True
    command, words, sets = command_line(written, "pre_land")
    where, head, tip = (
        f"PR #{pull['number']}",
        pull["headRefOid"],
        run_in(work, "rev-parse", "HEAD"),
    )
    # so the check can read the head; a head not on origin is merged_onto's to report
    if not fetched(head):
        return True
    try:
        ran = subprocess.run(
            words,
            cwd=work,
            env=os.environ | sets | {"LAND_HEAD": head, "LAND_BASE": tip},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise Refused(f"loop.md's `pre_land` {command!r} can't run: {exc}") from None
    reset(work, tip)  # the batch merges onto the base as it is, whatever the check left
    if not ran.returncode:
        return True
    failed.add(pull["number"])
    print(
        f"{where}: `{command}` refused it against {base} at {tip}, exiting {ran.returncode}: left out of this batch"
    )
    if not any(
        note["body"].startswith(PRE_LAND) and f"Head: {head}" in note["body"]
        for note in notes(pull)
    ):
        comment(
            pull["number"],
            f"{PRE_LAND}\nHead: {head}\n\n`{command}` refused it against {base} at {tip}, exiting {ran.returncode}: fix"
            " what it says, then land again.\n\n````\n"
            # its end, where a check says why, within GitHub's 65536 characters a comment holds
            + ran.stdout.rstrip("\n")[-60000:]
            + "\n````\n",
        )
    return False


def gate_batch(work: Path, pulls: list[dict[str, Any]]) -> tuple[str, str]:
    """The tree checked out in `work` and how it passed the gate (`run` or `reused`), empty when red. A pass is reused
    when the gate command passed on the tree before (reusable), on the batch's commit or a PR's head with that tree;
    never on GitHub's required checks alone, since the pass is published as the gate command's. Else the gate runs
    there and its pass is recorded by tree. Its log stays beside the worktree."""
    commit, tree = run_in(work, "rev-parse", "HEAD"), run_in(work, "rev-parse", "HEAD^{tree}")
    command = gate()[0]
    if reusable(commit) or any(
        tree_of(pull["headRefOid"]) == tree and reusable(pull["headRefOid"]) for pull in pulls
    ):
        print(f"Tree {tree}: `{command}` passed on it before, reused")
        return tree, "reused"
    log, fault = work.parent / f"{tree}.log", settings(project()[1]).get("machine_exit")
    for again in (False, True):
        with log.open("w") as out:
            code = ran_gate(work, out)
        if code != fault:
            break
        if again:
            raise MachineFault(
                f"Tree {tree}: `{command}` exited {code}, loop.md's `machine_exit`, twice: a machine fault, not the"
                " change's, so nothing more lands and nobody is evicted. Fix the machine, then land again."
                f" The gate's last lines (log {public(str(log))}):\n"
                + "\n".join(log.read_text(errors="replace").splitlines()[-LOG_TAIL:])
            )
        print(
            f"Tree {tree}: `{command}` exited {code}, loop.md's `machine_exit`: once more on the same tree"
        )
        reset(work, commit)
    if not code and (changed := run_in(work, "status", "--porcelain", "--untracked-files=all")):
        with log.open("a") as out:
            out.write(
                f"\nthe gate changed the tree, so it did not run on the batch as merged:\n{changed}\n"
            )
        code = 1
    print(f"Tree {tree}: `{command}` exited {code} (log {public(str(log))})")
    if code:
        return tree, ""
    record = {
        "head": commit,
        "tree": tree,
        "command": command,
        "exit": 0,
        "env": gate()[2],
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": socket.gethostname(),
    }
    (where := recorded(tree, command)).parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(record, indent=2) + "\n")
    return tree, "run"


def evict(pull: dict[str, Any], base: str, green: str, log: Path) -> None:
    """Take a PR red alone, twice, out of the batch: back to draft, so the next land leaves it out until `land <pr>`
    marks it ready again, and a comment holding its gate log's last LOG_TAIL lines."""
    where, head, number = f"PR #{pull['number']}", pull["headRefOid"], pull["number"]
    print(f"{where} is red alone on {base} at {green}, twice: evicted")
    try:
        tail = log.read_text(errors="replace").splitlines()[-LOG_TAIL:]
    except OSError:
        tail = []
    gh("pr", "ready", "--undo", str(number))
    comment(
        number,
        f"{EVICTED}\nHead: {head}\n\n`{gate()[0]}` failed twice on it merged alone onto {base} at {green}: fix it,"
        f" then `land {number}` marks it ready again.\n\n<details><summary>The gate's last lines</summary>\n\n````\n"
        + "\n".join(tail)
        + "\n````\n</details>\n",
    )


def merges(
    landed: list[tuple[dict[str, Any], str, str, str]],
    base: str,
    tip: str,
    work: Path,
    loop: str | None,
    failed: set[int],
) -> None:
    """Merge each PR through GitHub in the batch's order, pinned to its head (or, with loop.md's `land` section, as a
    signed squash of the tree it lands on the commit before it), stopping at the first one GitHub refuses or leaves
    open, then check the base ended at the gated tree: equal, publish the pass on the new tip; else (a refusal left
    the batch partial, or someone merged meanwhile) the tip is gated here. Each landed PR gets a `Landed` comment."""
    local, command, done = signed(loop), gate()[0], []
    for pull, tree, gated, how in landed:
        where, head = f"PR #{pull['number']}", pull["headRefOid"]
        try:
            if local:
                tip = signed_squash(pull, local[1], (tip, tree))
                print(f"{where} landed in {base} as {tip}, signed by a key in {local[1]}")
            else:
                # ponytail: no --delete-branch, which also deletes the local branch a worktree has checked out; the
                # repo's delete_branch_on_merge removes the remote one
                gh("pr", "merge", str(pull["number"]), "--squash", "--match-head-commit", head)
                # a base requiring a merge queue only queues it, to merge later on a tree this batch never gated
                if (state := pull_request(pull["number"])["state"]) != "MERGED":
                    raise Refused(f"GitHub left it {state}, not merged")
                print(f"{where} merged at {head}")
        except (subprocess.CalledProcessError, Refused) as exc:
            why = " ".join(str(getattr(exc, "stderr", None) or exc).split())
            print(
                f"{where}: the merge was refused, so it and every PR after it wait for the next land: {why}"
            )
            failed.update(other["number"] for other, *_ in landed[len(done) :])
            break
        done.append((pull, tree, gated, how))
    if not done:
        return
    git("fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
    tip = git("rev-parse", f"refs/remotes/origin/{base}").strip()
    actual, (_, tree, gated, _) = git("rev-parse", f"{tip}^{{tree}}").strip(), done[-1]
    if actual == gated:
        publish(tip, {"head": tip, "tree": actual, "command": command})
    else:
        numbers = ", ".join(f"#{pull['number']}" for pull, *_ in done)
        print(
            f"{base} holds {numbers} of the batch, whose tree {actual} was never gated, so {tip} is gated now"
            if actual == tree
            else f"{base}'s tree is {actual} after the merges, not the {tree} they make: someone merged meanwhile,"
            f" so {tip} is gated now"
        )
        reset(work, tip)
        try:
            if gate_batch(work, [])[1]:
                publish(tip, {"head": tip, "tree": actual, "command": command})
        except MachineFault as exc:  # the PRs landed: each still gets its comment
            print(exc)
    numbers = ", ".join(f"#{pull['number']}" for pull, *_ in done)
    for pull, tree, gated, how in done:
        comment(
            pull["number"],
            f"Landed\nBase: {tip}\nTree: {tree}\nGate: {command}, {how} on {gated}\nBatch: {numbers}\n",
        )


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
    comment(number, f"Approved: {point}\nBy: owner\n{record}")
    for note, _ in earlier:
        if not note.get("isMinimized") and note.get("viewerCanMinimize"):
            minimize(note["id"])
    label(number, f"approved:{point}", add=True)
    label(number, NEEDS_OWNER, add=False)
    return 0


def delegate(number: int) -> int:
    """The delegated approver's `approved:merge` on a PR into a feature branch, under the owner's standing rule: the
    label, then the record that names it the delegate's. Into the default branch, whose merge only the owner approves
    and where a label is no go, it is refused."""
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
        # a label with no record names no one: take it off again
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


LOCAL_CI = ["mise", "run", "check:all"]
# a status description's limit on GitHub, which holds the tree, the commit and the gate command (described)
DESCRIBED = 140


def gate(passed: list[str] | tuple[str, ...] = ()) -> tuple[str, list[str], dict[str, str]]:
    """loop.md's `gate` under `loop` (default LOCAL_CI): the command as written, its words, and the variables it sets
    in front of them (`GATE_UI_TESTS=0 mise run check:all`). The command alone is the gate: it runs with every name
    `local_ci_env` lists cleared but those it sets, so no host's ambient env changes what it ran. With `passed`, a
    head proof's names (head_proof), each one this process's environment sets is set to that value, over the
    command's own assignment of it, and the command returned names it, so its record and status say so."""
    return command_line(settings(project()[1]).get("gate") or shlex.join(LOCAL_CI), "gate", passed)


def command_line(
    written: str, key: str, passed: list[str] | tuple[str, ...] = ()
) -> tuple[str, list[str], dict[str, str]]:
    """loop.md's command `key` (`gate`, `pre_land`) as written: its words, and the variables it sets in front of them,
    each of `passed` this process's environment sets taking that value (gate). It runs with no shell, so a shell
    operator (`&&`, `;`, `|`) is refused: the words after it would be arguments, never a command."""
    lexer = shlex.shlex(written, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = list(lexer)
    assigned = len(
        list(
            itertools.takewhile(
                lambda word: re.fullmatch(r"[A-Za-z_]\w*=.*", word, re.DOTALL), words
            )
        )
    )
    if (
        assigned == len(words)
        or any(set(word) <= set("();<>|&") for word in words)
        or re.fullmatch(r"\w*=.*", words[assigned], re.DOTALL)
    ):
        raise Refused(
            f"loop.md's `{key}` is {written!r}: variables to set, then one command to run, with no shell operator"
            " (put a chain of checks in one task)"
        )
    sets = dict(word.split("=", 1) for word in words[:assigned])
    if caller := {name: os.environ[name] for name in passed if name in os.environ}:
        sets |= caller
        words = [*(f"{name}={value}" for name, value in sets.items()), *words[assigned:]]
        assigned = len(sets)
    return shlex.join(words), words[assigned:], sets


def ran_gate(
    cwd: Path | None = None, out: Any = None, passed: list[str] | tuple[str, ...] = ()
) -> int:
    """Run the gate (gate, with `passed`) in its environment (gate_env), in `cwd` with its output to `out` when given,
    and return its exit; a command that isn't there is refused, naming the gate, since loop.md is hand-written."""
    command, words, _ = gate(passed)
    where = {"cwd": cwd, "stdout": out, "stderr": subprocess.STDOUT} if cwd else {}
    try:
        return subprocess.run(words, check=False, env=gate_env(passed), **where).returncode
    except OSError as exc:
        raise Refused(f"loop.md's `gate` {command!r} can't run: {exc}") from None


def gate_env(passed: list[str] | tuple[str, ...] = ()) -> dict[str, str]:
    """The environment the gate runs in: this process's, without the names `local_ci_env` lists unless the gate's
    command sets them, or `passed` takes them from this process's (gate)."""
    cleared, sets = set(local_ci_env()), gate(passed)[2]
    return {name: value for name, value in os.environ.items() if name not in cleared} | sets


def local_ci_dir() -> Path:
    """Where local-ci keeps its records and runs: the git common dir, which every worktree of the clone shares and no
    commit carries."""
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    return common / "approvals" / "local-ci"


def recorded(tree: str, command: str) -> Path:
    """Where a local-ci pass of `command` on `tree` is recorded."""
    return local_ci_dir() / f"{tree}-{gate_key(command)}.json"


def gate_key(command: str) -> str:
    """A digest of the gate command, which names a record and stands for a command too long to publish (described)."""
    return hashlib.sha256(command.encode()).hexdigest()[:12]


def described(tree: str, commit: str, command: str) -> str:
    """A published pass's status description: the tree, the commit it ran on, and the command, or its digest when the
    command doesn't fit, so another host reads what ran and a refusal can name it."""
    line = f"Tree {tree} on {commit[:12]}: {command}"
    return (
        line
        if len(line) <= DESCRIBED
        else f"Tree {tree} on {commit[:12]}: sha256 {gate_key(command)}"
    )


def tree_of(commit: str) -> str | None:
    """The tree `commit` holds, fetching `origin` once when the clone lacks it; None when neither has it."""
    with contextlib.suppress(subprocess.CalledProcessError):
        return git("rev-parse", f"{commit}^{{tree}}").strip()
    with contextlib.suppress(subprocess.CalledProcessError):
        git("fetch", "--quiet", "origin")
        return git("rev-parse", f"{commit}^{{tree}}").strip()
    return None


def checkout_state() -> tuple[str, str]:
    """HEAD and every change in the checkout, empty when it is clean."""
    # untracked files and submodule edits listed whatever status.showUntrackedFiles or submodule.*.ignore say
    status = git("status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none")
    # status skips files whose index flag says so (assume-unchanged, set by core.ignoreStat; skip-worktree)
    hidden = [
        f"{line[2:]} (index flag hides its changes)\n"
        for line in git("ls-files", "-v").splitlines()
        if line[:1].islower() or line[:1] == "S"
    ]
    return git("rev-parse", "HEAD").strip(), status + "".join(hidden)


def run_local_ci(
    pr: int | None, head: str | None, passed: list[str] | tuple[str, ...] = ()
) -> dict[str, Any]:
    """Run the gate (with `passed`, gate) on a clean checkout (at PR `pr`'s `head`, when given) and record the pass by
    tree and command; refuse a check off the head, on a changed tree, failing, or changing the tree, recording
    nothing."""
    before = checkout_state()
    if head and before[0] != head:
        raise Refused(
            f"the checkout is at {before[0]}, PR #{pr}'s head is {head}: push, or check out the head"
        )
    if before[1]:
        raise Refused(f"the tree has changes, so the check would not run on the head:\n{before[1]}")
    command, _, env = gate(passed)
    code = ran_gate(passed=passed)
    if code == settings(project()[1]).get("machine_exit"):
        raise Refused(
            f"{command} hit a machine fault (exit {code}, loop.md's `machine_exit`): nothing recorded; fix the machine,"
            " then run it again"
        )
    if code:
        raise Refused(f"{command} exited {code}: nothing recorded")
    if checkout_state() != before:
        raise Refused(
            f"{command} changed the checkout, so it did not run on the head as pushed:\n{checkout_state()[1]}"
        )
    record = {
        "head": before[0],
        "tree": git("rev-parse", "HEAD^{tree}").strip(),
        "command": command,
        "exit": code,
        "env": env,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": socket.gethostname(),
    }
    where = recorded(record["tree"], command)
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(record, indent=2) + "\n")
    return record


DETACHED = "APPROVALS_LOCAL_CI_HEAD"


def leads_its_session() -> bool:
    """Whether this process leads its own session, so no caller's process group or terminal takes it down."""
    return os.getsid(0) == os.getpid()


def run_files(head: str) -> tuple[Path, Path, Path]:
    """The detached local-ci run's log, pid and exit files on `head`, beside the records: a run is keyed by the commit
    it was started on, since its tree and env are known only once it runs."""
    where = local_ci_dir() / head
    return where.with_suffix(".log"), where.with_suffix(".pid"), where.with_suffix(".exit")


def since(pid: int) -> str | None:
    """When process `pid` started, as ps prints it in the C locale (so the write and every check read the same
    text), or None for no such process."""
    shown = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    return shown.stdout.strip() or None


def lives(run: dict[str, Any]) -> bool:
    """Whether the pid file's run still lives: its pid and that process's start time, since the system hands a dead
    run's pid to the next process it starts."""
    now = since(run["pid"])
    return now is not None and now == run.get("since")


def going(started: str, exit_file: Path) -> dict[str, Any] | None:
    """The pid file's run, while it has written no exit code and its process lives; else None."""
    try:
        run = json.loads(started)
        return run if not exit_file.exists() and lives(run) else None
    except (ValueError, TypeError, KeyError):
        return None


def detach(argv: list[str]) -> int:
    """Run `local-ci` again in a session of its own, stdin from /dev/null and output to the log, and follow the log,
    exiting with its exit code, so a caller killed with its process group leaves the check to finish and record. A run
    already going on the head is followed instead; one started with other arguments is followed to its end, then this
    one starts."""
    head = git("rev-parse", "HEAD").strip()
    log, pid, exit_file = run_files(head)
    log.parent.mkdir(parents=True, exist_ok=True)
    while True:
        with open(pid, "a+") as claim:
            fcntl.flock(claim, fcntl.LOCK_EX)  # two callers at once start one run
            claim.seek(0)
            run, started = None, going(claim.read(), exit_file)
            if started is None:
                exit_file.unlink(missing_ok=True)
                with open(log, "wb") as out, open(os.devnull) as nothing:
                    run = subprocess.Popen(
                        [sys.executable, os.path.abspath(__file__), *argv],
                        stdin=nothing,
                        stdout=out,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        env={**os.environ, DETACHED: head},
                    )
                started = {"pid": run.pid, "since": since(run.pid), "argv": argv}
                claim.truncate(0)
                claim.write(json.dumps(started))
        code = follow(log, exit_file, started, run)
        if started["argv"] == argv:
            return code


def follow(
    log: Path, exit_file: Path, started: dict[str, Any], child: subprocess.Popen[bytes] | None
) -> int:
    """Print the log as it grows until the run ends; its exit code, or 1 for a run that ended without writing one."""
    with open(log, "rb") as lines:
        while True:
            # a run this call started is its child: poll reaps it, where a zombie would still show in ps
            running = child.poll() is None if child else lives(started)
            # checked before the read, so the last read holds everything
            ended = exit_file.exists() or not running
            sys.stdout.buffer.write(lines.read())
            sys.stdout.flush()
            if ended:
                break
            time.sleep(0.2)
    try:
        return int(exit_file.read_text())
    except (OSError, ValueError):
        print(f"the detached local-ci run ended without an exit code: its log is {log}")
        return 1


def finished(head: str, code: int) -> None:
    """The detached run's last step: its exit code, written whole, after all its output."""
    sys.stdout.flush()
    sys.stderr.flush()
    _, _, exit_file = run_files(head)
    partial = exit_file.with_suffix(".exit-partial")
    partial.write_text(f"{code}\n")
    os.replace(partial, exit_file)


def local_ci_status(head: str) -> int:
    """Say whether the detached local-ci run on `head` is running (exit 3), passed (0) or failed (1), with its log;
    passed only when a pass on `head`'s tree under this environment is recorded."""
    head = git("rev-parse", "--verify", f"{head}^{{commit}}").strip()
    log, pid, exit_file = run_files(head)
    try:
        code = int(exit_file.read_text())
    except (OSError, ValueError):
        code = None
    if code == 0 and not recorded(str(tree_of(head)), gate()[0]).exists():
        # a run on a checkout with changes, or on another PR's head, exits 0 with no pass on this one
        print(f"exited 0 without recording a pass on {head} under the gate's command: log {log}")
        return 1
    if code is not None:
        print(f"{'passed' if code == 0 else f'failed (exit {code})'} on {head}: log {log}")
        return 0 if code == 0 else 1
    started = going(pid.read_text() if pid.exists() else "", exit_file)
    if started:
        print(f"running on {head} (pid {started['pid']}): log {log}")
        return 3
    if log.exists():
        print(f"ended without an exit code on {head}: log {log}")
    else:
        print(f"no detached local-ci run on {head}")
    return 1


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


def reusable(head: str, passed: list[str] | tuple[str, ...] = ()) -> dict[str, Any] | None:
    """A green pass on `head`'s tree under today's gate command (with `passed`, gate), or None: this clone's record,
    made on any commit with that tree, else one published on `head` itself (published). The record's `head` is the
    commit the pass ran on. A record without `env` (0.23.1 wrote none) never matches, since nothing says what tier it
    ran."""
    if (held := tree_of(head)) is None:
        return None
    command, _, env = gate(passed)
    try:
        record = json.loads(recorded(held, command).read_text())
    except (OSError, ValueError):
        record = None
    # the posting path reads the commit and time too: a record without them is a miss, not a crash
    if (
        isinstance(record, dict)
        and all(isinstance(record.get(key), str) for key in ("head", "time"))
        and (record.get("tree"), record.get("command"), record.get("exit"), record.get("env"))
        == (held, command, 0, env)
    ):
        return record
    return published(head, held, command, env)


def published(
    head: str, held: str, command: str, env: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """A pass of `command` (setting `env`, default the gate's) on `head` another clone published (publish), as a
    record, or None: a `gate` status (stated) for `head`'s own tree `held` and that command (described)."""
    found = stated(
        head,
        PUBLISHED,
        lambda status, named: status["description"] == described(held, named[2], command),
    )
    if found is None:
        return None
    status, named = found
    return {
        "head": named[2],
        "tree": held,
        "command": command,
        "exit": 0,
        "env": gate()[2] if env is None else env,
        "time": status["created_at"],
        "published": True,
    }


def stated(
    head: str, context: str, wanted: Callable[[dict[str, Any], re.Match[str]], bool]
) -> tuple[dict[str, Any], re.Match[str]] | None:
    """The newest green status `context` on `head` whose description reads as a pass (PASSED) and is `wanted`, with
    that reading, or None. It counts only from the account running this or a writer, since a status is the repo's to
    write and a PR's author may hold no more than a fork. GitHub unreachable: None, so the check runs."""
    try:
        found = statuses(head)
    except (subprocess.CalledProcessError, OSError, ValueError):
        return None
    for status in found:  # newest first
        named = PASSED.fullmatch(status.get("description") or "")
        login = (status.get("creator") or {}).get("login")
        if (status.get("context"), status.get("state")) != (context, "success") or not named:
            continue
        if wanted(status, named) and login is not None and (login == viewer() or writer(login)):
            return status, named
    return None


def head_proof(loop: str | None) -> dict[str, Any] | None:
    """loop.md's `head_proof` (`status`, the commit status `land` requires on each head, and `env`, the names
    `local-ci --record --head-proof` takes from the caller), or None without it."""
    proof: dict[str, Any] | None = settings(loop).get("head_proof")
    if proof and (
        bad := [name for name in proof["env"] if not re.fullmatch(r"[A-Za-z_]\w*", name)]
    ):
        raise Refused(f"loop.md's `head_proof.env` names {bad[0]!r}, which is no variable name")
    # a context this script or the approvals workflow posts would let a plain gate pass or a go prove the head
    if proof and proof["status"] in {PUBLISHED, OWNER_GO, APPROVALS}:
        raise Refused(
            f"loop.md's `head_proof.status` is {proof['status']!r}, a status the loop already posts for another proof"
        )
    return proof


def proof_line(record: dict[str, Any], names: list[str]) -> str:
    """A head proof's status description: the tree, the commit the pass ran on, and the value of each of `names` it
    ran under (`default` for none), so the verifier reads the tier off the head."""
    values = " ".join(
        f"{name}={public(record['env'][name])}" for name in names if name in record["env"]
    )
    # ponytail: cut at GitHub's limit, which values past 77 characters reach; a digest if a tier ever gets that long
    return f"Tree {record['tree']} on {record['head'][:12]}: {values or 'default'}"[:DESCRIBED]


def proved(head: str, status: str) -> bool:
    """Whether `head` itself carries a green `status`, the head proof, naming its own tree (stated): a status on an
    older head never counts, since a status belongs to one commit."""
    held = tree_of(head)
    return (
        held is not None
        and stated(head, status, lambda _status, named: named[1] == held) is not None
    )


def elsewhere(head: str) -> str:
    """What a refusal adds when `head`'s tree passed under another gate command: `; its tree passed under <command>`
    for each, from this clone's records and the head's published statuses, then today's; empty when none did."""
    if (held := tree_of(head)) is None:
        return ""
    command, others = gate()[0], set()
    with contextlib.suppress(OSError):
        for path in recorded(held, command).parent.glob(f"{held}-*.json"):
            with contextlib.suppress(OSError, ValueError):
                record = json.loads(path.read_text())
                if (
                    isinstance(record, dict)
                    and record.get("exit") == 0
                    and isinstance(record.get("command"), str)
                ):
                    others.add(record["command"])
    with contextlib.suppress(subprocess.CalledProcessError, OSError, ValueError):
        for status in statuses(head):
            named = PASSED.fullmatch(status.get("description") or "")
            if (
                status.get("context") == PUBLISHED
                and status.get("state") == "success"
                and named
                and named[1] == held
            ):
                others.add(named[3])
    others -= {command, f"sha256 {gate_key(command)}"}
    if not others:
        return ""
    return (
        f"; its tree passed under `{'`, `'.join(sorted(others))}`, and the gate is now `{command}`"
    )


def statuses(head: str) -> list[dict[str, Any]]:
    """The commit statuses on `head`, newest first; ponytail: the first 100, which a head reaches only by hand."""
    out = gh("api", f"repos/{{owner}}/{{repo}}/commits/{head}/statuses?per_page=100")
    found: list[dict[str, Any]] = json.loads(out)
    return found


def publish(head: str, record: dict[str, Any], proof: dict[str, Any] | None = None) -> None:
    """Publish a pass as a commit status on `head`, unless one already does: success under the context `gate`, its
    description the tree, the commit the pass ran on and the command (described), so another clone's reusable() finds
    it; with `proof`, loop.md's `head_proof`, under its `status` instead, the description naming the values of its
    `env` (proof_line), which `land` reads (proved). A status, since gh's token can write one and only an account that
    can push may (a check run needs a GitHub App). GitHub refusing or unreachable: say so, and the record stays in
    this clone."""
    if proof is None:
        context, line = PUBLISHED, described(record["tree"], record["head"], record["command"])
        if published(head, record["tree"], record["command"]):
            return
    else:
        context, line = proof["status"], proof_line(record, proof["env"])
        if stated(head, context, lambda status, _named: status["description"] == line):
            return
    try:
        post_status(head, context, line)
    except (subprocess.CalledProcessError, OSError) as exc:
        why = (getattr(exc, "stderr", None) or str(exc)).strip()
        print(f"not published on GitHub, so only this clone reuses it: {why}")
        return
    print(f"published on {head} as the commit status `{context}`")


def post_status(head: str, context: str, description: str, state: str = "success") -> None:
    gh(
        "api",
        f"repos/{{owner}}/{{repo}}/statuses/{head}",
        "-f",
        f"state={state}",
        "-f",
        f"context={context}",
        "-f",
        f"description={description}",
        "--silent",
    )


def reused(record: dict[str, Any]) -> str:
    return f"Reused by tree from the pass recorded on {record['head']} at {record['time']}, not run again."


def local_ci(pr: int | None, proof: dict[str, Any] | None = None) -> int:
    """With a PR: post a pass on its head, from a recorded pass on its tree or from a run now. Without one: on a
    clean checkout, reuse or run and record a pass on HEAD, for `local-ci <pr>` to reuse; on one with changes, run the
    check and record nothing. Either publishes a pass this clone holds (publish). With `proof`, loop.md's
    `head_proof` (`--head-proof`, no PR), the gate takes its `env` names from this process (gate), and the pass is
    published as the head proof instead."""
    if pr is None:
        passed = proof["env"] if proof else ()
        head, changes = checkout_state()
        if changes:
            command, code = gate(passed)[0], ran_gate(passed=passed)
            print(
                f"{command} exited {code} on a checkout with changes, so nothing is recorded:\n{changes}"
            )
            return code
        if record := reusable(head, passed):
            print(f"{CHECKED} on {head}: {reused(record)}")
        else:
            record = run_local_ci(None, None, passed)
            print(f"{CHECKED} on {head}: recorded in {recorded(record['tree'], record['command'])}")
        if proof:
            publish(head, record, proof)
        elif not record.get("published"):
            publish(head, record)
        return 0
    head = pull_request(pr)["headRefOid"]
    if record := reusable(head):
        source = f"{reused(record)}\n"
    else:
        record = run_local_ci(pr, head)
        source = ""
    if not record.get("published"):
        publish(head, record)
    comment(
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
    approving = commands.add_parser("approve")
    approving.add_argument("point", choices=(*POINTS, "merge"))
    approving.add_argument("number", type=int)
    # an agent never approves: a record is a person's word, and the owner's policy in loop.md covers the rest
    approving.add_argument("--by", choices=("owner",), required=True)
    # merge only: the head the owner was shown, and their go taken back
    approving.add_argument("--head")
    approving.add_argument("--withdraw", action="store_true")
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
    recording.add_argument("--status", metavar="HEAD")
    recording.add_argument("--head-proof", action="store_true")
    merging = commands.add_parser("land")
    merging.add_argument("pr", type=int, nargs="?")
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
            if args.point == "queue":
                deprecated("check queue")
            return check(args.point, args.pr, args.head, args.issue)
        if args.command == "batch":
            deprecated("batch")
            return batch(args.pr, args.merge, args.batch, args.exit, args.log)
        if args.command == "approve":
            if args.point != "merge" and (args.head or args.withdraw):
                raise Refused("--head and --withdraw belong to `approve merge`")
            if args.point == "merge" and not args.head:
                raise Refused("approve merge needs --head <sha>: the head the owner was shown")
            return (
                go(args.number, args.head, args.withdraw)
                if args.point == "merge"
                else approve(args.point, args.number)
            )
        if args.command == "delegate":
            return delegate(args.pr)
        if args.command == "local-ci":
            if args.status is not None:
                if args.pr is not None or args.record:
                    raise Refused("local-ci --status takes a head alone")
                return local_ci_status(args.status)
            if (args.pr is None) != args.record:
                raise Refused(
                    "local-ci takes a PR number, or --record to record a run on HEAD before one exists"
                )
            proof = None
            if args.head_proof and (proof := head_proof(project()[1])) is None:
                raise Refused("loop.md sets no `head_proof`: --head-proof has no status to publish")
            if args.head_proof and not args.record:
                raise Refused("--head-proof goes with --record: the head proof is the checkout's")
            return local_ci(args.pr, proof) if leads_its_session() else detach(argv)
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
    detached = os.environ.pop(
        DETACHED, None
    )  # set by detach() for the run it starts, and for no process under it
    code = main(sys.argv[1:])
    if detached:
        finished(detached, code)
    sys.exit(code)
