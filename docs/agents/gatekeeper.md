# Gatekeeper

The policy `approvals.py` reads; `docs/agents/loop.md` keeps the loop's other facts.

## Policy

```yaml
spec:
  auto: true

loop:
  # the merge check CI runs (`mise run check`), as steps, so a step a cloud session passed on a tree is not rerun on a
  # host or by land; qualify's timeouts at 900 s on a shared host
  gate_steps:
    - name: vendor-engineering-check
      command: QUALIFY_TIMEOUT=900 mise run vendor-engineering-check
      where: any
    - name: test
      command: mise run test
      where: any
    - name: test-engineering-package
      command: mise run test-engineering-package
      where: any
  machine_exit: 78   # qualify exits 78 when a step stops on QUALIFY_TIMEOUT: the host's load, not the change

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
    - docs/agents/gatekeeper.md
```
