#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider "engineering/tests/test_omnigent_agent.py::test_brief_prints_the_first_message_start_sends_a_cloud_child"
