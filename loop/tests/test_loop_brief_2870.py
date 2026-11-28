"""scripts/loop.py brief: the verifier's first prompt carries the diff stat, the changed files and a tool-call budget, and
drops the PR body's spend lines (#2870). The gatekeeper's ports are a stand-in; the diff is a real one in a real clone."""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_loop import loop


def git(where: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(where), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str]:
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
        git(work, "config", key, value)
    (work / "keep.txt").write_text("same\n")
    (work / "edit.py").write_text("a = 1\n")
    (work / "gone.md").write_text("bye\n")
    git(work, "add", "."), git(work, "commit", "-qm", "base")
    base = git(work, "rev-parse", "HEAD")
    (work / "edit.py").write_text("a = 2\nb = 3\n")
    (work / "new.py").write_text("c = 4\n")
    git(work, "rm", "-q", "gone.md"), git(work, "add", "."), git(work, "commit", "-qm", "change")
    monkeypatch.chdir(work)
    return work, base, git(work, "rev-parse", "HEAD")


def stand_in(
    monkeypatch: pytest.MonkeyPatch,
    base: str,
    head: str,
    body: str,
    base_ref: str = "main",
    reusable: object = lambda head: None,
) -> None:
    pull = {
        "baseRefName": base_ref,
        "headRefOid": head,
        "title": "Change it",
        "body": body,
        "baseRepository": {"defaultBranchRef": {"name": "main"}},
        "closingIssuesReferences": {"nodes": [{"number": 2870}]},
        "labels": {"nodes": []},
    }
    fake = SimpleNamespace(
        __file__=str(Path(loop.gatekeeper.__file__)),
        Refused=loop.gatekeeper.Refused,
        Policy=loop.gatekeeper.Policy,
        LOOP="loop.md",
        pull_request=lambda number: pull,
        policy_from=lambda ref: contextlib.nullcontext(),
        project=lambda: (None, ""),
        toplevel=Path.cwd,
        conflicted=lambda number, ref, sha: [],
        passes=lambda found: [],
        merge_base=lambda ref, sha: base if ref == pull["baseRefName"] else "wrong-base",
        named=lambda text: [],
        section=lambda text, name: "",
        levels=lambda policy: {},
        no_ci=lambda policy: False,
        unforced=lambda found: None,
        overlaps=lambda number: [],
        reusable=reusable,
    )
    monkeypatch.setattr(loop, "gatekeeper", fake)


def test_the_brief_lists_the_changed_files_and_the_diff_stat(
    clone: tuple[Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Closes #2870\nSpec deviations: none\n")
    assert loop.brief(7, None, []) == 0
    out = capsys.readouterr().out
    assert "- Changed files (3, status then path):" in out
    assert "  M\tedit.py" in out and "  A\tnew.py" in out and "  D\tgone.md" in out
    assert "keep.txt" not in out  # a file the PR leaves alone is no part of its diff
    assert "- Diff stat (base to head):" in out and "3 files changed" in out


def test_the_brief_carries_a_tool_call_budget_and_drops_the_pr_bodys_spend_lines(
    clone: tuple[Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, base, head = clone
    body = "Closes #2870\nSpec deviations: none\nToken estimate: ~2M (two passes)\nTokens spent: 1.9M\n## Evidence\nran it\n"
    stand_in(monkeypatch, base, head, body)
    assert loop.brief(7, None, []) == 0
    out = capsys.readouterr().out
    assert f"- Budget: {loop.TOOL_CALL_BUDGET} tool calls" in out
    assert "Token estimate" not in out and "Tokens spent" not in out
    assert "Closes #2870" in out and "## Evidence" in out  # what a criterion can be about stays


def test_a_head_this_clone_lacks_is_fetched_and_a_failure_is_said_not_hidden(
    clone: tuple[Path, str, str],
) -> None:
    assert loop.diff_summary(clone[1], "0" * 40)[0].startswith("- Diff: not available here")


def test_the_brief_refuses_while_the_body_has_no_spec_deviations_line(
    clone: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Closes #629\n")
    with pytest.raises(loop.gatekeeper.Refused, match="Spec deviations:"):
        loop.brief(7, None, [])


def test_a_deviation_without_a_link_is_refused_and_one_with_a_link_or_none_passes(
    clone: tuple[Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Spec deviations:\n- drops the tracker's children\n")
    with pytest.raises(loop.gatekeeper.Refused, match="no link"):
        loop.brief(7, None, [])
    for body in (
        "Spec deviations:\n- drops the children, owner agreed in #630\n",
        "Spec deviations: none\n",
    ):
        stand_in(monkeypatch, base, head, body)
        assert loop.brief(7, None, []) == 0
    capsys.readouterr()


def test_a_stacked_pr_brief_names_the_merge_base_with_its_own_base_branch(
    clone: tuple[Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Spec deviations: none\n", base_ref="stack-base")
    assert loop.brief(7, None, []) == 0
    assert f"- Base: {base}" in capsys.readouterr().out


def test_the_brief_says_whether_the_head_has_a_recorded_gate_pass(
    clone: tuple[Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Spec deviations: none\n")
    loop.brief(7, None, [])
    assert "- Gates: no recorded pass on the head" in capsys.readouterr().out
    stand_in(monkeypatch, base, head, "Spec deviations: none\n", reusable=lambda h: {"time": "T1"})
    loop.brief(7, None, [])
    assert (
        "- Gates: passed on the head's tree at T1, recorded: don't rerun" in capsys.readouterr().out
    )
