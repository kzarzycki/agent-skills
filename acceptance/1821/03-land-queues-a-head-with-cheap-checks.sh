#!/bin/sh
# #1821: land queues a PR whose head carries only the cheap `qualify` run, and evicts one Mergify dequeued on a red batch.
set -e
exec uv run pytest -q -p no:cacheprovider \
  "gatekeeper/tests/test_approvals_mergify_queue.py::test_land_queues_a_head_whose_qualify_ran_only_cheap_checks" \
  "gatekeeper/tests/test_approvals_mergify_queue.py::test_land_evicts_a_dequeued_pr"
