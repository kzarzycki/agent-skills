#!/bin/sh
# #1855: release-check passes with `smoke run: off` while RELEASE_SMOKE_REPOSITORY is unset; set, it asks for the head's passing run.
set -e
exec uv run pytest -q -p no:cacheprovider \
  "tests/automation/test_release_scope.py::test_release_check_command_is_off_without_the_smoke_repository_and_prints_a_skip" \
  "tests/automation/test_release_scope.py::test_release_check_asks_about_the_head_it_checked_out" \
  "tests/automation/test_release_scope.py::test_release_check_refuses_without_a_smoke_run_for_the_release_head"
