#!/bin/sh
# #2229: `select.shards` splits a whole-suite selection into disjoint, duration-balanced shards, records one R1 pass
# per shard (written by `shards --record`, read by `shards --passed`), never splits a narrow selection, and the
# tests that read the edited gatekeeper files by path stay green.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 \
  gatekeeper/tests/test_approvals_shards.py \
  gatekeeper/tests/test_approvals_affected_tests.py \
  tests/test_skill_references.py tests/test_skill_layers.py tests/test_skill_requires.py \
  tests/test_old_paths.py tests/test_own_loop_settings.py
