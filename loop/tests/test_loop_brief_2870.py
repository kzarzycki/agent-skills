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
    done = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True, check=True)
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


def stand_in(monkeypatch: pytest.MonkeyPatch, base: str, head: str, body: str) -> None:
    pull = {
        "baseRefName": "main",
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
        merge_base=lambda ref, sha: base,
        named=lambda text: [],
        section=lambda text, name: "",
        levels=lambda policy: {},
        no_ci=lambda policy: False,
        unforced=lambda found: None,
        overlaps=lambda number: [],
    )
    monkeypatch.setattr(loop, "gatekeeper", fake)


def test_the_brief_lists_the_changed_files_and_the_diff_stat(
    clone: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Closes #2870\n")
    assert loop.brief(7, None, []) == 0
    out = capsys.readouterr().out
    assert "- Changed files (3, status then path):" in out
    assert "  M\tedit.py" in out and "  A\tnew.py" in out and "  D\tgone.md" in out
    assert "keep.txt" not in out  # a file the PR leaves alone is no part of its diff
    assert "- Diff stat (base to head):" in out and "3 files changed" in out


def test_the_brief_carries_a_tool_call_budget_and_drops_the_pr_bodys_spend_lines(
    clone: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, base, head = clone
    body = "Closes #2870\nToken estimate: ~2M (two passes)\nTokens spent: 1.9M\n## Evidence\nran it\n"
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
