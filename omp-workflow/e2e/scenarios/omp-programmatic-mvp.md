# Live E2E Scenario — OMP Programmatic Workflow MVP

## Work item prompt

Build a programmatic OMP workflow MVP. It starts from a vague work item, produces a Decision Spec, reviews it with fixed model reviewers, produces Tech Options, reviews those with fixed model reviewers, has human gates for research approval, Decision Spec approval, Tech Options research approval, and Tech Options approval, then stops at planning_pending. Human-facing files are limited to 01-DECISION-SPEC.md and 02-TECH-OPTIONS.md. Runtime artifacts stay under underscore directories. Reuse skill/agent prompt shapes where possible.

## Human simulator guidance

Approve research buckets for reusable skills/agents, OMP programmatic core, and artifact policy. Approve Decision Spec only if it has Question / problem, Rejected alternatives, Acceptance criteria, and agreed gate sequence. Approve Tech Options if it compares multiple families, recommends small first-party OMP core, and avoids extra human-facing artifacts. If model reviewers request rework, let workflow-advance regenerate and review again.

## Expected result

Final state: planning/planning_pending. Root artifacts inside this run: 01-DECISION-SPEC.md and 02-TECH-OPTIONS.md only, plus underscore runtime dirs.
