"""tools/cross_change_tests.py: the Mergify batch runs only the tests that a PR's diff and the rest of the merge both reach (R6)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import affected_tests as a
from tools import cross_change_tests as c


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def commit(name: str, text: str) -> None:
    Path(name).write_text(text)
    git("add", ".")
    git("commit", "-qm", name)


@pytest.fixture
def batch(tmp_path, monkeypatch):
    """main with one file, then two PR branches (touching x.py and y.py) merged into it: returns the base tip."""
    monkeypatch.chdir(tmp_path)
    git("init", "-q", "-b", "main")
    commit("seed.py", "1\n")
    tip = git("rev-parse", "HEAD")
    for name in ("x.py", "y.py"):
        git("checkout", "-q", "-b", f"pr-{name}", tip)
        commit(name, "1\n")
        git("checkout", "-q", "main")
        git("merge", "-q", "--no-ff", "-m", f"merge {name}", f"pr-{name}")
    return tip


def fake_targets(files, base=None):
    """The tests each file reaches: x.py -> t_x and t_both, y.py -> t_y and t_both; every set holds the cheap check."""
    reach = {"x.py": {"t_x", "t_both"}, "y.py": {"t_y", "t_both"}}
    return sorted({"cheap"}.union(*(reach.get(f, set()) for f in files)))


def test_it_runs_only_the_tests_both_the_pr_and_the_rest_reach(batch, monkeypatch, capsys) -> None:
    monkeypatch.setattr(a, "load_map", lambda: ("a" * 40, object()))
    monkeypatch.setattr(a, "targets", fake_targets)
    # t_x is reached only by PR 1 and t_y only by PR 2: each passed on its own head. t_both is the cross-change test.
    assert c.select(batch) == ["cheap", "t_both"]
    err = capsys.readouterr().err
    assert "cross-change: PR 1 of 2" in err and "cross-change: map of aaaaaaaaaaaa" in err


def test_a_lone_pr_on_an_unmoved_base_has_no_cross_change_test(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    git("init", "-q", "-b", "main")
    commit("seed.py", "1\n")
    tip = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "pr", tip)
    commit("x.py", "1\n")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "-m", "merge", "pr")
    monkeypatch.setattr(a, "load_map", lambda: ("a" * 40, object()))
    monkeypatch.setattr(a, "targets", fake_targets)
    assert c.select(tip) == ["cheap"]


def test_the_bases_new_commits_count_as_the_rest(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    git("init", "-q", "-b", "main")
    commit("seed.py", "1\n")
    point = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "pr", point)
    commit("x.py", "1\n")
    git("checkout", "-q", "main")
    commit("y.py", "1\n")  # main moved since the PR's branch point
    tip = git("rev-parse", "HEAD")
    git("merge", "-q", "--no-ff", "-m", "merge", "pr")
    monkeypatch.setattr(a, "load_map", lambda: ("a" * 40, object()))
    monkeypatch.setattr(a, "targets", fake_targets)
    assert c.select(tip) == ["cheap", "t_both"]


def test_without_a_map_it_falls_back_to_the_batchs_affected_tests_and_says_why(
    batch, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(a, "load_map", lambda: None)
    monkeypatch.setattr(a, "targets", fake_targets)
    assert c.select(batch) == ["cheap", "t_both", "t_x", "t_y"]
    assert (
        "cross-change: fallback to the batch's affected tests: no map at" in capsys.readouterr().err
    )


def test_commits_that_are_not_merges_fall_back_too(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    git("init", "-q", "-b", "main")
    commit("seed.py", "1\n")
    tip = git("rev-parse", "HEAD")
    commit("x.py", "1\n")
    monkeypatch.setattr(a, "load_map", lambda: ("a" * 40, object()))
    monkeypatch.setattr(a, "targets", fake_targets)
    assert c.select(tip) == ["cheap", "t_both", "t_x"]
    assert "don't split into PRs" in capsys.readouterr().err
