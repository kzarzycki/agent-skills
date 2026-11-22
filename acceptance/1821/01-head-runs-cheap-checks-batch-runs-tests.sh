#!/bin/sh
# #1821: a PR head's `qualify` runs only the cheap checks and still reports; the batch's draft PR runs the tests.
set -e
exec uv run pytest -q -p no:cacheprovider \
  "tests/test_mergify_config.py::test_a_pr_head_runs_only_cheap_checks_and_the_batch_runs_the_tests" \
  "tests/test_mergify_config.py::test_every_batch_is_tested_on_a_draft_pr_from_the_prefix_ci_tests" \
  tests/test_check_fast_selection.py
