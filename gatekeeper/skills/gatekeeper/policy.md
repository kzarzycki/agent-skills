# Policy

The project's `docs/agents/gatekeeper.md` holds the gatekeeper's policy, a fenced `yaml`
block under `## Policy`, which only `gatekeeper.py` reads, so a team that takes only the
gatekeeper writes no other file. Prose for people and agents (why a path is critical, how to
judge a finding, the risk criteria in words) stays outside the block, in the project's own
files. A project without gatekeeper.md may keep the block under `docs/agents/loop.md`'s
`## Settings` for now: the gatekeeper reads it there with a deprecation line, and refuses a
project with both, since two sources of the bar would drift. The block is YAML because a person
reads and edits it by hand as `key: value` under section names, a list one item per line,
and it is typed (a boolean, a number and a list are each their own kind, so none is a
string the reader guesses at). A string needs no quotes unless YAML would read it otherwise:
one that starts with `*`, `&`, `!` or `[`, holds `: ` or ` #`, or reads as another type.
YAML 1.1, which PyYAML follows, reads `yes`, `no`, `on` and `off` as booleans and `1.10` as
the number 1.1, so the gatekeeper matches each value's type exactly and refuses, naming the
key, a value or name YAML read as something else: quote it. A value names a thing (a label,
a glob, a skill, a branch, a kind of spec), never a rule in words: which specs the policy
approves is a list of kinds, not a phrase such as `auto unless risk` whose meaning lives in
the reader, so a person reads the policy off the block and may name any part of it.
The gatekeeper refuses, naming the key, a section or key it doesn't know and a value of the
wrong type, and refuses a policy file without the block, so a mistyped setting is never read as
a rule nobody wrote.

`gatekeeper.py` reads the block with PyYAML (SKILL.md says how `uv run` installs it).
Every key is optional:

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
  batch_queue: true   # lands through a batching merge queue of its own (below)
  owner: octocat   # whose own approved:spec label, added after the spec's last edit, is their approval

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
  renovate:                 # an updater under a person's token: named by its branch
    branch: renovate/
    paths:
      - uv.lock

land:
  signed_squash_to: main
  allowed_signers: ~/.config/git/allowed_signers

checks:
  changed: mise run test:changed
  check: mise run check     # what `record checks` runs and records
  all: mise run check:all   # what `local-ci` (`record checks --all`) runs and records

adapters:   # each port's adapter; github is the one there is
  tracker: github
  forge: github
  evidence: github

carry_over_main:
  # a clean merge of main keeps the head's verdict unless either side changed one of these
  except:
    - mise.toml
    - uv.lock
    - '**/uv.lock'
    - pyproject.toml
    - .github/**
```

| Section | Key | Value | Without it |
|---|---|---|---|
| `spec` | `auto` | a list of `bug`, `follow-up` and `sub-issue`, or `true` for every spec (Rules) | every spec waits for the owner |
| `loop` | `cap` | a whole number (SKILL.md, The cap) | the default |
| | `ci` | `false` for a project without CI, whose merge proof is then `record checks --all <pr>` (formerly `local-ci <pr>`; the docstring says what it records) | `true` |
| | `local_ci_env` | the environment variables the merge check reads (a tier, a scope): a `local-ci` pass records their values and is reused only under the same ones, and the posted comment names them | none |
| | `opt_out` | `true` where a person may work outside the loop (Opting out) | `false` |
| | `batch_queue` | `true` for a project that lands through a batching merge queue of its own (Batching merge queue) | no batch proof counts |
| | `owner` | a login whose own `approved:spec` (or `approved:plan`) label, added after the spec's last edit, `check` and `land` record as the owner's approval, removing `needs-owner` | an agent records the owner's word with `record approval` |
| `practice` | `intent`, `spec`, `plan`, `build`, `review`, `land` | the skill that fills that stage, which the flow reads; the gatekeeper reads only `plan`, since a `## Plan` comment is then due before the build | the stage's default |
| `risk`, `plan`, `signoff` | `always` (`true` or `false`), `labels`, `paths`, and in `risk` `verifier` | a rule (Rules); `plan` has no `paths`, since a plan comes before the change | no rule |
| `bot.<login>` | `paths`, and `branch` (a head-branch prefix) to name an updater by its branch instead | a bot whose PR needs no verifier review (Rules) | every PR needs one |
| `land` | `signed_squash_to`, `allowed_signers`, both | for a repo that trusts only commits its maintainers sign, the branch and the allowed signers file: `land` then squashes and signs the PR in the checkout instead of merging it on GitHub (`gatekeeper.py`'s docstring says how) | GitHub merges |
| `checks` | `changed`, `check`, `all`, each a shell command | the project's checks: while iterating, before every push (`record checks`), and the full merge check, which `local-ci` runs and records | `record checks` runs `mise run check`, `local-ci` `mise run check:all` |
| `adapters` | `tracker`, `forge`, `evidence`, each an adapter's name | the tool behind each of the gatekeeper's ports; a name with no adapter is refused | `github` |
| `carry_over_main` | `except`, a list of globs, required | the project's merge-check configuration (lint, type, test and gate config, lockfiles): a clean merge of main whose changes touch none of the PR's files, where neither the PR's changes nor main's touch one of these, keeps the head's verdict, never its `local-ci` record (Carry over main). A glob matches the full path, as `paths` does: a nested copy needs `**/<name>` beside `<name>` | every merge of main needs its own verifier pass |

## Rules

Each rule the policy states:

- `spec.auto`, a list, approves by policy, with no record or label, the spec of each
  kind it names: `bug`, a `kind:bug`; `follow-up`, an issue whose body has a `Found while
  #<n>` line (a follow-up an agent raised while working on #n, which puts the line on every
  issue it files); `sub-issue`, a native sub-issue of an
  epic the owner approved (their current record and `approved:spec`), opened by an account
  with write access to the repo. Any other spec, a new epic for one, needs the owner's
  approval; without `auto`, or with `false` or an empty list, every spec does.
- `spec.auto: true` approves every spec by policy, epics included, so the owner reads only the
  critical ones: a spec the `risk` rule matches, or one opened by an account without write
  access, since anyone who can open an issue would otherwise approve their own, waits for
  the owner's record and `approved:spec`. The risk rule then holds the spec instead of the
  merge: the owner decides while the change is still cheap, and its merge is automatic
  like any other. The gatekeeper judges the rule on the labels of the issue and the PR
  and the PR's files, at `check build` the files pushed so far, so a file the spec didn't
  foresee still reaches the owner before the merge. `auto: true` moves the rule rather than
  a key of its own, since with every spec approved by policy the spec is the one point the
  owner sees a risky change before it is built, and holding the merge as well would ask
  them twice.
- The gates are the merge approval of a change that is not high risk.
- `risk` says what is high risk here, and any one of its terms matching holds: `labels`,
  matched exactly on the PR and its issues as GitHub names them (`size:L` and `size:XL`
  for large or larger, `area:billing`, `kind:bug`); `paths`, globs matched on the PR's
  files; `always: true`; and `verifier: true`. The gatekeeper reads the keys, never the
  words, so a path such as `docs/verifier.md` is only a path. Paths it can't judge, past
  the one page of files it reads, hold, since nothing else would enforce them.
  The `verifier` term holds when the verifier judges the change high: the newest
  pass on the head, by a trusted account, says `Risk: high`, any word but `low`, or has no
  `Risk:` line (SKILL.md, Verifier report). Paths beside it hold whatever the verifier says, so
  `verifier: true` with `paths` `.github/**` and `CODEOWNERS` lets the verifier decide and
  keeps those files the owner's. The gate judges it at the merge, under `auto: true` too,
  since the verdict comes after the build, and quotes the verdict. A `risk:high` it added
  for that term comes off when a later pass says `Risk: low`; one added again after it
  stays. A project's criteria in words (a loop.md § Risk criteria, where it has one) are the
  verifier's to read; the gatekeeper reads only the keys.
- `plan` asks for the owner's approval of a matching plan.
- `bot.<login>`, such as `bot.dependabot[bot]` with `paths` `uv.lock` and
  `pyproject.toml`: a PR that bot opens needs no verifier review when every commit is the
  bot's (its authors, and its committer unless that is no account) and every file it
  changes, none renamed or copied, matches one of its `paths`, since no verifier runs on a
  bot's PR; anything else needs the review as usual. A section with `branch`, such as
  `bot.renovate` with `branch` `renovate/`, names an updater that opens its PRs under a
  person's token instead: the PR's head is this repository's branch starting with the
  prefix (a fork's PR may name any branch), and every commit is that person's, so the
  updater commits as that person (Renovate's `gitAuthor`), not as its default author. A PR labelled
  `verify` (a major update) needs the review either way. Without the section, every PR needs
  one.
- `signoff`, such as `labels` `area:ios` and `area:watch`: the owner signs off a
  matching change in use after it lands, which no gate can do for them. The rule reads as
  `risk` does, on the labels of the PR and the issue and the PR's files. The spec records the outcome in a line
  `Sign-off: owner` or `Sign-off: none`, and `owner` there asks for it where no rule does.
  The PR links such an issue with `Implements #<n>`, which GitHub does not close, so the
  issue stays open for the sign-off, and every other issue with `Closes #<n>`; `Part of
  #<n>` suits both. `check merge` refuses the wrong keyword. Without a `signoff` section
  no keyword is checked, and `Implements` is a link like `Part of`.

## Batching merge queue

A project may land a base through a batching merge queue of its own instead of one `land` per PR, opting in with
`batch_queue: true` under gatekeeper.md's `loop` (without it no batch proof counts): it merges every
waiting PR's verified head onto the base, runs the full gate once on the result and pushes
the batch, so a base that moved costs one gate, not a merge, a gate and a verdict per PR.
`gatekeeper.py check queue <pr> --head <sha>` says whether a head may enter
it: every merge proof but the CI wait, the head's own `local-ci --record` pass under the
current environment and, with CI, its `check`, and nothing high risk or
owner-approved, since the owner's label covers one head landing alone, through `land`. The
queue posts `gatekeeper.py batch` on each PR it pushed, and `check merge` takes that proof in
place of the CI wait once git shows the head merged unchanged and without conflict
resolution into a batch whose gate passed, and the head has its own `local-ci --record` pass
under the environment the proof names (`gatekeeper.py`'s docstring says how). A batch gate
never stands in for the head's own: `batch` refuses, and `check merge` rejects, a head that
was never gated. Only a proof posted by the running account or a writer counts, and a red or
unproven one leaves the wait exactly as it was, so a PR evicted through another PR's red batch
re-queues or lands alone at the same head. The queue never resolves a conflict: a PR that
conflicts goes back to whoever opened it.

## Carry over main

With gatekeeper.md's `carry_over_main` section, merging main into a PR head H keeps H's verdict
when git shows the merge changed nothing the PR's code reads: the merge H' has H as its
first parent and a commit on main as its second, its tree is `git merge-tree`'s of the two
(no conflict resolved, nothing added), and main's changes since the merge base touch none of
the PR's files, and neither the PR's changes nor main's touch an `except` glob, since a
config change on either side was never reviewed against the other side's code. H's verdict
then covers H'; `check merge` and `land` print one line naming H, H' and the predicate.
Anything else (a conflict, an evil merge, an overlapping file, a touched except path, a git
error) carries nothing: the merge needs its own verifier pass. The gate never carries: H'
runs its own, as CI does, and under `ci: false` that is `local-ci <pr>` on H', since a
`local-ci` record stands in for CI on one exact head. This skips a review on purpose, so a
project opts in by writing the section.

## Opting out

With `opt_out: true` in gatekeeper.md, a developer may keep their own PRs out of the
loop, by a line in their personal agent instructions (the loop reads `Engineering loop: off`)
and nothing on the PR. `check merge` then reads a PR with no loop trail (no verifier review, no
`Approved: spec` record or `approved:spec` on an issue it links, no `Reverts #<n>` line,
not an exempt bot PR) as outside the loop: it prints one line saying so and exits 0, so the
`loop:approvals` status is green and the PR's author merges it their usual way, under the
repo's own rules. `land` prints the same line and exits 1, so no agent merges it or turns
auto-merge on for it. Risk rules and `risk:high` hold no PR outside the loop; the project
accepts that by setting it. A spec a policy covers is no trail, since under
`spec.auto: true` every issue is covered. Any trail puts the PR back under every proof. Without
it, a PR with no trail fails the gate.

## Tracker settings

The project's `docs/agents/issue-tracker.md` holds its label and board facts in a block of
the same form under its own `## Settings`. `gatekeeper.py` parses it (`tracker_settings`) and
refuses it the same way: it reads `components` and `categories` for the label names `check
build` needs, and the `github-tracker` skill's `labels.py` and `board.py` read the rest through
it. Prose in that file (such as what never goes on GitHub) stays outside the block. Each section's values are strings:

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
| `renames` | an old label name: its new one, added to the loop's own renames | the loop's own renames only |
| `board` | a loop column: the board's column (`github-tracker`'s github.md, Board) | each column keeps its own name |
