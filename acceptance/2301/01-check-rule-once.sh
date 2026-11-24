#!/bin/sh
# #2301: engineering-loop's rule section states R5 by its current heading and names no runner, so
# tests/test_check_rule_once.py passes.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 tests/test_check_rule_once.py
