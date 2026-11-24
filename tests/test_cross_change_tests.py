"""tools/cross_change_tests.py: what a Mergify batch runs (R6): the unkeyed checks, the tests a PR's diff and the rest
of the merge both reach, the own tests of a PR with no record (the floor), and a refusal when that is nothing on a
merge a PR of which has no record."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import affected_tests as a
from tools import cross_change_tests as c

# the tests each file reaches: only `x2.py` and `y2.py` reach one test both
REACH = {"x.py": {"t_x"}, "y.py": {"t_y"}, "x2.py": {"t_x", "t_both"}, "y2.py": {"t_y", "t_both"}}


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def commit(name: str) -> None:
    Path(name).write_text("1\n")
    git("add", ".")
    git("commit", "-qm", name)


def draft(*prs: tuple[int, str]) -> tuple[str, dict[int, str]]:
    """main with one file, then Mergify's draft on it: one `Merge of PR <n>` commit per PR (its file), as the batch
    drafts of this repo are built. Returns the base tip and each PR's head."""
    git("init", "-q", "-b", "main")
    commit("seed.py")
    tip = git("rev-parse", "HEAD")
    heads = {}
    for number, name in prs:
        git("checkout", "-q", "-b", f"pr-{number}", tip)
        commit(name)
        heads[number] = git("rev-parse", "HEAD")
        git("checkout", "-q", "main")
        git("merge", "-q", "--no-ff", "-m", f"Merge of PR {number}", f"pr-{number}")
    return tip, heads


def fake_targets(files, base=None):
    return sorted(set().union(*(REACH.get(f, set()) for f in files or ())))


@pytest.fixture
def mapped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "load_map", lambda: ("a" * 40, object()))
    monkeypatch.setattr(a, "targets", fake_targets)


def records(*held: str):
    return lambda head: (head in held, "recorded: …" if head in held else "no record of the gate")


def test_every_pr_recorded_and_no_test_reached_twice_selects_only_the_unkeyed_checks(
    mapped, capsys
) -> None:
    tip, heads = draft((1, "x.py"), (2, "y.py"))
    assert c.select(tip, records(*heads.values()), lambda: ["sh live.sh"]) == (["sh live.sh"], [])
    err = capsys.readouterr().err
    assert "cross-change: PR #1 (head " in err and "record found" in err
    assert "cross-change: map of aaaaaaaaaaaa: 0 tests" in err


def test_a_pr_with_no_record_adds_its_own_affected_tests(mapped, capsys) -> None:
    tip, heads = draft((1, "x.py"), (2, "y.py"))
    assert c.select(tip, records(heads[1]), list) == ([], ["t_y"])
    assert (
        "PR #2: no record, so its own 1 affected tests run too (the floor)"
        in capsys.readouterr().err
    )


def test_a_queue_run_that_runs_nothing_on_a_tree_with_no_records_is_refused_with_its_reason(
    mapped,
) -> None:
    """Neither PR has a record, and no test reaches their files (`a.txt`, `b.txt`), so the floor adds nothing."""
    tip, _ = draft((1, "a.txt"), (2, "b.txt"))
    with pytest.raises(
        c.Refused, match=r"nothing to run, and #1, #2 has no record for its head's tree"
    ):
        c.select(tip, records(), list)


def test_the_refusal_fails_the_command_and_says_why(mapped, monkeypatch, capsys) -> None:
    tip, _ = draft((1, "a.txt"))
    monkeypatch.setattr(c.select, "__defaults__", (records(), list))
    assert c.main([tip]) == 1
    assert "cross-change: refused: nothing to run, and #1 has no record" in capsys.readouterr().err


def test_an_empty_set_passes_when_every_pr_has_a_record(mapped, capsys) -> None:
    tip, heads = draft((1, "x.py"))
    assert c.select(tip, records(*heads.values()), list) == ([], [])
    assert "every PR has a record" in capsys.readouterr().err


def test_a_test_both_prs_reach_runs(mapped) -> None:
    tip, heads = draft((1, "x2.py"), (2, "y2.py"))
    assert c.select(tip, records(*heads.values()), list) == ([], ["t_both"])


def test_the_bases_new_commits_count_as_the_rest(mapped) -> None:
    git("init", "-q", "-b", "main")
    commit("seed.py")
    point = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "pr", point)
    commit("x2.py")
    head = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    commit("y2.py")  # main moved since the PR's branch point
    tip = git("rev-parse", "HEAD")
    git("merge", "-q", "--no-ff", "-m", "Merge of PR 7", "pr")
    assert c.select(tip, records(head), list) == ([], ["t_both"])


def test_without_a_map_it_falls_back_to_the_batchs_affected_tests_and_says_why(
    mapped, monkeypatch, capsys
) -> None:
    tip, heads = draft((1, "x.py"), (2, "y.py"))
    monkeypatch.setattr(a, "load_map", lambda: None)
    assert c.select(tip, records(*heads.values()), list) == ([], ["t_x", "t_y"])
    assert (
        "cross-change: fallback to the batch's affected tests: no per-test map at"
        in capsys.readouterr().err
    )


def test_commits_that_are_not_merges_fall_back_too(mapped, capsys) -> None:
    git("init", "-q", "-b", "main")
    commit("seed.py")
    tip = git("rev-parse", "HEAD")
    commit("x.py")
    assert c.select(tip, records(), list) == ([], ["t_x"])
    assert "the commits don't split into PRs (" in capsys.readouterr().err


def test_a_fallback_that_selects_nothing_is_refused_too(mapped) -> None:
    git("init", "-q", "-b", "main")
    commit("seed.py")
    tip = git("rev-parse", "HEAD")
    commit("other.py")
    with pytest.raises(c.Refused, match="no PR's record can be read"):
        c.select(tip, records(), list)


def test_the_command_writes_the_unkeyed_checks_and_prints_the_targets(
    mapped, monkeypatch, capsys
) -> None:
    tip, heads = draft((1, "x.py"), (2, "y.py"))
    monkeypatch.setattr(c.select, "__defaults__", (records(heads[1]), lambda: ["sh live.sh"]))
    out = Path("unkeyed")
    assert c.main(["--unkeyed-out", str(out), tip]) == 0
    assert out.read_text() == "sh live.sh\n"
    assert capsys.readouterr().out == "t_y\n"
