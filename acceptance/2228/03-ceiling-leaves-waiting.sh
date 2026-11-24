#!/bin/sh
# #2228 Before merge 3 (from #2172, landed by #2199): the ceiling reached with checks in progress writes `waiting`, not
# `needs-owner`; `needs-owner` stays for a PR nothing moves.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 \
  "gatekeeper/tests/test_land_wait_budget.py::test_the_ceiling_leaves_a_pr_waiting_on_its_checks_waiting_and_asks_the_owner_for_one_nothing_moves" \
  "gatekeeper/tests/test_land_wait_budget.py::test_the_ceiling_leaves_a_pr_a_queue_holds_waiting"
