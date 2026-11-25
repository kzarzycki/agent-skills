"""tools/test_map_plugin.py (#1609): a pytest a test starts never inherits the outer run's PYTEST_ADDOPTS (the
nightly's coverage flags), and a subprocess a test starts is measured under that test's context."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import test_map_plugin as plugin

ROOT = Path(__file__).resolve().parents[1]


def test_a_nested_pytest_does_not_inherit_the_outer_runs_addopts(tmp_path: Path) -> None:
    (tmp_path / "test_inner.py").write_text(
        "import os\n\n\ndef test_inner():\n    assert 'PYTEST_ADDOPTS' not in os.environ\n"
    )
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(ROOT / "pyproject.toml"),
        ]
        + [str(tmp_path / "test_inner.py")],
        env={**os.environ, "PYTEST_ADDOPTS": "-q"},
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_this_run_does_not_hand_its_addopts_on() -> None:
    assert "PYTEST_ADDOPTS" not in os.environ


def serialized(data: object) -> str:
    return base64.b64encode(json.dumps(data).encode()).decode()


def test_a_childs_coverage_config_names_the_test_as_its_context() -> None:
    named = plugin.with_context(serialized({"context": None, "parallel": True}), "t.py::test_x|run")
    assert named is not None
    assert json.loads(base64.b64decode(named)) == {"context": "t.py::test_x|run", "parallel": True}


def test_a_config_it_cannot_read_is_left_alone() -> None:
    assert plugin.with_context("not base64 json", "t.py::test_x|run") is None
    assert plugin.with_context(serialized({"no": "context"}), "t.py::test_x|run") is None


def test_while_a_test_runs_a_childs_config_names_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook rewrites COVERAGE_PROCESS_CONFIG for the test's run and puts the outer value back after."""
    outer = serialized({"context": None})
    monkeypatch.setenv(plugin.CONFIG, outer)
    item = type("Item", (), {"nodeid": "t.py::test_x"})()
    hook = plugin.pytest_runtest_protocol(item, None)
    next(hook)
    assert json.loads(base64.b64decode(os.environ[plugin.CONFIG]))["context"] == "t.py::test_x|run"
    with pytest.raises(StopIteration):
        hook.send(True)
    assert os.environ[plugin.CONFIG] == outer


def test_a_skipped_test_is_listed_for_the_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = tmp_path / "skipped"
    monkeypatch.setenv(plugin.SKIPPED, str(listed))
    report = type("Report", (), {"skipped": True, "nodeid": "t.py::test_s"})()
    plugin.pytest_runtest_logreport(report)
    plugin.pytest_runtest_logreport(type("Report", (), {"skipped": False, "nodeid": "t.py::x"})())
    assert listed.read_text() == "t.py::test_s\n"


def test_xdist_workers_keep_the_runs_addopts(tmp_path: Path) -> None:
    """Workers read PYTEST_ADDOPTS when they start, between tests, so it is only out while a test runs."""
    (tmp_path / "test_w.py").write_text("def test_alpha(): pass\n\n\ndef test_beta(): pass\n")
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-c",
            str(ROOT / "pyproject.toml"),
        ]
        + ["-n", "2", str(tmp_path / "test_w.py")],
        env={**os.environ, "PYTEST_ADDOPTS": "-k alpha"},
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 passed" in done.stdout  # test_beta deselected on the worker too


def test_addopts_is_back_after_a_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_ADDOPTS", "-q")
    hook = plugin.pytest_runtest_protocol(type("Item", (), {"nodeid": "t.py::test_x"})(), None)
    next(hook)
    assert "PYTEST_ADDOPTS" not in os.environ
    with pytest.raises(StopIteration):
        hook.send(True)
    assert os.environ["PYTEST_ADDOPTS"] == "-q"


def test_the_durations_file_gets_one_durations_line_per_phase(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """#2445: with TEST_DURATIONS set, each test phase's time is appended in `pytest --durations=0`'s format."""
    listed = tmp_path / "durations.log"
    monkeypatch.setenv(plugin.DURATIONS, str(listed))
    report = pytest.TestReport(
        "tests/test_x.py::test_a",
        ("tests/test_x.py", 1, "test_a"),
        {},
        "passed",
        None,
        "call",
        duration=1.5,
    )
    plugin.pytest_runtest_logreport(report)
    assert listed.read_text() == "1.500s call tests/test_x.py::test_a\n"
