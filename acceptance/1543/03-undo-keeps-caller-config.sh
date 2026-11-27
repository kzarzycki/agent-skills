#!/usr/bin/env bash
# A test that calls monkeypatch.undo() early (its fixtures' temporary git config gone) hands the next test the
# caller's config, not the temporary one put back.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
probe=$(mktemp -d)
trap 'rm -rf "$probe"' EXIT
touch "$probe/gitconfig"
cat > "$probe/test_env_after_undo.py" <<'PY'
import os

def test_reaching_the_next_module_with_the_parent_git_config():
    assert os.environ["GIT_CONFIG_GLOBAL"] == os.environ["PROBE_1543_GIT_CONFIG"]
PY

cd "$root"
GIT_CONFIG_GLOBAL="$probe/gitconfig" PROBE_1543_GIT_CONFIG="$probe/gitconfig" \
  PYTEST_ADDOPTS= uv run pytest -q --tb=short -p no:cacheprovider -o addopts= \
    gatekeeper/tests/test_approvals.py::test_the_head_was_pushed_when_the_branchs_activity_last_names_it \
    "$probe/test_env_after_undo.py"
