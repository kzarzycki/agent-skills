Independent verification. Do NOT read any implementer self-assessment.
Read the acceptance criteria for every task in {{ITEM}}/plan.md and the spec at
{{ITEM}}/spec.md. Honor project rules:
{{RULES_BUNDLE}}

For each acceptance criterion, check exists / real / wired:
- exists: the artifact (function, endpoint, file, behavior) is present.
- real: it actually does the thing (not a stub), evidenced by running `{{VERIFY_CMD}}`
  or exercising it.
- wired: it is reachable from where the spec says it should be used.

Write {{ITEM}}/verify.md with per-criterion evidence and PASS/FAIL.
Return verdict pass only if every criterion passes.
