#!/usr/bin/env bash
# #1648 Acceptance: a bold verdict is read as the plain line on both routes, a pass without a yes/no verdict fails
# (exit 1) naming the next step, the brief pins the verdict form, a cloud VM's verifier event is skipped with a
# `cloud VM:` line, and an opt-out PR carrying a merge go (record or label) is told which trail is missing.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv run pytest -q -p no:cacheprovider \
  engineering/tests/test_cloud_verifier.py engineering/tests/test_cloud_verifier_events.py \
  engineering/tests/test_cloud_verifier_claude.py engineering/tests/test_cloud_limits.py \
  engineering/tests/test_approvals_opt_out_go.py
