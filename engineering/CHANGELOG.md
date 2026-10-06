# Changelog

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
