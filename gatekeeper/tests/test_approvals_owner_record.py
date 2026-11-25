"""`check build` leaves an `Owner:` record on the PR, the lead's session link, so several agent trees working one repo
can tell their PRs from another tree's (#2494). A run with no session to name writes none and is not refused."""

from __future__ import annotations

import subprocess

import pytest
from approvals_harness import approvals, approved, pull
from test_approvals import TRACKER, in_project, loop_md

SERVER, LEAD = "https://example.test", "lead-session"
LINK = f"{SERVER}/c/{LEAD}"


@pytest.fixture
def omnigent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNNER_SERVER_URL", f"{SERVER}/")
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", LEAD)


@pytest.fixture
def posted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Every comment `check build` posts, instead of posting it; the claim's own assignments are dropped."""
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(approvals, "assign", lambda *_a, **_k: None)
    monkeypatch.setattr(approvals, "session_field", lambda *_a: None)
    monkeypatch.setattr(approvals, "comment", lambda number, body: calls.append((number, body)))
    return calls


def build(monkeypatch: pytest.MonkeyPatch, *comments: str) -> int:
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, loop_md()))
    pr = pull(comments=comments)
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pr)
    return int(approvals.main(["check", "build", "7"]))


def owner_notes(posted: list[tuple[int, str]]) -> list[str]:
    return [body for _number, body in posted if body.startswith("Owner: ")]


@pytest.mark.usefixtures("omnigent")
def test_check_build_writes_the_owner_record_on_the_pr(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    assert build(monkeypatch) == 0
    assert [number for number, body in posted if body.startswith("Owner: ")] == [7]
    assert owner_notes(posted) == [f"Owner: {LINK}\n"]  # the first line, the link, nothing else


@pytest.mark.usefixtures("omnigent")
def test_a_record_that_already_says_the_same_is_not_written_again(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    assert build(monkeypatch, f"Owner: {LINK}\n") == 0
    assert owner_notes(posted) == []


@pytest.mark.usefixtures("omnigent")
def test_check_build_exits_1_when_the_record_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(number: int, body: str) -> None:
        if body.startswith("Owner: "):
            raise subprocess.CalledProcessError(1, "gh", stderr="FORBIDDEN")

    monkeypatch.setattr(approvals, "assign", lambda *_a, **_k: None)
    monkeypatch.setattr(approvals, "session_field", lambda *_a: None)
    monkeypatch.setattr(approvals, "comment", refuse)
    assert build(monkeypatch) == 1
    assert "PR #7: could not write the `Owner:` record (FORBIDDEN)" in capsys.readouterr().out


def test_a_run_with_no_session_writes_no_record_and_is_not_refused(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    monkeypatch.delenv("RUNNER_SERVER_URL", raising=False)
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)
    assert build(monkeypatch) == 0
    assert owner_notes(posted) == []


@pytest.mark.usefixtures("omnigent")
def test_the_record_names_no_session_id_but_the_server_relative_link(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    monkeypatch.setenv(
        "OMNIGENT_SESSION_ID", "worker-session"
    )  # a child's own id stays out of the record
    assert build(monkeypatch) == 0
    assert "worker-session" not in repr(posted)
