# Loop facts

The engineering loop's values for this repo. `engineering/skills/engineering-loop/SKILL.md`
(Approvals and proof) defines what each setting approves and what still waits for the owner.

Orchestration backend: omnigent

Worker model: mid for size:S or smaller

A mid worker costs about half a top one per item, and a small item needs no more.

Verifier model: mid for not risk:high

Lead autocompact: 150k

A lead re-reads its whole context every turn, so a smaller window costs less per turn; its notes
file carries the run's state across a compaction. Raise or remove the line if leads lose track.

## Settings

```yaml
spec:
  auto: true

loop:
  gate: QUALIFY_TIMEOUT=900 mise run check   # the merge check CI runs; qualify's timeouts at 900 s on a shared host

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
```

## Approvals

Specs and merges are approved by policy, so work doesn't stop on them; the owner sees only
what no automated check can settle. A `risk:high` PR into a feature branch lands on the chief
of staff's `approved:merge` (`approvals.py delegate`), so dependent work doesn't stall; the
branch's merge to main waits for the owner.

## Cloud worker

Cloud worker: claude-cloud, gate test

Workers run in an environment that holds no secrets, so their compute leaves the owner's
machines. The live-agent suites (`test-engineering-agents`, `test-chief-of-staff-live`) need
logged-in harnesses and Omnigent, so they stay with the host lead. A cloud session clones the
pushed branch, so push before starting a worker. `.claude/cloud-setup.sh` is the
environment's setup script; the environment keeps its own copy, so apply a change with
`POST /v1/environment_providers/<id>`, `config.init_script` set to the file.
