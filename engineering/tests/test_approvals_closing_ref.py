"""approvals.py: a PR that closes no open issue is refused at `check build`, since GitHub lists a PR on an issue's
Development panel only for a closing keyword (`Part of` alone shows on no issue)."""

from __future__ import annotations

import pytest
from approvals_harness import LOOP, TRACKER, approvals, approved, pull


def refusal(body: str, state: str = "OPEN") -> list[str]:
    issue = approved(1, "kind:bug")
    issue["state"] = state
    pr = pull(body=body)
    pr["closingIssuesReferences"]["nodes"] = [issue] if body.startswith("Closes") else []
    return approvals.closes_nothing(pr, [issue], LOOP)


@pytest.mark.parametrize("body", ["Part of #1", "Implements #1"])
def test_a_pr_with_only_a_link_is_refused(body: str) -> None:
    (line,) = refusal(body)
    assert line.startswith("the PR closes no open issue") and "own sub-issue" in line


def test_a_pr_closing_an_open_issue_passes() -> None:
    assert refusal("Closes #1") == []


def test_a_pr_closing_a_closed_issue_is_refused() -> None:
    assert refusal("Closes #1", "CLOSED")


def test_a_pr_naming_no_issue_is_left_to_the_no_issue_refusal() -> None:
    assert approvals.closes_nothing(pull(body="x"), [], LOOP) == []


def test_a_verified_release_pin_bump_is_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "pin_target", lambda _pull: "engineering-v1.0.0")
    assert refusal("Part of #1") == []


@pytest.mark.parametrize(("body", "refused"), [("Part of #1", True), ("Closes #1", False)])
def test_check_build_refuses_a_part_of_only_pr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], body: str, refused: bool
) -> None:
    """The refusal sits in gated(), which check build, check merge and land share: dropping that call must fail here."""
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, LOOP))
    issue = approved(1, "kind:bug")
    issue["state"] = "OPEN"
    pr = pull(body=body)
    pr["closingIssuesReferences"]["nodes"] = [issue] if not refused else []
    monkeypatch.setattr(approvals, "pull_request", lambda _pr: pr)
    monkeypatch.setattr(approvals, "issues_of", lambda numbers: [issue])
    approvals.main(["check", "build", "7"])
    out = capsys.readouterr().out
    assert ("the PR closes no open issue" in out) is refused
