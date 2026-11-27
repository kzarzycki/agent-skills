# ruff: noqa: F811
"""`claude-cloud-run` runs a detached HEAD on the remote branch that holds it, and refuses one no branch holds (#2918)."""

from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent
from test_omnigent_claude_cloud_run import checkout, commit, git  # noqa: F401


def test_a_detached_worktree_at_a_pushed_tip_runs_on_that_branch(
    checkout: Path, tmp_path: Path
) -> None:
    git("checkout", "-qb", "feat", cwd=checkout)
    tip = commit(checkout, "f.txt")
    git("push", "-q", "-u", "origin", "feat", cwd=checkout)
    side = tmp_path / "verifier"
    git("worktree", "add", "-q", "--detach", str(side), tip, cwd=checkout)
    _path, branch, remote, merge, head = omnigent_agent.run_head(side, "pytest")
    assert (branch, remote, merge, head) == ("feat", "origin", "feat", tip)


def test_a_detached_head_no_remote_branch_holds_is_refused(checkout: Path, tmp_path: Path) -> None:
    git("checkout", "-q", "--detach", cwd=checkout)
    commit(checkout, "local.txt")  # never pushed
    with pytest.raises(omnigent_agent.Fail, match="no single branch") as refused:
        omnigent_agent.run_head(checkout, "pytest")
    assert refused.value.code == omnigent_agent.CLOUD_RUN_FAILED
    assert "LOOP_HOST_RUN" in str(refused.value)
