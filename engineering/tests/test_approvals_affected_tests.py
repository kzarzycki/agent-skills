"""approvals.py push-gate: the worker's gate runs loop.md's `Affected tests: <command> <base>` line, else
`mise run check` (#1174)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    git_in,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

# A synthetic selector: the tests of each changed `.py` file since the base it is given, none for any other file, so a
# docs-only change selects nothing and it exits 0. It logs each test it "runs" and the variable SELECTOR_TIER it sees.
SELECTOR = """\
import os, subprocess, sys
changed = subprocess.run(
    ["git", "diff", "--name-only", sys.argv[1] + "...HEAD"], capture_output=True, text=True, check=True
).stdout.split()
picked = [name for name in changed if name.endswith(".py")]
with open(os.environ["RUNS_LOG"], "a") as log:
    log.write("".join(f"test {name} tier={os.environ.get('SELECTOR_TIER', '-')}\\n" for name in picked))
print(f"{len(picked)} tests selected")
"""
# the full check, standing in for `mise run check`: it logs `full` and exits FULL_EXIT
FULL = """\
import os, sys
open(os.environ["RUNS_LOG"], "a").write("full\\n")
sys.exit(int(os.environ.get("FULL_EXIT", "0")))
"""


def commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git_in(repo, "add", "-A")
    git_in(repo, "commit", "-qm", message)


def new_repo(path: Path) -> Path:
    path.mkdir()
    git_in(path, "init", "-q", "-b", "main")
    git_in(path, "config", "user.email", "loop@example.com")
    git_in(path, "config", "user.name", "loop")
    return path


@pytest.fixture
def gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A checkout on a branch off `main`, whose `origin/main` (and origin/HEAD) is that base; `base(line)` commits the
    base with loop.md holding that line (none for None), `change(files)` commits files on the branch, `runs()` reads
    what ran. The full check is a script that logs `full`."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "select.py").write_text(SELECTOR)
    (scripts / "full.py").write_text(FULL)
    runs = tmp_path / "runs.log"
    monkeypatch.setenv("RUNS_LOG", str(runs))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))  # no host heavy wrapper
    monkeypatch.setattr(approvals, "PUSH_CHECK", [sys.executable, str(scripts / "full.py")])
    repo = new_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    selector = f"{sys.executable} {scripts / 'select.py'}"

    def base(line: str | None) -> None:
        text = "# Loop facts\n\nOwner: someone\n" + (f"Affected tests: {line}\n" if line else "")
        commit(repo, {"app.py": "value = 1\n", "docs/agents/loop.md": text}, "base")
        git_in(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git_in(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        git_in(repo, "checkout", "-qb", "feature")

    return {
        "repo": repo,
        "selector": selector,
        "base": base,
        "change": lambda files: commit(repo, files, "change"),
        "runs": lambda: runs.read_text().splitlines() if runs.exists() else [],
    }


def test_a_docs_only_head_runs_no_tests_under_a_selector_that_returns_none(
    gate: dict[str, Any], capfd: pytest.CaptureFixture[str]
) -> None:
    gate["base"](f"{gate['selector']} origin/main")
    gate["change"]({"README.md": "# Docs\n"})
    assert approvals.main(["push-gate"]) == 0
    assert gate["runs"]() == []  # neither a selected test nor the full check
    captured = capfd.readouterr()
    assert "0 tests selected" in captured.out
    assert f"push-gate: {gate['selector']} origin/main" in captured.err


def test_a_code_change_runs_the_tests_its_selector_picks_against_the_base(
    gate: dict[str, Any],
) -> None:
    gate["base"](f"SELECTOR_TIER=fast {gate['selector']} origin/main")
    gate["change"]({"app.py": "value = 2\n", "README.md": "# Docs\n"})
    assert approvals.main(["push-gate"]) == 0
    assert gate["runs"]() == ["test app.py tier=fast"]


def test_without_the_line_the_push_runs_the_full_check_and_takes_its_exit(
    gate: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate["base"](None)
    gate["change"]({"README.md": "# Docs\n"})
    monkeypatch.setenv("FULL_EXIT", "3")
    assert approvals.main(["push-gate"]) == 3
    assert gate["runs"]() == ["full"]
    assert "loop.md has no `Affected tests:` line" in capsys.readouterr().err


def test_the_line_is_read_from_the_base_so_a_branch_cant_pick_its_own_gate(
    gate: dict[str, Any],
) -> None:
    gate["base"](None)
    gate["change"](
        {"docs/agents/loop.md": f"# Loop facts\n\nAffected tests: {gate['selector']} origin/main\n"}
    )
    assert approvals.main(["push-gate"]) == 0
    assert gate["runs"]() == ["full"]


def test_a_base_naming_no_commit_is_refused_and_runs_nothing(
    gate: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    gate["base"](f"{gate['selector']} origin/nowhere")
    gate["change"]({"app.py": "value = 2\n"})
    assert approvals.main(["push-gate"]) == 1
    assert "selects against origin/nowhere, which names no commit here" in capsys.readouterr().out
    assert gate["runs"]() == []


def test_a_line_with_no_base_is_refused(
    gate: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    gate["base"]("run-affected")
    assert approvals.main(["push-gate"]) == 1
    assert "a command and the base it selects against" in capsys.readouterr().out
    assert gate["runs"]() == []


def test_a_shallow_clone_fetches_its_base_before_the_selector_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cloud session's clone holds the PR branch alone, one commit deep: push-gate fetches `origin/main` and deepens
    until the merge base answers, so the selector compares against the base, not a missing ref."""
    runs = tmp_path / "runs.log"
    monkeypatch.setenv("RUNS_LOG", str(runs))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "select.py").write_text(SELECTOR)
    origin = new_repo(tmp_path / "origin")
    loop = (
        f"# Loop facts\n\nAffected tests: {sys.executable} {tmp_path / 'select.py'} origin/main\n"
    )
    commit(origin, {"app.py": "value = 1\n", "docs/agents/loop.md": loop}, "base")
    git_in(origin, "checkout", "-qb", "feature")
    commit(origin, {"README.md": "# Docs\n"}, "docs")
    commit(origin, {"app.py": "value = 2\n"}, "code")
    clone = tmp_path / "clone"
    git_in(
        tmp_path,
        "clone",
        "-q",
        "--depth",
        "1",
        "--single-branch",
        "--branch",
        "feature",
        f"file://{origin}",
        str(clone),
    )
    monkeypatch.chdir(clone)
    assert approvals.main(["push-gate"]) == 0
    assert runs.read_text().splitlines() == ["test app.py tier=-"]
