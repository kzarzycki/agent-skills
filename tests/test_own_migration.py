"""This repo's CI and loop settings sit on the loop rule set (#2232, part of #2143): its build inputs and limits are
stated once in docs/agents/gatekeeper.md, and the selector, the nightly workflow, pytest and the jobs read them there."""

from __future__ import annotations

import functools
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

from tools import affected_tests, timeouts_plugin

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "gatekeeper" / "skills" / "gatekeeper" / "scripts" / "gatekeeper.py"


@functools.cache
def pack():
    spec = importlib.util.spec_from_file_location("gatekeeper_own_migration", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def policy():
    return pack().Policy((REPOSITORY / "docs/agents/gatekeeper.md").read_text())


def test_the_selector_s_own_code_and_the_runner_config_are_build_inputs() -> None:
    """A change to the selector can't be judged by the selector it changes, so it runs the whole suite."""
    inputs = pack().settings(policy())["select"]["build_inputs"]
    for path in (
        "tools/affected_tests.py",
        "gatekeeper/skills/gatekeeper/scripts/gatekeeper.py",
        "pyproject.toml",
    ):
        assert path in inputs
        assert affected_tests.targets([path], build_inputs="full") == list(affected_tests.ALL)
    assert set(affected_tests.BUILD_INPUTS) == set(inputs)


def test_the_nightly_s_push_paths_are_the_build_inputs() -> None:
    paths = pack().push_paths(
        (REPOSITORY / ".github/workflows/nightly-build-inputs.yml").read_text()
    )
    assert sorted(paths) == sorted(pack().settings(policy())["select"]["build_inputs"])


def test_a_prose_change_still_runs_the_affected_tests_command() -> None:
    """Tests read prose and agent config here, so `select` must not turn them into a skipped change."""
    select = pack().settings(policy())["select"]
    [check] = select["checks"]
    assert check["command"] == "mise run check-affected"
    for path in ("*.md", "docs/*", ".claude/*", ".agents/*"):
        assert path in check["paths"]
    assert (
        "Affected tests: mise run check-affected"
        in (REPOSITORY / "docs/agents/loop.md").read_text()
    )


def test_pytest_s_per_test_limit_is_the_timeouts_block() -> None:
    import tomllib

    options = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())["tool"]["pytest"][
        "ini_options"
    ]
    assert "timeout" not in options, "the per-test limit is gatekeeper.md's `timeouts.test`"
    assert timeouts_plugin.test_limit() == pack().timeouts(policy())["test"]
    assert "tools.timeouts_plugin" in options["addopts"]


def test_the_gate_and_the_qualify_job_set_no_limit_by_hand() -> None:
    assert "QUALIFY_TIMEOUT" not in pack().settings(policy())["gate"]
    workflow = (REPOSITORY / ".github/workflows/engineering-ci.yml").read_text()
    assert re.search(r"^\s+timeout-minutes:\s*60\s+#\s*timeouts\.run\b", workflow, re.MULTILINE)


def test_every_limit_is_in_step_with_the_timeouts_block() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "timeouts", "--check"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
