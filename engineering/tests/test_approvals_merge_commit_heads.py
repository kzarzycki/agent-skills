"""approvals.py: `land.merge_commit_heads` lands a matching head with a merge commit, the rest squashed (#1029)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    HEAD,
    TREE,
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    loop_md,
    others_open,  # noqa: F401
    pull,
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

SYNC = loop_md("land:\n  merge_commit_heads:\n    - sync/*\n")
BOTH = loop_md(
    "land:\n  signed_squash_to: main\n  allowed_signers: /dev/null\n  merge_commit_heads:\n    - sync/*\n"
)
UNSET = loop_md("land:\n  where: both\n")


def land(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, loop: str, branch: str
) -> tuple[list[tuple[str, ...]], str]:
    """merges() of one PR on `branch`: the `gh pr merge` calls it makes, and what it printed."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(approvals, "gh", lambda *args, **_k: calls.append(args) or "")
    monkeypatch.setattr(approvals, "land_body", lambda _pull: None)
    monkeypatch.setattr(approvals, "pull_request", lambda _n: {"state": "MERGED"})
    monkeypatch.setattr(approvals, "git", lambda *args: TREE if args[0] == "rev-parse" else "")
    monkeypatch.setattr(approvals, "publish", lambda *_a, **_k: None)
    monkeypatch.setattr(approvals, "drop_records", lambda _heads: None)
    monkeypatch.setattr(approvals, "comment", lambda *_a: None)
    monkeypatch.setattr(approvals, "project", lambda: (None, loop))
    monkeypatch.setattr(approvals, "landed_pass", lambda *_a: None)
    landed: list[Any] = [({**pull(), "headRefName": branch}, TREE, TREE, "run")]
    approvals.merges(landed, "main", HEAD, tmp_path, loop, set())
    return [call for call in calls if call[:2] == ("pr", "merge")], ""


def test_a_matching_head_lands_with_a_merge_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (call,), _ = land(monkeypatch, tmp_path, SYNC, "sync/upstream")
    assert "--merge" in call and "--squash" not in call
    assert call[-2:] == ("--match-head-commit", pull()["headRefOid"])
    assert "lands as a merge" in capsys.readouterr().out


def test_a_head_that_does_not_match_lands_with_a_squash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (call,), _ = land(monkeypatch, tmp_path, SYNC, "feature/x")
    assert "--squash" in call and "--merge" not in call
    assert "lands as a squash" in capsys.readouterr().out


@pytest.mark.parametrize("loop", [UNSET, loop_md()])
def test_with_the_key_unset_the_command_is_unchanged(
    loop: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (call,), _ = land(monkeypatch, tmp_path, loop, "sync/upstream")
    assert call == ("pr", "merge", "7", "--squash", "--match-head-commit", pull()["headRefOid"])


def test_with_both_keys_set_a_matching_pr_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls, _ = land(monkeypatch, tmp_path, BOTH, "sync/upstream")
    assert calls == []
    out = capsys.readouterr().out
    assert "land.merge_commit_heads" in out and "land.signed_squash_to" in out
    assert "was refused" in out


def test_the_merge_gate_holds_a_matching_pr_under_both_keys() -> None:
    held = approvals.merge_method
    with pytest.raises(approvals.Refused, match="merge_commit_heads.*signed_squash_to"):
        held({**pull(), "headRefName": "sync/a"}, BOTH)
    assert held({**pull(), "headRefName": "other"}, BOTH) == "squash"


def test_the_key_alone_signs_nothing_and_one_signing_key_alone_is_refused() -> None:
    assert approvals.signed(SYNC) is None
    with pytest.raises(approvals.Refused, match="lacks `allowed_signers`"):
        approvals.settings(loop_md("land:\n  signed_squash_to: main\n"))
