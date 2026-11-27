"""A PR made under a session carries the session's link (#2825): `claim <issue>` writes it on the issue before any PR
exists, and `check session` / `check merge` fail an `Impl:` line that lacks it."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import approvals, approved, pull
from test_approvals import TRACKER, VERDICT, in_project, loop_md

SERVER, LEAD = "https://example.test", "0123456789abcdef0123456789abcdef"
LINK = f"{SERVER}/c/{LEAD}"
LOOP = loop_md()
LEAD_MD = Path(__file__).parents[2] / "loop/skills/engineering-loop/lead.md"

WITH_SESSION = f"## Evidence\n\nlog line\n\nImpl: cc/sonnet-5.5/? · Session: {LINK}\n"
WITHOUT_SESSION = "## Evidence\n\nlog line\n\nImpl: cc/sonnet-5.5/?\n"
NO_IMPL = "## Evidence\n\nlog line\n"


def test_claim_on_an_issue_with_no_pr_writes_the_assigned_record_with_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance 1: no PR is read, and the issue gets its claim and a Session line."""
    in_project(monkeypatch)
    monkeypatch.setenv("OMNIGENT_SESSION_LINK", LINK)
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, LOOP))
    monkeypatch.setattr(approvals, "viewer", lambda: "owner")
    monkeypatch.setattr(approvals, "issue_node", lambda _n: approved(1, "area:web", "kind:bug"))
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pytest.fail("read a PR"))
    posted: list[str] = []
    monkeypatch.setattr(approvals, "comment", lambda _n, body: posted.append(body))
    assert approvals.main(["claim", "1"]) == 0
    assert [approvals.machine(body) for body in posted] == [
        f"Assigned: @owner\nBy: claim\nSession: {LINK}\n"
    ]


def test_lead_md_step_1_tells_the_lead_to_claim_the_issue_it_takes() -> None:
    """Acceptance 1: the step that runs the claim at take-up, before any PR, is in the lead's role file."""
    text = " ".join(LEAD_MD.read_text().split())
    assert re.search(r"1\. \*\*Intent\.\*\*.*approvals\.py claim <issue>.*3\. \*\*Branch", text)


@pytest.mark.parametrize(
    ("body", "fails"),
    [(WITHOUT_SESSION, True), (WITH_SESSION, False), (NO_IMPL, False)],
    ids=["no-session-part", "session-part", "no-impl-line"],
)
def test_check_session_fails_only_an_impl_line_with_no_session_part(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: str,
    fails: bool,
) -> None:
    pr = pull(body=body)
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(approvals, "toplevel", lambda: Path("."))
    assert approvals.main(["check", "session", "7"]) == (1 if fails else 0)
    said = capsys.readouterr().out
    assert ("no session part" in said and "check build" in said) == fails


@pytest.mark.parametrize(
    ("body", "fails"),
    [(WITHOUT_SESSION, True), (WITH_SESSION, False), (NO_IMPL, False)],
    ids=["no-session-part", "session-part", "no-impl-line"],
)
def test_check_merge_fails_on_the_same_bodies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    required: list[str],
    body: str,
    fails: bool,
) -> None:
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, LOOP))
    pr: dict[str, Any] = pull(body=body, reviews=(VERDICT,), checks=(), files=("app.py",))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    assert approvals.main(["check", "merge", "7"]) == (1 if fails else 0)
    assert ("no session part" in capsys.readouterr().out) == fails
    assert required == ["main"]


@pytest.mark.parametrize(
    "line",
    [
        f"Impl: x · Session: {LINK[:-1]}",  # 31 hex
        f"Impl: x · Session: {SERVER}/c/{LEAD}0",  # 33 hex
        f"Impl: x · Session: {SERVER}/c/not-a-hex-id-not-a-hex-id-xxxxxxx",
        f"Impl: x\nSession: {LINK}",  # not on the Impl line
    ],
)
def test_a_malformed_or_misplaced_session_part_is_a_gap(line: str) -> None:
    assert approvals.session_gap(pull(body=f"## Evidence\n\n{line}\n"))
