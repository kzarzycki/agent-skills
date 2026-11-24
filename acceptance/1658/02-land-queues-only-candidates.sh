#!/bin/sh
# #1658 Before merge line 2: a PR missing a proof or with qualify red gets neither (exit 1), one with qualify running exits 3.
set -e
exec uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_mergify_queue.py::test_land_queues_only_candidates"
