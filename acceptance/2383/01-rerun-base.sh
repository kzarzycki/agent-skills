#!/bin/sh
# #2383: rerun.yml's `check rerun` step runs from a checkout of the base branch's tip, not the PR head; the head is
# checked out after it, only where a rerun is needed, for the selection run.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 tests/test_rerun_workflow.py
