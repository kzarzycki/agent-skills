# autopilot smoke test

Goal: a trivial spec runs end-to-end to an open PR on a throwaway branch.

## Happy path

1. In a scratch git repo with a remote, create `.work/2026-06-02-smoke/spec.md`:
   "Add a pure function `slugify(s)` in src/slugify.js that lowercases and
    hyphenates; cover it with a test. verifyCmd: node --test src/*.test.js."
   And `ITEM.md` (status `planning`; the six progress boxes).
2. Run:
   ```
   Workflow({ scriptPath: "<autopilot>/engine.js",
     args: { itemDir: ".work/2026-06-02-smoke", date: "2026-06-02", base: "main",
             repoRoot: "<scratch>", skillDir: "<autopilot>" } })
   ```
3. Expected:
   - `plan.md` gains tasks with fileScope `[src/slugify.js, src/slugify.test.js]`.
   - execute creates the function + test in a worktree, reconciles cleanly.
   - code-review panel finds nothing ≥80, passes.
   - verify PASS against acceptance.
   - finish: leak scan clean, branch pushed, PR opened; `ITEM.md` status=done; PR url returned.

## Leak-block path (failure injection)

4. Plant `sk-TESTSECRET0000` in the spec's example code. Confirm the finish leak
   scan BLOCKS: no PR is opened, `blocker.md` is written, status flips to `blocked`,
   and the engine returns `{ halted: 'finish', reason: 'leak-scan-blocked' }`.

## Dry-run (no remote, no tokens)

```
Workflow({ scriptPath: "<autopilot>/engine.js",
  args: { itemDir: ".work/dry", date: "2026-06-02", base: "main",
          repoRoot: ".", skillDir: "<autopilot>", dryRun: true } })
```
Expected: completes through all phases (Plan→Finish), logs the derived waves,
returns `{ prUrl: "dry-run://pr" }`, makes zero agent calls and zero file mutations.

## Recorded results

- Dry-run: PASS — completes Plan→Finish, returns `{ prUrl: "dry-run://pr" }` (see below).
- Happy path / leak-block: require a scratch repo with a remote + `gh` auth; run when available.
