---
name: engineering-loop
description: The engineering loop, run for every change that will land as a PR, however small - intent, a spec the owner reads, build, gates, proof, an independent verifier, triage, the pass cap and autonomous landing. Use from the owner's request onward, when working or verifying part of one, or when deciding whether a finding is worth fixing.
---

# Engineering loop

A project turns the loop on with one line in its `AGENTS.md`. From then on every change
that lands as a PR runs it, from the owner's request to the merge: tooling, agent
configuration and files under `~/` too, through the repo that owns them. Each step
prevents a failure, and leaves proof on GitHub that `approvals.py` checks. Size changes who
builds and how long the spec is, never which steps run: a step is skipped only when the
owner asks for that change, and the PR body says so.

| Step | Prevents |
|---|---|
| **Intent.** File the request as an issue; read it and the code it touches; ask the owner only at a fork, or park the issue for them. | building the wrong thing |
| **Spec.** Written into the intent's issue for the owner, then approved (`approved:spec`, the ready state); the PR closes it. | a decision the owner never saw |
| **Build.** Workers, or the coordinator when delegating costs more than it saves, always under the worker's rules. | nothing: the one step that scales |
| **Gates.** `mise run check` before every push; GitHub runs every `check:` part. | a broken change |
| **Proof.** On the PR branch before review, then on the owner's instance after landing: each new result against a reference the code did not produce. | works in tests, not in use |
| **Verify.** A verifier from the other model family, up to the cap (The cap). | the author's blind spots |
| **Land**, clean up everything the run created, then report. | a disk full of finished runs |

## What the project states

The loop never names a project's tools. Each step reads a section of one of these
(below, "loop.md § Worktree" means that file's `## Worktree`), and a missing fact is a
question for the owner, not a guess:

| Where | Sections | Read at |
|---|---|---|
| mise tasks (what each does is its `description`: `mise tasks ls`) | when the loop runs them: `test:changed` while iterating, `check` before every push, `loop:approvals <build\|merge> [pr]` before building and before merging, `loop:land <pr>` to merge, `setup:dev` on a fresh checkout | Build, Gates, Land |
| `docs/agents/loop.md` | Owner; Proof on a branch (bring an instance up, tell it is up, read its log, a step to rerun after a schema or build change); Acceptance references, in order; Practice (optional); Approvals (the owner's policy lines and `risk:` rules, Approvals and proof); In use (how to judge a finding); Worktree (create and tear down); Ledger (its path); Verifier checklist. Optional lines `Orchestration backend: <name>` (a pin), `OMP worker profile: <name>`, `cap: <n>` for the project's own cap (The cap), and `CI: none` for a project without CI, whose merge proof is then `python3 scripts/approvals.py local-ci <pr>` (its docstring says what it records). | every step but Gates |
| `docs/agents/issue-tracker.md` | the line `Tracker: GitHub (engineering-loop's github.md)`; Components; Never on GitHub; optionally Extra labels and Extra categories | Intent, Spec, Land |
| `docs/agents/coding-standards.md` | Domain facts | Build, Verify |

### Adopting the loop

kzarzycki/project-templates holds the repo files the loop runs on, so the pack keeps no
second copy. A new repo starts from it with Copier
(`copier copy --trust gh:kzarzycki/project-templates <dest>`); answering yes to mise, the
agent layer, the engineering pack and the engineering loop sets `loop_enabled`. An existing
repo takes these files from it. They are Jinja with includes, so render the template for the
repo's `project_type` into a scratch directory with `copier copy` and copy the rendered files:

- `mise.toml` tasks: the `check:`, `lint:`, `test:`, `ci:`, `loop:`, `setup:` and `agent:`
  groups, with the old names as aliases;
- `.pre-commit-config.yaml`: the git hooks, each one a caller of a mise task;
- `.github/workflows/`: CI, which runs every `check:` part, and the `loop:approvals`
  workflow, which turns `mise run loop:approvals merge`'s exit into the `loop:approvals`
  commit status on the head (0 success, 1 failure, 3 pending, since a job's own result can't
  hold a merge as pending), runs again when CI completes, posts success on a merge-queue
  commit, and removes `approved:merge` on a push;
- `.github/check-paths.yml`: each part's path filter;
- `.github/rulesets/main.json`: a ruleset named `loop-merge-queue` on main, with a squash
  merge queue, requiring exactly two checks, `check` and `loop:approvals`. `mise run
  setup:github` applies it; GitHub layers it on top of the repo's own rulesets, which it
  leaves untouched, and reverting deletes only it.

Hooks are git hooks, installed by `mise run setup:dev`; no check runs from a coding agent's
harness hook. A commit runs the `lint:` tasks on the staged files, and a push runs
`test:changed` and `check:secrets`. The proofs stay off the push, because a push is
reversible and a draft can't merge: `loop:approvals build` runs when the branch is cut, and
`loop:approvals merge` on ready PRs in CI.

A PR stays a draft until no core finding is open (Review trail on the PR), so CI skips its
jobs on draft PRs (`if: ${{ !github.event.pull_request.draft }}` on each job) and lists
`ready_for_review` in its `pull_request` types, so marking a PR ready starts them.
Merge-queue (`merge_group`) and push runs have no draft and run as before. While a PR is a
draft, `mise run check` before each push is its check.

[coding-standards.md](coding-standards.md) is the generic half of the standards, read
with the project's. Issue states, categories, sizes and board columns are the method's,
in [issues.md](issues.md), so every project's board looks the same; [github.md](github.md)
does them on GitHub. A
`scripts/` path is relative to this skill's folder; run it from the worktree with
`python3` (standard library only).

### Practice

loop.md § Practice names the skill that fills a stage, one line each, such as
`Spec: brainstorming`; a stage it does not name runs its default. Either way the stage
produces what this table says:

| Stage | Must produce | Default skill |
|---|---|---|
| Intent | open questions settled, or asked in the issue | `grilling` |
| Spec | the spec in the issue, or linked from it, with acceptance examples and the reference each checks against | `to-spec` |
| Plan, only when loop.md § Practice names a plan skill | ordered slices, each with its check, as a `## Plan` comment on the issue | none |
| Build | commits on the branch, with `check` green | the worker role |
| Review | findings with path, cost and repro, then the verdict lines | `code-review`, run by the verifier |
| Land | the PR body | `pr` |

Whatever the practice, the issue and the board hold the state, the gates run, the
verifier is from the other model family, and the loop merges. A practice skill's own
merging or state-keeping is overridden, because two writers of one state drift apart.

### Approvals and proof

Only people approve: the owner, or a teammate where loop.md asks for one. No agent writes
an approval record, since an agent approving its own work is no approval; where nobody
was asked, the authority is the owner's standing policy in loop.md § Approvals, which
`approvals.py` evaluates from the evidence on GitHub. A spec or plan approval is a comment
`python3 scripts/approvals.py approve <spec|plan> <issue> --by owner` writes on the
owner's word, tied to the spec's or plan's last edit as GitHub's edit history shows it, so
a later edit needs approving again, plus the `approved:<point>` label. A re-approval says
what changed and minimizes the records it supersedes as outdated. The verifier only gives
the verdict, which `python3 scripts/approvals.py verdict <pr> <report>` posts as a PR
review on the commit it reviewed.

loop.md § Approvals holds the policy, one line each:

- `spec: auto unless risk` approves by policy, with no record or label, the spec of a
  `bug`, of an issue whose body has a `Found while #<n>` line (a follow-up an agent
  raised, Triage), or of a native sub-issue of an epic the owner approved (their current
  record and `approved:spec`), opened by an account with write access to the repo. Any
  other spec, a new epic for one, needs the owner's approval; without the line, every
  spec does.
- `merge: auto unless risk`: the gates are the merge approval of a change that is not high
  risk, as they are without the line.
- `risk: <condition>`, one rule per line: what is high risk here, by path, area or kind,
  such as `risk: path .github/**` or `risk: size:L or larger, or component billing`.
  `approvals.py` judges a condition on the labels of the PR and its issues (size,
  component, category; `always` matches everything) and the PR's files (`path <glob>`); a
  condition it can't read matches, since nothing else would enforce it. A `merge:` line
  with a condition in place of the policy reads as a `risk:` rule until the project
  rewrites it, and so does a `spec:` condition beside `spec: auto unless risk`; without
  that line the owner approves every spec, so a `spec:` condition holds no merge.
- `plan: <condition>` asks for the owner's approval of a matching plan.

A change is high risk when `risk:high` is on the PR or an issue it closes, a risk rule
matches, or the cap was reached with a blocker or major open (The cap). A high-risk spec
covered by policy is still built and PR'd; its merge waits for the owner's
`approved:merge` label on the PR, asked for once `check` is green on the head: it counts
only when added after that head's push, and a push removes it, so it never covers code the
owner did not see. When the gate infers high risk, it adds `risk:high` to the PR. Otherwise
the merge approval is the gates themselves: every verifier review on the newest pass's
commit satisfied with no blocker or major open, that commit covering the head that lands,
every review thread resolved, no review requesting changes, and the base's required checks
green. A same-family pass counts, its heading saying so.

When a spec or plan needs the owner, add `needs-owner`, comment what to approve, and stop:
a person approves by adding `approved:<point>`, by saying so in the session, or, for a spec
on a repo with a board, by moving the issue to `Ready` while it has `needs-owner` (`python3
scripts/board.py column <issue>` prints `Ready`), and then you run `approve --by owner`,
which records their word, adds the label and removes `needs-owner`. A change to an
approved spec's scope or acceptance is a decision the owner never saw: remove
`approved:spec`, add `needs-owner` with a one-line comment saying what changed, and stop
until they approve. A spec the owner approved and then edited for wording needs their
`approve` again, since `approvals.py` can't tell wording from scope; one covered by policy
needs nothing. `mise run loop:approvals build` before building and `mise run
loop:approvals merge` before merging check every proof (`scripts/approvals.py` lists
them); `merge` exits 3 while it waits for `check` or the owner's label, and 1 when a proof
is missing. An agent merges only with `python3 scripts/approvals.py land <pr>` (the
project's `loop:land` task): it runs every merge proof, marks a draft ready and waits for
the CI that starts, and on a ready PR merges it pinned to its head, or turns on auto-merge
while only required checks are pending. Never run `gh pr ready` or `gh pr merge` by hand,
because `land` is what refuses a PR whose proof is missing. A repo without
`docs/agents/loop.md` has no rules: `land` there needs each named issue to carry
`approved:spec` and not `needs-owner`, and the PR's own proofs. A rule GitHub can enforce,
such as a required review or a code owner, belongs in branch protection or `CODEOWNERS`,
which the loop obeys and never overrides.

## Roles

- **Coordinator** ([coordinator.md](coordinator.md)): takes a request to a merged PR and
  runs every step above.
- **Worker** ([worker.md](worker.md)): implements a piece of the spec, or a list of
  findings, on its own branch. The coordinator follows it too when it builds itself.
- **Verifier** ([verifier.md](verifier.md)): reviews the PR, drives its instance, and
  leaves the tree as it found it.

Agents are started, messaged, listed and closed through one backend, the first that holds:
a pin in loop.md; the line `Orchestration backend: <name>` in the developer's personal
instructions; the session you run in, read from its environment (`OMNIGENT=1` is
omnigent, `HERDR_ENV=1` is herdr); else native:
[orchestration/native.md](orchestration/native.md),
[orchestration/omnigent.md](orchestration/omnigent.md) or
[orchestration/herdr-link.md](orchestration/herdr-link.md). Only that line names a
backend: an instruction about which CLI or model to use is not one, and never turns a
child into a separate process outside the backend. Inside a worker or verifier, review
angles run as native subagents, never as full harness sessions.

## Rules for every role

- **The owner is on the loop, not in it.** They read specs, never code: gates, tests and
  the verifier are the review. Ask them only at a fork that changes what gets built,
  before something hard to undo (deploy, publish, send, spend), for a credential only
  they hold, or at an approval loop.md § Approvals requires. A technical fork they can't judge is your call. Run commands yourself; when
  a guard blocks one, ask once for a scoped approval, then propose a narrow allow rule,
  never an interpreter-wide one. While they are away, make the reversible decisions, log
  each in one decision-log issue, wait out a usage limit and resume, and leave a handoff
  (`handoff` skill) when finished or stuck. Never idle: schedule a time-gated check and
  keep working.
- **Independent verification.** Nobody verifies a diff their own model family wrote. A PR
  with code from both families gets a verifier for each family's changes, integration
  edits included; each writes its own report, the cap counts rounds they share, and
  landing needs both clear. When the other family is not installed or is out of quota,
  the verifier is a fresh session of the same family and the PR body says
  `verifier: same family`. A brief never says who wrote the code or why the verifier
  shares its family: that biases the review.
- **Reports are files.** An agent writes its report to a file and sends only the path to
  whoever started it, through the backend's message operation, then stops. Text left in
  its own session reaches nobody. A report names each agent's model, and returns only
  what the next step needs; the agent cleans up what it created first.
- **Evidence, not claims.** Report each step's real exit code: a chain's status is its
  last command's. Prove a tooling or config change with a live round trip where it runs,
  and "can't" with a real call. Before saying done, check each item of the owner's
  feedback against what shipped, taking their example as one case of a class.
- **Stop on repeated failure.** Three tool calls in a row failing with the same error,
  even different calls, mean stop and report yourself blocked with the error line. That
  includes a permission classifier that fails closed because its provider is down: every
  retry is a full-context turn.
- **Land small and soon.** Every PR branches off a freshly fetched `origin/main` and merges
  as soon as its gates pass, because a branch that lives as long as the work behind it goes
  stale against main, and a pile of them cascades on every rebase and breaks main when they
  land. An epic lands as one PR per sub-issue, each off main, with no epic or integration
  branch. A sub-issue whose work isn't usable yet lands unexposed, so main stays
  releasable while the epic is half done: wired into no entry point, or behind a flag the
  user docs don't name yet. The sub-issue that exposes it comes last, and documents the
  flag or removes it.
- **One concern per PR.** A change the spec's diff doesn't need (agent config, a skill,
  CI, tooling, an unrelated fix) gets its own PR from main, so it can be reviewed and
  reverted alone. A finding goes on the open PR's branch only when it makes that PR wrong
  or unmergeable: a review blocker or major, a bug the PR introduced, its CI failing, or a
  break on main the PR would cause. Anything else (a minor, an improvement, an adjacent bug
  found on the way) waits for that PR to land and starts from main, because on its branch
  it restarts the PR's review and CI and couples two concerns; chains of follow-up PRs come
  from PRs landing slower than they are produced, and fast landing makes the wait cheap.
  Never push to a PR someone else owns, since that rewrites work under its owner: comment
  on it, or wait for it to land and start from main. Before starting a fix, look for one
  in flight on the board's `Build` column and in open PRs: use it, and don't pause other
  work waiting for it.
- **Stacks are one deep.** Stacking on an unmerged branch is the exception for when
  waiting isn't possible, and only on a PR already in Land (verdict triaged, waiting for
  CI), because a base still in review changes under its stack and every change cascades.
  Its owner moves the stacked PR onto main the moment its base lands, and it lands itself
  with its own `Closes`. Anything else waits, or builds
  on main behind a seam.
- **Revert first.** When main goes red after a merge, or a merged change proves wrong in
  use, the first fix is a revert PR off main, because a revert returns main to a state
  that passed, while a fix forward holds every other merge back and ages every branch. The
  reverted PR's issues reopen with a comment naming the revert, and the fix forward is a
  new change through the loop.
- **Review trail on the PR.** The PR opens as a draft with the branch's first push, and
  every commit after it is pushed. Each verifier pass is posted as a PR review with
  `approvals.py verdict`: one inline comment per finding, labelled `Verifier (<family>),
  pass <n>`, and a summary carrying the verdict. The gate reads these reviews, so the
  review is the verdict. Resolution follows triage, and the verifier never triages: the
  worker resolves only a thread it fixed, reason `ADDRESSED`, replying with the fixing SHA;
  the coordinator resolves a deferred finding `WONT_FIX`, replying with its triage and the
  issue it waits in, and a rejected one `INVALID`, with the one-line why. The owner may
  override any resolution, and alone dismisses a teammate's `CHANGES_REQUESTED`; an agent
  dismisses one only when the owner asks for that review in the session, quoting the ask
  in the dismissal. A human review follows the same pattern. The PR is marked ready once no core finding (blocker or major)
  is open, and squashed on merge. The PR keeps a public trail of what was found, fixed and
  iterated, and the project's CI skips draft PRs, so it doesn't run on half-done work:
  `mise run check` before each push is the check while a PR is a draft.
- **Remove, don't append.** Remove a thing as if it never existed. Edit and compress
  rather than append. A process failure or a costly manual step becomes a deterministic
  tool (a script, one call, no judgement). A routine that finds nothing to do succeeds
  silently.
- **Models.** Pick by what is at stake: the strongest for money paths and design, a
  cheaper one for mechanical items, never the top tier for review. When one family is
  out of quota, continue on the other; revive a stuck or interrupted agent rather than
  restart it.
- **Turns.** A turn the owner reads (not a child's path-only reply) ends with `DONE`,
  `STILL WORKING` or `USER NEEDED`. A status reply opens with a tl;dr: the loop step with
  links to the spec, the PR and the instance, what is blocked, what the owner must do (or
  "nothing"), and each open question restated. Past about 150K tokens of context, at a
  natural break, offer the owner a ready compact command with the summary it should keep.
- **Landing.** Land starts once the last verdict is triaged with no core finding open and
  the ledger is updated; it writes the PR's evidence and runs `approvals.py land <pr>`, which
  marks it ready and merges it, or turns on auto-merge. The PR merges only when the newest
  verdict covers the head that lands, the required checks are green there, and, where the
  change is high risk (Approvals and proof), the owner's `approved:merge` label is on.
  The verdict's commit is the head itself: any commit after it, a merge of main included,
  needs a verifier pass first, and a triage or comment is no verdict.

## Triage

Two axes per finding, judged by how the system is used (loop.md § In use), not by what a
hostile input could do. **Path**: core (the happy path a user or the pipeline hits every
run), edge (a real but rare input), theoretical (an input the system never produces, or
an interleaving nobody can trigger). **Cost**: silent (a wrong result, lost data or a leak
that nobody sees) or visible (crash, stale result, usability).

| Path | Silent | Visible |
|---|---|---|
| core | fix now | fix now |
| edge | fix if a one-liner, else fail-fast guard + ledger | ledger |
| theoretical | reject, one line why | reject |

A fail-fast guard is the cheapest thing that turns a silent wrong answer into a loud
refusal at the boundary (an assert on the assumption, a raise naming the ceiling) plus a
`ponytail:` comment. A rejection costs one line in the PR body. A fix that needs a new
mechanism (a lock, a trap, a baseline format) is a design change: one design note or ADR,
implemented once, not iterated against the verifier. A finding that contradicts the spec
may be resolved by correcting the spec.

The ledger (loop.md § Ledger) has one line per entry: what, where, the guard if
any, what would make it matter, and its issue. The coordinator writes it during triage,
in the fix commit; the verifier reads it first and does not re-report entries.

Everything real the PR leaves unfixed is placed before the report. The test: would
closing the spec's issue without it be dishonest?

- **Yes, it is within the issue's own acceptance:** the issue stays open, the PR says
  `Part of #n` instead of `Closes #n`, and a comment on the issue names what remains (a
  comment, since an edit to the spec needs approving again).
- **No, it is outside it** (a ledger entry, or a bug, a flaky test or a problem only the
  owner can fix, `needs-owner`, found outside the spec's diff): a new issue stating
  problem, cause, fix, acceptance and a `Found while #n …` line. It is a native sub-issue
  of the originating issue's epic, or of the originating issue itself when that issue's
  own goal contains it and it has no parent, which makes it an epic
  ([issues.md](issues.md), Epics): the PR then says `Part of #n`, since an epic stays open
  until its sub-issues are done. Otherwise it stands alone. Attached, it counts toward
  the epic's progress instead of starting a chain of follow-ups the board shows as a flat
  list.

A rejected finding is not real, so it gets no issue.

## The cap

The cap is 5 passes, unless the project's loop.md sets its own with a line `cap: <n>`.
Every other file says "the cap", so this is the one place to change it, and
`approvals.py` reads the same value. Pass 1 reviews the PR's full diff; each later pass
up to the cap reviews the diff since the previous report and reruns its repros. No fix
lands without review: every head that lands has a satisfied verdict on that exact head,
so any commit after the last verdict, a merge of main included, gets a verifier pass of
its own.

- **The last pass under the cap leaves a blocker or major open:** stop and ask the owner,
  since the fix keeps regressing and only they decide what happens next. They have two
  options. One is a fix followed by one pass past the cap, scoped to the open items. The
  other is leaving the code untouched, and parking or closing the PR. You never fix and
  land on your own call: `land` holds such a PR for the owner's `approved:merge` label,
  added after the head's push.
- **The last pass under the cap leaves only minor or edge findings open:** ledger them and
  file their issue (Triage), leave the code untouched, and land on the satisfied verdict.
  There is no owner stop.
