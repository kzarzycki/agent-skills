#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider gatekeeper/tests/test_approvals_catch_up_merges.py gatekeeper/tests/test_approvals_catch_up.py::test_a_clean_rebase_carries
