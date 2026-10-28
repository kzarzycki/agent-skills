# Gatekeeper policy

The gatekeeper's standing policy for this repo. `approvals.py` is this file's only reader;
`engineering/skills/engineering-loop/SKILL.md` (Settings, Approvals and proof) defines each
key and what still waits for the owner. The reasons for these values are loop.md's
Approvals.

## Policy

```yaml
spec:
  auto: true

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/gatekeeper.md
    - docs/agents/loop.md
```
