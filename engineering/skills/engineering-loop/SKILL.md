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
owner asks for that change, and the PR body says so. Where loop.md allows an opt-out, a
developer whose personal instructions hold the line `Engineering loop: off` works outside
it (Approvals and proof); no step runs for their changes.

| Step | Prevents |
|---|---|
| **Intent.** File the request as an issue; read it and the code it touches; ask the owner only at a fork, or park the issue for them. | building the wrong thing |
| **Spec.** Written into the intent's issue for the owner, then approved (`approved:spec`, the ready state); the PR closes it, or implements it where the owner signs it off. | a decision the owner never saw |
| **Build.** Workers, or the lead when delegating costs more than it saves, always under the worker's rules. | nothing: the one step that scales |
| **Gates.** `mise run check` before every push, its test part behind a host gate slot that exports `GATE_JOBS` (Rules, One heavy gate per host slot); GitHub runs every `check:` part. | a broken change |
| **Proof.** On the PR branch before review, then on the owner's instance after landing: each new result against a reference the code did not produce. | works in tests, not in use |
| **Verify.** A fresh verifier, of the other model family where one is available, up to the cap (The cap). | the author's blind spots |
| **Land**, clean up everything the run created, then report. | a disk full of finished runs |

## What the project states

The loop never names a project's tools. Each step reads a section of one of these
(below, "loop.md § Worktree" means that file's `## Worktree`), and a missing fact is a
question for the owner, not a guess:

| Where | Sections | Read at |
|---|---|---|
| mise tasks (what each does is its `description`: `mise tasks ls`) | when the loop runs them: `test:changed` while iterating, `check` before every push, `loop:approvals <build\|merge> [pr]` before building and before merging, `loop:land <pr>` to merge, `setup:dev` on a fresh checkout | Build, Gates, Land |
| `docs/agents/loop.md` | Settings (the block `approvals.py` reads, below); Owner; Proof on a branch (bring an instance up, tell it is up, read its log, a step to rerun after a schema or build change); Acceptance references, in order; Approvals (the owner's reasons for the settings, in words); Risk criteria (optional, the project's own, in words, which the verifier reads); In use (how to judge a finding); Worktree (create and tear down); Ledger (its path); Verifier checklist. Optional lines `Orchestration backend: <name>` (a pin), `OMP worker profile: <name>`, `Worker model: <tier> for <condition>` (Models) and `Cloud worker: <agent>, gate <task>` for a project whose workers run in cloud sessions (Cloud worker), which agents read. | every step but Gates |
| `docs/agents/issue-tracker.md` | the line `Tracker: GitHub (engineering-loop's github.md)`; Settings (the block `approvals.py`, `labels.py` and `board.py` read, below); Never on GitHub | Intent, Spec, Land |
| `docs/agents/coding-standards.md` | Domain facts | Build, Verify |

### Settings

loop.md opens with its settings, a fenced `yaml` block under `## Settings`, which
`approvals.py` reads; the prose below it is for people and agents: why a path is critical,
how to judge a finding, the risk criteria in words. The block is YAML because a person
reads and edits it by hand as `key: value` under section names, a list one item per line,
and it is typed (a boolean, a number and a list are each their own kind, so none is a
string the reader guesses at). A string needs no quotes unless YAML would read it otherwise:
one that starts with `*`, `&`, `!` or `[`, holds `: ` or ` #`, or reads as another type.
YAML 1.1, which PyYAML follows, reads `yes`, `no`, `on` and `off` as booleans and `1.10` as
the number 1.1, so `approvals.py` matches each value's type exactly and refuses, naming the
key, a value or name YAML read as something else: quote it. A value names a thing (a label,
a glob, a skill, a branch, a kind of spec), never a rule in words: which specs the policy
approves is a list of kinds, not a phrase such as `auto unless risk` whose meaning lives in
the reader, so a person reads the policy off the block and may name any part of it.
`approvals.py` refuses, naming the key, a section or key it doesn't know and a value of the
wrong type, and refuses a loop.md without the block, so a mistyped setting is never read as
a rule nobody wrote.

The scripts read the block with PyYAML, the one package they need beyond the standard
library. Each declares it inline (PEP 723), so `uv run scripts/approvals.py` installs it
into uv's cache on first use and nothing is installed by hand; uv comes with the project's
mise. Run with a bare `python3` that lacks PyYAML, a script exits with one line saying to
run it with `uv run`. They need Python 3.9 or later. Every key is optional:

```yaml
spec:
  # specs approved by policy, with no owner record; any other waits for the owner.
  # `auto: true` approves every spec, and the risk rule then holds the spec, not the merge
  auto:
    - bug
    - follow-up
    - sub-issue

loop:
  cap: 3
  ci: false
  local_ci_env:
    - GATE_TIER
  opt_out: true

practice:
  plan: writing-plans

risk:
  verifier: true
  labels:
    - size:L
    - size:XL
    - area:billing
  paths:
    - .github/**
    - CODEOWNERS

plan:
  labels:
    - size:XL

signoff:
  labels:
    - area:ios

bot:
  dependabot[bot]:
    paths:
      - uv.lock
      - "**/package.json"   # quoted: a leading * is a YAML alias

land:
  signed_squash_to: main
  allowed_signers: ~/.config/git/allowed_signers
```

| Section | Key | Value | Without it |
|---|---|---|---|
| `spec` | `auto` | a list of `bug`, `follow-up` and `sub-issue`, or `true` for every spec (Approvals and proof) | every spec waits for the owner |
| `loop` | `cap` | a whole number (The cap) | the default |
| | `ci` | `false` for a project without CI, whose merge proof is then `uv run scripts/approvals.py local-ci <pr>` (its docstring says what it records) | `true` |
| | `local_ci_env` | the environment variables that local check reads (Adopting the loop) | none |
| | `opt_out` | `true` where a person may work outside the loop (Approvals and proof) | `false` |
| `practice` | `intent`, `spec`, `plan`, `build`, `review`, `land` | the skill that fills that stage (Practice) | the stage's default |
| `risk`, `plan`, `signoff` | `always` (`true` or `false`), `labels`, `paths`, and in `risk` `verifier` | a rule (Approvals and proof); `plan` has no `paths`, since a plan comes before the change | no rule |
| `bot.<login>` | `paths` | a bot whose PR needs no verifier review (Approvals and proof) | every PR needs one |
| `land` | `signed_squash_to`, `allowed_signers`, both | for a repo that trusts only commits its maintainers sign, the branch and the allowed signers file: `land` then squashes and signs the PR in the checkout instead of merging it on GitHub (`approvals.py`'s docstring says how) | GitHub merges |

issue-tracker.md holds its label and board facts in a block of the same form under its own
`## Settings`, read by `approvals.py` (`label_names`), `labels.py` and `board.py`, refused the
same way; its Never on GitHub stays prose. Each section's values are strings:

```yaml
components:
  # a component, bare or in full: its label's description
  billing: invoices and payment runs.

categories:
  ops: runbooks and alerts.

labels:
  customer-reported: filed from a support ticket.

renames:
  # old label: new label
  frontend: area:web

board:
  # loop column: the board's column
  Build: In progress
```

| Section | Key: value | Without it |
|---|---|---|
| `components` | a component (`billing` or `area:billing`): its description | no `area:` label |
| `categories` | an extra category (`ops` or `kind:ops`): its description | the loop's categories only |
| `labels` | any other label, in full: its description | none |
| `renames` | an old label name: its new one (issues.md, Labels) | the loop's own renames only |
| `board` | a loop column: the board's column (github.md, Board) | each column keeps its own name |

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
  hold a merge as pending), passes its job's check run id in the env of the step that runs the check
  (`job` is allowed in a step's env, not the job's):

  ```yaml
  - env:
      APPROVALS_CHECK_RUN_ID: ${{ job.check_run_id }}
    run: mise run ci:approvals
  ```

  so the check skips that job and no other (without it, in Actions, the check holds), runs again when CI completes, posts success on a merge-queue
  commit, and removes `approved:merge` on a push;
- `.github/check-paths.yml`: each part's path filter;
- the test runner's retry of a failed test, once (Rules for every role, Flaky tests);
- `.github/rulesets/main.json`: a ruleset named `loop-merge-queue` on main, with a squash
  merge queue, requiring exactly two checks, `check` and `loop:approvals`. A repo that can't
  have a merge queue (one a user owns) gets the same ruleset with squash merges and no
  queue, and `land` merges its PRs directly or by auto-merge. Nothing then tests a PR on
  top of main unless the ruleset requires an up-to-date branch, the project's choice: each
  PR behind main costs a merge, a gate run and a verifier pass, and without it a break on
  main is reverted first (Rules for every role, Revert first). A private repo on GitHub's
  free plan has no rulesets, branch protection or auto-merge, so the ruleset can't be
  applied: `land` reads no required checks there, merges directly once its proofs hold, and
  says GitHub enforces nothing, since its proofs are the only gate. `mise run
  setup:github` applies it; GitHub layers it on top of the repo's own rulesets, which it
  leaves untouched, and reverting deletes only it. `setup:github` also syncs the repo's
  labels with `scripts/labels.py` (github.md, Labels).

Hooks are git hooks, installed by `mise run setup:dev`; no check runs from a coding agent's
harness hook. A commit runs the `lint:` tasks on the staged files, and a push runs
`test:changed` and `check:secrets`. The proofs stay off the push, because a push is
reversible and a draft can't merge: `loop:approvals build` runs when the branch is cut, and
`loop:approvals merge` on ready PRs in CI.

A PR stays a draft until no core finding is open (Review trail on the PR), so CI skips its
jobs on draft PRs (`if: ${{ !github.event.pull_request.draft }}` on each job) and lists
`ready_for_review` in its `pull_request` types, so marking a PR ready starts them.
Merge-queue (`merge_group`) and push runs have no draft and run as before. While a PR is a
draft, `mise run check` before each push is its check. With `ci: false` in loop.md, the
check on a head you push for review is `uv run scripts/approvals.py local-ci --record`
instead, committed and clean: it runs the merge check, `mise run check:all`, and records
the pass by commit in the clone's git dir, so `local-ci <pr>` at landing posts that pass
for the same head, command and environment rather than running the check again. A project
whose check reads environment variables (a tier, a scope) names them in loop.md's
`local_ci_env`: without it a pass recorded under one tier stands in for another, and the
posted comment names those values.

[coding-standards.md](coding-standards.md) is the generic half of the standards, read
with the project's. Issue states, categories, sizes and board columns are the method's,
in [issues.md](issues.md), so every project's board looks the same; [github.md](github.md)
does them on GitHub. A
`scripts/` path is relative to this skill's folder; run it from the worktree with
`python3` (standard library only), except `scripts/browse.py`, which needs Playwright and so
runs with `uv run`: it renders a web UI headless, signed in to an Omnigent server when
asked, and screenshots it (worker.md, Report; its docstring has the flags).

### Practice

loop.md's `practice` names the skill that fills a stage, one key each, such as
`spec: brainstorming`; a stage it does not name runs its default. Either way the stage
produces what this table says:

| Stage | Must produce | Default skill |
|---|---|---|
| Intent | open questions settled, or asked in the issue | `grilling` |
| Spec | the spec in the issue, or linked from it, with acceptance examples and the reference each checks against | `to-spec` |
| Plan, only when loop.md's `practice` names a `plan` skill | ordered slices, each with its check, as a `## Plan` comment on the issue | none |
| Build | commits on the branch, with `check` green | the worker role |
| Review | findings with path, cost and repro, then the verdict lines | `code-review`, run by the verifier |
| Land | the PR body | `pr` |

Whatever the practice, the issue and the board hold the state, the gates run, the
verifier is a fresh session (Independent verification), and the loop merges. A practice skill's own
merging or state-keeping is overridden, because two writers of one state drift apart.

### Approvals and proof

Only people approve: the owner, or a teammate where loop.md asks for one. No agent writes
an approval record, since an agent approving its own work is no approval; where nobody
was asked, the authority is the owner's standing policy in loop.md's settings, which
`approvals.py` evaluates from the evidence on GitHub. A spec or plan approval is a comment
`uv run scripts/approvals.py approve <spec|plan> <issue> --by owner` writes on the
owner's word, tied to the spec's or plan's last edit as GitHub's edit history shows it, so
a later edit needs approving again, plus the `approved:<point>` label. A re-approval says
what changed and minimizes the records it supersedes as outdated. The verifier only gives
the verdict, which `uv run scripts/approvals.py verdict <pr> <report>` posts as a PR
review on the commit it reviewed.

loop.md's settings hold the policy (Settings):

- `spec.auto`, a list, approves by policy, with no record or label, the spec of each
  kind it names: `bug`, a `kind:bug`; `follow-up`, an issue whose body has a `Found while
  #<n>` line (a follow-up an agent raised, Triage); `sub-issue`, a native sub-issue of an
  epic the owner approved (their current record and `approved:spec`), opened by an account
  with write access to the repo. Any other spec, a new epic for one, needs the owner's
  approval; without `auto`, or with `false` or an empty list, every spec does.
- `spec.auto: true` approves every spec by policy, epics included, so the owner reads only the
  critical ones: a spec the `risk` rule matches, or one opened by an account without write
  access, since anyone who can open an issue would otherwise approve their own, waits for
  the owner's record and `approved:spec`. The risk rule then holds the spec instead of the
  merge: the owner decides while the change is still cheap, and its merge is automatic
  like any other. `approvals.py` judges the rule on the labels of the issue and the PR
  and the PR's files, at `check build` the files pushed so far, so a file the spec didn't
  foresee still reaches the owner before the merge. `auto: true` moves the rule rather than
  a key of its own, since with every spec approved by policy the spec is the one point the
  owner sees a risky change before it is built, and holding the merge as well would ask
  them twice.
- The gates are the merge approval of a change that is not high risk.
- `risk` says what is high risk here, and any one of its terms matching holds: `labels`,
  matched exactly on the PR and its issues as GitHub names them (`size:L` and `size:XL`
  for large or larger, `area:billing`, `kind:bug`); `paths`, globs matched on the PR's
  files; `always: true`; and `verifier: true`. `approvals.py` reads the keys, never the
  words, so a path such as `docs/verifier.md` is only a path. Paths it can't judge, past
  the one page of files it reads, hold, since nothing else would enforce them.
  The `verifier` term holds when the verifier judges the change high: the newest
  pass on the head, by a trusted account, says `Risk: high`, any word but `low`, or has no
  `Risk:` line (verifier.md). Paths beside it hold whatever the verifier says, so
  `verifier: true` with `paths` `.github/**` and `CODEOWNERS` lets the verifier decide and
  keeps those files the owner's. The gate judges it at the merge, under `auto: true` too,
  since the verdict comes after the build, and quotes the verdict. A `risk:high` it added
  for that term comes off when a later pass says `Risk: low`; one added again after it
  stays. loop.md § Risk criteria adds the project's own criteria in words, which the
  verifier reads.
- `plan` asks for the owner's approval of a matching plan.
- `bot.<login>`, such as `bot.dependabot[bot]` with `paths` `uv.lock` and
  `pyproject.toml`: a PR that bot opens needs no verifier review when every commit is the
  bot's (its authors, and its committer unless that is no account) and every file it
  changes, none renamed or copied, matches one of its `paths`, since no verifier runs on a
  bot's PR; anything else needs the review as usual. Without the section, every PR needs
  one.
- `signoff`, such as `labels` `area:ios` and `area:watch`: the owner signs off a
  matching change in use after it lands, which no gate can do for them. The rule reads as
  `risk` does, on the labels of the PR and the issue and the PR's files. The spec records the outcome in a line
  `Sign-off: owner` or `Sign-off: none`, and `owner` there asks for it where no rule does.
  The PR links such an issue with `Implements #<n>`, which GitHub does not close, so the
  issue stays open for the sign-off, and every other issue with `Closes #<n>`; `Part of
  #<n>` suits both. `check merge` refuses the wrong keyword. Without a `signoff` section
  no keyword is checked, and `Implements` is a link like `Part of`.

A change is high risk when `risk:high` is on the PR or an issue it closes, a risk rule
matches (unless under `spec.auto: true`, where it held the spec, but for its `verifier` term), or the cap was reached with a blocker or major open (The cap). A high-risk spec
covered by policy is still built and PR'd; its merge waits for the owner's
`approved:merge` label on the PR, asked for once `check` is green on the head: it counts
only when added after that head's push, and a push removes it, so it never covers code the
owner did not see. When the gate infers high risk, it adds `risk:high` to the PR. Otherwise
the merge approval is the gates themselves: every verifier review on the newest pass's
commit satisfied with no blocker or major open, that commit covering the head that lands,
every review thread resolved, no review requesting changes, and the base's required checks
green. A pass counts whichever model family wrote it (Independent verification).

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
them); `merge` exits 3 while it waits for the checks `land` reads or the owner's label, and 1 when
a proof is missing. An agent merges only with `uv run scripts/approvals.py land <pr>` (the
project's `loop:land` task): it runs every merge proof, refuses a head behind or in
conflict with its base, marks a draft ready and waits for the CI that starts, and on a ready
PR merges it pinned to its head, or turns on auto-merge while only required checks are
pending. With `--wait` it is one background command that ends when the PR merges or needs
someone. Never run `gh pr ready` or `gh pr merge` by hand,
because `land` is what refuses a PR whose proof is missing. A repo without
`docs/agents/loop.md` has no rules: `land` there needs each named issue to carry
`approved:spec` and not `needs-owner`, and the PR's own proofs. A rule GitHub can enforce,
such as a required review or a code owner, belongs in branch protection or `CODEOWNERS`,
which the loop obeys and never overrides.

With `opt_out: true` in loop.md, a developer may keep their own PRs out of the
loop, by the line `Engineering loop: off` in their personal instructions and nothing on the
PR. `check merge` then reads a PR with no loop trail (no verifier review, no
`Approved: spec` record or `approved:spec` on an issue it links, no `Reverts #<n>` line,
not an exempt bot PR) as outside the loop: it prints one line saying so and exits 0, so the
`loop:approvals` status is green and the PR's author merges it their usual way, under the
repo's own rules. `land` prints the same line and exits 1, so no agent merges it or turns
auto-merge on for it. Risk rules and `risk:high` hold no PR outside the loop; the project
accepts that by setting it. A spec a policy covers is no trail, since under
`spec.auto: true` every issue is covered. Any trail puts the PR back under every proof. Without
it, a PR with no trail fails the gate.

## Roles

- **Lead** ([lead.md](lead.md)): takes a request to merged PRs, one per story, and
  runs every step above. A session whose brief names no role is the lead, since workers
  and verifiers are given theirs by the brief that starts them.
- **Worker** ([worker.md](worker.md)): implements a piece of the spec, or a list of
  findings, on its own branch. The lead follows it too when it builds itself.
- **Verifier** ([verifier.md](verifier.md)): reviews the PR, drives its instance, and
  leaves the tree as it found it.

Agents are started, messaged, watched and closed with the `orchestrating-agents` skill
(`../orchestrating-agents/SKILL.md`), which picks the backend and holds its rules, reports
and questions as files among them. Inside a worker or
verifier, review angles run as native subagents, never as full harness sessions.

## Cloud worker

With the loop.md line `Cloud worker: <agent>, gate <task>`, the lead and the verifier run on
the host and only the workers run in the cloud, as sessions of `<agent>`, a registered
Omnigent agent whose tools run in a cloud VM, which the lead starts. Without the line nothing
in this section applies and every role file reads as written. The split takes coding,
compiling and unit tests off the host. What stays there is what the VM can't do: every
`approvals.py` call and every thread resolution, since GitHub's GraphQL API answers 403 in the
VM; the signed land, since the VM holds no key; a verifier of the other family, since Codex
has no cloud bridge; anything that needs a device, a simulator, an emulator, a browser login
or the owner's private network.

- **Who does what.** The lead runs intent, spec, the branch and draft PR, `check build`,
  triage, the fetch and merge (or fast-forward) of each worker's reported branch into the
  PR branch, the full gate (`mise run
  check`, or `local-ci --record` with `ci: false`), the instance, the verdict's post, thread
  resolution, `land` and acceptance. The worker codes and compiles, runs `mise run <task>`,
  the light gate (what the VM can run: compile, unit tests, headless web tests on its
  Chromium), before each push, and pushes to the `claude/…` branch its session was given,
  since a cloud session declines any other branch without its own user's permission and a
  peer's brief is not that; no brief names another push target. Its brief names the role
  file by its path in the repo, since the host's worktrees and paths don't exist in the VM. The verifier runs on the host in the lead's worktree, as verifier.md says.
- **The PR is the interface for content.** The code is the worker's pushed branch. Its
  report is one comment on the PR: its branch and head SHA, each light-gate command with its
  exit code, what it left out and why. If the post fails, since the session's proxy-injected
  `GH_TOKEN` can expire 10 to 20 min in, its reply is `UNPOSTED REPORT` and then the body
  verbatim, and the backend's `wait --pr` posts it from the host. orchestrating-agents' `--pr` (its Omnigent backend, Cloud
  workers) has the worker post it and writes it to the report path on the host, so the lead
  reads a file as for any worker. The verdict is the review `approvals.py verdict` posts.
  The verifier names its evidence (screenshots, logs, result bundles) in its report, and the
  lead posts it with the verdict as assets of a prerelease linked from a PR comment, the way
  the `demo` skill posts videos, so the worker fixes a failure from its diagnostics without
  the host.
- **Control flow is the lead's own.** It starts the worker with `run --pr --keep` (from a
  host without the worker's harness, `start --top-level --host <host> --pr`, then
  `wait --pr --keep`), follows its turn end, and sends a fix list or a failing log, naming the
  review or comment to read, to that kept worker with `send --pr` while it is still there,
  since a fresh session is a fresh VM, clone and build and a kept one revives with its clone;
  else as a fresh `run --pr`. Nothing in
  the cloud calls the host, through MCP or otherwise, since such a tool can drop mid-run and
  stall the work, and nothing new watches the PR.
- **Proof.** The worker proves what the VM runs. The full gate's host-only parts (emulator,
  simulator and device tests), the instance, the acceptance examples and the evidence are
  the lead's and the verifier's, on the host. A failure there costs a round trip (relay,
  fix, push) instead of a local rerun, so it goes back with its diagnostics on the PR.
- **Host builds.** The host compiles at most once per verifier pass, the full gate and the
  instance build together, plus at most one compile for the verifier's mutation check, since
  taking builds off the host is the split's point; a worker's iterations compile only in the
  cloud.
- **Nothing on GitHub names a host, a path or a session**: not the report, the verdict, the
  evidence or a brief's text quoted there, since a public repo publishes them.
- **Auto-fix stays off on loop PRs** (a cloud session that subscribes to its own PR), since it
  pushes fixes and replies on threads by its own judgment, which is the lead's triage, and the
  lead already briefs the worker on each fix.

## Rules for every role

- **The owner is on the loop, not in it.** They read specs, never code: gates, tests and
  the verifier are the review. Ask them only at a fork that changes what gets built,
  before something hard to undo (deploy, publish, send, spend), for a credential only
  they hold, or at an approval loop.md's settings require. A technical fork they can't judge is your call. Run commands yourself; when
  a guard blocks one, ask once for a scoped approval, then propose a narrow allow rule,
  never an interpreter-wide one. While they are away, make the reversible decisions, log
  each in one decision-log issue, wait out a usage limit and resume, and leave a handoff
  (`handoff` skill) when finished or stuck. Never idle: schedule a time-gated check and
  keep working.
- **Owner steps park, they don't block.** A step only the owner can unblock (a GUI
  dialog, a locked screen, a device, a permission prompt or classifier denial, a
  credential, an approval link that expires) is stopped at its first sign, so a hang
  becomes a failure, and whatever it holds (a gate slot, a lock, an instance) is released.
  Comment `Owner step: <the exact action>, unblocks <what>` on its issue or PR, add
  `needs-owner`, add a checklist line to the decision-log issue so the owner clears every
  step in one sitting, and move to the next item; ask once, since a retry while they are
  away fails the same way. Before a long or unattended run, try once each owner-only
  prerequisite the queued items need (loop.md § Proof on a branch, the specs' acceptance)
  while the owner can still answer, and check such a precondition before a heavy step
  takes a slot.
- **One heavy gate per host slot.** Leads on one host share its cores, and gates run at
  once slow every one of them several times over and starve new sessions of the capacity
  to start. So the project's test part runs behind a host-wide slot that every worktree
  shares: the template's `scripts/gate-slot` (`GATE_SLOTS` slots, default 1; a lock frees
  itself however the run exits), or, in a project without it, a lock on the same file,
  `${XDG_CACHE_HOME:-~/.cache}/engineering-loop/gate.1.lock`, around its heavy check. A parallel runner takes the
  `GATE_JOBS` it exports (the cores free at start), never `-n auto` or a fixed count.
  `test:changed` while iterating and the lint parts stay outside the slot.
- **Independent verification.** The verifier is a fresh session, never the author's. It
  is of the other model family when that family is installed, within quota and the
  backend can start it (native starts only its own harness's subagents; Omnigent starts
  either), since it misses different things; otherwise, as for a user with one family installed, a fresh
  session of the same family is the normal path. The PR body names which ran
  (`verifier: same family` for the latter). A PR with code from both families gets a
  verifier for each family's changes where both are available, integration edits
  included; each writes its own report, and the cap counts rounds they share. The family
  is a preference the lead follows and a record, not a gate: the verifier names it
  in its review's heading, and the merge gate checks only that the newest pass on the head
  is satisfied, whichever family wrote it, since the heading is the verifier's own word
  and proves nothing the gate could hold it to. A brief never says who wrote the code or
  why the verifier shares its family: that biases the review. A verifier reviews a pushed
  PR head only, never an untracked helper script, a scratch wrapper or a mid-edit
  snapshot, since a review of what will not land proves nothing about what will: a helper
  worth reviewing is committed on a PR, and the cap counts PR passes only.
- **Reports are files**, sent as a path to whoever started the agent
  (orchestrating-agents, Reports are files).
- **Evidence, not claims.** Report each step's real exit code: a chain's status is its
  last command's. Prove a tooling or config change with a live round trip where it runs,
  and "can't" with a real call. Before saying done, check each item of the owner's
  feedback against what shipped, taking their example as one case of a class.
- **Stop on repeated failure.** Three tool calls in a row failing with the same error,
  even different calls, mean stop and report yourself blocked with the error line. That
  includes a permission classifier that fails closed because its provider is down: every
  retry is a full-context turn.
- **Flaky tests.** A project's `check` retries a failed test once, with its runner's own
  retry option, and prints each test that passed only on the retry; the gate is then green.
  Without one, rerun only the failed tests once, then only the parts of `check` the failure
  stopped, never the whole gate, whose minutes each flake would otherwise cost again; all
  green, the gate is green, and the report gives each command with its exit code. A
  `ci: false` project needs the retry option, since its `local-ci` record runs the whole
  `check`. Each test that passed on the retry has one open
  `kind:bug` issue titled `Flaky: <test id>`: search the open issues for the id before
  filing, and comment each occurrence on it (head SHA, PR, failure line), so two leads find
  the same issue and its comments count the occurrences. The third occurrence gets a PR
  from main that skips the test in the blocking gate, citing the issue, which stays open
  for the fix. A test red on both tries is a real failure: run it on main before blaming
  the PR.
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
  on it, or wait for it to land and start from main. Before filing an issue or starting a
  fix, search the open issues and PRs of this repo, and of the repo that owns the cause,
  for the symptom (the test id, the error line, the file), since the board's `Build`
  column misses an issue filed an hour ago and agents sharing one account share an
  assignee: comment your evidence on what you find, use it, and don't pause other work
  waiting for it; whoever filed first owns it. An issue an open PR links is taken, so
  the lead opens its draft PR when it cuts the branch (lead.md step 3). A PR another lead
  opened is taken over only on the word of that lead or of whoever started the leads,
  recorded in the PR thread so other leads see the new owner, never because it looks
  idle, since an idle PR may be waiting on CI or on an answer its lead still owns.
- **Stacks are one deep.** Stacking on an unmerged branch is the exception for when
  waiting isn't possible, and only on a PR already in Land (verdict triaged, waiting for
  CI), because a base still in review changes under its stack and every change cascades.
  Its owner moves the stacked PR onto main the moment its base lands, and it lands itself
  with its own `Closes` or `Implements`. Anything else waits, or builds
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
  the lead resolves a deferred finding `WONT_FIX`, replying with its triage and the
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
- **Models.** Never pick a model: every agent runs on its harness's configured default,
  which the owner sets, unless the owner names one for a task or loop.md's `Worker model:
  <tier> for <condition>` line names a tier for a worker whose issue matches the condition
  (on the issue's labels), so the choice and its reason sit in one file the
  owner can change. The tier is `top`, `mid` or `small` (Claude's Opus, Sonnet, Haiku;
  Codex's Sol, Terra, Luna; each family names its own), so one line holds for every family
  and outlives a release. A family's frontier model above `top` (Claude's Fable, Codex's
  Astra) is no tier and never runs, because it costs several times `top`. Resolve the tier
  at launch from the newest generation of the family's tier models only: its model of that
  tier, else its closest higher tier (its highest when none is higher), never an older
  generation's model, which the family has already superseded. A lead that can't read the
  family's current lineup (the backend's Model section) leaves the default. A launch that fails on
  capacity is retried later on the same model (the backend's Model section). When one
  family is out of quota, continue on the other in a fresh session briefed from the run's
  notes, the spec and the PR, never a fork of the old session, since every turn of a fork
  re-reads the whole transcript it copied; revive a stuck or interrupted agent rather than
  restart it.
- **Turns.** A turn the owner reads (not a child's path-only reply) ends with `DONE`,
  `STILL WORKING` or `USER NEEDED`; a `USER NEEDED` line wins over an earlier `DONE`, since an ask
  after it still needs its answer. A status reply opens with a tl;dr: the loop step with
  links to the spec, the PR and the instance, what is blocked, what the owner must do (or
  "nothing"), and each open question restated. Past about 150K tokens of context, at a
  natural break, offer the owner a ready compact command with the summary it should keep.
- **Landing.** Land starts once the last verdict is triaged with no core finding open and
  the ledger is updated; it writes the PR's evidence and runs `approvals.py land <pr> --wait`,
  which marks it ready and merges it, or turns on auto-merge and waits for the merge. The PR merges only when the newest
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
any, what would make it matter, and its issue. The lead writes it during triage,
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
- **Its cause is in another repo** (a shared skill, a tool, a project template): two
  issues. In the repo that owns the cause, a generic one: problem, cause, fix and
  acceptance, the case described so it holds anywhere; when that repo is more public than
  this one, it names none of this project's names, products, customers, tickets or links.
  Here, one for this project's side: what happened, the plan (adopting the fix, a
  workaround meanwhile), and a link to the generic issue. Links point from the less
  public repo to the more public one, never back.

A rejected finding is not real, so it gets no issue.

## The cap

The cap is 5 passes, unless the project's loop.md sets its own with `cap` under `loop` in its settings.
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
