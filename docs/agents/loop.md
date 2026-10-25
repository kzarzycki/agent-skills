# Loop facts

The engineering loop's values for this repo. `engineering/skills/engineering-loop/SKILL.md`
(Approvals and proof) defines what each line approves and what still waits for the owner.

Orchestration backend: omnigent

Worker model: mid for size:S or smaller

A tier, not a model id, so the line holds for every family and each new generation (#247): today
`claude-sonnet-5-5` for Claude and `gpt-6.1-sol` for Codex (#250: Sol is Codex's `top`, the only
tier model of its newest generation, 6.1). A one-week trial to 2026-10-27,
decided under the owner's standing decision of 2026-10-20 (chief-of-staff session 13cd3ad1) to
approve reversible progress (#245, evidence on #228): a Sonnet worker cost about half an Opus
one per item. At its end, telemetry compares verifier passes per PR against the Opus workers of
2026-10-18..20. Leads and verifiers keep their defaults.

## Approvals

- spec: auto
- merge: auto unless risk
- risk: verifier or path .github/** or path CODEOWNERS or path docs/agents/loop.md

The owner's reason: specs and merges are approved by policy, so work doesn't stop on them,
and the owner sees only what no automated check can settle (#330). The verifier judges each
change's risk (`verifier`); CI, code owners and this file's own approval rules always reach
the owner, which under `spec: auto` means their spec does. Also waiting for the owner: a
spec opened by an account without write access, `risk:high` on a PR or issue, and the
verifier's cap reached with a blocker or major open.
