# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

loop:
  # the merge check CI runs; qualify's timeouts at 900 s on a shared host; pytest on xdist, a worker per free core (#941)
  gate: QUALIFY_TIMEOUT=900 GATE_TEST_PARALLEL=1 mise run check
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT: the host's load, not the change

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
    - docs/agents/gatekeeper.md
```
