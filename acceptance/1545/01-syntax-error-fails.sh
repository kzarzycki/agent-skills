#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider engineering/tests/test_acceptance.py -k "does_not_parse or runs_to_its_end or execute_only"
