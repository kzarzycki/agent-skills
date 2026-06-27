---
name: autopilot
description: Autonomous brainstorm→PR pipeline. Invoke on /autopilot. Runs an interactive brainstorming session to an approved spec, then launches a background Workflow that plans, builds, reviews, verifies, and opens a PR with no further human input. Resumes a halted run when re-invoked.
---

# autopilot

One interactive step (brainstorming), then an unsupervised background engine that
plans → adversarially reviews the plan → executes in dependency waves → runs a
multi-dimension code review → independently verifies → opens a PR.

## Flow

First classify the invocation into one of three modes:

- **Resume** — a feature dir has `run.json` with a non-`done` status and a `blocker.md`.
  Relaunch (step 6) with `resumeFromRunId` from `run.json`; no brainstorming.
- **Increment** — the most recent feature item is `done`/`blocked`/`in_progress` with a
  `prUrl` in `run.json`, AND the prompt reads as fixes/refinements to that work ("fix
  this and that", a bug, a tweak). Propose: *"Iterate on `<item>` (PR #N)? Or start a
  new feature?"* and confirm. An explicit new feature starts fresh.
- **New** — no matching item, or the user starts a new feature.

### New feature

1. **Brainstorm.** Invoke `superpowers:brainstorming`. Save the approved spec to
   `.work/<YYYY-MM-DD>-<feature-slug>/spec.md` (NOT `docs/superpowers/specs/`).
2. **Create the feature dir** with an `iterations/` subdir and **`ITEM.md`:**
   - `## Status: planning`
   - `## Progress` — unchecked: `Plan created`, `Plan reviewed`, `Executed`, `Reviewed`, `Verified`, `Finished`
   - `## Log` — empty
3. **Detect `verifyCmd`** from repo config (package.json scripts, Makefile, pyproject…);
   if undetectable, leave it to the plan phase.
4. **Launch** (step 6) with `increment: false`.

### Increment

1. **Scoped brainstorm.** Invoke `superpowers:brainstorming`, telling it to read the
   existing `spec.md` as context and grill ONLY on the new increment. Append the result
   as a new `## Iteration N` section to the same `spec.md` (do not rewrite earlier sections).
2. **Reopen** the item: leave `ITEM.md` history intact (the engine flips status back to
   `in_progress`). Stay on the same feature branch.
3. **Launch** (step 6) with `increment: true` and `iteration: N` (next iteration number).

### Launch (step 6)

```
Workflow({
  scriptPath: "<this skill dir>/engine.js",
  args: {
    itemDir: ".work/<date>-<feature>",
    date: "<YYYY-MM-DD>",
    base: "<default branch>",
    repoRoot: "<absolute repo path>",
    skillDir: "<absolute path to this skill dir>",
    increment: <true|false>,
    iteration: <N>
  }
})
```

For a resume, add `resumeFromRunId: <run.json.workflowRunId>`.

7. **Report** the run ID; the engine runs in the background. The user is notified on PR
   (new) / PR update comment (increment) or halt (`blocker.md`, status `blocked`).

## Defaults

- Finish action is `pr` — open a PR, never merge. The leak scan in `finish-branch` is
  mandatory and cannot be skipped; the PR is unreachable unless it passes.
- Retry budgets default to 3 per phase (set via `maxIters` in the engine).
- Change a phase's behavior by editing `phases/<phase>.md`; there is no config.
- To swap the reviewer, rewrite `phases/code-review.md` to invoke an external tool
  and map its output onto `{ findings, verdict }`.

## Requirements

- `finish-branch` must be available as a named workflow, or vendored alongside the
  engine. It runs the verify command, leak-scans the net diff, then squashes and
  opens the PR.
- Run from a feature branch, not the default branch.
