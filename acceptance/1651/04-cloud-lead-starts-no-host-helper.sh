#!/bin/sh
# #1651 Before merge line 4: every cloud session's first message says it never creates a child session to run host work.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_agent.py -k host_helper_child
