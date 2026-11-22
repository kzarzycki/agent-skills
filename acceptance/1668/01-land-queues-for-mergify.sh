#!/bin/sh
# #1668 (slice 1 of #1658) Before merge line 1: a PR holding every proof gets the land status and loop:queued, with no gate, lock or merge.
set -e
exec uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_mergify_queue.py::test_land_queues_for_mergify"
