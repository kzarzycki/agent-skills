#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider engineering/tests/test_acceptance.py -k "syntax_error or runs_to_its_end or execute_only"
