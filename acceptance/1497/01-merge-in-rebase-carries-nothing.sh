#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider engineering/tests/test_approvals_catch_up_merges.py engineering/tests/test_approvals_catch_up.py::test_a_clean_rebase_carries
