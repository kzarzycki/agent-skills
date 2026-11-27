#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider gatekeeper/tests/test_approvals_setup_pack_name.py
