#!/bin/sh
# #1471 Before merge line 1: a cloud start with --role carries the role text and a host start the path.
set -e
exec uv run pytest -q -p no:cacheprovider "omnigent/tests/test_omnigent_agent.py::test_a_cloud_child_gets_its_role_file_s_text_and_a_host_child_its_path"
