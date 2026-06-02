---
name: autopilot
description: Autonomous brainstorm→PR pipeline. Invoke on /autopilot. Runs an interactive brainstorming session to an approved spec, then launches a background Workflow that plans, builds, reviews, verifies, and opens a PR with no further human input. Resumes a halted run when re-invoked.
---

# autopilot

One interactive step (brainstorming), then an unsupervised background engine that
plans → adversarially reviews the plan → executes in dependency waves → runs a
multi-dimension code review → independently verifies → opens a PR.

## Flow

1. **Resume check.** If a feature dir `.work/<date>-<feature>/` has `run.json` with a
   non-`done` status and a `blocker.md`, this is a resume — skip to step 6 and pass
   `resumeFromRunId` from `run.json`.
2. **Brainstorm.** Invoke `superpowers:brainstorming`. Save the approved spec to
   `.work/<YYYY-MM-DD>-<feature-slug>/spec.md` (NOT `docs/superpowers/specs/`).
3. **Create the feature dir** `.work/<date>-<feature>/` with an `iterations/` subdir.
4. **Create `ITEM.md`:**
   - `## Status: planning`
   - `## Progress` — unchecked boxes: `Plan created`, `Plan reviewed`, `Executed`,
     `Reviewed`, `Verified`, `Finished`
   - `## Log` — empty
5. **Detect `verifyCmd`** — the repo's test/build command (package.json scripts,
   Makefile, pyproject, etc.). If none is detectable, leave it to the plan phase.
6. **Launch the engine:**

   ```
   Workflow({
     scriptPath: "<this skill dir>/engine.js",
     args: {
       itemDir: ".work/<date>-<feature>",
       date: "<YYYY-MM-DD>",
       base: "<default branch>",
       repoRoot: "<absolute repo path>",
       skillDir: "<absolute path to this skill dir>"
     }
   })
   ```

   For a resume, add `resumeFromRunId: <run.json.workflowRunId>`.
7. **Report** the run ID and that the engine is running in the background. The user is
   notified on PR (success) or halt (`blocker.md` written, status `blocked`).

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
