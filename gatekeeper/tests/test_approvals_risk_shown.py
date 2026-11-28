"""approvals.py: the risk `check merge` prints follows the PR's `risk:*` label and the verifier's `Risk:` word, and a
merged PR's closed issue is no "closes no open issue" (#2876)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    LOOP,
    TRACKER,
    approvals,
    approved,
    gating,  # noqa: F401
    judged_pr,
    judging,
    pull,
)
from test_approvals_risk_levels import check_merge, lands, policy  # noqa: F401

Gate = tuple[dict[str, Any], list[tuple[int, str]]]


def test_a_medium_label_and_a_medium_verdict_print_medium_not_low(
    gating: Gate, capsys: pytest.CaptureFixture[str]
) -> None:
    state, _ = gating
    policy(
        "spec:\n  auto:\n    - bug\n"
    )  # no `risk: verifier` term: no rule rates the change above low
    state["pull"] = judged_pr(judging("medium — unsure"), labels=("risk:medium",))
    _, _, err = check_merge(capsys)
    line = "\n".join(each for each in err if each.startswith("PR #7:"))
    assert line.startswith("PR #7: risk: medium (") and "risk: low" not in line
    assert "PR label `risk:medium`" in line and "verifier `Risk: medium`" in line


def test_a_label_and_a_verdict_that_disagree_are_both_named(
    gating: Gate, capsys: pytest.CaptureFixture[str]
) -> None:
    state, _ = gating
    policy("spec:\n  auto:\n    - bug\n")
    state["pull"] = judged_pr(judging("high — wide"), labels=("risk:medium",))
    _, _, err = check_merge(capsys)
    line = "\n".join(each for each in err if each.startswith("PR #7:"))
    assert (
        "disagree" in line and "PR label `risk:medium`" in line and "verifier `Risk: high`" in line
    )


def test_a_pr_with_no_stated_risk_still_prints_low(
    gating: Gate, capsys: pytest.CaptureFixture[str]
) -> None:
    state, _ = gating
    policy("spec:\n  auto:\n    - bug\n")
    state["pull"] = judged_pr(judging("low — fine"))
    _, _, err = check_merge(capsys)
    assert "PR #7: risk: low; merge: gates" in err


def merged(state: str) -> dict[str, Any]:
    found = approved(1, "kind:bug")
    found["state"] = "CLOSED"
    pr = {**pull(body="Closes #1"), "state": state}
    pr["closingIssuesReferences"]["nodes"] = [found]
    return pr


def test_a_merged_prs_issue_closed_by_the_merge_is_no_finding() -> None:
    pr = merged("MERGED")
    assert approvals.closes_nothing(pr, pr["closingIssuesReferences"]["nodes"], LOOP) == []
    found, _ = approvals.gated("merge", pr, TRACKER, LOOP)
    assert not [line for line in found if "closes no open issue" in line]


def test_an_open_prs_closed_issue_is_still_refused() -> None:
    pr = merged("OPEN")
    assert approvals.closes_nothing(pr, pr["closingIssuesReferences"]["nodes"], LOOP)


def stated_line(
    gating: Gate, capsys: pytest.CaptureFixture[str], verdict: str, label: str, settings: str
) -> str:
    state, _ = gating
    policy(settings)
    state["pull"] = judged_pr(judging(verdict), labels=(label,))
    _, _, err = check_merge(capsys)
    return "\n".join(each for each in err if each.startswith("PR #7:"))


VERIFIER = "risk:\n  verifier: true\n"


def test_a_high_gate_rating_still_shows_the_stated_medium(
    gating: Gate, capsys: pytest.CaptureFixture[str]
) -> None:
    """With `risk.verifier` a medium verdict makes the gate rate the change high; the line keeps that rating and the
    merge action, and shows what the label and the verdict say beside it."""
    line = stated_line(gating, capsys, "medium — unsure", "risk:medium", VERIFIER)
    assert line.startswith("PR #7: risk: high (") and "; merge: go" in line
    assert "PR label `risk:medium`" in line and "verifier `Risk: medium`" in line


def test_a_high_gate_rating_names_a_label_and_verdict_that_disagree(
    gating: Gate, capsys: pytest.CaptureFixture[str]
) -> None:
    line = stated_line(gating, capsys, "high — wide", "risk:medium", VERIFIER)
    assert line.startswith("PR #7: risk: high (") and "disagree" in line
    assert "PR label `risk:medium`" in line and "verifier `Risk: high`" in line


def test_check_merge_on_a_merged_pr_says_nothing_of_a_closed_issue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command a lead runs after the merge: the PR is MERGED and GitHub closed its `Closes #n` issue."""
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, LOOP))
    pr = merged("MERGED")
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(
        approvals, "issues_of", lambda numbers: [pr["closingIssuesReferences"]["nodes"][0]]
    )
    approvals.main(["check", "merge", "7"])
    assert "closes no open issue" not in capsys.readouterr().out


def test_a_high_label_and_a_low_verdict_are_both_shown_beside_the_gate_rating(
    gating: Gate, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rating line stays as it was; the disagreement is a line of its own."""
    line = stated_line(gating, capsys, "low — fine", "risk:high", VERIFIER)
    first, second = line.splitlines()
    assert first == "PR #7: risk: high (`risk:high` is on PR #7); merge: go"
    assert (
        "disagree" in second
        and "PR label `risk:high`" in second
        and "verifier `Risk: low`" in second
    )


def test_land_wait_reads_a_pr_that_merged_after_the_listing(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bare `land --wait`: `open_pulls()` lists PR 7 open, then it merges and GitHub closes its `Closes #n` issue
    before `candidates_of()` reads it by number and judges it (landable, proof_gaps, gated, closes_nothing)."""
    lands["open"](7, {"7.txt": "7\n"})
    real = approvals.open_pulls

    def listed() -> list[dict[str, Any]]:
        found = real()
        pr = lands["pulls"][7]
        pr["state"] = "MERGED"
        for each in pr["closingIssuesReferences"]["nodes"]:
            each["state"] = "CLOSED"
        return found

    monkeypatch.setattr(approvals, "open_pulls", listed)
    _, lines = lands["land"]("--wait")
    assert not [line for line in lines if "closes no open issue" in line], lines
