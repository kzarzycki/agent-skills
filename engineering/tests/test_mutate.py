"""scripts/mutate.py: each patch alone against the tests, a log stamped with the head, and the tree as it started
after every run, a killed one included."""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

MUTATE = (
    Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts" / "mutate.py"
)
MODULE = "def add(a, b):\n    return a + b\n\n\ndef double(x):\n    return x * 2\n"
TEST = "from calc import add\n\nassert add(2, 3) == 5\n"
TESTS = f"{sys.executable} test_calc.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with one module and its test, which covers add() but not double()."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text(MODULE)
    (repo / "test_calc.py").write_text(TEST)
    (repo / ".gitignore").write_text("tmp/\n__pycache__/\n")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "calc")
    (repo / "tmp" / "loop").mkdir(parents=True)
    return repo


def patch(repo: Path, name: str, old: str, new: str) -> Path:
    """A patch that changes `old` to `new` in calc.py, saved in the ignored tmp/loop/."""
    (repo / "calc.py").write_text(MODULE.replace(old, new))
    path = repo / "tmp" / "loop" / name
    path.write_text(git(repo, "diff", "--", "calc.py"))
    git(repo, "checkout", "--", "calc.py")
    return path


def mutate(repo: Path, *patches: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MUTATE),
            "--test",
            TESTS,
            "--log",
            "tmp/loop/m.log",
            *map(str, patches),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def log(repo: Path) -> list[str]:
    return (repo / "tmp" / "loop" / "m.log").read_text().splitlines()


def clean(repo: Path) -> bool:
    return git(repo, "status", "--porcelain", "--untracked-files=all") == ""


def test_a_patch_the_tests_catch_is_killed_and_the_run_exits_0(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, killed)
    assert result.returncode == 0, result.stderr
    lines = log(repo)
    assert lines[0] == git(repo, "rev-parse", "HEAD").strip()
    assert "mutate.py --test" in lines[1]
    assert lines[2] == f"{killed}: exit 1 killed"
    assert f"== {killed} ==" in lines and "AssertionError" in "\n".join(lines)
    assert clean(repo) and (repo / "calc.py").read_text() == MODULE


def test_a_patch_no_test_catches_survives_and_the_log_names_it(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    survivor = patch(repo, "double.patch", "x * 2", "x * 3")
    result = mutate(repo, killed, survivor)
    assert result.returncode == 1, result.stderr
    assert log(repo)[2:4] == [f"{killed}: exit 1 killed", f"{survivor}: exit 0 survived"]
    assert clean(repo)


def test_a_tree_with_a_change_is_refused_before_any_test_runs(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    (repo / "notes.txt").write_text("not ignored\n")
    result = mutate(repo, killed)
    assert result.returncode == 2
    assert "notes.txt" in result.stderr
    assert not any(line.startswith(str(killed)) for line in log(repo))
    (repo / "notes.txt").unlink()
    assert clean(repo)


def test_a_patch_that_does_not_apply_is_refused_before_any_test_runs(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    stale = repo / "tmp" / "loop" / "stale.patch"
    stale.write_text(killed.read_text().replace("a + b", "a * b"))
    result = mutate(repo, killed, stale)
    assert result.returncode == 2
    assert f"{stale} does not apply" in result.stderr
    assert not any(line.startswith(str(killed)) for line in log(repo))
    assert clean(repo)


def test_sigterm_while_a_patch_is_applied_leaves_the_tree_as_it_started(
    repo: Path, tmp_path: Path
) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    started = tmp_path / "started"
    before = (git(repo, "status", "--porcelain"), git(repo, "diff"))
    run = subprocess.Popen(
        [
            sys.executable,
            str(MUTATE),
            "--test",
            f"touch {started} && sleep 60",
            "--log",
            "tmp/loop/m.log",
            str(killed),
        ],
        cwd=repo,
    )
    deadline = time.monotonic() + 30
    while not started.exists():
        assert time.monotonic() < deadline and run.poll() is None
        time.sleep(0.05)
    assert "a - b" in (repo / "calc.py").read_text()
    run.send_signal(signal.SIGTERM)
    assert run.wait(timeout=30) == -signal.SIGTERM
    assert (git(repo, "status", "--porcelain"), git(repo, "diff")) == before
    assert clean(repo) and log(repo)[-1] == "stopped by SIGTERM"
