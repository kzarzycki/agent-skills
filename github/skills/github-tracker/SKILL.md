---
name: github-tracker
description: The GitHub tracker and forge conventions the engineering loop and the gatekeeper run on - issue, label, assignee, review-trail and board operations with gh, label sync (labels.py) and board moves (board.py), and the apply step that turns a split manifest into a GitHub issue batch or into local ticket files (issue_batch.py, local.md). Use when a project's docs/agents/issue-tracker.md names GitHub or local files as its tracker, when applying a split manifest, or when syncing a repo's labels or moving an issue on its board.
metadata:
  requires: "gh uv"
---

# GitHub tracker

[github.md](github.md) is the GitHub tracker's realization file: how the loop's issue
conventions are done with `gh`. A project whose `docs/agents/issue-tracker.md` says
`Tracker: GitHub (github-tracker's github.md)`, or `engineering-loop's github.md` as before
this package split, follows it in place.

Three scripts, each run with `uv run <this skill's folder>/scripts/<name>.py` from the
checkout:

- `scripts/labels.py` (reads the label names and tracker settings through the `gatekeeper`
  skill's `gatekeeper.py`, found where the host installed that skill, and exits naming it when
  it is missing) syncs the repo's labels with the loop's fixed set and the project's
  components and categories (github.md, Labels).
- `scripts/board.py` moves an issue to a board column, or prints the loop's column for it
  (github.md, Board); it reads them the same way.
- `scripts/issue_batch.py` validates a split manifest and prints the canonical issue batch with
  its `batch_sha256` and markers (`github`), or writes the manifest as numbered ticket files
  (`local`). Run `github` whenever github.md's Publish an issue batch starts from a manifest;
  it is stdlib only and calls no tracker.

[local.md](local.md) is the realization for a project that keeps tickets as local files: read
it when `docs/agents/issue-tracker.md` names local files as the tracker, to apply a split
manifest with `issue_batch.py local`.

Each docstring is its manual.
