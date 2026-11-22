# Policy

gatekeeper.md holds the gatekeeper's policy, a fenced `yaml` block under `## Policy`, which
`approvals.py` reads, so a team that takes only the gatekeeper writes no loop file; loop.md
keeps the prose for people and agents: why a path is critical, how to judge a finding, the
risk criteria in words. A project without gatekeeper.md may keep the block under loop.md's
`## Settings` for now: `approvals.py` reads it there with a deprecation line, and refuses a
project with both, since two sources of the bar would drift. `uv run --python '>=3.11' approvals.py check setup` is a consumer's gate on a pack upgrade: it reads the policy this way and
scans the repo's mise config and workflows for a pack script run without `uv run` (README § Upgrading the pack). `approvals.py` reads these files,
and issue-tracker.md, from the base's copy on `origin/<base>`, never the checkout's: the base the
PR a command acts on merges onto, the ref `land` builds on (`check`, `land`, `local-ci <pr>`,
`approve merge`, `delegate`, `brief`), else the default branch. `land` fetches the base before
it reads the policy (where it may run, its key, which drafts to ready) and reads it again after
its fetch under the landing lock, so a policy another land changed meanwhile decides the batch:
it places the land again (refused, the lock released, where the base now excludes the place it
runs; signed with the key it now names), and a draft it readied that the new policy would not
ready goes back to draft. A failed fetch before the lock readies no draft. So a PR can't
loosen its own gate and a checkout behind its
base can't hold an old one: a working-tree copy that differs gets one line naming the file and
both commits, and only a checkout without that ref (no `origin`) reads its own, with a line
saying so. A PR that changes the gate is therefore gated, recorded and landed under the base's
gate, and its own applies from the next PR on. The block is YAML because a person
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
wrong type, and refuses a policy file without the block, so a mistyped setting is never read as
a rule nobody wrote.

The scripts read the block with PyYAML, the one package they need beyond the standard
library. Each declares it inline (PEP 723), so `uv run <this skill's folder>/scripts/approvals.py` installs it
into uv's cache on first use and nothing is installed by hand; uv comes with the project's
mise. Run with a bare `python3` that lacks PyYAML, a script exits with one line saying to
run it with `uv run`. They need Python 3.9 or later, except `check setup`, which needs 3.11 (it reads mise's TOML). Every key is optional:

```yaml
spec:
  # specs approved by policy, with no owner record; any other waits for the owner.
  # `auto: true` approves every spec, and by default the risk rule then holds the spec, not the merge
  auto:
    - bug
    - follow-up
    - sub-issue
    - paths:   # a spec labelled spec:paths whose PR stays inside these globs
        - mise.toml
        - docs/agents/**

loop:
  cap: 3
  ci: false
  gate: GATE_TIER=full mise run check:all   # the merge check, and the variables it sets
  local_ci_env:
    - GATE_TIER
  opt_out: true
  batch_queue: true   # deprecated with ci and carry_over_main: land batches every landable PR
  owner: octocat   # whose own approved:spec label, added after the spec's last edit, is their approval
  machine_exit: 78   # the gate's exit for "this machine isn't ready": land runs it again, then stops
  short_seconds: 120   # a job expected to finish within this takes the host's short lane; 0 turns the lane off
  pre_land: python3 scripts/check_fork.py   # land's check of each PR against the base, before it batches them
  delegate: all   # the delegated approver's go on a head covers a PR into the default branch too; default feature
  pack_staleness: refuse   # approvals.py exits 1 at start when its checkout is behind its upstream and the script changed there (default warn; omnigent_agent.py only warns)
  stalled_after_hours: 12   # check stalled lists a verified PR still missing its go or record this long after its head's push (default 4)
  head_proof:      # the status land requires on each head, and the names its recording takes from the caller
    status: gate-ui
    env:
      - GATE_UI_TESTS

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
  critical_paths:   # the `critical` level, whatever the labels and the verifier say; was merge_paths
    - src/orders/**

levels:   # what each level asks; the values shown are the defaults
  low:
    spec: policy
    merge: gates
  high:   # under `spec.auto: true` {spec: owner, merge: gates}
    spec: policy
    merge: go
  critical:
    spec: policy
    merge: owner

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
  batch_wait_seconds: 600   # land waits up to this long before it gates, while another PR waits only on its required checks; default 0
  gate_on: cloud   # land's batch gate runs in a standing cloud session, the host as fallback; default host
  cloud_gate_timeout_seconds: 2400   # how long land waits for that session's record before gating on the host; default 2400
  # queue: mergify   # land hands each landable PR to a Mergify merge queue (`.mergify.yml`) instead; refused with signed_squash_to

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
| `spec` | `auto` | a list of `bug`, `follow-up`, `sub-issue` and `paths` terms, or `true` for every spec (Approvals and proof) | every spec waits for the owner |
| `loop` | `cap` | a whole number (The cap) | the default |
| | `ci` | deprecated, goes in the next release (Approvals and proof); `false` for a project without CI, whose merge proof is then `uv run <this skill's folder>/scripts/approvals.py local-ci <pr>` (its docstring says what it records) | `true` |
| | `gate` | the merge check `local-ci` runs: a command, with any variables it sets in front (Adopting the loop) | `mise run check:all` |
| | `gate_steps` | the merge check as steps, in place of `gate`: a list of `name`, `command` (parsed as `gate` is), `where` (`any`; `host`: never run in a cloud session; or `linux`: only where `sys.platform` is Linux, a Linux host or a cloud session, never macOS) and optionally `paths`, globs of the files the step reads, matched on the full path as `paths` are, so its pass is reused on any tree whose files under them are the same; each step's pass recorded and reused by itself (Adopting the loop) | the one `gate` command; a step without `paths` reads the whole tree |
| | `local_ci_env` | the environment variables the check reads, cleared for its run unless `gate` sets them (Adopting the loop) | none |
| | `machine_exit` | the gate's exit that means the machine isn't ready (a locked screen, low disk), such as 78: `land` runs that gate once more on the same tree, and a second one stops the run landing, evicting and posting nothing, and `local-ci` refuses it as a machine fault (`approvals.py`'s docstring) | every non-zero exit is red |
| | `short_seconds` | a whole number of seconds: a job expected to finish within it takes the host's short lane instead of the heavy slot, and `0` turns the lane off (Rules, One heavy gate per host slot) | `120` |
| | `opt_out` | `true` where a person may work outside the loop (Approvals and proof) | `false` |
| | `pre_land` | a check `land` runs for each PR before batching it, parsed as `gate` is, from the base's tree with `LAND_HEAD` and `LAND_BASE` set, such as one refusing a branch forked before a restructuring; non-zero leaves that PR out of the batch with one comment per head holding its output, and it stays ready (`approvals.py`'s docstring says how) | no check |
| | `head_proof` | `status`, a commit status `land` requires on each head, and `env`, the variables `local-ci --record --head-proof` takes from the caller for that run, both required (Approvals and proof) | the batch gate is the only proof |
| | `stalled_after_hours` | a whole number of hours: `check stalled` lists an open PR whose newest verifier pass on its head is satisfied (or at the cap) but that still lacks the go its rating asks or the `head_proof` record, once its head was pushed more than this long ago with neither coming in, naming what it misses (`missing: go`, `missing: record`) | `4` |
| `mutate` | `inconclusive_exit` | a whole number from 1 to 255: the exit a test command returns for "setup failed, no verdict", which `mutate.py` reports as an inconclusive patch (never killed) and exits 3 for; the project's test command exits with it when its device or build setup fails (verifier.md, Mutation-check the new tests) | `75` |
| `practice` | `intent`, `spec`, `plan`, `build`, `review`, `land` | the skill that fills that stage (Practice) | the stage's default |
| `risk`, `plan`, `signoff` | `always` (`true` or `false`), `labels`, `paths`, and in `risk` `verifier` | a rule (Approvals and proof); `plan` has no `paths`, since a plan comes before the change | no rule |
| `risk` | `critical_paths` | globs matched on the PR's files, as `paths` are: a PR touching one rates `critical` (Approvals and proof); `merge_paths` is its deprecated name, read with a `deprecated:` line, and both set is refused | nothing rates `critical` |
| `incubating` | `append_paths` (globs of existing files a feature may only append lines to), `waive` (any of `evidence`, `proof_run`, `verifier`, `full_gate`, `coverage`) | what an eligible `incubating` PR stops owing (Approvals and proof, Incubating) | the mode is off; with the section and no `waive`, all five |
| `levels` | `low`, `high`, `critical`, each with `spec` (`policy` or `owner`) and `merge` (`gates`, `go` or `owner`) | what a change rated at that level needs (Approvals and proof); a key left out keeps its default | `low` {policy, gates}; `high` {policy, go}, or under `spec.auto: true` {owner, gates}; `critical` {policy, owner} |
| `bot.<login>` | `paths`, and `branch` (a head-branch prefix) to name an updater by its branch instead | a bot whose PR needs no verifier review (Approvals and proof) | every PR needs one |
| `land` | `signed_squash_to` and `allowed_signers`, set together or not at all; `where` (`host`, `claude-cloud` or `both`; `cloud` still means `claude-cloud`), `signing_key_env`, `merge_queue`, `merge_commit_heads` (a list of fnmatch patterns over head branch names, such as `sync/*`), `batch_wait_seconds` (a whole number of seconds, 0 or more), `gate_on` (`host` or `cloud`), `cloud_gate_timeout_seconds` (a whole number of seconds, 0 or more) and `queue` (`mergify`) | for a repo that trusts only commits its maintainers sign, the branch and the allowed signers file: `land` then squashes and signs the PR in the checkout instead of merging it on GitHub; `where` is where `land` may run (default `both`: a cloud session lands too, with no `land` section on a base whose ruleset requires GitHub's merge queue), and in a cloud session a repo with `signed_squash_to` signs with the key in the variable `signing_key_env` names, which must be in the allowed signers, never the session's own, and lands a PR there only with `merge_queue: false`, since REST can't say whether the base requires a merge queue (`approvals.py`'s docstring says how); a base whose ruleset requires GitHub's merge queue needs no key there, since GitHub merges and signs; `batch_wait_seconds` makes `land`, holding the lock, wait up to that long before it gates the batch while another open PR into the same base is held by nothing but its required checks still running (the proofs and any owner go already hold, and a PR whose required check no workflow will run, a conflicting one or a readied draft whose workflow lacks `ready_for_review`, never counts), and each such PR whose checks turn green in that time joins the batch and shares its one gate; its wait and who joined are printed and shown on the `Landed` comment's `Batch:` line, and `land` of named PRs only never waits; with `gate_on: cloud`, `land`, holding the lock, pushes the batch commit as the branch `loop-land/<tree>`, asks the repo's one standing cloud gate session (started on first use, its id kept in `.git/approvals/cloud-gate.json`) to run `local-ci --record` on it, waits for the record branch of exactly that tree (the same rule as any reused pass), deletes `loop-land/<tree>` and then gates as usual, which now reuses that pass and runs nothing on the host; a `where: host` step still runs there. No record within `cloud_gate_timeout_seconds` (default 2400 s: the measured cloud gate took 1,200 to 1,650 s, and the first batch also starts the session; the session's `launch-dir` and `start` take up to 600 s each on top), a session whose turn has ended with no record and no red line, a refused start or a session that is gone is one printed line, and the host gates as without the setting, so a cloud outage never blocks landing; a session whose turn ended (or that is archived, never one in a `failed` state, whose last message can be an earlier turn's) on `DONE: red <tree>` (a failed gate pushes no record) fails the tree at once with no host re-run, since a red suite stays red (a `machine_exit` exit is a machine fault, not red); the red path (each PR alone, then evict) takes the same route; it is optional, so it needs no signing keys; `queue: mergify` names a Mergify merge queue as the base's queue, on a base whose rules require no GitHub merge queue (they win): `land` posts the `land` status on each candidate's head and adds `loop:queued`, which the repo's `.mergify.yml` queue conditions read, and Mergify tests and merges (below), with no lock, no host gate and no signing key, so a cloud session lands too; `approve merge` and `record verdict` each end by that hand-over when `check merge` passes (else they print what is missing and queue nothing), and `check stalled` lists each open PR with its go and a satisfied verdict that is neither queued nor merged (exit 1), so a land that was stopped or died is noticed, and also each verified PR that has waited past `loop.stalled_after_hours` for a go or record it lacks, naming what is missing (on any base: one `land` merges itself is listed while still open, one GitHub's merge queue holds while not in it, and a PR it can't judge from this checkout, such as one stacked on another PR's branch, gets its own `not judged` line and stops no other, and leaves the exit as it is: exit 0 with `not judged` lines means those PRs were not judged, not that none is stalled; a checkout's own edit of the policy files changes nothing, since the base's are read); with `signed_squash_to` it is refused, since GitHub signs Mergify's merges | GitHub merges, on a host, or in a cloud session on a base whose ruleset requires the merge queue; no wait for `batch_wait_seconds`; a PR whose head matches `merge_commit_heads` lands with `gh pr merge --merge --match-head-commit`, keeping the head's ancestry (an upstream-sync PR needs it), and every other PR is squashed as before; `land` prints each PR's method, and a match with `signed_squash_to` set is refused, since a signed squash has no merge-commit form |
| `carry_over_main` | `except`, a list of globs, required | deprecated, goes in the next release (Approvals and proof); the project's merge-check configuration (lint, type, test and gate config, lockfiles): clean merges of main whose changes touch none of the PR's files, where neither the PR's changes nor main's touch one of these, keeps the head's verdict, never its `local-ci` record (Approvals and proof). A glob matches the full path, as `paths` does: a nested copy needs `**/<name>` beside `<name>` | every merge of main needs its own verifier pass |
| `breakglass` | `max_age` (`7d` or `12h`), `max_commits`, `smoke` (a command, as `gate`), `earlier_runs`, `artifact`, all optional | the windows of the owner's break-glass proof (breakglass.md); `loop.owner` must name the owner's login, since only their status and record count | `7d`, `20`, the `gate`, `2`, `failed-tests` |
| `adapters` | `tracker`, `forge`, `evidence` | the adapter each of the gatekeeper's ports runs on, by name: `github`, `gatekeeper.py`'s own (`github_adapter.py`), is the one it ships, and a name no adapter has is refused, naming it (`gatekeeper.py`'s docstring) | `github` |

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
