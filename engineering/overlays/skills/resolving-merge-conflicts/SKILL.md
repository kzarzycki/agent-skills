---
name: resolving-merge-conflicts
description: "Resolve an in-progress git merge or rebase conflict by each side's intent, then finish the operation. Use when a merge or rebase stops on conflicts."
---

Resolve the conflicts by intent, not by picking lines, then finish the operation.

- For each conflict, find why each side changed: commit messages, PRs, the original issues or tickets.
- Keep both intents where they are compatible. Where they are not, keep the one that matches the merge's stated goal and note the trade-off. Don't invent new behaviour.
- Always resolve; don't `--abort`.
- Run the project's checks (typically typecheck, tests, format) and fix what the merge broke.
- Stage and commit; for a rebase, continue until every commit is applied.
