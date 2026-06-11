---
name: tech-options
description: Use when approved needs require comparing implementation approaches before planning.
---

# Tech Options

Compare ways to satisfy the approved Decision Spec. Start from approved needs, not a favored tool.

This file is the phase contract. Whoever executes the phase -- the analyst agent or the workflow engine in-situ -- follows it; executors add their own run/return mechanics, not rules.

## Execution

Delegated by default: the engine stays orchestrator and runs this plugin's saved workflow
`Workflow({ name: 'tech-options-phase', args: { workId, pluginRoot, instructions?, contentFrozen? } })`
(`pluginRoot` = the installed plugin dir containing `contracts/`; fall back to
`scriptPath: <pluginRoot>/workflows/tech-options-phase.js` when the name is unregistered).
The workflow runs the whole autonomous loop -- analyst authors `02-TECH-OPTIONS.md`, the format
gate checks it, both reviewers judge it independently in parallel, rework cycles until pass /
`needs-user` / the rework cap -- and returns `{ status, rounds, verdicts, formatGate, artifact }`.
The engine never authors or reviews in its own context; it only presents the result at the
user gate. Fallbacks, same contract: spawn the analyst as a teammate (no Workflow tool), or
run in-situ (no agents at all).

## Contract

- Input: approved `01-DECISION-SPEC.md`.
- Output: one evolving root human artifact, `02-TECH-OPTIONS.md`.
- Research multiple option families: first-party implementation, capabilities of the existing runtime/platform, reusable in-repo skills/agents/components, and third-party packages as references.
- Treat third-party workflow packages as references only until safety audit, compatibility check, wrapper design, and user approval; the same rule applies to any third-party dependency.
- Include artifact UX assessment: how each option affects the user-facing artifact experience. The work-item layout rule stands: root numbered human artifacts, underscore internals, no routine history.
- If findings change the product need, trigger a focused Discuss addendum instead of silently changing the spec.

## Artifact shape and language

- Sections are defined in `../../contracts/tech-options.json` (relative to this skill's base dir); names and order are normative there.
- Structure over prose: the Scorecard is always a table; enumerable facts in tables (option | tradeoff; need | coverage), parallel items in lists with bold lead-ins, prose only where narrative genuinely explains.
- A few sentences for simple sections, ~300 words for nuanced ones; short sentences.
- Current truth only: history and superseded recommendations live in the Approval record.

## Format gate

Before the review gate: `mdsmith check -c <plugin>/contracts/mdsmith.yml <work-item>/02-TECH-OPTIONS.md`, where `<plugin>` = the installed plugin root (the dir containing `contracts/`) and `<work-item>` = `.workflow/<id>/`. Install hints and rule semantics are in the config header. MDS020 = contract violation, fix first. MDS023/MDS036/MDS056 = language budget, rework input. Beyond section names, mdsmith enforces document shape: line 1 is an H1 title, sections are H2 in contract order, no YAML frontmatter, no extra H2s. Gate owner: the author runs the gate pre-review; reviewers verify it, do not own it. Without mdsmith installed, verify sections manually against the contract JSON.

## Scorecard

Derive the needs from the approved Decision Spec -- its Constraints and Acceptance criteria
sections, plus any need the spec's Goal makes explicit. One scorecard row per need, one column
per option, each cell a short verifiable judgment. Do not reuse another work item's needs list;
if the spec yields fewer than three needs, that is a Discuss gap -- raise it instead of padding.

## Review gate

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Reuse/Coverage Reviewer (`agents/reuse-coverage-reviewer.md`) | Candidate breadth, source coverage, needs mapping |
| Fit/Risk Reviewer (`agents/fit-risk-reviewer.md`) | Capability fit, lock-in, safety/audit risk, reversibility |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`. Semantics: `needs-user` = a product question only the user can answer, or a contradiction with user-stated intent; `needs-rework` = a fixable defect. Aggregation: any `needs-user` wins, else any `needs-rework`, else `pass`. Rework cap: 2 per phase; exceeding it escalates to the user.
