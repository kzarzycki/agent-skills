---
name: discuss
description: Use when a vague work item needs product/user clarification before planning or implementation.
---

# Discuss

Turn a vague work item into a Decision Spec. Reuse existing project docs and code facts; ask the user only for product choices tools cannot answer.

## Contract

- Research proposal first: propose buckets, ask the user to approve/narrow/reject, then run only approved buckets.
- Grill with one adaptive question at a time. Prefer `mattpocock-skills:grill-me` or the local interviewer agent when available.
- Preserve the original question/problem and rejected alternatives.
- Root human artifact: `01-DECISION-SPEC.md` only.
- Internal notes, research, and review evidence go under underscore dirs.
- Standalone `/discuss` must not call `workflow-start` or `workflow-resume`.

## Decision Spec sections

- Goal
- Question / problem
- User and value
- Current context
- Desired behavior
- Key decisions and rationale
- Rejected alternatives
- Non-goals
- Constraints
- Acceptance criteria
- Risks / open questions
- Approval record

## Review gate

Run fixed reviewers:

| Reviewer | Checks |
|---|---|
| Intent Reviewer | User intent, scope, original problem, rejected alternatives |
| Testability Reviewer | Observable acceptance criteria, edge cases, verification path |

Verdicts are exactly: `pass`, `needs-rework`, `needs-user`.
