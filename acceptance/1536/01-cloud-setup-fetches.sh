#!/usr/bin/env bash
set -euo pipefail
uv run pytest -q -p no:cacheprovider tests/test_cloud_setup.py
