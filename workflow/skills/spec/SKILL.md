---
name: spec
description: Use when a vague work item needs product/user clarification before planning or implementation.
---

# Spec

Turn a vague work item into a Decision Spec. Reuse existing project docs and code facts; ask the user only for product choices tools cannot answer.

This file is the phase contract. Whoever executes the phase -- the interviewer agent or the workflow engine in-situ -- follows it; executors add their own run/return mechanics, not rules.

## Execution

The interviewer teammate owns the phase by default: it interviews the user, writes the draft
`01-DECISION-SPEC.md`, then runs this plugin's `spec-phase` saved workflow (args/returns in its
meta; `scriptPath` fallback when the name is not in the session registry). The workflow runs
the convergence loop -- author rework from the `_phases/spec/` record, format gate, both
reviewers in parallel, rework cycles -- until it returns `pass`, `needs-user`, or the rework
cap. `needs-user` and the cap go back to the user over the interview channel. The user gate is
the artifact path + verdicts (plus the HTML gate page when rendered); the artifact content
stays out of the orchestrator's context. In-situ fallback (no tmux): the engine interviews
itself, then runs the same workflow.

## Contract

- Research proposal first: propose buckets, ask the user to approve/narrow/reject, then run only approved buckets.
- Interview composition: the interview runs with the content of BOTH `superpowers:brainstorming` (domain coverage -- purpose, approaches, architecture/components/data flow/error handling/testing) and `mattpocock-skills:grill-me` (adversarial depth, one adaptive question at a time) loaded in context -- via an agent's `skills` preload or explicit Skill calls. Record in `_phases/spec/interview-notes.md` which were loaded and what each contributed; the review gate checks this record. If a skill cannot be loaded (plugin not installed), the executor records "could not load X" in `interview-notes.md`; reviewers treat that record as `needs-user` (escalate), not `needs-rework`. Architecture answers gathered during the interview are recorded as inputs for Tech Options, not decided in Spec.
- Interview record: record the interview decisions, answers, and rejected alternatives in `_phases/spec/interview-notes.md` -- it is the author's and reviewers' input in the convergence loop.
- Preserve the original question/problem and rejected alternatives.
- Root human artifact: `01-DECISION-SPEC.md` only.
- Internal notes, research, and review evidence go under underscore dirs.

## Spec shape and language

- Sections are defined in `../../contracts/decision-spec.json` (relative to this skill's base dir); names and order are normative there.
- Structure over prose: tables for enumerable facts (alternative | why rejected; risk | routed to), bullet/numbered lists for parallel items, prose only where narrative genuinely explains. Scannable, not decorated.
- Brainstorming's scaling: a few sentences for simple sections, ~300 words for nuanced ones.
- Current truth only: history and superseded decisions live in the Approval record, each decision stated once.

## Format gate

Before the review gate: `mdsmith check -c <plugin>/contracts/mdsmith.yml <work-item>/01-DECISION-SPEC.md`, where `<plugin>` = the installed plugin root (the dir containing `contracts/`) and `<work-item>` = `.workflow/<id>/`. Install hints and rule semantics are in the config header. MDS020 = contract violation, fix first. MDS023/MDS036/MDS056 = language budget, rework input. Beyond section names, mdsmith enforces document shape: line 1 is an H1 title, sections are H2 in contract order, no YAML frontmatter, no extra H2s. Gate owner: the phase loop runs the gate as its own step after each author round and routes violations back to the author; the testability reviewer verifies it, does not own it. Without mdsmith installed, verify sections manually against the contract JSON.

## Review gate

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Intent Reviewer (`agents/intent-reviewer.md`) | Intent and scope fidelity; interview composition record |
| Testability Reviewer (`agents/testability-reviewer.md`) | Observable acceptance criteria; format gate |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`. Semantics: `needs-user` = a product question only the user can answer, or a contradiction with user-stated intent; `needs-rework` = a fixable defect. Aggregation: any `needs-user` wins, else any `needs-rework`, else `pass`. Rework cap: 2 per phase; exceeding it escalates to the user.
