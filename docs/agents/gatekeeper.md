# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

loop:
  # the merge check `local-ci` runs, and `land`'s batch gate where it lands without a queue (with `land.queue: mergify` below no landing runs it): vendor check, lint and the Mergify template drift check, about a minute, no tests: the command `qualify` runs on a PR head, so a worker's `local-ci --record` pass of it is the record CI reads and skips on (tools/pr_head_record.py). Since the Mergify batch's `qualify` runs the tests its combined diff touches (test-batch) once per tree. The nightly run covers the full suite; a red nightly becomes an issue, a bisect over the day's merges, and a revert or fix PR through the loop.
  gate: QUALIFY_TIMEOUT=900 mise run check-fast
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT: the host's load, not the change
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
