"""approvals.py: the policy is read from the base the PR merges onto, origin/<base>, not the working tree (#1047)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

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
        # a mutation check may take a cache off: the tests below then fail on what it changes, not here
        if clear := getattr(cached, "cache_clear", None):
            clear()


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


def gated(text: str) -> str:
    return gatekeeper_md(f"loop:\n  gate: {text}\n")


@pytest.fixture
def based(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A clone whose origin's main holds the gate `echo default` and whose branch `feature` holds `echo feature`, the
    working tree on main; `push(text)` commits a gate on main and pushes it, as another land would."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    checkout(repo)
    git_in(repo, "remote", "add", "origin", str(origin))
    policy(repo, gated("echo default"), "main's gate")
    git_in(repo, "push", "-q", "origin", "main")
    git_in(repo, "switch", "-qc", "feature")
    policy(repo, gated("echo feature"), "feature's gate")
    git_in(repo, "push", "-q", "origin", "feature")
    git_in(repo, "switch", "-q", "main")
    git_in(repo, "fetch", "-q", "origin")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    pull = {"number": 7, "state": "OPEN", "baseRefName": "feature", "isDraft": False}
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pull)

    def push(text: str) -> None:
        clone = tmp_path / "other"
        if not clone.exists():
            git_in(tmp_path, "clone", "-q", str(origin), str(clone))
            git_in(clone, "config", "user.email", "loop@example.com")
            git_in(clone, "config", "user.name", "loop")
            git_in(clone, "config", "commit.gpgsign", "false")
        policy(clone, text, "another land's policy")
        git_in(clone, "push", "-q", "origin", "HEAD:main")

    return {"repo": repo, "pull": pull, "push": push}


def test_a_pr_into_a_feature_branch_is_gated_by_that_branchs_policy(
    based: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """check, land and local-ci <pr> each read the policy of the base the PR merges onto, the ref land builds on; a
    command with no PR reads the default branch's."""
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        approvals, "checked", lambda *_a: seen.append(("check", approvals.gate()[0])) or 0
    )
    monkeypatch.setattr(
        approvals, "pr_local_ci", lambda *_a: seen.append(("local-ci", approvals.gate()[0])) or 0
    )
    monkeypatch.setattr(
        approvals,
        "landing_here",
        lambda named, base, worst, tracker, loop, only: (
            seen.append(("land", approvals.settings(loop)["gate"])) or (0, False)
        ),
    )
    assert approvals.check("merge", 7) == 0
    assert approvals.local_ci(7) == 0
    assert approvals.landing(7) == (0, False)
    assert seen == [
        ("check", "echo feature"),
        ("local-ci", "echo feature"),
        ("land", "echo feature"),
    ]
    assert approvals.gate()[0] == "echo default"
    based["pull"]["baseRefName"] = "main"
    seen.clear()
    assert approvals.check("merge", 7) == 0
    assert seen == [("check", "echo default")]


def test_land_decides_under_the_policy_it_fetched_under_the_lock(
    based: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another land changes main's policy while this one waits for the lock: the batch is judged under the fetched
    one, and a verdict readied() kept under the old one is not reused."""
    based["pull"]["baseRefName"] = "main"
    monkeypatch.setattr(approvals, "in_cloud", lambda: False)
    monkeypatch.setattr(
        approvals, "readied", lambda named, *_a: [{**pull, "verdict": "old"} for pull in named]
    )
    monkeypatch.setattr(
        approvals,
        "locked",
        lambda *_a: (
            based["push"](gatekeeper_md("loop:\n  gate: echo newer\n  owner: ann\n")) or True
        ),
    )
    monkeypatch.setattr(approvals, "unlock", lambda *_a: subprocess.CompletedProcess([], 0, "", ""))
    judged: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    monkeypatch.setattr(
        approvals,
        "batched",
        lambda named, base, tracker, loop, *_a: (
            judged.append((named, approvals.settings(loop))) or (0, False)
        ),
    )
    assert approvals.landing(7) == (0, False)
    [(named, policy)] = judged
    assert (policy["gate"], policy["owner"]) == ("echo newer", "ann")
    assert "verdict" not in named[0]


def test_the_default_branch_is_asked_of_origin_once_per_run(
    based: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clone without origin/HEAD asks origin for its HEAD: once, however often the policy is read."""
    asked: list[list[str]] = []
    real = subprocess.run

    def run(args: list[str], *rest: Any, **kw: Any) -> Any:
        if "ls-remote" in args:
            asked.append(args)
        return real(args, *rest, **kw)

    monkeypatch.setattr(approvals.subprocess, "run", run)
    for _ in range(3):
        assert approvals.gate()[0] == "echo default"
    assert len(asked) == 1


@pytest.mark.parametrize(
    "command",
    [
        lambda: approvals.go(7, "a" * 40, approvals.DELEGATE),
        lambda: approvals.delegate(7),
        lambda: approvals.brief(7, None, []),
    ],
    ids=["approve merge --by delegate", "delegate", "brief"],
)
def test_each_command_on_a_pr_reads_its_bases_policy(
    based: dict[str, Any], monkeypatch: pytest.MonkeyPatch, command: Any
) -> None:
    based["pull"].update(headRefOid="a" * 40)
    read: list[str | None] = []

    def project(**_kw: Any) -> Any:
        read.append(approvals.POLICY_BASE.get())
        raise approvals.Refused("read")

    monkeypatch.setattr(approvals, "project", project)
    with pytest.raises(approvals.Refused, match="read"):
        command()
    assert read == ["feature"]
