#!/bin/sh
# #1658 Before merge line 5: a bare land comments Landed (Gate: Mergify merge queue) on a merged queued PR and takes the label off.
set -e
exec uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_mergify_queue.py::test_bare_land_writes_the_trail"
