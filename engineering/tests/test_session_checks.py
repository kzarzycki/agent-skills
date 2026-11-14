"""conftest.py: the scripts the tests run write no bytecode, a run stops at once naming each tool it lacks (#1022), and
the approvals stubs stay in the approvals modules (#1015)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
REPOSITORY = HERE.parents[1]


def test_a_script_the_tests_run_writes_no_bytecode_beside_it(tmp_path: Path) -> None:
    """A skill's script that imports its sibling, as the tests run one, leaves no __pycache__ in the folder."""
    (tmp_path / "sibling.py").write_text("VALUE = 7\n")
    (tmp_path / "script.py").write_text("import sibling\nprint(sibling.VALUE)\n")
    run = subprocess.run(
        [sys.executable, str(tmp_path / "script.py")], capture_output=True, text=True, check=True
    )
    assert run.stdout == "7\n"
    assert not (tmp_path / "__pycache__").exists()


def test_a_run_started_without_the_variable_still_writes_no_bytecode() -> None:
    """The test above, in a run whose environment lacks PYTHONDONTWRITEBYTECODE, as a gate or a host starts one."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    test = f"{Path(__file__).relative_to(REPOSITORY)}::test_a_script_the_tests_run_writes_no_bytecode_beside_it"
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test],
        cwd=REPOSITORY,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_the_approvals_stubs_stay_out_of_other_modules(request: pytest.FixtureRequest) -> None:
    assert "board_risks" not in request.fixturenames


def collect(tmp_path: Path, *modules: str) -> subprocess.CompletedProcess[str]:
    """A pytest run of `modules` with a PATH that holds none of the tools the suite runs."""
    env = {**os.environ, "PATH": str(tmp_path / "empty-bin")}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *modules],
        cwd=REPOSITORY,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def test_a_run_without_apm_stops_before_its_first_test_naming_apm(tmp_path: Path) -> None:
    run = collect(tmp_path, "engineering/tests/test_consumer_e2e.py")
    assert run.returncode == pytest.ExitCode.USAGE_ERROR, run.stdout + run.stderr
    assert "missing tools the tests run: apm; put them on PATH" in run.stdout + run.stderr
    assert "passed" not in run.stdout and "failed" not in run.stdout


@pytest.mark.parametrize(
    ("module", "tools"),
    [
        ("e2e/test_static_discovery.py", "apm"),
        ("test_approvals.py", "ssh-keygen"),
        ("test_omnigent_agent.py", "perl"),
        ("test_board.py", None),
    ],
)
def test_each_module_s_tools_are_checked_before_it_runs(
    tmp_path: Path, module: str, tools: str | None
) -> None:
    run = collect(tmp_path, f"engineering/tests/{module}", "--collect-only")
    said = [line for line in (run.stdout + run.stderr).splitlines() if "missing tools" in line]
    if tools is None:
        assert run.returncode == 0 and not said, run.stdout + run.stderr
    else:
        assert said and f"missing tools the tests run: {tools}; put them on PATH" in said[0]


def test_one_line_names_every_missing_tool_of_the_selected_tests(tmp_path: Path) -> None:
    run = collect(
        tmp_path,
        "engineering/tests/test_consumer_e2e.py",
        "engineering/tests/test_omnigent_agent.py",
        "engineering/tests/test_board.py",
    )
    assert "missing tools the tests run: apm, perl; put them on PATH" in run.stdout + run.stderr
