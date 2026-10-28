# Local-files tracker

The realization for a project whose `docs/agents/issue-tracker.md` keeps tickets as files
in the repo instead of on a tracker. It applies a split manifest (docs/layers.md, Split
manifest), the way github.md, Publish an issue batch, does for GitHub, so the skill that
splits writes no ticket files.

Run `uv run <this skill's folder>/scripts/issue_batch.py local <manifest> [--out <dir>]
[--status <name>]` from the checkout. It validates the manifest exactly as the GitHub
apply step does (same code, same refusals, nothing written on a refusal) and writes one
file per item at `<dir>/<NN>-<slug>.md`, never one combined file:

- `<dir>` defaults to `issues/` beside the manifest, so a manifest at
  `.scratch/<feature-slug>/split-manifest.json` gives `.scratch/<feature-slug>/issues/`.
- `NN` counts from `01` in dependency order (blockers first, ties by title bytes), the
  order github.md's canonical batch uses, so both trackers number a manifest alike.
- Each file is the local ticket template, filled from the spec's `## What to build`,
  `## Acceptance criteria` and `## Blocked by` sections (a spec with none of them becomes
  the "What to build" text):

```
# <NN>: <Ticket title>

**What to build:** the end-to-end behaviour this ticket makes work.

**Blocked by:** the numbers and titles of the gating tickets, or "None (can start immediately)".

**Status:** ready-for-agent

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2
```

`Status` is `ready-for-agent` unless `--status` names another. A rerun overwrites the same
files, so it is safe to repeat.
