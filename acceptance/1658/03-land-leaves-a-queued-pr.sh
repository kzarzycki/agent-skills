#!/bin/sh
# #1658 Before merge line 3: a PR already queued at its head is left alone and reported queued.
set -e
exec uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_mergify_queue.py::test_land_leaves_a_queued_pr"
