---
name: discuss
description: Use when a vague work item needs product/user clarification before planning or implementation.
---

# Discuss

Turn a vague work item into a Decision Spec. Reuse existing project docs and code facts; ask the user only for product choices tools cannot answer.

This file is the phase contract. Whoever executes the phase -- the interviewer agent, the workflow engine in-situ, or the OMP driver -- follows it; executors add their own run/return mechanics, not rules.

## Contract

- Research proposal first: propose buckets, ask the user to approve/narrow/reject, then run only approved buckets.
- Interview composition: the interview runs with the content of BOTH `superpowers:brainstorming` (domain coverage -- purpose, approaches, architecture/components/data flow/error handling/testing) and `mattpocock-skills:grill-me` (adversarial depth, one adaptive question at a time) loaded in context -- via an agent's `skills` preload or explicit Skill calls. Record in `_phases/discuss/interview-notes.md` which were loaded and what each contributed; the review gate checks this record.
- Preserve the original question/problem and rejected alternatives.
- Root human artifact: `01-DECISION-SPEC.md` only.
- Internal notes, research, and review evidence go under underscore dirs.
- Standalone `/discuss` must not call `workflow-start` or `workflow-resume`.

## Spec shape and language

- Sections are defined in `../../contracts/decision-spec.json` (relative to this skill's base dir); names and order are normative there.
- Structure over prose: tables for enumerable facts (alternative | why rejected; risk | routed to), bullet/numbered lists for parallel items, prose only where narrative genuinely explains. Scannable, not decorated.
- Brainstorming's scaling: a few sentences for simple sections, ~300 words for nuanced ones.
- Current truth only: history and superseded decisions live in the Approval record, each decision stated once.

## Format gate

Before the review gate: `mdsmith check -c ../../contracts/mdsmith.yml 01-DECISION-SPEC.md` (config relative to this skill's base dir; install hints and rule semantics in the config header). MDS020 = contract violation, fix first. MDS023/MDS036/MDS056 = language budget, rework input. Without mdsmith installed, verify sections manually against the contract JSON.

## Review gate

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Intent Reviewer (`agents/intent-reviewer.md`) | Intent and scope fidelity; interview composition record |
| Testability Reviewer (`agents/testability-reviewer.md`) | Observable acceptance criteria; format gate |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`.
