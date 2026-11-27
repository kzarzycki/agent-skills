"""gatekeeper.py: the forge's remote is the branch's upstream's, else gatekeeper.md's `forge_remote`, else `origin` (#2710)."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import approvals, gatekeeper_md, git_in
from test_approvals_policy_base import NEW, OLD, checkout, fresh, policy  # noqa: F401


def two_remotes(tmp_path: Path) -> tuple[Path, Path, Path]:
    """`origin` (the upstream) holds main with one gate; the fork holds main with gate steps, and the branch tracks the fork."""
    origin, fork, repo = tmp_path / "origin.git", tmp_path / "fork.git", tmp_path / "repo"
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(fork))
    checkout(repo)
    git_in(repo, "remote", "add", "origin", str(origin))
    git_in(repo, "remote", "add", "fork", str(fork))
    policy(repo, OLD, "one gate")
    git_in(repo, "push", "-q", "origin", "main")
    policy(repo, NEW, "gate steps")
    git_in(repo, "push", "-q", "-u", "fork", "main")
    git_in(repo, "fetch", "-q", "--all")
    return origin, fork, repo


def test_the_policy_is_read_from_the_remote_the_branch_tracks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _origin, _fork, repo = two_remotes(tmp_path)
    git_in(
        repo, "reset", "-q", "--hard", "HEAD~1"
    )  # the working tree holds the old policy: the fork's base wins
    monkeypatch.chdir(repo)
    assert approvals.forge() == "fork"
    assert [step["name"] for step in approvals.gate_plan()] == ["lint", "unit"]
    assert approvals.policy_base(str(repo)) == (
        "fork/main",
        git_in(repo, "rev-parse", "fork/main").strip(),
    )


def test_the_base_is_fetched_from_the_tracked_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, _fork, repo = two_remotes(tmp_path)
    monkeypatch.chdir(repo)
    fresh_tip = policy(repo, NEW + "\n", "newer")
    git_in(repo, "push", "-q", "fork", "main")
    git_in(repo, "update-ref", "-d", "refs/remotes/fork/main")
    approvals.base_policy("main", None)
    assert git_in(repo, "rev-parse", "refs/remotes/fork/main").strip() == fresh_tip
    assert git_in(origin, "rev-parse", "main").strip() != fresh_tip  # origin never saw it


def test_the_setting_then_origin_are_the_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _origin, _fork, repo = two_remotes(tmp_path)
    monkeypatch.chdir(repo)
    git_in(repo, "branch", "--unset-upstream")
    assert approvals.forge() == "origin"
    policy(
        repo,
        gatekeeper_md("loop:\n  gate: mise run check\n  forge_remote: fork\n"),
        "names the fork",
    )
    assert approvals.forge() == "origin"  # the working tree's own copy decides nothing (#2710)
    git_in(repo, "push", "-q", "origin", "main")  # origin's default branch holds it now
    assert approvals.forge() == "fork"
    git_in(
        repo, "push", "-q", "fork", "main"
    )  # the base holds the setting, which the schema accepts
    assert approvals.settings(approvals.project()[1])["forge_remote"] == "fork"


def test_a_detached_head_whose_own_policy_names_another_remote_still_uses_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PR's working-tree gatekeeper.md never picks the remote its base and policy are judged against (#2710)."""
    _origin, _fork, repo = two_remotes(tmp_path)
    monkeypatch.chdir(repo)
    policy(
        repo,
        gatekeeper_md("loop:\n  gate: mise run check\n  forge_remote: fork\n"),
        "the PR names the fork",
    )
    git_in(repo, "checkout", "-q", "--detach", "HEAD")
    assert approvals.forge() == "origin"
    assert approvals.policy_base(str(repo)) == (
        "origin/main",
        git_in(repo, "rev-parse", "origin/main").strip(),
    )


@pytest.mark.parametrize("remotes", ["origin\n", ""])
def test_a_checkout_with_only_origin_asks_git_for_its_remotes_and_nothing_else(
    remotes: str,
) -> None:
    """Every rule ends in `origin` there, so the five other git calls it saved are never made (#1400)."""
    asked: list[tuple[str, ...]] = []

    def git(*args: str) -> str:
        asked.append(args)
        return remotes

    assert approvals.loop_events.forge_remote(None, git) == "origin"
    assert asked == [("remote",)]
