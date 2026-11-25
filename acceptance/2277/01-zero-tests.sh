#!/bin/sh
# #2277: a rerun whose test report shows zero tests, where the red run had some, prints "did not run" and exits 75
# (DID_NOT_RUN), never "the flake passed". The test fails with origin/main's gatekeeper.py from before the change.
set -eu
cd "$(git rev-parse --show-toplevel)/gatekeeper"
uv run pytest -q -p no:cacheprovider -n0 tests/test_approvals_rerun_tests.py -k zero_tests
