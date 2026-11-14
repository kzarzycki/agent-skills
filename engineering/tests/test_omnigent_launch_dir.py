"""launch-dir makes a worktree of a same-repository checkout, so it inherits the checkout's folder
trust, and `start` refuses a cloud launch from an untrusted folder before any session exists (#980)."""

import json
import subprocess
from pathlib import Path

import pytest
from test_omnigent_agent import (  # noqa: F401  (the fixtures apply here by name)
    REAL_TRUSTED,
    FakeOmnigent,
    no_model,
    no_sleep,
    omnigent_agent,
    this_repo,
    trusted_folders,
)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def bare(tmp_path: Path) -> Path:
    """A bare remote that serves partial clones, holding main and a PR branch."""
    seed = tmp_path / "seed"
    git("init", "-q", "-b", "main", str(seed), cwd=tmp_path)
    git("config", "user.email", "t@example.com", cwd=seed)
    git("config", "user.name", "t", cwd=seed)
    (seed / "a.txt").write_text("a")
    git("add", ".", cwd=seed)
    git("commit", "-qm", "one", cwd=seed)
    git("checkout", "-qb", "pr-branch", cwd=seed)
    (seed / "b.txt").write_text("b")
    git("add", ".", cwd=seed)
    git("commit", "-qm", "two", cwd=seed)
    git("checkout", "-q", "main", cwd=seed)
    remote = tmp_path / "remote.git"
    git("clone", "-q", "--bare", str(seed), str(remote), cwd=tmp_path)
    git("config", "uploadpack.allowFilter", "true", cwd=remote)
    return remote


@pytest.fixture
def real_trust(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The real trust check, reading a config of the test's own."""
    config = tmp_path / "claude.json"
    monkeypatch.setattr(omnigent_agent, "folder_trusted", REAL_TRUSTED)
    monkeypatch.setattr(omnigent_agent, "claude_config", lambda: config)
    return config


def missing(repo: Path, rev: str) -> list[str]:
    """The objects ``rev`` reaches that ``repo`` lacks, listed without fetching them."""
    out = git("rev-list", "--objects", "--missing=print", rev, cwd=repo)
    return [line for line in out.splitlines() if line.startswith("?")]


def checkout(bare: Path, dest: Path, *flags: str) -> Path:
    git("clone", "-q", *flags, f"file://{bare}", str(dest), cwd=dest.parent)
    git("config", "user.email", "t@example.com", cwd=dest)
    return dest


def test_a_clone_launch_dir_is_blobless(tmp_path: Path, bare: Path) -> None:
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "pr-branch", "env_1", dest, here=tmp_path)
    assert len(missing(dest, "HEAD")) == 2  # a.txt and b.txt, never fetched


def test_a_launch_dir_inside_a_same_repo_checkout_is_a_worktree_without_blobs(
    tmp_path: Path, bare: Path, real_trust: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = checkout(bare, tmp_path / "main", "--no-checkout", "--filter=blob:none")
    before = missing(main, "origin/pr-branch")
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "pr-branch", "env_1", dest, here=main)
    assert git("rev-parse", "--git-common-dir", cwd=dest) == str(main / ".git")  # a linked worktree
    assert git("rev-parse", "HEAD", cwd=dest) == git("rev-parse", "origin/pr-branch", cwd=main)
    assert not (dest / "a.txt").exists() and not (dest / "b.txt").exists()
    assert not Path(
        git("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=dest)
    ).exists()
    assert missing(dest, "HEAD") == before and len(before) == 2  # no blob came with it
    pin = json.loads((dest / ".claude" / "settings.local.json").read_text())
    assert pin == {"remote": {"defaultEnvironmentId": "env_1"}}
    assert (dest / "tmp" / "loop").is_dir()
    assert not real_trust.exists()  # no trust entry written
    assert "NOT trusted" in capsys.readouterr().out  # the checkout is not trusted here


def test_the_worktree_is_trusted_when_its_checkout_is_and_no_entry_is_written(
    tmp_path: Path, bare: Path, real_trust: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = checkout(bare, tmp_path / "main")
    entry = {"projects": {str(main.resolve()): {"hasTrustDialogAccepted": True}}}
    real_trust.write_text(json.dumps(entry))
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "main", "env_1", dest, here=main)
    assert json.loads(real_trust.read_text()) == entry
    assert omnigent_agent.folder_trusted(dest)
    assert ", trusted" in capsys.readouterr().out
    # the checkout's own branch is untouched by the worktree
    assert git("symbolic-ref", "--short", "HEAD", cwd=main) == "main"


def test_a_checkout_of_another_repository_gets_a_clone(
    tmp_path: Path, bare: Path, real_trust: Path
) -> None:
    other = tmp_path / "other"
    git("init", "-q", str(other), cwd=tmp_path)
    git("remote", "add", "origin", "https://example.com/else/where.git", cwd=other)
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "main", "env_1", dest, here=other)
    assert git("rev-parse", "--git-common-dir", cwd=dest) == ".git"  # its own repository


def test_trust_is_by_path_so_a_clone_inside_a_trusted_folder_is_untrusted(
    tmp_path: Path, bare: Path, real_trust: Path
) -> None:
    real_trust.write_text(
        json.dumps({"projects": {str(tmp_path.resolve()): {"hasTrustDialogAccepted": True}}})
    )
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "main", "env_1", dest, here=tmp_path)
    assert not omnigent_agent.folder_trusted(dest)


def test_trust_flag_writes_the_entry_as_before(
    tmp_path: Path, bare: Path, real_trust: Path
) -> None:
    main = checkout(bare, tmp_path / "main")
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "main", "env_1", dest, trust=True, here=main)
    assert json.loads(real_trust.read_text())["projects"][str(dest.resolve())] == {
        "hasTrustDialogAccepted": True
    }


def start_argv(tree: Path) -> list[str]:
    (tree / "tmp" / "loop").mkdir(parents=True, exist_ok=True)
    return [
        "start",
        "claude-cloud",
        "t-launch",
        "do X",
        str(tree / "tmp" / "loop" / "r.md"),
        "--confirm-seconds",
        "0",
        "--workspace",
        str(tree),
    ]


def test_start_from_an_untrusted_launch_dir_refuses_before_a_session_exists(
    tmp_path: Path,
    bare: Path,
    real_trust: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    og = FakeOmnigent()
    og.harnesses = {"claude-cloud": "acp:claude-cloud"}
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "main", "env_1", dest, here=tmp_path)
    assert omnigent_agent.main(start_argv(dest)) != 0
    err = capsys.readouterr().err
    assert str(dest) in err and "launch-dir --trust" in err and "trusted checkout" in err
    assert not og.sessions  # nothing was created


def test_start_from_a_worktree_of_a_trusted_checkout_creates_the_session_and_writes_no_trust(
    tmp_path: Path, bare: Path, real_trust: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.harnesses = {"claude-cloud": "acp:claude-cloud"}
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    main = checkout(bare, tmp_path / "main")
    entry = json.dumps({"projects": {str(main.resolve()): {"hasTrustDialogAccepted": True}}})
    real_trust.write_text(entry)
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "main", "env_1", dest, here=main)
    assert omnigent_agent.main(start_argv(dest)) == 0
    assert len(og.sessions) == 1
    assert real_trust.read_text() == entry


def test_start_pr_moves_a_worktree_launch_dirs_own_branch_not_the_checkouts(
    tmp_path: Path, bare: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "pr_branch", lambda pr, workspace: "pr-branch")
    git("update-ref", "refs/pull/7/head", "pr-branch", cwd=bare)
    main = checkout(bare, tmp_path / "main")
    dest = tmp_path / "launch"
    omnigent_agent.launch_dir(f"file://{bare}", "main", "env_1", dest, here=main)
    omnigent_agent.move_head(dest, 7)
    assert git("rev-parse", "HEAD", cwd=dest) == git("rev-parse", "origin/pr/7", cwd=dest)
    assert git("rev-parse", "main", cwd=main) == git("rev-parse", "origin/main", cwd=main)
    assert git("symbolic-ref", "--short", "HEAD", cwd=main) == "main"
