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
    whitespace = next(
        step for step in _steps(workflow) if step.get("name") == "Check changed-file whitespace"
    )

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
    assert whitespace["env"]["BASE_SHA"] == (
        "${{ github.event.pull_request.base.sha || github.event.before }}"
    )
    assert "HEAD^" not in whitespace["run"]
    for command in (
        "mise install",
        "uv sync --frozen",
        "mise run vendor-engineering-check",
        "mise run test",
        "mise run test-engineering-package",
        "git diff --check",
    ):
        assert command in commands


def test_tag_workflow_is_package_scoped() -> None:
    workflow = _workflow("engineering-tag-check.yml")
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))

    assert workflow["on"]["push"]["tags"] == ["engineering-v*"]
    assert "release-check engineering" in commands
    assert "mise run vendor-engineering-check" in commands
    assert "mise run test-engineering-package" in commands
    sync = workflow["jobs"]["consumer-sync"]
    assert sync["needs"] == "qualify"
    assert sync["uses"] == "./.github/workflows/engineering-consumer-sync.yml"
    assert sync["with"] == {
        "source_tag": "${{ github.ref_name }}",
        "source_commit": "${{ github.sha }}",
    }


def test_consumer_sync_is_exact_app_authenticated_and_draft_only() -> None:
    workflow = _workflow("engineering-consumer-sync.yml")
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))
    proposal = next(
        step for step in _steps(workflow) if step.get("name") == "Reconcile exact consumer draft"
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["on"]["workflow_dispatch"]["inputs"] == {
        "source_tag": {
            "description": "Exact released engineering-vX.Y.Z tag to recover",
            "required": "true",
            "type": "string",
        },
        "source_commit": {
            "description": "Commit peeled from the exact release tag",
            "required": "true",
            "type": "string",
        },
    }
    assert "prepare-consumer" in commands
    assert "agent-sync --refresh" in commands
    assert "agent-sync --frozen" in commands
    refresh_index = commands.index("agent-sync --refresh")
    commit_index = commands.index("git commit -m")
    frozen_index = commands.index("agent-sync --frozen")
    assert refresh_index < commit_index < frozen_index
    assert "git add --all" in commands
    assert "assert-engineering-codex-inventory" in commands
    assert all("${{" not in step.get("run", "") for step in _steps(workflow))
    assert "resolved_tag" in (ROOT / "tools" / "capability_pack" / "consumer.py").read_text()
    assert "reconcile-draft-pr" in proposal["run"]
    assert "automation/engineering-consumer-sync" in proposal["run"]
    assert proposal["env"]["GH_TOKEN"] == "${{ steps.app-token.outputs.token }}"
    assert "peter-evans/create-pull-request" not in str(workflow)
    assert [step.get("name") for step in _steps(workflow) if "GH_TOKEN" in step.get("env", {})] == [
        "Reconcile exact consumer draft"
    ]


def test_all_actions_are_pinned_to_full_commit_shas() -> None:
    uses = [
        step["uses"]
        for path in WORKFLOWS.glob("engineering-*.yml")
        for step in _steps(_workflow(path.name))
        if "uses" in step
    ]

    assert uses
    assert all(re.search(r"@[0-9a-f]{40}$", value) for value in uses)


def test_consumer_generated_state_triggers_qualification() -> None:
    workflow = _workflow("engineering-ci.yml")
    required = {".agents/**", ".claude/**", "apm.yml", "apm.lock.yaml"}
    assert required <= set(workflow["on"]["pull_request"]["paths"])
    assert required <= set(workflow["on"]["push"]["paths"])
