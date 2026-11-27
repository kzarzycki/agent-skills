# Loop telemetry inventory (#945)

What a landed PR cost and where its time went, item by item: where it is recorded today, or `gap` with what closes it.
Stack-side gaps (collector, storage, dashboard, GitHub poller, time buckets, pack-version label) are filed in the
owner's private infrastructure repo and linked from #945; this table holds the pack side.

| Item | Recorded today | Gap and what closes it |
|---|---|---|
| CI runs, re-runs, results | GitHub Actions runs per head; `loop_metrics.py` sums runner minutes per PR | none on the pack side; per-PR time buckets are the stack's poller |
| PR opened, ready, merge go, merged | PR timeline; `approvals.py` records and `Landed` comment | the poller joins them (stack) |
| Gate runs | gate records under `.git/approvals/`, `local-ci` status on the head | the poller reads the status (stack) |
| Verifier passes and fix rounds | verdict reviews on the PR (`Verifier ... pass <n>`) | none on the pack side |
| Merge queue, evictions | `land` comments, queue batch PRs (`mergify/merge-queue/`) | the poller (stack) |
| Merges of main into the branch | PR timeline commits | the poller (stack) |
| Session role | label `omni.role` | none |
| Session PR | label `omni.pr` (worker, verifier; a lead may hold several) | none |
| Session phase | none | closed here: label `omni.phase` (`lead`, `build`, `verify`) set at create |
| Session model, host, tokens, cost | Omnigent session record and usage; `omnigent-telemetry` | tokens and cost may be missing on an older server: show `unknown`, never 0 (stack) |
| Pack version at merge | the pin in the project's `apm.lock.yaml` | label in the stack (stack) |
