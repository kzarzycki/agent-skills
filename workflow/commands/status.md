Show the status of workflow work-items in this project.

Scan `.workflow/<yyyy-mm-dd>-<slug>/` directories and present a concise overview. For each work item, most recent first:

1. Which phase artifacts exist — `01-DECISION-SPEC.mdx` (Spec), `02-TECH-DESIGN.mdx` (Tech Design).
2. The furthest phase reached and its gate state — read the verdicts in `_reviews/<phase>/<reviewer>.md` (`intent`/`testability` for `spec`; `reuse-coverage`/`fit-risk` for `tech_design`). Both `pass` with no later artifact = awaiting user approval; any `needs-user` = blocked on the user.
3. Anything still open (an unresolved gate, a `needs-user`).

Present in this format:

```
## Work items — .workflow/
| Item | Phase | Latest artifact | Gate |
|------|-------|-----------------|------|
| 2026-06-25-borrow-feedbacks | Tech Design | 02-TECH-DESIGN.mdx | reviewers pass — awaiting approval |

## Suggested next
[the open gate to act on, or the next phase to run]
```

If `.workflow/` does not exist or is empty, say: "No workflow work-items found. Start one with the `workflow:workflow` skill."
