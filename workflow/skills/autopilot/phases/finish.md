Finish composes the `finish-branch` workflow, which (a) runs the verify command,
(b) HARD-GATE scans the net diff for leaked secrets / credentials / financial data
/ PII and refuses to publish if anything is found, then (c) squashes the branch to
one clean commit and opens a PR. autopilot always uses action "pr" (never merge).

The rules bundle's outward-facing constraints (e.g. "no account numbers, balances,
or P&L in commits/PRs") are exactly what the scan enforces; pass known-safe
identifiers via allowlist.
