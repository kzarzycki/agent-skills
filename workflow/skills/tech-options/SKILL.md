---
name: tech-options
description: Use when approved needs require comparing implementation approaches before planning.
---

# Tech Options

Compare ways to satisfy the approved Decision Spec. Start from approved needs, not a favored tool.

## Contract

- Input: approved `01-DECISION-SPEC.md`.
- Output: one evolving root human artifact, `02-TECH-OPTIONS.md`.
- Research multiple option families: first-party implementation, existing OMP/Pi capabilities, reusable skills/agents, and third-party packages as references.
- Treat third-party workflow packages as references only until safety audit, compatibility check, wrapper design, and user approval.
- Include artifact UX assessment: root numbered human artifacts, underscore internals, no routine history.
- If findings change the product need, trigger a focused Discuss addendum instead of silently changing the spec.

## Tech Options sections

- Needs
- Options considered
- Scorecard
- Recommended option
- Rejected alternatives
- Risks
- Approval record

## Scorecard

Score each option against approved needs:

| Need | What to check |
|---|---|
| Limited human artifacts | Does it avoid review-packet sprawl? |
| Hidden internals | Can runtime files stay under underscore dirs? |
| Approval gates | Can it pause for human decisions? |
| Resumability | Can it restart from durable state? |
| Model-agent orchestration | Can OMP steer agents/filters programmatically? |
| Maintainability | Is the surface small and first-party enough? |

## Review gate

Run fixed reviewers:

| Reviewer | Checks |
|---|---|
| Reuse/Coverage Reviewer | Candidate breadth, source coverage, needs mapping, artifact UX |
| Fit/Risk Reviewer | Capability fit, lock-in, safety/audit risk, reversibility, user-overwhelm risk |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`.
