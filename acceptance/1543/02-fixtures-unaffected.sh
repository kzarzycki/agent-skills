#!/usr/bin/env bash
set -euo pipefail
# The restore undoes only what a test call changed and nothing put back: a direct edit, also one a monkeypatch
# recorded after it, is undone for the next test, under xdist too; a session fixture keeps its variable, and a
# module fixture still sees its teardown phase.

root=$(git rev-parse --show-toplevel)
probe=$(mktemp -d)
trap 'rm -rf "$probe"' EXIT
ln -s "$root/engineering/tests/conftest.py" "$probe/conftest.py"

cat > "$probe/test_environ_probe.py" <<'PY'
import os
import sys

import pytest
from approvals_harness import approvals

VENV_BIN = os.path.join(sys.prefix, "bin")


@pytest.fixture(scope="session")
def session_env(worker_id):
    key = "PROBE_1543_SESSION"
    assert key not in os.environ
    os.environ[key] = worker_id
    yield key, worker_id
    assert os.environ.pop(key) == worker_id


def test_simple_leak(session_env):
    key, worker = session_env
    assert os.environ[key] == worker
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (call)")
    if worker != "master":
        assert os.environ["PYTEST_XDIST_WORKER"] == worker
    os.environ[key] = "changed directly"
    os.environ["PROBE_1543_ADDED"] = "added directly"
    del os.environ["VIRTUAL_ENV"]


def test_simple_restore(session_env):
    key, worker = session_env
    assert os.environ[key] == worker
    assert "PROBE_1543_ADDED" not in os.environ
    assert os.path.normpath(os.environ["VIRTUAL_ENV"]) == os.path.normpath(sys.prefix)
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (call)")
    if worker != "master":
        assert os.environ["PYTEST_XDIST_WORKER"] == worker


def test_mixed_leak(monkeypatch):
    assert VENV_BIN in os.get_exec_path()
    approvals.leave_own_environment()
    assert VENV_BIN not in os.get_exec_path()
    monkeypatch.setenv("PATH", os.environ["PATH"])


def test_mixed_restore():
    assert VENV_BIN in os.get_exec_path()


@pytest.fixture(scope="module")
def observe_teardown_phase():
    yield
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (teardown)")


def test_phase(observe_teardown_phase):
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (call)")
PY

cd "$root"
export PYTHONPATH="$root/engineering/tests${PYTHONPATH:+:$PYTHONPATH}"
uv run pytest -q --tb=short -p no:cacheprovider --rootdir "$probe" "$probe/test_environ_probe.py"
uv run pytest -q --tb=short -p no:cacheprovider --rootdir "$probe" -n 2 --dist loadfile "$probe/test_environ_probe.py"
