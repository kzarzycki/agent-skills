from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


def test_live_agent_gate_requests_both_supported_agents() -> None:
    task = (REPOSITORY / "mise.toml").read_text()

    assert (
        'run = "CLAUDE_CODE_E2E=1 CODEX_E2E=1 uv run pytest -q -m live_agent engineering/tests/e2e"'
    ) in task


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
    result = subprocess.run(
        ["mise", "run", "test-engineering-package"],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )

    assert result.returncode != 0, (
        f"advertised package gate accepted {mutation} marketplace metadata\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "test_claude_marketplace_exposes_only_the_owned_engineering_package" in (
        result.stdout + result.stderr
    )
