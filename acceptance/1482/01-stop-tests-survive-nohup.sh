#!/usr/bin/env bash
# the stop tests pass when this run itself has SIGHUP ignored, as a gate detached under nohup does
set -euo pipefail
nohup uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_heavy_wrapper.py" -k "stop" </dev/null 2>&1 | tail -5
test "${PIPESTATUS[0]}" -eq 0
