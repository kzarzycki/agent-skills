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


def test_engineering_ci_runs_on_every_pr_and_all_deterministic_gates() -> None:
    workflow = _workflow("engineering-ci.yml")
    # qualify is a required check: a path-filtered PR run never reports, so the PR never merges
    assert not workflow["on"]["pull_request"]
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert "paths" not in workflow["on"]["push"]
    assert workflow["on"]["schedule"]
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))
    whitespace = next(
        step for step in _steps(workflow) if step.get("name") == "Check changed-file whitespace"
    )

    assert whitespace["env"]["BASE_SHA"] == (
        "${{ github.event.pull_request.base.sha || github.event.before }}"
    )
    assert "HEAD^" not in whitespace["run"]
    fast = next(st for st in _steps(workflow) if st.get("run") == "mise run check-fast")
    batch = next(st for st in _steps(workflow) if st.get("run") == "mise run test-batch")
    full = next(st for st in _steps(workflow) if st.get("run") == "mise run check")
    test_map = next(st for st in _steps(workflow) if st.get("with", {}).get("path") == ".test-map")
    # a `tests` dispatch (the break-glass proof's re-run alone) runs those tests instead
    assert (
        fast["if"] == "github.event_name != 'schedule' && github.event_name != 'workflow_dispatch'"
    )
    # one test run per tree (#1821): only a Mergify batch's draft PR runs the tests, against its base, and only it
    # reads the test map; a PR head runs the cheap checks alone
    assert "env" not in fast
    on_a_batch = "startsWith(github.head_ref, 'mergify/merge-queue/')"
    assert batch["if"] == test_map["if"] == on_a_batch
    assert batch["env"]["GATE_BASE"] == "${{ github.event.pull_request.base.sha }}"
    assert full["if"] == "github.event_name == 'schedule'"
    for command in (
        "mise install",
        "uv sync --frozen",
        "mise run check-fast",
        "mise run test-batch",
        "mise run check",
        "git diff --check",
    ):
        assert command in commands


def test_tag_workflow_is_package_scoped() -> None:
    workflow = _workflow("engineering-tag-check.yml")
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))

    assert workflow["on"]["push"]["tags"] == ["engineering-v*"]
    assert "release-check engineering" in commands
    assert "--skip-smoke" in commands  # CI cannot reach the private smoke repository
    assert "mise run vendor-engineering-check" in commands
    assert "mise run test-engineering-package" in commands
    assert (
        "mise run test-slow" in commands
    )  # a release tag runs the tests `mise run test` leaves out (#1610)
    sync = workflow["jobs"]["consumer-sync"]
    # the bumps wait on the release's identity alone: a red suite on the tagged commit held every bump from 0.34.0
    assert sync["needs"] == "release"
    release = "\n".join(step.get("run", "") for step in workflow["jobs"]["release"]["steps"])
    assert "release-check engineering" in release
    assert "mise run test" not in release
    assert sync["uses"] == "./.github/workflows/engineering-consumer-sync.yml"
    assert sync["with"] == {
        "source_tag": "${{ github.ref_name }}",
        "source_commit": "${{ github.sha }}",
    }


def test_consumer_sync_bumps_every_listed_consumer_ready_and_app_authenticated() -> None:
    workflow = _workflow("engineering-consumer-sync.yml")
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))
    steps = {step.get("name"): step for step in _steps(workflow)}
    proposal = steps["Reconcile the consumer's bump PR"]
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
    # the list comes from the owner's variable, read by a standard-library script before any tool is installed
    plan = workflow["jobs"]["plan"]
    assert plan["steps"][-1]["env"]["ENGINEERING_CONSUMERS"] == "${{ vars.ENGINEERING_CONSUMERS }}"
    assert "python3 -I tools/capability_pack/consumers.py" in plan["steps"][-1]["run"]
    propose = workflow["jobs"]["propose"]
    assert propose["needs"] == "plan"
    assert propose["strategy"]["fail-fast"] == "false"  # one consumer's failure stops only its leg
    assert (
        propose["strategy"]["matrix"]["include"] == "${{ fromJSON(needs.plan.outputs.consumers) }}"
    )
    # one App token per leg, scoped to that consumer alone
    token = next(st for st in propose["steps"] if st.get("id") == "app-token")
    assert token["with"]["owner"] == "${{ steps.target.outputs.owner }}"
    assert token["with"]["repositories"] == "${{ steps.target.outputs.name }}"
    assert (
        steps["Check out the consumer"]["with"]["token"] == "${{ steps.app-token.outputs.token }}"
    )
    assert steps["Check out the consumer"]["with"]["persist-credentials"] == "false"
    assert "prepare-consumer" in commands
    refresh_index = commands.index("agent-sync --refresh")
    commit_index = commands.index("git commit -m")
    frozen_index = commands.index("agent-sync --frozen")
    assert refresh_index < commit_index < frozen_index
    # no GitHub account holds the commits' identity, which a `bot.pack-bump` branch section counts as the author's
    assert "users.noreply.invalid" in commands and "41898282" not in commands
    assert (
        steps["Assert released Codex inventory"]["if"] == "matrix.repository == github.repository"
    )
    assert all("${{" not in step.get("run", "") for step in _steps(workflow))
    assert "resolved_tag" in (ROOT / "tools" / "capability_pack" / "consumer.py").read_text()
    # ready, on the branch the gatekeeper's pack-bump fast path names, superseding older bumps, and queued
    assert propose["env"]["BRANCH"] == "claude/ready-pack-bump-${{ inputs.source_tag }}"
    for flag in (
        "reconcile-pr",
        "--ready",
        "--supersede-prefix claude/ready-pack-bump-",
        "--auto-merge",
        "loop:queued",
    ):
        assert flag in proposal["run"]
    assert "--draft" not in commands
    assert proposal["env"]["GH_TOKEN"] == "${{ steps.app-token.outputs.token }}"
    handover = steps["Hand this repo's bump to its Mergify queue"]
    assert handover["if"] == "matrix.repository == github.repository && matrix.queue == 'mergify'"
    assert handover["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "peter-evans/create-pull-request" not in str(workflow)
    assert [step.get("name") for step in _steps(workflow) if "GH_TOKEN" in step.get("env", {})] == [
        "Reconcile the consumer's bump PR",
        "Hand this repo's bump to its Mergify queue",
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


def test_release_workflow_cuts_on_dispatch_and_tags_the_squash_commit() -> None:
    """One `gh workflow run release.yml` cuts every package and, after the merge, tags each (#1861)."""
    workflow = _workflow("release.yml")
    assert workflow["on"]["workflow_dispatch"]["inputs"]["magnitude"]["options"] == [
        "patch",
        "minor",
    ]
    assert workflow["on"]["push"]["branches"] == ["main"]
    cut, tag = workflow["jobs"]["cut"], workflow["jobs"]["tag"]
    cut_commands = "\n".join(step.get("run", "") for step in cut["steps"])
    tag_commands = "\n".join(step.get("run", "") for step in tag["steps"])
    assert "cli cut-release --magnitude" in cut_commands
    assert 'branch="release/' in cut_commands
    assert "--label loop:queued" in cut_commands
    assert "context=land" in cut_commands
    assert "startsWith(github.event.head_commit.message, 'chore(release):')" in tag["if"]
    assert "cli release-tags" in tag_commands
    assert "release-check" in tag_commands
    assert (
        "git push origin $TAGS" in tag_commands
    )  # one push: every tag is in place for each tag check
    # a push or PR made with github.token starts no workflow: no qualify on the PR, no tag check on the tags
    for job in (cut, tag):
        checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout"))
        assert checkout["with"]["token"] == "${{ secrets.RELEASE_TOKEN }}"
        assert checkout["with"]["fetch-depth"] == "0"


def test_qualify_holds_a_release_pr_to_the_fold() -> None:
    steps = _steps(_workflow("engineering-ci.yml"))
    verify = next(st for st in steps if "release-verify" in st.get("run", ""))
    assert verify["if"] == "startsWith(github.head_ref, 'release/')"
    assert verify["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
