#!/bin/sh
# #1668 (slice 1 of #1658) Before merge line 6: a cloud session with no signing key queues for Mergify while the local path still refuses.
set -e
exec uv run pytest -q -p no:cacheprovider "gatekeeper/tests/test_approvals_mergify_queue.py::test_cloud_land_queues_for_mergify"
