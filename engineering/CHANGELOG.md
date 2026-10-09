# Changelog

## Unreleased

A bot's lock- or manifest-only PR merges without a verifier review (#106).

- loop.md § Approvals takes `bot: <login> <condition>`, such as
  `bot: dependabot[bot] path uv.lock or path pyproject.toml`. `check merge` and `land`
  waive the verifier review for a PR that bot opened when every file it changes matches
  the condition on its path and every commit is the bot's (authors, and a committer that is the bot or no account);
  any other file, a renamed or copied one, or a person's commit or rebase needs the review as usual. Without the line, no PR is
  exempt. The login matches with or without `[bot]`, and only a bot account.
- The verifier resolves no review thread.
- The merge gate does not enforce reviewer family (#118): the verifier names its family
  in the review heading for the record, and the gate checks only that the newest pass on
  the head is satisfied, whichever family wrote it. The coordinator still prefers a
  verifier of the other family when it is installed and within quota; otherwise a fresh
  same-family session is the normal path, and the PR body names which ran.
- An unreadable `cap:` line in loop.md, such as `- cap: 3 passes`, is refused at the
  start of `check` and `land` (#119): the refusal is the only line printed, and `land`
  marks no draft ready. Before, a PR a risk rule or `risk:high` already held never read
  the cap, so `check merge` printed its proofs and `land` marked the draft ready.
- The cap hold (0.14.0) applies when a verifier review at the cap or later left a
  blocker or major open, and also when it says `SATISFIED: no` with none open.

## 0.16.0 - 2026-10-09

Labels as code: `area:` and `kind:` labels, synced with in-place renames, and the
assignee says whose an issue is (#103).

- Categories are `kind:bug`, `kind:enhancement`, `kind:chore` and `kind:documentation`;
  `documentation` is renamed to `kind:documentation`. A component's label is `area:<name>`, an extra category's
  `kind:<name>`. `approvals.py` reads only these names, and loop.md conditions
  (`component billing`, `category bug`) match them. Migration, since the old names no
  longer count: upgrade the pack, run `python3 scripts/labels.py --dry-run` from the
  installed engineering-loop skill in the project's checkout, then without the flag, then
  rerun `approvals.py check`. `setup:github` runs the sync only once project-templates
  wires it in, a follow-up.
- `scripts/labels.py [--dry-run]` syncs the repo's labels with the loop's set and
  `docs/agents/issue-tracker.md`: renames in place (the loop's map, the tracker's new
  `## Renamed labels`, and each bare component name), creates and updates the listed
  labels, deletes an unlisted one only when no issue or PR carries it, and never renames,
  folds or deletes Dependabot's or one whose name has a comma.
- `approvals.py check build` refuses an issue assigned to anyone but its spec's approver;
  once every build proof holds it assigns the approver where no one is, and the PR its
  issue's assignees, recording each assignment in a comment first. `approvals.py release <issue>` removes, on parking or dropping, only
  an assignee the loop added.

## 0.15.0 - 2026-10-09

Approvals come only from people, and risk is defined in one place (#121).

- `approvals.py approve` takes only `--by owner`: a person's record, written on their
  word. `check` and `land` no longer ask for a coordinator record, and an agent's earlier
  record approves nothing. Without a loop.md policy line every spec needs the owner's
  current record and `approved:spec`; a plan needs them only where a `plan:` rule asks.
- loop.md § Approvals `spec: auto unless risk` approves by policy, with no record or
  label, the spec of a `bug`, of an issue with a `Found while #<n>` line, or of a native
  sub-issue of an epic with the owner's current approval, opened by an account whose
  collaborator permission is admin, maintain or write. `needs-owner` still blocks.
- `risk: <condition>` lines define high risk, with the conditions `merge:` rules had. A
  change is high risk when `risk:high` is on the PR or an issue it closes, a risk rule
  matches, or the cap was reached with a core finding open; only then does the merge wait
  for the owner's `approved:merge`, and the wait line says why. `merge: auto unless risk`
  states the default. When the gate infers high risk, `check merge` and `land` add
  `risk:high` to the PR; a failure to add it is reported, never fatal.
- Migration: a `merge: <condition>` line reads as a `risk:` rule until the project
  rewrites it, so its paths still hold merges for the owner. A `spec: <condition>` line
  reads as one only beside `spec: auto unless risk`; without that line the owner approves
  every spec already, so a legacy `spec: always` holds no merge.

## 0.14.0 - 2026-10-09

- `scripts/gate.py` and `approvals.py record-check`, the old names kept through 0.13, are gone:
  run `approvals.py` and `approvals.py local-ci`.
- No fix lands without review (#116). `approvals.py land` merges only a head with a
  satisfied verifier review on that exact commit: any commit after the verdict, a merge of
  main included, needs a verifier pass of its own. A head that only took in main's changes
  to other files is no longer covered.
- The cap is defined once, in SKILL.md § The cap: 5 passes by default, or a project's own
  through a loop.md line `cap: <n>`, which `approvals.py` reads too. When a review at the
  cap or later left a blocker or major open, the owner decides: a fix and one pass past
  the cap, scoped to the open items, or leaving the code untouched. `land` holds such a PR
  for the owner's `approved:merge` label, added after the head's push. When the cap's last
  pass leaves only minor or edge findings, they go to the ledger and an issue, and the PR
  lands with no owner stop.

## 0.13.1 - 2026-10-09

- `approvals.py land` reruns a stale `loop:approvals`. Resolving a review thread starts no
  GitHub Actions workflow, so the FAILURE the approvals workflow posted while a thread was
  open stayed on the head and `land` exited 3 for good. When every proof holds and that
  status is the only required check that is red, `land` reruns the Actions run its target URL
  names (`gh run rerun`) and exits 3. A run still in progress is waited on, and a status naming
  no run of this repo is reported; neither is rerun.

## 0.13.0 - 2026-10-09

The merge contract's landing (kzarzycki/agent-skills#108, #106) and the launcher's resilience (#93).

- `approvals.py land <pr>` is the one way an agent lands a PR. It refuses (exit 1, the PR
  untouched) on a missing proof; marks a draft ready and waits (exit 3: run it again once CI
  starts); then merges at the head (`gh pr merge --squash --match-head-commit`), or turns on
  auto-merge pinned to the head while only required checks are pending. Required checks are
  the base's rulesets and branch protection; a base requiring none needs every check green,
  and a draft's skipped run is no result.
- The gates are the merge approval. A loop.md § Approvals `merge:` rule (same conditions as
  `spec:`, plus `path <glob>` read from the PR's files) asks for the owner's `approved:merge`;
  a `merge:` condition the gate can't read asks for it too. With no rule, no label is needed.
  A project that wants the 0.12.0 behaviour, a label on every merge, writes `- merge: always`.
- The verifier's verdict is a GitHub PR review: `approvals.py verdict <pr> <report>` posts the
  report on its reviewed `Head:` with one inline thread per finding, and refuses a report it
  can't parse. `check merge` and `land` need the newest pass's reviews on that commit
  satisfied with 0 blocker and 0 major, on the head or with only a main merge since that
  touches no PR file; no unresolved review thread; and no person's latest
  `CHANGES_REQUESTED`. A verdict comment no longer counts. Only a review by the PR's author
  or the viewer counts.
- A repo without `docs/agents/loop.md` has no rules: each issue the PR names needs
  `approved:spec` and no `needs-owner`. The loop's files are read from the checkout's top
  level, so a run from a subdirectory reads the same rules.
- The loop docs: land only through `approvals.py land`; every fix after a verdict, a note's
  included, gets a delta pass, and after pass 3 a delta check; who replies on and resolves
  which review thread (`ADDRESSED`, `WONT_FIX`, `INVALID`).
- `gate.py` and `record-check` stay as aliases until 0.14.0, which removes them.
- `omnigent_agent.py watch` exits as soon as a session ends a turn, blocks on a prompt or
  fails (#97); worktrees nest inside the project and the agent that starts them (#101); the
  launcher retries idempotent reads, never doubles a timed-out create and nudges a turn that
  ended without its report (#107); `send` revives a reaped session in place (#111).

## 0.12.0 - 2026-10-07

The merge contract's agent-skills part (kzarzycki/agent-skills#102, #104).

- `scripts/gate.py` is `scripts/approvals.py`, with the subcommands `check`, `approve`,
  `verdict` and `local-ci`. `local-ci` (formerly `record-check`) runs `mise run check:all` on a
  clean checkout at the PR head for a `CI: none` repo; a record of the old `mise run check`
  still counts. `gate.py` and `record-check` stay for this release as aliases with the same
  output and exit code.
- `check merge` reads one check, the aggregate `check` on the head, counting only its newest
  run per workflow, so a red advisory check or a run cancelled by a newer green one no longer
  blocks (replaces #76).
- The merge approval is the owner's `approved:merge` label, added after the head's push (dated
  by GitHub's repository activity) and still present; the `Approved: merge` record and
  `approve merge` are gone, and a loop.md `merge:` rule is ignored. `check merge` exits 1 when
  a proof is missing (Evidence, the verdict, an approved spec) and 3 while it waits for a green
  `check` or the label, which the approvals workflow posts as a `pending` `loop:approvals`
  status. The coordinator asks the owner only once `check` is green, turns on auto-merge with
  `gh pr ready` (`gh pr merge <pr> --auto --squash --match-head-commit <head>`), and deletes
  no remote branch: GitHub deletes the merged head branch.
- `headed()` matches a comment's whole first line, so `## Specification notes` is no `## Spec`.
- `approved:spec` is the ready state and `ready-for-agent` is gone: `check build` needs
  `approved:spec`, a size, a category and a component, and no `needs-owner`. A `wayfinder:`
  ticket needs `approved:spec` in place of `ready-for-agent`. Category, component and size
  names are read through one rule, `label_names`: the loop's fixed set plus
  `docs/agents/issue-tracker.md`.
- `board.py column` prints the later of the issue's board column and the one its labels give,
  so an issue with `approved:spec` reads `Ready`.
- The loop docs use the contract's task names (`check`, `check:all`, `test:changed`,
  `loop:approvals`, `setup:dev`, `setup:github`, `pr:demo`, `agent:sync`) and point at
  `mise tasks ls` for what each does. Main requires exactly `check` and `loop:approvals`;
  hooks are git hooks, and the proofs leave the push. The verification flow: the worker runs
  `test:changed` while iterating and `check` before each push; the PR goes ready once
  `check` passed and the verifier is satisfied; a check red after ready goes back to draft
  and to a worker with the failing log, while the coordinator waits on one
  `gh pr checks --watch --fail-fast`. An epic's stories are filed before its approval is
  asked for, and each has its own approval.

## 0.11.0 - 2026-10-06

- Human review findings on an open PR (`coordinator.md`, Land): each review comment is triaged
  with One concern per PR. A blocker, a major or a bug the PR introduced is fixed on that PR's
  branch; anything else is answered on its thread and waits for the merge. The fixes follow the
  review trail below: the PR goes back to draft, each fix is a pushed commit replied on its
  thread, and the PR is ready again after a verifier pass. No fix cascades down a stack: a merge
  queue tests each PR on top of main, and a stacked PR follows Stacks are one deep.
- Review trail on the PR (`SKILL.md`, `coordinator.md`, `worker.md`, `github.md`): the PR opens
  as a draft with the first push, and each verifier pass is posted as a PR review with one inline
  comment per finding, labelled `Verifier (<family>), pass <n>`, and the verdict in its summary.
  Each fix is its own commit, replied on its thread with the SHA and the thread resolved; a
  deferred finding's reply links its issue. The PR goes ready once no blocker or major is open,
  and is squashed on merge. `github.md` gives the `gh api` calls (review, thread reply,
  `resolveReviewThread`).
- Adopting the loop (`SKILL.md`): a new repo starts from kzarzycki/project-templates with
  Copier (`loop_enabled`); an existing repo copies the rendered CI workflow, `gate.yml`,
  pre-commit and pre-push hooks, mise `check`/`gate`/`merge-queue` tasks and main's ruleset from
  there, so the pack keeps no second copy. CI skips draft PRs and runs on `ready_for_review`;
  merge-queue and push runs are unaffected, and the local pre-push gate checks a draft.
- The merge gate lets an exact revert through without a new spec: a PR whose body says
  `Reverts #<n>`, with #n merged and a diff that is file for file the inverse of #n's (line
  order, file status and modes included), skips the spec proofs and the verifier verdict, and
  `approve merge` records `Verdict: exact revert of #<n>`. It still needs Evidence, green CI and
  the merge approvals. A merge rule's owner check reads the union of the PR's issues' labels, so
  a path rule also holds on a PR that names no issue.

## 0.10.0 - 2026-10-06

- Land small and soon (`SKILL.md`): every PR branches off `origin/main` and merges as soon as
  its gates pass. An epic lands as one PR per sub-issue, each off main, with no epic or
  integration branch; work not yet usable lands unexposed (no entry point, or a flag the user
  docs don't name), and the sub-issue that exposes it comes last.
- Stacks are one deep, and only on a PR already in Land; the stacked PR moves onto main the
  moment its base lands, moved by the coordinator only when it owns that PR (otherwise a
  comment naming the merge SHA asks its owner). A stacked PR keeps its own `Closes`; they are
  copied to the base only when the base contains the stacked work.
- One concern per PR, rewritten: a finding goes on the open PR's branch only when it makes that
  PR wrong or unmergeable; anything else, a satisfied verdict's note included, waits for the
  merge and starts from main. Never push to a PR someone else owns. A process fix that makes
  the open PR wrong follows this rule too, instead of going to a separate PR.
- Revert first: when main goes red after a merge, or a merged change proves wrong in use, the
  first fix is a revert PR off main, and the reverted PR's issues reopen. Accept starts by
  reading main's push run on the merge SHA.
- Waiting: while a PR waits for CI, the coordinator moves other ready items forward.

## 0.9.2 - 2026-10-05

- Epics (`issues.md`): an epic is an issue whose goal is an outcome the owner tracks, with
  its work items as native sub-issues and the `epic` label. Two levels only, so every work
  item shows under its epic on the board. Convert an issue whose spec already states the
  outcome rather than file a new one; the epic closes when its sub-issues are done.
- Triage places what a PR leaves unfixed by one test: would closing the issue without it be
  dishonest? Within the issue's acceptance, the issue stays open and the PR says `Part of #n`.
  Outside it, a new issue with a `Found while #n` line, attached as a sub-issue of the
  originating issue's epic, so follow-ups no longer grow into loose chains.
- A change to an approved spec's scope or acceptance removes `approved:spec` and parks the
  issue with `needs-owner`; a wording fix keeps the label.
- Landing: closing keywords fire only on a PR merged into the default branch, so a stacked
  PR's issues are closed on the PR that reaches it, or by the coordinator. A replacement PR
  carries `Closes` for every issue the replaced one closed.
- `gate.py` reads `Part of #n` as naming the spec, like `Closes #n`, so a PR that leaves its
  spec open still passes the gate.
- `github.md`: setting a parent with `addSubIssue`, after reading the current one, since an
  issue has at most one and a repeated add is refused.

## 0.9.1 - 2026-10-05

- Upstream intake, mattpocock/skills `d81f3a1..24fe0ef` (v1.3.1).
- `ask-matt` (ported): once `/diagnosing-bugs` has fixed a bug, run `/retro` in the same
  session to ask what would have prevented it; a finding that no seam can lock the bug down
  still goes to `/improve-codebase-architecture`.

## 0.9.0 - 2026-10-03

- New owned skill `demo`: record a change a user sees running at the PR's head and post the
  video to the PR. `scripts/post_demo.sh` posts one `## Demo` comment with the videos attached
  (`gh pr comment --attach`), refuses a checkout that is not the PR's head, and minimizes
  earlier demo comments as outdated. One file per recorder, read only for the surface in play:
  VHS for a CLI or TUI, Playwright for a web page, `simctl` for the iOS simulator,
  `screenrecord` for Android. When to record is the project's rule, not the skill's.
- `pr`: Evidence names the demo when one was recorded, or suggests one when the project's
  instructions call for it. A repo PR template's headings win; the sections fit under them.
- `ask-matt` routes `/demo`.

## 0.8.3 - 2026-10-02

- An approval names the spec or plan by its last edit, as GitHub's edit history shows it
  (`Spec: as edited 2026-10-02 14:35:27 UTC`), instead of a 12-character hash a person could
  not check against the text. Any edit still needs approving again. Records written with the
  hash no longer count: an issue approved before this release needs one more approval.
- A re-approval says why: `The spec changed after the last approval, so it was checked
  again.` (the head moved, for a merge). `approve` then minimizes, as outdated, each earlier
  record it supersedes, so the issue shows only the approvals that count. Another approver's
  record of the same version stays open. Minimized comments stay readable, and the gate still
  reads them.
- A merge path rule reads every file a PR changes, not just GraphQL's first 100. Past that page
  the gate lists the files through the REST API, up to GitHub's 3000. Adopting the template
  commits the synced agent files, so the adoption PR alone was refused as "more than 100
  changed files".

## 0.8.2 - 2026-10-02

- Under `CI: none`, the merge proof is a record, not a sentence. `gate.py record-check <pr>` runs
  `mise run check` on a clean checkout at the PR head and posts `Local check passed` with the
  head commit. The merge gate needs that record on the current head. It no longer reads
  `## Evidence` for `mise run check` and `exit 0`. That matching was brittle, and it was not
  tied to the head, so a line written for an earlier commit still passed.
- Instructions are code for the further-pass rule (coordinator step 7). A fix after a satisfied
  verdict skips another verifier pass only when it changes nothing an agent or tool reads. A
  skill, role file, brief, `AGENTS.md`, `docs/agents/` file or prompt needs the pass.

## 0.8.1 - 2026-10-02

- `gate.py` reads a PR's changed files only when a merge rule has a path condition. A PR with
  more than one page of files is refused only then, and at the merge point. Before this, every
  build check refused such a PR, and the pre-push hook refused the very push that would shrink
  it, because the hook reads the PR as GitHub last saw it. `approve merge` now refuses the
  unread page too, instead of judging a path rule on a truncated list.
- A project without CI says so with the line `CI: none` in `docs/agents/loop.md`. Its merge
  proof is then the PR's Evidence naming `mise run check` with exit 0 on the head, in place of
  green CI checks. Projects with CI keep the CI proof.

## 0.8.0 - 2026-10-01

The engineering loop ships as a method any project turns on. No upstream change.

- New owned skill `engineering-loop`: intent, spec, build, gates, proof,
  verify, land, with coordinator, worker and verifier roles, triage, the
  three-pass cap and the landing rule. It names no project: each step reads
  `mise run check` or the project's `docs/agents/loop.md`, `issue-tracker.md`
  or `coding-standards.md`, and a test fails on a project term. It carries
  the generic coding standards, the owner-on-the-loop rules and status
  conventions, and three stdlib scripts: `board.py` (move a ticket),
  `gate.py` (the proof gate) and `omnigent_agent.py` (its project defaults to the
  repo's name).
- A project configures the loop rather than forking it: `loop.md § Practice`
  names the skill that fills a stage (defaults: `grilling`, `to-spec`,
  `code-review`, `pr`), and `§ Approvals` lists the spec, plan or merge points
  that wait for a person. The loop keeps the state, the gate, the cross-family
  verifier and the merge whatever the practice.
- Every step leaves proof on GitHub, and `scripts/gate.py check <build|merge>`
  checks it: the issues the PR closes are specced and labelled (what
  `spec_gate.py` did), each approval is recorded, and at merge the PR has its
  `## Evidence`, a posted verifier verdict, green CI and a merge approval on its
  head. The coordinator approves spec, plan and merge itself (`gate.py
  approve`), the verifier only gives the verdict (`gate.py verdict`), and a
  `§ Approvals` rule adds a person's approval, made by adding the
  `approved:<point>` label. A project runs the gate as `mise run gate`, adding
  its own checks; the loop, a pre-push hook and CI call it. A step is skipped
  only when the owner asks: `size:XS` no longer skips the verifier.
- Orchestration backends: native subagents (the default), Omnigent and
  herdr-link, picked by `Orchestration backend: <name>` in personal
  instructions. Without the other model family, the verifier is a fresh session
  of the same family and the PR body says `verifier: same family`; the brief
  never says so.
- The loop's issue conventions (states, categories, sizes, board columns) are
  its `issues.md`, and its `github.md` does them on GitHub (`gh` operations,
  board moves, the issue-batch protocol the setup skill used to write). Both
  are read in place, never copied: a project's `issue-tracker.md` holds the
  line `Tracker: GitHub (engineering-loop's github.md)`, its Components, what
  is Never on GitHub, and optionally Extra labels and Extra categories.
- Removed `setup-engineering-workflow-for-apm`: the project template writes
  `docs/agents/`, and two writers drift apart. `to-spec`, `triage`,
  `to-tickets`, `implement-spec`, `ask-matt`, `code-review` and `wayfinder`
  send a user without `docs/agents/issue-tracker.md` to create it. Drop
  `/setup-engineering-workflow-for-apm` from your own instructions.

## 0.7.0 - 2026-09-30

Upstream `mattpocock/skills` `c55ee46..d81f3a1` (release v1.3).

- Removed `resolving-merge-conflicts`, as upstream did in `daa01d8`: nothing
  replaces it, because the agent works through a merge or rebase conflict
  without a dedicated skill. Drop any reference to `/resolving-merge-conflicts`
  or the `resolving-merge-conflicts` skill from your own instructions.
  `ask-matt` and `implement-spec` no longer name it.
- The domain glossary is now `GLOSSARY.md`, and the multi-context map
  `GLOSSARY-MAP.md`, in every skill that reads or writes it, and
  `domain-modeling`'s format file is `GLOSSARY-FORMAT.md`. The skills no longer
  look for `CONTEXT.md` or `CONTEXT-MAP.md`: `git mv` an existing one to the new name.
- `implement-spec` (ported): the goal is one integration branch with every ticket
  resolved the way the tracker closes work. A draft PR opens only when the
  tracker closes work through PRs or the user asks, after the first merge. Each
  implementer checks its worktree's base, builds with `tdd` and merges the
  integration tip before reporting. Upstream's description wording is declined.
- `ask-matt` (ported): `retro` closes the main flow, and `implement-spec` is
  routed as landing on one integration branch.
- `pr` (ported): the glossary rename. Upstream's reformatted component-tree
  example and CREDITS rewording touch text the tuned skill had already condensed away.
- `codebase-design`, `diagnosing-bugs`, `domain-modeling`,
  `improve-codebase-architecture`, `tdd`, `triage`, `wait-what` (ported): the
  glossary rename only. `grill-with-docs`, `to-spec`, `to-tickets` and the setup
  skill take the same rename for consistency.
- Upstream graduated `implement-spec`, `pr` and `retro` out of `in-progress/`;
  the package now imports them from `skills/engineering/`.
- A skill is retired by removing its `vendir.yml` entry and its overlay: the
  refresh prunes the leaf and proposes a minor version. A configured leaf that
  vanishes upstream still stops the refresh.

## 0.6.2 - 2026-09-30

- `to-spec` writes the spec into the issue the conversation started from, under
  the original text quoted in full, instead of filing a second issue. The
  project's `docs/agents/issue-tracker.md` can send it to a comment where an
  issue's body is not the skill's to rewrite. With no issue it files one, as before.

## 0.6.1 - 2026-09-29

- `code-review` hands each reviewer this skill's path and its section instead
  of a paraphrased brief, which had dropped the smell baseline and report rules.
- The tuning contract says the same for any skill that prescribes a subagent's
  brief.

## 0.6.0 - 2026-09-23

- Tuned all 26 imported skills, the setup overlay and the owned skills
  (`audit-third-party-software`, `context-extractor`, `operating-omnigent`)
  for current models:
  generic advice, pressure language and step choreography removed, delegation
  left to judgment, harness- and tracker-neutral wording. Formats, gates and
  cross-references are kept. Supporting files that only repeated their skill
  were merged into it.
- Tuned skills are now owned overlays. The GitHub issue-batch patch is folded
  into `to-tickets` and `wayfinder`, and the patch series is gone.
- Upstream intake is now semantic: an upstream change under a tuned skill stops
  the refresh with its delta saved until a port or decline is recorded in
  `upstream-intake.yml`. The first intake ports upstream `c55ee46` (Merge
  Danger template in `pr`).
- An agent routine (`ROUTINE.md`), meant for a scheduled host: it ports
  upstream, has a fresh-context reviewer check the ports, merges its own PR and
  tags the release. It replaces the scheduled deterministic refresh,
  which followed upstream stable tags (none since `v1.2.3`) and could not port;
  that workflow and its publication tooling are deleted.
- Version bumps count from the last `engineering-v*` tag, so a port, review and
  rerun loop bumps once per release.
- `upstream-intake.yml` is validated on every check, and the package-test
  hang guard is 300 s (the APM install tests take about 110 s).
- Refreshed upstream from `74ca5fe` to `c55ee46` (`v1.2.3-54-gc55ee46`).
- Behaviour changes: `to-spec` publishes through the tracker document's issue-batch rules;
  `code-review` diffs against the merge-base and includes uncommitted and
  untracked files; `tdd` treats seams agreed in the spec as confirmed;
  `context-extractor` proposes edits to the sources when agent files are
  compiled (for example through APM); the third-party audit drafts the vendor issue and never files it.

## 0.4.0 - 2026-09-01

- Imported four skills from the upstream `in-progress` bucket at
  `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`: `claude-handoff`,
  `implement-spec`, `loop-me`, and `retro`.
- These are upstream beta: that bucket is excluded from the upstream plugin and
  its skills may change or disappear without warning. A disappearance fails the
  refresh rather than silently dropping a skill, because the removal check
  compares the committed inventory against what vendir produced.
- No change to the eighteen previously imported skills or to the source commit.
- Replaced the `/setup-matt-pocock-skills` rename patch with a literal
  substitution rule in `upstream.yml`, applied before the ordered patches. The
  shipped output is unchanged; the rule survives upstream rewording that a
  context diff did not.

## 0.3.1 - 2026-09-01

- Refreshed the reviewed Matt Pocock skill inventory from
  `84fdeffd12f2ee307994d1eb6feb48173b6e0502` to
  `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76` (`v1.2.3-39-g6654f6b`).
- Adopted an untagged upstream snapshot: upstream has published no stable tag
  since `v1.2.3`, so `stable_baseline_tag` stays `v1.2.3` and the package
  version magnitude comes from the inventory delta (no skills added or
  removed, so a patch bump).
- Rebased both downstream patches onto the upstream rewording (repo-wide
  em-dash removal and the "tell the user to run" setup phrasing).
- No inventory change: the same eighteen imported skills, all seventeen
  changed in content.

## 0.3.0 — 2026-08-09

- Refreshed the reviewed Matt Pocock skill inventory from
  `2ab958093e83e0ec752e6c1c5932da465bf23e0c` to
  `84fdeffd12f2ee307994d1eb6feb48173b6e0502` (`v1.2.3-2-g84fdeff`).
- Added the upstream `wizard` skill and adopted upstream updates across the
  existing engineering inventory.
- Rebased the downstream APM setup patch while preserving the package's
  repository-owned compilation and audit contract.

## 0.2.0 — 2026-07-30

- Added an independent APM manifest targeting Claude Code and Codex.
- Added the `engineering-v0.2.0` package tag contract and `^0.2.0` consumer
  dependency.
- Preserved native Claude marketplace installation through
  `engineering@kzarzycki-agent-skills`.
- Removed the floating `mattpocock-skills` marketplace entry in favor of the
  reviewed, pinned inventory shipped by this package.
