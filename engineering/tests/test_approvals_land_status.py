"""approvals.py: `land` posts the `land` status on a head right before it merges it, and on no head it doesn't merge (#1289)."""

from __future__ import annotations

import re
from typing import Any

import pytest
from approvals_harness import (
    approvals,
    lands,  # noqa: F401
)


@pytest.fixture
def posted(lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Every status land posts, in order with its merge calls (`lands["calls"]`)."""
    seen: list[tuple[Any, ...]] = []

    def post(head: str, context: str, description: str, state: str = "success") -> None:
        seen.append((head, context, description, state, len(lands["calls"])))

    monkeypatch.setattr(approvals, "post_status", post)
    return seen


def test_a_land_that_merges_posts_land_on_the_head_before_the_merge_call(
    lands: dict[str, Any], posted: list[tuple[Any, ...]]
) -> None:
    head = lands["open"](7, {"7.txt": "7\n"})
    code, lines = lands["land"]()
    assert code == 0, lines
    [(sha, context, description, state, merges_before)] = [p for p in posted if p[1] == "land"]
    assert (sha, context, state) == (head, "land", "success")
    assert re.search(r"nonce [0-9a-f]{16}$", description), description
    assert not any(call[:2] == ("pr", "merge") for call in lands["calls"][:merges_before])
    assert lands["calls"][merges_before][:2] == ("pr", "merge")


def test_a_land_that_does_not_merge_posts_no_land_status(
    lands: dict[str, Any], posted: list[tuple[Any, ...]]
) -> None:
    lands["open"](7, {"7.txt": "7\n", "red.txt": ""})
    code, lines = lands["land"]()
    assert code == 1, lines
    assert not any(call[:2] == ("pr", "merge") for call in lands["calls"])
    assert [p for p in posted if p[1] == "land"] == []
