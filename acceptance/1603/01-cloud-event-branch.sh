#!/usr/bin/env bash
# #1603 Acceptance: the cloud-branch tests pass, and events.md documents the branch form.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv run pytest -q -p no:cacheprovider engineering/tests/test_events_cloud_branch.py
grep -q 'loop-event/<kind>/<branch>' engineering/skills/engineering-loop/events.md
test -s engineering/changelog.d/1603.md
