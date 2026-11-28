# One-shot verifier

A cheap review pass: one Omnigent Codex session (workspace-write sandbox) reads one bundle and judges. Read this
when a verifier pass is started through `scripts/one_shot.py` (#2996). The checks around the model are the script's.

## Before the pass

- `one_shot.py tier`: a PR whose paths all match the low-risk list in `agents.yml` lands with gates only, and the gate says why.
- `one_shot.py plan`: the first pass runs once gates are green on the head; a later pass reviews only the delta since the last
  verdict; a head that already has a verdict is refused.
- `one_shot.py bundle`: spec and Acceptance, diff and raw gate output, inline in the first message. A cut names what was cut. A gate
  result not written by the gate script is refused. A change to gate config gets a finding.

## The brief

You judge; you may read the whole checkout and run the acceptance tests. Do not read rule files in-session: the rules that matter
are cited in the bundle. Cap shell output (`| head -200`). Mutation checks stay yours: choose the production changes to undo,
one at a time, and `mutate.py` runs them.

Report only what the change introduced, with provable impact, citing the AGENTS.md rule each finding breaks. Priority: P0 (blocks
release), P1 (urgent), P2 (normal), P3 (low). Answer with one JSON block:

`{"findings": [{"priority": "P1", "title": "...", "location": "path:line", "body": "...", "rules": ["..."]}],
"acceptance_not_run": ["..."], "overall_correctness": "patch is correct" | "patch is incorrect", "risk": "low — why"}`

`one_shot.py verdict` maps it to `VERDICT:`, `SATISFIED:` and `Risk:` lines (P0 blocker, P1 major, P2 and P3 minor), so
`approvals.py verdict` is unchanged. Over 30 model calls or 2 credits the verdict says so; the pass is not stopped.
