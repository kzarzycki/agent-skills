#!/usr/bin/env bash
set -euo pipefail
# A test call's direct edits are undone for the next test, under xdist too, in order with the test's own monkeypatch:
# a PATH patch made after the CLI strips the venv, and a CLI deletion of a session fixture's variable, are both put
# back; a session fixture keeps its variable, and a module fixture still sees its teardown phase. Each run clears the
# caller's PYTEST_ADDOPTS, so the serial run stays serial.

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
def session_env():
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
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


def test_prepend_leak(monkeypatch, tmp_path):
    approvals.leave_own_environment()
    assert VENV_BIN not in os.get_exec_path()
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)


def test_prepend_restore():
    assert VENV_BIN in os.get_exec_path()


@pytest.fixture(scope="session")
def fixture_venv():
    os.environ["PROBE_1543_VENV"] = sys.prefix
    yield
    os.environ.pop("PROBE_1543_VENV", None)


def test_session_delete_leak(fixture_venv):
    del os.environ["PROBE_1543_VENV"]


def test_session_delete_restore(fixture_venv):
    assert os.environ.get("PROBE_1543_VENV") == sys.prefix


@pytest.fixture(scope="module")
def observe_teardown_phase():
    yield
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (teardown)")


def test_phase(observe_teardown_phase):
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (call)")
PY

cd "$root"
export PYTHONPATH="$root/engineering/tests${PYTHONPATH:+:$PYTHONPATH}"
PYTEST_ADDOPTS= uv run pytest -q --tb=short -p no:cacheprovider -p no:xdist --rootdir "$probe" "$probe/test_environ_probe.py"
PYTEST_ADDOPTS= uv run pytest -q --tb=short -p no:cacheprovider --rootdir "$probe" -n 2 --dist loadfile "$probe/test_environ_probe.py"
