#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_agent.py -k "test_brief_prints_the_body_start_sends_a_child or test_brief_prints_the_body_the_start_command_sends_with_pr or test_brief_refuses_an_unreadable_role_and_takes_a_long_brief"
