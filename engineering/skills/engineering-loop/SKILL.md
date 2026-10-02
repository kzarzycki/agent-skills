---
name: engineering-loop
description: The engineering loop, run for every change that will land as a PR, however small - intent, a spec the owner reads, build, gates, proof, an independent verifier, triage, the three-pass cap and autonomous landing. Use from the owner's request onward, when working or verifying part of one, or when deciding whether a finding is worth fixing.
---

# Engineering loop

A project turns the loop on with one line in its `AGENTS.md`. From then on every change
that lands as a PR runs it, from the owner's request to the merge: tooling, agent
configuration and files under `~/` too, through the repo that owns them. Each step
prevents a failure, and leaves proof on GitHub that the gate checks. Size changes who
builds and how long the spec is, never which steps run: a step is skipped only when the
owner asks for that change, and the PR body says so.

| Step | Prevents |
|---|---|
| **Intent.** File the request as an issue; read it and the code it touches; ask the owner only at a fork, or park the issue for them. | building the wrong thing |
| **Spec.** Written into the intent's issue for the owner, then `ready-for-agent` and approved; the PR closes it. | a decision the owner never saw |
| **Build.** Workers, or the coordinator when delegating costs more than it saves, always under the worker's rules. | nothing: the one step that scales |
| **Gates.** `mise run check`. | a broken change |
| **Proof.** On the PR branch before review, then on the owner's instance after landing: each new result against a reference the code did not produce. | works in tests, not in use |
| **Verify.** A verifier from the other model family, three passes at most. | the author's blind spots |
| **Land**, clean up everything the run created, then report. | a disk full of finished runs |

## What the project states

The loop never names a project's tools. Each step reads a section of one of these
(below, "loop.md § Worktree" means that file's `## Worktree`), and a missing fact is a
question for the owner, not a guess:

| Where | Sections | Read at |
|---|---|---|
| `mise run check` | the gate: lint, types, tests, e2e, leak checks; CI runs the same task | Gates, Land |
| `mise run gate <build\|merge> [pr]` | the proof gate: `scripts/gate.py check`, then the project's own checks; a pre-push hook and CI run it too | Build, Land |
| `docs/agents/loop.md` | Owner; Proof on a branch (bring an instance up, tell it is up, read its log, a step to rerun after a schema or build change); Acceptance references, in order; Practice (optional); Approvals; In use (how to judge a finding); Worktree (create and tear down); Ledger (its path); Verifier checklist. Optional lines `Orchestration backend: <name>` (a pin), `OMP worker profile: <name>`, and `CI: none` for a project without CI, whose merge proof is then `mise run check` exit 0 in the PR's Evidence. | every step but Gates |
| `docs/agents/issue-tracker.md` | the line `Tracker: GitHub (engineering-loop's github.md)`; Components; Never on GitHub; optionally Extra labels and Extra categories | Intent, Spec, Land |
| `docs/agents/coding-standards.md` | Domain facts | Build, Verify |

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
| Build | commits on the branch, with the gate green | the worker role |
| Review | findings with path, cost and repro, then the verdict lines | `code-review`, run by the verifier |
| Land | the PR body | `pr` |

Whatever the practice, the issue and the board hold the state, the gate runs, the
verifier is from the other model family, and the loop merges. A practice skill's own
merging or state-keeping is overridden, because two writers of one state drift apart.

### Approvals and proof

The coordinator approves each point itself with
`python3 scripts/gate.py approve <spec|plan|merge> <issue or PR> --by coordinator`: the
spec once it meets its contract, the plan once it covers the spec, the merge once the
verifier's verdict is triaged with no core finding open and the gate is green. The
verifier only gives the verdict, which `python3 scripts/gate.py verdict <pr> <report>`
posts on the PR. Each approval is a comment the gate reads, tied to the spec's text or
the head commit, so a later edit or push needs approving again, plus the
`approved:<point>` label. `mise run gate build` before building and `mise run gate merge`
before merging check every proof (`scripts/gate.py` lists them).

loop.md § Approvals adds a person's approval, never in place of the loop's: one rule per
line, `<point>: <condition>`, such as `spec: size:L or larger, or component billing`. The
condition is judged on what the issue carries (size, component, category), the paths the
PR touches (merge only: a spec or plan comes before the change, so there the loop judges a
path), or the kind of change; `always` matches everything. When a rule matches,
`approve` leaves the label off, adds `needs-owner`, and you stop: a person approves by
adding `approved:<point>`, or by saying so in the session, and then you run `approve`
with `--by owner`. A condition `gate.py` can't read is yours alone to judge. A rule GitHub
can enforce, such as a required review or a code owner, belongs in branch protection or
`CODEOWNERS`, which the loop obeys and never overrides.

## Roles

- **Coordinator** ([coordinator.md](coordinator.md)): takes a request to a merged PR and
  runs every step above.
- **Worker** ([worker.md](worker.md)): implements a piece of the spec, or a list of
  findings, on its own branch. The coordinator follows it too when it builds itself.
- **Verifier** ([verifier.md](verifier.md)): reviews the PR, drives its instance, and
  leaves the tree as it found it.

Agents are started, messaged, listed and closed through one backend. The developer picks
it with the line `Orchestration backend: <name>` in their personal instructions; a pin
in loop.md wins, and no line means native: [orchestration/native.md](orchestration/native.md),
[orchestration/omnigent.md](orchestration/omnigent.md) or
[orchestration/herdr-link.md](orchestration/herdr-link.md). Delegate through the backend
you are actually in. Inside a worker or verifier, review angles run as native subagents,
never as full harness sessions.

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
- **One concern per PR.** A change the spec's diff doesn't need (agent config, a skill,
  CI, tooling, an unrelated fix) gets its own PR from a freshly fetched `origin/main`, so
  it can be reviewed and reverted alone. A change that needs another unmerged branch
  stacks on it and rebases onto `origin/main` once that lands. Before starting a fix,
  look for one in flight on the board's `Build` column and in open PRs: use it, and don't
  pause other work waiting for it.
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
  the ledger is updated; it writes the PR's evidence and the merge approval. The PR merges
  when `mise run gate merge <pr>` then exits 0 on the head that lands (the reviewed head,
  plus only what `coordinator.md` steps 7 and 8 exempt from a further pass). Nothing else
  needs authorising, except an owner who asked to see the change first: then hold the
  merge and give them the link and what to click.

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

Everything real the PR leaves unfixed is filed as an issue before the report: each
ledger entry, and anything found outside the spec's diff, such as a bug, a flaky test or
a problem only the owner can fix (`needs-owner`). Each states problem, cause, fix and
acceptance. A rejected finding is not real, so it gets no issue.

## The cap

Pass 1 reviews the PR's full diff; passes 2 and 3 review the diff since the previous
report and rerun its repros. After pass 3, fix the open core items and check them with
the verifier's repro files, ledger the edge items, reject the theoretical ones, and land.
The one stop: a core item still open after pass 3 means the fix keeps regressing, so it
goes to the owner as a question about the design, not a pass 4.
