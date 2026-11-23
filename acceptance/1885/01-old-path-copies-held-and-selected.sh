#!/bin/sh
# #1885: the old-path copies of the loop docs match their originals, and a loop doc change selects the test that holds them.
set -e
exec uv run pytest -q -p no:cacheprovider tests/test_old_paths.py \
  "tests/test_affected_tests.py::test_a_loop_doc_change_runs_the_test_that_holds_its_old_path_copy"
