#!/bin/sh
# #1821: a red batch is retried once, then split until only the failing PR is dequeued.
set -e
exec uv run pytest -q -p no:cacheprovider \
  "tests/test_mergify_config.py::test_a_red_batch_is_retried_once_and_a_dropped_pr_labelled_for_eviction" \
  "tests/test_mergify_config.py::test_a_red_batch_is_split_until_only_the_failing_pr_leaves"
