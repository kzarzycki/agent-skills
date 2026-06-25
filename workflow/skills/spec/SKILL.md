---
name: spec
description: Use when a vague work item needs product/user clarification before planning or implementation.
---

# Spec

Turn a vague work item into a Decision Spec. Reuse existing project docs and code facts; ask the user only for product choices tools cannot answer.

This file is the phase contract. Whoever executes the phase -- the interviewer agent or the workflow engine in-situ -- follows it; executors add their own run/return mechanics, not rules.

## Execution

The interviewer teammate owns the phase by default: it interviews the user, writes the draft
`01-DECISION-SPEC.mdx`, then runs this plugin's `spec-phase` saved workflow (args/returns in its
meta; `scriptPath` fallback when the name is not in the session registry). The workflow runs
the convergence loop -- author rework from the `_phases/spec/` record, format gate, both
reviewers in parallel, rework cycles -- until it returns `pass`, `needs-user`, or the rework
cap. `needs-user` and the cap go back to the user over the interview channel. The user gate is
the artifact path + verdicts (plus the rendered MDX gate page); the artifact content
stays out of the orchestrator's context. In-situ fallback (no tmux): the engine interviews
itself, then runs the same workflow.

## Contract

- Research proposal first: propose buckets, ask the user to approve/narrow/reject, then run only approved buckets.
- Interview composition: the interview runs with the content of BOTH `superpowers:brainstorming` (domain coverage -- purpose, approaches, architecture/components/data flow/error handling/testing) and `mattpocock-skills:grill-me` (adversarial depth, one adaptive question at a time) loaded in context -- via an agent's `skills` preload or explicit Skill calls. Record in `_phases/spec/interview-notes.md` which were loaded and what each contributed; the review gate checks this record. If a skill cannot be loaded (plugin not installed), the executor records "could not load X" in `interview-notes.md`; reviewers treat that record as `needs-user` (escalate), not `needs-rework`. Architecture answers gathered during the interview are recorded as inputs for Tech Design, not decided in Spec. Pacing: questions resolving the same decision branch may be batched into one AskUserQuestion call (max 4); grill-me's adaptivity applies between branches, so don't batch across a dependency.
- Interview record: record the interview decisions, answers, and rejected alternatives in `_phases/spec/interview-notes.md` -- it is the author's and reviewers' input in the convergence loop.
- Testable rationale: a decision justified by a capability must have an acceptance criterion that exercises that capability. The reason for a choice gets verified, not just its happy-path result.
- Preserve the original question/problem and rejected alternatives.
- Root human artifact: `01-DECISION-SPEC.mdx` only.
- Internal notes, research, and review evidence go under underscore dirs.

## Spec shape and language

- The spec is **rich MDX** (`01-DECISION-SPEC.mdx`), authored with the `communicating-in-mdx` skill loaded. Defer to that skill's "when MDX beats Markdown" judgment: reach for a component where it lands harder than prose, not for decoration. The body is still contract-clean Markdown underneath — H1 title on line 1, the H2 sections below, no extra H2s, no frontmatter.
- Sections are defined in `../../contracts/decision-spec.json` (relative to this skill's base dir); names and order are normative there.
- Diagrams are part of the spec: render architecture / data flow / sequence as a ` ```mermaid ` fence inside the relevant section (Current context or Desired behavior). The fence is portable Markdown and renders in the runner.
- Structure over prose: tables for enumerable facts (alternative | why rejected; risk | routed to), bullet/numbered lists for parallel items, a `<Callout>` for the load-bearing intent or a decision the user must not miss, prose only where narrative genuinely explains. Scannable, not decorated.
- Brainstorming's scaling: a few sentences for simple sections, ~300 words for nuanced ones.
- Current truth only: history and superseded decisions live in the Approval record, each decision stated once. The gate page (not the spec body) carries the changelog and the cross-round `<DocDiff>`.

## Format gate

Before the review gate: `mdsmith check -c <plugin>/contracts/mdsmith.yml <work-item>/01-DECISION-SPEC.mdx`, where `<plugin>` = the installed plugin root (the dir containing `contracts/`) and `<work-item>` = `.workflow/<id>/`. Install hints and rule semantics are in the config header. mdsmith reads MDX out of the box: JSX components and ` ```mermaid ` fences pass through, and the H2 structure check still applies. MDS020 = contract violation, fix first. MDS023/MDS036/MDS056 = language budget, rework input. MDS025 (table alignment) is advisory, auto-fixable with `mdsmith fix`. Beyond section names, mdsmith enforces document shape: line 1 is an H1 title, sections are H2 in contract order, no YAML frontmatter, no extra H2s. Gate owner: the author runs the gate itself after each writing round and fixes structure violations before returning; on a fresh draft with no author round, the phase loop runs the gate in parallel with the reviewers; the testability reviewer verifies it, does not own it. Without mdsmith installed, verify sections manually against the contract JSON.

## Review gate

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Intent Reviewer (`agents/intent-reviewer.md`) | Intent and scope fidelity; interview composition record |
| Testability Reviewer (`agents/testability-reviewer.md`) | Observable acceptance criteria; format gate |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`. Semantics: `needs-user` = a product question only the user can answer, or a contradiction with user-stated intent; `needs-rework` = a fixable defect. Aggregation: any `needs-user` wins, else any `needs-rework`, else `pass`. Rework cap: 2 per phase; exceeding it escalates to the user.
