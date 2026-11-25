"""approvals.py: `check merge` and `land` name the base's failed push run, refuse one that failed before any test
ran, and say nothing of a green one (#2565)."""

from __future__ import annotations

import subprocess

import pytest
from approvals_harness import LOOP, TRACKER, VERDICT, approvals, approved, pull
from test_approvals import in_project

URL = "https://github.com/o/r/actions/runs/9/job/1"


def checks(conclusion: str) -> dict[str, dict[str, str]]:
    return {
        "test": {"conclusion": conclusion, "url": URL},
        "loop:approvals": {"conclusion": "FAILURE", "url": "x"},
    }


@pytest.fixture(autouse=True)
def forge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda base: {"test", "loop:approvals"})
    # the run published its failed test ids unless a test says otherwise
    monkeypatch.setattr(approvals, "run_artifact", lambda run, name: {"failed": ["t::x"]})


def test_a_red_latest_push_run_is_named_with_its_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("FAILURE"))
    advice, refusals = approvals.red_base("main")
    assert refusals == [] and len(advice) == 1
    assert "main is red" in advice[0] and "`test`" in advice[0] and "actions/runs/9" in advice[0]


def test_a_green_latest_push_run_says_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("SUCCESS"))
    assert approvals.red_base("main") == ([], [])


def test_a_run_that_failed_before_any_test_ran_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("FAILURE"))
    monkeypatch.setattr(approvals, "run_artifact", lambda run, name: None)
    advice, refusals = approvals.red_base("main")
    assert advice == [] and "before any test ran" in refusals[0]


def test_an_unreadable_forge_is_said_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(ref: str) -> dict[str, dict[str, str]]:
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(approvals, "commit_checks", down)
    advice, refusals = approvals.red_base("main")
    assert refusals == [] and "could not be read" in advice[0]


def merge_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "required_checks", lambda base: set())
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, LOOP))
    pr = pull(reviews=(VERDICT,), checks=(), files=("app.py",))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)


def test_check_merge_prints_a_red_base_and_still_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    merge_ready(monkeypatch)
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("FAILURE"))
    assert approvals.main(["check", "merge", "7"]) == 0
    assert "main is red" in capsys.readouterr().out


def test_check_merge_refuses_a_base_that_failed_before_any_test(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    merge_ready(monkeypatch)
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("FAILURE"))
    monkeypatch.setattr(approvals, "run_artifact", lambda run, name: None)
    assert approvals.main(["check", "merge", "7"]) == 1
    assert "before any test ran" in capsys.readouterr().out


def test_land_prints_a_red_base_and_refuses_one_that_failed_before_any_test(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(approvals, "commit_checks", lambda ref: checks("FAILURE"))

    def stop(*_a: object, **_k: object) -> None:
        raise RuntimeError("past the red-base read")

    monkeypatch.setattr(approvals, "held_by", stop)
    with pytest.raises(RuntimeError, match="past the red-base read"):
        approvals.landing_here([], "main", 0, TRACKER, LOOP, rules={"test"}, ready=False)
    assert "main is red" in capsys.readouterr().out
    monkeypatch.setattr(approvals, "run_artifact", lambda run, name: None)
    with pytest.raises(approvals.Refused, match="before any test ran"):
        approvals.landing_here([], "main", 0, TRACKER, LOOP, rules={"test"}, ready=False)
