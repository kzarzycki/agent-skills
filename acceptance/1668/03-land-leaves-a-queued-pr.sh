#!/bin/sh
# #1668 (slice 1 of #1658) Before merge line 3: a PR already queued at its head is left alone and reported queued.
set -e
exec uv run pytest -q -p no:cacheprovider "engineering/tests/test_approvals_mergify_queue.py::test_land_leaves_a_queued_pr"
