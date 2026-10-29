"""scripts/mutate.py: each patch alone against the tests, a log stamped with the head, and the tree as it started
after every run, a killed one included."""

from __future__ import annotations

import os
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
    """A repo with one module, its test, which covers add() but not double(), and a docs/ folder."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text(MODULE)
    (repo / "test_calc.py").write_text(TEST)
    (repo / ".gitignore").write_text("tmp/\n__pycache__/\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "README.md").write_text("calc\n")
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


def mutate(
    repo: Path, *patches: Path, test: str = TESTS, cwd: Path | None = None, to: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MUTATE),
            "--test",
            test,
            "--log",
            str(to or log_path(repo)),
            *map(str, patches),
        ],
        cwd=cwd or repo,
        # a mutate.py run over these tests passes its switch down, which would hide this one lacking it
        env={k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"},
        capture_output=True,
        text=True,
        check=False,
    )


def stopped(repo: Path, tmp_path: Path, *signals: signal.Signals, first: str = "") -> int:
    """Send `signals` to a run while its patch is applied and its test command sleeps, after running `first`; its
    exit code."""
    killed = patch(repo, "add.patch", "a + b", "a - b")
    started = tmp_path / "started"
    command = [sys.executable, str(MUTATE), "--test", f"{first}touch {started} && sleep 60"]
    run = subprocess.Popen([*command, "--log", str(log_path(repo)), str(killed)], cwd=repo)
    deadline = time.monotonic() + 30
    while not started.exists():
        assert time.monotonic() < deadline and run.poll() is None
        time.sleep(0.05)
    assert "a - b" in (repo / "calc.py").read_text()
    for sent in signals:
        run.send_signal(sent)
    return run.wait(timeout=30)


def log_path(repo: Path) -> Path:
    return repo / "tmp" / "loop" / "m.log"


def log(repo: Path) -> list[str]:
    return log_path(repo).read_text().splitlines()


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
    assert "the tree has changes" in result.stderr and "notes.txt" in result.stderr
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
    assert log(repo)[-1].startswith(f"refused: {stale} does not apply")
    assert not any(line.startswith(str(killed)) for line in log(repo))
    assert clean(repo)


def test_sigterm_while_a_patch_is_applied_leaves_the_tree_as_it_started(
    repo: Path, tmp_path: Path
) -> None:
    before = (git(repo, "status", "--porcelain"), git(repo, "diff"))
    assert stopped(repo, tmp_path, signal.SIGTERM) == -signal.SIGTERM
    assert (git(repo, "status", "--porcelain"), git(repo, "diff")) == before
    assert clean(repo) and log(repo)[-1] == "stopped by SIGTERM"


def test_a_second_signal_during_the_restore_does_not_interrupt_it(
    repo: Path, tmp_path: Path
) -> None:
    code = stopped(repo, tmp_path, signal.SIGINT, signal.SIGTERM)
    assert code in (-signal.SIGINT, -signal.SIGTERM)
    assert clean(repo) and log(repo)[-1].startswith("stopped by SIG")


def test_a_run_from_a_subdirectory_patches_files_outside_it(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    test = f"{sys.executable} {repo / 'test_calc.py'}"
    result = mutate(repo, killed, test=test, cwd=repo / "docs")
    assert result.returncode == 0, result.stderr
    assert log(repo)[2] == f"{killed}: exit 1 killed"
    assert clean(repo)


def test_the_test_command_writes_no_bytecode_that_could_hide_the_next_patch(repo: Path) -> None:
    survivor = patch(repo, "double.patch", "x * 2", "x * 3")
    assert mutate(repo, survivor).returncode == 1
    assert not (repo / "__pycache__").exists()


def test_a_test_command_that_leaves_a_file_fails_the_restore_and_names_it(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, killed, test=f"touch stray.txt; {TESTS}")
    assert result.returncode == 2
    assert "could not be restored" in result.stderr and "stray.txt" in result.stderr
    assert (repo / "calc.py").read_text() == MODULE
    # the test had finished: its result and output stay in the log beside the refusal
    lines = log(repo)
    assert lines[2:4] == [
        f"{killed}: exit 1 killed",
        f"refused: the tree could not be restored after {killed}:",
    ]
    assert f"== {killed} ==" in lines
    (repo / "stray.txt").unlink()
    assert clean(repo)


def test_a_change_an_index_flag_hides_is_refused(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    git(repo, "update-index", "--assume-unchanged", "calc.py")
    (repo / "calc.py").write_text(MODULE + "# edited\n")
    result = mutate(repo, killed)
    assert result.returncode == 2
    assert "calc.py (index flag hides its changes)" in result.stderr
    assert log(repo)[-1].startswith("refused: the tree has changes")


def test_outside_a_git_checkout_it_refuses(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "x.patch").write_text("")
    result = subprocess.run(
        [sys.executable, str(MUTATE), "--test", "true", "--log", "m.log", "x.patch"],
        cwd=plain,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "not in a git checkout" in result.stderr


def test_a_signal_whose_restore_fails_is_refused_with_exit_2(repo: Path, tmp_path: Path) -> None:
    code = stopped(repo, tmp_path, signal.SIGTERM, first="echo edited >> docs/README.md; ")
    assert code == 2
    assert (repo / "calc.py").read_text() == MODULE
    assert log(repo)[-1].startswith("refused: the tree could not be restored")


def test_test_output_that_is_not_utf8_is_logged_and_the_tree_restored(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, killed, test=f"printf '\\377'; {TESTS}")
    assert result.returncode == 0, result.stderr
    assert clean(repo) and f"{killed}: exit 1 killed" in log(repo)


@pytest.mark.parametrize("target", ["tracked", "patch"])
def test_a_log_path_that_is_tracked_or_a_patch_is_refused_and_left_as_it_was(
    repo: Path, target: str
) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    path = repo / "docs" / "README.md" if target == "tracked" else killed
    before = path.read_text()
    result = mutate(repo, killed, to=path)
    assert result.returncode == 2 and "the log" in result.stderr
    assert path.read_text() == before and clean(repo)
