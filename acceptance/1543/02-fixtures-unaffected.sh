#!/usr/bin/env bash
set -euo pipefail
# A test call's direct edits are undone for the next test, serial and under xdist, in order with the test's own
# monkeypatch: a PATH patch made after the CLI strips the venv, the CLI's deletion of a VIRTUAL_ENV a session fixture
# set, an edit from a second thread while another is mid-edit, and the edits before one the OS refuses are all put
# back, and a write an audit hook refuses reaches no child process. A session fixture keeps its variable, and a module
# fixture still sees its teardown phase. Each run clears the caller's PYTEST_ADDOPTS, so the serial run stays serial,
# and starts without VIRTUAL_ENV, so only a fixture sets it.

root=$(git rev-parse --show-toplevel)
probe=$(mktemp -d)
trap 'rm -rf "$probe"' EXIT
ln -s "$root/conftest.py" "$probe/conftest.py"

cat > "$probe/test_environ_probe.py" <<'PY'
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event

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
    del os.environ["PROBE_1543_INHERITED"]


def test_simple_restore(session_env):
    key, worker = session_env
    assert os.environ[key] == worker
    assert "PROBE_1543_ADDED" not in os.environ
    assert os.environ["PROBE_1543_INHERITED"] == "caller"
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (call)")
    if worker != "master":
        assert os.environ["PYTEST_XDIST_WORKER"] == worker


def test_mixed_leak(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    assert VENV_BIN in os.get_exec_path()
    approvals.leave_own_environment()
    assert VENV_BIN not in os.get_exec_path()
    monkeypatch.setenv("PATH", os.environ["PATH"])


def test_mixed_restore():
    assert VENV_BIN in os.get_exec_path()


def test_prepend_leak(monkeypatch, tmp_path):
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    approvals.leave_own_environment()
    assert VENV_BIN not in os.get_exec_path()
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)


def test_prepend_restore():
    assert VENV_BIN in os.get_exec_path()


@pytest.fixture(scope="session")
def fixture_venv():
    assert "VIRTUAL_ENV" not in os.environ
    os.environ["VIRTUAL_ENV"] = sys.prefix
    yield
    os.environ.pop("VIRTUAL_ENV", None)


def test_session_cli_leak(fixture_venv):
    approvals.leave_own_environment()
    assert "VIRTUAL_ENV" not in os.environ


def test_session_cli_restore(fixture_venv):
    assert os.environ.get("VIRTUAL_ENV") == sys.prefix
    assert VENV_BIN in os.get_exec_path()


def test_overlap_leak(monkeypatch):
    entered, finished, putenv = Event(), Event(), os.putenv

    def pause_first_write(key, value):
        if key == b"PROBE_1543_FIRST":  # the assignment's own encoded write, inside monkeypatch's edit
            entered.set()
            assert finished.wait(timeout=5)
        putenv(key, value)

    def second_write():
        assert entered.wait(timeout=5)
        try:
            os.environ["PROBE_1543_SECOND"] = "second"
        finally:
            finished.set()

    monkeypatch.setattr(os, "putenv", pause_first_write)
    with ThreadPoolExecutor(max_workers=2) as threads:
        first = threads.submit(os.environ.__setitem__, "PROBE_1543_FIRST", "first")
        threads.submit(second_write).result(timeout=10)
        first.result(timeout=10)
    assert os.environ["PROBE_1543_SECOND"] == "second"


def test_overlap_restore():
    assert "PROBE_1543_FIRST" not in os.environ
    assert "PROBE_1543_SECOND" not in os.environ


def test_refused_leak():
    os.environ["PROBE_1543_BEFORE_REFUSED"] = "changed"
    with pytest.raises(ValueError):
        os.environ["REFUSED=NAME"] = "ignored"


def test_refused_restore():
    assert "PROBE_1543_BEFORE_REFUSED" not in os.environ


def child_sees(key):
    code = f"import os; print(os.environ.get({key!r}))"
    return subprocess.run([sys.executable, "-c", code], check=True, text=True, capture_output=True).stdout.strip()


def test_audit_refused_leak():
    key, writes = "PROBE_1543_AUDITED", []

    def allow_one_write(event, args):
        if event == "os.putenv" and args[0] == key.encode():
            writes.append(args)
            if len(writes) > 1:
                raise PermissionError("one write to this key is allowed")

    sys.addaudithook(allow_one_write)
    try:
        os.environ[key] = "audited"
    except PermissionError:
        pass
    assert str(os.environ.get(key)) == child_sees(key)


def test_audit_refused_restore():
    assert "PROBE_1543_AUDITED" not in os.environ
    assert child_sees("PROBE_1543_AUDITED") == "None"


@pytest.fixture(scope="module")
def observe_teardown_phase():
    yield
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (teardown)")


def test_phase(observe_teardown_phase):
    assert os.environ["PYTEST_CURRENT_TEST"].endswith(" (call)")
PY

cd "$root"
export PYTHONPATH="$root/gatekeeper/tests" PROBE_1543_INHERITED=caller PYTEST_ADDOPTS=
pytest=(uv run env -u VIRTUAL_ENV python -m pytest -q --tb=short -p no:cacheprovider --rootdir "$probe")
"${pytest[@]}" -n 0 "$probe/test_environ_probe.py"
"${pytest[@]}" -n 2 --dist loadfile "$probe/test_environ_probe.py"
