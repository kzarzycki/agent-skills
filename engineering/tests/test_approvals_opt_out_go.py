"""approvals.py: under `opt_out: true`, a PR with no loop trail that carries a merge go (`Approved: merge`) is named as
missing its trail, not left to its author to merge by hand (#1648)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import approvals

# the record `approve merge --by delegate` posts, built as it builds it
GO = approvals.fold(
    approvals.VOICED[approvals.DELEGATE],
    "Go to merge aaaaaaa.",
    f"Approved: merge\nBy: {approvals.DELEGATE}\nHead: {'a' * 40}",
)


def pull(*bodies: str) -> dict[str, Any]:
    return {
        "number": 7,
        "body": "A change.",
        "comments": {"totalCount": len(bodies), "nodes": [{"body": b} for b in bodies]},
    }


@pytest.fixture
def opted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "opted_out", lambda _loop: True)
    monkeypatch.setattr(approvals, "passes", lambda _pull: [])
    monkeypatch.setattr(approvals, "exempt", lambda _pull, _loop: False)
    monkeypatch.setattr(approvals, "closing_issues", lambda _pull: [])
    monkeypatch.setattr(approvals, "source", lambda _loop: "loop.md")


def test_a_pr_with_a_merge_go_and_no_trail_is_told_what_trail_is_missing(opted: None) -> None:
    why = approvals.outside(pull(GO), "")
    assert why is not None and "its author merges it" not in why
    assert "carries a merge go" in why and "approvals.py verdict" in why


def test_a_pr_with_no_go_and_no_trail_is_still_its_authors(opted: None) -> None:
    why = approvals.outside(pull("Looks fine."), "")
    assert why is not None and why.endswith("its author merges it")
