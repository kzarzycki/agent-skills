"""The gate's parallel test run (#941, #1610): `mise run test` runs pytest on pytest-xdist unless GATE_TEST_PARALLEL=0,
and `-n auto` there takes GATE_JOBS, else the cores free at start (tools/gate_workers.py)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from tools import gate_workers

ROOT = Path(__file__).resolve().parents[1]
PARALLEL = ["-p", "tools.gate_workers", "-n", "auto", "--dist", "loadfile"]


def pytest_words(tmp_path: Path, env: dict[str, str], task: str = "test") -> list[str]:
    """The words `mise run test` passes on to pytest, from its run string under `sh -c` with a fake `uv` that records
    each call and succeeds, so the lock wrapper, pytest and ruff never run."""
    run = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"][task]["run"]
    calls = tmp_path / "calls"
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uv").write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > "{calls}.$$"\necho "{calls}.$$" >> "{calls}"\n'
    )
    (fake / "uv").chmod(0o755)
    base = {k: v for k, v in os.environ.items() if k != "GATE_TEST_PARALLEL"}
    subprocess.run(
        ["sh", "-c", run],
        env={**base, "PATH": f"{fake}:{base['PATH']}", **env},
        check=True,
        cwd=tmp_path,
    )
    first = Path(calls.read_text().split()[0]).read_text().splitlines()
    return first[first.index("pytest") :]


DEFAULT = ["pytest", "-q", "-m", "not live_agent and not slow"]


@pytest.mark.parametrize("env", [{}, {"GATE_TEST_PARALLEL": "1"}, {"GATE_TEST_PARALLEL": ""}])
def test_the_test_task_runs_pytest_on_xdist_a_file_per_worker_by_default(
    tmp_path: Path, env: dict[str, str]
) -> None:
    assert pytest_words(tmp_path, env) == [*DEFAULT, *PARALLEL]


@pytest.mark.parametrize("task", ["test", "test-slow"])
def test_gate_test_parallel_0_runs_pytest_serially(tmp_path: Path, task: str) -> None:
    words = pytest_words(tmp_path, {"GATE_TEST_PARALLEL": "0"}, task)
    assert words[-2:] == ["-n", "0"] and "auto" not in words


def test_test_and_test_slow_together_select_the_whole_non_live_suite() -> None:
    """`test` leaves the slow tests out and `test-slow` runs exactly them, so a test moved to `slow` still runs in the
    tasks that call both: the release tag check, pinned in tests/automation/test_workflows.py (#1610). The nightly's
    `check` runs no tests while #1653 holds, so it is not one."""
    tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
    marks = {
        name: re.search(r"-m '([^']+)'", tasks[name]["run"])[1] for name in ("test", "test-slow")
    }
    assert marks == {"test": "not live_agent and not slow", "test-slow": "slow and not live_agent"}


def test_test_slow_is_parallel_unless_the_gate_turns_it_off() -> None:
    run = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]["test-slow"]["run"]
    assert '"${GATE_TEST_PARALLEL:-1}" != 0' in run and " ".join(PARALLEL) in run


def test_the_nightly_test_map_run_stays_serial() -> None:
    """Under xdist `--cov-context=test` records no per-test contexts, so the map would name no test (#1610)."""
    steps = yaml.safe_load((ROOT / ".github/workflows/engineering-ci.yml").read_text())
    jobs = [s for job in steps["jobs"].values() for s in job["steps"]]
    mapped = [s for s in jobs if "--cov-context=test" in s.get("env", {}).get("PYTEST_ADDOPTS", "")]
    assert mapped and all(s["env"]["GATE_TEST_PARALLEL"] == "0" for s in mapped)
    # pyproject's addopts runs every pytest in parallel, so the serial run says `-n 0` itself
    assert all(" -n 0 " in f" {s['env']['PYTEST_ADDOPTS']} " for s in mapped)


def test_a_bare_pytest_is_parallel_by_default() -> None:
    """A run with no mise task, as an agent types it, costs what `mise run test` does (#1610): `-n auto` is in addopts."""
    addopts = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"][
        "addopts"
    ]
    assert "-n auto" in addopts and "--dist loadfile" in addopts and "tools.gate_workers" in addopts


def test_free_cores_are_the_cores_less_the_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "process_cpu_count", lambda: 8)
    monkeypatch.setattr(os, "getloadavg", lambda: (2.7, 0.0, 0.0))
    assert gate_workers.free_cores() == 6


def test_free_cores_are_at_least_one_on_a_loaded_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "process_cpu_count", lambda: 4)
    monkeypatch.setattr(os, "getloadavg", lambda: (9.0, 0.0, 0.0))
    assert gate_workers.free_cores() == 1


def test_free_cores_are_every_core_where_the_host_hides_its_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def hidden() -> tuple[float, float, float]:
        raise OSError("no load average")

    monkeypatch.setattr(os, "process_cpu_count", lambda: 4)
    monkeypatch.setattr(os, "getloadavg", hidden)
    assert gate_workers.free_cores() == 4


@pytest.mark.parametrize("jobs, workers", [("3", 3), ("", 5), ("0", 5), ("x", 5)])
def test_xdist_auto_takes_gate_jobs_when_it_is_a_positive_count_else_the_free_cores(
    monkeypatch: pytest.MonkeyPatch, jobs: str, workers: int
) -> None:
    monkeypatch.setenv("GATE_JOBS", jobs)
    monkeypatch.setattr(gate_workers, "free_cores", lambda: 5)
    assert gate_workers.pytest_xdist_auto_num_workers(None) == workers  # type: ignore[arg-type]


@pytest.mark.slow  # a nested pytest run with its own xdist workers (#1610)
def test_the_plugin_sets_the_worker_count_xdist_auto_starts(tmp_path: Path) -> None:
    # one more than every core, so xdist's own count (every core) can't pass for it
    jobs = (os.process_cpu_count() or 1) + 1
    (tmp_path / "test_one.py").write_text("def test_one() -> None:\n    pass\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_XDIST_AUTO_NUM_WORKERS"}
    said = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *PARALLEL[:2]]
        + ["-n", "auto", "--rootdir", str(tmp_path), str(tmp_path / "test_one.py")],
        env={**env, "GATE_JOBS": str(jobs)},
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert said.returncode == 0, said.stdout + said.stderr
    assert f"{jobs} workers [1 item]" in said.stdout
