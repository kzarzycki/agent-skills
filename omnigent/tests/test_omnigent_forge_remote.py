# ruff: noqa: F811
"""`claude-cloud-run` takes the forge's remote from the branch's upstream, the launch dir sits beside the worktree it
serves, a trusted parent folder trusts its children, and a `--shared` clone is refused before any session (#2710)."""

import json
import subprocess
from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent
from test_omnigent_claude_cloud_run import checkout, commit, git  # noqa: F401


def fork_of(tmp_path: Path, work: Path) -> None:
    """A second bare remote ``fork`` holding main, which the branch ``main`` of ``work`` tracks while ``origin`` stays."""
    fork = tmp_path / "fork.git"
    git("init", "-q", "--bare", "-b", "main", str(fork), cwd=tmp_path)
    git("remote", "add", "fork", f"file://{fork}", cwd=work)
    git("push", "-q", "-u", "fork", "main", cwd=work)


def test_the_forge_remote_is_the_branchs_upstream(checkout: Path, tmp_path: Path) -> None:
    assert omnigent_agent.forge_remote(checkout) == "origin"
    fork_of(tmp_path, checkout)
    assert omnigent_agent.forge_remote(checkout) == "fork"
    _path, _branch, remote, merge, _head = omnigent_agent.run_head(checkout)
    assert (remote, merge) == ("fork", "main")  # the repo and base the cloud session clones


def test_the_setting_is_the_fallback_then_origin(checkout: Path, tmp_path: Path) -> None:
    git("remote", "add", "fork", "file:///nowhere", cwd=checkout)
    git("branch", "--unset-upstream", cwd=checkout)
    assert omnigent_agent.forge_remote(checkout) == "origin"
    policy = checkout / "docs" / "agents" / "gatekeeper.md"
    policy.parent.mkdir(parents=True)
    policy.write_text("```yaml\nloop:\n  forge_remote: fork\n```\n")
    assert omnigent_agent.forge_remote(checkout) == "fork"
    policy.write_text("```yaml\nloop:\n  forge_remote: nosuch\n```\n")
    assert omnigent_agent.forge_remote(checkout) == "origin"


def test_the_gatekeeper_reads_the_same_remote(checkout: Path, tmp_path: Path) -> None:
    events = omnigent_agent.EVENTS
    assert events is not None
    fork_of(tmp_path, checkout)
    assert events.forge_remote(checkout) == omnigent_agent.forge_remote(checkout) == "fork"
    # a ref pushed through the gatekeeper's helper lands on the fork, not on origin
    commit(checkout, "e.txt")
    events.push(checkout, "HEAD:refs/loop/x/y")
    assert "refs/loop/x/y" in events.remote_refs(checkout, "refs/loop/*/*")
    origin = git("ls-remote", "origin", "refs/loop/*", cwd=checkout)
    assert "refs/loop/x/y" not in origin


def test_the_launch_dir_sits_beside_the_worktree(checkout: Path, tmp_path: Path) -> None:
    side = tmp_path / "wt" / "side"
    side.parent.mkdir()
    git("worktree", "add", "-q", "-b", "side", str(side), cwd=checkout)
    git("push", "-q", "-u", "origin", "side", cwd=side)
    place = omnigent_agent.cloud_run_dir(side, "side", "origin", "side")
    assert place == side.parent / "claude-cloud-run-side"
    assert place.is_dir()
    assert not (checkout / ".worktrees").exists()


def test_a_trusted_parent_folder_trusts_its_children(tmp_path: Path) -> None:
    config = tmp_path / "claude.json"
    child = tmp_path / "trusted" / "a" / "b"
    child.mkdir(parents=True)
    config.write_text(
        json.dumps({"projects": {str(tmp_path / "trusted"): {"hasTrustDialogAccepted": True}}})
    )
    assert omnigent_agent.folder_trusted(child, config)
    assert not omnigent_agent.folder_trusted(tmp_path / "other", config)


def test_a_shared_clone_is_refused_before_any_session(
    checkout: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shared = tmp_path / "shared"
    subprocess.run(["git", "clone", "-q", "--shared", str(checkout), str(shared)], check=True)
    assert (shared / ".git" / "objects" / "info" / "alternates").is_file()
    with pytest.raises(omnigent_agent.Fail, match="borrows its objects"):
        omnigent_agent.refuse_alternates(shared)
    omnigent_agent.refuse_alternates(checkout)  # a full clone passes
    # claude-cloud-run's own refusal comes before the launch dir and any session
    git("config", "user.email", "t@example.com", cwd=shared)
    with pytest.raises(omnigent_agent.Fail):
        omnigent_agent.run_head(shared, "pytest")
