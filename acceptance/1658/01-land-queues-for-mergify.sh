#!/bin/sh
# #1658 Before merge line 1: a PR holding every proof gets the land status and loop:queued, with no gate, lock or merge.
set -e
exec uv run pytest -q -p no:cacheprovider "engineering/tests/test_approvals_mergify_queue.py::test_land_queues_for_mergify"
