#!/bin/sh
# #2228 Before merge 1: gatekeeper.md documents `timeouts`, and the policy reader accepts it with today's values as
# defaults, refusing a malformed duration naming its key.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 \
  "gatekeeper/tests/test_approvals_timeouts.py::test_nothing_set_keeps_todays_limits" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_the_reader_takes_both_keys_and_each_alone" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_malformed_duration_is_refused_naming_its_key" \
  "gatekeeper/tests/test_approvals_timeouts.py::test_a_bare_number_and_an_unknown_key_are_refused_naming_the_key" \
  tests/test_skill_references.py
