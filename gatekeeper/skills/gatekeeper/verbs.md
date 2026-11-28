# Verb reference

What each `gatekeeper.py` verb checks, writes and refuses, and its full usage lines. This text was the script's module
docstring until #2834, which moved it here unchanged so `--help` stays short; the script's own `<verb> --help` is the
short form. Its rules also appear, in other words, in [policy.md](policy.md) and [SKILL.md](SKILL.md). Where they differ,
the code and its tests decide, and the difference is a bug to fix in the text.

`approvals.py` in the usage lines is the script's name before #614; it runs the same verbs. Stale in the text below, kept as it was: the `approvals.py` prefix; `approvals.py release <issue>` is gone from this script (its usage line is dropped; the loop's `loop.py release <issue>` does it); and "reads docs/agents/ at the checkout's root" was replaced by the base-ref rule in the Ports section.

## Usage

```
uv run scripts/approvals.py check <build|merge> [pr]  # one line per missing proof, exit 1; waiting: exit 3
    uv run scripts/approvals.py check build --issue <n>   # before the PR exists: the issue's build proofs; exit 0 or 1
    uv run scripts/approvals.py check build <n>           # <n> no PR has: the same as --issue <n>
    uv run --python '>=3.11' scripts/approvals.py check setup               # a pack upgrade's gate: the repo's policy parses and its mise tasks and workflows run the scripts with uv; exit 0 or 1
    uv run scripts/approvals.py check ready <pr>                # the author's step before the verifier: the PR body's `## Evidence` (and demo form) alone, the check merge runs; exit 0 or 1
    uv run scripts/approvals.py check session <pr>              # the PR body's `Impl:` line must carry `Session: <server>/c/<id>` (check merge runs it too); a body with no `Impl:` line passes; exit 0 or 1
    uv run scripts/approvals.py check stalled              # every open PR land would take that its queue does not hold, or verified and idle past loop.stalled_after_hours with no go or record: one line each, exit 1; one not judged here: its line, which changes no exit
    uv run scripts/approvals.py land [<pr>... [--only]] [--wait] [--json]  # land every landable PR through the base's merge queue; exit 0, 1 or 3
    uv run scripts/approvals.py approve <spec|plan> <issue> --by <owner|delegate>   # on the owner's word, or the delegate's under `loop.delegate: all`
    uv run scripts/approvals.py approve merge <pr> --head <sha> --by <owner|delegate> [--withdraw]  # a go on that head
    uv run scripts/approvals.py delegate <pr>              # the delegated approver's approved:merge, feature branch only
    uv run scripts/approvals.py verdict <pr> <report>      # post a verifier report as a PR review
    uv run scripts/approvals.py report <report>            # check a verifier report as verdict reads it; posts nothing
    uv run scripts/approvals.py overlap <pr>|--files <path>... [--base <b>]  # other open PRs changing the same files: hunks, and whether the heads merge
    uv run scripts/approvals.py local-ci <pr> [--head <sha>] [--run]  # --head: the commit just pushed, refused if GitHub's head stays another; with `ci: false`: post the head's recorded pass, refuse without one; --run runs `mise run check:all` here then
    uv run scripts/approvals.py local-ci --record [--base <rev>]  # the same on HEAD, the gate before each push; reused by tree; narrowed under `ci: false` or with --base (Narrowed mode)
    uv run scripts/approvals.py local-ci --status <head>   # the detached run on a head: running (exit 3), passed, failed
    uv run scripts/approvals.py local-ci --record --head-proof  # the same under the caller's env values: loop.md's head proof
    uv run scripts/approvals.py local-ci --record --rerun [--base <rev>] [--no-push]  # an independent rerun of HEAD's selection: nothing reused, its record keyed apart (levels' `rerun`); --no-push keeps the record commit as a local branch and names it, for a CI job without a write token
    uv run scripts/approvals.py check rerun <pr>           # whether the PR's rating asks a rerun and has one: `rerun: needed`, `rerun: done` or `rerun: not needed (<why>)`; exit 0 once it has read the PR (a missing PR exits 1)
    uv run scripts/approvals.py gate-record <head> [-- <command>]  # the verifier's read: origin's pass record of the gate (or <command>) on <head>'s tree, exit 0, else 1 naming what to run
    uv run scripts/approvals.py queue-select [<base>]      # a merge queue's batch check (R6): one command per line to run on the batch, the select.unkeyed checks and `affected-tests --base <point>` for each PR with no record; exit 1 when that is nothing while a PR has no record
    uv run scripts/approvals.py queue-config               # the Mergify config `.mergify.yml` holds: the pack's mergify.yml with gatekeeper.md's `land` batch_size and batch_wait_seconds
    uv run scripts/approvals.py timeouts [--json|--mergify|--check]  # every limit the working tree's `timeouts` derive; --mergify prints .mergify.yml from it, as queue-config does; --check: exit 1, one line each, when .mergify.yml, a marked workflow job's `timeout-minutes`, loop.md's `Wall-clock variable:`, a hand-set `land.wait` or the nightly's push paths (against `select.build_inputs`) is out of step
    uv run scripts/approvals.py durations [--record <junit.xml|durations.txt> [--out <file>] [--setup <seconds>]] [--report]  # the nightly's per-test durations file (what `shards --durations` and `affected-tests`' estimate read); --report: a line per gate run whose time is over 25% from its estimate
    uv run scripts/approvals.py affected-tests [--base <rev>] [--record] [--local]  # a whole-suite selection (a declared `select.whole_suite` file; `select.checks` still run) under `loop.ci` true prints `whole suite selected; CI runs it` and runs nothing, its record the head's tests pass; --local runs it here; the worker's test run on a head: loop.md's `Affected tests:` command against <rev>, else the merge base; the narrowest set when it can't tell; `check` under `Gate: full` or with no selector; --record: its pass pushed as `local-ci --record` pushes a narrowed one; stopped at `timeouts.run`, exit 124 and one line
    uv run scripts/approvals.py rerun-tests <failed-tests.json> --red <head> [--base <rev>]  # a red run's one rerun (R5): the failed tests plus what the fix reaches, else the red run's whole selection, where a pass is a flake; the red head's `Affected tests:` line, never the base's; exit 75 when the rerun ran no test
    uv run scripts/approvals.py prune-records [--head <sha>...]  # delete origin's gate records (`refs/loop/gate/` refs and `loop-gate/` branches) no open PR head needs, then run the one upgrade sweep (old `loop-gate/` and `loop-event/` branches moved to `refs/loop/`; `claude/*` branches whose PR is merged or closed deleted, #2821): the trees of the given (closed or merged) heads at once, any other tree over a day old with no open PR; every `land` ends with it, so a merge by Mergify or a queue, or a closed PR, leaves none (#1869); needs a token that can delete refs
    uv run scripts/approvals.py shards --suite <file> [--selection <file>] [--whole] [--durations <file>] [--passed <head> | --record <head> --shard <i>] [--command <cmd>]  # a whole-suite selection split into `select.shards` disjoint shards; --passed: whether each shard has a pass on <head>'s tree; --record: run shard <i> and record its pass
    uv run scripts/approvals.py claim <issue> [--takeover|--release]  # an early claim as an `Assigned: @` record on the issue; --takeover writes `Handover:`; --release `Released:`
    uv run scripts/approvals.py graduate <epic> --pr <n>   # graduate an incubating epic: label off, then close
    uv run scripts/approvals.py heavy <command> [args...]  # one heavy command under the host's heavy wrapper; its exit code passes through
    uv run scripts/approvals.py heavy --plan               # the host's gate slot count and the limit that set it
```

gatekeeper.py is the gatekeeper; approvals.py, its name before #614, runs it for one release line, every verb above
unchanged. Its own names for three of them, and one verb more:

```
uv run scripts/gatekeeper.py record approval <spec|plan|merge> <n> --by ...  # `approve`, the same arguments
    uv run scripts/gatekeeper.py record verdict <pr> <report>   # `verdict`
    uv run scripts/gatekeeper.py record checks [<pr>] [--record|--run|--status <head>|--head-proof]  # `local-ci`
    uv run scripts/gatekeeper.py record waiting <pr> --on <what> [--within 4h|2d]  # a PR waiting on another agent tree's go: `Waiting on:` and its `Deadline:` (default 24h); `--clear` ends it (#2501)
    uv run scripts/gatekeeper.py report --json <report>   # the report's facts as JSON: verifier, head, verdict, ...
```

## Ports, staleness and where the policy comes from

The policy reaches the tracker, the forge and the evidence only through their ports (PORTS), each run by the adapter
the policy's `adapters` section names for it (`tracker`, `forge`, `evidence`), `github` for one it doesn't:
github_adapter.py, through `gh`, with its GraphQL reads falling back to REST where GitHub refuses GraphQL, and every
posted body checked against the deny list first. A name no adapter has is refused, naming it. The gate's own commit
status counts under `loop:approvals`, the name the project template's workflow posts, and under `gatekeeper` for one
release line: `check merge` and `land` wait for neither.

At start every verb warns on stderr, once, when this script's checkout is behind its upstream's last fetched tip (no
fetch) and the script differs there: the count and `git pull`. loop.md's `pack_staleness: refuse` under `loop` makes
it a refusal (exit 1).

Run anywhere in the checkout: it reads docs/agents/ from `origin/<base>` (the ref `land` builds its merge on), so a PR can't loosen its own gate; a differing copy in the working tree gets a stderr line, and the base's is used (`project()`). The policy is gatekeeper.md's block under
`## Policy`; without that file, loop.md's block under `## Settings`, with a deprecation line on stderr, and with both a
policy in each is refused, naming both, since two sources of the bar would drift. "gatekeeper.md's" setting below means the
policy's, in whichever file holds it. The project's `mise run loop:approvals
<point> [pr]` task runs `check`, and its `loop:land <pr>` task, where it has one, runs `land`; the loop and CI call
those tasks.

## `check build`, `check merge`, `land` and the other verbs

`check build` needs every issue the PR closes to be free of `needs-owner`, with exactly one category, a component and
exactly one size (a `wayfinder:` ticket needs only `approved:spec` and no `needs-owner`), and its spec approved: the
owner's current record and `approved:spec`, unless gatekeeper.md's `spec.auto` covers it
(below). A `## Plan` comment needs the same where the `plan` rule asks, and is due when gatekeeper.md's `practice` names a
`plan` skill. Category, component and size names are the loop's fixed set plus docs/agents/issue-tracker.md's
(`label_names`): a category is `kind:<name>`, a component `area:<name>`, whether the tracker file names it bare or in
full.
`check build` with a PR also runs `check merge`'s keyword check (below), where the lead hands the PR over, so a wrong
keyword is fixed before the PR reaches the landing queue. `check build` also refuses an issue assigned to anyone but its approver (the person who last added `approved:spec`,
or for a spec the policy approves the account running this), since an assignee says whose the issue is; and, with a
PR, an issue another open PR closes too (a closing keyword, or `Implements` under a `signoff` rule), naming that PR
and its branch, since each build runs its own verifier, gate and queue. When every build proof holds, it assigns each issue no one holds to its approver, comments a record that the loop did, and gives
the PR its issues' assignees, reporting a refusal and carrying on. A flow that releases the claim (the loop's `release`) removes an assignee that record names,
unless someone assigned them again after it, and keeps every other: a claim a person made stays.
Under Omnigent (the lead's own `OMNIGENT_SESSION_LINK`, else `OMNIGENT_RUNNER_PRIMARY_SESSION_ID` and `RUNNER_SERVER_URL` set) the record's details add `Session:
<server>/c/<lead's session id>`, which names the lead from inside its workers and verifiers too, and the issue's `Session`
issue field is set to the same link. The field is optional: the account's owner creates it (a text field); without it,
the run says so in one line after one lookup, the record still carries the link, and the claim and the exit code are
unchanged. A refused write is a line too. Where GitHub refuses GraphQL, REST sets it, with the field's id read off an
issue already carrying a value; otherwise the supervisor, which runs where GraphQL works, sets it from the record. `check setup` prints one line and GitHub's steps when the account lacks the field.
A repo without docs/agents/gatekeeper.md or loop.md has no rules: each issue needs only `approved:spec` and no `needs-owner`, with no
approval record. Without docs/agents/issue-tracker.md no label's shape is checked.
`check merge` also fails a PR that itself carries `needs-owner` (`#<n> waits for the owner (needs-owner)`), so `land`
never takes it, alone or in a batch, until the owner's go on its head (`approve merge --by owner`) removes the label.
`check merge` adds the PR's, whose absence fails (exit 1): the `## Evidence` section of its body; the keyword linking
each issue, where gatekeeper.md has a `signoff` rule (below); the verifier's PR
reviews, a review counting only when its body starts `Verifier (<family>), pass <n>` (same-family included) and the
PR's author, the account running this or an account that can write to the repo posted it, since anyone can review a
public repo: every one on the newest
pass's commit says `SATISFIED: yes` with 0 blocker and 0 major, and that commit is the head itself, since every
commit after a verdict needs one of its own; on a high-risk change (below), that pass came from the default tier, not
one whose heading names `mid` or `small` (a `Verifier model:` tier, the verifier role), since a lower tier's review is enough
only for a change it rates low (a fallback verifier's family, `agy`, `gemini` or `same-family`, is no tier), and on a PR
that only bumps the pack's pin, the pin target's tier rule judges that pass instead (pin_target); no unresolved
review thread; no review whose latest state is `CHANGES_REQUESTED`; and a newest `## Demo` comment, where a trusted
author posted one, that embeds its videos and screenshots as user-attachments (`demo.sh`), which `check build` checks too. Then it waits (exit 3, one line per wait; the approvals workflow maps it to a `pending`
status) for the newest run of each check the base branch requires, as `land` reads them, to be green on the head,
since GitHub merges nothing without them (a base that requires none waits for no check, and `ci: false` asks no
`local-ci` pass: the verifier's record is the merge's proof, and no gate runs after it), and, while the change's level asks a go of its merge
(below), for the owner's go on that head: the newest commit status `owner` on the head commit by the account running this or a writer is
green, and the PR holds the owner's record (`Approved by the owner.`, then `Approved: merge`, `By: owner`,
`Head: <sha>`) naming that head. `approve merge <pr> --head <sha> --by owner` posts both on the owner's word, the
record's every word the script writes, refusing a head other than the one named, which is the one the owner was
shown; `--withdraw` posts a newer failing status and a `Withdrawn: merge` record and removes the `approved:merge`
label. A status belongs to one commit, so no push carries the go to a head the owner didn't see. `--by delegate` is
the delegated approver's go, pinned to one head the same way: the `owner` status described as the delegate's (`The
delegate's go on <sha>, under the owner's delegation`) and the record `Approved under the owner's delegation.`, then
`Approved: merge`, `By: delegate`, `Head: <sha>`, so the PR shows whose go it is. Where GitHub refuses the status
write with a 403, as a cloud session's proxy does (#1816), the record is posted with a `Status: refused` line and
stands as the go alone on a head with no `owner` status: the newest such record, or `Withdrawn: merge` record, naming
that head and written by the account running this or a writer decides, still pinned to its head; over a status on
the head only such a record written after it decides (so a withdrawal recorded from the cloud takes back a host's
go), and a record without the line still needs its status. Into the default branch it is
refused unless loop.md's `delegate: all` under `loop` (default `feature`) lets the delegate's go cover that branch
too, and a delegate's status there counts only while it does, so removing the setting withdraws those goes on open
PRs; into a feature branch it counts either way. `check merge` and `land` print whose go, the owner's or the
delegate's, a head whose level asks a go has. Into the default branch these are the only go: a
label is anyone's with triage rights, the delegated approver's included, so `approved:merge` there is no go, nor is
an `owner` status an older gate wrote from the label (marked as from it). On a change whose level asks no go the
label means nothing. Risk is a rating, and the policy's `levels` say what each level asks (rating, levels): `high` is
`risk:high` on the PR or an issue it names, or a risk rule matching (below); `critical` a path `risk.critical_paths` names
(below); `low` anything else. Each level asks `policy` or `owner` of the spec and `gates`, `go` (a person's go on the
head, as above) or `owner` (the owner's own go on the head, into any branch, no delegate's go nor label counting) of
the merge; the merge takes the strictest any of its terms asks. The defaults are `low` {policy, gates}, `high`
{policy, go}, or under `spec.auto: true` {owner, gates}, and `critical` {policy, owner}. A term the spec's hold never
reads (the label, a revert, the `verifier` term) rates the change only after its spec was approved, and asks
`go` where its level asks `owner` of the spec and `gates` of the merge, since the owner never saw that rating.
`check merge` and `land` print the level and the merge action on stderr (`PR #7: risk: high (<why>); merge: go`). When
the gate rates a change high or critical, `check merge` and `land` add `risk:high` to the PR, reporting a failure to
add it and carrying on, except for a term the label, read back as a `high` rating after the spec, would ask more of:
by default a rule that held the spec under `spec.auto: true`, whose level is {owner, gates}. On a PR into a feature branch (any base but the repository's default branch)
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
With `opt_out: true` in gatekeeper.md, a person may keep their PRs out of the loop: `check merge` on a PR that
left no loop trail (no verifier review, no `Approved: spec` record or `approved:spec` on an issue it links, no
`Reverts #<n>` line, not an exempt bot PR) prints that it is outside the loop, naming the proofs it lacks, and exits 1, as `land` does for the same PR (one rule, `outside`): `land`
never takes it into a batch, and named, prints the same line and exits 1, so the loop never merges it and its author merges it their usual way. Risk rules and `risk:high` hold no such PR. `check build` is
unchanged. A spec a policy covers is no trail, since under `spec.auto: true` every issue is covered.
`land [<pr>... [--only]]` is the one way an agent merges. It lands every landable PR into one base, the first named PR's or else the
repository's default branch, through one of three merge queues, picked by the base's rules (`required_checks`) and the
policy: the GitHub merge queue where the rules carry a `merge_queue` rule, else the Mergify queue where the policy's
`land.queue` is `mergify` (below), else the local merge queue, the path for a project without a queue (held_by).
`land.queue: github` records the project's choice of GitHub's queue: it changes nothing where the rules carry the
`merge_queue` rule, and is refused (exit 1) where they carry none, since `land` would then merge each PR itself while
the policy says a queue does. All take the
same candidates (step 2). A queue gates each group it merges in CI (GitHub's `merge_group` run, Mergify's batch
check); the local merge queue runs no gate at all: a PR merges on the verifier's record on its head, with the checks
the base requires green there, and nothing reruns at land (#1872). Since no queue run tests that merge, a head with no
record on origin of loop.md's `Affected tests:` run against its merge base (`gate-record <head> -- <the narrowed
command>` exit 1; the gate's record where the project has no narrowed run) is not landed, and `land` says which record
is missing and that `affected-tests --record` (else `local-ci --record`) on that head makes it (head_recorded, R6); a
break-glass PR, which the owner merges, is not held. One `land` runs one of them, never a mix. The local
merge queue lands its candidates as one batch:
1. It takes the landing lock, the branch `loop-landing/<base>` on `origin`, which only moves forward, so a host whose
pushes may only create or fast-forward a branch under `refs/heads/` (a cloud session's) takes and releases it too. Its
tip says the state: each lock commit holds the empty tree, its title says `landing lock: held` or `landing lock: free`
with `[skip ci]` (so a project whose workflows run on every branch push starts none), its body the pid, the PR
it lands (`land <pr>`'s, none for a bare `land`) and a random value (so two lands in the same second never make the same
commit), and its commit date is its age. A land pushes a `held` child of a `free` tip (or the first lock commit, with no
parent, where the branch is missing), leased on that tip with `--force-with-lease`, so of two lands from one tip one
wins. Once its batch is merged locally, before its first merge on GitHub, it moves the lock to a `held` child of its own naming the
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
own output) green on its head. Under `ci: false` the head needs no `local-ci` pass. With loop.md's `head_proof`, the head also carries its head proof (below), else it is no candidate and `land`
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
3. With loop.md's `land: batch_wait_seconds` set (a whole number, default 0: no wait), and before the worktree below,
it waits up to that long while another open PR into the same base is held by nothing but its required checks still
running (its proofs and any owner go already hold: a red check, a draft, a proof gap or an owner wait never counts),
polling every QUEUE_POLL seconds; each such PR that turns landable joins the batch. It stops
when none is pending or the time is up, so a lone PR lands at once; with PRs named by `--only` it never reads or waits
on other PRs. It prints the wait and who joined, and the `Landed` comment's `Batch:` line adds `(waited N s, joined:
...)`. The key is optional in `land`, which asks for signing keys only where `signed_squash_to` is set.
   In a temporary worktree of `origin/<base>` under the git common dir, removed after, it first runs loop.md's
`pre_land`, where set, for each candidate: a command parsed as `gate` is, run there at the base's tip with `LAND_HEAD`
(the PR's head) and `LAND_BASE` (that tip) set, so the base's tree holds the check and a PR never changes what judges
it. A non-zero exit leaves that PR out of this batch, printing the check's last lines on every land, with a comment,
once per head, holding its output; it is not red, so it is neither evicted nor turned back to draft. Then it merges each candidate's head
(`git merge --no-ff`). A PR that conflicts is skipped, with a comment, once per head, saying it conflicts with the base
plus the PRs merged before it, so it needs the base merged in. No gate runs on the result: no `gate` or
`gate_steps` command, no reuse of a recorded pass, no re-run of a red one.
From a clone with no working tree (no index: a `--no-checkout` launch dir), where every command reads the policy files
from origin's default branch (policy_ref), step 3 makes no worktree: the heads merge in objects (`git merge-tree
--write-tree`), and `land` refuses a `pre_land` it has no checkout to run in.
   `check merge` runs the same `pre_land` the same way (one function, pre_land_run), in a temporary worktree of the
base's tip, once nothing else holds the merge, so it never calls clear a PR `land` would leave out: a refusal prints
`PR #<n>: `<cmd>` refuses it against <base> at <tip>, exiting <code>: land leaves it out` with its output's last
lines and exits WAITING, not 1, since land keeps the PR ready; it posts no comment. While something else holds the
merge it prints `PR #<n>: pre_land not run: `<cmd>` (land runs it once nothing else holds the merge)`, and from a
clone with no working tree, where land refuses a `pre_land`, a `pre_land not run` line saying so, exiting WAITING.
4. It merges each PR through GitHub in that order, pinned to its head (`gh pr merge --squash
--match-head-commit`), with the body the repo's squash default writes. A merge GitHub refuses, or leaves unmerged
(a merge queue the base's rules don't name, such as classic branch protection's, only queues it, to merge later on a
tree no land saw), stops there: that PR and those after it wait for the next land. Then it deletes the record
branches no head needs: those of the heads it landed, and those over a day old whose tree is no open PR's head (a head
replaced or never landed; the day spares a record pushed before its PR opened). A refused delete is said and never
fails the landing. No gate runs on the base's new tip either: the nightly's full run is what catches a break the
merged trees make. Each PR landed gets one comment, `Landed`, then `Base:` the new tip, `Tree:` the tree it landed
(the base with it and the PRs before it merged), `Gate: none at land, on the verifier's record of the head`, and
`Batch:` the PRs landed together. Each PR it merged then has its kept `--pr` worker sessions finished by a detached
(the omnigent-agents skill's `omnigent_agent.py reap --merged --pr <n>`), whose outcome goes to its own log, never the land's.
Exit 0 when the named PR merged (on a GitHub-queue base, also once it is enqueued or queued), or with no PR named when nothing landable failed; 1 for a refusal, a conflict, an
eviction (a queue's) or a merge GitHub refused; 3 while it waits; 143 or 129 when stopped by SIGTERM or SIGHUP.
`land --wait` runs it again while it waits on the lock or on CI, printing each new state once, for up to its ceiling,
derived from the policy's `timeouts.run` (the queue's checks timeout) plus a margin of one more run, for the batch
ahead of the PR or the one retry of a red batch: 2 hours with nothing set, 8 hours with `run: 4h` (`gatekeeper.py
timeouts` prints it; a `land.wait` duration such as `4h30m`, deprecated, still overrides it), then exits 3, leaving the PR's event `waiting` where a queue
or its checks still move it, else `needs-owner`; a wait for the owner ends it at once, since only the owner clears it. Between two runs it reads every 30
seconds only what it waits on, at no API quota: a held lock with one `git ls-remote` (running again once the lock moves
past its holder's heartbeat, or has not moved for 15 minutes), a named PR's CI with one ls-remote of the base and the
heads and an ETag read of each head's checks, which GitHub answers 304 for free while nothing changed (#1915).
Each named PR's branch carries the `land` event (events.md): `waiting` rewritten at each poll of `--wait`, `ok` once it
merged (its refs cleared EVENT_GRACE seconds later, so a `wait land <branch>` finds the end), `failed` when evicted (its
`url` the log comment), `needs-owner` at the owner's go or at the ceiling while nothing moves the PR. A write that fails changes no exit code.
The GitHub merge queue takes no landing lock (GitHub orders the entries, and two lands enqueueing one PR change
nothing), builds no local batch, runs no local gate, publishes no pass. Its record branches are swept all the same: `landing()` ends every land, this path included, with `drop_records` (#1869, #2692). Once it has fetched
the base (the base-drift refusal below), each of step 2's candidates, oldest PR first, goes in with GraphQL
`enqueuePullRequest`, `expectedHeadOid` the head the proofs judged, and GitHub drops an entry whose head moves, so no
proof outlives a push. Where GraphQL answers 403 it goes in with auto-merge on (REST `ccr/auto_merge`, the queue's
merge method and that head), and the PR is read again: a head other than the judged one has auto-merge taken off
and is refused (exit 1), naming both heads, and the other candidates still go in. A PR already queued is left alone, unless its entry is in `AWAITING_CHECKS` with no check suite
on its group's commit 10 minutes after that commit was made (GitHub lost its `merge_group` event): then it is dequeued
and enqueued again. Else
the queue's last removal of the head decides: the PR's `RemovedFromMergeQueueEvent`s since its head was pushed and since
it last went ready, so a PR evicted and marked ready again counts anew. `merged`: nothing to do (exit 0), since GitHub reports
the merge a moment after the removal. A PR GitHub reports conflicting: step 3's conflict comment, once per head, and not
enqueued (exit 1). A `merge_conflict` removal holds only that long, since the queue tests an entry on the entries ahead
of it, so the conflict may have been with one of them: while GitHub works the PR's mergeability out again after the
base moved, land exits 3 at once (`GitHub is still working out whether PR #<n> conflicts`), and a later land, once GitHub
reports it mergeable, enqueues it again. `failed_checks`: first the checks the base requires are read on its tip; one red there stops
the land (exit 1, `<base> itself is red`), counting nothing and evicting nobody. Then each such removal is placed on
the base commit its group was built on (the merge base of the base and the group's commit): a required check that
failed there (`FAILURE`, `TIMED_OUT`, `STARTUP_FAILURE` or `ERROR`; a run cancelled, stale or awaiting approval failed
nothing, and the queue's own run on that commit went green) makes it the base's fault, so it never counts and gets no comment, and the PR is enqueued again; still running,
nothing counts yet (exit 3, `<base>'s checks on <sha> are still running`). Of the removals that count, the head's first
gets a `Red in the merge queue` comment naming the check that failed on the queue's commit, its run and
its failed job log's last 30 lines, and is enqueued again; its second turns the PR back to draft with the same, as
Mergify's queue evicts (`Evicted from the merge queue`, exit 1). A `failed_checks` removal whose required checks on the
group's commit failed only by timing out (`TIMED_OUT`) counts for nothing, as any other removal (`checks_timed_out`,
`manual`) does, and the PR is enqueued again: a timeout is no test's failure (#2228), until the head's second one (a removal of either kind): that PR stays out of
the queue, `land` printing one line that names `timeouts.run` and its length and exiting 3 as a wait on a person (raise
the budget or shard the suite), and a Mergify dequeue its check run calls a timeout does the same on its second at one
head, from the `Timed out in the merge queue` records land comments (#2308). Either queue's stop lifts with a new
head, a ready-again (as its reds' count does) or a changed `timeouts.run`, which the `Timed out twice in the merge
queue` record each leaves at the head names (`Run:`). Mergify records its first timeout too, so a budget raised between
the two makes the next a fresh first; the GitHub queue records only its stop, so both timeouts count. The count lives in GitHub's timeline, so any land applies it and `land` keeps no
state. A PR enqueued or already queued exits 0, naming its queue position and head, and `land` ends. `land <pr> --wait`
waits on instead until the queue merges it (exit 0, after its `Landed` comment) or takes it out, whose removal the
next round reads as above (#2101): between rounds it reads, each QUEUE_WATCH seconds (60), only the PR's state, head and
queue entry, one GraphQL call (two ETag reads on REST, a 304 costing no quota), so a lead need not poll the PR itself;
the same holds under `land.queue: mergify`, where a merge, Mergify's dequeued label or a push ends that read. A later
`land <pr>` reads a removed entry's state once (above). Exit 3 stays for a PR whose conflict GitHub is still
working out, or a base still running its checks: nothing was enqueued yet. Without `--wait`, who tells the lead of a merge or a removal
is the project's watcher, not `land`.
`land --json` prints, after the usual output, one JSON line per PR the land judged (every candidate, for a bare `land`):
`{"pr": <n>, "head": "<sha>", "state": "...", "cause": "...", "url": "..."}`, so a caller that routes on the exit code can
tell what the exit hides. `state` is `merged` or `queued` (no `cause`, null), `waiting` (something is moving: cause
`lock`, `checks`, `mergeability`, `base-checks` or `base-red`, a red base, which is no fault of the PR and exits as ever),
`needs-owner` (only a person can act: `go`, `queue-timeout` or `ceiling`) or `refused` (the PR needs a fix: `proof`, `checks`,
`conflict`, `evicted` or `github`). `url` is the comment that carries the detail where land posted one, else the PR's. Each
line is written where its exit is picked, so the two agree, and the exit codes and the output without `--json` are unchanged.
Under `--wait` the lines are the last round's. A PR left out before it is judged (closed, or on another base) has none.
 The first land that reads
a PR the queue merged (a `land <pr>` naming it, or a bare `land`, which reads every merged PR into the base that carries
`loop:queued`, the label `land` puts on each PR before it enqueues it) comments `Landed` on it, `Base:` its merge commit, `Tree:` that commit's tree and `Gate: merge
queue` with the links of the runs on that commit (the queue's `merge_group` CI), and finishes its worker sessions as
step 5 does, then takes the label off, so a trail that failed (said, never failing the land) is written by the next
land. The queue merges with its own `merge_method` and writes the squash message from the repo's squash
default, which `land` neither sets nor overrides, as in step 5. A head matching
`land.merge_commit_heads` is refused unless the queue's method is `MERGE`, since the queue merges every entry one way;
`land.signed_squash_to` is refused, since GitHub signs the queue's commit. A cloud session takes this path too, with
no `land.signing_key_env`, since GitHub signs: REST answers every step (auto-merge off dequeues; the PR's queue state
is its timeline's queue events, GitHub's `gh-readonly-queue/<base>/pr-<n>-<sha>` ref and the repo's `merge_group`
runs), and since REST names no removal's reason, each is read from its group's commit: `merged` when GitHub reports
the PR merged or that commit is in the base, `failed_checks` when a check the base requires failed on it,
`merge_conflict` when GitHub reports the PR conflicting or is still working that out, else none, which counts for nothing.
With `land.queue: mergify` in the policy (gatekeeper.md's `land:` section), on a base whose rules require no GitHub merge
queue (they win), a Mergify queue that `.mergify.yml` configures merges instead, which needs a repo no organisation owns
no GitHub queue for: `land` takes no lock, runs no gate and merges nothing. It judges the same candidates (step 2) with
the base's code, and hands each to Mergify by posting the `land` status (success, `Queued for Mergify at <sha>`) on its
head and adding `loop:queued`; `.mergify.yml`'s queue conditions
read both, and the status binds the hand-over to that head, so a push leaves them unmet. Where GitHub refuses the
status write with a 403 (a cloud session's proxy), `land` adds the label and comments a `Queued for Mergify` record
with `Head: <sha>`, once per head, and the repo's `.github/workflows/land-status.yml` posts the `land` success on that
sha for a writer's record while it is the PR's head and the label is on; an eviction's `land` error refused there is
said, and the label coming off leaves the queue. A PR already carrying the label
with `land` green on its head is reported queued and left alone. Mergify tests each batch as a draft PR on top of the
base in CI, retries a red one once itself and squash-merges on green; a PR it dequeues (red again, or conflicting) gets
its `dequeued_label`, `loop:dequeued`, and the next land that reads it with `land` green on the head evicts it: `land`
`error` on the head, both labels off, back to draft and an `Evicted from the merge queue` comment naming Mergify's
reason where its queue check run on the head gives one (a label left from an older head just comes off). A dequeue
whose queue check run's title or summary says it timed out is no test's failure: the label comes off and `@mergifyio
queue` takes the PR back, evicting no one (#2228). A bare land, or
`land <pr>` naming a merged one, comments `Landed` on each merged PR still carrying `loop:queued` (`Base:` its merge
commit, `Tree:` that commit's tree, `Gate: Mergify merge queue` with the Actions runs on that commit), finishes its
worker sessions and takes the label off. Exits as the GitHub merge queue path: 0 once queued, 1 for a refusal or an
eviction, 3 while a required check on the head runs (`--wait` waits for that, and for a named PR it queued, until
Mergify merges it or dequeues it, as above). Every call of a round is REST, so a cloud session lands this way with no signing key; with `land.signed_squash_to` it is refused, since GitHub signs
Mergify's merges.
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
`land.merge_commit_heads` (a list of fnmatch patterns over head branch names, such as `sync/*`) lands a PR whose head
matches with `gh pr merge --merge --match-head-commit`, a merge commit that keeps the head's ancestry (an upstream-sync
PR needs it), instead of the squash above; every other PR lands as before. `land` prints each PR's method, and a
match with `signed_squash_to` set is refused, since a signed squash has no merge-commit form.
`where: host | cloud | both` (default `both`) says where `land` runs: it refuses elsewhere, exit 1, before reading any
PR. A cloud session is one where Claude Code sets `CLAUDE_CODE_REMOTE=true`. There, without `signed_squash_to`, `land`
merges each PR over REST (`PUT pulls/N/merge`, squash, `sha` the judged head), since GitHub's GraphQL merge is refused by
the session's proxy; GitHub signs that commit as it does a host's, and no signing key is needed. With `signed_squash_to`
its checkout signs with the session's own key, shared across that service's users, so `land` refuses without
`ssh-keygen` installed, when it names no `signing_key_env`, and when that variable
is unset, empty, no unencrypted SSH private key, or a key whose public half is no line of the allowed signers file, each
refusal naming which and never the key. Else it writes the key to a mode-0600 file in a fresh temporary directory,
removed however the land ends, and every git command of the land runs with it (`-c gpg.format=ssh -c
user.signingkey=<file> -c gpg.ssh.program=ssh-keygen`, over the session's key and signing program), so each squash is
signed and verified with it. There REST alone answers, and it says neither whether a PR is in a merge queue nor
whether classic branch protection requires one, so a PR is a candidate there only with `merge_queue: false` in the
section, the project's word that its base requires none (a ruleset that does picks the GitHub merge queue, above);
a draft is marked ready and an evicted PR turned back to draft through the proxy's draft routes
(`ccr/ready_for_review`, `ccr/convert_to_draft`). Off a cloud session only `where` is new.
`land` (once it has fetched the base) and `check merge` refuse, naming the files, when this script or the tracker file, loop.md or gatekeeper.md differ from `origin/<base>`'s, so a PR is judged by the base's code and rules, never its own: run from a checkout of the base. `check merge` under `GITHUB_ACTIONS` also refuses when the checked-out commit is not on the base's history (an older base commit passes this step, and the drift check above judges its files). `land --wait` that meets the refusal because another land moved those files while it waited fast-forwards a clean checkout of the base (its branch checked out, no tracked file edited) and runs again from the new code, keeping its ceiling; any other checkout is left alone and the land runs again from a fresh detached worktree of `origin/<base>`, removed when it ends; the refusal stands only when nothing newer exists to run from (the checkout is the base's tip, or the base lacks the running script).
loop.md's `carry_over_main` and `ci` work as below for one more release, each printing one `deprecated:` line on
stderr. The keys that drove a gate at land, `batch_queue` under `loop` and `land`'s `gate_on`,
`cloud_gate_timeout_seconds` and `host_gate`, do nothing (#1872): a policy that still sets one parses, with one
`ignored:` line on stderr naming it, and the `check queue` and `batch` verbs are gone.
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
the tree, as above; a change to `gate_steps` changes every keyed step's key. A step may set `on_demand: true` (#2295),
for a check too costly to run on every PR (an hours-long run against a paid external system): `local-ci` and
`local-ci --record` skip it, each saying `<step>: skipped, on demand`, `land` reads only the other steps' records, and
the gate's pass never needs it, since a
gate step runs on every PR whose tree has no pass of it. `local-ci --record --step <name>` (repeatable, with
`--record` alone; a name `gate_steps` lacks is refused) runs those steps alone and records, publishes and reuses each
pass as any step's, by its inputs key, so an unchanged input never runs it again; it writes no `gate` status or event,
since it is no pass of the gate, and `gate-record <head> -- <its command>` reads its pass. A cloud session runs no `host` step: `local-ci --record` there runs the rest, says
which step it left and exits 0, with no head proof and no pass on the whole gate, which `local-ci <pr>` needs
and refuses there. Each step that runs, or the one gate, holds the host gate slot (an exclusive flock on
`${XDG_CACHE_HOME:-~/.cache}/engineering-loop/gate.<n>.lock`, n up to the host's slot count) for its run only, with `LOOP_GATE_SLOT_HELD` set to that
path so a wrapper in it takes no lock of its own, and none when this process already runs under it. The count is `GATE_SLOTS`
when it is a whole number from 1; else, where loop.md has the line `Gate cost: <cores> cores, <GB> GB` (optional
`, reserve <GB> GB`, by default a quarter of the host's total memory, at least 4 GB), the smaller of the cores ÷ the
cost's cores and (total memory − reserve) ÷ the cost's GB, at least 1; without the line, a third of the cores, at least
1. `GATE_SLOTS=off` takes no slot at all. `heavy --plan` prints the count and the limit that set it, `slots <n>:
<cores|memory|GATE_SLOTS|off> (<cores> cores, <GB> GB, cost <c> cores <m> GB, reserve <r> GB)`, as the template's
`gate-slot --plan` does, and a wait for a slot says the same line; `local-ci --record` makes one on HEAD with no PR. On a checkout with changes `--record` runs the check, records
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
A run that gates a branch also writes its `gate` event (events.md, `refs/loop/gate/<branch>`, the checked-out branch): `waiting` while a step waits for a slot or runs, rewritten every SLOT_SAY_SECONDS; `ok` at the end with
`url` the record (with `gate_steps`, the records' directory); `failed` with `url` the detached run's log when there is one,
else empty (a failed step records nothing, and a refusal has no log either). The detaching `local-ci` writes `waiting`
first, before it starts the run, so a wait that follows it never reads the previous head's end, and ends the event itself when the run wrote none (`failed` with the log on a nonzero exit, `ok` with no url on exit 0, as a record on a changed tree); a step left for a host keeps `waiting`. Writing an event never
changes the exit code. The `gate` commit status stays on the PR head: `wait-for --until gate` reads it and the PR
page shows it, and no event reader replaces it yet. `land` publishes none on main, since it runs no gate.
Every pass this clone holds, run or reused, is published one way from every session, host or cloud: pushed to origin
as the ref `refs/loop/gate/<tree>-<command's key>` (the branch `loop-gate/<tree>-<key>` where origin refuses a ref outside `refs/heads/`, as a cloud session's proxy does: the `loop-refs.yml` workflow moves it and deletes the branch; every reader reads the ref first, then the branch), on a
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
where GraphQL answers 403, so it runs in a cloud session too. `local-ci <pr>` and `local-ci --record` read it the
same way; the posted comment then says it was reused by tree from the pass recorded on that commit, and when, instead
of running the check again. The host stays
in the record: nothing `approvals.py` posts names it, and posted text writes the home directory `~` (public), since a
public board would show both. The posted comment names the gate's command and the variables it sets (`Env: A=1`, or
`Env: default`).
With loop.md's `head_proof` under `loop` (`status: <context>`, `env: [<names>]`), each head proves itself under env values
the lead picks (the PR's acceptance test classes), which the gate's fixed env doesn't. `local-ci --record --head-proof` runs the gate as `--record`
does, but takes each `env` name the caller's environment sets from it instead of clearing it, over the gate line's own
assignment of that name, so the command it records names the value (`GATE_UI_TESTS=LoginAcceptanceTest mise run check:all`). It
publishes the pass as the commit status `<context>` instead of `gate`, described `Tree <tree> on <commit's first 12>:
<name>=<value> ...` for the `env` names it ran with (`default` for none), so the verifier reads the values off the head.
`land` reads it, the one status a decision reads for a pass: a green status of that context on the head commit itself, naming the head's tree,
by the account running this or a writer. A status on an older head never counts, since a status belongs to one commit.
Which tests prove a change is the project's rule (the PR's own acceptance tests); `land` checks only that a head proof exists.
Narrowed mode: loop.md's line `Affected tests: <command>` without the line `Gate: full`, the opt-out (narrowing). Its
command is the whole narrowed check: the project's selector plus its cheap whole-repo lint and type checks, reading the
base from the variable `Gate base:` names, else `GATE_BASE`. `affected-tests` runs it against `--base <rev>` (a PR's
base SHA, a push's previous tip), else the merge base with the branch's base. Where it can't tell exactly, it runs
the narrowest set it can still name (#2217): a `<rev>` git can't resolve (all zeros, a new branch) selects against the
merge base, and a loop.md without the line runs the `select` cut, then `mise run check` for a change the cut can't
settle; zero runs only for a change of non-product paths, saying `0 selected: non-product`. The opt-out runs `mise run
check`. Under
`ci: false`, `local-ci --record` runs it against `--base`, else the merge base, and `local-ci <pr>` posts that pass on
the head's tree, against the merge base of the head and the PR's base; `check merge` reads no local-ci pass (#1872). A
narrowed pass's command is the variable's assignment, the command, then ` (narrowed)`, which no gate command can hold,
so its record and key never equal a full pass's, and nothing that wants a full pass takes it. `affected-tests
--record` records its pass the same way (local_ci under narrowed_to its base), and `gate-record <head> -- <the narrowed
command>` reads it, its last word `(narrowed)`. Its `gate` status and record branch say `narrowed vs <base>`, and `local-ci --status` says `narrowed against <base>`. A project with
`gate_steps` keeps its steps everywhere, since each narrows by its `paths`. Without the `Affected tests:` line, `check
build` says in one line that every gate runs the full check (not with the opt-out, which chose it).
Deprecated: with loop.md's `carry_over_main` section (`except: <globs>`), merges of the base into a PR head H keep H's proofs:
each commit from the head H' down its first-parent line to H is a merge whose second parent is on the base (an
ancestor of its tip), whose tree is what `git merge-tree --write-tree` makes of its parents (no conflict resolved,
nothing added), and where the base's changes since the merge base touch no file the PR's side changes and no path an
`except` glob matches (fnmatch, as a rule's `paths`: the project's merge-check configuration, such as lint, type,
test and gate config and lockfiles). So a PR commit after H, new, edited or rebased, carries nothing. Then H's newest
verdict covers H' (`check merge` and `land`, the verifier's `Risk:` line included). It never carries
a `local-ci` record: H' runs its own gate, as CI would run on it. `check merge` and `land` print one line per merge
naming it, its first parent and the predicate, or why the head carries nothing. A git error, a second merge base or
any failed condition carries nothing: the head needs its own verdict, as without the section, where `check merge` and `land` read no git for it.
Every comment and review `approvals.py` posts is checked first against a local deny list, the file the environment
variable `LOOP_DENY_LIST` names (denied): a line naming a listed term, outside an Omnigent session link, refuses the post before any call to GitHub.
`verdict` posts a report in the verifier role's format as one PR review (event COMMENT, since GitHub refuses the others on
one's own PR) on the commit its `Head:` line names, carrying any text after the pass number on its `Verifier:` line
(a qualifier, such as why the verifier shares the author's family) into the review's first line, refusing a report without that line or its
`Verifier: <family>, pass <n>` line or its `Risk:` line, a `### ` heading with a `(<severity>)` it can't read as a finding, or finding
headings that don't add up to the `VERDICT:` counts (any other `### ` heading is a sub-heading and posts nothing), a report
with no `## Criteria` section or an empty one, an `Accepted on evidence: <line> — <proof log>` line naming no proof log,
and any `Accepted on evidence:` line in a report whose `Risk:` is not `low`, naming it, since a manual line on a high-risk
change is probed by hand: one
inline comment per finding, moved to the nearest line of the diff when its
line is outside it and saying so, and in the review's body when its file is outside the diff. The review's body
carries the `## Criteria` section first and each `Accepted on evidence:` line before the closing lines.

## Reverts, approvals and the spec's identity

An exact revert skips the spec and the verdict: a PR whose body has a line `Reverts #<n>` (GitHub's Revert button writes
`Reverts <owner>/<repo>#<n>`), where #n is a merged PR and, file for file as GitHub's diff of each shows them, the PR
removes what #n added and adds what #n removed (files, and each run of lines in order; line numbers and context may
differ), and every path either touches has at the PR's merge base the mode it had after #n and at its head the mode
it had before #n, absence included. A file GitHub shows no diff of (binary, too large, only renamed or moded) is never
exact. Its code returns to a state already specced and reviewed, so `check build` passes it and `check merge` asks
only for Evidence (what went wrong), no unresolved thread or review requesting changes, the base's required checks
green and the label where the change is high risk, which for a revert also means `risk:high` on an issue it names or on #n, or #n's
last verdict judging it high, since undoing a high-risk change changes as much as making it.
A `Reverts #<n>` PR that is not exact gets a line saying why, then every proof of any PR.

A spec or plan approval is a person's: a comment `approve --by owner` writes on the owner's word, which the gate
reads, plus the `approved:<point>` label for the board. No agent writes one, since an agent approving its own work
is no approval. Where the policy on origin's default branch sets `loop.delegate: all`, the owner's standing
delegation covers specs and plans too: `approve <spec|plan> <issue> --by delegate` writes the record with `By:
delegate` under the line `Approved under the owner's delegation.`, adds the label and removes the issue's
`needs-owner`, the spec's hold; without the setting it is refused. `loop.delegate_spec: false` (default true) keeps
specs and plans the owner's under `delegate: all`: `approve <spec|plan> --by delegate` is refused, naming the key, and
a delegate's record counts for nothing, while the delegate's go on a merge is unchanged. The gate counts a delegate's
current record in place of the owner's only while the policy it reads sets `delegate: all`, no `delegate_spec:
false`, and the PR touches no path `risk.critical_paths` names, which stays the owner's, and otherwise names why it
doesn't count. `approve breakglass` stays the owner's
alone. The owner's record:

```
Approved: spec
    By: owner
    Spec: sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08      (plan: Plan:)
```

A spec or plan is named by its text, the sha256 of the issue's or comment's body as GitHub stores it (line ends read
as `
`), so any change to the text voids the approval, read through GraphQL or REST alike, and restoring
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
does, or marks fields FORBIDDEN, as a job token in a private organization repository gets: after one refused call a
run reads REST alone, the same fields call by call. REST has no closing links, so a PR's issues are its body's
`Closes`, `Part of` and `Implements` lines; its review threads come from the proxy's `pulls/<n>/ccr/review_threads`
route, or, where GitHub itself answers 404 there, from GraphQL asked for the threads alone, and where neither answers
the read fails rather than count none; a commit
co-author, which only GraphQL resolves to an account, exempts no PR from review; and whether a PR is in a merge queue
can't be read, so `land` refuses it there. The proxy refuses the collaborator lookup too, so there only the account
running this counts as a writer, by its own permissions on the repo.

## The policy block and its rules

The policy block (policy.md beside SKILL.md has every key), YAML, holds the owner's standing policy, checked against SCHEMA: a
section or key it doesn't know or a value of the wrong type is refused, naming the key, and so is a file without
the block. `loop` holds `cap`, `ci`, `opt_out`, `gate`, `local_ci_env`, `owner`, `machine_exit`,
`short_seconds` (mutate.py's), `pre_land` and `head_proof`; `mutate` holds `inconclusive_exit` (mutate.py's); `spec` holds `auto`; `levels` holds `low`,
`high` and `critical`, each with `spec` and `merge` (above), and `rerun`, whether `check merge` and `land` need an
independent rerun of the head's selection on its tree (default false at every level: a repo turns it on once a workflow pushes the rerun record): a
record of `local-ci --record --rerun` on origin that an app pushed (a CI run on the head) or that a verifier pass on
the head names on a `Rerun: <record commit>` line (a fresh session the verifier started), never the worker's own
record (rerun_gap).
`spec.auto` as a list approves by policy, with no record or label, the spec of an issue of each kind it names:
`bug`, labelled a bug; `follow-up`, carrying a `Found while #<n>` line in its body (a follow-up an agent raised);
`sub-issue`, a native sub-issue of an epic with the owner's current spec record and `approved:spec`, opened by an
account GitHub's collaborator permission gives admin, maintain or write. A high-risk one is still built; its merge
waits for what its level asks. `spec.auto: true` approves every spec the same
way, epics included, except one opened by an account without write access, or one rated before the build at a level
whose `spec` is `owner` (by default `high` there: the risk rule on the labels of the issue and the PR and the PR's
files, at `check build` the files pushed so far): those need the owner's record and label, and `check` says why. A
level asking `owner` of the spec holds a spec a `spec.auto` kind covers too. Under `spec.auto: true` the risk rule
holds the spec instead of the merge by default, since the owner approved the change before it was built; `risk:high`
and the `verifier` term still hold the merge. The list may also
hold a `paths` term (`- paths: [mise.toml, docs/agents/**]`), globs as a rule's `paths` are: it approves by policy the
spec of an issue labelled `spec:paths`, which the lead adds to declare that the change stays inside them, since the
gate can't tell that from the spec alone and the setting alone would approve every spec until its merge. `check build`
and `check merge` judge it on the issue's and the PR's labels and every path the PR touches, at `check build` before
the PR the branch's files so far: it approves only while every path matches a glob, a moved file's old name as well
as its new one, so a rename across the boundary either way voids it; GitHub gives the whole file list and every old
name; neither carries `risk:high` nor the risk rule holds (its `verifier` term too, once a review is read); and the
issue's author can write to the repo. Otherwise the owner approves the spec, and `check` names why, the files outside
the globs included. The label without the term approves nothing. Without `auto`, or
with `false` or an empty list, the owner approves every spec, and the gates are the merge approval of a change whose level
asks `gates` of the merge.
Whatever `spec.auto` says, a migration row's issue that nothing above covers is covered by its parent's approval: a
native sub-issue whose body opens with `Part of #<parent> (row <name>)`, naming that parent, whose spec carries
`approved:spec` and a current record as a direct link's would (the owner's, or the delegate's where it counts), opened
by an account that can write to the repo, where neither the issue nor the PR carries `risk:high` and neither the risk
rule nor `risk.critical_paths` holds on the PR's files. `check` names the parent and the row it credits, or the piece
missing from a row it doesn't; the verifier checks the row against the parent's table.

A rule (`risk`, `plan`, `signoff`) is a section of terms, any one of which matches: `always: true`; `labels`,
label names matched exactly on the PR and its issues; `paths`, globs matched on the PR's files; and in `risk` alone
`verifier: true`. `risk.critical_paths` (deprecated name `merge_paths`, read with a `deprecated:` line; both set is
refused), globs matched on the PR's files as `paths` are, is no term of the rule: a PR touching one rates `critical`
whatever its labels, `spec.auto` and the verifier's `Risk:` line say, and by default only the owner's go
on its head lets it merge, into any branch, so `check merge` and `land` wait for it, `approve merge
--by delegate` and `delegate` refuse it, and the label is no go; files it can't read hold. A list holds strings. The gate reads the keys, never the words of a rule, so a path or
label can never read as a term. A glob matches every path the PR touches on either side of the change: a
deleted file's, and a renamed or copied file's old name as well as its new one. Paths it can't judge, past the one
page of files it reads or an old name GitHub won't give, hold. The `plan` rule asks
for the owner's plan approval, and has no `paths`, since a plan comes before the change. A `bot.<login>` section,
such as `bot.dependabot[bot]` with `paths` uv.lock and **/package.json, lets that bot's PR merge without a verifier
review when every commit is the bot's (author, and a committer that is the bot or no account) and each file it changes, none renamed or copied,
matches one of its paths (exempt); with `branch: renovate/` it names an updater opening PRs under a person's token by
its head branch instead, and a `verify` label refuses either; without one, every PR needs the review. The `signoff` rule says whose change the
owner signs off in use after it lands: `check merge` needs the PR to link each issue it matches, or whose spec has a
line `Sign-off: owner`, with `Implements #<n>`, which leaves it open for the sign-off, and every other issue with a
closing keyword (`Part of` suits both); without a `signoff` section no keyword is checked and `Implements` is a link like
`Part of`. `verifier` holds at the merge (under `spec.auto: true` too, since the verdict comes after the build) when the
verifier judges the change high: the highest `Risk:` of the verifier's passes since its last `Scope: full` pass (its first pass counts as one), by
a trusted account (passes), is `high`, any word but `low`, or missing, and the hold quotes it. A head no review covers waits for its review instead; a
PR that needs none (exempt, an exact revert) has no judgment. A `risk:high` the gate added for that term comes with a
comment saying so, and the gate takes the label off once a later `Scope: full` pass says `Risk: low`, unless it was added again
after that comment, which is a raise only the owner lowers. Paths in the same rule hold whatever the verifier says.
The board's `Risk` field follows the label and the verifier's word, and a field at `High` adds the label (flag); the
label stays the gate's only input, and a board it can't reach is a line, never a failure.
The spec is the issue body, or its last comment whose first line is `## Spec`, where a tool owns the body. A soft gate against a forgotten step, not a security boundary: the agent holds the same
credentials as the person. issue-tracker.md's components and extra categories are the keys of its settings block's
`components` and `categories` (tracker_settings). Reads and writes through `gh`. Stdlib, and PyYAML for the settings
block (SKILL.md § Settings says how it is delivered).
