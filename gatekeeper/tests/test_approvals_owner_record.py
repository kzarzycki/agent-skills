"""`check build` leaves an `Owner:` record on the PR, the team and the lead's session link, so several teams on one
project can tell their PRs from another team's (#2494). It is kept only where the policy has a `team` section."""

from __future__ import annotations

import subprocess

import pytest
from approvals_harness import approvals, approved, pull
from test_approvals import TRACKER, in_project, loop_md

SERVER, LEAD = "https://example.test", "lead-session"
LINK = f"{SERVER}/c/{LEAD}"
TEAM = loop_md("team:\n  name: alpha\n")


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


def build(
    monkeypatch: pytest.MonkeyPatch, loop: str, *comments: str, viewer: str | None = "ci-account"
) -> int:
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, loop))
    monkeypatch.setattr(approvals, "viewer", lambda: viewer)
    pr = pull(comments=comments)
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pr)
    return int(approvals.main(["check", "build", "7"]))


def owner_notes(posted: list[tuple[int, str]]) -> list[str]:
    return [approvals.machine(body) for number, body in posted if body.startswith("Owner: ")]


@pytest.mark.usefixtures("omnigent")
def test_check_build_writes_the_owner_record_on_the_pr(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    assert build(monkeypatch, TEAM) == 0
    assert [number for number, body in posted if body.startswith("Owner: ")] == [7]
    assert owner_notes(posted) == [f"Owner: alpha\nSession: {LINK}\n"]


@pytest.mark.usefixtures("omnigent")
def test_the_team_defaults_to_the_account_name(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    assert build(monkeypatch, loop_md("team: {}\n")) == 0
    assert owner_notes(posted) == [f"Owner: ci-account\nSession: {LINK}\n"]


@pytest.mark.usefixtures("omnigent")
def test_a_record_that_already_says_the_same_is_not_written_again(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    same = approvals.fold("Owner: alpha", details=f"Session: {LINK}")
    assert build(monkeypatch, TEAM, same) == 0
    assert owner_notes(posted) == []


def test_check_build_exits_1_with_no_session_to_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    posted: list[tuple[int, str]],
) -> None:
    monkeypatch.delenv("RUNNER_SERVER_URL", raising=False)
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)
    assert build(monkeypatch, TEAM) == 1
    assert "no `Owner:` record: this run names no Omnigent session" in capsys.readouterr().out
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
    assert build(monkeypatch, TEAM) == 1
    assert "PR #7: could not write the `Owner:` record (FORBIDDEN)" in capsys.readouterr().out


def test_a_policy_without_a_team_section_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    monkeypatch.delenv("RUNNER_SERVER_URL", raising=False)
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)
    assert build(monkeypatch, loop_md()) == 0
    assert owner_notes(posted) == []


@pytest.mark.usefixtures("omnigent")
def test_the_record_names_no_session_id_but_the_server_relative_link(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    monkeypatch.setenv(
        "OMNIGENT_SESSION_ID", "worker-session"
    )  # a child's own id stays out of the record
    assert build(monkeypatch, TEAM) == 0
    assert "worker-session" not in repr(posted)
