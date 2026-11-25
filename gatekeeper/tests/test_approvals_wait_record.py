"""`record waiting` leaves a `Waiting on:` record, with a deadline, on a PR that waits on another agent tree's go, and clears
it; the supervisor of the owning agent tree reads it (#2501)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from approvals_harness import approvals, pull
from test_approvals import in_project


@pytest.fixture
def posted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(approvals, "comment", lambda number, body: calls.append((number, body)))
    return calls


def record(monkeypatch: pytest.MonkeyPatch, *comments: str, argv: tuple[str, ...]) -> int:
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pull(comments=comments))
    return int(approvals.main(["record", "waiting", "7", *argv]))


def deadline_of(body: str) -> datetime:
    line = next(l for l in approvals.machine(body).splitlines() if l.startswith("Deadline: "))
    return datetime.fromisoformat(line.removeprefix("Deadline: "))


def test_a_wait_is_recorded_with_the_default_deadline(monkeypatch, posted) -> None:
    assert record(monkeypatch, argv=("--on", "the other agent tree's go")) == 0
    [(number, body)] = posted
    assert number == 7 and body.startswith("Waiting on: the other agent tree's go\n")
    span = deadline_of(body) - datetime.now(UTC)
    assert timedelta(hours=23, minutes=58) < span <= timedelta(hours=24)


def test_a_span_sets_the_deadline(monkeypatch, posted) -> None:
    assert record(monkeypatch, argv=("--on", "a go", "--within", "2d")) == 0
    span = deadline_of(posted[0][1]) - datetime.now(UTC)
    assert timedelta(hours=47, minutes=58) < span <= timedelta(days=2)


def test_the_record_names_no_session_host_or_link(monkeypatch, posted) -> None:
    record(monkeypatch, argv=("--on", "a go"))
    assert "Session" not in posted[0][1] and "http" not in posted[0][1]


def test_clear_posts_the_record_again_with_a_cleared_line(monkeypatch, posted, capsys) -> None:
    earlier = approvals.fold("Waiting on: a go", details="Deadline: 2026-11-26T10:00:00Z")
    assert record(monkeypatch, earlier, argv=("--clear",)) == 0
    [(_, body)] = posted
    assert body.startswith("Waiting on: a go\n")
    assert "Cleared: " in approvals.machine(body) and "Deadline" not in approvals.machine(body)


@pytest.mark.parametrize(
    "argv", [(), ("--on", "a go", "--clear"), ("--on", "a go", "--within", "soon")]
)
def test_a_bad_call_is_refused_and_posts_nothing(monkeypatch, posted, argv) -> None:
    assert record(monkeypatch, argv=argv) == 1
    assert not posted


def test_clearing_a_cleared_or_absent_wait_is_refused(monkeypatch, posted) -> None:
    done = approvals.fold("Waiting on: a go", details="Cleared: 2026-11-25T10:00:00Z")
    assert record(monkeypatch, argv=("--clear",)) == 1
    assert record(monkeypatch, done, argv=("--clear",)) == 1
    assert not posted
