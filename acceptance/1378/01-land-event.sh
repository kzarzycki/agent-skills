#!/bin/sh
# #1378 Before merge lines: `land` writes the `land` event of each PR's branch: `waiting` beats under --wait, `ok` once a
# PR merged and its refs gone after the grace, `failed` with the eviction comment's URL, `needs-owner` for the owner's go
# or the 2-hour ceiling; none of land's exit codes change when origin refuses the event or emit raises; a native
# `wait land <branch>` follows a land.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_approvals_land_event.py
