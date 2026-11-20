#!/bin/sh
# #1557 Before merge lines 1 and 2: a far lead in a worktree or submodule workspace gets the delegation text, and dropping the raw Accept header fails a test.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_lead_delegation.py -k "another_host or far_worktree or raw_contents or far_workspace"
