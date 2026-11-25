"""A test sees the same environment wherever it runs, and a new environment read is decided when it is written (#2455).

The merge queue's CI sets `GITHUB_HEAD_REF=mergify/merge-queue/<id>`, which tools/affected_tests.py reads to pick its
queue policy; tests inherited it and failed in the queue only (#2449). The root conftest clears the runner's variables
(tools/test_env.py), and a variable product code reads by literal name must be named there as cleared or host-neutral.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from tools import test_env

ROOT = Path(__file__).resolve().parents[1]


def env_reads(source: str) -> set[str]:
    """The environment variables `source` reads by literal name: `os.environ.get("X")`, `os.environ["X"]`,
    `os.getenv("X")`, `"X" in os.environ` (and the same through any name that holds an environ)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        name = None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            holder = ast.unparse(node.func.value)
            if (node.func.attr in ("get", "pop", "setdefault") and "environ" in holder) or (
                node.func.attr == "getenv" and holder == "os"
            ):
                name = node.args[0].value
        elif (
            isinstance(node, ast.Subscript)
            and "environ" in ast.unparse(node.value)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            name = node.slice.value
        elif (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str)
            and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops)
            and any("environ" in ast.unparse(c) for c in node.comparators)
        ):
            name = node.left.value
        if name:
            found.add(name)
    return found


def product_files() -> list[Path]:
    """The code a test runs against: `tools/` and each package's skill `scripts/`, never their tests."""
    files = [*(ROOT / "tools").rglob("*.py"), *ROOT.glob("*/skills/*/scripts/**/*.py")]
    return sorted(f for f in files if "tests" not in f.relative_to(ROOT).parts)


def uncovered(runner: tuple[str, ...] = test_env.RUNNER) -> dict[str, list[str]]:
    """Each variable product code reads by name that is neither cleared for tests nor host-neutral, with its files."""
    missing: dict[str, list[str]] = {}
    for path in product_files():
        for name in env_reads(path.read_text()):
            if name in runner or (test_env.covered(name) and name not in test_env.RUNNER):
                continue
            missing.setdefault(name, []).append(str(path.relative_to(ROOT)))
    return missing


def test_the_scan_reads_every_form_of_a_literal_environment_read() -> None:
    source = (
        "import os\n"
        "a = os.environ.get('A')\nb = os.environ['B']\nc = os.getenv('C', 'x')\nd = 'D' in os.environ\n"
        "e = env.get('not-environ')\nf = os.environ.get(name)\n"
    )
    assert env_reads(source) == {"A", "B", "C", "D"}


def test_every_variable_product_code_reads_is_cleared_for_tests_or_listed_host_neutral() -> None:
    assert uncovered() == {}, (
        "name each in tools/test_env.py: RUNNER/SESSION to clear it, HOST_NEUTRAL to leave it"
    )


def test_the_queue_variable_the_selector_reads_is_cleared_for_tests() -> None:
    """Drop GITHUB_HEAD_REF from the cleared list and the selector's read is no longer covered: the check fails."""
    assert "GITHUB_HEAD_REF" in env_reads((ROOT / "tools/affected_tests.py").read_text())
    without = tuple(v for v in test_env.RUNNER if v != "GITHUB_HEAD_REF")
    assert "GITHUB_HEAD_REF" in uncovered(without)


def test_the_runner_variables_the_queue_sets_are_cleared() -> None:
    assert {"GITHUB_HEAD_REF", "GATE_IN_QUEUE", "GITHUB_EVENT_NAME", "GITHUB_ACTIONS"} <= set(
        test_env.RUNNER
    )


def test_the_selector_tests_pass_in_the_queues_environment() -> None:
    """#2449: the same two files, run with the queue's variables set, as the queue's CI runs them."""
    env = {**os.environ, "GITHUB_HEAD_REF": "mergify/merge-queue/abc", "GATE_IN_QUEUE": "1"}
    env["GITHUB_EVENT_NAME"], env["GITHUB_ACTIONS"] = "pull_request", "true"
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-n",
            "0",
            "-p",
            "no:cacheprovider",
            "tests/test_affected_tests.py",
            "tests/test_affected_tests_floor.py",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-500:]
