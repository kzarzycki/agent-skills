"""approvals.py: the local queue's `land` refuses a PR head with no pass record (R6, #2178): it runs no test, so a
merge with neither a queue run nor a record of each PR is refused, naming the missing record and the command that
makes it."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    approvals,
    lands,  # noqa: F401
)


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    """The heads origin holds a gate pass record of; gate_record answers for them as `gate-record <head>` does."""
    held: set[str] = set()

    def gate_record(head: str, words: list[str]) -> int:
        assert words == []
        if head in held:
            print(f"recorded: Tree t on {head[:12]}: mise run check, as refs/heads/loop-gate/t-k")
            return 0
        print(
            f"no record of `mise run check` on tree t: run it (origin holds no record branch for {head[:12]})"
        )
        return 1

    monkeypatch.setattr(approvals, "gate_record", gate_record)
    return held


def test_a_head_with_no_pass_record_is_not_landed_and_land_says_what_makes_one(
    lands: dict[str, Any], records: set[str]
) -> None:
    head = lands["open"](7, {"7.txt": "7\n"})
    code, lines = lands["land"]("7")
    assert code == 1, lines
    assert lands["merged"]() == []
    said = "\n".join(lines)
    assert f"PR #7: not landed: no pass record on its head {head[:12]}" in said
    assert "no record of `mise run check` on tree t" in said
    assert "run `approvals.py local-ci --record` on that head" in said


def test_a_recorded_head_lands_beside_a_refused_one(
    lands: dict[str, Any], records: set[str]
) -> None:
    records.add(lands["open"](7, {"7.txt": "7\n"}))
    lands["open"](8, {"8.txt": "8\n"})
    code, lines = lands["land"]()
    assert lands["merged"]() == ["7"], lines
    assert any(line.startswith("PR #8: not landed: no pass record") for line in lines)
    assert code == 0  # a bare land: the refused PR is said, and only a named one's exit counts
    assert lands["land"]("8")[0] == 1
