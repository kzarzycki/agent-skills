#!/bin/sh
# #1632: a claude-cloud start sends no permission mode unless the flag names one, warns on an
# environment-only mode, and prints the mode the session got.
set -e
exec uv run pytest -q -p no:cacheprovider omnigent/tests/test_omnigent_cloud_mode.py
