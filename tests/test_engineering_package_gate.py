from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

pytestmark = (
    pytest.mark.slow
)  # runs the packaged gate over a mutated marketplace, 15-20 s each (#1610)

REPOSITORY = Path(__file__).resolve().parents[1]


def test_live_agent_gate_requests_both_supported_agents() -> None:
    task = (REPOSITORY / "mise.toml").read_text()

    assert (
        'run = "CLAUDE_CODE_E2E=1 CODEX_E2E=1 uv run pytest -q -m live_agent engineering/tests/e2e"'
    ) in task


def test_the_check_task_runs_the_gates_ci_runs_in_its_order() -> None:
    tasks = tomllib.loads((REPOSITORY / "mise.toml").read_text())["tasks"]
    workflow = (REPOSITORY / ".github" / "workflows" / "engineering-ci.yml").read_text()
    ran = re.findall(r"^\s*run: (mise run \S+)$", workflow, re.MULTILINE)

    # CI runs the cheap checks on a PR or push, the tests on a Mergify batch's draft PR (#1821) and the full check
    # on the nightly schedule
    assert ran == ["mise run check-fast", "mise run test-batch", "mise run check"]
    assert tasks["check"]["run"][0] == "mise run vendor-engineering-check"


def test_the_nightly_check_runs_the_full_suite() -> None:
    """#1872: no PR runs the whole suite, so the nightly `check` must, slow tests included."""
    tasks = tomllib.loads((REPOSITORY / "mise.toml").read_text())["tasks"]
    assert {"mise run test", "mise run test-slow"} <= set(tasks["check"]["run"])


@pytest.mark.timeout(300)  # it runs the package gate in a subprocess: 20-40 s, more under load
@pytest.mark.parametrize("mutation", ["corrupt", "delete"])
def test_advertised_package_gate_rejects_marketplace_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    checkout = tmp_path / "repository"
    shutil.copytree(
        REPOSITORY,
        checkout,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            "__pycache__",
            "*.pyc",
            ".engineering-stage-*",
        ),
    )
    marketplace = checkout / ".claude-plugin" / "marketplace.json"
    if mutation == "delete":
        marketplace.unlink()
    else:
        data = json.loads(marketplace.read_text())
        engineering = next(item for item in data["plugins"] if item["name"] == "engineering")
        engineering["source"] = "./broken-engineering"
        marketplace.write_text(json.dumps(data, indent=2) + "\n")

    env = os.environ.copy()
    env.pop("CAPABILITY_PACK_QUALIFICATION_STAGE_ROOT", None)
    env["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY / ".venv")
    env["UV_NO_SYNC"] = "1"
    # The gate's time follows the host's load: 120 s failed under a loaded host's full gate, so the default is
    # 600, and QUALIFY_TIMEOUT raises it, as for vendir sync.
    timeout = int(os.environ.get("QUALIFY_TIMEOUT", "600"))
    try:
        result = subprocess.run(
            ["mise", "run", "test-engineering-package"],
            cwd=checkout,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"the package gate took over {timeout} seconds; on a loaded host raise QUALIFY_TIMEOUT"
        )

    assert result.returncode != 0, (
        f"advertised package gate accepted {mutation} marketplace metadata\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "test_claude_marketplace_exposes_only_the_owned_engineering_package" in (
        result.stdout + result.stderr
    )


def test_the_affected_tests_line_runs_the_selected_tests() -> None:
    """#2232 row 1: the worker's recorded `Affected tests:` run proves the PR's tests, so the batch floor (#2178) may
    drop them; a line naming check-fast alone proves lint only."""
    line = re.search(
        r"^Affected tests:[ \t]*(.+?)[ \t]*$",
        (REPOSITORY / "docs" / "agents" / "loop.md").read_text(),
        re.MULTILINE,
    )
    assert line and line[1] == "mise run check-affected"
    tasks = tomllib.loads((REPOSITORY / "mise.toml").read_text())["tasks"]
    assert tasks["check-affected"]["run"].splitlines() == [
        "mise run check-fast",
        "GATE_IN_QUEUE=1 mise run test-batch",
    ]
