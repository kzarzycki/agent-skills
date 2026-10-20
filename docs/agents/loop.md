# Loop facts

The engineering loop's values for this repo. `engineering/skills/engineering-loop/SKILL.md`
(Approvals and proof) defines what each line approves and what still waits for the owner.

Orchestration backend: omnigent

Worker model: mid for size:S or smaller

A tier, not a model id, so the line holds for every family and each new generation (#247): today
`claude-sonnet-5-5` for Claude and `gpt-6.1-sol` for Codex. A one-week trial to 2026-10-27,
decided under the owner's standing decision of 2026-10-20 (chief-of-staff session 13cd3ad1) to
approve reversible progress (#245, evidence on #228): a Sonnet worker cost about half an Opus
one per item. At its end, telemetry compares verifier passes per PR against the Opus workers of
2026-10-18..20. Leads and verifiers keep their defaults.

## Approvals

- spec: auto
- merge: auto unless risk

The owner's reason: specs and merges are approved by policy, so work doesn't stop on them.
No `risk:` rule is set; what still waits for the owner is what the loop builds in: a spec
opened by an account without write access, `risk:high` on a PR or issue, and the verifier's
cap reached with a blocker or major open.
