"""approvals.py `check ready`: the PR body's `## Evidence` alone, by the code `check merge` runs (#1577)."""

from __future__ import annotations

import pytest
from approvals_harness import approvals, approved, loop_md, pull


@pytest.fixture(autouse=False)
def project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "project", lambda: (None, loop_md("")))
    monkeypatch.setattr(approvals, "adopted", lambda issues, loop: issues)
    monkeypatch.setattr(approvals, "closing_issues", lambda pr: [approved(1)])


def test_ready_refuses_a_body_with_no_evidence_and_says_what_merge_says(
    project: None, capsys: pytest.CaptureFixture[str]
) -> None:
    pr = pull(body="Closes #1\n")
    assert approvals.checked("ready", pr, None) == 1
    assert capsys.readouterr().out.strip() in approvals.proofs("merge", pr, [approved(1)], loop_md(""))


def test_ready_takes_a_body_with_evidence_and_checks_nothing_else(
    project: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert approvals.checked("ready", pull(body="## Evidence\n\nran it\n"), None) == 0  # no verdict, no gate owed
    assert "evidence proof" in capsys.readouterr().out
