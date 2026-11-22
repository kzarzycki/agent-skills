#!/bin/sh
# #1668 (slice 1 of #1658) Before merge line 4: a PR Mergify dequeued goes back to draft with land error, both labels off and an eviction comment.
set -e
exec uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_mergify_queue.py::test_land_evicts_a_dequeued_pr"
