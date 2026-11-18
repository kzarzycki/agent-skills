# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

loop:
  # the landing gate: vendor check, lint and the tests the change touches, about a minute. The full suite is the required `qualify` check on every PR head and on every push to main, off the laptop; a batch's untested combination is caught there and fixed forward.
  gate: QUALIFY_TIMEOUT=900 mise run check-fast
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT: the host's load, not the change

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
    - docs/agents/gatekeeper.md
```
