#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Approvals (engineering-loop): every step leaves proof on GitHub, and this checks it before the loop moves on.

    uv run scripts/approvals.py check <build|merge> [pr]  # one line per missing proof, exit 1; waiting: exit 3
    uv run scripts/approvals.py check build --issue <n>   # before the PR exists: the issue's build proofs; exit 0 or 1
    uv run scripts/approvals.py check build <n>           # <n> no PR has: the same as --issue <n>
    uv run scripts/approvals.py check queue <pr> --head <sha>  # deprecated: may that head enter a project's own queue
    uv run scripts/approvals.py batch <pr> --merge <sha> --batch <sha> --exit <n> --log <path>  # deprecated: its proof
    uv run scripts/approvals.py land [<pr>... [--only]] [--wait]  # land every landable PR as one gated batch; exit 0, 1 or 3
    uv run scripts/approvals.py approve <spec|plan> <issue> --by owner   # on the owner's word
    uv run scripts/approvals.py approve merge <pr> --head <sha> --by <owner|delegate> [--withdraw]  # a go on that head
    uv run scripts/approvals.py delegate <pr>              # the delegated approver's approved:merge, feature branch only
    uv run scripts/approvals.py verdict <pr> <report>      # post a verifier report as a PR review
    uv run scripts/approvals.py report <report>            # check a verifier report as verdict reads it; posts nothing
    uv run scripts/approvals.py brief <pr> [--priorities <file>] [--proof <log>]...  # a verifier pass's brief
    uv run scripts/approvals.py local-ci <pr> [--run]      # with `ci: false`: post the head's recorded pass, refuse without one; --run runs `mise run check:all` here then
    uv run scripts/approvals.py local-ci --record          # the same on HEAD, the gate before each push; reused by tree
    uv run scripts/approvals.py local-ci --status <head>   # the detached run on a head: running (exit 3), passed, failed
    uv run scripts/approvals.py local-ci --record --head-proof  # the same under the caller's tier: loop.md's head proof
    uv run scripts/approvals.py release <issue>            # parked or dropped: remove the assignee the loop added
    uv run scripts/approvals.py commit-msg <file>          # a commit-msg hook: drop `Claude-Session:` lines from it

At start every verb warns on stderr, once, when this script's checkout is behind its upstream's last fetched tip (no
fetch) and the script differs there: the count and `git pull`. loop.md's `pack_staleness: refuse` under `loop` makes
it a refusal (exit 1).

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
`check build` with a PR also runs `check merge`'s keyword check (below), where the lead hands the PR over, so a wrong
keyword is fixed before the PR reaches the landing queue. `check build` also refuses an issue assigned to anyone but its approver (the person who last added `approved:spec`,
or for a spec the policy approves the account running this), since an assignee says whose the issue is; and, with a
PR, an issue another open PR closes too (a closing keyword, or `Implements` under a `signoff` rule), naming that PR
and its branch, since each build runs its own verifier, gate and queue. When every build proof holds, it assigns each issue no one holds to its approver, comments a record that the loop did, and gives
the PR its issues' assignees, reporting a refusal and carrying on. `release` removes an assignee that record names,
unless someone assigned them again after it, and keeps every other: a claim a person made stays.
A repo without docs/agents/gatekeeper.md or loop.md has no rules: each issue needs only `approved:spec` and no `needs-owner`, with no
approval record. Without docs/agents/issue-tracker.md no label's shape is checked.
`check merge` also fails a PR that itself carries `needs-owner` (`#<n> waits for the owner (needs-owner)`), so `land`
never takes it, alone or in a batch, until the owner's go on its head (`approve merge --by owner`) removes the label.
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
author posted one, that embeds its videos and screenshots as user-attachments (`demo.sh`), which `check build` checks too. Then it waits (exit 3, one line per wait; the approvals workflow maps it to a `pending`
status) for the newest run of each check the base branch requires, as `land` reads them, to be green on the head, or
of the aggregate `check` when it requires none (with
`ci: false` in loop.md, a `local-ci` pass on the head's tree under today's gate command, read as `local-ci` reads
it below, instead; its comment is the trace, never the proof), and, while the change is high risk, for the owner's
go on that head: the newest commit status `owner` on the head commit by the account running this or a writer is
green, and the PR holds the owner's record (`Approved by the owner.`, then `Approved: merge`, `By: owner`,
`Head: <sha>`) naming that head. `approve merge <pr> --head <sha> --by owner` posts both on the owner's word, the
record's every word the script writes, refusing a head other than the one named, which is the one the owner was
shown; `--withdraw` posts a newer failing status and a `Withdrawn: merge` record and removes the `approved:merge`
label. A status belongs to one commit, so no push carries the go to a head the owner didn't see. `--by delegate` is
the delegated approver's go, pinned to one head the same way: the `owner` status described as the delegate's (`The
delegate's go on <sha>, under the owner's delegation`) and the record `Approved under the owner's delegation.`, then
`Approved: merge`, `By: delegate`, `Head: <sha>`, so the PR shows whose go it is. Into the default branch it is
refused unless loop.md's `delegate: all` under `loop` (default `feature`) lets the delegate's go cover that branch
too, and a delegate's status there counts only while it does, so removing the setting withdraws those goes on open
PRs; into a feature branch it counts either way. `check merge` and `land` print whose go, the owner's or the
delegate's, a high-risk head has. Into the default branch these are the only go: a
label is anyone's with triage rights, the delegated approver's included, so `approved:merge` there is no go, nor is
an `owner` status an older gate wrote from the label (marked as from it). On a change that is not high risk the
label means nothing. High risk is `risk:high` on the
PR or an issue it names, a risk rule matching (below) unless under `spec.auto: true`, a path `risk.merge_paths` names
(below), or a review at the cap or later not satisfied or
with a blocker or major open (`cap`, SKILL.md § The cap); when the gate infers it, `check merge` and `land` add `risk:high` to the PR, reporting a
failure to add it and carrying on. On a PR into a feature branch (any base but the repository's default branch)
`approved:merge` added after the head was pushed is a go too, the push time being GitHub's repository activity for
the head branch; a label added before the push is no go, and the approvals workflow removes it on `synchronize`. There
the label may be the delegated approver's: `delegate <pr>` adds it, then a record (`Approved: merge`,
`By: delegate`), and refuses a PR into the default branch, where a label is no go. A PR from a branch
into the default branch is high risk while any PR merged into that branch carries `risk:high`, so a feature
branch's merge waits for the owner.
Every proof held: exit 0. Before the PR exists, `check build` judges the issue `--issue <n>` names (or a positional
number no PR has), else the one
the branch's name starts a segment with (`loop/329-fix`), the same way, and claims nothing; with neither it exits 1,
since a build needs an approved spec. `check merge` with no PR yet: exit 0.
With `opt_out: true` in loop.md, a person may keep their PRs out of the loop: `check merge` on a PR that
left no loop trail (no verifier review, no `Approved: spec` record or `approved:spec` on an issue it links, no
`Reverts #<n>` line, not an exempt bot PR) prints that it is outside the loop and exits 0, so the approvals
workflow posts success and its author merges it their usual way; `land` never takes it into a batch, and named,
prints the same line and exits 1, so the loop never merges it. Risk rules and `risk:high` hold no such PR. `check build` is
unchanged. A spec a policy covers is no trail, since under `spec.auto: true` every issue is covered.
`land [<pr>... [--only]]` is the one way an agent merges. It lands every landable PR into one base, the first named PR's or else the
repository's default branch, as one batch:
1. It takes the landing lock, the branch `loop-landing/<base>` on `origin`, which only moves forward, so a host whose
pushes may only create or fast-forward a branch under `refs/heads/` (a cloud session's) takes and releases it too. Its
tip says the state: each lock commit holds the empty tree, its title says `landing lock: held` or `landing lock: free`
with `[skip ci]` (so a project whose workflows run on every branch push starts none), its body the pid, the PR
it lands (`land <pr>`'s, none for a bare `land`) and a random value (so two lands in the same second never make the same
commit), and its commit date is its age. A land pushes a `held` child of a `free` tip (or the first lock commit, with no
parent, where the branch is missing), leased on that tip with `--force-with-lease`, so of two lands from one tip one
wins. Once its batch is gated, before its first merge, it moves the lock to a `held` child of its own naming the
batch's last PR, leased on its own, so a lock taken by another land meanwhile stops it, merging nothing (exit 1). A
`held` tip is another land's: exit 3, naming its holder and age. One naming a PR that GitHub reports merged, with its
merge commit in origin's base, is released, left by a land that died after its merges: it is broken and taken in the
same push, a `held` child of it. One naming no PR (a bare `land` before its merges, or a lock written before #901), an
open one, or one GitHub can't read now waits; one older than 2 hours is stale, left by a land that died before its
merges, and is broken the same way. The lock is released at the end whatever happened, a SIGTERM or SIGHUP included (exit 128
plus the signal), by pushing a `free` child of ours leased on it, so a stale one broken and taken by another land stays
theirs; SIGKILL leaves it to be broken as stale. No push deletes a ref or rewrites one, so the branch's history only
grows. While the previous version's lock `refs/loop/landing` is on `origin` (read, never written), `land` waits on it
(exit 3), so a host still on that version and this one never land at once; one older than 2 hours is stale, passed
over and left in place. The base is fetched once the lock is taken, so the batch starts from the base as it is then.
2. The candidates, oldest PR first, are every open PR into the base from this repository, not a draft, that holds every
proof of `check merge` but its CI wait, is not outside the loop (`opt_out`, below), has the owner's go where it is high
risk, and has the checks the base requires on GitHub (`required_checks`, but `loop:approvals`, which is check merge's
own output) green on its head. Under `ci: false` the head needs no `local-ci` pass of its own: the gate on the batch is
the proof. With loop.md's `head_proof`, the head also carries its head proof (below), else it is no candidate and `land`
names the command that records it. `land <pr>` on a draft marks it ready, never on a missing proof, since ready starts CI, and does so before it
waits for the lock, so the holder's next batch includes it; while the checks that starts are required, it waits (exit 3).
`land` takes several PRs: each named draft is marked ready the same way, and the named PRs land in one batch with the other
candidates. `land <pr>... --only` (with or without `--wait`) makes the named PRs the only candidates: every other PR is left untouched (not
marked ready, commented on, evicted or merged), and the rest is as without the flag; `--only` without a PR exits 2.
The check of each PR (`landable`) writes nothing to GitHub: `land`'s own path marks a ready draft ready and adds `risk:high`, so a probe that only reads never readies a draft.
A named PR that is no candidate (or is closed, or targets another base than the first's) is left out and says why, and the rest still land: a missing proof exits 1,
a wait for the owner or a pending required check 3, a red required check 1; with several PRs named the exit is the worst of them, 1 over 3 over 0.
A named PR missing a required check, or a named draft, that GitHub reports conflicting exits 1 with the fix, `merge
origin/<base> in` (a draft is not marked ready first), since GitHub runs no workflow on a conflicting PR, so the check
would never come.
3. In a temporary worktree of `origin/<base>` under the git common dir, removed after, it first runs loop.md's
`pre_land`, where set, for each candidate: a command parsed as `gate` is, run there at the base's tip with `LAND_HEAD`
(the PR's head) and `LAND_BASE` (that tip) set, so the base's tree holds the check and a PR never changes what judges
it. A non-zero exit leaves that PR out of this batch, printing the check's last lines on every land, with a comment,
once per head, holding its output; it is not red, so it is neither evicted nor turned back to draft. Then it merges each candidate's head
(`git merge --no-ff`). A PR that conflicts is skipped, with a comment, once per head, saying it conflicts with the base
plus the PRs merged before it, so it needs the base merged in.
4. It gates the result's tree. A pass is reused when the gate command passed on that tree before (reusable, below):
this clone's record, or a record branch in origin for a candidate's head with that same tree, so one PR already up to
date with the base runs no gate. GitHub's required checks never stand in for it, since the pass is then published as the gate
command's. Otherwise it runs the gate there as `local-ci` does (below), its log under the git common dir, and records
the pass by tree; a gate that leaves the worktree changed is red, since it no longer ran on the batch as merged.
5. Green: it merges each PR through GitHub in that order, pinned to its head (`gh pr merge --squash
--match-head-commit`), with the body the repo's squash default would write less every `Claude-Session:` line, since a
cloud session's harness adds its link to each commit and the PR may be public: under the commit-messages default the
body GitHub builds from the commits (one: its message after the subject, its co-author lines moved to the end;
several: each message as a `* ` item, then `---------` and their co-authors), under the PR-description default the
PR's body, and under the blank default none. A merge GitHub refuses, or leaves unmerged
(a base requiring a merge queue only queues it, to merge later on a tree no gate saw), stops there: that PR and those
after it wait for the next land. Then it fetches and compares the base's tree with the gated tree. Equal: the pass is
published (below) on the new tip. It then deletes the record branches no head needs: those of the trees it landed, and
those over a day old whose tree is no open PR's head (a head replaced or never landed; the day spares a record pushed
before its PR opened). A refused delete is said and never fails the landing.
Different, because a refusal left only part of the batch on the base or someone merged by hand meanwhile: it says
which, gates the tip, and publishes only a pass. Each PR landed gets one comment, `Landed`, then `Base:` the new tip,
`Tree:` the tree it landed (the base with it and the PRs before it merged), `Gate:` the command, `run` or `reused`,
and the tree it passed on, and `Batch:` the PRs landed together. Each PR it merged then has its kept `--pr` worker sessions finished by a detached
(orchestrating-agents' `omnigent_agent.py reap --merged --pr <n>`), whose outcome goes to its own log, never the land's.
6. Red: it lands one PR at a time instead, each merged onto the last green commit and gated alone (a one-PR batch's red run counts as its first run alone). A PR red alone is
gated once more (green then is a flake, and it lands), then evicted: back to draft, so later batches leave it out until
`land <pr>` marks it ready again, and a comment holding its log's last 30 lines. When the first PR alone is red twice,
the bare base is gated: red, the run stops (exit 1) and evicts nobody, since every PR would fail on that base.
With loop.md's `machine_exit` (78, say), a gate run in steps 4 and 6 exiting with it is the machine's fault, not the
tree's: it runs once more on the same tree, and a second such exit stops the run (exit 1), landing nothing, evicting
nobody and posting nothing, and prints the log's last 30 lines: fix the machine, then land again.
Exit 0 when the named PR merged, or with no PR named when nothing landable failed; 1 for a refusal, a conflict, an
eviction, a merge GitHub refused or a red base; 3 while it waits; 143 or 129 when stopped by SIGTERM or SIGHUP.
`land --wait` runs it again every 30 seconds while it waits on the lock or on CI, printing each new state once, for up
to 2 hours, then exits 3; a wait for the owner ends it at once, since only the owner clears it.
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
`where: host | cloud | both` (default `host`) says where `land` runs: it refuses elsewhere, exit 1, before reading any
PR. A cloud session is one where Claude Code sets `CLAUDE_CODE_REMOTE=true`; its checkout signs with the session's own
key, shared across that service's users, so there `land` refuses without the section (GitHub's merge is GraphQL, which
the session's proxy refuses, and signs with GitHub's key), when it names no `signing_key_env`, and when that variable
is unset, empty, no unencrypted SSH private key, or a key whose public half is no line of the allowed signers file, each
refusal naming which and never the key. Else it writes the key to a mode-0600 file in a fresh temporary directory,
removed however the land ends, and every git command of the land runs with it (`-c gpg.format=ssh -c
user.signingkey=<file> -c gpg.ssh.program=ssh-keygen`, over the session's key and signing program), so each squash is
signed and verified with it. The batch's pass is published as below: GitHub refusing the status
there, it goes to origin as a ref. There REST alone answers, and it says neither whether a PR is in a merge queue nor
whether classic branch protection requires one, so a PR is a candidate there only with `merge_queue: false` in the
section, the project's word that its base requires none (`required_checks` still refuses a ruleset that does); a draft is refused, and an evicted PR stays
ready, each said, since GitHub changes a draft only over GraphQL. Off a cloud session only `where` is new.
`check queue`, `batch` and loop.md's `batch_queue`, `carry_over_main` and `ci` work as below for one more release, each
printing one `deprecated:` line on stderr, so a project's own queue keeps running until it adopts `land`.
`local-ci` runs only on a clean checkout at the PR head, and records nothing if the check fails or changes the tree.
In a shallow clone (a cloud session's), before the gate it fetches the base (the PR's, else the default branch) into
`refs/remotes/origin/<base>` and deepens (`git fetch --deepen 50`, up to three times, then `--unshallow`) until `git
merge-base origin/<base> HEAD` answers, so a gate step that diffs against the merge base gets a ref; each step's outcome
is one `local-ci:` line on stderr. A full clone runs nothing new, and no tracked file changes, so the recorded tree is
the same.
The check is the gate: loop.md's `gate` under `loop` (default `mise run check:all`), variables it sets in front of
its command included (`GATE_UI_TESTS=0 mise run check:all`), one command run with no shell, so an operator
such as `&&` is refused. It runs with every name loop.md's `local_ci_env` lists
removed from the environment unless the command sets it, so a host's ambient tier never changes what ran and the
command alone says what a pass proves. A pass also leaves a record keyed by tree and command under the git common dir
(`approvals/local-ci/<tree>-<key>.json`: head, tree, command, exit, env, time, host, seconds, slot_wait_seconds,
load_1m, swap_used_mb, `head` being the commit it ran on, `env` the variables the command sets, `<key>` a digest of
the command, `seconds` how long it ran, `slot_wait_seconds` how long it waited for the host gate slot, and `load_1m`
and `swap_used_mb` the host's 1-minute load average and swap in use, in MiB, when it started, each null where the host
doesn't say), which every worktree sees and nothing commits. With loop.md's `gate_steps` under `loop` (a list of `name`, `command`, parsed as `gate` is, and `where`: `any`,
or `host`, never run in a cloud session), in place of `gate`, the gate is those steps in order, and each step is a gate
of its own: its pass is recorded, published and reused by its tree and command alone, its record naming it as `step`,
so `local-ci`, `local-ci --record` and `land` run only the steps with no pass on the tree, stop at the first that fails
(a failed step records nothing, so it is never reused), and print one line per step naming the record branch or
commit each reused one passed on. A step may also name `paths`, a list of globs (fnmatch, case and all) of the files
it reads (#963): its pass is then found by its command and its inputs key, a digest of the `gate_steps` setting as
read and the mode, object id and path of each file under its paths in the tree, held as the record's `inputs` and its
record branch's `Inputs: <key>` line, so any tree with the same key reuses it, from this clone's records or from
origin's record branches of that command, and the step's line says `<step>: reused, inputs unchanged since <tree>`. A
found record counts only when today's `paths` give its own tree the same key, so one whose tree holds other inputs
counts for nothing. A step without `paths`, with an empty list, or whose paths match no file in the tree is keyed by
the tree, as above; a change to `gate_steps` changes every keyed step's key. A cloud session runs no `host` step: `local-ci --record` there runs the rest, says
which step it left and exits 0, with no head proof and no pass on the whole gate, which `local-ci <pr>` and `land` need
and refuse there. Each step that runs, or the one gate, holds the host gate slot (an exclusive flock on
`${XDG_CACHE_HOME:-~/.cache}/engineering-loop/gate.1.lock`) for its run only, with `LOOP_GATE_SLOT_HELD` set to that
path so a wrapper in it takes no lock of its own, and none when this process already runs under it; `local-ci --record` makes one on HEAD with no PR. On a checkout with changes `--record` runs the check, records
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
Every pass this clone holds, run or reused, is published one way from every session, host or cloud: pushed to origin
as the branch `loop-gate/<tree>-<command's key>` (a branch, since a cloud session's proxy pushes nothing else), on a
commit holding the tree, the commit the pass ran on as its parent, and as its message the line `Tree <tree> on
<commit's first 12>: <command>` (the command's digest, `sha256 <key>`, when it doesn't fit GitHub's 140 characters)
and an `Env:` line, then `Seconds: <n>` and `Slot wait seconds: <n>` (a record pushed before them still counts); `local-ci` says which branch. origin refusing the push (a commit not pushed yet) or unreachable is
said and changes nothing else: the record stays local, and a later `local-ci` publishes it. The pass is then shown as
a commit status on the head, success, context `gate`, description that line, where the token allows; a refused status
is said and is no error, since no decision reads it: anyone who can write a status may type one. A pass is reusable
for a commit when this clone's record for its tree holds exit 0 under today's command, or else when origin holds that
tree's record branch under today's command whose commit says that tree, command and env: a branch in the base repo is
its write access, so one on a PR's fork never counts, and it counts at every risk. A clone that reuses a record writes
the `gate` status it holds on the head, so the PR shows the pass. So any clone reuses a pass from any other, and
adding a name to `local_ci_env` keeps every pass. `local-ci <pr>` reads the PR's head through REST
where GraphQL answers 403, so it runs in a cloud session too. `local-ci <pr>`, `local-ci --record`, `land`, `check
queue`, `batch` and `check merge` read it the same way; the posted comment then says it was reused by tree from the
pass recorded on that commit, and when, instead of running the check again. A refusal for a missing pass names each
other command the tree passed under, from this clone's records and the tree's record branches, and today's. The host stays
in the record: nothing `approvals.py` posts names it, and posted text writes the home directory `~` (public), since a
public board would show both. The posted comment names the gate's command and the variables it sets (`Env: A=1`, or
`Env: default`).
With loop.md's `head_proof` under `loop` (`status: <context>`, `env: [<names>]`), each head proves itself under a tier
the lead picks, which the batch gate's fixed tier doesn't. `local-ci --record --head-proof` runs the gate as `--record`
does, but takes each `env` name the caller's environment sets from it instead of clearing it, over the gate line's own
assignment of that name, so the command it records names the value (`GATE_UI_TESTS=smoke mise run check:all`). It
publishes the pass as the commit status `<context>` instead of `gate`, described `Tree <tree> on <commit's first 12>:
<name>=<value> ...` for the `env` names it ran with (`default` for none), so the verifier reads the tier off the head.
`land` reads it, the one status a decision reads for a pass: a green status of that context on the head commit itself, naming the head's tree,
by the account running this or a writer. A status on an older head never counts, since a status belongs to one commit.
Which tier a change needs is the project's rule; `land` checks only that a head proof exists.
Deprecated: a project may land through a batching merge queue of its own (merge every waiting PR's head onto the base, run the
full gate once on the result, push the batch) instead of one `land` per PR, opting in with `batch_queue: true` under
loop.md's `loop`; without it `check queue` refuses and no batch proof counts, so a project that never set one up gets
no second way to satisfy the CI wait. `check queue <pr> --head <sha>` exits 0
when that head may enter it: it is the PR's head, every proof of `check merge` holds but the CI wait, which the queue's
gate on the batch replaces, the head has its own `local-ci --record` pass under the current env, or loop.md's
`head_proof` status green for its tree, such as a light gate's pass (either is what `batch` needs) and,
with CI, the checks `check merge` waits for passed, and a high-risk change has the owner's go on that head
(owner_waits, as `check merge` and `land` read it), which the queue checks again before it merges it. After its gate the queue posts `batch` on
each PR it merged: a comment `Merge queue batch` naming the head, the PR's merge commit, the batch commit, the gate's
exit, the env and time of the head's own `local-ci --record` pass, or for a head with none an `Admitted:` line naming
the head proof status and tree it entered on, and the log and its last lines; `batch` refuses a head with neither.
`check merge` takes that comment in place of the CI wait (either kind) once it holds: the exit is 0, the head has its
own green `local-ci --record` pass under the current env and the env the comment names, or the head proof status
green for its tree that the `Admitted:` line names, since a batch gate never stands in for a head's own pass or its
head proof, the merge commit's second parent is the head
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
    Spec: sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08      (plan: Plan:)

A spec or plan is named by its text, the sha256 of the issue's or comment's body as GitHub stores it (line ends read
as `\n`), so any change to the text voids the approval, read through GraphQL or REST alike, and restoring
exactly the approved text restores it, since the text is then the one approved. A record written before
texts were named carries the last edit as GitHub's edit history shows it (`as edited <time>`, `as written <time>`
before any): GraphQL still dates it, so it holds on a host until the next edit; REST has no edit time, so there it is
refused with the command that renews it. Every approval is a new comment: a re-approval says the spec or plan
changed, and `approve` minimizes as outdated each earlier record, which it supersedes, where GraphQL says this
account may. With `owner: <login>` under loop.md's `loop`, `check build`, `check merge` and `land` record an
`approved:spec` (or `approved:plan`) label that login added after the spec's (plan's) last edit as `approve --by
owner` would, removing `needs-owner`, and say so: the label is the owner's word. One they added before the last edit
is named and changes nothing, nor does anyone else's. Over REST the last edit is the spec's `updated_at`, which every
edit moves (and any other change), so a label is recorded only when nothing changed the spec after it.

GitHub is read through GraphQL, the fast path, and through REST where GraphQL answers 403, as a cloud session's proxy
does: after one refused call a run reads REST alone, the same fields call by call. REST has no closing links, so a
PR's issues are its body's `Closes`, `Part of` and `Implements` lines; its review threads come from the proxy's
`pulls/<n>/ccr/review_threads` route, and where that route is missing the read fails rather than count none; a commit
co-author, which only GraphQL resolves to an account, exempts no PR from review; and whether a PR is in a merge queue
can't be read, so `land` refuses it there. The proxy refuses the collaborator lookup too, so there only the account
running this counts as a writer, by its own permissions on the repo.

The policy block (SKILL.md § Settings), YAML, holds the owner's standing policy, checked against SCHEMA: a
section or key it doesn't know or a value of the wrong type is refused, naming the key, and so is a file without
the block. `loop` holds `cap`, `ci`, `opt_out`, `gate`, `local_ci_env`, `batch_queue`, `owner`, `machine_exit`,
`short_seconds` (mutate.py's), `pre_land` and `head_proof`; `mutate` holds `inconclusive_exit` (mutate.py's); `spec` holds `auto`.
`spec.auto` as a list approves by policy, with no record or label, the spec of an issue of each kind it names:
`bug`, labelled a bug; `follow-up`, carrying a `Found while #<n>` line in its body (a follow-up an agent raised);
`sub-issue`, a native sub-issue of an epic with the owner's current spec record and `approved:spec`, opened by an
account GitHub's collaborator permission gives admin, maintain or write. A high-risk one is still built; its merge
waits for the owner. `spec.auto: true` approves every spec the same
way, epics included, except one the risk rule matches on the labels of the issue and the PR and the PR's files (at
`check build` the files pushed so far), or one opened by an account without write access: those need the owner's
record and label, and `check` says why. Under `spec.auto: true` the risk rule holds the spec instead of the merge, since
the owner approved the change before it was built; `risk:high` and the cap still hold the merge. The list may also
hold a `paths` term (`- paths: [mise.toml, docs/agents/**]`), globs as a rule's `paths` are: it approves by policy the
spec of an issue labelled `spec:paths`, which the lead adds to declare that the change stays inside them, since the
gate can't tell that from the spec alone and the setting alone would approve every spec until its merge. `check build`
and `check merge` judge it on the issue's and the PR's labels and every path the PR touches, at `check build` before
the PR the branch's files so far: it approves only while every path matches a glob, a moved file's old name as well
as its new one, so a rename across the boundary either way voids it; GitHub gives the whole file list and every old
name; neither carries `risk:high` nor the risk rule holds (its `verifier` term too, once a review is read); and the
issue's author can write to the repo. Otherwise the owner approves the spec, and `check` names why, the files outside
the globs included. The label without the term approves nothing. Without `auto`, or
with `false` or an empty list, the owner approves every spec, and the gates are the merge approval of a change that is not high risk.

A rule (`risk`, `plan`, `signoff`) is a section of terms, any one of which matches: `always: true`; `labels`,
label names matched exactly on the PR and its issues; `paths`, globs matched on the PR's files; and in `risk` alone
`verifier: true`. `risk.merge_paths`, globs matched on the PR's files as `paths` are, is no term of the rule: a PR
touching one is high risk whatever its labels, `spec.auto` and the verifier's `Risk:` line say, and only the owner's go
on its head lets it merge, into any branch, so `check merge`, `check queue` and `land` wait for it, `approve merge
--by delegate` and `delegate` refuse it, and the label is no go; files it can't read hold. A list holds strings. The gate reads the keys, never the words of a rule, so a path or
label can never read as a term. A glob matches every path the PR touches on either side of the change: a
deleted file's, and a renamed or copied file's old name as well as its new one. Paths it can't judge, past the one
page of files it reads or an old name GitHub won't give, hold. The `plan` rule asks
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
The board's `Risk` field follows the label and the verifier's word, and a field at `High` adds the label (flag); the
label stays the gate's only input, and a board it can't reach is a line, never a failure.
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
import importlib.util
import io
import itertools
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

try:
    import yaml
except ImportError:  # run as `python3 approvals.py` where PyYAML isn't installed
    sys.exit(
        f"{Path(sys.argv[0]).name} needs PyYAML: run it with `uv run {sys.argv[0]}`, which installs it"
    )

# the ready state: an approved spec (board: Ready); waiting for the owner
READY, NEEDS_OWNER = "approved:spec", "needs-owner"
BUG, EPIC = "kind:bug", "epic"
# the lead's claim that a spec's change stays inside `spec.auto`'s `paths`, which the policy then approves (scoped)
SCOPED = "spec:paths"
CATEGORIES = {BUG, "kind:enhancement", "kind:chore", "kind:documentation"}
# a component's label is `area:<name>` and a category's `kind:<name>`; the docs name them bare or in full (qualified)
PREFIXES = {"component": "area:", "category": "kind:"}
SIZE_ORDER = ["size:XS", "size:S", "size:M", "size:L", "size:XL"]
SIZES = set(SIZE_ORDER)
TRACKER, LOOP = Path("docs/agents/issue-tracker.md"), Path("docs/agents/loop.md")
# the gatekeeper's policy, under `## Policy`; loop.md's `## Settings` block is read without it, deprecated
POLICY = Path("docs/agents/gatekeeper.md")
POINTS = ("spec", "plan")
# the `By:` of the delegated approver's merge record (delegate); on the default branch it counts only with
# `loop.delegate: all` (owned)
DELEGATE = "delegate"
# the plain line atop the merge records `approve merge` writes, by `--by`, so a person reads off the PR whose go it is
VOICED = {"owner": "Approved by the owner.", DELEGATE: "Approved under the owner's delegation."}
# the description of the delegate's OWNER_GO status, after `The delegate's go on <sha>`
DELEGATED = ", under the owner's delegation"
MERGE_LABEL = "approved:merge"
# the go on a high-risk head, the owner's or the delegate's, a commit status on that one commit (approve merge), so no
# push carries it over but merges of the base a verifier pass says change no logic (carried_go)
OWNER_GO = "owner"
# the verdict line a verifier pass on a merge-only delta writes, `Logic change: none`, which carries the go (carried_go)
LOGIC = "Logic change"
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
# a fallback verifier, run when Codex refuses (a Gemini pass through agy, `agy/<model>/<effort>`, or a same-family one):
# a family naming one counts as a lower tier, so a high-risk change never lands on it (loop.md, Verifier route)
FALLBACK_FAMILY = re.compile(
    r"(?<![^\s,/])(agy|gemini[\w.-]*|same-family)(?![^\s,/])", re.IGNORECASE
)
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
PULL = f"""id number title isCrossRepository author {{ __typename login }} {ASSIGNEES} state isDraft mergeable autoMergeRequest {{ enabledAt }} isInMergeQueue body baseRefName baseRefOid headRefName headRefOid baseRepository {{ nameWithOwner defaultBranchRef {{ name }} }} labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}
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
# the board's single-select field holding a PR's risk beside its `risk:high` label (the board template's)
BOARD_RISK = "Risk"
# a revert's line, as GitHub's Revert button writes it or by hand; ponytail: one revert per PR, the first line counts.
REVERTS = re.compile(r"^[ \t]*Reverts[ \t]+([\w.-]+/[\w.-]+)?#(\d+)\b", re.MULTILINE)
CHECKED = "Local check passed"
# a gate pass published as a commit status: its context, and its description (described): tree, commit, command
PUBLISHED = "gate"
# where publish() pushes a pass in origin, the one route another clone reads it by: a branch, since a cloud session's
# proxy refuses a push outside refs/heads/; land deletes it once no head needs it (drop_records)
RECORD_BRANCH = "refs/heads/loop-gate/{}"
# how old a record branch whose tree is no open PR's head must be before land deletes it: a record may be pushed
# before its PR is opened
RECORD_AGE = 24 * 60 * 60
# a pushed record's author and committer: no person's name or address reaches the repo through it
RECORDER = {"GIT_AUTHOR_NAME": "loop", "GIT_AUTHOR_EMAIL": "loop@invalid"} | {
    "GIT_COMMITTER_NAME": "loop",
    "GIT_COMMITTER_EMAIL": "loop@invalid",
}
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
# a URL in a `## Demo` comment; gh's --attach embeds a video or image as a bare user-attachments one, which plays inline
URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+")
ATTACHMENT = "https://github.com/user-attachments/"
# land --wait: seconds between tries, and how long it waits in all before it exits 3; a landing lock older than the
# ceiling is stale
POLL, CEILING = 30, 2 * 60 * 60
# the signals that stop a land and release its lock (stopped)
STOPS = (signal.SIGTERM, signal.SIGHUP)
# the landing lock of a base: a branch that only moves forward, since a host may be allowed only to create and
# fast-forward a branch (a cloud session's proxy refuses a push outside refs/heads/ and every delete); its tip's title
# says whether it is held, and [skip ci] in it starts no workflow
LOCK = "refs/heads/loop-landing/{}"
HELD, FREE = "landing lock: held", "landing lock: free"
# the lock before #814, a ref outside refs/heads/: a land waits while it is on origin, never writing it, so a host still
# on that version and this one never land at once
LEGACY = "refs/loop/landing"
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
    """A settings section whose every key is required but those `optional` names, such as `land`."""

    def __init__(self, *args: Any, optional: tuple[str, ...] = (), **kinds: Any) -> None:
        super().__init__(*args, **kinds)
        self.optional = frozenset(optional)


class Choice(tuple):
    """A setting that is one of these names, such as `loop.delegate`."""


class Rows(Table):
    """A setting that is a list of sections, each holding these keys, such as `loop.gate_steps`; `unique` names the
    keys no two rows may share."""

    def __init__(self, *args: Any, unique: tuple[str, ...] = (), **kinds: Any) -> None:
        super().__init__(*args, **kinds)
        self.unique = unique


# where `land` may run (loop.md's `land.where`): a host, a cloud session (CLOUD), or either
PLACES = ("host", "cloud", "both")
# where a gate step may run (loop.md's `gate_steps`): any machine, or only a host, never a cloud session (CLOUD)
STEP_PLACES = ("any", "host")
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
        "gate_steps": Rows(
            name=str,
            command=str,
            where=Choice(STEP_PLACES),
            paths=list,
            unique=("name", "command"),
            optional=("paths",),
        ),
        "batch_queue": bool,
        "owner": str,
        "machine_exit": int,
        "short_seconds": int,
        "pre_land": str,
        "head_proof": Table(status=str, env=list),
        "delegate": Choice(("all", "feature")),
        "pack_staleness": Choice(("warn", "refuse")),
    },
    "mutate": {"inconclusive_exit": int},
    "spec": {"auto": SPEC_KINDS},
    "practice": dict.fromkeys(STAGES, str),
    "risk": {"always": bool, "labels": list, "paths": list, "verifier": bool, "merge_paths": list},
    "plan": {"always": bool, "labels": list},
    "signoff": {"always": bool, "labels": list, "paths": list},
    "bot": {"paths": list, "branch": str},
    "land": Table(
        signed_squash_to=str,
        allowed_signers=str,
        where=Choice(PLACES),
        signing_key_env=str,
        merge_queue=bool,
        optional=("where", "signing_key_env", "merge_queue"),
    ),
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
        if isinstance(kind, Rows):  # a list of sections, such as `loop.gate_steps`
            if not (
                isinstance(value, list) and value and all(isinstance(row, dict) for row in value)
            ):
                raise Refused(
                    f"{file}'s {where} must be a list of sections each holding `{'`, `'.join(kind)}`"
                )
            for row in value:
                typed(row, kind, f"{name}.{key}", file)
            for unique in kind.unique:
                seen = [row[unique] for row in value]
                if twice := sorted({v for v in seen if seen.count(v) > 1}):
                    raise Refused(f"{file}'s {where} names the {unique} {twice[0]!r} twice")
        elif isinstance(kind, dict):  # a section within the section, such as `loop.head_proof`
            if not isinstance(value, dict):
                raise Refused(f"{file}'s {where} must be a section holding `{'`, `'.join(kind)}`")
            typed(value, kind, f"{name}.{key}", file)
        elif isinstance(kind, Choice):
            if not (isinstance(value, str) and value in kind):
                raise Refused(f"{file}'s {where} must be one of {', '.join(kind)}, not {value!r}")
        elif isinstance(kind, tuple):  # true, false, or a list naming some of the tuple's values
            # `spec.auto`'s list may also hold a `paths` term, a list of globs (spec_paths)
            for term in value if isinstance(value, list) else []:
                if not isinstance(term, dict):
                    continue
                globs = term.get("paths")
                if list(term) != ["paths"] or not (
                    isinstance(globs, list)
                    and globs
                    and all(isinstance(g, str) and g for g in globs)
                ):
                    raise Refused(
                        f"{file}'s {where} term must be `paths`, a list of globs, not {term!r}"
                    )
            if not (
                isinstance(value, bool)
                or isinstance(value, list)
                and all(isinstance(item, dict) or item in kind for item in value)
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
    if isinstance(schema, Table) and (
        missing := [key for key in schema if key not in section and key not in schema.optional]
    ):
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


def delegation(loop: str | None) -> str:
    """loop.md's `delegate`: `all` when the delegated approver's go on a head covers a PR into the default branch
    too, else `feature`, today's rule, where only the owner's does."""
    return str(settings(loop).get("delegate", "feature"))


def spec_auto(loop: str | None) -> bool:
    """Whether loop.md's `spec.auto` is true, under which a risk rule holds the spec instead of the merge."""
    return settings(loop).get("spec", {}).get("auto") is True


def spec_kinds(loop: str | None) -> set[str]:
    """The kinds of spec loop.md's `spec.auto` list names (SPEC_KINDS), which the policy approves; empty when it
    is no list."""
    auto = settings(loop).get("spec", {}).get("auto")
    return {kind for kind in auto if isinstance(kind, str)} if isinstance(auto, list) else set()


def spec_paths(loop: str | None) -> list[str]:
    """The globs of loop.md's `spec.auto` `paths` terms, inside which a spec carrying SCOPED is approved by policy
    (scoped); empty without one."""
    auto = settings(loop).get("spec", {}).get("auto")
    terms = [term for term in auto if isinstance(term, dict)] if isinstance(auto, list) else []
    return [glob for term in terms for glob in term["paths"]]


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
    renamed = any(
        file.get("changeType") in ("RENAMED", "COPIED") for file in pull["files"]["nodes"]
    )
    labels = {label["name"] for label in pull["labels"]["nodes"]}
    if renamed or "verify" in labels:
        return False
    author, files = pull.get("author") or {}, paths(pull)
    if not files:
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
    """The files the PR changes; None past the one page of 100 the gate reads. A rule on paths reads touched(),
    which adds a moved file's old name."""
    files = pull["files"]
    found = [file["path"] for file in files["nodes"]]
    return None if (files.get("totalCount") or 0) > len(found) else found


def touched(pull: dict[str, Any]) -> list[str] | None:
    """Every path the PR touches on either side of the change: each file's path (a deleted file's is its old one), and
    a renamed or copied file's old name too (previous), since moving a file across a boundary changes both sides;
    None past the one page of 100 the gate reads, or when any moved file's old name can't be read, so a rule on paths
    holds rather than misses one. The one place the gate reads renames (#791 reads them here too)."""
    found = paths(pull)
    if found is None:
        return None
    moved = [
        file["path"]
        for file in pull["files"]["nodes"]
        if file.get("changeType") in ("RENAMED", "COPIED")
    ]
    if moved:
        old = previous(pull)
        # every moved file needs its own old name: a response that lacks one (an entry without it, a file list that
        # changed between the two reads) proves nothing about where it came from
        if old is None or not all(old.get(path) for path in moved):
            return None
        found = found + [old[path] for path in moved if old[path] not in found]
    return found


def previous(pull: dict[str, Any]) -> dict[str, str] | None:
    """Each renamed or copied file's old name by its new one, which GitHub's GraphQL omits, read once per PR from its
    REST file list (pr_changes); None when GitHub can't give the list."""
    if "previousPaths" not in pull:
        try:
            changes = pr_changes(pull["number"])
        except (subprocess.CalledProcessError, OSError, ValueError, KeyError):
            return None
        pull["previousPaths"] = {
            change["filename"]: change["previous_filename"]
            for change in changes
            if change.get("filename") and change.get("previous_filename")
        }
    return pull["previousPaths"]


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


def owners_only(pull: dict[str, Any], loop: str | None) -> str | None:
    """Why only the owner's go on the head lets the PR merge, or None: it touches a path loop.md's `risk.merge_paths`
    names, whatever its labels, `spec.auto` and the verifier's `Risk:` line say, since the owner keeps the last look
    at those paths. Files the gate can't read hold, as a risk rule's `paths` do."""
    globs = settings(loop).get("risk", {}).get("merge_paths", [])
    if not globs:
        return None
    files = touched(pull)
    if files is None:
        return "the gate can't read every file the PR changes, so `risk.merge_paths` holds until the owner judges them"
    for glob in globs:
        for path in files:
            if fnmatch.fnmatch(path, glob):
                return f"it touches `{path}`, which `risk.merge_paths` names (`{glob}`), so only the owner approves its merge"
    return None


def head_passes(
    pull: dict[str, Any], loop: str | None
) -> tuple[str, list[tuple[int, dict[str, str]]]] | str:
    """The commit the verifier's passes judge, the head or the commit whose proofs it carries (carried), and those
    passes' numbers and lines (passes); a string names why none can be read."""
    found = passes(pull)
    if isinstance(found, str):
        return found
    head = pull["headRefOid"].lower()
    on_head = [(number, lines) for commit, number, lines in found if commit == head]
    if not on_head and found and isinstance(carry := carried(pull, loop, found[-1][0]), tuple):
        head = carry[0]
        on_head = [(number, lines) for commit, number, lines in found if commit == head]
    return head, on_head


def judged(pull: dict[str, Any], loop: str | None = None) -> str | None:
    """Why the verifier holds the change high, or None: the highest pass on the head (passes), or on the commit whose
    proofs the head carries (carried), says `Risk: high`, any other word than `low`, or has no `Risk:` line; a mixed
    PR's two verifiers both must say `low`. A head no review covers is None, since reviewed() then refuses the merge,
    or the PR needs no review (exempt, an exact revert)."""
    found = head_passes(pull, loop)
    if isinstance(found, str):
        return f"the gate can't read the verifier's `Risk:` line: PR #{pull['number']} {found}"
    head, on_head = found
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
    was built, while its `verifier` term still holds the merge; a path `risk.merge_paths` names (owners_only), under
    `spec.auto` too; or a review at the cap was not satisfied or left a
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
    if why := owners_only(pull, loop):
        return why
    if not spec_auto(loop):
        labels = names(pull).union(*(names(issue) for issue in issues))
        if why := ruled(labels, touched(pull), loop, judged(pull, loop)):
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
    # ponytail: one page of 100 through GraphQL; page when a feature branch takes more high-risk PRs than that
    found = fast(
        lambda: gh(
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
        ),
        # REST: every closed PR into the branch, the merged ones carrying the label
        lambda: "\n".join(
            str(pull["number"])
            for pull in rest_pages(f"pulls?state=closed&base={branch}&per_page=100")
            if pull.get("merged_at")
            and RISK_LABEL in {label["name"] for label in pull.get("labels") or []}
        ),
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
    hit = matches(terms, names(pull) | names(issue), touched(pull))
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
    anyway. An issue GitHub links without a body line closes on merge. Each line names the keyword the PR says
    (worded), the one it needs, and the label, path or spec line that decides it, since a line naming only the
    keyword to use reads as a description of the PR."""
    body = pull["body"] or ""
    kinds, found = links(body), []
    for issue in issues:
        judged = signoff(pull, issue, loop)
        if judged is None or any(label.startswith("wayfinder:") for label in names(issue)):
            continue
        number, kind, (needed, why) = issue["number"], kinds.get(issue["number"], CLOSES), judged
        says = worded(body, number, kind)
        if needed and kind == CLOSES:
            found.append(
                f"#{number}: {says}, but #{number} waits for the owner's sign-off after landing, since {why}:"
                f" use `Implements #{number}`, which leaves it open"
            )
        elif not needed and kind == IMPLEMENTS:
            found.append(
                f"#{number}: {says}, but #{number} needs no sign-off ({why}): use `Closes #{number}`, since"
                " `Implements` would leave it open for a sign-off nobody asked for"
            )
    return found


def worded(body: str, number: int, kind: str) -> str:
    """What the PR body says links issue #number with `kind` (links), the keyword as written (`Fixes #3`), or that
    GitHub links it as closing with no body line."""
    for closes, part, implements, found in CLOSING.findall(QUOTED.sub("", body)):
        word = closes or part or implements
        if (
            int(found) == number
            and (CLOSES if closes else IMPLEMENTS if implements else PART) == kind
        ):
            return f"the PR says `{word.capitalize()} #{number}`"
    return f"GitHub links #{number} to the PR as closing, with no line in its body"


def flag(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> list[str]:
    """Add `risk:high` to a high-risk PR that lacks it, so the board shows why it waits: take off every other `risk:*`
    label, since two give the board two answers, and comment the reason risk() gave. A line when GitHub refuses,
    never a failure, since the merge already waits for the owner either way. Added for the verifier's `Risk:` line,
    the comment is FLAGGED, and the label comes off once a later pass judges the risk low (unflag).
    The PR's board `Risk` field (BOARD_RISK) follows (boarded): `High` beside the label. A field already at `High` on a
    PR without the label adds it, naming the field in the comment, since whoever set it made the risk call; a lower
    field never takes the label off, since the label is the merge check's input and only the owner lowers a raise."""
    shown = board_risk(pull["number"])
    if RISK_LABEL in names(pull):
        return unflag(pull, issues, loop) + boarded(pull, loop, shown)
    if (why := risk(pull, issues, loop)) is not None:
        return raise_risk(pull, why, loop) + boarded(pull, loop, shown, high=True)
    if shown[1] != "High":
        return boarded(pull, loop, shown)
    # risk() said low, so the checks after flag() read the label added here to hold the merge
    why = f"the board's `{BOARD_RISK}` field says `High`"
    return raise_risk(pull, why, loop, mark=True)


def raise_risk(pull: dict[str, Any], why: str, loop: str | None, mark: bool = False) -> list[str]:
    """flag()'s raise: add `risk:high` for `why`, take off the other `risk:*` labels and comment the reason; `mark`
    puts the label on the PR as read here too, first, so a refused write still holds this run's merge."""
    where, before = f"PR #{pull['number']}", names(pull)
    if mark:
        pull["labels"] = {"nodes": [{"name": n} for n in sorted(before | {RISK_LABEL})]}
    try:
        label(pull["number"], RISK_LABEL, add=True)
    except subprocess.CalledProcessError as exc:
        return [
            f"{where}: could not add `{RISK_LABEL}` ({(exc.stderr or '').strip() or exc}): add it by hand"
        ]
    found = []
    for other in sorted(n for n in before if n.startswith("risk:")):
        try:
            label(pull["number"], other, add=False)
        except subprocess.CalledProcessError as exc:
            found.append(
                f"{where}: could not remove `{other}` beside `{RISK_LABEL}` ({(exc.stderr or '').strip() or exc}): remove it by hand"
            )
    if (verdict := judged(pull, loop)) and verdict in why:
        body = f"{FLAGGED}, since {why}. A later pass that says `Risk: low` takes it off.\n"
        failed = f"{where}: could not comment why the gate added `{RISK_LABEL}`, so it stays until a person removes it"
    else:
        body = f"`{RISK_LABEL}` added, since {why}.\n"
        failed = f"{where}: could not comment why `{RISK_LABEL}` was added ({why})"
    try:
        comment(pull["number"], body)
    except subprocess.CalledProcessError as exc:
        found.append(f"{failed} ({exc})")
    return found


def board() -> Any:
    """board.py beside this script, loaded on first use, since it imports this module: it reads this same one."""
    if "board" not in sys.modules:
        if here := sys.modules.get(__name__):
            sys.modules.setdefault("approvals", here)
        spec = importlib.util.spec_from_file_location("board", Path(__file__).with_name("board.py"))
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["board"] = module
    return sys.modules["board"]


def board_risk(number: int) -> tuple[dict[str, Any] | None, str]:
    """The board's lookup of the PR's `Risk` field (board.py) and the field's option, '' when unset or off the board;
    or None and why the board can't be read: no linked board or field, no `project` token scope, or an API error.
    A workflow's default token can't read a board a personal account owns, so the label alone decides there."""
    if _rest_only:
        return None, "GitHub refuses GraphQL here"
    try:
        found = board().lookup(number, BOARD_RISK)
        return found, board().value(found, BOARD_RISK) or ""
    except (ValueError, LookupError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        return None, (getattr(exc, "stderr", "") or "").strip() or str(exc)


def boarded(
    pull: dict[str, Any],
    loop: str | None,
    shown: tuple[dict[str, Any] | None, str],
    high: bool = False,
) -> list[str]:
    """Set the PR's board `Risk` field (board_risk's `shown`) to `High` beside `risk:high` (or `high`, raised this
    run), else to the verifier's `Risk:` word on the head (head_passes), so whoever makes the risk call sets it; no
    pass yet, or the field already at that option, leaves it. Best effort, like a column move: a board that can't
    be read or set is a line, never a failure, since the label is what the merge check reads."""
    if high or RISK_LABEL in names(pull):
        option = "High"
    elif isinstance(found := head_passes(pull, loop), str) or not found[1]:
        return []
    else:
        option = "High" if judged(pull, loop) else "Low"
    repo, said = shown
    if repo is not None and said == option:
        return []
    why = said
    if repo is not None:
        try:
            board().set_field(pull["number"], BOARD_RISK, option, repo)
            return []
        except (ValueError, LookupError, TypeError, OSError, subprocess.CalledProcessError) as exc:
            why = (getattr(exc, "stderr", "") or "").strip() or str(exc)
    return [
        (
            f"PR #{pull['number']}: could not set the board's `{BOARD_RISK}` field to `{option}` ({why}); the"
            f" `{RISK_LABEL}` label alone shows the risk"
        )
    ]


def unflaggable(
    pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None
) -> dict[str, Any] | None:
    """The PR without the `risk:high` the gate added for the verifier's `Risk:` line (FLAGGED), when nothing holds the
    change high without it and unflag would take it off; else None. Reads only, so a check can judge the PR as unflag
    leaves it."""
    flagged = [note["createdAt"] for note in notes(pull) if note["body"].startswith(FLAGGED)]
    added = [
        event["createdAt"]
        for event in pull["timelineItems"]["nodes"]
        if (event.get("label") or {}).get("name") == RISK_LABEL
    ]
    if not flagged or max(added, default="") > max(flagged):
        return None
    unlabelled = {**pull, "labels": {"nodes": [{"name": n} for n in names(pull) - {RISK_LABEL}]}}
    return unlabelled if risk(unlabelled, issues, loop) is None else None


def flagged_as(
    pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None
) -> dict[str, Any]:
    """The PR as `flag` would leave it, reading only (the board's field included): without the `risk:high` unflag
    would take off (unflaggable), or with the one a board `Risk` field at `High` adds beside a low risk() (flag's
    last case), so a check holds the merge for either as `flag` does in place."""
    if RISK_LABEL in names(pull):
        return unflaggable(pull, issues, loop) or pull
    if risk(pull, issues, loop) is None and board_risk(pull["number"])[1] == "High":
        return {
            **pull,
            "labels": {"nodes": [{"name": n} for n in sorted(names(pull) | {RISK_LABEL})]},
        }
    return pull


def unflag(pull: dict[str, Any], issues: list[dict[str, Any]], loop: str | None) -> list[str]:
    """Take off a `risk:high` the gate added for the verifier's `Risk:` line (FLAGGED) once nothing holds the change
    high without it, since the verifier re-judges a disputed risk. A label added after the gate's comment is a
    person's or the lead's raise, which only the owner lowers."""
    if (unlabelled := unflaggable(pull, issues, loop)) is None:
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


def texted(holder: dict[str, Any]) -> str:
    """The spec or plan named by its text: `sha256 <digest>` of the body as GitHub stores it, line ends made `\\n`.
    An approval names it, so any change to the text voids it wherever the text is read, GraphQL or REST."""
    body = (holder.get("body") or "").replace("\r\n", "\n")
    return f"sha256 {hashlib.sha256(body.encode()).hexdigest()}"


def versions(holder: dict[str, Any]) -> set[str]:
    """The names an approval of this spec or plan may carry: its text's (texted), and, where GraphQL gave its edit
    time, its last edit's (version), which approvals recorded before texts were named carry. REST has no edit time,
    so an approval of the edit alone is unproven there."""
    found = {texted(holder)}
    if "lastEditedAt" in holder:
        found.add(version(holder))
    return found


def last_change(holder: dict[str, Any]) -> str:
    """When the spec or plan last changed, at the latest: its last edit from GraphQL; from REST, which has no edit
    time, its `updatedAt`, which every edit moves (and any other change, so it is never too early)."""
    if "lastEditedAt" in holder:
        return str(holder.get("lastEditedAt") or holder["createdAt"])
    return str(holder.get("updatedAt") or holder["createdAt"])


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
    if lines and lines[0].strip() in VOICED.values():  # the plain line atop a merge record
        lines = lines[1:]
    if not lines or lines[0].strip() != f"Approved: {point}":
        return None
    return {
        key.strip().lower(): value.strip()
        for key, _, value in (line.partition(":") for line in lines[1:])
    }


def records(node: dict[str, Any], point: str) -> list[dict[str, str]]:
    """The approval records for `point` among a node's comments."""
    return [found for body in bodies(node) if (found := parsed(body, point)) is not None]


def current(node: dict[str, Any], point: str, key: str, value: str | set[str], by: str) -> bool:
    """Whether `by` approved `point` for this spec or plan: a record whose `key` is `value`, or one of them."""
    values = {value} if isinstance(value, str) else value
    return any(
        record.get("by") == by and record.get(key) in values for record in records(node, point)
    )


def approvals(where: str, node: dict[str, Any], point: str, holder: dict[str, Any]) -> list[str]:
    """One line per approval `point` lacks on `node`: the owner's record of this spec or plan (versions), and the
    label. A record of its last edit where the edit time can't be read (REST) says how to renew it."""
    found = []
    if not current(node, point, point, versions(holder), "owner"):
        owners = [record for record in records(node, point) if record.get("by") == "owner"]
        edited = "lastEditedAt" not in holder and any(
            str(record.get(point, "")).startswith(("as edited ", "as written "))
            for record in owners
        )
        found.append(
            f"{where} has no `Approved: {point}` record by the owner"
            + (
                f" for its current text: its record names the {point}'s last edit, which GitHub's REST API can't"
                f" date, so the owner approves it again (`approve {point} {node['number']} --by owner`) or the"
                " check runs where GraphQL answers"
                if edited
                else f" for its current {point}: the owner approves it again"
                if owners
                else ""
            )
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
    if not current(parent, "spec", "spec", versions(spec_holder(parent)), "owner"):
        return False
    login = (issue.get("author") or {}).get("login")
    return bool(login) and writer(login)


def spec_hold(pull: dict[str, Any], issue: dict[str, Any], loop: str | None) -> str | None:
    """Why `spec.auto: true` leaves the issue's spec to the owner, or None when the policy approves it: a risk rule (ruled)
    on the labels of the issue and the PR and the files pushed so far, so a file the spec didn't foresee still reaches
    the owner; or an author without write access, since anyone who can open an issue would otherwise have their own
    spec approved."""
    if why := ruled(names(issue) | names(pull), touched(pull), loop):
        return why
    login = (issue.get("author") or {}).get("login")
    if not (login and writer(login)):
        return f"its author {f'@{login}' if login else '(no account)'} can't write to the repo"
    return None


def scoped(pull: dict[str, Any], issue: dict[str, Any], loop: str | None) -> str | None:
    """Why the issue's SCOPED label doesn't approve its spec, or None when loop.md's `spec.auto` `paths` term
    (spec_paths) does: the term is set; neither the issue nor the PR carries `risk:high`; the risk rule, the
    verifier's `Risk:` line included once a review is read, doesn't hold on their labels and every path the PR
    touches (touched); its author can write to the repo; and every path the PR touches, a moved file's old name
    too, matches one of the globs. A file list the gate can't read in full voids it, so the change is never judged
    on part of its files. At `check build` before the PR exists the files are the branch's so far (unopened); the
    merge judges the PR's."""
    globs = spec_paths(loop)
    if not globs:
        return f"`spec.auto` names no `paths`, so `{SCOPED}` approves nothing"
    marked = [f"#{issue['number']}"] * (RISK_LABEL in names(issue))
    if RISK_LABEL in names(pull):  # an unopened branch has no number and no labels
        marked.append(f"PR #{pull['number']}")
    if marked:
        return f"`{RISK_LABEL}` is on {', '.join(marked)}"
    files = touched(pull)
    verdict = judged(pull, loop) if "reviews" in pull else None
    if why := ruled(names(issue) | names(pull), files, loop, verdict):
        return why
    login = (issue.get("author") or {}).get("login")
    if not (login and writer(login)):
        return f"its author {f'@{login}' if login else '(no account)'} can't write to the repo"
    if files is None:
        return "GitHub can't give every file the PR changes, an old name of a moved file included"
    outside = [path for path in files if not any(fnmatch.fnmatch(path, glob) for glob in globs)]
    if outside:
        return f"the PR changes {', '.join(f'`{path}`' for path in outside)}, outside `spec.auto`'s `paths`"
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
    found = fast(
        lambda: json.loads(
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
        ),
        # REST has no closing references: closed() reads each body's lines, as it does for the PR checked
        lambda: [
            {
                "number": other["number"],
                "headRefName": other["head"]["ref"],
                "baseRefName": other["base"]["ref"],
                "isDraft": bool(other.get("draft")),
                "body": other.get("body") or "",
                "closingIssuesReferences": [],
            }
            for other in rest_pages("pulls?state=open&per_page=100")[:OPEN_LIMIT]
        ],
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
    """A line when the PR's newest `## Demo` comment by a trusted author, not minimized as outdated, links a video or
    screenshot (a release asset, any URL but a user-attachments one) instead of embedding it, or embeds none; a PR
    with no demo has none. A stranger's demo neither holds nor clears the merge."""
    shown = lambda note: not note.get("isMinimized") and trusted(pull, note)
    demo = headed(pull, "## Demo", shown) if "comments" in pull else None
    if demo is None:
        return []
    urls = URL.findall(demo["body"])
    linked = [url for url in urls if not url.startswith(ATTACHMENT)]
    if not linked and urls:
        return []
    what = f"links {linked[0]}" if linked else "embeds no video or screenshot"
    return [
        (
            f"PR #{pull['number']}: its `## Demo` comment {what}: post the demo with the demo skill's"
            " `scripts/demo.sh`, which embeds each video or screenshot as an attachment that plays inline"
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
    (spec_policy), `spec.auto: true` does (spec_hold), or its `paths` term does an issue labelled SCOPED (scoped).
    A plan needs them where the `plan` rule asks. What the merge
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
        covered = every and spec_hold(pull, issue, loop) is None or spec_policy(issue, kinds)
        if not covered and SCOPED in labels:
            why = scoped(pull, issue, loop)
            covered = why is None
            if why:
                found.append(
                    f"{where}: its spec is the owner's to approve, though it carries `{SCOPED}`, since {why}"
                )
        if not covered:
            found += approvals(where, issue, "spec", spec_holder(issue))
        plan = headed(issue, "## Plan")
        if plan is not None:
            if matches(rule.get("plan", {}), labels, None):
                found += approvals(where, issue, "plan", plan)
        elif "plan" in rule.get("practice", {}):
            found.append(f"{where} has no `## Plan` comment, and one is due")
    if (
        point == "build" and "number" in pull
    ):  # before the PR exists (unopened) there is nothing to compare
        found += duplicates(pull, loop)
        # where a lead hands the PR over, so a wrong keyword is fixed before the PR reaches the landing queue
        if loop is not None:
            found += linked(pull, issues, loop)
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
    """The verifier's PR reviews in order, each as its commit, pass number and `VERDICT:`/`SATISFIED:`/`Risk:`/`Logic change:` lines: a body
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
                    if key.strip() in ("VERDICT", "SATISFIED", "Risk", LOGIC)
                },
            },
        )
        for review in found
        if (review.get("author") or {}).get("login") in trusted
    ]


def lower(verdicts: list[tuple[str, int, dict[str, str]]] | str) -> str | None:
    """The tier below the default (LOWER_TIER) the newest verifier pass names in its heading's family, the newest
    commit's highest pass (a mixed PR's two verifiers share one), or None; a fallback family (`agy`, `gemini`,
    `same-family`) counts as one: a heading naming no tier reads as the default, so verdicts written before tiers were named keep landing. `verdicts` is passes()'s."""
    if isinstance(verdicts, str) or not verdicts:
        return None
    head = verdicts[-1][0]
    on_head = [(number, lines) for commit, number, lines in verdicts if commit == head]
    last = max(number for number, _ in on_head)
    tiers = [
        found[1]
        for number, lines in on_head
        if number == last
        and (found := LOWER_TIER.search(lines["Family"]) or FALLBACK_FAMILY.search(lines["Family"]))
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
    since every commit after a verdict needs one of its own, unless the head carries that commit's proofs (carried: on
    the same tree, or where loop.md opts in, which prints a line either way), or on its commit the highest pass (a mixed PR's two
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


# the variable Claude Code sets to `true` in a cloud session's VM, where the checkout's signing key is the session's own
CLOUD = "CLAUDE_CODE_REMOTE"
# the config every git command takes during a cloud land (placed): sign and verify a squash with the landing key, through
# ssh-keygen itself rather than the VM's signing program, which signs with the session's key
SIGNING: list[str] = []


def in_cloud() -> bool:
    return os.environ.get(CLOUD) == "true"


def listed(public: str, signers: Path) -> bool:
    """Whether the public key `public` (`<type> <base64> [comment]`) is a line of the allowed signers file."""
    key = public.split()[:2]
    lines = signers.read_text().splitlines()
    return len(key) == 2 and any(
        fields[i : i + 2] == key
        for line in lines
        if not line.lstrip().startswith("#")
        for fields in [line.split()]
        for i in range(len(fields) - 1)
    )


@contextlib.contextmanager
def placed(loop: str | None) -> Any:
    """Refuse a land where loop.md's `land.where` (default `host`) excludes the place it runs, before any PR is read.
    In a cloud session (CLOUD) also refuse one without the `land` section, since GitHub's own merge is GraphQL there
    and signs with GitHub's key, and one whose `signing_key_env` variable is unset, empty or holds a key the allowed
    signers lack; else hold that key in a mode-0600 file in a fresh temporary directory, removed whatever happens, and
    sign each squash with it (SIGNING). The key and the variable's value are never printed."""
    global SIGNING
    land, cloud = settings(loop).get("land"), in_cloud()
    place = "a cloud session" if cloud else "a host"
    if cloud and land is None:
        raise Refused(
            "land in a cloud session needs loop.md's `land` section: without it GitHub merges, over GraphQL, which"
            " the session's proxy refuses, and signs with GitHub's key"
        )
    where = (land or {}).get("where", "host")
    if where not in ("both", "cloud" if cloud else "host"):
        raise Refused(f"loop.md's `land.where` is `{where}`, so land does not run in {place}")
    if not cloud:
        yield
        return
    name = land.get("signing_key_env")
    if not name:
        raise Refused(
            "land in a cloud session signs with the key in the variable loop.md's `land.signing_key_env` names,"
            " and it names none"
        )
    key = os.environ.get(name)
    if key is None:
        raise Refused(f"the variable {name} (loop.md's `land.signing_key_env`) is not set")
    if not key.strip():
        raise Refused(f"the variable {name} (loop.md's `land.signing_key_env`) is empty")
    signers = Path(land["allowed_signers"]).expanduser()
    if not signers.is_file():
        raise Refused(f"no allowed signers file at {signers}")
    folder = Path(tempfile.mkdtemp(prefix="land-key-"))
    try:
        file = folder / "key"
        with os.fdopen(os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
            out.write(key if key.endswith("\n") else key + "\n")
        public = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(file)],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        # ssh-keygen's error is not repeated: it is about the key, which stays unprinted
        if public.returncode:
            raise Refused(
                f"the variable {name} (loop.md's `land.signing_key_env`) holds no SSH private key without a"
                " passphrase"
            )
        if not listed(public.stdout, signers):
            raise Refused(
                f"the key in the variable {name} (loop.md's `land.signing_key_env`) is not in {signers}: add its"
                " public key there"
            )
        SIGNING = [
            *("-c", "gpg.format=ssh"),
            *("-c", f"user.signingkey={file}"),
            *("-c", "gpg.ssh.program=ssh-keygen"),
        ]
        try:
            yield
        finally:
            SIGNING = []
    finally:
        shutil.rmtree(folder, ignore_errors=True)


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
    # REST can't say whether a PR is queued, nor whether classic branch protection requires a queue (required_checks()
    # refuses only a ruleset's): a cloud session, where only REST answers, takes the project's word in loop.md
    if pull["isInMergeQueue"] is None and not (
        in_cloud() and settings(project()[1]).get("land", {}).get("merge_queue") is False
    ):
        return (
            f"{where}: GitHub's REST API doesn't say whether it is in a merge queue, which would merge it with GitHub's"
            " signature: land it where GraphQL answers, or, where the base requires no merge queue, say so with"
            " `merge_queue: false` in loop.md's `land` section"
        )
    # the URL as configured, before any `insteadOf` rewrite
    origin = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=False
    )
    if github_repo(origin.stdout.strip()) != pull["baseRepository"]["nameWithOwner"].lower():
        return f"this checkout's `origin` is not {pull['baseRepository']['nameWithOwner']}, where {where} lives"
    # with SIGNING, as the land signs: a cloud land's own key over the VM's
    config = subprocess.run(
        ["git", *SIGNING, "config", "--get", "user.signingkey"],
        capture_output=True,
        text=True,
        check=False,
    )
    gpg = subprocess.run(
        ["git", *SIGNING, "config", "--get", "gpg.format"],
        capture_output=True,
        text=True,
        check=False,
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
    if batch_queue(loop) and queued(pull, loop) is None:
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


def queued(pull: dict[str, Any], loop: str | None = None) -> list[str] | None:
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
        if (why := unproven(head, fields, loop)) is None:
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


def unproven(head: str, fields: dict[str, str], loop: str | None = None) -> str | None:
    """Why a batch proof's fields prove nothing about `head`, or None: its gate exited 0, the head has its own green
    local-ci pass under the gate command, the env the proof names, or entered the queue on its head proof (admitted),
    the stand-in the proof names, since a batch gate never stands in for the head's own pass, its merge commit's second
    parent is the head, so the head landed unchanged, its tree is the clean merge of its parents, so the queue resolved
    no conflict and added nothing, and the batch commit contains it."""
    merge, batch, code = (fields.get(key, "").lower() for key in ("Merge", "Batch", "Exit"))
    if code != "0":
        return f"the merge queue's gate on batch {batch} exited {code or 'with no exit code'}"
    # the proof's own line says which it entered on, so a record made later doesn't void an `Admitted:` proof
    if "Admitted" in fields:
        if (entry := admitted(head, loop)) is None:
            return (
                f"batch {batch} names the stand-in `{fields['Admitted']}`, but the head {head} has no green loop.md"
                f" `head_proof` status for its tree"
            )
        if fields["Admitted"] != entry:
            return f"batch {batch} names the head's stand-in `{fields['Admitted']}`, its head proof `{entry}`"
    elif (record := reusable(head)) is None:
        return (
            f"the head {head} has no green `local-ci --record` pass of its own under the gate command, which a batch"
            f" never stands in for{elsewhere(head)}"
        )
    # the comment names the env as posted, its home written `~` (public)
    elif (env := public(env_line(record["env"])[len("Env: ") :].strip())) != fields.get("Env"):
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
    A head with `verified`'s tree (same_tree) carries it with or without the setting, by one same_tree_line(). A
    string names why it carries nothing; None without the setting and with another tree."""
    if tree := same_tree(pull["headRefOid"], verified):
        return verified, [same_tree_line(verified, tree)]
    guard = settings(loop).get("carry_over_main")
    if guard is None:
        return None
    walked = base_merges(pull, verified)
    if isinstance(walked, str):
        return walked
    base, lines = pull["baseRefName"], []
    for commit, first, second in walked:
        found = merged(first, second, guard["except"], base)
        if isinstance(found, str):
            return found
        try:
            tree = git("rev-parse", f"{commit}^{{tree}}").strip()
        except (subprocess.CalledProcessError, OSError) as exc:
            return f"git failed reading {commit}: {exc}"
        if found[0] != tree:
            return f"{commit}'s tree is not git merge-tree's of its parents: the merge resolved or added something"
        lines.insert(0, carry_line(commit, first, second, found[1], base))
    return verified, lines


def same_tree(head: str, old: str) -> str | None:
    """The tree `head` and `old` both hold (tree_of), else None: a head whose tree is an earlier head's keeps that
    head's verdict (carried) and go (carried_go), since every file reviewed and approved there is byte-for-byte the
    same, as after a reword of commit messages only. A tree neither the clone nor origin has is None."""
    mine = tree_of(head)
    return mine if mine is not None and mine == tree_of(old) else None


def same_tree_line(old: str, tree: str) -> str:
    """The line check merge and land print when the head carries `old`'s verdict on the same tree (same_tree)."""
    return f"verdict on {old} carried: same tree {tree}"


def base_merges(pull: dict[str, Any], since: str) -> list[tuple[str, str, str]] | str:
    """Each commit on the PR head's first-parent line down to `since`, newest first, as (commit, first parent, second
    parent), when every one is a merge whose second parent is on the base (an ancestor of its tip), so nothing but
    merges of the base, conflict fixes and all, came after `since`; a string names the first commit that is anything
    else. Fail-closed: a git error is a why."""
    head, tip, base = pull["headRefOid"].lower(), pull["baseRefOid"].lower(), pull["baseRefName"]
    commit, found = head, []
    try:
        if not (fetched(head) and fetched(tip)):
            return f"the head or {base}'s head {tip} is not a commit origin has"
        while commit != since:
            it, its = ("it", "its") if commit == head else (commit, f"{commit}'s")
            parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
            if len(parents) != 2:
                return f"{it} is no merge of two parents"
            first, second = parents
            on_base = ["git", "merge-base", "--is-ancestor", second, tip]
            if subprocess.run(on_base, capture_output=True, check=False).returncode:
                return f"{its} second parent {second} is not on {base}"
            found.append((commit, first, second))
            commit = first
    except (subprocess.CalledProcessError, OSError) as exc:
        return f"git failed reading {commit}: {exc}"
    return found


def unforced(pull: dict[str, Any]) -> str | None:
    """The line check merge and brief print when every commit since the newest verdict's commit is a merge of the
    base (base_merges) and land posted no CONFLICTS comment naming a head that walk passes, so nothing forced the
    merge: land merges each head onto the base itself and gates that, and the merge only costs a gate and a verifier
    pass. None otherwise, a head or base tip that one fetch (fetched, in base_merges) cannot bring included, since the
    line is advice and blocks nothing."""
    verdicts = passes(pull)
    if isinstance(verdicts, str) or not verdicts or not (verified := verdicts[-1][0]):
        return None
    if verified == pull["headRefOid"].lower():
        return None
    walked = base_merges(pull, verified)
    if isinstance(walked, str):
        return None
    earlier = {first for _, first, _ in walked}
    try:
        found = notes(pull)
    except Refused:
        return None
    # as land writes it (merged_onto), by an account whose word counts, since anyone can comment on a public repo
    if any(
        note["body"].startswith(CONFLICTS)
        and trusted(pull, note)
        and earlier
        & {
            line[len("Head: ") :].strip().lower()
            for line in note["body"].splitlines()
            if line.startswith("Head: ")
        }
        for note in found
    ):
        return None
    base = pull["baseRefName"]
    return f"unforced merge of {base}: land merges heads itself (lead.md step 8); this pass is avoidable"


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
    # with CI too: batch refuses a head with neither, so it may not enter
    if reusable(head) is None and admitted(head, loop) is None:
        found.append(
            f"{where}: no `local-ci --record` pass on {head} under the gate command (approvals.py local-ci --record)"
            f"{nor_head_proof(loop)}{elsewhere(head)}"
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
    lines. A head with no such pass that entered the queue on its head proof (admitted) gets an `Admitted:` line naming
    that status and its tree in place of the env and time. Refused for a head with neither."""
    if not fetched(merge.lower()):
        raise Refused(f"merge {merge} is not a commit here or on origin")
    head = git("rev-parse", f"{merge}^2").strip()
    record, entry, loop = reusable(head), None, project()[1]
    if record is None and (entry := admitted(head, loop)) is None:
        raise Refused(
            f"the head {head} has no green `local-ci --record` pass of its own under the gate command"
            f"{nor_head_proof(loop)}: no batch proof without it{elsewhere(head)}"
        )
    try:
        tail = log.read_text(errors="replace").splitlines()[-LOG_TAIL:]
    except OSError:
        tail = []
    body = (
        f"{BATCHED}\nHead: {head}\nMerge: {merge}\nBatch: {batch_sha}\nExit: {code}\n"
        + (
            f"{env_line(record['env'])}Gated: {record['time']}\n"
            if record
            else f"Admitted: {entry}\n"
        )
        + f"Log: {log}\n"
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
    """A line while the change is high risk (risk) and no go is on the head (owned): the owner's, or with
    `loop.delegate: all` the delegate's. Into the default branch only such a head-pinned go counts, since a delegate
    acting through the owner's account adds a label no differently from the owner; into a feature branch the `approved:merge` label, added after the head's push, counts too, the
    owner's or the delegate's (delegate). `pushed(pull)` is when the head was pushed (default: GitHub's repository
    activity). A path `risk.merge_paths` names (owners_only) takes the owner's own go on the head, into any branch.
    """
    where, found = f"PR #{pull['number']}", []
    why = risk(pull, issues, loop)
    if why is None:
        return found
    carry, sole = carried_go(pull, loop), owners_only(pull, loop)
    by = carry[0] if isinstance(carry, tuple) else None
    if by == "owner" or by and not sole:
        return found
    command = f"`approve merge {pull['number']} --head {pull['headRefOid']} --by owner`"
    if sole:
        # neither the delegate's go nor the label, into any branch: the path is the owner's alone
        return [
            (
                f"{where} waits for the owner's go on its head ({command}; the delegate's go and `{MERGE_LABEL}` are"
                f" no go), since {sole}"
            )
        ]
    # why the go on an earlier head stops short of this one, so the lead knows what a new verdict could fix
    stale = [f"{where}: {carry}"] if isinstance(carry, str) else []
    if default(pull):
        return [
            (
                f"{where} waits for the owner's go on its head ({command}; into {pull['baseRefName']} `{MERGE_LABEL}`"
                f" is no go), since it is high risk: {why}"
            ),
            *stale,
        ]
    if MERGE_LABEL not in names(pull):
        return [
            (
                f"{where} waits for the owner's go on its head ({command}, or `{MERGE_LABEL}`), since it is high"
                f" risk: {why}"
            ),
            *stale,
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


def owned(pull: dict[str, Any], loop: str | None = None) -> str | None:
    """Whose go covers the PR's head, `owner` or `delegate`, else None: one on the head, or one carried to it
    (carried_go)."""
    found = carried_go(pull, loop)
    return found[0] if isinstance(found, tuple) else None


def carried_go(pull: dict[str, Any], loop: str | None) -> tuple[str, str] | str | None:
    """(whose, the head it is on) for the go (go_on) covering the PR's head: the go on the head itself, else the go
    on the head of the PR's newest merge record, when the head has that head's tree (same_tree), or every commit since
    is a merge of the base (base_merges) and the newest verifier pass on the head is satisfied with no blocker or major
    open and says `Logic change: none`, since the approver saw that change and a merge adds none to it. Any status on
    the head decides alone, so a go withdrawn there stays withdrawn. A string names why the older go carries nothing;
    None: no go to carry."""
    head = pull["headRefOid"]
    by = go_on(pull, head, loop)
    if by is not None:
        return (by, head) if by else None
    earlier = [
        record["head"]
        for record in records(pull, "merge")
        if record.get("head") and record["head"].lower() != head.lower()
    ]
    if not earlier or not (by := go_on(pull, earlier[-1], loop)):
        return None
    old = earlier[-1]
    if same_tree(head, old):
        return by, old
    why = unchanged(pull, old.lower())
    return f"the go on {old} carries nothing to {head}: {why}" if why else (by, old)


def unchanged(pull: dict[str, Any], old: str) -> str | None:
    """Why the PR's head may not keep the go on `old` (carried_go), or None: the newest verifier pass on the head is
    satisfied with no blocker or major open and says `Logic change: none`, and every commit since `old` is a merge of
    the base (base_merges). The verdict is read first, since it needs no git."""
    head = pull["headRefOid"].lower()
    verdicts = passes(pull)
    if isinstance(verdicts, str):
        return f"the PR {verdicts}"
    on_head = [(n, lines) for commit, n, lines in verdicts if commit == head]
    if not on_head:
        return f"no verifier review is on {head}"
    last = max(n for n, _ in on_head)
    same = [lines for n, lines in on_head if n == last]
    if not all(held(lines) for lines in same):
        return (
            f"the verifier's pass {last} on {head} is not satisfied, or has a blocker or major open"
        )
    if any(lines.get(LOGIC, "").lower().split()[:1] != ["none"] for lines in same):
        return f"the verifier's pass {last} on {head} does not say `{LOGIC}: none`"
    walked = base_merges(pull, old)
    return walked if isinstance(walked, str) else None


def go_on(pull: dict[str, Any], head: str, loop: str | None) -> str | None:
    """Whose go (go) is on `head`, `owner` or `delegate`; '' when a status there is no go; None with no status there:
    the newest `owner` status there by the account running this or a writer (a status is the repo's to write) is green,
    so a later one withdrawing it wins, and the PR holds the record by the same approver naming that head. The
    delegate's (its description says so) counts into the default branch only while the default branch's `delegate` is `all`, so
    removing the setting withdraws it. A status once turned from the label (LABELLED) is no go. GitHub unreachable: no
    go."""
    try:
        found = statuses(head)
    except (subprocess.CalledProcessError, OSError, ValueError):
        return ""
    for status in found:  # newest first
        login = (status.get("creator") or {}).get("login")
        if (
            status.get("context") != OWNER_GO
            or login is None
            or not (login == viewer() or writer(login))
        ):
            continue
        description = status.get("description") or ""
        by = DELEGATE if description.endswith(DELEGATED) else "owner"
        if (
            status.get("state") != "success"
            or description.endswith(LABELLED)
            or by == DELEGATE
            and default(pull)
            and delegation(base_policy(pull["baseRefName"], loop)) != "all"
        ):
            return ""
        return by if current(pull, "merge", "head", head, by) else ""
    return None


def whose(pull: dict[str, Any], loop: str | None) -> list[str]:
    """The line check merge and land print for a head that carries a go (owned): whose it is, and the head it was given
    on when carried there (carried_go)."""
    found = carried_go(pull, loop)
    if not isinstance(found, tuple):
        return []
    by, old = found
    head = f"PR #{pull['number']}: the go on {old}"
    line = f"{head} is the delegate's{DELEGATED}" if by == DELEGATE else f"{head} is the owner's"
    if old != pull["headRefOid"] and (tree := same_tree(pull["headRefOid"], old)):
        line += f", carried to {pull['headRefOid']}: same tree {tree}"
    elif old != pull["headRefOid"]:
        line += (
            f", carried to {pull['headRefOid']}: every commit since is a merge of {pull['baseRefName']}, and the"
            f" verifier's pass on it says `{LOGIC}: none`"
        )
    return [line]


def go(number: int, head: str, by: str = "owner", withdraw: bool = False) -> int:
    """approve merge: the go on `head`, the PR's head the approver was shown, on their word: the owner's, or with `by`
    `delegate` the delegated approver's under the owner's delegation; the status OWNER_GO on that commit and a record
    naming it, whose first line says whose go it is; with `withdraw`, a newer failing status and record that take it
    back. The script writes every word, so no agent's description of the change travels with it. A head that moved is
    refused, since the approver saw the one they were asked about. The delegate's go into the default branch is
    refused unless `delegate` is `all` in the policy on `origin/<base>` (base_policy), since without it only the owner's
    go covers that branch and a branch's own edit is not the owner's, and on a PR
    touching a path `risk.merge_paths` names (owners_only) into any branch, since that merge is the owner's alone."""
    pull = pull_request(number)
    if pull["state"] != "OPEN":
        raise Refused(f"PR #{number} is {pull['state'].lower()}: nothing to approve")
    if pull["headRefOid"].lower() != head.lower():
        raise Refused(
            f"PR #{number}'s head is {pull['headRefOid']}, not {head}: ask about the head it has now"
        )
    head = pull["headRefOid"]
    who = "the delegate" if by == DELEGATE else "the owner"
    if by == DELEGATE and not withdraw:
        loop = project()[1]
        if sole := owners_only(pull, loop):
            raise Refused(
                f"PR #{number}: the delegate's go is no go here, since {sole}: it waits for the owner's"
            )
        if default(pull) and delegation(base := base_policy(pull["baseRefName"], loop)) != "all":
            raise Refused(
                f"PR #{number} targets {pull['baseRefName']}, the default branch: the delegate's go covers it only"
                f" with `loop.delegate: all` in {pull['baseRefName']}'s {source(base)}, so it waits for the owner's"
            )
    if withdraw:
        # the label off too, since into a feature branch it is a go of its own
        label(number, MERGE_LABEL, add=False)
        post_status(
            head, OWNER_GO, f"{who.capitalize()} withdrew their go on {head[:12]}", state="failure"
        )
        comment(number, f"Withdrawn: merge\nBy: {by}\nHead: {head}\n")
        print(f"PR #{number}: {who}'s go on {head} is withdrawn")
        return 0
    if by == DELEGATE:
        post_status(head, OWNER_GO, f"The delegate's go on {head[:12]}{DELEGATED}")
    else:
        post_status(head, OWNER_GO, f"The owner's go on {head[:12]}")
    comment(number, f"{VOICED[by]}\nApproved: merge\nBy: {by}\nHead: {head}\n")
    print(f"PR #{number}: {who}'s go is on {head}{DELEGATED if by == DELEGATE else ''}")
    if by != DELEGATE and NEEDS_OWNER in names(pull):
        # the owner's go names this PR, so the hold it waited on is theirs to lift; the delegate's never is
        label(number, NEEDS_OWNER, add=False)
        print(f"PR #{number}: `{NEEDS_OWNER}` removed, since the owner's go names it")
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


# how GitHub, or a cloud session's proxy in front of it, refuses GraphQL: `gh` ends its error with it
FORBIDDEN = "HTTP 403"
# set once GraphQL was refused, so the rest of this run reads REST without asking GraphQL again
_rest_only = False
Answer = TypeVar("Answer")


def fast(graphql: Callable[[], Answer], rest: Callable[[], Answer]) -> Answer:
    """GraphQL's answer, the fast path, or REST's where GitHub refuses GraphQL with a 403, as a cloud session's proxy
    does. REST reads the same fields call by call, in the same shape. After one refusal the run reads REST alone, so a
    run there makes one refused GraphQL call at most. Any other error raises."""
    global _rest_only
    if not _rest_only:
        try:
            return graphql()
        except subprocess.CalledProcessError as exc:
            if FORBIDDEN not in (exc.stderr or ""):
                raise
            _rest_only = True
    return rest()


def rest(path: str) -> Any:
    return json.loads(gh("api", path))


def rest_pages(path: str, items: str = ".[]") -> list[Any]:
    """Every item of a paged REST list, `items` picking them out of each page."""
    out = gh("api", "--paginate", f"repos/{{owner}}/{{repo}}/{path}", "--jq", items)
    return [json.loads(line) for line in out.splitlines()]


def actor(user: dict[str, Any] | None) -> dict[str, Any] | None:
    """A REST user as GraphQL names it: its login without the `[bot]` REST adds, and its type."""
    if not user:
        return None
    return {"login": user["login"].removesuffix("[bot]"), "__typename": user.get("type") or "User"}


def rest_notes(number: int) -> dict[str, Any]:
    """An issue's or PR's comments from REST, every page, as GraphQL's `comments` reads them. REST has no edit time,
    so a note has no `lastEditedAt` (versions() then reads its text alone), only `updatedAt`, which every edit moves;
    nor can this account's right to minimize be read, so approve() minimizes nothing it read here."""
    nodes = [
        {
            "id": found["node_id"],
            "author": actor(found.get("user")),
            "body": found.get("body") or "",
            "createdAt": found["created_at"],
            "updatedAt": found["updated_at"],
            "isMinimized": bool(found.get("minimized")),
            "viewerCanMinimize": False,
        }
        for found in rest_pages(f"issues/{number}/comments?per_page=100")
    ]
    return {"totalCount": len(nodes), "nodes": nodes}


# REST timeline events as GraphQL's timelineItems types them
TIMELINE = {
    "labeled": "LabeledEvent",
    "assigned": "AssignedEvent",
    "ready_for_review": "ReadyForReviewEvent",
}


def rest_timeline(number: int) -> dict[str, Any]:
    """An issue's or PR's label, assign and ready events from REST's timeline, every page."""
    nodes = []
    for event in rest_pages(f"issues/{number}/timeline?per_page=100"):
        if (kind := TIMELINE.get(event.get("event"))) is None:
            continue
        found: dict[str, Any] = {"__typename": kind, "createdAt": event.get("created_at")}
        if kind == "LabeledEvent":
            found |= {"actor": actor(event.get("actor")), "label": event.get("label")}
        if kind == "AssignedEvent":
            found["assignee"] = actor(event.get("assignee"))
        nodes.append(found)
    return {"nodes": nodes}


def rest_specced(found: dict[str, Any]) -> dict[str, Any]:
    """The SPECCED fields of a REST issue: its body and labels, and its comments read too. No `lastEditedAt`: REST has
    no edit time, so the spec's text names its version (versions)."""
    return {
        "number": found["number"],
        "body": found.get("body") or "",
        "createdAt": found["created_at"],
        "updatedAt": found["updated_at"],
        "labels": {"nodes": [{"name": label["name"]} for label in found.get("labels") or []]},
        "comments": rest_notes(found["number"]),
    }


def rest_issue(number: int) -> dict[str, Any] | None:
    """Issue #number as ISSUE reads it, from REST; None for a pull request, as GraphQL's `... on Issue` gives."""
    found = rest(f"repos/{{owner}}/{{repo}}/issues/{number}")
    if "pull_request" in found:
        return None
    try:
        parent = rest_specced(rest(f"repos/{{owner}}/{{repo}}/issues/{number}/parent"))
    except subprocess.CalledProcessError as exc:
        if "HTTP 404" not in (exc.stderr or ""):
            raise
        parent = None
    return rest_specced(found) | {
        "author": actor(found.get("user")),
        "parent": parent,
        "assignees": {"nodes": [actor(user) for user in found.get("assignees") or []]},
        "timelineItems": rest_timeline(number),
    }


# REST's file status as GraphQL's changeType
CHANGE_TYPES = {"added": "ADDED", "removed": "DELETED", "renamed": "RENAMED", "copied": "COPIED"}
# a trailer naming a commit's co-author, which GraphQL resolves to an account and REST does not
CO_AUTHOR = re.compile(r"^co-authored-by:", re.IGNORECASE | re.MULTILINE)


def rest_authored(number: int, total: int) -> dict[str, Any]:
    """A PR's commits as `authored` reads them, from REST: each commit's author and committer account. A co-author
    trailer, which only GraphQL resolves to an account, counts as an author not read, so exempt() exempts nothing."""
    nodes = []
    for found in rest_pages(f"pulls/{number}/commits?per_page=100"):
        authors = [{"user": actor(found.get("author"))}]
        committer = actor(found.get("committer"))
        # GitHub's web-flow commits for a bot or the API: GraphQL gives that committer no account
        if committer and committer["login"] == "web-flow":
            committer = None
        co = len(CO_AUTHOR.findall((found.get("commit") or {}).get("message") or ""))
        nodes.append(
            {
                "commit": {
                    "authors": {"totalCount": 1 + co, "nodes": authors},
                    "committer": {"user": committer},
                }
            }
        )
    return {"totalCount": total, "nodes": nodes}


def rest_latest(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each reviewer's newest review that approves, requests changes or was dismissed: a comment-only review
    leaves a reviewer's request for changes standing, as GitHub's review decision reads it."""
    latest: dict[str, dict[str, Any]] = {}
    for review in reviews:
        if review["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[(review.get("author") or {}).get("login") or ""] = review
    return list(latest.values())


def rest_checks(head: str) -> dict[str, Any]:
    """The head's checks as `statusCheckRollup` reads them, from REST: every check run (each rerun too), named by its
    workflow, and each status context's newest state."""
    runs = rest_pages(f"commits/{head}/check-runs?filter=all&per_page=100", ".check_runs[]")
    suites = {
        suite["id"]: suite
        for suite in rest_pages(f"commits/{head}/check-suites?per_page=100", ".check_suites[]")
    }
    flows = {
        run["check_suite_id"]: run["name"]
        for run in rest_pages(f"actions/runs?head_sha={head}&per_page=100", ".workflow_runs[]")
    }
    nodes: list[dict[str, Any]] = []
    for run in runs:
        suite = (run.get("check_suite") or {}).get("id")
        flow = flows.get(suite)
        nodes.append(
            {
                "__typename": "CheckRun",
                "name": run["name"],
                "status": (run.get("status") or "").upper(),
                "conclusion": (run.get("conclusion") or "").upper() or None,
                "startedAt": run.get("started_at"),
                "completedAt": run.get("completed_at"),
                "checkSuite": {
                    "status": ((suites.get(suite) or {}).get("status") or "").upper(),
                    "workflowRun": {"workflow": {"name": flow}} if flow else None,
                },
            }
        )
    combined = rest(f"repos/{{owner}}/{{repo}}/commits/{head}/status?per_page=100")
    for status in combined.get("statuses") or []:
        nodes.append(
            {
                "__typename": "StatusContext",
                "context": status["context"],
                "state": status["state"].upper(),
                "createdAt": status.get("created_at"),
                "targetUrl": status.get("target_url"),
            }
        )
    total = len(nodes) - len(combined.get("statuses") or []) + combined.get("total_count", 0)
    return {"contexts": {"totalCount": total, "nodes": nodes}}


def rest_threads(number: int) -> dict[str, Any]:
    """A PR's review threads, whether each is resolved, from the review-thread route a cloud session's GitHub proxy
    serves (GitHub's own REST has none). Where it is missing, as on a host whose GraphQL refused for another reason,
    the error raises: unresolved threads are never read as none."""
    threads = rest(f"repos/{{owner}}/{{repo}}/pulls/{number}/ccr/review_threads")
    nodes = [{"isResolved": bool(thread.get("resolved"))} for thread in threads]
    return {"totalCount": len(nodes), "nodes": nodes}


def rest_pull(pr: int) -> dict[str, Any]:
    """PR #pr as PULL reads it, from REST, call by call. `closingIssuesReferences` is empty, since REST has no such
    link: the PR's issues are its body's `Closes`, `Part of` and `Implements` lines (closing_issues). Whether it is in
    a merge queue can't be read: `isInMergeQueue` is None, which unsignable() refuses unless a cloud session's loop.md
    says `merge_queue: false`."""
    found = rest(f"repos/{{owner}}/{{repo}}/pulls/{pr}")
    base, head = found["base"], found["head"]
    reviews = [
        {
            "author": actor(review.get("user")),
            "state": review["state"],
            "body": review.get("body") or "",
            "commit": {"oid": review.get("commit_id") or ""},
        }
        for review in rest_pages(f"pulls/{pr}/reviews?per_page=100")
    ]
    files = [
        {"path": file["filename"], "changeType": CHANGE_TYPES.get(file["status"], "MODIFIED")}
        for file in pr_changes(pr)
    ]
    state = "MERGED" if found.get("merged") else found["state"].upper()
    return {
        "id": found["node_id"],
        "number": found["number"],
        "title": found["title"],
        "isCrossRepository": (head.get("repo") or {}).get("full_name") != base["repo"]["full_name"],
        "author": actor(found.get("user")),
        "assignees": {"nodes": [actor(user) for user in found.get("assignees") or []]},
        "state": state,
        "isDraft": bool(found.get("draft")),
        # REST's true or false, or null while GitHub computes it, as GraphQL's MergeableState reads them
        "mergeable": {True: "MERGEABLE", False: "CONFLICTING"}.get(
            found.get("mergeable"), "UNKNOWN"
        ),
        "autoMergeRequest": {"enabledAt": None} if found.get("auto_merge") else None,
        "isInMergeQueue": None,
        "body": found.get("body") or "",
        "baseRefName": base["ref"],
        # the base branch's tip now, as GraphQL's baseRefOid is; REST's base.sha is the tip when the PR last synced
        "baseRefOid": rest(f"repos/{{owner}}/{{repo}}/branches/{base['ref']}")["commit"]["sha"],
        "headRefName": head["ref"],
        "headRefOid": head["sha"],
        "baseRepository": {
            "nameWithOwner": base["repo"]["full_name"],
            "defaultBranchRef": {"name": base["repo"]["default_branch"]},
        },
        "labels": {"nodes": [{"name": label["name"]} for label in found.get("labels") or []]},
        "comments": rest_notes(pr),
        "files": {"totalCount": found.get("changed_files") or len(files), "nodes": files},
        "latestReviews": {"nodes": rest_latest(reviews)},
        "reviews": {"totalCount": len(reviews), "nodes": reviews},
        "reviewThreads": rest_threads(pr),
        "authored": rest_authored(pr, found.get("commits") or 0),
        "timelineItems": rest_timeline(pr),
        "commits": {"nodes": [{"commit": {"statusCheckRollup": rest_checks(head["sha"])}}]},
        "closingIssuesReferences": {"nodes": []},
    }


def pull_request(pr: int) -> dict[str, Any]:
    return fast(
        lambda: _graphql(_repository(f"pullRequest(number: $n) {{ {PULL} }}"), n=pr)["pullRequest"],
        lambda: rest_pull(pr),
    )


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
    def rest_read() -> dict[str, Any]:
        found = rest_issue(number)
        if found is None:
            raise Refused(f"#{number} is a pull request, not an issue")
        return found

    node: dict[str, Any] = fast(
        lambda: _graphql(_repository(f"issue(number: $n) {{ {ISSUE} }}"), n=number)["issue"],
        rest_read,
    )
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
        found = fast(
            lambda: list(
                _graphql(
                    f"query($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {aliases} }} }}"
                ).values()
            ),
            lambda: [rest_issue(n) for n in unlinked],
        )
        issues = issues + [issue for issue in found if issue]
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
    except subprocess.CalledProcessError as exc:
        # a cloud session's proxy refuses this path; the repo's own permissions answer it for the account running this
        # alone, and anyone else still can't, so a stranger never counts as a writer
        if FORBIDDEN not in (exc.stderr or "") or login != viewer():
            return False
        try:
            mine = rest("repos/{owner}/{repo}").get("permissions") or {}
        except subprocess.CalledProcessError:
            return False
        return bool(mine.get("push") or mine.get("maintain") or mine.get("admin"))
    return permission.strip() in WRITE


def current_pr() -> int | None:
    def graphql() -> int | None:
        try:
            return int(gh("pr", "view", "--json", "number", "--jq", ".number"))
        except subprocess.CalledProcessError as exc:
            if "no pull requests found" in exc.stderr:
                return None
            raise

    def rest_read() -> int | None:
        # the open PR whose head is this branch of origin's repo, as `gh pr view` finds it
        branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
        owner = rest("repos/{owner}/{repo}")["owner"]["login"]
        found = rest_pages(f"pulls?state=open&head={owner}:{branch}&per_page=100")
        return int(found[0]["number"]) if found else None

    return fast(graphql, rest_read)


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
    """The base's docs/agents/issue-tracker.md and its policy, None for one it lacks: a repo without the files has no
    rules, and its issues no label shape. Each file is read from `origin/<base>` (policy_base), the ref `land` builds
    its merge on, so a PR can't loosen its own gate and a checkout behind its base can't hold an old one; a copy in the
    working tree that differs gets one stderr line naming the file and both commits, and the base's is used. Without
    that ref (no origin) the working tree's are read, with one stderr line saying so. The policy is gatekeeper.md's (a
    Policy), else loop.md's `## Settings` block, read with a deprecation line; a project with both is refused, since
    two sources of the bar would drift. Settings off their schema are refused here, before any proof is printed or any
    PR touched."""
    root = toplevel()
    tracker, loop, policy = (policy_file(root, path) for path in (TRACKER, LOOP, POLICY))
    loop = chosen(loop, policy)
    if tracker is not None:
        tracker_settings(tracker)
    return tracker, loop


def policy_file(root: Path, path: Path) -> str | None:
    """`path` as project() reads it: from `origin/<base>` (policy_base), None where the base lacks it, printing
    `differs` once when the working tree's copy is another; from the working tree, printing `unbased` once, when there
    is no such ref."""
    found = policy_base(str(root))
    held = read(root / path) if (root / path).exists() else None
    if found is None:
        unbased(str(root))
        return held
    ref, tip = found
    shown = subprocess.run(
        ["git", "-C", str(root), "show", f"{tip}:./{path.as_posix()}"],
        capture_output=True,
        text=True,
        check=False,
    )
    based = shown.stdout if shown.returncode == 0 else None
    if held != based:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        differs(path.as_posix(), head or "no commit", ref, tip)
    return based


def policy_base(root: str) -> tuple[str, str] | None:
    """The ref the policy is read from in the checkout at `root`, `origin/<base>` for its default branch
    (default_base), and that ref's commit now, since `land` fetches it during a run; None without such a ref."""
    base = default_base(root) or ""  # none: `refs/remotes/origin/` names no commit
    tip = subprocess.run(
        [
            "git",
            "-C",
            root,
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/remotes/origin/{base}^{{commit}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return (f"origin/{base}", tip) if tip else None


@functools.cache
def default_base(root: str) -> str | None:
    """The default branch of the checkout at `root`, as base_branch finds it (origin/HEAD, else what `origin` says its
    HEAD is), None when neither answers. Once per run, since project() is read many times and asking origin is a
    network call."""

    def ask(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, text=True, check=False
        )
        return done.stdout.strip() if done.returncode == 0 else ""

    if base := ask("symbolic-ref", "--short", "refs/remotes/origin/HEAD").removeprefix("origin/"):
        return base
    for line in ask("ls-remote", "--symref", "origin", "HEAD").splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split("\t")[0].removeprefix("ref: refs/heads/")
    return None


@functools.cache
def unbased(root: str) -> None:
    """One line per run and checkout, however often the policy is read; none for a directory that is no checkout (a
    test's, since toplevel() refuses one), which has no base to fall back from."""
    inside = subprocess.run(
        ["git", "-C", root, "rev-parse", "--is-inside-work-tree"], capture_output=True, check=False
    )
    if inside.returncode:
        return
    print(
        "approvals.py: no origin/<base> ref, so the policy is read from the working tree",
        file=sys.stderr,
    )


@functools.cache
def differs(path: str, head: str, ref: str, tip: str) -> None:
    """One line per run, file and pair of commits, however often the policy is read."""
    print(
        f"approvals.py: {path} in the working tree (at {head}) differs from {ref}'s (at {tip}): using {ref}'s",
        file=sys.stderr,
    )


def chosen(loop: str | None, policy: str | None) -> str | None:
    """The policy of a loop.md and a gatekeeper.md's texts, None for one missing (project): gatekeeper.md's (a Policy),
    else loop.md's `## Settings` block, read with a deprecation line; both holding one is refused, since two sources of
    the bar would drift. Settings off their schema are refused here."""
    if policy is not None:
        if loop is not None and SETTINGS.search(section(loop, "Settings")):
            raise Refused(
                f"both {POLICY} and {LOOP}'s ## Settings hold a policy: keep it in {POLICY} alone"
            )
        loop = Policy(policy)
    elif loop is not None:
        moved()
    settings(loop)
    return loop


def base_policy(base: str, checkout: str | None) -> str | None:
    """The policy on `origin/<base>` after a fetch of it, chosen from its files as project() chooses the default
    branch's, since a branch's own edit of the policy is not the one the owner approved; `checkout`, project()'s, when
    that ref holds neither file (or no fetch ever made it), today's rule. A failed fetch reads the ref as last fetched."""
    ref = f"refs/remotes/origin/{base}"
    root = toplevel()
    subprocess.run(
        ["git", "-C", str(root), "fetch", "-q", "origin", f"+refs/heads/{base}:{ref}"],
        capture_output=True,
        check=False,
    )

    def shown(path: Path) -> str | None:
        found = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:{path.as_posix()}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return found.stdout if found.returncode == 0 else None

    loop, policy = shown(LOOP), shown(POLICY)
    if loop is None and policy is None:
        return checkout
    return chosen(loop, policy)


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
            value = texted(holder)
            if current(issue, point, point, versions(holder), "owner"):
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
            if added[-1]["createdAt"] <= last_change(holder):
                print(
                    f"#{number}: the owner's `{name}` was added before the {point}'s last edit ({version(holder)}): the"
                    " owner adds it again"
                    if "lastEditedAt" in holder
                    else f"#{number}: the owner's `{name}` can't be dated after the {point}'s last edit, since GitHub's"
                    f" REST API gives no edit time and the {point} changed at {last_change(holder)}, after it: the owner"
                    f" records it with `approve {point} {number} --by owner`, or the check runs where GraphQL answers"
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
    reads its issues from `named` and the reverted PR's risk from `reverted` instead). At merge, a PR that itself carries
    `needs-owner` waits for the owner, so no batch takes a PR held for their go."""
    held = (
        [f"#{pull['number']} waits for the owner ({NEEDS_OWNER})"]
        if point == "merge" and NEEDS_OWNER in names(pull)
        else []
    )
    revert, found = reverts(pull)
    found = held + found
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


# what GitHub says of a PR number no PR has: GraphQL's refusal, REST's 404
NO_PULL = ("Could not resolve to a PullRequest", "Not Found")


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
    try:
        pull = pull_request(pr)
    except subprocess.CalledProcessError as exc:
        if point == "build" and any(text in (exc.stderr or "") for text in NO_PULL):
            return unbuilt(
                pr, tracker, loop
            )  # a number no PR has is the issue's, as `--issue` reads it
        raise
    if point == "queue" and head is not None:
        return queueable(pull, head, tracker, loop)
    if point == "merge" and (why := outside(pull, loop)):
        print(why)
        return 0
    found, issues = gated(point, pull, tracker, loop)
    # flag() first, since a `risk:high` it takes off no longer holds the merge
    after = flag(pull, issues, loop) if point == "merge" else [] if found else claim(pull, issues)
    waiting = waits(pull, issues, loop) if point == "merge" else []
    used = (
        whose(pull, loop)
        if point == "merge" and not found and not waiting and risk(pull, issues, loop)
        else []
    )
    # advice, so it prints whatever else holds the merge and changes no exit code
    advice = (
        [f"PR #{pull['number']}: {said}"] if point == "merge" and (said := unforced(pull)) else []
    )
    for line in holds(pull, issues, loop) + found + waiting + after + used + advice:
        print(line)
    return 1 if found else WAITING if waiting else 0


def unopened() -> dict[str, Any]:
    """The PR `check build` judges an issue's spec beside before it exists: no labels, and the files the branch has
    changed since it left origin's default branch, as a PR's would be at `check build`; when git can't tell, more files
    than it lists (paths() None), so a `paths` risk rule holds rather than reading as unmatched."""
    try:
        base = git("rev-parse", "--abbrev-ref", "origin/HEAD").strip()
        # NUL-separated, since git quotes a non-ASCII name and a name may hold spaces
        # --no-renames: a moved file lists its old name too, since moving it out of a ruled path changes it
        found = git("diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD").split("\0")[:-1]
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


def land(pr: int | Sequence[int] | None, wait: bool = False, only: bool = False) -> int:
    """landing() once, or with `wait` again every POLL seconds while it waits on something time clears, printing each
    new state once: until it ends, or exit 3 at CEILING."""
    if not wait:
        return landing(pr, only)[0]
    deadline, said = time.monotonic() + CEILING, ""
    while True:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code, again = landing(pr, only)
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


def landing(pr: int | Sequence[int] | None, only: bool = False) -> tuple[int, bool]:
    """Land every landable PR into the base (the first named PR's, else the default branch) as one gated batch, under
    the landing lock, where loop.md lets land run (placed) (`only`: the named PRs alone); the exit, and whether a wait
    would end it (lock, CI on a head), so land --wait runs it again."""
    tracker, loop = project()
    with placed(loop):
        return landing_here(pr, tracker, loop, only)


def landing_here(
    pr: int | Sequence[int] | None, tracker: str | None, loop: str | None, only: bool = False
) -> tuple[int, bool]:
    numbers = [] if pr is None else [pr] if isinstance(pr, int) else list(dict.fromkeys(pr))
    named: list[dict[str, Any]] = []
    worst = 0  # of the named PRs that end here, 1 over 3 over 0
    for number in numbers:
        pull = pull_request(number)
        if pull["state"] == "MERGED":
            print(f"PR #{number} is merged")
        elif pull["state"] != "OPEN":
            if len(numbers) == 1:
                raise Refused(f"PR #{number} is closed: nothing to land")
            print(f"PR #{number} is closed: nothing to land")
            worst = 1
        elif named and pull["baseRefName"] != named[0]["baseRefName"]:
            print(
                f"PR #{number} targets {pull['baseRefName']}, not {named[0]['baseRefName']} like #{named[0]['number']}:"
                " land one base at a time"
            )
            worst = 1
        else:
            named.append(pull)
    if numbers and not named:
        return worst, False
    base = (
        named[0]["baseRefName"]
        if named
        else fast(
            lambda: gh(
                "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"
            ).strip(),
            lambda: rest("repos/{owner}/{repo}")["default_branch"],
        )
    )
    # a draft is ready before the wait for the lock, so the holder's next batch includes it
    named = readied(named, base, tracker, loop)
    previous = {sig: signal.getsignal(sig) for sig in STOPS}
    stoppable = {sig for sig, handler in previous.items() if handler is not signal.SIG_IGN}
    # every lock commit pushed, each before its push; taken stays None while the last one's push may have reached origin
    held: list[str] = []
    taken = None
    try:
        for sig in stoppable:  # a land under nohup still outlives a hangup
            signal.signal(sig, stopped)
        taken = locked(base, held, named[0]["number"] if named else None)
        if not taken:
            # a named PR left out already is a refusal, which the wait for the lock doesn't clear: 1 over 3
            return (1 if worst else WAITING), True
        # the base as origin has it once the lock is ours, so no land moved it between this fetch and the batch
        git("fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
        return batched(named, base, tracker, loop, only, held, worst)
    finally:
        # a stop from here on waits, blocked, until the lock is released and the handlers are back: raised inside the
        # release it would kill its push and leave the lock. The push runs in a session of its own, since some of its
        # children (ssh, gh as the credential helper) unblock the signals, and a stop of the land's group would end them
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, STOPS)
        if held and taken is not False:
            released = unlock(base, held[-1])
            if released.returncode and taken:
                print(
                    f"the landing lock {lock_name(base)} was not released: {' '.join(released.stderr.split())}"
                )
        for sig, handler in previous.items():
            if handler is not None:  # None: a handler set outside Python, which can't be put back
                signal.signal(sig, handler)
        waiting = signal.sigpending() & stoppable
        # taken here, so a stop that waited ends the land as one caught earlier would, not by the default handler
        for sig in waiting:
            signal.sigwait({sig})
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        if waiting:
            sys.exit(128 + min(waiting))


def stopped(signum: int, _frame: Any) -> None:
    """A land stopped by SIGTERM or SIGHUP (a killed process group, a harness timeout) unwinds, so landing's finally
    releases the lock. Further stops are ignored first: `uv run` forwards the same signal again, and a second exit
    raised on the way to the release would cut landing's cleanup short. SIGKILL can't be caught, and leaves the lock to
    be broken as stale."""
    for sig in STOPS:
        signal.signal(sig, signal.SIG_IGN)
    sys.exit(128 + signum)


def lock_name(base: str) -> str:
    """The landing lock's branch for `base`, as messages name it."""
    return LOCK.format(base).removeprefix("refs/heads/")


def lock_commit(title: str, parent: str | None, pr: int | None = None) -> str:
    """A landing lock commit: the empty tree, `title` (HELD or FREE) with [skip ci], `parent` the tip it moves on from,
    and in its body the pid and the PR `pr` it lands last (so a waiting land reads the lock as released once that PR
    merged: released; no hostname goes on the public branch), then a random value, since two lands in the same
    second, under one identity, would otherwise build one commit, and the second push of it would succeed as a no-op.
    Its commit date is its age."""
    empty = git("hash-object", "-t", "tree", "-w", os.devnull).strip()
    landing = f", PR #{pr}" if pr is not None else ""
    return git(
        "commit-tree",
        *(["-p", parent] if parent else []),
        "-m",
        f"{title} [skip ci]\n\npid {os.getpid()}{landing}, nonce {os.urandom(8).hex()}",
        empty,
    ).strip()


def leased(base: str, ours: str, tip: str | None, **kw: Any) -> subprocess.CompletedProcess[str]:
    """Push `ours`, a child of `tip` (None: the branch is missing), to the base's lock branch, leased on `tip`, so of
    two lands pushing from one tip one wins and nothing is ever rewritten. --no-verify, since a lock commit holds the
    empty tree and a project's pre-push checks have nothing of it to check."""
    ref = LOCK.format(base)
    return subprocess.run(
        [
            "git",
            "push",
            "-q",
            "--no-verify",
            f"--force-with-lease={ref}:{tip or ''}",
            "origin",
            f"{ours}:{ref}",
        ],
        capture_output=True,
        text=True,
        check=False,
        **kw,
    )


def unlock(base: str, ours: str) -> subprocess.CompletedProcess[str]:
    """Release the landing lock: push a FREE child of `ours`, leased on it, so a lock broken as stale and taken by
    another land meanwhile stays theirs. In a session of its own (landing says why)."""
    return leased(base, lock_commit(FREE, ours), ours, start_new_session=True)


def locked(base: str, held: list[str], pr: int | None = None) -> bool:
    """Take the base's landing lock, naming `pr`: push a HELD child of its FREE tip (the first lock commit, with no
    parent, where the branch is missing), leased on that tip. A HELD tip is another land's; one older than CEILING by
    its commit date is stale, and one naming a PR already merged into the base is released (released): either is
    broken and taken by the same push of a HELD child. Each commit is put in `held` before its push, so a stop
    as it reaches origin still releases it. False, after saying who holds it since when, while another land holds it
    or LEGACY, the previous version's lock, is on origin and no older than CEILING."""
    ref, name = LOCK.format(base), lock_name(base)
    tip, refused = (
        "",
        "",
    )  # "": not read yet; a refusal of a push from the tip read again is origin's, not a race's
    for _ in range(3):
        listed = {
            line.split("\t")[1] for line in git("ls-remote", "origin", LEGACY, ref).splitlines()
        }
        if LEGACY in listed:
            try:
                git("fetch", "-q", "origin", f"+{LEGACY}:{LEGACY}")
            except subprocess.CalledProcessError as exc:
                if git(
                    "ls-remote", "origin", LEGACY
                ).strip():  # still there: the fetch itself failed
                    raise Refused(
                        f"could not read the previous version's landing lock {LEGACY}: {' '.join(str(exc.stderr).split())}"
                    ) from exc
                continue  # released since the listing: read origin again
            age = int(time.time()) - int(git("log", "-1", "--format=%ct", LEGACY).strip())
            if age <= CEILING:
                print(
                    f"a land of the previous version holds the landing lock {LEGACY}: land --wait waits for it"
                )
                return False
            # stale, left by a land that died: passed over, never written, as the previous version would break it
        before, tip = tip, None
        if ref in listed:
            git("fetch", "-q", "origin", f"+{ref}:refs/remotes/origin/{name}")
            tip = git("rev-parse", f"refs/remotes/origin/{name}").strip()
        if refused and tip == before:
            raise Refused(f"origin refused the landing lock {name}: {refused}")
        if tip:
            stamp, title, holder = git("log", "-1", "--format=%ct%x00%s%x00%b", tip).split("\0")
            if title.startswith(HELD):
                taken = int(stamp)
                age = int(time.time()) - taken
                holder = holder.strip().split(", nonce ")[0]
                if age <= CEILING and (done := released(base, holder)):
                    print(f"the landing lock {name} ({holder}) is released: {done}: broken")
                elif age <= CEILING:
                    print(
                        f"another land holds the landing lock {name} ({holder}), taken {age // 60} minutes ago"
                        f" ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(taken))}): land --wait waits for it"
                    )
                    return False
                else:
                    print(
                        f"the landing lock {name} is {age // 3600} hours old, past {CEILING // 3600} hours: broken as"
                        " stale"
                    )
        held.append(lock_commit(HELD, tip, pr))
        pushed = leased(base, held[-1], tip)
        if not pushed.returncode:
            return True
        refused = " ".join(pushed.stderr.split())
    print(
        f"other lands kept taking the landing lock {name} as this one tried to: land --wait waits for it"
    )
    return False


def released(base: str, holder: str) -> str | None:
    """Why a HELD lock whose body is `holder` is released though never freed: the PR it names (the last its land
    merges) is merged and origin's base holds its merge commit, so its land's work is done; None for a lock naming no
    PR (written before #901, waited on until CEILING), an open one, a merge the base lacks, or a PR GitHub can't read
    now (waited on, so a GitHub outage breaks no live land's lock)."""
    if (named := re.search(r"\bPR #(\d+)\b", holder)) is None:
        return None
    number = int(named[1])
    try:
        pull = merged_pull(number)
    except subprocess.CalledProcessError:
        return None
    if pull is None or not (sha := pull.get("merge_commit_sha")):
        return None
    subprocess.run(
        ["git", "fetch", "-q", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}"],
        capture_output=True,
        check=False,
    )
    contained = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, f"refs/remotes/origin/{base}"],
        capture_output=True,
        check=False,
    )
    return f"PR #{number} merged into {base} as {sha}" if contained.returncode == 0 else None


def repointed(base: str, held: list[str], pr: int) -> None:
    """Before the batch's merges, move the lock to a HELD child of ours naming `pr`, the last PR it merges, leased on
    ours: a lock naming an earlier PR would read as released once that one merged, with the rest still to merge. A
    refused push means another land took the lock meanwhile (it read our PR as merged, merged by hand, or our lock as
    stale), so nothing is merged and theirs is left alone: our commits are dropped from `held`, which nothing then
    releases."""
    ours = held[-1]
    held.append(lock_commit(HELD, ours, pr))
    pushed = leased(base, held[-1], ours)
    if pushed.returncode:
        held.clear()
        raise Refused(
            f"another land took the landing lock {lock_name(base)} before this one's merges, so nothing was merged:"
            f" {' '.join(pushed.stderr.split())}"
        )


def proof_gaps(
    pull: dict[str, Any], tracker: str | None, loop: str | None
) -> tuple[list[str], Any]:
    """What keeps the PR from landing before CI is asked about, as lines to print (none: it holds every proof, and a
    draft may be marked ready, since ready starts CI), with the issues its spec links."""
    where, local = f"PR #{pull['number']}", signed(loop)
    if pull["isCrossRepository"]:
        return [
            f"{where} comes from another repository: land merges only branches of this one"
        ], None
    if why := outside(pull, loop):
        # land is the loop's merge: a PR no verifier saw merges its author's way
        return [why], None
    found, issues = gated("merge", pull, tracker, loop)
    if found:
        return holds(pull, issues, loop) + found, issues
    if (proof := head_proof(loop)) and not proved(pull["headRefOid"], proof["status"]):
        names = f", with the tier set in {', '.join(proof['env'])}" if proof["env"] else ""
        gone = (
            f"{where}: its head {pull['headRefOid']} has no green `{proof['status']}` status for its tree (loop.md"
            f" `head_proof`): run `approvals.py local-ci --record --head-proof` on a clean checkout of it{names}"
        )
        return [gone], issues
    if local and (why := unsignable(pull, *local)):
        return [why], issues
    return [], issues


def mark_ready(pull: dict[str, Any], required: set[str]) -> tuple[int, bool] | None:
    """Mark a draft ready (a write: `land`'s own path only, never on a PR `landable` refused, since ready starts CI).
    None when its required checks (if any) need no wait; else the exit its start of CI means."""
    where = f"PR #{pull['number']}"
    # CI skips a draft, and a skipped check counts as green: a draft's checks say nothing about the ready PR
    gh("pr", "ready", str(pull["number"]))
    print(f"{where} is ready now")
    if required:
        print(f"{where}: CI starts on ready, so its required checks are pending")
        return WAITING, True
    return None


class Verdict(NamedTuple):
    """What `landable` found. `exit`: None when the PR may land, else the exit it means for a named PR and whether a wait
    would clear it. `draft`: a draft that holds every proof, ready to mark (a write for `land`'s own path). `issues`: the
    issues its spec links, None while a proof is missing, so `land` flags a PR's risk only once its proofs hold."""

    exit: tuple[int, bool] | None
    draft: bool = False
    issues: list[dict[str, Any]] | None = None


def readied(
    named: list[dict[str, Any]],
    base: str,
    tracker: str | None,
    loop: str | None,
) -> list[dict[str, Any]]:
    """The named PRs, each draft `landable` finds ready to mark flagged and marked ready (and read again) before the
    wait for the lock, so the holder's next batch includes it. A draft it refuses is returned with its verdict in
    `verdict`, which `batched` reuses instead of asking again; a readied one with `readied`, and `waiting` for what its
    start of CI means for this pass."""
    drafts = [pull for pull in named if pull["isDraft"]]
    if not drafts:
        return named
    required = required_checks(base) - {APPROVALS}
    found: dict[int, dict[str, Any]] = {}
    for pull in drafts:
        verdict = landable(pull, tracker, loop, required, named=True)
        if not verdict.draft:
            found[pull["number"]] = {**pull, "verdict": verdict}
            continue
        for line in flag(pull, verdict.issues or [], loop):
            print(line)
        waiting = mark_ready(pull, required)
        found[pull["number"]] = {
            **pull_request(pull["number"]),
            "readied": True,
            "waiting": waiting,
        }
    return [found.get(pull["number"], pull) for pull in named]


def landable(
    pull: dict[str, Any],
    tracker: str | None,
    loop: str | None,
    required: set[str],
    named: bool = False,
) -> Verdict:
    """A check, which writes nothing to GitHub: whether the PR is a candidate for the batch (every merge proof, gated,
    the head's own CI or local-ci pass aside, since the batch's gate is the proof; no owner wait; the base's required
    checks green on its head; a signed squash possible where loop.md asks for one), or a draft that holds all that and is
    ready to mark, or why not, said once on stdout. The PR is judged as `flag` leaves it (a `risk:high` the gate added
    that `unflag` would take off no longer holds it); `land` writes the label and the ready mark itself. The `named` PR
    missing a required check, or a draft, that GitHub reports conflicting ends the wait, since no workflow runs on it."""
    where = f"PR #{pull['number']}"
    lines, issues = proof_gaps(pull, tracker, loop)
    if lines:
        for line in lines:
            print(line)
        return Verdict((1, False))
    pull = flagged_as(pull, issues, loop)
    # GitHub runs no workflow on a conflicting PR, so a required check it lacks never comes, nor do a draft's once
    # it is ready: before the draft is marked ready, since that would start nothing
    if (
        named
        and required
        and pull.get("mergeable") == "CONFLICTING"
        and (pull["isDraft"] or required - {name for name, _ in head_checks(pull, required)[0]})
    ):
        for line in ci(where, pull, required):
            print(line)
        base = pull["baseRefName"]
        print(f"{where} conflicts with {base}: merge `origin/{base}` in")
        return Verdict((1, False), issues=issues)
    if pull["isDraft"]:
        if owner := owner_waits(pull, issues, loop):  # ready starts CI, so never before the go
            for line in owner:
                print(line)
            return Verdict((WAITING, False), issues=issues)
        # GitHub marks a draft ready only over GraphQL, which a cloud session's proxy refuses
        if in_cloud():
            print(
                f"{where} is a draft, and a cloud session can't mark it ready: mark it ready on GitHub"
            )
            return Verdict((1, False), issues=issues)
        return Verdict(None, draft=True, issues=issues)
    if pull.get("waiting"):  # readied by this land: its CI has only just started
        return Verdict(pull["waiting"], issues=issues)
    if required and (lines := ci(where, pull, required)):
        for line in lines:
            print(line)
        red = {state for _, state in head_checks(pull, required)[0]} & RED
        wait = (1, False) if red or any(line.endswith(PAGED) for line in lines) else (WAITING, True)
        return Verdict(wait, issues=issues)
    # after CI, so the owner is never asked about a head CI could still reject
    if owner := owner_waits(pull, issues, loop):
        for line in owner:
            print(line)
        return Verdict((WAITING, False), issues=issues)  # the owner is asked, not polled
    if risk(pull, issues, loop):
        for line in whose(pull, loop):
            print(line)
    return Verdict(None, issues=issues)


def batched(
    named: list[dict[str, Any]],
    base: str,
    tracker: str | None,
    loop: str | None,
    only: bool = False,
    held: list[str] | None = None,
    worst: int = 0,
) -> tuple[int, bool]:
    """Under the lock (`held`, its commits): merge every candidate's head onto `base` locally, oldest PR first, gate
    the result's tree once (or reuse a pass on it), move the lock to name the last PR to land (repointed), and merge each
    through GitHub in that order; a red batch lands one PR at a time."""
    # `loop:approvals` is check merge's own status, on the proofs land reads itself
    required = required_checks(base) - {APPROVALS}
    waits: dict[int, tuple[int, bool]] = {}
    candidates = []
    listed = {
        other["number"]
        for other in (
            [] if only else open_pulls()
        )  # `only`: no other PR is read, let alone touched
        if other["baseRefName"] == base and not other["isDraft"]
    } | {pull["number"] for pull in named}
    pulls = {pull["number"]: pull for pull in named}
    for number in sorted(listed):
        pull = pulls.get(number) or pull_request(number)
        verdict = pull.get("verdict") or landable(pull, tracker, loop, required, number in pulls)
        # the board shows why a PR waits: flag its risk once its proofs hold, before it is refused for anything else
        if verdict.issues is not None and not pull.get("readied"):
            for line in flag(pull, verdict.issues, loop):
                print(line)
        if verdict.exit is None:
            candidates.append(pull)
        else:
            waits[number] = verdict.exit
    failed: set[int] = set()
    # each PR to land, the tree it lands, the tree gated with it, and how that passed
    landed: list[tuple[dict[str, Any], str, str, str]] = []
    if candidates:
        with batch_tree(base) as work:
            tip = run_in(work, "rev-parse", "HEAD")
            candidates = [pull for pull in candidates if pre_landed(pull, base, work, loop, failed)]
            landed = merge_batch(candidates, base, work, failed)
            if landed and held:
                repointed(base, held, landed[-1][0]["number"])
            if landed:
                merges(landed, base, tip, work, loop, failed)
    if named:
        # each named PR's exit: its wait's, else 0 when it merged, else 1; the worst of them, 1 over 3 over 0
        done = {pull["number"] for pull, *_ in landed} - failed
        exits = [
            waits[p["number"]] if p["number"] in waits else (0 if p["number"] in done else 1, False)
            for p in named
        ]
        code = max((c for c, _ in exits), key=lambda c: {1: 2, WAITING: 1}.get(c, 0), default=0)
        code = 1 if worst else code
        return code, code == WAITING and any(again for c, again in exits if c == WAITING)
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
        # a one-PR batch's red run was this PR merged onto the same tip, the same tree: that is its first run alone
        tree, how = (tree, "") if len(merged) == 1 else gate_batch(work, [pull])
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
    leaves the PR out of this batch with its output's end printed on every land and said once per head on the PR; it
    isn't red, so it stays ready."""
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
    # its output's end on every land, not only in the comment, which is once per head: a land again on the same head
    # would otherwise say only the exit code
    print(
        f"{where}: `{command}` refused it against {base} at {tip}, exiting {ran.returncode}: left out of this batch"
        + "".join(f"\n  {line}" for line in ran.stdout.rstrip("\n").splitlines()[-LOG_TAIL:])
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
    """The tree checked out in `work` and how it passed the gate (`run` or `reused`), empty when red. Each gate step
    (gate_plan) that passed on the tree before, on any commit with it (a PR's head or the batch's), is reused (run_steps,
    step_pass), which says where; never on GitHub's required checks alone, since the pass is published as the gate
    command's. The others run there, under the host gate slot, each pass recorded by tree, so a tree equal to a head's
    whose every step passed runs nothing. A `host` step with no pass in a cloud session is refused, naming it, since
    the batch can't pass here and no PR is at fault. `pulls` is unused: a pass is found by tree. Its log stays beside
    the worktree."""
    commit, tree = run_in(work, "rev-parse", "HEAD"), run_in(work, "rev-parse", "HEAD^{tree}")
    command = gate()[0]
    log, fault = work.parent / f"{tree}.log", settings(project()[1]).get("machine_exit")
    for again in (False, True):
        with log.open("w") as out:
            done = run_steps(
                commit,
                tree,
                lambda: (
                    head_moved(
                        commit,
                        tree,
                        run_in(work, "rev-parse", "HEAD"),
                        run_in(work, "rev-parse", "HEAD^{tree}"),
                    )
                    or run_in(work, "status", "--porcelain", "--untracked-files=all")
                ),
                work,
                out,
            )
        code = done["code"]
        if done["left"]:
            raise Refused(
                f"Tree {tree}: {', '.join(f'`{name}`' for name in done['left'])} has no pass on it and runs only on"
                " a host (`where: host`): land on a host, or pass it there on a head with this tree"
            )
        if not done["ran"]:
            found = done["records"]
            pushed = f" from {found[0]['ref']}" if len(found) == 1 and found[0].get("ref") else ""
            print(f"Tree {tree}: `{command}` passed on it before, reused{pushed}")
            return tree, "reused"
        if done["step"] is None or code != fault:
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
    if not code and done["changed"]:
        with log.open("a") as out:
            out.write(
                f"\nthe gate changed the tree, so it did not run on the batch as merged:\n{done['changed']}\n"
            )
        code = 1
    print(f"Tree {tree}: `{command}` exited {code} (log {public(str(log))})")
    if code:
        return tree, ""
    return tree, "run"


def landed_pass(tip: str, tree: str) -> dict[str, Any]:
    """The pass `land` publishes on the base's new tip `tip`, whose tree `tree` was gated: each step's record on the
    tree (gate_plan), run on the tip, with the seconds its pass took where this clone or origin holds them, so the
    record branch pushed again for the tree keeps them."""
    plan, steps = gate_plan(), []
    for step in plan:
        found = step_pass(tip, tree, step, show=False) or {}
        steps.append(
            {"head": tip, "tree": tree, "command": step["command"], "env": step["sets"]}
            | {key: found[key] for key in TIMED if isinstance(found.get(key), int)}
            | {key: found[key] for key in LOADED if found.get(key) is not None}
            | step_field(step)
            | inputs_field(tree, step)
        )
    if plan[0]["legacy"]:
        return steps[0]
    return {"head": tip, "tree": tree, "command": gate()[0], "env": gate()[2], "steps": steps}


def evict(pull: dict[str, Any], base: str, green: str, log: Path) -> None:
    """Take a PR red alone, twice, out of the batch: back to draft, so the next land leaves it out until `land <pr>`
    marks it ready again, and a comment holding its gate log's last LOG_TAIL lines."""
    where, head, number = f"PR #{pull['number']}", pull["headRefOid"], pull["number"]
    print(f"{where} is red alone on {base} at {green}, twice: evicted")
    try:
        tail = log.read_text(errors="replace").splitlines()[-LOG_TAIL:]
    except OSError:
        tail = []
    # GitHub turns a PR back to draft only over GraphQL, which a cloud session's proxy refuses
    if in_cloud():
        print(
            f"{where} stays ready, since a cloud session can't make it a draft: make it one on GitHub"
        )
    else:
        gh("pr", "ready", "--undo", str(number))
    comment(
        number,
        f"{EVICTED}\nHead: {head}\n\n`{gate()[0]}` failed twice on it merged alone onto {base} at {green}: fix it,"
        f" then `land {number}` marks it ready again.\n\n<details><summary>The gate's last lines</summary>\n\n````\n"
        + "\n".join(tail)
        + "\n````\n</details>\n",
    )


# a cloud session's link, which its harness adds to every commit message; land drops it from the squash body
SESSION_LINE = re.compile(r"^Claude-Session:.*(?:\n|$)", re.MULTILINE)
CO_AUTHOR = re.compile(r"^Co-authored-by:[ \t]*(.*?)[ \t]*$", re.MULTILINE | re.IGNORECASE)


def squash_body(commits: list[dict[str, Any]], author: str | None) -> str:
    """The body GitHub's squash writes under the repo's commit-messages default, from the PR's commits as REST lists
    them (oldest first) and the PR author's login, as 250 squashes on this repo's main show it. Its co-authors are, in
    commit order, each commit's author other than the PR's (a merge commit's too), then each `Co-authored-by:` its
    message names, one per email, the first seen keeping its name. The commits less merge commits: one is its message
    after the subject with those trailer lines emptied, then the co-authors; several are each whole message as a `* `
    item, then `---------` and the co-authors."""
    named: dict[str, str] = {}
    for commit in commits:
        if (commit.get("author") or {}).get("login") != author:
            who = commit["commit"]["author"]
            named.setdefault(who["email"].casefold(), f"{who['name']} <{who['email']}>")
        for line in CO_AUTHOR.findall(commit["commit"]["message"]):
            email = re.search(r"<([^>]*)>", line)
            named.setdefault((email[1] if email else line).casefold(), line)
    footer = "\n".join(f"Co-authored-by: {who}" for who in named.values())
    messages = [commit["commit"]["message"] for commit in commits if len(commit["parents"]) < 2]
    if len(messages) == 1:
        text = CO_AUTHOR.sub("", messages[0].partition("\n")[2]).strip()
        return "\n\n".join(part for part in (text, footer) if part)
    items = "\n\n".join(f"* {message}" for message in messages)
    return f"{items}\n\n---------\n\n{footer}" if footer else items


def unlinked(text: str) -> str:
    """text less every `Claude-Session:` line, the blank lines around each removed one folded into one (none when
    it sat between two text lines); blank lines elsewhere (a PR body's code block) stay as written."""
    marked = "\n".join("\0" if SESSION_LINE.match(line) else line for line in text.split("\n"))

    def fold(run: re.Match[str]) -> str:  # each removed line held one of the run's line breaks
        return "\n\n" if run[0].count("\n") - run[0].count("\0") >= 2 else "\n"

    return re.sub(r"\n*(?:\0(?:\n|$))+\n*", fold, marked).strip()


def commit_msg(message: Path) -> int:
    """The commit-msg hook: the message file less every `Claude-Session:` line, as unlinked() folds them for land, so a
    cloud session's branch commits carry no link either, since a public repo publishes them; a message with none is
    left as written."""
    text = message.read_text()
    if SESSION_LINE.search(text):
        message.write_text(unlinked(text) + "\n")
    return 0


def land_body(pull: dict[str, Any]) -> str | None:
    """The `--body` land passes to GitHub's squash of pull, whatever the repo's squash default would put a
    `Claude-Session:` line in, or None to leave GitHub's default. The repo's `squash_merge_commit_message` picks it:
    COMMIT_MESSAGES, squash_body() less those lines; PR_BODY, the PR's body less them; BLANK, None, since GitHub
    writes no body. ponytail: under PR_BODY GitHub's own co-author lines, if it adds any, are not added here, as no
    squash on this repo shows that setting."""
    setting = json.loads(gh("api", "repos/{owner}/{repo}"))["squash_merge_commit_message"]
    if setting == "BLANK":
        return None
    if setting == "PR_BODY":
        text = pull.get("body") or ""
    else:
        number = pull["number"]
        commits = [
            json.loads(line)
            for line in gh(
                "api",
                "--paginate",
                f"repos/{{owner}}/{{repo}}/pulls/{number}/commits?per_page=100",
                "--jq",
                ".[]",
            ).splitlines()
        ]
        # ponytail: REST lists a PR's first 250 commits
        text = squash_body(commits, (pull.get("author") or {}).get("login"))
    # GitHub writes no body for this PR either, so there is nothing to override
    if not text.strip():
        return None
    # ponytail: a body that was only `Claude-Session:` lines goes as an empty `--body`; whether GitHub then writes
    # its default instead is unproven
    return unlinked(text)


def merged_anyway(number: int, head: str, exc: subprocess.CalledProcessError) -> str:
    """The merge commit of PR #number when `gh pr merge` failed with exc but GitHub merged it at head all the same,
    since a transport error (a response cut off mid-stream) can come after the merge. Anything else is Refused with
    exc's error, and with the re-read's as well when re-reading the PR failed too."""
    why = " ".join(str(exc.stderr or exc).split())
    try:
        found = merged_pull(number)
    except (subprocess.CalledProcessError, ValueError) as again:
        reread = " ".join(str(getattr(again, "stderr", None) or again).split())
        raise Refused(f"{why}; re-reading the PR failed too: {reread}") from exc
    if found is None or (found.get("head") or {}).get("sha") != head:
        raise Refused(why) from exc
    return str(found.get("merge_commit_sha"))


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
                body = land_body(pull)
                try:
                    gh(
                        "pr",
                        "merge",
                        str(pull["number"]),
                        "--squash",
                        *(("--body", body) if body is not None else ()),
                        "--match-head-commit",
                        head,
                    )
                except subprocess.CalledProcessError as exc:
                    merge = merged_anyway(pull["number"], head, exc)
                    print(
                        f"{where}: the merge call failed, but the PR is merged at {head} as {merge}"
                    )
                else:
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
        publish(tip, landed_pass(tip, actual))
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
                publish(tip, landed_pass(tip, actual))
        except MachineFault as exc:  # the PRs landed: each still gets its comment
            print(exc)
    # after every publication above, which pushes the landed tree's record again when it is the heads' tree
    drop_records([pull["headRefOid"] for pull, *_ in done])
    numbers = ", ".join(f"#{pull['number']}" for pull, *_ in done)
    for pull, tree, gated, how in done:
        comment(
            pull["number"],
            f"Landed\nBase: {tip}\nTree: {tree}\nGate: {command}, {how} on {gated}\nBatch: {numbers}\n",
        )
        archive_workers(pull["number"])


def archive_workers(number: int) -> None:
    """Start, detached, the finish of the kept `--pr` worker sessions of PR #number, which merged:
    orchestrating-agents' `omnigent_agent.py reap --merged --pr <n>`. It is not waited on, so a slow Omnigent or
    GitHub never holds the land, and its outcome goes to its own log, named in the line printed. A checkout without
    that skill, or a start that fails, is a printed line only: the PR has landed, and a session left open is the
    next `reap`'s."""
    script = Path(__file__).resolve().parents[2] / "orchestrating-agents/scripts/omnigent_agent.py"
    if not script.is_file():
        print(f"PR #{number}: no worker sessions finished: {script.name} is not installed")
        return
    try:
        with tempfile.NamedTemporaryFile(
            "w", prefix=f"reap-pr{number}-", suffix=".log", delete=False
        ) as log:
            subprocess.Popen(
                [sys.executable, str(script), "reap", "--merged", "--pr", str(number)],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as exc:
        print(f"PR #{number}: worker sessions not finished: {exc}")
        return
    print(f"PR #{number}: finishing its worker sessions in the background, log {log.name}")


def approve(point: str, number: int, seen: str | None = None) -> int:
    """Record the owner's approval of the issue's current spec or plan, on their word: the record, the label, and
    `needs-owner` removed. Every earlier record of the point is superseded and minimized. With `seen`, the version
    the owner's label was checked against (adopted), an edit since is refused: the label never covered it."""
    issue = issue_node(number)
    holder = spec_holder(issue) if point == "spec" else headed(issue, "## Plan")
    if holder is None:
        raise Refused(f"#{number} has no `## Plan` comment to approve")
    value = texted(holder)
    if seen is not None and value != seen:
        raise Refused(
            f"#{number}: the {point} was edited after the owner's `approved:{point}`: the owner adds it again"
        )
    record = f"{point.capitalize()}: {value}\n"
    earlier = [
        (note, found) for note in notes(issue) if (found := parsed(note["body"], point)) is not None
    ]
    if any(
        found.get("by") == "owner" and found.get(point) not in versions(holder)
        for _, found in earlier
    ):
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
    label, then the record that names it the delegate's. Into the default branch, where a label is no go, it is
    refused: there the go is pinned to a head (go). So is a PR touching a path `risk.merge_paths` names, whose merge
    only the owner's go on the head allows (owners_only)."""
    pull = pull_request(number)
    if sole := owners_only(pull, project()[1]):
        raise Refused(
            f"PR #{number}: `{MERGE_LABEL}` is no go here, since {sole}: it waits for the owner's go on its head"
        )
    if default(pull):
        raise Refused(
            f"PR #{number} targets {pull['baseRefName']}, the default branch, where a label is no go: the head-pinned"
            f" `approve merge {number} --head <sha> --by delegate` gives the delegate's go there with `loop.delegate:"
            " all`, and the owner's go always covers it"
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
    `VERDICT:`, `SATISFIED:`, `Risk:` and any `Logic change:` lines, and the qualifier its `Verifier:` line has after the pass number ('' for
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
    # a run not made can't back a satisfied verdict: that ends in a question for the lead's proof run
    if satisfied[-1].lower().split()[1:2] == ["yes"] and any(
        re.match(r"Not run:", line) for line in lines
    ):
        raise Refused(
            f"{report}: `{satisfied[-1]}` lists a `Not run:` line, so a run it relies on was never made: "
            "end the turn in `<report>.question` (verifier.md, A run the sandbox refuses)"
        )
    # an unsatisfied pass with nothing found spends a pass on a run the verifier couldn't make: that ends in a question
    if (
        not any(tally)
        and satisfied[-1].lower().split()[1:2] != ["yes"]
        and not any(re.match(r"Not run:.*\bowner action:\s*\S", line) for line in lines)
    ):
        raise Refused(
            f"{report}: `{satisfied[-1]}` with no finding spends a pass on a run the sandbox refused: "
            "end the turn in `<report>.question` (verifier.md, A run the sandbox refuses), or name what "
            "was not run on a `Not run: <step>, owner action: <what>` line"
        )
    family, number, qualifier = passes[-1].groups()
    logic = [line for line in lines if line.startswith(f"{LOGIC}:")]
    closing = [verdicts[-1], satisfied[-1], judgments[-1], *logic[-1:]]
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
    return subprocess.run(
        ["git", *SIGNING, *args], check=True, capture_output=True, text=True
    ).stdout


LOCAL_CI = ["mise", "run", "check:all"]
# a status description's limit on GitHub, which holds the tree, the commit and the gate command (described)
DESCRIBED = 140


def gate(passed: list[str] | tuple[str, ...] = ()) -> tuple[str, list[str], dict[str, str]]:
    """loop.md's `gate` under `loop` (default LOCAL_CI): the command as written, its words, and the variables it sets
    in front of them (`GATE_UI_TESTS=0 mise run check:all`). The command alone is the gate: it runs with every name
    `local_ci_env` lists cleared but those it sets, so no host's ambient env changes what it ran. With `passed`, a
    head proof's names (head_proof), each one this process's environment sets is set to that value, over the
    command's own assignment of it, and the command returned names it, so its record and status say so. With
    `gate_steps` (gate_plan), the gate as people read it: `<name>: <command>` for each step, joined by `; `, no words
    (each step runs its own), and the variables every step sets."""
    loop = settings(project()[1])
    if not loop.get("gate_steps"):
        return command_line(loop.get("gate") or shlex.join(LOCAL_CI), "gate", passed)
    plan = gate_plan(passed)
    return (
        "; ".join(f"{step['name']}: {step['command']}" for step in plan),
        [],
        {name: value for step in plan for name, value in step["sets"].items()},
    )


# the name the one step of a gate without `gate_steps` is shown by; it is that gate by its `legacy` flag, never by this
# name, which a project's `gate_steps` may give a step too
WHOLE = "gate"


def gate_plan(passed: list[str] | tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """The gate's steps, in order, each `name`, `command` (as gate() reads one, with `passed`), `words`, `sets` and
    `where` (`any`, or `host`: never run in a cloud session): the base's policy's `gate_steps` (project(), so a PR's own
    edit of its gate is not the one it is gated by), else the one `gate` command as
    the step WHOLE, `any`, flagged `legacy`, which records, publishes and prints as the one gate always did (a plan
    from `gate_steps` is stepped whatever its names or length: its steps are not `legacy`). Each step's pass is recorded and reused by itself, keyed by its tree and command (recorded),
    so a step that passed on a tree anywhere is not run again; a project without `gate_steps` keeps one record. A
    policy setting both is refused, since two sources of the gate would drift."""
    loop = settings(project()[1])
    written = loop.get("gate_steps")
    if not written:
        command, words, sets = gate(passed)
        return [
            {
                "name": WHOLE,
                "command": command,
                "words": words,
                "sets": sets,
                "where": "any",
                "legacy": True,
                "paths": None,
                "setting": None,
            }
        ]
    if loop.get("gate"):
        raise Refused(
            f"{source(project()[1])} sets both `gate` and `gate_steps`: keep `gate_steps`, the gate's steps, and"
            " drop `gate`"
        )
    plan = []
    for step in written:
        command, words, sets = command_line(step["command"], f"gate_steps.{step['name']}", passed)
        plan.append(
            {
                "name": step["name"],
                "command": command,
                "words": words,
                "sets": sets,
                "where": step["where"],
                "legacy": False,
                "paths": step.get("paths"),
                "setting": written,
            }
        )
    return plan


def inputs_key(tree: str, step: dict[str, Any]) -> str | None:
    """A gate step's inputs key on `tree` (#963): a digest of the `gate_steps` setting as read (which holds every
    step's command and `paths`) and the mode, object id and path of each file under the step's `paths` in `tree` (globs
    matched on the full path, case and all, so every host reads the same files), or None, which keys the step on the
    whole tree as #940 did: a step without `paths`, an empty one, one matching no file in `tree`, or a tree git can't
    list. A pass is found by its command (the record's name, recorded) and this key, so any tree with the same key
    reuses it: a change outside the step's paths runs nothing again, while a change to the setting, the command a
    head proof runs (gate) or a file the step reads gives another."""
    globs = step.get("paths")
    if not globs:
        return None
    try:
        listed = git("ls-tree", "-r", "-z", "--full-tree", tree)
    except (subprocess.CalledProcessError, OSError):
        return None
    read = [
        entry
        for entry in listed.split("\0")
        if "\t" in entry
        and any(fnmatch.fnmatchcase(entry.split("\t", 1)[1], glob) for glob in globs)
    ]
    if not read:
        return None
    digest = hashlib.sha256()
    for part in (json.dumps(step["setting"], sort_keys=True), *sorted(read)):
        digest.update(part.encode() + b"\0")
    return digest.hexdigest()


def here(step: dict[str, Any]) -> bool:
    """Whether `step` may run here: a `host` step never runs in a cloud session (in_cloud)."""
    return step["where"] != "host" or not in_cloud()


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
    """Run each step of the gate that may run here (gate_plan, here), in order, to the first that fails, and return
    that step's exit, else 0; nothing is recorded (a checkout with changes)."""
    for step in gate_plan(passed):
        if here(step) and (code := ran_step(step, cwd, out)[0]):
            return code
    return 0


def ran_step(
    step: dict[str, Any],
    cwd: Path | None = None,
    out: Any = None,
    load: dict[str, Any] | None = None,
) -> tuple[int, int, int]:
    """Run one gate step (gate_plan) in its environment (gate_env) under the host gate slot (heavy_slot), in `cwd`
    with its output to `out` when given: its exit, the seconds it ran and the seconds it waited for the slot; `load`,
    when given, gets the host's load at the step's start, once it holds the slot (host_load). A command that isn't
    there is refused, naming the gate, since loop.md is hand-written."""
    where = {"cwd": cwd, "stdout": out, "stderr": subprocess.STDOUT} if cwd else {}
    with heavy_slot(step["name"], out) as (slot, waited):
        if load is not None:
            load.update(host_load())
        began = time.monotonic()
        try:
            code = subprocess.run(
                step["words"], check=False, env=gate_env(step) | {SLOT_HELD: slot}, **where
            ).returncode
        except OSError as exc:
            what = "gate" if step["legacy"] else f"gate step `{step['name']}`"
            raise Refused(f"loop.md's {what} {step['command']!r} can't run: {exc}") from None
        return code, round(time.monotonic() - began), waited


def host_load() -> dict[str, Any]:
    """The host's 1-minute load average and the swap it uses, in whole MiB, each None where the host doesn't say, so a
    step's seconds can be read beside the load it ran under (#963)."""
    try:
        load: float | None = round(os.getloadavg()[0], 2)
    except OSError:
        load = None
    return {"load_1m": load, "swap_used_mb": swap_used_mb()}


MEMINFO = "/proc/meminfo"


def swap_used_mb() -> int | None:
    """Swap in use, in whole MiB: Linux's /proc/meminfo, else macOS's `sysctl vm.swapusage`; None for neither."""
    with contextlib.suppress(OSError, KeyError, ValueError, IndexError):
        with open(MEMINFO) as info:
            kib = {
                name: int(rest.split()[0])
                for name, _, rest in (line.partition(":") for line in info)
                if name in ("SwapTotal", "SwapFree")
            }
        return (kib["SwapTotal"] - kib["SwapFree"]) // 1024
    with contextlib.suppress(OSError, subprocess.SubprocessError, ValueError):
        said = subprocess.run(
            ["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=False
        ).stdout
        if used := re.search(r"used = ([\d.]+)M", said):
            return int(float(used[1]))
    return None


def gate_env(step: dict[str, Any]) -> dict[str, str]:
    """The environment a gate step runs in: this process's, without the names `local_ci_env` lists unless the step's
    command sets them, or a head proof's `passed` takes them from this process's (gate)."""
    cleared = set(local_ci_env())
    return {name: value for name, value in os.environ.items() if name not in cleared} | step["sets"]


# the variable naming the host gate slot a run holds, so a gate wrapper under it takes no lock of its own (SKILL.md, One
# heavy gate per host slot; mutate.py sets it the same way)
SLOT_HELD = "LOOP_GATE_SLOT_HELD"


def slot_path() -> str:
    """The host gate slot's lock file, the one SKILL.md, mutate.py and the project's gate wrapper name."""
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME", "~"), ".cache")
    return os.path.join(cache, "engineering-loop", "gate.1.lock")


@contextlib.contextmanager
def heavy_slot(name: str, out: Any = None) -> Any:
    """Hold the host gate slot, an exclusive flock on slot_path(), for one gate step: (its path, the whole seconds
    waited for it). A run already under a holder of that path (SLOT_HELD) takes none and waits 0, since it would wait
    on its own parent. A wait is said once, as `local-ci: <step>: waiting for the host gate slot`."""
    path, began = slot_path(), time.monotonic()
    if os.environ.get(SLOT_HELD) == path:
        yield path, 0
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                f"local-ci: {name}: waiting for the host gate slot",
                file=out or sys.stderr,
                flush=True,
            )
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield path, round(time.monotonic() - began)
    finally:
        os.close(fd)


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


# how long tree_of waits for one commit's fetch, so a check never hangs on the network
TREE_FETCH_SECONDS = 60
# each (checkout, commit) tree_of already asked origin for in this run, so a missing one costs one fetch, not one per call
TREE_FETCHED: set[tuple[str, str]] = set()


def tree_of(commit: str) -> str | None:
    """The tree `commit` holds, else None. A commit the clone lacks is fetched from `origin` by itself (GitHub serves
    any commit reachable from a branch or a PR), once per run and within TREE_FETCH_SECONDS, since a bare fetch brings
    every branch and may wait on the network for ever; a failed or timed-out fetch is None."""
    with contextlib.suppress(subprocess.CalledProcessError):
        return git("rev-parse", f"{commit}^{{tree}}").strip()
    asked = (os.getcwd(), commit)
    if asked in TREE_FETCHED:
        return None
    TREE_FETCHED.add(asked)
    fetch = ["git", *SIGNING, "fetch", "--quiet", "--no-tags", "origin", commit]
    try:
        # its own process group with no pipes, so a timeout kills the transport (ssh, a credential helper) too
        run = subprocess.Popen(
            fetch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
    except OSError:
        return None
    try:
        if run.wait(timeout=TREE_FETCH_SECONDS):
            return None
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(run.pid, signal.SIGKILL)
        run.wait()
        return None
    with contextlib.suppress(subprocess.CalledProcessError):
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


def base_branch(pr: int | None) -> str | None:
    """The branch `local-ci` diffs against: PR `pr`'s base, else the default branch (`origin/HEAD`, else what `origin`
    says its HEAD is); None when neither answers."""
    if pr is not None:
        return str(pull_request(pr)["baseRefName"])
    with contextlib.suppress(subprocess.CalledProcessError):
        return (
            git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
            .strip()
            .removeprefix("origin/")
        )
    with contextlib.suppress(subprocess.CalledProcessError):
        for line in git("ls-remote", "--symref", "origin", "HEAD").splitlines():
            if line.startswith("ref: refs/heads/"):
                return line.split("\t")[0].removeprefix("ref: refs/heads/")
    return None


DEEPEN_STEPS = 3
DEEPEN_BY = 50


def deepened(pr: int | None) -> None:
    """In a shallow clone, fetch the base (base_branch) into `refs/remotes/origin/<base>` and deepen until `git
    merge-base origin/<base> HEAD` answers (`--deepen 50` up to DEEPEN_STEPS times, then `--unshallow`), so a gate
    step that diffs against the merge base gets a ref; each step's outcome is a line on stderr. A full clone runs
    nothing, and no tracked file changes, so the tree a pass records is the same."""
    if git("rev-parse", "--is-shallow-repository").strip() != "true":
        return
    base = base_branch(pr)
    if base is None:
        print(
            "local-ci: shallow clone, but no base branch is known: not deepening", file=sys.stderr
        )
        return
    ref = f"origin/{base}"
    spec = f"+refs/heads/{base}:refs/remotes/{ref}"

    def fetch(*flags: str) -> bool:
        done = subprocess.run(
            ["git", "fetch", "--quiet", *flags, "origin", spec],
            capture_output=True,
            text=True,
            check=False,
        )
        what = " ".join(flags) or "fetch"
        outcome = (
            "ok" if done.returncode == 0 else f"failed: {done.stderr.strip() or done.returncode}"
        )
        print(
            f"local-ci: shallow clone, git fetch {what} origin {base}: {outcome}", file=sys.stderr
        )
        return done.returncode == 0

    def found() -> bool:
        return (
            subprocess.run(
                ["git", "merge-base", ref, "HEAD"], capture_output=True, check=False
            ).returncode
            == 0
        )

    if fetch() and found():
        return
    for _ in range(DEEPEN_STEPS):
        if fetch("--deepen", str(DEEPEN_BY)) and found():
            return
    if fetch("--unshallow") and found():
        return
    print(f"local-ci: no merge base of {ref} and HEAD after deepening", file=sys.stderr)


def run_local_ci(
    pr: int | None, head: str | None, passed: list[str] | tuple[str, ...] = ()
) -> dict[str, Any]:
    """Run the gate (with `passed`, gate) on a clean checkout (at PR `pr`'s `head`, when given) and record the pass by
    tree and command, one record per step (run_steps), each step with a pass on the tree reused; refuse a check off
    the head, on a changed tree, failing, or changing the tree, recording nothing for the step that did. The pass
    (whole): with a `host` step left in a cloud session, its `left` names it, and it is no pass on the whole gate."""
    before = checkout_state()
    if head and before[0] != head:
        raise Refused(
            f"the checkout is at {before[0]}, PR #{pr}'s head is {head}: push, or check out the head"
        )
    if before[1]:
        raise Refused(f"the tree has changes, so the check would not run on the head:\n{before[1]}")
    deepened(pr)
    tree = git("rev-parse", "HEAD^{tree}").strip()

    def changes() -> str:
        now = checkout_state()
        return head_moved(before[0], tree, now[0], git("rev-parse", "HEAD^{tree}").strip()) or (
            "" if now == before else now[1]
        )

    done = run_steps(before[0], tree, changes, passed=passed)
    code, step = done["code"], done["step"]
    if step is not None:
        command = step["command"]
        nothing = "nothing recorded" if step["legacy"] else f"nothing recorded for `{step['name']}`"
        if code == settings(project()[1]).get("machine_exit"):
            raise Refused(
                f"{command} hit a machine fault (exit {code}, loop.md's `machine_exit`): {nothing}; fix the machine,"
                " then run it again"
            )
        if code:
            raise Refused(f"{command} exited {code}: {nothing}")
        raise Refused(
            f"{command} changed the checkout, so it did not run on the head as pushed:\n{done['changed']}"
        )
    return whole(done["records"], passed, tree) | ({"left": done["left"]} if done["left"] else {})


def run_steps(
    commit: str,
    tree: str,
    changes: Callable[[], str],
    cwd: Path | None = None,
    out: Any = None,
    passed: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Run each gate step (gate_plan, with `passed`) that has no pass on `tree` (step_pass) and may run here (here),
    in order, each under the host gate slot (ran_step), and record each that passes as run on `commit`, with the
    seconds it ran and the seconds it waited for the slot (stored). A step with a pass is reused and a `host` step in a
    cloud session left, each said on one line naming where the reused pass was recorded, so the log says which steps
    ran. It stops at the first step that fails or changes the checkout (`changes`: what changed, empty when nothing
    did), recording nothing for it. Returns `code` (that step's exit, else 0), `step` (that step, else None),
    `changed`, `records` (each passed step's record, in order), `ran` and `left` (step names)."""
    done: dict[str, Any] = {
        "code": 0,
        "step": None,
        "changed": "",
        "records": [],
        "ran": [],
        "left": [],
    }
    for step in gate_plan(passed):
        # a gate without `gate_steps` says nothing more than it did: its one step is the gate
        say = print if not step["legacy"] else (lambda *_a, **_k: None)
        if (found := step_pass(commit, tree, step)) is not None:
            if found["tree"] == tree:
                say(f"{step['name']}: passed on tree {tree} before, reused from {origin_of(found)}")
            else:
                say(
                    f"{step['name']}: reused, inputs unchanged since {found['tree']} (from {origin_of(found)})"
                )
            done["records"].append(found)
            continue
        if not here(step):
            say(
                f"{step['name']}: no pass on tree {tree}, and it runs only on a host (`where: host`)"
            )
            done["left"].append(step["name"])
            continue
        load: dict[str, Any] = {}
        code, seconds, waited = ran_step(step, cwd, out, load)
        done["ran"].append(step["name"])
        if code or (changed := changes()):
            return done | {"code": code, "step": step, "changed": "" if code else changed}
        record = (
            {
                "head": commit,
                "tree": tree,
                "command": step["command"],
                "exit": 0,
                "env": step["sets"],
                "time": now(),
                "host": socket.gethostname(),
                "seconds": seconds,
                "slot_wait_seconds": waited,
                **{key: load.get(key) for key in LOADED},
            }
            | step_field(step)
            | inputs_field(tree, step)
        )
        stored(record)
        say(
            f"{step['name']}: passed in {seconds} s, after {waited} s waiting for the host gate slot"
        )
        done["records"].append(record)
    return done


def head_moved(commit: str, tree: str, now: str, now_tree: str) -> str:
    """What a gate step did to where the run stands, empty when nothing: HEAD at another commit, or another tree, clean
    or not, means the step's pass would be recorded for `tree` though the steps after it run on another (run_steps)."""
    if (now, now_tree) == (commit, tree):
        return ""
    return f"HEAD moved during the gate: it is {now} (tree {now_tree}), not {commit} (tree {tree})"


def stored(record: dict[str, Any]) -> None:
    """Write a pass this clone ran to its record file (recorded)."""
    where = recorded(record["tree"], record["command"])
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(record, indent=2) + "\n")


def origin_of(record: dict[str, Any]) -> str:
    """Where a reused pass was recorded: its record branch on origin, else this clone's record of the run on a
    commit."""
    return record.get("ref") or f"this clone's record of its run on {record['head']}"


def whole(
    found: list[dict[str, Any]], passed: list[str] | tuple[str, ...] = (), tree: str | None = None
) -> dict[str, Any]:
    """The gate's pass made of its steps' passes `found`, in plan order (gate_plan): without `gate_steps`, the one
    record itself; else one built from them, as a pass is read (head, tree, command and env as gate() names them,
    exit, time, seconds and slot_wait_seconds), the newest step's commit and time, the seconds summed, and `steps`,
    each step's record. Its tree is `tree`, the one gated, when given, since a step reused by its inputs (#963)
    passed on another. Nothing writes it: each step's record is the stored and published pass."""
    plan = gate_plan(passed)
    if plan[0]["legacy"]:
        return found[0] if found else {}
    command, _, env = gate(passed)
    newest = max(found, key=lambda record: record["time"]) if found else {}
    return {
        "head": newest.get("head"),
        "tree": tree or newest.get("tree"),
        "command": command,
        "exit": 0,
        "env": env,
        "time": newest.get("time"),
        "seconds": sum(record.get("seconds", 0) for record in found),
        "slot_wait_seconds": sum(record.get("slot_wait_seconds", 0) for record in found),
        "steps": found,
        "published": all(record.get("published") for record in found),
    }


DETACHED = "APPROVALS_LOCAL_CI_HEAD"
RAN: dict[
    str, str
] = {}  # the gate command this process's local-ci ran, for the detached run to record (finished)


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


def ran_command_file(head: str) -> Path:
    """Where the detached run on `head` records the gate command it ran, beside its exit code."""
    return run_files(head)[2].with_suffix(".command")


def finished(head: str, code: int, command: str | None = None) -> None:
    """The detached run's last step: the gate command it ran (with a head proof, under the caller's tier), then its
    exit code, written whole, after all its output."""
    sys.stdout.flush()
    sys.stderr.flush()
    _, _, exit_file = run_files(head)
    if command:
        ran_command_file(head).write_text(command + "\n")
    partial = exit_file.with_suffix(".exit-partial")
    partial.write_text(f"{code}\n")
    os.replace(partial, exit_file)


def local_ci_status(head: str) -> int:
    """Say whether the detached local-ci run on `head` is running (exit 3), passed (0) or failed (1), with its log;
    passed only when a pass on `head`'s tree under this environment is recorded: with `gate_steps`, of each step the
    run had to pass (ran_command_file), here or, for a step it reused, on origin (record_ref)."""
    head = git("rev-parse", "--verify", f"{head}^{{commit}}").strip()
    log, pid, exit_file = run_files(head)
    try:
        code = int(exit_file.read_text())
    except (OSError, ValueError):
        code = None
    plain = [step["command"] for step in gate_plan() if here(step)]
    try:
        # what the run ran, one command per line, else the plain gate
        commands = ran_command_file(head).read_text().strip().splitlines() or plain
    except OSError:
        commands = plain
    command, held = "; ".join(commands), str(tree_of(head))
    single = len(commands) == 1
    # a step keyed by its inputs (inputs_key) may have passed on another tree with the same inputs
    keyed = {step["command"]: step for step in gate_plan() if inputs_key(held, step) is not None}
    if code == 0 and not all(
        recorded(held, one).exists()
        or not single
        and record_ref(held, one, command_line(one, "gate")[2]) is not None
        or one in keyed
        and step_pass(head, held, keyed[one], show=False) is not None
        for one in commands
    ):
        # a run on a checkout with changes, or on another PR's head, exits 0 with no pass on this one
        print(f"exited 0 without recording a pass on {head} under the gate's command: log {log}")
        return 1
    if code is not None:
        under = f" under `{command}`" if commands != plain else ""
        print(f"{'passed' if code == 0 else f'failed (exit {code})'} on {head}{under}: log {log}")
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


def reusable(
    head: str, passed: list[str] | tuple[str, ...] = (), why: list[str] | None = None
) -> dict[str, Any] | None:
    """A green pass on `head`'s tree under today's gate (with `passed`, gate), or None: a pass of each of its steps
    (gate_plan, step_pass), put together (whole). The record's `head` is the commit the pass ran on. With `why`, the
    reason origin's record branch, found, was rejected is appended to it (record_ref), and with `gate_steps` each step
    with no pass is named."""
    if (held := tree_of(head)) is None:
        return None
    found = []
    for step in gate_plan(passed):
        if (record := step_pass(head, held, step, why)) is None:
            if why is not None and not step["legacy"]:
                why.append(
                    f"the gate step `{step['name']}` ({step['command']}) has no pass on tree {held}"
                )
            return None
        found.append(record)
    return whole(found, passed, held)


def step_pass(
    head: str, held: str, step: dict[str, Any], why: list[str] | None = None, show: bool = True
) -> dict[str, Any] | None:
    """A green pass of gate step `step` (gate_plan) on tree `held` (`head`'s), or None: this clone's record, made on
    any commit with that tree, else one another clone pushed to origin for that tree (published). A record without
    `env` (0.23.1 wrote none) never matches, since nothing says what tier it ran; nor does a failed one, which is never
    recorded. With `why`, the reason origin's record branch, found, was rejected is appended to it (record_ref).
    Without `show`, origin's record is read without writing the `gate` status on `head` (published). A step whose
    `paths` give it an inputs key on `held` (inputs_key) is found by that key alone (input_pass), on any tree."""
    if (key := inputs_key(held, step)) is not None:
        return input_pass(head, key, step, why, show)
    command, env = step["command"], step["sets"]
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
        return record | step_field(step)
    found = (
        published(head, held, command, env, why) if show else record_ref(held, command, env, why)
    )
    return found | step_field(step) if found is not None else None


def input_pass(
    head: str,
    key: str,
    step: dict[str, Any],
    why: list[str] | None = None,
    show: bool = True,
) -> dict[str, Any] | None:
    """A green pass of gate step `step` on any tree whose inputs key (inputs_key) is `key`, or None: this
    clone's record of the step's command holding `key`, else origin's record branch for a tree whose `Inputs:` line
    says it (input_candidates), sound as record_ref reads one. Either counts only when today's `paths` give its own
    tree the same key, so a record saying a key its tree doesn't hold counts for nothing; of this clone's, the newest.
    With `why` and `show` as step_pass's."""
    command, env, name = step["command"], step["sets"], step["name"]
    found = []
    with contextlib.suppress(OSError):
        for path in local_ci_dir().glob(f"*-{gate_key(command)}.json"):
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if (
                isinstance(record, dict)
                and all(isinstance(record.get(field), str) for field in ("head", "time", "tree"))
                and (
                    record.get("command"),
                    record.get("exit"),
                    record.get("env"),
                    record.get("step"),
                    record.get("inputs"),
                )
                == (command, 0, env, name, key)
                and inputs_key(record["tree"], step) == key
            ):
                found.append(record)
    if found:
        return max(found, key=lambda record: record["time"])
    for tree in input_candidates(command, key, why):
        record = record_ref(tree, command, env, why)
        if record is not None and inputs_key(tree, step) == key:
            if show:
                shown(head, record)
            return record | step_field(step)
    return None


def input_candidates(command: str, key: str, why: list[str] | None = None) -> list[str]:
    """The trees of origin's record branches of `command` whose message says the inputs key `key` (record_message),
    each still to be read as record_ref reads one; origin unreachable: none, with the reason appended to `why`."""
    pattern = RECORD_BRANCH.format(f"*-{gate_key(command)}")
    trees = []
    try:
        listed = [line.split("\t") for line in git("ls-remote", "origin", pattern).splitlines()]
        if not listed:
            return []
        names = {ref: ref.rsplit("/", 1)[1] for _, ref in listed}
        git(
            "fetch",
            "-q",
            "--no-tags",
            "origin",
            *(f"+{ref}:refs/loop/records/{name}" for ref, name in names.items()),
        )
        for commit, ref in listed:
            message = git("cat-file", "commit", commit).partition("\n\n")[2]
            if f"{INPUTS}{key}" in message.splitlines()[1:]:
                trees.append(names[ref].split("-", 1)[0])
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        if why is not None:
            cause = " ".join((getattr(exc, "stderr", None) or str(exc)).split())
            why.append(f"origin's record branches for `{command}` could not be read: {cause}")
        return []
    return trees


def inputs_field(tree: str, step: dict[str, Any]) -> dict[str, str]:
    """A gate step's record's `inputs` field, its inputs key on `tree` (inputs_key); none for a step keyed by tree."""
    key = inputs_key(tree, step)
    return {"inputs": key} if key else {}


def step_field(step: dict[str, Any]) -> dict[str, str]:
    """A gate step's record's `step` field, its name; none for the one step of a gate without `gate_steps`."""
    return {} if step["legacy"] else {"step": step["name"]}


def published(
    head: str,
    held: str,
    command: str,
    env: dict[str, str] | None = None,
    why: list[str] | None = None,
) -> dict[str, Any] | None:
    """A pass of `command` (setting `env`, default the gate's) on `head`'s tree `held` that a clone pushed to origin
    as its record branch (publish, record_ref), as a record, or None. It is the one route another clone's pass is read
    by: a `gate` status is only shown, never read, since anyone who can write one may type it. A reader that finds the
    record writes the `gate` status on `head`, so the PR shows the pass, where the token allows."""
    record = record_ref(held, command, env if env is not None else gate()[2], why)
    if record is not None:
        shown(head, record)
    return record


def record_name(tree: str, command: str) -> str:
    """A pushed record's name: the tree it passed on and the gate command's digest (gate_key)."""
    return f"{tree}-{gate_key(command)}"


# a pushed record's lines for the seconds its run took and waited for the host gate slot (record_message)
TIMED = {"seconds": "Seconds: ", "slot_wait_seconds": "Slot wait seconds: "}
# a record's fields and a pushed record's lines for the host's load at the step's start (host_load), and the line for
# its inputs key (inputs_key)
LOADED = {"load_1m": "Load 1m: ", "swap_used_mb": "Swap used MB: "}
INPUTS = "Inputs: "


def record_message(record: dict[str, Any]) -> str:
    """A pushed record's commit message: the status description (described), then the env the gate ran under, and
    the seconds it ran and waited for the slot where the record holds them (TIMED)."""
    env = record.get("env", gate()[2])
    timed = "".join(
        f"{line}{record[key]}\n" for key, line in TIMED.items() if isinstance(record.get(key), int)
    )
    loaded = "".join(
        f"{line}{record[key]}\n"
        for key, line in LOADED.items()
        if type(record.get(key)) in (int, float)
    )
    inputs = f"{INPUTS}{record['inputs']}\n" if record.get("inputs") else ""
    return (
        f"{described(record['tree'], record['head'], record['command'])}\n\n"
        f"Env: {json.dumps(env, sort_keys=True)}\n{timed}{loaded}{inputs}"
    )


def record_ref(
    held: str, command: str, env: dict[str, str], why: list[str] | None = None
) -> dict[str, Any] | None:
    """A pass of `command` under `env` on tree `held` pushed to origin as its record branch (push_record), as a
    record, or None. Only origin is read, the repo `land` pushes its lock to, so a branch on a PR's fork never counts:
    one in the base repo is its write access. The branch's commit must hold `held` as its tree, its parent the commit
    its description names, and the env line `env`, so a record whose content is not what its name says counts for
    nothing. origin unreachable: None, so `local-ci <pr>` refuses unless it is given `--run`. With `why`, a line
    naming the branch found and why it was rejected (or that origin could not be read) is appended to it, so the
    refusal says what to push."""
    name = record_name(held, command)
    ref = RECORD_BRANCH.format(name)
    try:
        listed = git("ls-remote", "origin", ref).split()
        if ref not in listed[1::2]:
            return None
        git("fetch", "-q", "--no-tags", "origin", f"+{ref}:refs/loop/records/{name}")
        body = git("cat-file", "commit", listed[listed.index(ref) - 1])
    except (subprocess.CalledProcessError, OSError) as exc:
        if why is not None:
            cause = " ".join((getattr(exc, "stderr", None) or str(exc)).split())
            why.append(f"origin's record branch {ref} could not be read: {cause}")
        return None
    header, _, message = body.partition("\n\n")
    fields = [line.split(" ", 1) for line in header.splitlines()]
    trees = [value for key, value in fields if key == "tree"]
    parents = [value for key, value in fields if key == "parent"]
    committed = [value for key, value in fields if key == "committer"]
    lines = message.splitlines()
    env_wanted = f"Env: {json.dumps(env, sort_keys=True)}"
    if trees != [held]:
        rejected = f"its commit holds the tree {' '.join(trees) or 'none'}, not {held}"
    elif len(parents) != 1:
        rejected = f"its commit has {len(parents)} parents, not the one commit the pass ran on"
    elif not lines or lines[0] != described(held, parents[0], command):
        found = repr(lines[0]) if lines else "nothing"
        rejected = f"its description reads {found}, not {described(held, parents[0], command)!r}"
    elif env_wanted not in lines[1:]:
        rejected = f"its message lacks the line {env_wanted!r}, the env the gate runs under now"
    elif not committed:
        rejected = "its commit names no committer, so its time is unknown"
    else:
        rejected = ""
    if rejected:
        if why is not None:
            why.append(f"origin holds the record branch {ref}, but it is not this pass: {rejected}")
        return None
    when = int(committed[0].rsplit(" ", 2)[1])
    # a record pushed before #940 names no seconds: still a pass, with its seconds unknown
    timed = {
        key: int(line[len(prefix) :])
        for key, prefix in TIMED.items()
        for line in lines[1:]
        if line.startswith(prefix) and line[len(prefix) :].isdigit()
    }
    loaded: dict[str, Any] = {}
    for key, prefix in LOADED.items():
        for line in lines[1:]:
            if line.startswith(prefix):
                with contextlib.suppress(ValueError):
                    value = float(line[len(prefix) :])
                    loaded[key] = int(value) if key == "swap_used_mb" else value
    inputs = [line[len(INPUTS) :] for line in lines[1:] if line.startswith(INPUTS)]
    return {
        "head": parents[0],
        "tree": held,
        "command": command,
        "exit": 0,
        "env": env,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when)),
        **timed,
        **loaded,
        **({"inputs": inputs[0]} if inputs else {}),
        "published": True,
        "ref": ref,
    }


def push_record(record: dict[str, Any]) -> str:
    """Push a pass to origin as its record branch (RECORD_BRANCH) on a commit holding its tree, its parent the commit
    it ran on, its message the status description and env (record_message), and return the ref. The commit's author,
    committer and dates are fixed, so pushing a pass again pushes the same commit. Refused: CalledProcessError."""
    when = {"GIT_COMMITTER_DATE": record["time"], "GIT_AUTHOR_DATE": record["time"]}
    commit = subprocess.run(
        [
            "git",
            "commit-tree",
            record["tree"],
            "-p",
            record["head"],
            "-m",
            record_message(record),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ | RECORDER | (when if record.get("time") else {}),
    ).stdout.strip()
    ref = RECORD_BRANCH.format(record_name(record["tree"], record["command"]))
    git("push", "-q", "--no-verify", "origin", f"{commit}:{ref}")
    return ref


def drop_records(heads: list[str]) -> None:
    """Delete from origin the record branches no head needs any more: each of the trees of `heads`, landed now, and
    each whose tree is no open PR's head tree and whose record is over a day old (RECORD_AGE), a head that was
    replaced or never landed. The day spares a record pushed before its PR was opened. Only a host deletes, since a
    cloud session can't delete a ref; a refusal is said, and the branch stays for the next land. The open PRs
    unreadable, or an open PR's head tree unknown here (a fork's head this clone can't fetch): only the landed trees'
    branches go, since the unknown tree may be one an old record holds."""
    landed = {held for head in heads if (held := tree_of(head))}
    try:
        # whole objects, since rest_pages decodes each line as JSON and a bare SHA is none
        open_trees: set[str | None] | None = {
            tree_of(pull["head"]["sha"]) for pull in rest_pages("pulls?state=open&per_page=100")
        }
    except (subprocess.CalledProcessError, OSError, ValueError):
        open_trees = None
    if open_trees is not None and None in open_trees:
        open_trees = None
    try:
        git(
            "fetch",
            "-q",
            "--prune",
            "--no-tags",
            "origin",
            f"+{RECORD_BRANCH.format('*')}:refs/loop/records/*",
        )
        listed = git(
            "for-each-ref",
            "--format=%(refname:lstrip=3) %(committerdate:unix)",
            "refs/loop/records/",
        )
    except (subprocess.CalledProcessError, OSError):
        return
    old = time.time() - RECORD_AGE
    for name, when in (line.split() for line in listed.splitlines() if len(line.split()) == 2):
        held = name.split("-", 1)[0]
        stale = open_trees is not None and held not in open_trees and int(when) < old
        if held not in landed and not stale:
            continue
        try:
            git("push", "-q", "--no-verify", "origin", f":{RECORD_BRANCH.format(name)}")
        except subprocess.CalledProcessError as exc:
            print(
                f"the record branch {RECORD_BRANCH.format(name)} was not deleted: {' '.join((exc.stderr or '').split())}"
            )


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


def admitted(head: str, loop: str | None) -> str | None:
    """The stand-in for `head`'s own local-ci pass that let it into a merge queue, `<status> status on tree <tree>`, or
    None: loop.md's head proof (head_proof), such as a light gate's pass, green on the head for its own tree (proved).
    It is the only stand-in, so no queue entry records one: the status on the head says it."""
    proof = head_proof(loop)
    if proof is None or not proved(head, proof["status"]):
        return None
    return f"{proof['status']} status on tree {tree_of(head)}"


def nor_head_proof(loop: str | None) -> str:
    """A refusal's mention of the head proof that would also have let the head in, when loop.md sets one."""
    return ", nor its loop.md `head_proof` status" if head_proof(loop) else ""


def elsewhere(head: str) -> str:
    """What a refusal adds when `head`'s tree passed under another gate command: `; its tree passed under <command>`
    for each, from this clone's records and the tree's record branches in origin, then today's; empty when none did.
    Today's steps (gate_plan) are no other command, so a step's own pass is never named as one."""
    if (held := tree_of(head)) is None:
        return ""
    command, others = gate()[0], set()
    today = {step["command"] for step in gate_plan()} | {command}
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
    others |= pushed_commands(held)
    others -= today | {f"sha256 {gate_key(one)}" for one in today}
    if not others:
        return ""
    return (
        f"; its tree passed under `{'`, `'.join(sorted(others))}`, and the gate is now `{command}`"
    )


def pushed_commands(held: str) -> set[str]:
    """The gate commands (a digest, `sha256 <key>`, for one too long to name) of the record branches origin holds for
    tree `held`, as their lines name them; origin unreachable: none."""
    found = set()
    with contextlib.suppress(subprocess.CalledProcessError, OSError):
        for line in git("ls-remote", "origin", RECORD_BRANCH.format(f"{held}-*")).splitlines():
            commit, ref = line.split()
            git(
                "fetch",
                "-q",
                "--no-tags",
                "origin",
                f"+{ref}:refs/loop/records/{ref.rsplit('/', 1)[1]}",
            )
            named = PASSED.fullmatch(git("log", "-1", "--format=%s", commit).strip())
            if named and named[1] == held:
                found.add(named[3])
    return found


def statuses(head: str) -> list[dict[str, Any]]:
    """The commit statuses on `head`, newest first; ponytail: the first 100, which a head reaches only by hand."""
    out = gh("api", f"repos/{{owner}}/{{repo}}/commits/{head}/statuses?per_page=100")
    found: list[dict[str, Any]] = json.loads(out)
    return found


def shown(head: str, record: dict[str, Any]) -> str | None:
    """Write the `gate` status for `record` on `head`, which the PR page shows and nothing reads; refused or
    unreachable: why, which is no error, since the record branch is the pass."""
    try:
        post_status(head, PUBLISHED, described(record["tree"], record["head"], record["command"]))
    except (subprocess.CalledProcessError, OSError) as exc:
        return (getattr(exc, "stderr", None) or str(exc)).strip()
    return None


def publish(head: str, record: dict[str, Any], proof: dict[str, Any] | None = None) -> None:
    """Publish a pass this clone holds. Without `proof`: push it to origin as its record branch (push_record), the one
    route by which another clone reuses it (published), then show it as the `gate` status on `head` (shown); each
    refusal is said, and a refused push leaves the pass in this clone only. With `proof`, loop.md's `head_proof`: post
    it as the commit status of the proof's `status`, the description naming the values of its `env` (proof_line),
    which `land` reads (proved), unless one already does."""
    if proof is not None:
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
        return
    # with `gate_steps`, each step's record is pushed by itself, one already in origin left as it is
    for one in record.get("steps", [record]):
        if "steps" in record and one.get("published"):
            continue
        try:
            ref = push_record(one | {"time": one.get("time") or now()})
        except (subprocess.CalledProcessError, OSError) as exc:
            why = (getattr(exc, "stderr", None) or str(exc)).strip()
            print(f"not pushed to origin, so only this clone reuses it: {why}")
        else:
            print(f"published in origin as the record branch {ref}")
    if why := shown(head, record):
        print(f"the `gate` status, which only shows the pass on the PR, was not written: {why}")


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
    """How a reused pass is said: the commit it ran on, when, and its record branch; with `gate_steps`, each step's."""
    if "steps" in record:
        each = "; ".join(
            f"`{one['step']}` from the pass recorded on {one['head']} at {one['time']}"
            + (f" and pushed as {one['ref']}" if one.get("ref") else "")
            for one in record["steps"]
        )
        return f"Reused by tree, step by step: {each}; none run again."
    pushed = f" and pushed as {record['ref']}" if record.get("ref") else ""
    return f"Reused by tree from the pass recorded on {record['head']} at {record['time']}{pushed}, not run again."


def no_pass(head: str, why: list[str] | tuple[str, ...] = ()) -> str:
    """Why `local-ci <pr>` found no usable pass for `head`: the head, its tree, the record branch looked for, what
    was wrong with this clone's record (a missing field, another command or env), and `why`, the reasons reusable()
    gave for rejecting origin's record branch, one line each. With `gate_steps`, each line names its step, and a step
    whose record here is sound gets none."""
    held = tree_of(head)
    if held is None:
        return f"no pass for {head}: its tree is unknown here (fetch the head)"
    lines = []
    for step in gate_plan():
        command, env = step["command"], step["sets"]
        said = "" if step["legacy"] else f"step `{step['name']}`: "
        if (key := inputs_key(held, step)) is not None:
            if step_pass(head, held, step, show=False) is None:
                lines.append(
                    f"{said}no pass on its inputs in tree {held} (key {key[:12]}, the files under its `paths`):"
                    f" looked in this clone's records and origin's record branches of {command}"
                )
            continue
        ref = RECORD_BRANCH.format(record_name(held, command))
        found = []
        try:
            record = json.loads(recorded(held, command).read_text())
        except OSError:
            found.append("this clone holds no record for that tree and gate command")
        except ValueError:
            found.append("this clone's record is not JSON")
        else:
            if not isinstance(record, dict):
                found.append("this clone's record is not an object")
            else:
                for key in ("head", "time"):
                    if not isinstance(record.get(key), str):
                        found.append(f"this clone's record lacks its `{key}` field")
                for key, want in (("tree", held), ("command", command), ("exit", 0), ("env", env)):
                    if record.get(key) != want:
                        found.append(
                            f"this clone's record has {key} {record.get(key)!r}, not {want!r}"
                        )
        if said and not found:
            continue
        lines.append(
            f"{said}no pass for the head {head}, tree {held}: looked for the record branch {ref} on origin"
        )
        lines.extend(f"{said}{line}" for line in found)
    lines.extend(why)
    lines.append(
        "push the record (`local-ci --record` on the head) or run the gate here with `local-ci <pr> --run`"
    )
    return "\n".join(lines)


def local_ci(pr: int | None, proof: dict[str, Any] | None = None, run: bool = False) -> int:
    """With a PR: post a pass on its head, from a recorded pass on its tree; with `run`, from a run now when there is
    none, and without it refuse then (no_pass). Without a PR: on a
    clean checkout, reuse or run and record a pass on HEAD, for `local-ci <pr>` to reuse; on one with changes, run the
    check and record nothing. Either publishes a pass this clone holds (publish). With `proof`, loop.md's
    `head_proof` (`--head-proof`, no PR), the gate takes its `env` names from this process (gate), and the pass is
    published as the head proof instead. With `gate_steps`, a step with a pass on the tree is reused and only the
    others run; in a cloud session a `host` step is left for a host, said, and the steps that passed are published,
    but no head proof, nor a pass for a PR, since the gate as a whole has none."""
    if pr is None:
        passed = proof["env"] if proof else ()
        # the commands this run must leave a pass of, one per line, for `--status` (ran_command_file)
        RAN["command"] = "\n".join(step["command"] for step in gate_plan(passed) if here(step))
        head, changes = checkout_state()
        if changes:
            deepened(None)
            command, code = gate(passed)[0], ran_gate(passed=passed)
            print(
                f"{command} exited {code} on a checkout with changes, so nothing is recorded:\n{changes}"
            )
            return code
        if record := reusable(head, passed):
            print(f"{CHECKED} on {head}: {reused(record)}")
        else:
            record = run_local_ci(None, None, passed)
            where = (
                local_ci_dir() if "steps" in record else recorded(record["tree"], record["command"])
            )
            print(f"{CHECKED} on {head}: recorded in {where}")
        if left := record.get("left"):
            print(
                f"{head} has no pass on the whole gate yet: {', '.join(f'`{name}`' for name in left)} runs only on a"
                " host (`where: host`), where `local-ci` runs it alone"
            )
            # each step by itself, so the `gate` status shows a step's pass, never the whole gate's
            for one in record["steps"]:
                if not one.get("published"):
                    publish(head, one)
            return 0
        if proof:
            publish(head, record, proof)
        elif not record.get("published"):
            publish(head, record)
        return 0
    head = pull_request(pr)["headRefOid"]
    why: list[str] = []
    if record := reusable(head, why=why):
        source = f"{reused(record)}\n"
    elif run:
        record = run_local_ci(pr, head)
        source = ""
        if left := record.get("left"):
            raise Refused(
                f"no pass on the whole gate for {head}: {', '.join(f'`{name}`' for name in left)} runs only on a host"
                " (`where: host`); the steps that passed here are recorded"
            )
    else:
        raise Refused(no_pass(head, why))
    if not record.get("published"):
        publish(head, record)
    comment(
        pr,
        f"{CHECKED}\nHead: {head}\nCommand: {record['command']}\n{env_line(record['env'])}{source}",
    )
    return 0


def brief(pr: int, priorities: Path | None, proofs: list[Path], far: Path | None = None) -> int:
    """Print a verifier pass's brief (lead.md step 7) with its facts read from the PR, so none is a previous pass's: the
    verifier role, the base (the merge-base with the default branch), the head, the spec, the pass (one after the
    newest verdict review's) and its report path, from pass 2 the previous report and its head, then the priorities
    file as is and loop.md's `## Verifier brief`, read from loop.md where the policy is gatekeeper.md's. A proof log whose first line isn't the head is refused, since the
    verifier counts a stale proof as missing and spends the pass on it. With `far` (a verifier on another host, `far` an
    absolute path there holding a clone of the repo) its paths are that host's: it fetches the head and makes its own
    detached worktree under `far`'s `tmp/loop/` first, the role is read there, and the report, the previous report and
    the proof logs are in `far`'s `tmp/loop/`, where the lead's `start --file` writes the last two, as are the previous
    pass's repros, each named by its path there from the copy of that report `wait` brought to `tmp/loop/` here."""
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
    role = Path(__file__).resolve().parents[1] / "verifier.md"
    loop_dir = far / "tmp" / "loop" if far else Path("tmp/loop")  # the verifier's tmp/loop/
    tree = loop_dir / f"pr{pr}-v{number}-tree"
    if far:
        if not far.is_absolute():
            raise Refused(f"--far {far}: an absolute path on the verifier's host")
        role = tree / role.relative_to(toplevel())  # the worktree's own copy
    lines = [
        f"Review PR #{pr} as the verifier, pass {number}, following {os.path.relpath(role) if not far else role}.",
        f"- Base: {base}",
        f"- Reviewed head: {head}",
        f"- Spec: {', '.join(f'#{n}' for n in issues) or 'none linked'}",
    ]
    if far:
        lines.append(
            f"- Worktree: first, in {far}, run `git fetch origin pull/{pr}/head` and"
            f" `git worktree add --detach {tree} {head}`, then run every command of this brief in {tree}"
        )
    lines.append(f"- Report: {loop_dir / f'pr{pr}-v{number}.md'}")
    if reviewed:
        newest = next(commit for commit, n, _ in reversed(reviewed) if n == number - 1)
        lines.append(
            f"- Previous report: {loop_dir / f'pr{pr}-v{number - 1}.md'}, on {newest}: review the diff since that head"
            " and rerun its repros"
        )
        # a far verifier works in its worktree, but the last one saved its repros beside its report, in the clone's
        # tmp/loop/: each by its path there, from the copy wait brought home
        if far and (home := Path("tmp/loop") / f"pr{pr}-v{number - 1}.md").is_file():
            saved = re.findall(r"tmp/loop/([\w.-]+)(?![\w./-])", home.read_text())
            lines += [
                f"- Repro: {loop_dir / name}"
                for name in dict.fromkeys(saved)
                if name not in (home.name, f"pr{pr}-v{number}.md")
            ]
    lines += [
        f"- Proof log: {loop_dir / log.name if far else log} (its first line is the head)"
        for log in proofs
    ]
    if line := unforced(pull):
        lines.append(f"- Note: {line}")
    if priorities is not None:
        lines += ["", "Priorities:", priorities.read_text().rstrip()]
    # as written, but for the blank lines around it: indentation may be a snippet's
    if (own := section(loop or "", "Verifier brief").strip("\n")).strip():
        lines += ["", own]
    print("\n".join(lines))
    return 0


def leave_own_environment() -> None:
    """Hand every command this script starts the caller's environment, not the script's own. uv puts the script's
    environment in VIRTUAL_ENV, its bin first on PATH and counts the run in UV_RUN_RECURSION_DEPTH, and a tool that
    follows VIRTUAL_ENV (a type checker) would check the project against the script's packages. A VIRTUAL_ENV equal
    to this script's own is dropped with its bin on PATH, and one that points elsewhere (the script started by an
    interpreter directly) is passed on unchanged; no value is reconstructed, so under `uv run`, which replaces the
    caller's VIRTUAL_ENV before the script starts, the caller's own value does not reach the commands."""
    own = os.path.normpath(sys.prefix)
    if os.path.normpath(os.environ.get("VIRTUAL_ENV", "\0")) != own:
        return
    del os.environ["VIRTUAL_ENV"]
    bin_dir = os.path.join(own, "bin")
    os.environ["PATH"] = os.pathsep.join(
        e for e in os.environ.get("PATH", "").split(os.pathsep) if os.path.normpath(e) != bin_dir
    )
    if (depth := os.environ.get("UV_RUN_RECURSION_DEPTH", "")).isdigit():
        if int(depth) > 1:
            os.environ["UV_RUN_RECURSION_DEPTH"] = str(int(depth) - 1)
        else:
            del os.environ["UV_RUN_RECURSION_DEPTH"]


def pack_behind(script: Path | str) -> str | None:
    """One line, or None: how many commits its upstream's last fetched tip holds that the checkout lacks and that
    changed ``script``, counted since the merge base, so a local commit to it, or upstream changes elsewhere, say
    nothing. Never fetches, so it stays fast and offline-safe; a checkout with no upstream,
    one not behind, or one whose script is unchanged upstream is None. A short copy of this lives in
    orchestrating-agents' omnigent_agent.py (`pack_behind`), since skills install separately and neither may import
    the other: change both together."""
    here = Path(script).resolve()

    def ask(*args: str) -> str | None:
        try:  # a probe that fails for any reason says nothing, since it must never stop a command
            done = subprocess.run(
                ["git", "-C", str(here.parent), *args], capture_output=True, text=True, check=False
            )
        except Exception:  # noqa: BLE001
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    behind = ask("rev-list", "--count", "HEAD..@{upstream}", "--", str(here))
    if behind is None or int(behind) == 0:
        return None
    return (
        f"{here.name}: this checkout is behind its upstream, where {behind} commit(s) changed this script: "
        "run `git pull`"
    )


def refuses_stale() -> bool:
    """Whether the project's `pack_staleness: refuse` (loop.md's `loop` section) makes a stale pack a refusal; a
    project without settings, or outside a checkout, only gets the warning."""
    try:
        return settings(project()[1]).get("pack_staleness") == "refuse"
    except (Refused, subprocess.CalledProcessError):
        return False


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
    # an agent never approves: a record is a person's word, and the owner's policy in loop.md covers the rest; a
    # merge's go may be the delegated approver's, under the owner's delegation
    approving.add_argument("--by", choices=("owner", DELEGATE), required=True)
    # merge only: the head the approver was shown, and their go taken back
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
    recording.add_argument("--run", action="store_true")
    recording.add_argument("--status", metavar="HEAD")
    recording.add_argument("--head-proof", action="store_true")
    merging = commands.add_parser("land")
    merging.add_argument("pr", type=int, nargs="*")
    merging.add_argument("--wait", action="store_true")
    merging.add_argument("--only", action="store_true")
    briefing = commands.add_parser("brief")
    briefing.add_argument("pr", type=int)
    # a verifier on another host: the absolute path there holding a clone of the repo
    briefing.add_argument("--far", type=Path)
    briefing.add_argument("--priorities", type=Path)
    briefing.add_argument("--proof", type=Path, action="append", default=[])
    releasing = commands.add_parser("release")
    releasing.add_argument("issue", type=int)
    hooking = commands.add_parser("commit-msg")
    hooking.add_argument("message", type=Path)
    args = parser.parse_args(argv)
    try:
        if stale := pack_behind(__file__):
            print(stale, file=sys.stderr)
            if refuses_stale():
                return 1
        if args.command == "report":  # reads a local file only, so no remote needs choosing
            return report_check(args.report)
        if args.command == "commit-msg":  # the same: git hands the hook its message file
            return commit_msg(args.message)
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
                raise Refused("approve merge needs --head <sha>: the head the approver was shown")
            if args.point != "merge" and args.by != "owner":
                raise Refused(
                    f"approve {args.point} is the owner's: only a merge's go may be the delegate's"
                )
            return (
                go(args.number, args.head, args.by, args.withdraw)
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
            if args.run and args.pr is None:
                raise Refused("local-ci --run goes with a PR: --record already runs the gate")
            if (args.pr is None) != args.record:
                raise Refused(
                    "local-ci takes a PR number, or --record to record a run on HEAD before one exists"
                )
            proof = None
            if args.head_proof and (proof := head_proof(project()[1])) is None:
                raise Refused("loop.md sets no `head_proof`: --head-proof has no status to publish")
            if args.head_proof and not args.record:
                raise Refused("--head-proof goes with --record: the head proof is the checkout's")
            return local_ci(args.pr, proof, args.run) if leads_its_session() else detach(argv)
        if args.command == "land":
            if args.only and not args.pr:
                parser.error("land --only needs a PR: there is nothing to restrict to")
            return land(args.pr or None, args.wait, args.only)
        if args.command == "brief":
            return brief(args.pr, args.priorities, args.proof, args.far)
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
    leave_own_environment()  # before any command it starts
    detached = os.environ.pop(
        DETACHED, None
    )  # set by detach() for the run it starts, and for no process under it
    code = main(sys.argv[1:])
    if detached:
        finished(detached, code, RAN.get("command"))
    sys.exit(code)
