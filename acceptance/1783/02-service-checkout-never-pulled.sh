#!/bin/sh
# #1783 Before merge line 02-service-checkout-never-pulled.sh: a checkout that runs services (a process has it open, a service unit points at it) is never pulled, only installed from its committed lock.
set -e
exec uv run pytest -q -p no:cacheprovider "engineering/tests/test_agent_hygiene_refresh.py::test_a_clone_a_process_has_open_is_not_pulled_but_installed" "engineering/tests/test_agent_hygiene_refresh.py::test_a_clone_a_service_unit_points_at_is_not_pulled" "engineering/tests/test_agent_hygiene_refresh.py::test_a_unit_naming_the_clone_through_home_or_linked_from_it_keeps_it_unpulled" "engineering/tests/test_agent_hygiene_refresh.py::test_the_unit_scan_reads_linked_units_the_local_share_folder_and_the_real_path"
