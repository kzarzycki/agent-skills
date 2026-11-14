"""approvals.py: `land --wait` stops at once on a conflicting PR its required checks never reach (#998)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

NO_QUALIFY = "PR #7: no `qualify` on the head commit yet"


@pytest.fixture
def unchecked(lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """PR #7 open with no check on its head, on a base that requires `qualify`."""
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"qualify"})
    lands["open"](7, {"7.txt": "7\n"}, checks=())
    return lands


def test_a_conflicting_pr_missing_its_required_check_stops_the_wait_with_the_fix(
    unchecked: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    unchecked["pulls"][7]["mergeable"] = "CONFLICTING"

    def slept(_seconds: float) -> None:
        raise AssertionError("land --wait waited on a check no workflow runs")

    monkeypatch.setattr(approvals.time, "sleep", slept)
    code, lines = unchecked["land"]("7", "--wait")
    assert code == 1, lines
    assert lines == [NO_QUALIFY, "PR #7 conflicts with main: merge `origin/main` in"]
    assert unchecked["merged"]() == []


@pytest.mark.parametrize("mergeable", ["MERGEABLE", "UNKNOWN"])
def test_a_pr_not_reported_conflicting_still_waits_for_its_required_check(
    unchecked: dict[str, Any], monkeypatch: pytest.MonkeyPatch, mergeable: str
) -> None:
    unchecked["pulls"][7]["mergeable"] = mergeable
    monkeypatch.setattr(approvals, "CEILING", 0)  # one look, then the ceiling
    code, lines = unchecked["land"]("7", "--wait")
    assert code == approvals.WAITING, lines
    assert lines == [NO_QUALIFY, "land --wait stopped after 0 hours, still waiting"]


def test_a_land_naming_no_pr_still_waits_on_a_conflicting_one(
    unchecked: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop is the named PR's: a batch land with nothing named keeps the wait it has today."""
    unchecked["pulls"][7]["mergeable"] = "CONFLICTING"
    monkeypatch.setattr(approvals, "CEILING", 0)
    code, lines = unchecked["land"]("--wait")
    assert code == approvals.WAITING, lines
    assert lines == [NO_QUALIFY, "land --wait stopped after 0 hours, still waiting"]


def test_a_conflicting_pr_with_its_required_check_red_is_red_not_a_conflict(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a missing check is one the conflict explains: a red one ran, and says so."""
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"qualify"})
    lands["open"](7, {"7.txt": "7\n"}, checks=(("qualify", "FAILURE"),))
    lands["pulls"][7]["mergeable"] = "CONFLICTING"
    code, lines = lands["land"]("7")
    assert code == 1, lines
    assert lines == ["PR #7: `qualify` is FAILURE on the head commit"]


@pytest.mark.parametrize(
    ("rest", "graphql"), [(True, "MERGEABLE"), (False, "CONFLICTING"), (None, "UNKNOWN")]
)
def test_rest_reads_mergeable_as_graphql_names_it(
    monkeypatch: pytest.MonkeyPatch, rest: bool | None, graphql: str
) -> None:
    """A cloud session reads the PR over REST, whose `mergeable` is a boolean, or null while GitHub computes it."""
    repo = {"full_name": "owner/repo", "default_branch": "main"}
    found = {
        "node_id": "PR_1",
        "number": 7,
        "title": "Feature",
        "state": "open",
        "mergeable": rest,
        "base": {"ref": "main", "repo": repo},
        "head": {"ref": "feature", "sha": "h", "repo": repo},
    }

    def read(path: str) -> Any:
        return found if path.endswith("/pulls/7") else {"commit": {"sha": "b"}}

    monkeypatch.setattr(approvals, "rest", read)
    for name in ("pr_changes", "rest_pages", "rest_latest"):
        monkeypatch.setattr(approvals, name, lambda *_args: [])
    for name in ("rest_notes", "rest_threads", "rest_authored", "rest_timeline", "rest_checks"):
        monkeypatch.setattr(approvals, name, lambda *_args: {})
    assert approvals.rest_pull(7)["mergeable"] == graphql
