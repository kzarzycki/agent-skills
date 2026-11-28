# One-shot verifier

A cheap review pass: one Omnigent Codex session (workspace-write sandbox) reads one bundle and judges. Read this
when a verifier pass is started through `scripts/one_shot.py` (#2996). The checks around the model are the script's.

## Before the pass

- `one_shot.py tier`: a PR whose paths all match the low-risk list in `agents.yml` lands with gates only, and the gate says why.
- `one_shot.py plan`: the first pass runs once gates are green on the head; a later pass reviews only the delta since the last
  verdict; a head that already has a verdict is refused.
- `one_shot.py bundle`: spec and Acceptance, the gatekeeper's own `gate-record` lookup for the head, the raw output of the gate's own steps, run by the script on
  the head's clean checkout (a failing step is refused; no CI log and no gate result a caller supplies is taken), the rules, nearby code and the diff,
  inline in the first message. One range (`--base` for a delta, else `--against`) gives the paths, the diff and the heading; paths are
  git's (`--name-status -z -M -C`), a rename or copy giving both sides. A cut, or an input not given, is named. A change to gate
  config or to a file in the policy's `select.build_inputs` (read as the gatekeeper parses them) gets a finding, and `tier` never
  skips its review.

## The brief

You judge; you may read the whole checkout and run the acceptance tests. Do not read rule files in-session: the rules that matter
are cited in the bundle. Cap shell output (`| head -200`). Mutation checks stay yours: choose the production changes to undo,
one at a time, and `mutate.py` runs them.

Checklist: try the edge inputs (empty, missing, malformed, duplicate, oversized) of any parser or settings loader the change
touches; that is where earlier passes' misses cluster.

Report only what the change introduced, with provable impact, citing the AGENTS.md rule each finding breaks. Priority: P0 (blocks
release), P1 (a major, as verifier.md's Major defines it, with its `breaks`, `path` and, from pass 2, `origin` lines), P2 (normal), P3 (low). Answer with one JSON block:

```json
{"criteria": ["<Acceptance line: how it was checked>"],
 "findings": [{"priority": "P1", "title": "...", "location": "path:line", "body": "...", "rules": ["..."], "breaks": "Acceptance <line> | repro <command> | standing bar <kind>", "path": "<standing bar's input, steps, impact>", "origin": "new"}],
 "acceptance_not_run": [
   {"check": "<what could not run>", "command": "<exact command>"},
   {"check": "<mutation not run>", "command": "<exact test command>",
    "mutation": {"patch": "<the change to make>", "undo": "<command>", "redo": "<command>"}}],
 "overall_correctness": "patch is correct",
 "risk": "low — why"}
```

`overall_correctness` is `"patch is correct"` or `"patch is incorrect"`. `acceptance_not_run` is `[]` when every check ran; every
`check`, `command`, `patch`, `undo` and `redo` is a nonblank string. `one_shot.py verdict` maps it to a report `approvals.py report` reads (`Verifier:`, `## Criteria`, `### Fn (severity) path:line: title`, `VERDICT:`, `SATISFIED:`, `Risk:`; P0 blocker, P1 major, P2 and
P3 minor), so `approvals.py verdict` is unchanged. A check you could not run goes in `acceptance_not_run` (the example above): the script then writes `<report>.question` for
the lead's proof run (exit 3), never a report. A step only the owner can take goes in `owner_only_not_run`
with `owner_action`. Over 30 model calls or 2 credits the `Verifier:` line says so; the pass is not stopped.
