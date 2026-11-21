# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

loop:
  # `land`'s batch gate: vendor check and lint, about a minute, no tests, since main requires the `qualify` check, which ran each head's touched tests (loop.md's `Affected tests:` command, check-fast) on that head. The nightly run covers the full suite; a red nightly becomes an issue, a bisect over the day's merges, and a revert or fix PR through the loop.
  gate: QUALIFY_TIMEOUT=900 mise run check-land
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT: the host's load, not the change
  delegate: all   # the delegated approver's go on a head covers a PR into the default branch too

incubating:
  # a feature may append lines to the layer table (every new skill needs its layer, #1288); no waive list: all five
  append_paths:
    - docs/layers.md

land:
  # PRs into main merge through the Mergify merge queue `.mergify.yml` configures: land posts `land` and adds `loop:queued` on each landable PR, and Mergify tests each batch as a draft PR in CI and squash-merges it, so no host runs a landing gate (#1658). GitHub's own queue needs an organisation-owned repo.
  queue: mergify

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
    - docs/agents/gatekeeper.md
```
