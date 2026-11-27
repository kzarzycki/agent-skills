"""approvals.py: `land --json` names each PR's outcome on a line of its own after the usual output (#2829).

One test per state and cause: `{"pr", "head", "state", "cause", "url"}`, read off the fake GitHub's runs of `land`. The
line is written where the exit is picked, so each test also pins the exit it goes with.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from approvals_harness import (
    approvals,
    lands,  # noqa: F401
)
from test_approvals import lock_commit
from test_approvals_github_queue import (  # noqa: F401
    AGAIN_AT,
    RED_AT,
    queue,
    red_group,
    run,
)
from test_approvals_land_event import hold_lock


def outcomes(lines: list[str]) -> list[dict[str, Any]]:
    """The JSON lines of a land's output, and nothing of the usual text among them."""
    return [json.loads(line) for line in lines if line.startswith("{")]


def only(lines: list[str], number: int, head: str) -> tuple[str, str | None]:
    """The one line of PR `number`, its `pr` and `head` checked and its `url` a string: (state, cause)."""
    [found] = outcomes(lines)
    assert found["pr"] == number and found["head"] == head
    assert set(found) == {"pr", "head", "state", "cause", "url"} and isinstance(found["url"], str)
    return found["state"], found["cause"]


# --- merged and queued


def test_a_pr_the_local_queue_merged_is_merged(lands: dict[str, Any]) -> None:
    head = lands["open"](7, {"7.txt": "7\n"})
    code, lines = lands["land"]("7", "--json")
    assert code == 0, lines
    assert only(lines, 7, head) == ("merged", None)
    assert lines[-1].startswith("{") and lands["merged"]() == ["7"]


def test_a_pr_enqueued_in_githubs_queue_is_queued(queue: dict[str, Any]) -> None:
    head = queue["opened"](7)
    code, lines = queue["land"]("7", "--json")
    assert code == 0, lines
    assert only(lines, 7, head) == ("queued", None)


def test_a_bare_land_names_each_candidate_it_queued(queue: dict[str, Any]) -> None:
    eight, seven = queue["opened"](8), queue["opened"](7)
    code, lines = queue["land"]("--json")
    assert code == 0, lines
    assert [(each["pr"], each["head"], each["state"]) for each in outcomes(lines)] == [
        (7, seven, "queued"),
        (8, eight, "queued"),
    ]


def test_without_json_land_prints_no_outcome_line(queue: dict[str, Any]) -> None:
    queue["opened"](7)
    code, lines = queue["land"]("7")
    assert code == 0 and outcomes(lines) == []


# --- waiting: something is moving


def test_a_land_behind_another_lands_lock_is_waiting_on_the_lock(lands: dict[str, Any]) -> None:
    head = lands["open"](7, {"7.txt": "7\n"})
    lock_commit(lands, 10 * 60)
    code, lines = lands["land"]("7", "--json")
    assert code == approvals.WAITING, lines
    assert only(lines, 7, head) == ("waiting", "lock")


def test_a_pr_whose_required_check_is_pending_is_waiting_on_checks(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"check"})
    head = lands["open"](7, {"7.txt": "7\n"}, checks=(("check", "PENDING"),))
    code, lines = lands["land"]("7", "--json")
    assert code == approvals.WAITING, lines
    assert only(lines, 7, head) == ("waiting", "checks")


def test_a_conflict_removal_github_is_still_working_out_is_waiting_on_mergeability(
    queue: dict[str, Any],
) -> None:
    head = queue["opened"](8)
    queue["pulls"][8]["mergeable"] = "UNKNOWN"
    queue["remove"](8, approvals.MERGE_CONFLICT)
    code, lines = queue["land"]("8", "--json")
    assert code == approvals.WAITING, lines
    assert only(lines, 8, head) == ("waiting", "mergeability")


def test_a_red_group_built_on_a_base_commit_still_running_is_waiting_on_base_checks(
    queue: dict[str, Any],
) -> None:
    head = queue["opened"](7)
    queue["remove"](7, approvals.FAILED_CHECKS, at=RED_AT, group="g1")
    red_group(queue, "g1", 410)
    queue["built"]["g1"] = "m1"
    queue["checks"]["m1"] = [run("qualify", None, 500)]  # type: ignore[arg-type]
    code, lines = queue["land"]("7", "--json")
    assert code == approvals.WAITING, lines
    assert only(lines, 7, head) == ("waiting", "base-checks")


def test_a_red_base_is_waiting_on_base_red_and_not_the_prs_fault(queue: dict[str, Any]) -> None:
    head = queue["opened"](7)
    queue["remove"](7, approvals.FAILED_CHECKS, at=RED_AT, group="g1")
    queue["remove"](7, approvals.FAILED_CHECKS, at=AGAIN_AT, group="g2")
    red_group(queue, "g2", 420)
    queue["checks"]["main"] = [run("qualify", "failure", 500)]
    code, lines = queue["land"]("7", "--json")
    assert code == 1, lines  # the exit stays 1: only the line tells it from a fault of the PR
    assert only(lines, 7, head) == ("waiting", "base-red")


def test_a_bare_land_on_a_red_base_names_every_ready_pr_as_waiting_on_base_red(
    queue: dict[str, Any],
) -> None:
    seven, eight = queue["opened"](7), queue["opened"](8)
    queue["remove"](7, approvals.FAILED_CHECKS, at=RED_AT, group="g1")
    red_group(queue, "g1", 410)
    queue["checks"]["main"] = [run("qualify", "failure", 500)]
    code, lines = queue["land"]("--json")
    assert code == 1, lines
    assert [
        (each["pr"], each["head"], each["state"], each["cause"]) for each in outcomes(lines)
    ] == [
        (7, seven, "waiting", "base-red"),
        (8, eight, "waiting", "base-red"),
    ]


# --- needs-owner: only a person can act


def test_a_high_risk_pr_without_the_owners_go_needs_the_owners_go(queue: dict[str, Any]) -> None:
    head = queue["opened"](7, {".github/ci.yml": "ci\n"})
    queue["pulls"][7]["files"] = {"nodes": [{"path": ".github/ci.yml"}]}
    code, lines = queue["land"]("7", "--json")
    assert code == approvals.WAITING, lines
    assert only(lines, 7, head) == ("needs-owner", "go")


def test_a_head_that_timed_out_twice_in_the_queue_needs_a_person(queue: dict[str, Any]) -> None:
    head = queue["opened"](7)
    queue["checks"]["g1"] = [run("qualify", "timed_out", 410)]
    queue["checks"]["g2"] = [run("qualify", "timed_out", 420)]
    queue["remove"](7, approvals.FAILED_CHECKS, at=RED_AT, group="g1")
    assert queue["land"]("7")[0] == 0
    queue["remove"](7, approvals.FAILED_CHECKS, at=AGAIN_AT, group="g2")
    code, lines = queue["land"]("7", "--json")
    assert code == approvals.WAITING, lines
    assert only(lines, 7, head) == ("needs-owner", "queue-timeout")


def test_a_wait_that_reaches_its_ceiling_on_a_held_lock_needs_a_person(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    head = lands["open"](7, {"7.txt": "7\n"})
    hold_lock(lands)
    monkeypatch.setattr(approvals, "land_wait", lambda: 0)  # one look, then the ceiling
    code, lines = lands["land"]("7", "--wait", "--json")
    assert code == approvals.WAITING, lines
    assert only(lines, 7, head) == ("needs-owner", "ceiling")


# --- refused: the PR needs a fix


def test_a_pr_with_no_verifier_review_is_refused_for_its_proof(lands: dict[str, Any]) -> None:
    head = lands["open"](7, {"7.txt": "7\n"}, reviews=())
    code, lines = lands["land"]("7", "--json")
    assert code == 1, lines
    assert only(lines, 7, head) == ("refused", "proof")


def test_a_pr_whose_required_check_is_red_is_refused_for_its_checks(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"check"})
    head = lands["open"](7, {"7.txt": "7\n"}, checks=(("check", "FAILURE"),))
    code, lines = lands["land"]("7", "--json")
    assert code == 1, lines
    assert only(lines, 7, head) == ("refused", "checks")


def test_a_pr_github_reports_conflicting_is_refused_for_its_conflict(
    queue: dict[str, Any],
) -> None:
    head = queue["opened"](7)
    queue["pulls"][7]["mergeable"] = "CONFLICTING"
    code, lines = queue["land"]("7", "--json")
    assert code == 1, lines
    assert only(lines, 7, head) == ("refused", "conflict")


def test_a_pr_red_in_the_queue_twice_on_one_head_is_refused_as_evicted(
    queue: dict[str, Any],
) -> None:
    head = queue["opened"](7)
    queue["remove"](7, approvals.FAILED_CHECKS, at=RED_AT, group="g1")
    red_group(queue, "g1", 410)
    queue["land"]("7")
    queue["remove"](7, approvals.FAILED_CHECKS, at=AGAIN_AT, group="g2")
    red_group(queue, "g2", 420)
    code, lines = queue["land"]("7", "--json")
    assert code == 1, lines
    assert only(lines, 7, head) == ("refused", "evicted")


def test_an_enqueue_github_refuses_is_refused_as_github(queue: dict[str, Any]) -> None:
    head = queue["opened"](7)
    queue["refuse"] = True
    code, lines = queue["land"]("7", "--json")
    assert code == 1, lines
    assert only(lines, 7, head) == ("refused", "github")
