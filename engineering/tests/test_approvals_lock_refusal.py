"""approvals.py: a land whose heartbeat finds the lock taken mid-gate refuses before any merge (#1498)."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import approvals

PULL = {"number": 7, "headRefOid": "a" * 40}


@pytest.mark.parametrize("working_tree", [True, False])
def test_a_lock_the_heartbeat_lost_mid_gate_refuses_with_no_merge(
    working_tree: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = ["ours"]

    def gate(*_a: Any) -> list[tuple[dict[str, Any], str, str, str]]:
        held.clear()  # what heartbeat() does when another land's tip holds the lock
        return [(PULL, "t" * 40, "t" * 40, "run")]

    merged: list[Any] = []
    monkeypatch.setattr(approvals, "candidates_of", lambda named, *_a: (named, {}, {}))
    monkeypatch.setattr(approvals, "settings", lambda loop: {})
    monkeypatch.setattr(
        approvals, "policy_ref", lambda root: None if working_tree else "origin/main"
    )
    monkeypatch.setattr(approvals, "git", lambda *_a: "b" * 40)
    monkeypatch.setattr(approvals, "batch_tree", lambda base: contextlib.nullcontext(Path(".")))
    monkeypatch.setattr(approvals, "run_in", lambda *_a: "b" * 40)
    monkeypatch.setattr(approvals, "pre_landed", lambda *_a: True)
    monkeypatch.setattr(approvals, "merge_batch", gate)
    monkeypatch.setattr(approvals, "merged_trees", gate)
    monkeypatch.setattr(approvals, "merges", lambda *a: merged.append(a))
    with pytest.raises(approvals.Refused, match="took the landing lock"):
        approvals.local_queue([PULL], "main", None, None, set(), held=held)
    assert merged == []
