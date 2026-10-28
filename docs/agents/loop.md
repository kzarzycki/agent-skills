# Loop facts

The engineering loop's values for this repo. `engineering/skills/engineering-loop/SKILL.md`
(Approvals and proof) defines what each setting approves and what still waits for the owner.

Orchestration backend: omnigent

## Settings

```yaml
spec:
  auto: true

tiers:
  claude: {top: claude-opus-5-5, mid: claude-sonnet-5-5, small: claude-haiku-5-5}
  codex: {top: gpt-6.1-sol, mid: gpt-6.1-terra}

models:
  worker:
    - when: {labels: [size:XS, size:S]}
      tier: mid
  verifier:
    - when: {risk: high}
      tier: top
    - tier: mid

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
```

The lineup names no frontier model (Fable, Astra): it costs several times `top`, and the tiers below are at least on
par for this work. A mid worker costs about half a top one per item, and a small item needs no more.

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
