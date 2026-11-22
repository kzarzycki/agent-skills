#!/bin/sh
# #1783 Before merge line 05-forwarder-target-installed.sh: a forwarder without its target skill is drift, and the round installs the target.
set -e
exec uv run pytest -q -p no:cacheprovider "engineering/tests/test_agent_hygiene_refresh.py::test_a_forwarder_without_its_target_gets_the_target_installed" "engineering/tests/test_agent_hygiene_refresh.py::test_a_forwarder_whose_target_stays_missing_is_drift"
