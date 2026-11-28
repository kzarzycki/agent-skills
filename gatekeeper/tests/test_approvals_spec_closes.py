"""approvals.py: a spec approval newer than a not-satisfied verdict, naming its findings, lands without a new pass (#2992)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    AS_WRITTEN,
    HEAD,
    LOOP,
    approvals,
    issue,
    note,
    pull,
    record,
    verdict_on,
)

POSTED = "2026-10-02T09:00:00Z"
LATER = "2026-10-03T09:00:00Z"
EARLIER = "2026-10-01T10:00:00Z"
UNSATISFIED = f"PR #7: a verifier review on {HEAD} is not satisfied: fix and verify again"
NAMES_F1 = f"F1 of the pass-1 verdict on {HEAD}"


def verdict(*findings: str, counts: str = "0 blocker, 1 major, 0 minor") -> dict[str, Any]:
    """A pass-1 review that is not satisfied, with one finding heading per id."""
    review = verdict_on(HEAD, counts, satisfied="no")
    headings = "".join(
        f"### {name} (major) a.py:1: the spec lacks a line\n\nbody\n\n" for name in findings
    )
    review["submittedAt"] = POSTED
    review["body"] = review["body"].replace("\n\nVERDICT", f"\n\n{headings}VERDICT", 1)
    return review


def spec(closes: str | None, at: str = LATER, text: str = AS_WRITTEN) -> Any:
    """The linked issue, its spec approved by the owner with a record at `at` that closes `closes`."""
    extra = {"closes": closes} if closes else {}
    body = record("spec", "owner", spec=text, **extra)
    return issue(1, "area:web", "size:S", "approved:spec", comments=(note(body, createdAt=at),))


def lines(review: dict[str, Any], linked: Any) -> list[str]:
    return approvals.proofs("merge", pull(reviews=(review,)), [linked], LOOP)


def test_a_newer_spec_approval_naming_the_only_finding_lands_the_head_without_a_new_pass(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lines(verdict("F1"), spec(NAMES_F1)) == []
    said = capsys.readouterr().out
    assert f"F1 of the pass-1 verdict on {HEAD} is closed by owner's spec approval on #1" in said
    assert LATER in said


@pytest.mark.parametrize(
    ("review", "linked"),
    [
        # recorded before the verdict
        (verdict("F1"), spec(NAMES_F1, at=EARLIER)),
        # names no finding
        (verdict("F1"), spec(None)),
        (verdict("F1"), spec("the line was missing")),
        # names another finding, another pass or another commit
        (verdict("F1"), spec(f"F2 of the pass-1 verdict on {HEAD}")),
        (verdict("F1"), spec(f"F1 of the pass-2 verdict on {HEAD}")),
        (verdict("F1"), spec("F1 of the pass-1 verdict on " + "b" * 40)),
        # a second finding stays open
        (verdict("F1", "F2", counts="0 blocker, 2 major, 0 minor"), spec(NAMES_F1)),
        # a record of an older spec text
        (verdict("F1"), spec(NAMES_F1, text="as written 2026-09-01 09:00:00 UTC")),
        # a verdict whose headings do not add up to its counts
        (verdict("F1", counts="0 blocker, 2 major, 0 minor"), spec(NAMES_F1)),
    ],
)
def test_an_approval_that_does_not_close_every_finding_still_blocks(
    review: dict[str, Any], linked: Any
) -> None:
    assert UNSATISFIED in lines(review, linked)


def test_two_findings_closed_by_one_approval_land() -> None:
    both = f"F1, F2 of the pass-1 verdict on {HEAD}"
    assert lines(verdict("F1", "F2", counts="0 blocker, 2 major, 0 minor"), spec(both)) == []


def test_a_verdict_naming_a_run_never_made_stays_open() -> None:
    review = verdict("F1")
    review["body"] += "Not run: the e2e\n"
    assert UNSATISFIED in lines(review, spec(NAMES_F1))
