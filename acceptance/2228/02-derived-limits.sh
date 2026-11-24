#!/bin/sh
# #2228 Before merge 2: with `timeouts.run: 4h` the rendered queue checks timeout and the `land --wait` ceiling both
# follow it; with nothing set the queue stays at 1 hour and `land --wait` at 2 hours; the repo's .mergify.yml is in step.
set -e
uv run pytest -q -p no:cacheprovider -n0 \
  "gatekeeper/tests/test_approvals_timeouts.py::test_the_queue_timeout_the_job_limit_and_the_land_wait_ceiling_follow_the_run" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_with_nothing_set_the_rendered_file_is_the_template_byte_for_byte" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_land_wait_waits_until_the_derived_ceiling" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_land_wait_set_before_the_derivation_still_wins_with_a_deprecation_line" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_the_check_passes_in_step_and_fails_once_the_run_moves" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_check_setup_reads_only_the_timeout_line" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_the_verb_labels_a_land_wait_override_as_such" \
  tests/test_mergify_config.py
exec uv run gatekeeper/skills/gatekeeper/scripts/gatekeeper.py timeouts --check
