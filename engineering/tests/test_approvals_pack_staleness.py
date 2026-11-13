"""approvals.py: a start-up line when the script's checkout is behind its upstream and the script changed there, and
`pack_staleness: refuse` making it a refusal (#942)."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    git_in,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    loop_md,
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

SCRIPT = "scripts/tool.py"


def commit(where: Path, name: str, text: str) -> None:
    (where / name).parent.mkdir(parents=True, exist_ok=True)
    (where / name).write_text(text)
    git_in(where, "add", "-A")
    git_in(where, "-c", "user.email=a@example.com", "-c", "user.name=a", "commit", "-q", "-m", name)


@pytest.fixture
def clone(tmp_path: Path) -> tuple[Path, Path]:
    """(origin, work): work is a clone of origin holding SCRIPT, with its upstream not yet advanced."""
    origin, work = tmp_path / "origin", tmp_path / "work"
    git_in(tmp_path, "init", "-q", "-b", "main", str(origin))
    commit(origin, SCRIPT, "v1\n")
    git_in(tmp_path, "clone", "-q", str(origin), str(work))
    return origin, work


def fetched(origin: Path, work: Path) -> None:
    git_in(work, "fetch", "-q")


def test_behind_with_the_script_changed_warns(clone: tuple[Path, Path]) -> None:
    origin, work = clone
    commit(origin, SCRIPT, "v2\n")
    commit(origin, "other.txt", "x\n")
    fetched(origin, work)
    line = approvals.pack_behind(work / SCRIPT)
    assert line is not None and "2 commits behind" in line and "git pull" in line


def test_behind_with_the_script_unchanged_is_silent(clone: tuple[Path, Path]) -> None:
    origin, work = clone
    commit(origin, "other.txt", "x\n")
    fetched(origin, work)
    assert approvals.pack_behind(work / SCRIPT) is None


def test_not_behind_is_silent(clone: tuple[Path, Path]) -> None:
    _, work = clone
    assert approvals.pack_behind(work / SCRIPT) is None


def test_no_upstream_is_silent(tmp_path: Path) -> None:
    alone = tmp_path / "alone"
    git_in(tmp_path, "init", "-q", "-b", "main", str(alone))
    commit(alone, SCRIPT, "v1\n")
    assert approvals.pack_behind(alone / SCRIPT) is None


def test_it_never_fetches(clone: tuple[Path, Path]) -> None:
    origin, work = clone
    commit(origin, SCRIPT, "v2\n")  # origin moved, but work has not fetched
    assert approvals.pack_behind(work / SCRIPT) is None


def test_refuse_setting_is_read_from_the_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    text = loop_md("loop:\n  pack_staleness: refuse\n")
    monkeypatch.setattr(approvals, "project", lambda: (None, text))
    assert approvals.refuses_stale() is True
    monkeypatch.setattr(approvals, "project", lambda: (None, loop_md("loop:\n  cap: 3\n")))
    assert approvals.refuses_stale() is False


def test_main_warns_then_refuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        approvals, "pack_behind", lambda _: "tool.py: 3 commits behind: run `git pull`"
    )
    monkeypatch.setattr(approvals, "refuses_stale", lambda: True)
    assert approvals.main(["report", "nonexistent.md"]) == 1
    assert "git pull" in capsys.readouterr().err
