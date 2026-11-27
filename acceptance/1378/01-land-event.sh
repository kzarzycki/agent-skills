#!/bin/sh
# #1378 Before merge lines: `land` writes the `land` event of each PR's branch, read from another clone with `wait land
# <branch>`: `waiting` at each poll of `--wait`, `ok` once a PR merges (here or outside `land`) with its refs cleared a grace
# later, `failed` with the eviction comment's URL, `needs-owner` at the owner's go (ready or draft PR) or the 2-hour
# ceiling; an origin that refuses the push, or an emit that raises, changes no exit code of `land`.
set -e
exec uv run pytest -q -p no:cacheprovider gatekeeper/tests/test_approvals_land_event.py
