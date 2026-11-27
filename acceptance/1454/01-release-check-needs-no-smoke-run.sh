#!/bin/sh
# #1454: release-check passes with neither smoke variable set and never runs the smoke; smoke-run is the on-demand command.
set -e
exec uv run pytest -q -p no:cacheprovider \
  "tests/automation/test_release_scope.py::test_release_check_passes_with_neither_smoke_variable_set" \
  "tests/automation/test_release_scope.py::test_release_check_does_not_consult_the_smoke_run_even_when_configured" \
  "tests/automation/test_release_scope.py::test_smoke_run_command_fails_clearly_when_the_variables_are_unset" \
  "tests/automation/test_release_scope.py::test_run_smoke_dispatches_for_the_commit_and_reports_the_runs_result" \
  "tests/automation/test_release_scope.py::test_smoke_run_command_exits_with_the_runs_result" \
  "tests/automation/test_workflows.py::test_tag_workflow_is_package_scoped"
