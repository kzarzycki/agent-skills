"""approvals.py: a base that requires `land` makes no land wait for it, since only the merge step of that land posts it (#1323)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    approvals,
    lands,  # noqa: F401
)


@pytest.fixture
def land_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """The base's rules require `land`, and the checks `loop:approvals` and `gatekeeper` the loop posts too."""
    monkeypatch.setattr(
        approvals, "required_checks", lambda _base: {"land", "loop:approvals", "gatekeeper"}
    )


def merged_after_land_status(lands: dict[str, Any]) -> bool:
    return lands["merged"]() == ["7"]


def test_a_required_land_does_not_hold_the_land_that_posts_it(
    lands: dict[str, Any], land_required: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    posted: list[str] = []
    monkeypatch.setattr(approvals, "post_status", lambda _head, context, *_: posted.append(context))
    code, lines = lands["land"]()
    assert code == 0, lines
    assert merged_after_land_status(lands)
    assert posted[0] == "land"  # before the merge call; the gate may post its own after


def test_a_required_land_does_not_hold_the_ci_wait(
    lands: dict[str, Any], land_required: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    # CI is on for this project; its head has no check of any name `land` could satisfy
    monkeypatch.setattr(approvals, "head_checks", lambda _pull, required: ([], None, set()))
    waits = approvals.ran(lands["pulls"][7], None)
    assert not any("`land`" in line for line in waits), waits


def test_a_required_land_does_not_keep_a_draft_from_being_readied(
    lands: dict[str, Any], land_required: None
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    lands["pulls"][7]["isDraft"] = True
    code, lines = lands["land"]("7")
    assert code == 0, lines
    assert merged_after_land_status(lands)
    assert not any(call[:3] == ("pr", "ready", "7") and "--undo" in call for call in lands["calls"])


def test_unreadied_judges_a_draft_without_the_statuses_the_loop_posts(
    lands: dict[str, Any], land_required: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    asked: list[set[str]] = []

    def landable(_pull: Any, _tracker: Any, _loop: Any, required: set[str], named: bool) -> Any:
        asked.append(required)
        return type("Verdict", (), {"draft": True})()

    monkeypatch.setattr(approvals, "landable", landable)
    pull = {**lands["pulls"][7], "readied": True, "waiting": []}
    assert approvals.unreadied([pull], "main", None, None) == [pull]
    # the same set readied() was given, so a draft it readied is not sent back for a status only land posts
    assert asked == [set()]


def test_land_joins_the_statuses_the_wait_skips_without_joining_own() -> None:
    # OWN keeps its meaning for head_proof: adding `land` to it would be a second change
    assert approvals.LAND not in approvals.OWN
    assert approvals.OWN <= approvals.OWN_WAIT and approvals.LAND in approvals.OWN_WAIT
