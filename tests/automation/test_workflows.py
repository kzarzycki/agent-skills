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


def test_weekly_updater_is_draft_only_and_narrowly_permissioned() -> None:
    workflow = _workflow("engineering-upstream-check.yml")
    triggers = workflow["on"]
    jobs = workflow["jobs"]
    commands = "\n".join(step.get("run", "") for step in _steps(workflow)).lower()
    proposal = next(step for step in jobs["publish"]["steps"] if step.get("id") == "proposal")

    assert triggers["schedule"]
    assert "workflow_dispatch" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "engineering-upstream-refresh",
        "cancel-in-progress": "false",
    }
    assert jobs["report"]["permissions"] == {"contents": "read", "issues": "write"}
    assert all(job.get("timeout-minutes") for job in jobs.values())
    assert "reconcile-draft-pr" in proposal["run"]
    assert "automation/engineering-upstream" in proposal["run"]
    assert proposal["env"] == {
        "GH_TOKEN": "${{ steps.app-token.outputs.token }}",
        "REFRESH_MODE": "${{ needs.qualify.outputs.mode }}",
    }
    assert "peter-evans/create-pull-request" not in str(workflow)
    assert "mise run refresh-engineering" in commands
    assert "finalize-publication" in commands
    assert "final-status" in commands
    assert "test -s artifacts/engineering-refresh/candidate.patch" in commands
    assert "git apply --check artifacts/engineering-refresh/candidate.patch" in commands
    build = next(
        step
        for step in jobs["qualify"]["steps"]
        if step.get("name") == "Build nonempty candidate transfer"
    )
    apply = next(
        step for step in jobs["publish"]["steps"] if step.get("name") == "Apply qualified candidate"
    )
    assert "git apply --check" not in build["run"]
    assert "test -s artifacts/engineering-refresh/candidate.patch" in build["run"]
    assert "git apply --check artifacts/engineering-refresh/candidate.patch" in apply["run"]
    assert jobs["publish"]["if"] == "always() && needs.qualify.result == 'success'"
    assert "engineering-refresh-qualified" in str(workflow)
    assert "steps.publication-artifact.outcome != 'success'" in str(workflow)
    assert any(step.get("if") == "always()" for step in _steps(workflow))
    assert "engineering-updater-publish" in str(workflow)
    assert "secrets.github_token" not in str(workflow).lower()
    assert all("${{" not in step.get("run", "") for step in _steps(workflow))
    token = next(
        step for step in _steps(workflow) if "create-github-app-token" in step.get("uses", "")
    )
    assert token["with"] == {
        "app-id": "${{ secrets.UPDATER_APP_ID }}",
        "private-key": "${{ secrets.UPDATER_APP_PRIVATE_KEY }}",
    }
    assert "env" not in jobs["publish"]
    report_names = [step.get("name") for step in jobs["report"]["steps"]]
    assert report_names.index("Select reporting evidence") < next(
        index
        for index, step in enumerate(jobs["report"]["steps"])
        if "jdx/mise-action" in step.get("uses", "")
    )
    assert "Finalize reporting bootstrap failure without dependencies" in report_names
    assert report_names[-1] == "Fail reporting bootstrap"
    assert "fallback_finalize.py" in commands
    gh_token_steps = [step for step in _steps(workflow) if "GH_TOKEN" in step.get("env", {})]
    assert [step.get("id") or step.get("name") for step in gh_token_steps] == [
        "proposal",
        "Reconcile blocked intake issue",
    ]
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
    assert "prepare-consumer" in commands
    assert "agent-sync --refresh" in commands
    assert "agent-sync --frozen" in commands
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
