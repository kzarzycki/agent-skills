---
name: tech-design
description: Use when an approved spec needs a technical design -- architecture and technology choices grounded in compared options -- before planning.
---

# Tech Design

Design how to satisfy the approved Decision Spec: compare candidate approaches, choose one, and record the resulting design -- architecture, components, and the technical decisions that bind it. Options research is the evidence; the chosen design is the product. Start from approved needs, not a favored tool.

This file is the phase contract. Whoever executes the phase -- the designer agent or the workflow engine in-situ -- follows it; executors add their own run/return mechanics, not rules.

## Execution

Delegated by default: the engine stays orchestrator and runs this plugin's `tech-design-phase`
saved workflow (args/returns in its meta; `scriptPath` fallback when the name is not in the
session registry). The workflow runs the whole autonomous loop -- the designer authors
`02-TECH-DESIGN.md`, the format gate checks it, both reviewers judge it independently in
parallel, rework cycles -- until it returns `pass`, `needs-user`, or the rework cap.
The engine never authors or reviews in its own context; it only presents the result at the
user gate. Fallbacks, same contract: spawn the designer as a teammate (no Workflow tool), or
run in-situ (no agents at all).

## Contract

- Input: approved `01-DECISION-SPEC.mdx`, plus any architecture answers the Spec interview recorded as design inputs.
- Output: one evolving root human artifact, `02-TECH-DESIGN.md`.
- Research multiple option families: first-party implementation, capabilities of the existing runtime/platform, reusable in-repo skills/agents/components, and third-party packages as references.
- Treat third-party workflow packages as references only until safety audit, compatibility check, wrapper design, and user approval; the same rule applies to any third-party dependency.
- The chosen design must follow from the scorecard: pick the winning option and commit it to a concrete shape -- architecture sketch, components and their responsibilities, data flow. H3 subsections inside Chosen design are free-form.
- Key technical decisions records every binding choice beyond the headline option (libraries, protocols, storage, naming) as decision | choice | rationale rows; a decision without a stated alternative is a smell.
- Include artifact UX assessment: how the design affects the user-facing artifact experience. The work-item layout rule stands: root numbered human artifacts, underscore internals, no routine history.
- If findings change the product need, trigger a focused Spec addendum instead of silently changing the spec.

## Artifact shape and language

- Sections are defined in `../../contracts/tech-design.json` (relative to this skill's base dir); names and order are normative there.
- Structure over prose: the Scorecard is always a table; Key technical decisions is always a table; enumerable facts in tables (option | tradeoff; need | coverage), parallel items in lists with bold lead-ins, prose only where narrative genuinely explains. A small diagram-as-text (component list or ASCII sketch) is welcome inside Chosen design.
- A few sentences for simple sections, ~300 words for nuanced ones; short sentences.
- Current truth only: history and superseded designs live in the Approval record.

## Format gate

Before the review gate: `mdsmith check -c <plugin>/contracts/mdsmith.yml <work-item>/02-TECH-DESIGN.md`, where `<plugin>` = the installed plugin root (the dir containing `contracts/`) and `<work-item>` = `.workflow/<id>/`. Install hints and rule semantics are in the config header. MDS020 = contract violation, fix first. MDS023/MDS036/MDS056 = language budget, rework input. Beyond section names, mdsmith enforces document shape: line 1 is an H1 title, sections are H2 in contract order, no YAML frontmatter, no extra H2s. Gate owner: the author runs the gate itself after each writing round and fixes structure violations before returning; on a fresh draft with no author round, the phase loop runs the gate in parallel with the reviewers; reviewers verify it, do not own it. Without mdsmith installed, verify sections manually against the contract JSON.

## Scorecard

Derive the needs from the approved Decision Spec -- its Constraints and Acceptance criteria
sections, plus any need the spec's Goal makes explicit. One scorecard row per need, one column
per option, each cell a short verifiable judgment. Do not reuse another work item's needs list;
if the spec yields fewer than three needs, that is a Spec gap -- raise it instead of padding.

## Review gate

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Reuse/Coverage Reviewer (`agents/reuse-coverage-reviewer.md`) | Candidate breadth, source coverage, needs mapping |
| Fit/Risk Reviewer (`agents/fit-risk-reviewer.md`) | Design follows from evidence; capability fit, lock-in, safety/audit risk, reversibility |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`. Semantics: `needs-user` = a product question only the user can answer, or a contradiction with user-stated intent; `needs-rework` = a fixable defect. Aggregation: any `needs-user` wins, else any `needs-rework`, else `pass`. Rework cap: 2 per phase; exceeding it escalates to the user.
