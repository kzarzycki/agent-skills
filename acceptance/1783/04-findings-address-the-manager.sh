#!/bin/sh
# #1783 Before merge line 04-findings-address-the-manager.sh: finding wording addresses the manager, not the owner.
set -e
exec uv run pytest -q -p no:cacheprovider "engineering/tests/test_agent_hygiene_refresh.py::test_a_finding_addresses_the_manager_not_the_owner"
