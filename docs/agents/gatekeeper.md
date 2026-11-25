# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

levels:
  # this repo has rerun.yml, which pushes the rerun record: a high or critical head merges only on it
  high:
    rerun: true
  critical:
    rerun: true

loop:
  # the merge check `local-ci` runs, and `land`'s batch gate where it lands without a queue (with `land.queue: mergify` below no landing runs it): vendor check, lint and the Mergify template drift check, about a minute, no tests: the command `qualify` runs on a PR head, so a worker's `local-ci --record` pass of it is the record CI reads and skips on (tools/pr_head_record.py). Since the Mergify batch's `qualify` runs the tests its combined diff touches (test-batch) once per tree. The nightly run covers the full suite; a red nightly becomes an issue, a bisect over the day's merges, and a revert or fix PR through the loop.
  gate: mise run check-fast
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT (vendor-engineering-check's own default, mise.toml): the host's load, not the change
  owner: kzarzycki   # the login whose own records count as the owner's: break-glass approvals, and an approved:spec or approved:plan label added after the issue's last edit
  delegate: all   # the delegated approver's go on a head covers a PR into the default branch too

incubating:
  # a feature may append lines to the layer table (every new skill needs its layer, #1288); no waive list: all five
  append_paths:
    - docs/layers.md

bot:
  pack-bump:   # the engineering pack's bump, which a cloud worker pushes to claude/ready-pack-bump-<tag>
    branch: claude/ready-pack-bump-
    paths:
      - apm.yml
      - apm.lock.yaml
      - ".agents/**"
      - ".claude/**"
      - ".codex/**"
  # the Release workflow's PR (#1861, engineering/RELEASING.md): `qualify`'s `cli release-verify` fails it unless its tree is exactly `cli cut-release` rerun on its branch point, so no verifier reads it. Its commits carry an identity no GitHub account holds, which a `branch` section counts as the PR author's.
  release:
    branch: release/
    paths:
      - "*/CHANGELOG.md"
      - "*/changelog.d/*.md"
      - "*/apm.yml"
      - "*/.claude-plugin/plugin.json"
      - "*/README.md"

land:
  # PRs into main merge through the Mergify merge queue `.mergify.yml` configures: land posts `land` and adds `loop:queued` on each landable PR, and Mergify tests each batch as a draft PR in CI and squash-merges it, so no host runs a landing gate (#1658). GitHub's own queue needs an organisation-owned repo.
  queue: mergify
  # the batching `approvals.py queue-config` renders into `.mergify.yml` (check-fast fails on drift): up to 3 PRs per batch, each batch waiting up to 5 minutes for more
  batch_size: 3
  batch_wait_seconds: 300

select:
  # The files every test reads, or that select the tests: a change to one runs the whole suite (outside the merge queue; under
  # `build_inputs_in_queue: floor` the queue adds nothing for one, and the nightly workflow below runs the suite after the
  # merge). The selector's own code is one: a change to the selector can't be judged by the selector it changes (#2232).
  # tools/affected_tests.py's BUILD_INPUTS is this list, and `timeouts --check` fails when the nightly's push paths differ.
  build_inputs:
    - pyproject.toml
    - uv.lock
    - mise.toml
    - conftest.py
    - tools/affected_tests.py
    - gatekeeper/skills/gatekeeper/scripts/gatekeeper.py
  # What a change with no build input runs: this repo's tests read prose and agent config (the skill-reference and layer
  # tests), so a change to one still runs the `Affected tests:` command, as before `select` was set.
  checks:
    - paths:
        - "*.md"
        - docs/*
        - .claude/*
        - .agents/*
      command: mise run check-affected

timeouts:
  test: 60s   # one test: tools/timeouts_plugin.py gives it to pytest-timeout (pyproject.toml sets no limit of its own)
  run: 60m    # one selection run: .mergify.yml's checks_timeout and the qualify job's timeout-minutes derive from it

breakglass:
  max_age: 7d   # a run older than this counts for nothing in the owner's break-glass proof
  max_commits: 20   # nor a head further from the PR's
  earlier_runs: 2   # green runs of the required check the proof needs from before the red

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
    - docs/agents/gatekeeper.md
```
