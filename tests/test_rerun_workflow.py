"""The independent rerun's CI half (#2240, .github/workflows/rerun.yml): the PR's code runs only under a token that
can't write, and the job holding the write token checks out nothing of the PR, runs none of its code and pushes only
a `loop-gate/` record branch of the PR's head. Its push step is run here for real, against a local origin."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "rerun.yml"


def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(one for one in job["steps"] if one.get("name") == name)


def test_no_job_but_the_push_holds_a_write_token() -> None:
    found = workflow()
    assert found["permissions"] == {}
    assert found["jobs"]["rerun"]["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert found["jobs"]["push"]["permissions"] == {"contents": "write"}
    assert set(found["jobs"]) == {"rerun", "push"}


def test_the_run_job_reads_the_rating_first_and_runs_the_rest_only_when_a_rerun_is_needed() -> None:
    steps = workflow()["jobs"]["rerun"]["steps"]
    rating = next(i for i, one in enumerate(steps) if one.get("id") == "rating")
    assert "check rerun" in steps[rating]["run"]
    assert '*"rerun: needed"*) echo "needed=true"' in steps[rating]["run"]
    assert all("needed == 'true'" in one.get("if", "") for one in steps[rating + 1 : -1])
    record = next(one for one in steps if one.get("id") == "record")
    assert "local-ci --record --rerun --no-push" in record["run"]
    checkout = steps[0]
    assert checkout["with"]["persist-credentials"] is False


def test_the_push_job_checks_out_and_runs_nothing_of_the_pr() -> None:
    job = workflow()["jobs"]["push"]
    assert job["needs"] == "rerun"
    assert "needs.rerun.result == 'success'" in job["if"]
    uses = [one["uses"].split("@")[0] for one in job["steps"] if "uses" in one]
    assert uses == ["actions/download-artifact"]
    runs = "\n".join(one.get("run", "") for one in job["steps"])
    for word in ("checkout", "uv ", "mise", "python", "pip", "npm", "make", "bash ./", "sh ./"):
        assert word not in runs, word


def test_a_fork_pr_skips_the_push_and_says_so_in_one_line() -> None:
    job = workflow()["jobs"]["push"]
    fork = step(job, "Fork PR")
    assert fork["if"] == "github.event.pull_request.head.repo.full_name != github.repository"
    assert len(fork["run"].strip().splitlines()) == 1
    for one in job["steps"][1:]:
        assert one["if"] == "github.event.pull_request.head.repo.full_name == github.repository"


# --- the push step, run against a local origin ---


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> dict[str, Any]:
    """A bare origin holding a PR head, and a clone where a record commit is made and bundled as the run job does."""
    bare, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(tmp_path, "clone", "-q", str(bare), str(work))
    git(work, "config", "user.email", "loop@example.com")
    git(work, "config", "user.name", "loop")
    (work / "app.py").write_text("value = 1\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "base")
    (work / "app.py").write_text("value = 2\n")
    git(work, "commit", "-qam", "head")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/pr")
    head = git(work, "rev-parse", "HEAD")
    tree = git(work, "rev-parse", "HEAD^{tree}")
    # the push step's own allowance for fetching a commit by its id, which GitHub serves
    git(bare, "config", "uploadpack.allowAnySHA1InWant", "true")
    return {"bare": bare, "work": work, "head": head, "tree": tree, "tmp": tmp_path}


def bundle(state: dict[str, Any], refs: dict[str, str]) -> None:
    """The run job's artifact: `refs` (ref: commit) bundled against the head."""
    work = state["work"]
    for ref, commit in refs.items():
        git(work, "update-ref", ref, commit)
    (state["tmp"] / "record").mkdir(exist_ok=True)
    git(
        work,
        "bundle",
        "create",
        str(state["tmp"] / "record" / "rerun.bundle"),
        *refs,
        f"^{state['head']}",
    )


def record(state: dict[str, Any], tree: str | None = None, parent: str | None = None) -> str:
    return git(
        state["work"],
        "commit-tree",
        tree or state["tree"],
        "-p",
        parent or state["head"],
        "-m",
        f"Tree {state['tree']} on {state['head'][:12]}: LOOP_RERUN=1 mise run check-fast",
    )


def pushed(state: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    """The workflow's push step, its origin URL pointed at the local origin."""
    script = step(workflow()["jobs"]["push"], "Push the record branch")["run"]
    script = script.replace(
        '"https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"',
        f'"{state["bare"]}"',
    )
    assert str(state["bare"]) in script
    env = {
        **os.environ,
        "RUNNER_TEMP": str(state["tmp"]),
        "HEAD_SHA": state["head"],
        "GH_TOKEN": "unused",
        "GITHUB_REPOSITORY": "o/r",
    }
    return subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=False
    )


def branches(state: dict[str, Any]) -> str:
    return git(state["bare"], "for-each-ref", "--format=%(refname)", "refs/heads/loop-gate/")


def test_a_record_of_the_head_is_pushed_as_its_loop_gate_branch(origin: dict[str, Any]) -> None:
    commit = record(origin)
    ref = f"refs/heads/loop-gate/{origin['tree']}-0123456789ab"
    bundle(origin, {ref: commit})
    run = pushed(origin)
    assert run.returncode == 0, run.stderr
    assert git(origin["bare"], "rev-parse", ref) == commit


@pytest.mark.parametrize(
    "case",
    ["another-branch", "another-tree-name", "another-parent", "another-tree", "two-branches"],
)
def test_anything_but_one_record_branch_of_the_heads_tree_is_refused(
    origin: dict[str, Any], case: str
) -> None:
    good = f"refs/heads/loop-gate/{origin['tree']}-0123456789ab"
    base_tree = git(origin["work"], "rev-parse", "HEAD~1^{tree}")
    refs = {
        "another-branch": {"refs/heads/main": record(origin)},
        "another-tree-name": {f"refs/heads/loop-gate/{base_tree}-0123456789ab": record(origin)},
        # a commit on top of the head, carried in the bundle, so only the parent check tells it apart
        "another-parent": {good: record(origin, parent=record(origin))},
        "another-tree": {good: record(origin, tree=base_tree)},
        "two-branches": {good: record(origin), "refs/heads/loop-gate/x": record(origin)},
    }[case]
    bundle(origin, refs)
    run = pushed(origin)
    assert run.returncode != 0
    said = {
        "another-branch": "is no record branch of the head's tree",
        "another-tree-name": "is no record branch of the head's tree",
        "another-parent": "one parent is not the head",
        "another-tree": "holds another tree than the head",
        "two-branches": "the bundle holds more than one branch",
    }[case]
    assert "refused: " in run.stdout and said in run.stdout, run.stdout + run.stderr
    assert branches(origin) == ""
    assert git(origin["bare"], "for-each-ref", "--format=%(refname)", "refs/heads/main") == ""
