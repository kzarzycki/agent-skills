#!/bin/sh
# #1794 Before merge lines 1 and 2: a rerun attempt of a red `qualify` calls `approvals.py rerun-tests`, never `pytest` on
# the failed ids alone, and engineering-ci.yml's break-glass line and `tests` dispatch no longer say or do "failed alone".
set -e
exec uv run pytest -q -p no:cacheprovider tests/automation/test_workflows.py::test_qualify_rerun_attempt_calls_rerun_tests_never_the_failed_tests_alone
