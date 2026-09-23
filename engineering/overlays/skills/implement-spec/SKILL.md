---
name: implement-spec
description: "Implement a spec and its tickets as one PR on a single branch, working the ticket graph's frontier concurrently."
disable-model-invocation: true
---

# Implement Spec

Deliver one PR, on one branch, that implements the whole spec. The spec's tickets are a **task graph** of blocking edges, not a list of steps: every ticket whose blockers are done is on the **frontier** and can start.

1. Read the spec and enough of the tickets to see the graph.
2. Create the branch and a draft PR that closes the spec issue and every ticket.
3. Work the frontier. Hand tickets that can run in parallel, or would flood your context, to background implementers, each in its own worktree on its own branch; do a small ticket yourself when that is quicker. Exploration the tickets need (code or external docs) can go to a helper that writes markdown notes to a directory outside the repo, where every later implementer can read them.
4. Merge each finished branch into the PR branch (conflicts per the `resolving-merge-conflicts` skill), then start whatever the merge put on the frontier.
5. When every ticket is merged, run the `code-review` skill on the PR branch against its base and fix every finding, in one implementer pass or yourself.
6. Mark the PR ready for review, with its body per the `pr` skill, and remove the implementer worktrees.

Brief helpers with **context pointers** (the spec, the ticket, research notes, earlier commits) rather than copies of what those already say, and keep messages to and from them short.
