"""The scheduled full run's shards (#2804): tools/shard_plugin.py splits one pytest run into disjoint shards that run
at the same time, with every test run once, each shard's coverage kept apart and folded into the file a serial run writes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import shard_plugin

ROOT = Path(__file__).resolve().parent.parent


def test_split_gives_every_file_one_shard_and_balances_the_load() -> None:
    counts = {"a": 50, "b": 30, "c": 30, "d": 20, "e": 10, "f": 10}
    held = shard_plugin.split(counts, 2)
    assert set(held) == set(counts) and set(held.values()) == {0, 1}
    load = [sum(n for p, n in counts.items() if held[p] == i) for i in (0, 1)]
    assert abs(load[0] - load[1]) <= 10
    assert shard_plugin.split(counts, 2) == held  # every shard computes the same split


def project(tmp_path: Path) -> Path:
    """A tiny suite: three files, one test of which fails when FAIL is set, one that runs a nested pytest."""
    (tmp_path / "test_a.py").write_text(
        "def test_a1(): pass\ndef test_a2(): pass\ndef test_a3(): pass\n"
    )
    (tmp_path / "test_b.py").write_text("def test_b1(): pass\ndef test_b2(): pass\n")
    (tmp_path / "test_c.py").write_text(
        "import os\n"
        "def test_c1(): assert not os.environ.get('FAIL')\n"
        "def test_skipped():\n    import pytest\n    pytest.skip('x')\n"
    )
    (tmp_path / "test_nested.py").write_text(
        "import os, subprocess, sys\n"
        "def test_a_nested_pytest_runs_whole_and_sees_no_shard_variables(tmp_path):\n"
        "    assert not {'TEST_SHARDS', 'SHARD_INDEX', 'SHARD_COUNT'} & set(os.environ)\n"
        "    (tmp_path / 'test_n.py').write_text('def test_1(): pass\\ndef test_2(): pass\\n')\n"
        "    out = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-q', str(tmp_path)],\n"
        "        capture_output=True, text=True, cwd=tmp_path)\n"
        "    assert '2 passed' in out.stdout, out.stdout\n"
    )
    return tmp_path


def run(tmp_path: Path, shards: int, **env: str) -> subprocess.CompletedProcess[str]:
    base = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTEST_ADDOPTS", "COVERAGE_PROCESS_CONFIG")
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tools.test_map_plugin",
            "-p",
            "tools.shard_plugin",
            "-p",
            "no:cacheprovider",
            "-n",
            "0",
            "-rs",
            "-v",
            "-o",
            "addopts=",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env={**base, "PYTHONPATH": str(ROOT), "TEST_SHARDS": str(shards), **env},
    )


def test_shards_run_every_test_once_and_report_the_worst_status(tmp_path: Path) -> None:
    project(tmp_path)
    done = run(tmp_path, 3)
    assert done.returncode == 0, done.stdout + done.stderr
    for name in ("a1", "a2", "a3", "b1", "b2", "c1"):
        assert done.stdout.count(f"test_{name[0]}.py::test_{name} PASSED") == 1, done.stdout
    assert "shard 1/3" in done.stdout and "shard 3/3" in done.stdout
    failing = run(tmp_path, 3, FAIL="1")
    assert failing.returncode == 1 and "test_c1 FAILED" in failing.stdout


def test_a_shard_that_selects_no_test_is_no_failure(tmp_path: Path) -> None:
    (tmp_path / "test_only.py").write_text("def test_x(): pass\n")
    done = run(tmp_path, 4)
    assert done.returncode == 0 and done.stdout.count("test_only.py::test_x PASSED") == 1


def test_no_shard_variable_runs_one_whole_pytest(tmp_path: Path) -> None:
    project(tmp_path)
    done = run(tmp_path, 1)
    assert "shard 1/" not in done.stdout and done.returncode == 0, done.stdout


def test_each_shard_keeps_its_own_files_and_the_outer_run_folds_them(tmp_path: Path) -> None:
    project(tmp_path)
    (tmp_path / ".coveragerc").write_text(
        "[run]\nparallel = true\nrelative_files = true\n"
    )  # as pyproject.toml
    skipped, durations = tmp_path / "skipped", tmp_path / "durations.log"
    done = run(
        tmp_path,
        2,
        COVERAGE_CORE="ctrace",  # sysmon, the default, records no per-test contexts
        COVERAGE_FILE=str(tmp_path / "cov"),
        TEST_MAP_SKIPPED=str(skipped),
        TEST_DURATIONS=str(durations),
        PYTEST_ADDOPTS=f"--cov={tmp_path} --cov-context=test --cov-report=",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert skipped.read_text().splitlines() == ["test_c.py::test_skipped"]
    assert len(durations.read_text().splitlines()) >= 8
    assert not list(tmp_path.glob("cov-shard*")) and not list(tmp_path.glob("skipped-shard*"))
    assert not list(tmp_path.glob("durations.log-shard*")) and (tmp_path / "cov").exists()
    import sqlite3

    contexts = {
        c for (c,) in sqlite3.connect(tmp_path / "cov").execute("select context from context")
    }
    assert any("test_a.py::test_a1" in c for c in contexts) and any(
        "test_b.py::test_b1" in c for c in contexts
    )


@pytest.mark.parametrize("value", ["", "0", "1", "x"])
def test_split_stays_off_below_two_shards(tmp_path: Path, value: str) -> None:
    (tmp_path / "test_only.py").write_text("def test_x(): pass\n")
    done = run(tmp_path, 1, TEST_SHARDS=value)
    assert "shard 1/" not in done.stdout and done.returncode == 0
