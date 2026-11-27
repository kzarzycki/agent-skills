#!/bin/sh
# #1821: .mergify.yml is the pack template byte for byte, and check-fast fails when it drifts.
set -e
uv run gatekeeper/skills/gatekeeper/scripts/approvals.py queue-config | cmp - .mergify.yml
exec uv run pytest -q -p no:cacheprovider \
  "tests/test_mergify_config.py::test_the_repo_file_is_the_rendered_template_and_the_head_check_catches_drift"
