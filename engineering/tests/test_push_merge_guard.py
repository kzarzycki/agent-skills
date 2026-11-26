"""The engineering pack's PreToolUse hook refuses a push of a merge of the base into a PR branch that
merges cleanly, and allows one that resolved a conflict or carries the bypass (#2602)."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "hooks" / "push_merge_guard.py"
spec = importlib.util.spec_from_file_location("push_merge_guard", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def commit(repo, name, text):
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-m", f"{name} {text}")


def repo_with_base_merge(tmp_path, conflict):
    """A loop repo whose branch has merged main; the merge is clean unless ``conflict``."""
    repo = tmp_path / ("conflict" if conflict else "clean")
    (repo / "docs" / "agents").mkdir(parents=True)
    (repo / "docs" / "agents" / "loop.md").write_text("Cloud worker: claude\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    commit(repo, "shared.txt", "base\n")
    git(repo, "add", "docs")
    git(repo, "commit", "-m", "loop")
    git(repo, "checkout", "-q", "-b", "pr")
    commit(repo, "shared.txt" if conflict else "mine.txt", "pr\n")
    git(repo, "checkout", "-q", "main")
    commit(repo, "shared.txt" if conflict else "theirs.txt", "main\n")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "pr")
    if conflict:
        subprocess.run(
            ["git", "-C", str(repo), "merge", "-q", "main"], capture_output=True, check=False
        )
        (repo / "shared.txt").write_text("resolved\n")
        git(repo, "add", "shared.txt")
        git(repo, "commit", "-m", "merge main")
    else:
        git(repo, "merge", "-q", "--no-edit", "main")
    return repo


@pytest.mark.parametrize(
    "conflict, command, refused",
    [
        (False, "git push origin pr", True),
        (False, "git -C {repo} push", True),
        (False, "LOOP_MERGE_MAIN=land-reported-conflict git push origin pr", False),
        (False, "git status", False),
        (False, "git push --delete origin pr", False),
        (True, "git push origin pr", False),
    ],
)
def test_push_of_a_base_merge(tmp_path, conflict, command, refused):
    repo = repo_with_base_merge(tmp_path, conflict)
    got = guard.verdict(
        {
            "tool_name": "Bash",
            "cwd": str(repo),
            "tool_input": {"command": command.format(repo=repo)},
        }
    )
    assert (got[0] == 2) is refused
    if refused:
        assert "land" in got[1] and "LOOP_MERGE_MAIN" in got[1]


def test_a_push_that_is_no_merge_passes(tmp_path):
    repo = repo_with_base_merge(tmp_path, False)
    git(repo, "reset", "-q", "--hard", "HEAD^1")
    assert (
        guard.verdict({"cwd": str(repo), "tool_input": {"command": "git push origin pr"}})[0] == 0
    )
