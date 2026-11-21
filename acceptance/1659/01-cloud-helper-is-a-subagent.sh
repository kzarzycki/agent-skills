#!/bin/sh
# #1659 Before merge line 1: every cloud session's first message says a helper is a native subagent, never a created session; a host session's does not.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_agent.py -k helper_is_a_native_subagent
