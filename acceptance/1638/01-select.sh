#!/bin/sh
# #1638: gatekeeper.md's `select` cuts affected-tests and the narrowed gate by build input: a non-product change runs
# only the checks it touches, a build input, an unclear path or uncommitted work runs the `Affected tests:` command,
# and `local-ci <pr>` reads the PR's head from any checkout.
set -e
exec uv run pytest -q -p no:cacheprovider gatekeeper/tests/test_approvals_select.py
