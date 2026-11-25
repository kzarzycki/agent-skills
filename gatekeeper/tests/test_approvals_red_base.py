"""approvals.py: `check merge` and `land` name the base's failed push run, and say nothing of a green one (#2565)."""

from __future__ import annotations

import pytest
from approvals_harness import approvals

URL = "https://github.com/o/r/actions/runs/9/job/1"


def checks(conclusion: str) -> dict[str, dict[str, str]]:
    return {
        "test": {"conclusion": conclusion, "url": URL},
        "loop:approvals": {"conclusion": "FAILURE", "url": "x"},
    }


@pytest.fixture(autouse=True)
def required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda base: {"test", "loop:approvals"})


def test_a_red_latest_push_run_is_named_with_its_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("FAILURE"))
    lines = approvals.red_base("main")
    assert len(lines) == 1
    assert "main is red" in lines[0] and "`test`" in lines[0] and "actions/runs/9" in lines[0]


def test_a_green_latest_push_run_says_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("SUCCESS"))
    assert approvals.red_base("main") == []
