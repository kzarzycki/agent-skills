#!/bin/sh
# #1668 (slice 1 of #1658) Before merge line 7: land.queue: mergify with signed_squash_to is refused naming both.
set -e
exec uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_mergify_queue.py::test_mergify_refuses_signed_squash"
