#!/bin/sh
# #1651 Before merge line 1: on a marked host approvals.py's gate verbs and run_heavy refuse, spawning nothing, naming the marker and claude-cloud-run; an unmarked host runs them.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_approvals_orchestration_host.py
