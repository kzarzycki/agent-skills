"""conftest.py: the scripts the tests run write no bytecode, a run stops at once naming each tool it lacks (#1022), and
the approvals stubs stay in the approvals modules (#1015)."""

from __future__ import annotations

import ast
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


def path_without(tmp_path: Path, *tools: str) -> str:
    """A PATH that holds every program the current one does but `tools`."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for folder in os.environ["PATH"].split(os.pathsep):
        if os.path.isdir(folder):
            for program in os.scandir(folder):
                if program.name not in tools and not (bin_ / program.name).exists():
                    (bin_ / program.name).symlink_to(program.path)
    return str(bin_)


def run_tests(path: str, *args: str) -> subprocess.CompletedProcess[str]:
    """A pytest run of `args` with `path` as PATH."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=REPOSITORY,
        env={**os.environ, "PATH": path},
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def stops(run: subprocess.CompletedProcess[str], tools: str) -> bool:
    """`run` stopped before its first test with the line naming `tools`."""
    return run.returncode == pytest.ExitCode.USAGE_ERROR and (
        f"missing tools the tests run: {tools}; put them on PATH" in run.stdout + run.stderr
    )


def test_a_run_without_apm_stops_before_its_first_test_naming_apm(tmp_path: Path) -> None:
    run = run_tests(str(tmp_path), "engineering/tests/test_consumer_e2e.py")
    assert stops(run, "apm"), run.stdout + run.stderr
    assert "passed" not in run.stdout and "failed" not in run.stdout


# A test that runs no tool, in a module whose other tests run one, beside one that runs it (V1).
TOOL_FREE = [
    (
        "apm",
        "e2e/test_static_discovery.py::test_run_agent_uses_isolated_config_without_stderr_assumptions",
    ),
    ("apm", "test_consumer_e2e.py::test_file_manifest_leaves_out_python_bytecode"),
    (
        "perl",
        "test_omnigent_agent.py::test_a_running_session_reads_its_signature_without_launch_arguments",
    ),
    (
        "ssh-keygen",
        "test_approvals.py::test_the_label_rule_is_the_loops_fixed_set_plus_the_tracker_files_sections",
    ),
]
NEEDING = [
    ("apm", "e2e/test_static_discovery.py::test_installation_does_not_leak_global_catalog_content"),
    ("apm", "test_consumer_e2e.py::test_local_package_packs_and_installs_for_claude_and_codex"),
    (
        "perl",
        "test_omnigent_agent.py::test_worker_md_s_heavy_lock_command_waits_for_the_lock_and_passes_the_exit_through",
    ),
    # through the `signing` fixture
    (
        "ssh-keygen",
        "test_approvals.py::test_land_with_the_line_refuses_a_checkout_that_signs_nothing",
    ),
    # the test runs it itself
    (
        "ssh-keygen",
        "test_approvals.py::test_a_green_signed_batch_gives_each_pr_a_commit_of_its_own_change",
    ),
]


@pytest.mark.parametrize(("tool", "test"), TOOL_FREE)
def test_a_selected_test_that_runs_no_tool_runs_though_its_module_s_others_do(
    tmp_path: Path, tool: str, test: str
) -> None:
    run = run_tests(path_without(tmp_path, tool), f"engineering/tests/{test}")
    assert run.returncode == 0 and "missing tools" not in run.stdout + run.stderr, (
        run.stdout + run.stderr
    )


@pytest.mark.parametrize(("tool", "test"), NEEDING)
def test_a_selected_test_that_runs_a_missing_tool_stops_the_run(
    tmp_path: Path, tool: str, test: str
) -> None:
    run = run_tests(path_without(tmp_path, tool), f"engineering/tests/{test}", "--collect-only")
    assert stops(run, tool), run.stdout + run.stderr


def test_one_line_names_every_missing_tool_of_the_selected_tests(tmp_path: Path) -> None:
    run = run_tests(
        path_without(tmp_path, "apm", "perl", "ssh-keygen"),
        "engineering/tests/test_consumer_e2e.py",
        "engineering/tests/test_omnigent_agent.py",
        "engineering/tests/test_board.py",
        "--collect-only",
    )
    assert stops(run, "apm, perl"), run.stdout + run.stderr


def test_deselecting_the_tests_that_need_a_tool_runs_the_rest(tmp_path: Path) -> None:
    """`-m "not needs_tool"` leaves out a test that needs a tool through a fixture, too."""
    run = run_tests(
        path_without(tmp_path, "ssh-keygen"),
        "engineering/tests/test_approvals.py::test_land_with_the_line_refuses_a_checkout_that_signs_nothing",
        "engineering/tests/test_approvals.py::test_the_label_rule_is_the_loops_fixed_set_plus_the_tracker_files_sections",
        "-m",
        "not needs_tool",
    )
    assert run.returncode == 0 and "1 passed, 1 deselected" in run.stdout, run.stdout + run.stderr


def marked_tools(path: Path) -> dict[str, tuple[str, ...]]:
    """The tools each test function of `path` names in a `needs_tool` mark."""
    found: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == (
                    "pytest.mark.needs_tool"
                ):
                    found[node.name] = tuple(ast.literal_eval(arg) for arg in decorator.args)
    return found


def test_each_test_that_runs_a_tool_itself_carries_its_mark() -> None:
    """The tests that fail without the tool, beyond those that take a fixture in conftest.py's FIXTURE_TOOLS."""
    marked = {
        f"{path.relative_to(HERE).as_posix()}::{name}": tools
        for path in sorted(HERE.rglob("test_*.py"))
        for name, tools in marked_tools(path).items()
    }
    apm = ("apm",)
    assert marked == {
        "e2e/test_static_discovery.py::test_apm_targets_receive_complete_canonical_inventory": apm,
        "e2e/test_static_discovery.py::test_complete_inventory_rejects_symmetric_target_mutation": apm,
        "e2e/test_static_discovery.py::test_deployed_relative_references_and_packaged_scripts_resolve": apm,
        "e2e/test_static_discovery.py::test_installation_does_not_leak_global_catalog_content": apm,
        "e2e/test_static_discovery.py::test_neutral_catalog_adapter_detects_artifact_mutation": apm,
        "e2e/test_static_discovery.py::test_wayfinder_is_byte_identical_across_canonical_and_targets": apm,
        "test_approvals.py::test_a_green_signed_batch_gives_each_pr_a_commit_of_its_own_change": (
            "ssh-keygen",
        ),
        "test_consumer_e2e.py::test_local_package_packs_and_installs_for_claude_and_codex": apm,
        "test_consumer_e2e.py::test_virtual_subdirectory_release_installs_and_replays_frozen": apm,
        "test_omnigent_agent.py::test_the_role_files_detach_runs_here_and_records_its_exit_code": (
            "perl",
        ),
        "test_omnigent_agent.py::test_worker_md_s_heavy_lock_command_waits_for_the_lock_and_passes_the_exit_through": (
            "perl",
        ),
    }
