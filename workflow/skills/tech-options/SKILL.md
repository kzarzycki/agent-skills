---
name: tech-options
description: Use when approved needs require comparing implementation approaches before planning.
---

# Tech Options

Compare ways to satisfy the approved Decision Spec. Start from approved needs, not a favored tool.

This file is the phase contract. Whoever executes the phase -- the analyst agent, the workflow engine in-situ, or the OMP driver -- follows it; executors add their own run/return mechanics, not rules.

## Contract

- Input: approved `01-DECISION-SPEC.md`.
- Output: one evolving root human artifact, `02-TECH-OPTIONS.md`.
- Research multiple option families: first-party implementation, existing OMP/Pi capabilities, reusable skills/agents, and third-party packages as references.
- Treat third-party workflow packages as references only until safety audit, compatibility check, wrapper design, and user approval.
- Include artifact UX assessment: root numbered human artifacts, underscore internals, no routine history.
- If findings change the product need, trigger a focused Discuss addendum instead of silently changing the spec.

## Artifact shape and language

- Sections are defined in `../../contracts/tech-options.json` (relative to this skill's base dir); names and order are normative there.
- Structure over prose: the Scorecard is always a table; enumerable facts in tables (option | tradeoff; need | coverage), parallel items in lists with bold lead-ins, prose only where narrative genuinely explains.
- A few sentences for simple sections, ~300 words for nuanced ones; short sentences.
- Current truth only: history and superseded recommendations live in the Approval record.

## Format gate

Before the review gate: `mdsmith check -c ../../contracts/mdsmith.yml 02-TECH-OPTIONS.md` (config relative to this skill's base dir; install hints and rule semantics in the config header). MDS020 = contract violation, fix first. MDS023/MDS036/MDS056 = language budget, rework input. Without mdsmith installed, verify sections manually against the contract JSON.

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

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Reuse/Coverage Reviewer (`agents/reuse-coverage-reviewer.md`) | Candidate breadth, source coverage, needs mapping |
| Fit/Risk Reviewer (`agents/fit-risk-reviewer.md`) | Capability fit, lock-in, safety/audit risk, reversibility |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`.
