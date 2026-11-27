#!/usr/bin/env bash
# #1491: the SSH check line gets exit 75 and a card naming host, command, purpose and link;
# any other ssh ending (exit 0 and 3) passes output and exit code through; argv stays intact.
set -euo pipefail
uv run pytest -q -p no:cacheprovider omnigent/tests/test_omnigent_agent_ssh.py
