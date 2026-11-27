#!/bin/sh
# #1157 Before merge lines 1 and 2: `verdict` posts a satisfied report with `## Criteria` and an
# `Accepted on evidence:` line under `Risk: low`, refuses it under `Risk: high` naming the line and
# refuses a report without `## Criteria`; `brief` prints loop.md's `Acceptance tests:` command with
# the issue, else the fallback runner.
set -e
exec uv run pytest -q -p no:cacheprovider gatekeeper/tests/test_approvals_acceptance_evidence.py
