from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict:
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


def _steps(workflow: dict) -> list[dict]:
    return [step for job in workflow["jobs"].values() for step in job.get("steps", [])]


def test_engineering_ci_is_path_scoped_and_runs_all_deterministic_gates() -> None:
    workflow = _workflow("engineering-ci.yml")
    paths = set(workflow["on"]["pull_request"]["paths"])
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))

    assert {
        ".github/workflows/engineering-*.yml",
        ".gitattributes",
        "engineering/**",
        "tools/capability_pack/**",
        "tests/capability_pack/**",
        "tests/automation/**",
        "mise.toml",
        "pyproject.toml",
        "uv.lock",
        ".claude-plugin/marketplace.json",
        "README.md",
        "CLAUDE.md",
    } <= paths
    assert set(workflow["on"]["push"]["paths"]) == paths
    for command in (
        "mise install",
        "uv sync --frozen",
        "mise run vendor-engineering-check",
        "mise run test",
        "mise run test-engineering-package",
        "git diff --check",
    ):
        assert command in commands


def test_weekly_updater_is_draft_only_and_narrowly_permissioned() -> None:
    workflow = _workflow("engineering-upstream-check.yml")
    triggers = workflow["on"]
    job = workflow["jobs"]["update"]
    commands = "\n".join(step.get("run", "") for step in job["steps"]).lower()
    pull_request = next(
        step for step in job["steps"] if "peter-evans/create-pull-request" in step.get("uses", "")
    )

    assert triggers["schedule"]
    assert "workflow_dispatch" in triggers
    assert job["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert pull_request["with"]["draft"] == "always-true"
    assert pull_request["with"]["branch"] == "automation/engineering-upstream"
    assert pull_request["with"]["body-path"] == "/tmp/engineering-update.md"
    assert "mise run vendor-engineering -- --summary /tmp/engineering-update.md" in commands
    for forbidden in ("gh pr merge", "gh release create", "git tag", "automerge"):
        assert forbidden not in commands
        assert forbidden not in str(workflow).lower()


def test_tag_workflow_is_package_scoped() -> None:
    workflow = _workflow("engineering-tag-check.yml")
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))

    assert workflow["on"]["push"]["tags"] == ["engineering-v*"]
    assert "release-check engineering" in commands
    assert "mise run vendor-engineering-check" in commands
    assert "mise run test-engineering-package" in commands


def test_all_actions_are_pinned_to_full_commit_shas() -> None:
    uses = [
        step["uses"]
        for path in WORKFLOWS.glob("engineering-*.yml")
        for step in _steps(_workflow(path.name))
        if "uses" in step
    ]

    assert uses
    assert all(re.search(r"@[0-9a-f]{40}$", value) for value in uses)
