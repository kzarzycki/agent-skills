from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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
    # a `tests` dispatch (the break-glass proof's rerun) runs rerun-tests on those ids instead
    assert fast["if"] == (
        "github.event_name != 'schedule' && github.event_name != 'workflow_dispatch'"
        " && steps.tested.outputs.skip != 'true' && steps.record.outputs.recorded != 'true'"
    )
    # one test run per tree (#1821): only a Mergify batch's draft PR runs the tests, against its base, and only it
    # reads the test map; a PR head runs the cheap checks alone
    assert "env" not in fast
    on_a_batch = "startsWith(github.head_ref, 'mergify/merge-queue/')"
    assert test_map["if"] == on_a_batch
    assert (
        batch["if"] == f"{on_a_batch} && steps.read.outputs.red != 'read'"
    )  # a rerun's read of the red skips it
    assert batch["env"]["GATE_BASE"] == "${{ github.event.pull_request.base.sha }}"
    assert full["if"] == "github.event_name == 'schedule' && steps.tested.outputs.skip != 'true'"
    for command in (
        "mise install",
        "uv sync --frozen",
        "mise run check-fast",
        "mise run test-batch",
        "mise run check",
        "git diff --check",
    ):
        assert command in commands


def test_the_scheduled_run_runs_acceptance_all_and_a_red_one_opens_the_nightly_issue() -> None:
    """#1386: the scheduled run runs every spec's acceptance checks, and a red one calls `nightly.py red`."""
    workflow = _workflow("engineering-ci.yml")
    jobs = workflow["jobs"]
    acceptance = jobs["acceptance"]
    assert acceptance["if"] == "github.event_name == 'schedule'"
    assert any(step.get("run", "").endswith("acceptance.py --all") for step in acceptance["steps"])
    red = jobs["nightly-red"]
    assert set(red["needs"]) == {"qualify", "acceptance"}
    assert red["if"].startswith("always() && github.event_name == 'schedule'")
    assert "needs.qualify.result == 'failure'" in red["if"]
    assert "needs.acceptance.result == 'failure'" in red["if"]
    # the one job that writes issues; the workflow's default stays read-only
    assert red["permissions"]["issues"] == "write"
    assert "issues" not in workflow["permissions"]
    call = next(step for step in red["steps"] if "nightly.py red" in step.get("run", ""))
    for flag in ("--last-green", "--red", "--run"):
        assert flag in call["run"]


def test_tag_workflow_is_package_scoped() -> None:
    workflow = _workflow("engineering-tag-check.yml")
    commands = "\n".join(step.get("run", "") for step in _steps(workflow))

    assert workflow["on"]["push"]["tags"] == ["engineering-v*", "!engineering-v*-next"]
    assert "release-check engineering" in commands
    assert "--skip-smoke" in commands  # CI cannot reach the private smoke repository
    assert "mise run vendor-engineering-check" in commands
    assert "mise run test-engineering-package" in commands
    assert (
        "mise run test-slow" in commands
    )  # a release tag runs the tests `mise run test` leaves out (#1610)
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
    assert (
        "resolved_tag"
        in (ROOT / "vendoring/skills/vendoring/scripts/capability_pack/consumer.py").read_text()
    )
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


def test_qualify_rerun_attempt_calls_rerun_tests_never_the_failed_tests_alone() -> None:
    """R5 (#1794): a rerun attempt of a red batch run reruns the red run's selection, never its failed ids alone."""
    text = (WORKFLOWS / "engineering-ci.yml").read_text()
    workflow = _workflow("engineering-ci.yml")
    steps = _steps(workflow)
    runs = [step.get("run", "") for step in steps]

    assert workflow["permissions"]["actions"] == "read"
    # the red attempt's artifact, read only on a later attempt of a batch run
    red = next(st for st in steps if st.get("id") == "red")
    assert "github.run_attempt != '1'" in red["if"]
    assert red["with"]["name"] == "failed-tests"
    assert red["continue-on-error"] == "true"
    # one rerun-tests call per path, each handing it the failed-tests file and the head
    reruns = [run for run in runs if "approvals.py rerun-tests" in run]
    assert len(reruns) == 2
    assert all(
        "--red " in run and "failed-tests.json" in run or "dispatch.json" in run for run in reruns
    )
    # a pytest run on the failed ids alone is the shortcut R5 forbids
    assert not any("pytest" in run and "TESTS" in run for run in runs)
    assert "failed alone" not in text and "to run alone" not in text
    # with a red read, the usual batch step is skipped and the rerun's pass counts as the selection
    batch = next(st for st in steps if st.get("id") == "batch")
    assert "steps.read.outputs.red != 'read'" in batch["if"]
    rerun = next(st for st in steps if st.get("id") == "rerun")
    assert rerun["if"] == "steps.read.outputs.red == 'read'"
    selection = next(st for st in steps if st.get("id") == "selection")
    assert "steps.rerun.outcome == 'success'" in selection["if"]
    # V1: the artifact handling holds under each undoing
    assert "startsWith(github.head_ref, 'mergify/merge-queue/')" in red["if"]
    read = next(st for st in steps if st.get("id") == "read")
    assert '["failed"]' in read["run"] and "sys.exit(0 if" in read["run"]
    upload = next(
        st for st in steps if st.get("with", {}).get("path") == ".qualify/failed-tests.json"
    )
    assert upload["with"]["overwrite"] == "true"


def _rerun_check(tmp_path: Path, red: list[str], ran: list[tuple[str, str]] | None):
    """Run the `rerun` step's lines after `rerun-tests` (the missing-id check) under `bash -e`, as Actions does, in a
    scratch checkout holding the red attempt's failed ids and, when `ran` is given, a JUnit file of the tests that ran."""
    step = next(st for st in _steps(_workflow("engineering-ci.yml")) if st.get("id") == "rerun")
    lines = step["run"].splitlines()
    after = lines[next(n for n, line in enumerate(lines) if "rerun-tests" in line) + 1 :]
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "failed_tests.py").write_text(
        (ROOT / "tools" / "failed_tests.py").read_text()
    )
    (tmp_path / ".qualify" / "red").mkdir(parents=True)
    (tmp_path / ".qualify" / "red" / "failed-tests.json").write_text(json.dumps({"failed": red}))
    if ran is not None:
        cases = "".join(f'<testcase classname="{c}" name="{n}"/>' for c, n in ran)
        (tmp_path / ".qualify" / "junit.xml").write_text(
            f"<testsuites><testsuite>{cases}</testsuite></testsuites>"
        )
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python3").symlink_to(
        sys.executable
    )  # the repo's python, as mise puts it on PATH in CI
    return subprocess.run(
        ["bash", "-e", "-c", "\n".join(after)],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_rerun_passes_only_when_it_ran_every_test_the_red_attempt_failed(tmp_path: Path) -> None:
    (tmp_path / "ok").mkdir()
    ran = [("a.b", "t1"), ("a.b", "t[x y]"), ("a.b", "t3")]
    ok = _rerun_check(tmp_path / "ok", ["a.b::t1", "a.b::t[x y]"], ran)
    assert ok.returncode == 0, ok.stderr
    (tmp_path / "missing").mkdir()
    gone = _rerun_check(tmp_path / "missing", ["a.b::t1", "a.b::t2"], [("a.b", "t1")])
    assert gone.returncode != 0 and "a.b::t2" in gone.stderr
    (tmp_path / "none").mkdir()
    assert (
        _rerun_check(tmp_path / "none", ["a.b::t1"], None).returncode != 0
    )  # no JUnit: nothing ran
    (tmp_path / "empty").mkdir()
    assert _rerun_check(tmp_path / "empty", ["a.b::t1"], []).returncode != 0
