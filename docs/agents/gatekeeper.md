# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

loop:
  # the landing gate: vendor check, lint and the tests the change touches, about a minute. The required `qualify` check runs the same on a PR head and on a push to main; the full suite runs nightly (schedule), blocking nothing. A batch's untested combination or a red nightly becomes an issue, a bisect over the day's merges, and a revert or fix PR through the loop.
  gate: QUALIFY_TIMEOUT=900 mise run check-fast
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT: the host's load, not the change

incubating:
  # a feature may append lines to the layer table (every new skill needs its layer, #1288); no waive list: all five
  append_paths:
    - docs/layers.md

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
    - docs/agents/gatekeeper.md
```
