"""approvals.py: the policy is read from the base the PR merges onto, origin/<base>, not the working tree (#1047)."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    gatekeeper_md,
    git_in,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

OLD = gatekeeper_md("loop:\n  gate: mise run check\n")
NEW = gatekeeper_md(
    "loop:\n  gate_steps:\n"
    "    - name: lint\n      command: mise run lint\n      where: any\n"
    "    - name: unit\n      command: mise run unit\n      where: any\n"
)
UNBASED = "approvals.py: no origin/<base> ref, so the policy is read from the working tree\n"


@pytest.fixture(autouse=True)
def fresh() -> None:
    """No base found and no line printed yet this run, so a test's stderr doesn't depend on which ran before it."""
    for cached in (approvals.default_base, approvals.unbased, approvals.differs):
        cached.cache_clear()


def checkout(repo: Path) -> None:
    repo.mkdir()
    git_in(repo, "init", "-q", "-b", "main")
    git_in(repo, "config", "user.email", "loop@example.com")
    git_in(repo, "config", "user.name", "loop")
    git_in(repo, "config", "commit.gpgsign", "false")


def policy(repo: Path, text: str, message: str) -> str:
    agents = repo / "docs" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "gatekeeper.md").write_text(text)
    git_in(repo, "add", "-A")
    git_in(repo, "commit", "-qm", message)
    return git_in(repo, "rev-parse", "HEAD").strip()


def test_a_checkout_behind_its_base_gates_under_the_bases_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The working tree is a commit behind origin/main, whose newer commit adds `gate_steps`: the stepped plan, and
    one line naming the file and both commits."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    checkout(repo)
    git_in(repo, "remote", "add", "origin", str(origin))
    old = policy(repo, OLD, "one gate")
    new = policy(repo, NEW, "gate steps")
    git_in(repo, "push", "-q", "origin", "main")
    git_in(repo, "fetch", "-q", "origin")
    git_in(repo, "reset", "-q", "--hard", old)  # the host checkout sat behind origin/main
    monkeypatch.chdir(repo)
    assert [step["name"] for step in approvals.gate_plan()] == ["lint", "unit"]
    assert capsys.readouterr().err == (
        f"approvals.py: docs/agents/gatekeeper.md in the working tree (at {old}) differs from origin/main's"
        f" (at {new}): using origin/main's\n"
    )
    approvals.gate_plan()
    assert capsys.readouterr().err == ""  # once per run


def test_a_checkout_without_origin_reads_the_working_tree_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    checkout(repo)
    policy(repo, OLD, "one gate")
    (repo / "docs" / "agents" / "gatekeeper.md").write_text(NEW)  # uncommitted, and still read
    monkeypatch.chdir(repo)
    assert [step["name"] for step in approvals.gate_plan()] == ["lint", "unit"]
    assert capsys.readouterr().err == UNBASED
    approvals.gate_plan()
    assert capsys.readouterr().err == ""  # once per run


def test_the_base_is_the_branch_origin_head_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clone's origin/HEAD names the default branch, read before asking origin, whose HEAD may name another."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    checkout(repo)
    git_in(repo, "remote", "add", "origin", str(origin))
    old = policy(repo, OLD, "one gate")
    git_in(repo, "push", "-q", "origin", "main")
    new = policy(repo, NEW, "gate steps")
    git_in(repo, "push", "-q", "origin", "HEAD:refs/heads/trunk")
    git_in(repo, "fetch", "-q", "origin")
    git_in(repo, "remote", "set-head", "origin", "trunk")
    git_in(repo, "reset", "-q", "--hard", old)
    monkeypatch.chdir(repo)
    assert [step["name"] for step in approvals.gate_plan()] == ["lint", "unit"]
    assert f"differs from origin/trunk's (at {new})" in capsys.readouterr().err
