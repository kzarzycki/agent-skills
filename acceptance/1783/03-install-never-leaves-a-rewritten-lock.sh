#!/bin/sh
# #1783 Before merge line 03-install-never-leaves-a-rewritten-lock.sh: an install never leaves a rewritten lock or changed committed copies, and a failure is reported.
set -e
exec uv run pytest -q -p no:cacheprovider "engineering/tests/test_agent_hygiene_refresh.py::test_a_failed_install_restores_the_lock_and_is_told_to_the_manager" "engineering/tests/test_agent_hygiene_refresh.py::test_a_lock_an_earlier_install_rewrote_is_restored_and_pins_nothing_older" "engineering/tests/test_agent_hygiene_refresh.py::test_the_self_install_after_a_fast_forward_leaves_the_lock_committed" "engineering/tests/test_agent_hygiene_refresh.py::test_an_install_that_changes_committed_copies_is_put_back_and_told"
