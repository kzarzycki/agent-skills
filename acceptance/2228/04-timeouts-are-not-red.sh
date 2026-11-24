#!/bin/sh
# #2228 (and #2143's "Machine-not-ready and timeouts are not red"): a run over `timeouts.run` says so in one line, and a
# queue's timeout evicts no one and counts no red.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_step_over_its_budget_is_killed_with_its_group_and_reads_as_a_timeout" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_command_exiting_124_itself_is_no_timeout" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_affected_tests_over_the_budget_says_so_in_one_line" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_github_queue_group_red_only_by_a_timeout_counts_for_nothing" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_github_queue_group_with_a_real_failure_beside_a_timeout_still_counts" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_group_is_timeout_only_when_every_failed_required_check_timed_out" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_mergify_dequeue_on_a_timeout_queues_the_pr_again_and_evicts_no_one" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_full_run_over_the_budget_names_the_whole_suite" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_mergify_dequeue_that_is_no_queue_timeout_is_evicted" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_stale_dequeued_label_with_timeout_text_only_comes_off" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_refused_queue_command_leaves_the_dequeued_label_for_the_next_land" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_group_github_cannot_read_is_no_timeout"
