"""The gate's parallel test run (#941): `mise run test` runs pytest on pytest-xdist only with GATE_TEST_PARALLEL=1,
and `-n auto` there takes GATE_JOBS, else the cores free at start (tools/gate_workers.py)."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tools import gate_workers

ROOT = Path(__file__).resolve().parents[1]
PARALLEL = ["-p", "tools.gate_workers", "-n", "auto", "--dist", "loadfile"]


def pytest_words(tmp_path: Path, env: dict[str, str]) -> list[str]:
    """The words `mise run test` passes on to pytest, from its run string under `sh -c` with a fake `uv` that records
    each call and succeeds, so the lock wrapper, pytest and ruff never run."""
    run = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]["test"]["run"]
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


@pytest.mark.parametrize("env", [{}, {"GATE_TEST_PARALLEL": "0"}, {"GATE_TEST_PARALLEL": ""}])
def test_the_test_task_runs_pytest_serially_unless_the_gate_turns_parallel_on(
    tmp_path: Path, env: dict[str, str]
) -> None:
    assert pytest_words(tmp_path, env) == ["pytest", "-q", "-m", "not live_agent"]


def test_gate_test_parallel_1_runs_pytest_on_xdist_a_file_per_worker(tmp_path: Path) -> None:
    assert pytest_words(tmp_path, {"GATE_TEST_PARALLEL": "1"}) == [
        "pytest",
        "-q",
        "-m",
        "not live_agent",
        *PARALLEL,
    ]


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
