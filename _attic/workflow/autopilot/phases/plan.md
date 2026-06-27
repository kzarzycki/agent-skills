Read the approved spec at {{ITEM}}/spec.md. Produce an implementation plan as a
list of bite-sized, independently-committable tasks. Detect the repo's
test/build command (verifyCmd) from config files; if the spec names one, prefer it.

For EACH task provide:
- id: short kebab-case
- desc: what to build, concrete enough to implement without re-reading the spec
- deps: ids of tasks that must complete first ([] if none)
- fileScope: exact relative paths this task will create or modify (used to
  parallelize; keep scopes disjoint between tasks that could run together)
- acceptance: testable conditions that prove the task is done

Write the plan to {{ITEM}}/plan.md (human-readable) AND return the structured object.
Apply YAGNI: no task outside the spec's scope.
