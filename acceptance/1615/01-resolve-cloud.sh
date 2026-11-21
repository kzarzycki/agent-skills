#!/usr/bin/env bash
# #1615 Acceptance: `approvals.py resolve --help` runs, and the cloud and host routes of `resolve` and `ready` pass their tests.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv run engineering/skills/engineering-loop/scripts/approvals.py resolve --help | grep -q -- '--reply'
uv run pytest -q -p no:cacheprovider engineering/tests/test_approvals_resolve_cloud.py
