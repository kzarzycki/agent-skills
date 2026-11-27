"""The workflow that moves a cloud session's loop-gate/ and loop-event/ branches to their refs/loop/ names (#2821,
.github/workflows/loop-refs.yml): triggered by those branches alone, holding the one write token, checking out and
running none of the pushed code, and moving each name as the readers expect. Its shell step is run here for real,
against a local origin."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "loop-refs.yml"


def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def test_it_runs_on_the_three_branch_families_alone_with_the_write_token() -> None:
    found = workflow()
    assert found[True]["push"]["branches"] == [
        "loop-gate/**",
        "loop-event/**",
        "claude/loop-event/**",
    ]  # PyYAML reads the key `on` as True
    assert found["permissions"] == {"contents": "write"}
    [job] = found["jobs"].values()
    assert [one.get("uses", "").split("@")[0] for one in job["steps"]] == ["actions/checkout", ""]
    assert (
        "${{ github.ref_name }}" not in job["steps"][1]["run"]
    )  # reaches the shell through env only
    assert found["concurrency"] == {
        "group": "loop-refs-${{ github.ref }}",
        "cancel-in-progress": False,
    }  # two beats of one branch never run together


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    ).stdout


@pytest.mark.parametrize(
    ("branch", "dest"),
    [
        ("loop-gate/abc-123", "refs/loop/gate/abc-123"),
        ("loop-event/lead/feat/x", "refs/loop/lead/feat/x"),
        ("claude/loop-event/verifier/feat/x", "refs/loop/verifier/feat/x"),
    ],
)
def test_each_branch_moves_to_its_ref_and_is_deleted(
    tmp_path: Path, branch: str, dest: str
) -> None:
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "init", "-q", str(clone))
    git(clone, "remote", "add", "origin", str(origin))
    git(
        clone,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@invalid",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "a",
    )
    sha = git(clone, "rev-parse", "HEAD").strip()
    git(clone, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    git(
        clone,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@invalid",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "b",
    )
    newer = git(clone, "rev-parse", "HEAD").strip()
    script = next(s for s in workflow()["jobs"]["move"]["steps"] if "run" in s)["run"]
    git(clone, "push", "-q", "--force", "origin", f"{sha}:refs/heads/{branch}")
    subprocess.run(
        ["bash", "-c", script],
        cwd=clone,
        check=True,
        env=os.environ | {"BRANCH": branch, "SHA": sha},
    )
    assert git(origin, "rev-parse", dest).strip() == sha
    assert git(origin, "for-each-ref", "--format=%(refname)", "refs/heads/") == ""
    # a later beat of the same event: the branch again, a newer commit, the ref replaced
    git(clone, "push", "-q", "origin", f"{newer}:refs/heads/{branch}")
    subprocess.run(
        ["bash", "-c", script],
        cwd=clone,
        check=True,
        env=os.environ | {"BRANCH": branch, "SHA": newer},
    )
    assert git(origin, "rev-parse", dest).strip() == newer


def test_a_late_run_for_an_older_commit_changes_nothing_and_a_run_for_a_gone_branch_succeeds(
    tmp_path: Path,
) -> None:
    """#2821 F1: the run for beat 1 starts after beat 2 moved the branch: it must not overwrite the ref with the older
    commit or delete the newer branch; a run whose branch is already deleted exits 0."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "init", "-q", str(clone))
    git(clone, "remote", "add", "origin", str(origin))
    ident = ["-c", "user.name=t", "-c", "user.email=t@invalid"]
    git(clone, *ident, "commit", "-q", "--allow-empty", "-m", "a")
    older = git(clone, "rev-parse", "HEAD").strip()
    git(clone, *ident, "commit", "-q", "--allow-empty", "-m", "b")
    newer = git(clone, "rev-parse", "HEAD").strip()
    branch = "loop-event/lead/feat/x"
    script = next(s for s in workflow()["jobs"]["move"]["steps"] if "run" in s)["run"]

    def run(sha: str) -> None:
        subprocess.run(
            ["bash", "-c", script],
            cwd=clone,
            check=True,
            env=os.environ | {"BRANCH": branch, "SHA": sha},
        )

    git(clone, "push", "-q", "origin", f"{newer}:refs/heads/{branch}")  # beat 2 already there
    run(older)  # beat 1's late run
    assert git(origin, "for-each-ref", "--format=%(refname)") == f"refs/heads/{branch}\n"
    run(newer)
    assert git(origin, "rev-parse", "refs/loop/lead/feat/x").strip() == newer
    assert git(origin, "for-each-ref", "--format=%(refname)", "refs/heads/") == ""
    run(newer)  # the same run again, the branch gone: no error
    assert git(origin, "rev-parse", "refs/loop/lead/feat/x").strip() == newer
