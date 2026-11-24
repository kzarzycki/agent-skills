"""`mise run test-batch`, the tests `qualify` runs on a Mergify batch (#1609, #1821, #1872): a selector that fails
fails the step, and one that prints nothing runs no pytest, since pytest given no targets would run the whole suite;
the unkeyed checks it writes to its `--unkeyed-out` file run first (R6)."""

import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(tmp_path: Path, selector: str) -> subprocess.CompletedProcess[str]:
    """test-batch's script, run by sh with `uv` stubbed: `uv run python -m tools.cross_change_tests` runs `selector` (a
    shell snippet, `$6` the `--unkeyed-out` file), any other `uv run` logs its arguments."""
    lines = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]["test-batch"][
        "run"
    ].splitlines()
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text(
        "#!/bin/sh\n"
        'case "$*" in *cross_change_tests*) ' + selector + " ;; esac\n"
        f'echo "ran: $*" >> {tmp_path / "ran.log"}\n'
    )
    (stub / "uv").chmod(0o755)
    env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}", "GATE_BASE": "base"}
    return subprocess.run(
        ["sh", "-c", "\n".join(lines)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )


def test_a_failed_selection_fails_without_running_pytest(tmp_path: Path) -> None:
    done = run_step(tmp_path, "exit 2")
    assert done.returncode != 0 and "tools/cross_change_tests.py failed or refused" in done.stderr
    assert not (tmp_path / "ran.log").exists()


def test_an_empty_selection_runs_nothing_says_so_and_passes(tmp_path: Path) -> None:
    """#1872: a selector that can't tell runs nothing, never the whole suite."""
    done = run_step(tmp_path, "exit 0")
    assert done.returncode == 0, done.stderr
    assert "selected nothing, so no tests run" in done.stderr
    assert not (tmp_path / "ran.log").exists()


def test_a_selection_runs_pytest_on_its_targets(tmp_path: Path) -> None:
    done = run_step(tmp_path, "echo tests/test_a.py; echo tests/test_b.py; exit 0")
    assert done.returncode == 0, done.stderr
    [line] = (tmp_path / "ran.log").read_text().splitlines()
    assert line.endswith(
        "pytest -q -m not live_agent and not slow -p tools.gate_workers -n auto --dist loadfile"
        " tests/test_a.py tests/test_b.py"
    )


def test_the_unkeyed_checks_run_before_the_tests(tmp_path: Path) -> None:
    done = run_step(tmp_path, 'echo "echo unkeyed >> ran.log" > "$6"; echo tests/test_a.py; exit 0')
    assert done.returncode == 0, done.stderr
    first, tests = (tmp_path / "ran.log").read_text().splitlines()
    assert first == "unkeyed" and tests.endswith("tests/test_a.py")


def test_a_failed_unkeyed_check_fails_without_running_pytest(tmp_path: Path) -> None:
    done = run_step(tmp_path, 'echo false > "$6"; echo tests/test_a.py; exit 0')
    assert done.returncode != 0 and "the unkeyed check failed: false" in done.stderr
    assert not (tmp_path / "ran.log").exists()
