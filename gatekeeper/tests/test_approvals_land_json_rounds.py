"""approvals.py: `land --json` follows the exit a later step picks, and names a PR whose GitHub write fails (#2829)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from approvals_harness import (
    approvals,
    lands,  # noqa: F401
)
from test_approvals_batch_wait import (  # noqa: F401
    Clock,
    check,
    checks_required,
    clock,
    policy,
)
from test_approvals_github_queue import queue  # noqa: F401


def line_of(lines: list[str], number: int) -> dict[str, Any]:
    [found] = [
        each
        for each in map(json.loads, (x for x in lines if x.startswith("{")))
        if each["pr"] == number
    ]
    return found


@pytest.mark.parametrize(
    ("change", "cause"),
    [
        ("red", "checks"),
        ("conflict", "conflict"),
        ("no review", "proof"),
    ],
)
def test_a_pr_that_becomes_unlandable_during_the_batch_wait_is_refused_not_waiting(
    lands: dict[str, Any],
    clock: Clock,
    change: str,
    cause: str,
) -> None:
    policy(lands, "land:\n  batch_wait_seconds: 600")
    lands["open"](7, {"7.txt": "7\n"})
    lands["open"](8, {"8.txt": "8\n"})
    check(lands, 8, "PENDING")

    def turn(_now: float) -> None:
        if change == "red":
            check(lands, 8, "FAILURE")
        elif change == "conflict":
            lands["pulls"][8]["mergeable"] = "CONFLICTING"
        else:
            lands["pulls"][8]["reviews"]["nodes"] = []

    clock.tick = turn
    code, lines = lands["land"]("8", "--json")
    assert code == 1, lines
    found = line_of(lines, 8)
    assert (found["state"], found["cause"]) == ("refused", cause)


def test_a_failed_comment_write_still_names_the_conflicting_pr(
    queue: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = queue["opened"](7)
    queue["pulls"][7]["mergeable"] = "CONFLICTING"

    def refused(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403: comment refused")

    monkeypatch.setattr(approvals, "comment", refused)
    code, lines = queue["land"]("7", "--json")
    assert code == 1, lines
    assert "HTTP 403: comment refused" in lines
    found = line_of(lines, 7)
    assert (found["head"], found["state"], found["cause"]) == (head, "refused", "conflict")


def test_a_failed_write_that_no_step_marked_is_refused_as_github(
    queue: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = queue["opened"](7)

    def refused(*_args: Any, **_kwargs: Any) -> None:
        raise approvals.Refused("signing is not possible here")

    monkeypatch.setattr(approvals, "signed", refused)
    code, lines = queue["land"]("7", "--json")
    assert code == 1, lines
    found = line_of(lines, 7)
    assert (found["head"], found["state"], found["cause"]) == (head, "refused", "github")


def test_a_queue_merged_pr_names_the_landed_comment_it_posted(
    queue: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue["opened"](7)
    queue["pulls"][7]["url"] = "https://github.com/o/r/pull/7"
    assert queue["land"]("7")[0] == 0
    queue["queue_merge"](7)
    posted = approvals.comment

    def linked(number: int, body: str) -> str:
        posted(number, body)
        return f"https://github.com/o/r/pull/{number}#issuecomment-123"

    monkeypatch.setattr(approvals, "comment", linked)
    code, lines = queue["land"]("7", "--json")
    assert code == 0, lines
    found = line_of(lines, 7)
    assert (found["state"], found["url"]) == (
        "merged",
        "https://github.com/o/r/pull/7#issuecomment-123",
    )


def test_a_failed_label_write_keeps_the_bare_candidate_in_the_lines(
    queue: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    head = queue["opened"](7)
    original = approvals.label

    def refused(number: int, name: str, *, add: bool) -> None:
        if name == approvals.QUEUED and add:
            raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403: label refused")
        return original(number, name, add=add)

    monkeypatch.setattr(approvals, "label", refused)
    code, lines = queue["land"]("--json")
    assert code == 1, lines
    found = line_of(lines, 7)
    assert (found["head"], found["state"], found["cause"]) == (head, "refused", "github")


def test_an_error_before_any_candidate_is_judged_names_every_ready_pr_of_a_bare_land(
    queue: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    seven, eight = queue["opened"](7), queue["opened"](8)

    def refused(*_args: Any, **_kwargs: Any) -> None:
        raise approvals.Refused("signing is not possible here")

    monkeypatch.setattr(approvals, "signed", refused)
    code, lines = queue["land"]("--json")
    assert code == 1, lines
    assert [
        (each["pr"], each["head"], each["cause"])
        for each in map(json.loads, (x for x in lines if x.startswith("{")))
    ] == [
        (7, seven, "github"),
        (8, eight, "github"),
    ]
