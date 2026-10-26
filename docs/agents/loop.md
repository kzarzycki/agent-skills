# Loop facts

The engineering loop's values for this repo. `engineering/skills/engineering-loop/SKILL.md`
(Approvals and proof) defines what each setting approves and what still waits for the owner.

Orchestration backend: omnigent

Worker model: mid for size:S or smaller

A tier, not a model id, so the line holds for every family and each new generation (#247): today
`claude-sonnet-5-5` for Claude and `gpt-6.1-sol` for Codex (#250: Sol is Codex's `top`, the only
tier model of its newest generation, 6.1). A one-week trial to 2026-10-27,
decided under the owner's standing decision of 2026-10-20 (chief-of-staff session 13cd3ad1) to
approve reversible progress (#245, evidence on #228): a Sonnet worker cost about half an Opus
one per item. At its end, telemetry compares verifier passes per PR against the Opus workers of
2026-10-18..20. Leads and verifiers keep their defaults.

## Settings

```yaml
spec:
  auto: true

risk:
  verifier: true
  paths:
    - .github/**
    - CODEOWNERS
    - docs/agents/loop.md
```

## Approvals

The owner's reason: specs and merges are approved by policy, so work doesn't stop on them,
and the owner sees only what no automated check can settle (#330). The verifier judges each
change's risk (`verifier`); CI, code owners and this file's own approval rules always reach
the owner, which under `spec: auto` means their spec does. Also waiting for the owner: a
spec opened by an account without write access, `risk:high` on a PR or issue, and the
verifier's cap reached with a blocker or major open.

## Cloud worker

Cloud worker: c03634ba708ed6b23439fc16f2fa6f7a, gate test

The agent is given by id: this server holds several agents called `claude-cloud`, and `omnigent_agent.py` refuses a name more than one agent holds. This one is the `claude-cloud` agent whose tools are served from this host.

Workers code and run `mise run test` in Claude cloud sessions, in an environment that holds no secrets, so their compute leaves the owner's machines. The lead and the Codex verifier stay on the host (`engineering/skills/engineering-loop/SKILL.md`, Cloud worker). Cold, a session runs the gate in about 1–2.5 minutes after a setup of about 25 s. These stay with the host lead: `approvals.py`, because GraphQL answers 403 in the VM; the signed land; the live-agent suites (`test-engineering-agents`, `test-chief-of-staff-live`), which need logged-in harnesses and Omnigent; and the full gate.

A cloud session clones the GitHub branch of the workspace it starts from, in the environment named by that workspace's untracked `.claude/settings.local.json` (`{"remote": {"defaultEnvironmentId": "<id>"}}`). So the lead copies that file into each new worktree and pushes the branch before it starts a worker. `.claude/cloud-setup.sh` is the environment's setup script. The environment keeps its own copy, so a change is applied with `POST /v1/environment_providers/<id>`, with `config.init_script` set to the file. Undo: delete the line.
