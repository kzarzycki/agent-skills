#!/bin/sh
# #2392: a row line or `spec:paths` that doesn't cover a spec refuses the PR only beside a missing approval: with
# the owner's record and `approved:spec` on the spec, nothing is left; without them, the line still shows beside the
# missing-record lines.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 \
  gatekeeper/tests/test_approvals_row_spec.py \
  gatekeeper/tests/test_approvals_spec_paths.py
