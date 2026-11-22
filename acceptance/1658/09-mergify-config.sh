#!/bin/sh
# #1658 Before merge line 9: .mergify.yml names one squash queue on exactly land's hand-over, a queue action on the same conditions, no CI check, and the policy sets land.queue: mergify.
set -e
exec uv run pytest -q -p no:cacheprovider tests/test_mergify_config.py
