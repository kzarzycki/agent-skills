# ruff: noqa: F811
"""`claude-cloud-run` runs a detached HEAD on the remote branch that holds it, and refuses one no branch holds (#2918)."""

from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent
from test_omnigent_claude_cloud_run import (  # noqa: F401
    FAILED,
    checkout,
    cloud,
    cloud_run,
    commit,
    git,
    no_model,
    no_sleep,
    trusted_folders,
)


def test_a_detached_worktree_at_a_pushed_tip_runs_on_that_branch(
    checkout: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    og = cloud(monkeypatch, "REPORT\nEXIT: 0\n1 passed")
    git("checkout", "-qb", "feat", cwd=checkout)
    tip = commit(checkout, "f.txt")
    git("push", "-q", "-u", "origin", "feat", cwd=checkout)
    # a second clone that fetched only the tip commit, so it has no tracking ref for the branch
    other = tmp_path / "other"
    git(
        "clone",
        "-q",
        "--no-checkout",
        "--single-branch",
        "--branch",
        "main",
        str(tmp_path / "remote.git"),
        str(other),
        cwd=tmp_path,
    )
    git("config", "user.email", "t@example.com", cwd=other)
    git("config", "user.name", "t", cwd=other)
    git("fetch", "-q", "origin", tip, cwd=other)
    git("checkout", "-q", "--detach", tip, cwd=other)
    assert not git("branch", "-r", "--contains", "HEAD", cwd=other)
    assert cloud_run(other, "pytest") == 0
    assert f"exited 0 on {tip[:12]}" in capsys.readouterr().out
    brief = omnigent_agent.text_of(og.sessions["s0"][1])
    assert f"git fetch origin feat && git checkout --detach {tip}" in brief


def test_a_stale_tracking_ref_does_not_make_the_branch_ambiguous(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloud(monkeypatch, "REPORT\nEXIT: 0")
    git("checkout", "-qb", "old", cwd=checkout)
    tip = commit(checkout, "o.txt")
    git("push", "-q", "-u", "origin", "old", cwd=checkout)
    git("checkout", "-qb", "feat", cwd=checkout)
    git("push", "-q", "-u", "origin", "feat", cwd=checkout)
    git(
        "push", "-q", "origin", "--delete", "old", cwd=checkout
    )  # origin/old stays here until pruned
    git("checkout", "-q", "--detach", tip, cwd=checkout)
    assert cloud_run(checkout, "pytest") == 0


def test_a_detached_head_no_remote_branch_holds_exits_125_with_the_fallback(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = cloud(monkeypatch, "REPORT\nEXIT: 0")
    git("checkout", "-q", "--detach", cwd=checkout)
    commit(checkout, "local.txt")  # never pushed
    assert cloud_run(checkout, "pytest") == FAILED
    err = capsys.readouterr().err
    assert "detached HEAD that no single branch of origin holds" in err
    assert "LOOP_HOST_RUN=<reason> pytest" in err
    assert og.sessions == {}
