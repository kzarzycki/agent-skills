#!/bin/sh
# #2261: `nightly.py moved push|schedule|tag` ships in the loop package, reads the batches of `land.queue` (mergify's
# `pull_request` runs, GitHub's `merge_group` runs), and CI calls it instead of a repo-local script.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 tests/test_after_merge_untested.py
