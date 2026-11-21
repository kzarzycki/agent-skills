"""`mise run check-fast`'s test step (#1609): a selector that fails or prints nothing fails the step, since pytest
given no targets would run the whole suite and still pass."""

import os
import subprocess
import tomllib
from pathlib import Path

import pytest

# ponytail: check-fast runs no tests until the suite runs whole in a few minutes (#1653); these pin the selection step
# #1653 brings back, so they come back with it.
pytestmark = pytest.mark.skip(reason="check-fast runs no tests until #1653")

ROOT = Path(__file__).resolve().parents[1]


def run_step(tmp_path: Path, selector: str) -> subprocess.CompletedProcess[str]:
    """check-fast's lines after the vendor check and before lint, run by sh with `uv` stubbed: `uv run python
    tools/affected_tests.py` runs `selector` (a shell snippet), any other `uv run` logs its arguments."""
    run = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]["check-fast"]["run"]
    lines = [line for line in run.splitlines() if not line.startswith("mise run ")]
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text(
        "#!/bin/sh\n"
        'case "$*" in *affected_tests.py*) ' + selector + " ;; esac\n"
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


@pytest.mark.parametrize(
    "selector, error",
    [("exit 2", "tools/affected_tests.py failed"), ("exit 0", "selected nothing")],
)
def test_a_failed_or_empty_selection_fails_without_running_pytest(
    tmp_path: Path, selector: str, error: str
) -> None:
    done = run_step(tmp_path, selector)
    assert done.returncode != 0 and error in done.stderr
    assert not (tmp_path / "ran.log").exists()


def test_a_selection_runs_pytest_on_its_targets(tmp_path: Path) -> None:
    done = run_step(tmp_path, "echo tests/test_a.py; echo tests/test_b.py; exit 0")
    assert done.returncode == 0, done.stderr
    [line] = (tmp_path / "ran.log").read_text().splitlines()
    assert line.endswith("pytest -q -m not live_agent tests/test_a.py tests/test_b.py")
