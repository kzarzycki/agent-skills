# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

loop:
  gate: QUALIFY_TIMEOUT=900 mise run check   # the merge check CI runs; qualify's timeouts at 900 s on a shared host
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT: the host's load, not the change

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
    - docs/agents/gatekeeper.md
  lower_tier_until: 2026-11-20   # Codex is out of quota until 2026-11-20 05:47 UTC: a fallback verdict lands a high-risk PR through that UTC day
```
