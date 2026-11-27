#!/bin/sh
# #1783 Before merge line 06-tests-and-changelog.sh: one small test per behaviour (fake checkouts in a tmp dir), and a changelog.d entry.
set -e
grep -q 1783 engineering/CHANGELOG.md
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_agent_hygiene_refresh.py
