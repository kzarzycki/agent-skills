#!/bin/sh
# #1632: a claude-cloud start takes auto from the flag only, warns on an environment-only mode,
# fails loudly when Omnigent refuses the bypass default, and prints the mode the session got.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_cloud_mode.py
