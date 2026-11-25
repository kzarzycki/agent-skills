"""`claim <issue>` leaves an early claim as a record on the issue, `--takeover` a `Handover:` record, and `check build`
refuses an issue another session holds an unreleased claim on (#2498). Both apply whenever the run has a session to
name, with no policy section; a run with no session writes and reads no claim."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import approvals, approved, pull
from test_approvals import TRACKER, in_project, loop_md

SERVER, LEAD, OTHER = "https://example.test", "lead-session", "other-session"
LINK, THEIRS = f"{SERVER}/c/{LEAD}", f"{SERVER}/c/{OTHER}"
LOOP = loop_md()


def held(session: str, head: str = "Assigned: @owner") -> str:
    return approvals.fold(head, details=f"By: claim\nSession: {session}")


@pytest.fixture
def omnigent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNNER_SERVER_URL", f"{SERVER}/")
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", LEAD)
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "worker-session")


@pytest.fixture
def posted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(approvals, "assign", lambda *_a, **_k: None)
    monkeypatch.setattr(approvals, "session_field", lambda *_a: None)
    monkeypatch.setattr(approvals, "comment", lambda number, body: calls.append((number, body)))
    return calls


def claim_args(monkeypatch: pytest.MonkeyPatch, loop: str, *comments: str) -> None:
    """A project whose issue 1 carries `comments`."""
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, loop))
    monkeypatch.setattr(approvals, "viewer", lambda: "owner")
    issue = approved(1, "area:web", "kind:bug")
    issue["comments"] = approved(1, "area:web", "kind:bug", body="x")["comments"]
    issue["comments"]["nodes"] = [*issue["comments"]["nodes"], *_notes(comments)]
    issue["comments"]["totalCount"] = len(issue["comments"]["nodes"])
    monkeypatch.setattr(approvals, "issue_node", lambda _n: issue)


def _notes(bodies: tuple[str, ...]) -> list[dict[str, Any]]:
    from test_approvals import note

    return [note(body) for body in bodies]


def build(monkeypatch: pytest.MonkeyPatch, loop: str, *comments: str) -> int:
    claim_args(monkeypatch, loop, *comments)
    pr = pull()
    pr["closingIssuesReferences"]["nodes"] = [approvals.issue_node(1)]
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pr)
    return int(approvals.main(["check", "build", "7"]))


def records(posted: list[tuple[int, str]], first: str) -> list[str]:
    return [approvals.machine(b) for n, b in posted if n == 1 and b.startswith(first)]


@pytest.mark.usefixtures("omnigent")
def test_claim_writes_an_assigned_record_naming_the_session(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    claim_args(monkeypatch, LOOP)
    assert approvals.main(["claim", "1"]) == 0
    assert records(posted, "Assigned: @owner") == [
        f"Assigned: @owner\nBy: claim\nSession: {LINK}\n"
    ]


@pytest.mark.usefixtures("omnigent")
def test_a_second_session_is_refused_naming_the_holder(
    monkeypatch: pytest.MonkeyPatch,
    posted: list[tuple[int, str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    claim_args(monkeypatch, LOOP, held(THEIRS))
    assert approvals.main(["claim", "1"]) == 1
    said = capsys.readouterr().out
    assert f"claimed by @owner (session {THEIRS})" in said
    assert posted == []


@pytest.mark.usefixtures("omnigent")
def test_check_build_exits_1_naming_the_holder_and_claims_nothing(
    monkeypatch: pytest.MonkeyPatch,
    posted: list[tuple[int, str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert build(monkeypatch, LOOP, held(THEIRS)) == 1
    assert f"#1: claimed by @owner (session {THEIRS})" in capsys.readouterr().out
    assert [b for _n, b in posted if b.startswith("Assigned: ")] == []


@pytest.mark.usefixtures("omnigent")
def test_check_build_passes_for_the_session_that_holds_the_claim(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    assert build(monkeypatch, LOOP, held(LINK)) == 0


@pytest.mark.usefixtures("omnigent")
def test_a_released_claim_no_longer_blocks(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    released = approvals.fold("Released: @owner", details="By: claim")
    assert build(monkeypatch, LOOP, held(THEIRS), released) == 0


@pytest.mark.usefixtures("omnigent")
def test_takeover_writes_a_handover_record(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    claim_args(monkeypatch, LOOP, held(THEIRS))
    assert approvals.main(["claim", "1", "--takeover"]) == 0
    assert records(posted, "Handover: @owner") == [
        f"Handover: @owner\nBy: claim\nFrom: {THEIRS}\nSession: {LINK}\n"
    ]
    # the handover is now the claim: this session holds it, the other no longer does
    after = approvals.fold(
        "Handover: @owner", details=f"By: claim\nFrom: {THEIRS}\nSession: {LINK}"
    )
    assert build(monkeypatch, LOOP, held(THEIRS), after) == 0


@pytest.mark.usefixtures("omnigent")
def test_release_ends_only_this_sessions_claim(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    claim_args(monkeypatch, LOOP, held(THEIRS))
    assert approvals.main(["claim", "1", "--release"]) == 1
    claim_args(monkeypatch, LOOP, held(LINK))
    assert approvals.main(["claim", "1", "--release"]) == 0
    assert [b.split("\n")[0] for _n, b in posted] == ["Released: @owner"]


def test_a_run_with_no_session_writes_reads_and_refuses_nothing(
    monkeypatch: pytest.MonkeyPatch,
    posted: list[tuple[int, str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("RUNNER_SERVER_URL", raising=False)
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)
    assert build(monkeypatch, LOOP, held(THEIRS)) == 0
    claim_args(monkeypatch, LOOP, held(THEIRS))
    assert approvals.main(["claim", "1"]) == 0
    assert approvals.main(["claim", "1", "--takeover"]) == 0
    assert "names no session" in capsys.readouterr().out
    assert [b for _n, b in posted if b.startswith(("Handover", "Released"))] == []
    # only check build's own claim, the record it wrote before this story
    assert [b for _n, b in posted if "By: claim" in b] == []


@pytest.mark.usefixtures("omnigent")
def test_the_records_name_no_session_id_but_the_server_relative_link(
    monkeypatch: pytest.MonkeyPatch, posted: list[tuple[int, str]]
) -> None:
    claim_args(monkeypatch, LOOP)
    assert approvals.main(["claim", "1"]) == 0
    claim_args(monkeypatch, LOOP, held(THEIRS))
    assert approvals.main(["claim", "1", "--takeover"]) == 0
    assert "worker-session" not in repr(posted)
    assert LINK in repr(posted)
