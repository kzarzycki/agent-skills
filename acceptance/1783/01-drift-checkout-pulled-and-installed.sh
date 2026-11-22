#!/bin/sh
# #1783 Before merge line 01-drift-checkout-pulled-and-installed.sh: a clean, fast-forwardable checkout on its default branch is pulled and installed (its sync task, else apm install from the committed lock); any other state goes to the repo's manager.
set -e
exec uv run pytest -q -p no:cacheprovider "engineering/tests/test_agent_hygiene_refresh.py::test_a_clean_clone_behind_is_pulled_and_installed_from_its_committed_lock" "engineering/tests/test_agent_hygiene_refresh.py::test_a_repo_with_a_sync_task_installs_through_it" "engineering/tests/test_agent_hygiene_refresh.py::test_a_checkout_without_its_install_tool_says_what_is_missing" "engineering/tests/test_agent_hygiene_drift.py"
