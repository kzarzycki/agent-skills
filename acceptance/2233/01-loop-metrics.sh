#!/bin/sh
# #2233: loop-metrics prints the week's merged count, median ready->merged, runner-minutes, no-record, reverts and
# red nights beside the week before, on recorded API responses: a draft first, a queue batch split evenly, a rerun,
# the 1000-run cap, an API error and a repo with no Actions.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 gatekeeper/tests/test_loop_metrics.py
