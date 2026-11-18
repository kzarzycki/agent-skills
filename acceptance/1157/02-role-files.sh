#!/bin/sh
# #1157 Before merge line 3: `mise run test-engineering-package` exits 0 with the text tests that pin
# verifier.md's Criteria step before the worker's report, lead.md step 7's four shared-worktree
# conditions and SKILL.md's `Verifier session: reuse | fresh`.
set -e
exec mise run test-engineering-package
