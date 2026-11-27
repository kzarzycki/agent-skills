#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider "omnigent/tests/test_omnigent_agent.py::test_every_cloud_preamble_keeps_out_of_git_and_one_without_pr_reports_in_its_last_message"
