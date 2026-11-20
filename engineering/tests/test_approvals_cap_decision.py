"""approvals.py: at the pass cap the lead decides, recorded as a `Cap: #<follow-up>` line in the PR body (#1517)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import BARE, HEAD, LOOP, approvals, approved, pull, verdict_on

CAP = approvals.cap(LOOP)
DECIDED = "## Evidence\n\nlog line\n\nCap: #99\n"
UNSATISFIED = f"PR #7: a verifier review on {HEAD} is not satisfied: fix and verify again"


def at(number: int, counts: str) -> dict[str, Any]:
    return verdict_on(HEAD, counts, satisfied="no", heading=f"Verifier (claude), pass {number}")


def verified(review: dict[str, Any], body: str) -> list[str]:
    pr = pull(reviews=(review,), files=("app.py",), body=body)
    return approvals.proofs("merge", pr, [approved(1, "area:web")], LOOP)


def test_majors_open_at_the_cap_land_once_the_lead_records_its_decision_with_no_go() -> None:
    majors = at(CAP, "0 blocker, 1 major, 0 minor")
    assert verified(majors, "## Evidence\n\nlog line\n") == [
        UNSATISFIED,
        f"PR #7: the verifier reviews on {HEAD} have 0 blocker and 1 major open: fix and verify again",
    ]
    assert verified(majors, DECIDED) == []
    # the cap adds no risk, so a change otherwise low risk waits for no go
    assert (
        approvals.owner_waits(pull(reviews=(majors,), files=("app.py",), body=DECIDED), [], BARE)
        == []
    )


@pytest.mark.parametrize(
    ("review", "body"),
    [
        (
            at(CAP, "1 blocker, 1 major, 0 minor"),
            DECIDED,
        ),  # a blocker means the change is wrong as it stands
        (
            at(CAP - 1, "0 blocker, 1 major, 0 minor"),
            DECIDED,
        ),  # before the cap the loop fixes and verifies again
        # a quoted line is an example, not the record
        (at(CAP, "0 blocker, 1 major, 0 minor"), "```\nCap: #99\n```\n"),
        (at(CAP, "0 blocker, 1 major, 0 minor"), "~~~\nCap: #99\n~~~\n"),
        (at(CAP, "0 blocker, 1 major, 0 minor"), "`Cap: #99`\n"),
        (at(CAP, "0 blocker, 1 major, 0 minor"), "> Cap: #99\n"),
        (at(CAP, "0 blocker, 1 major, 0 minor"), "    Cap: #99\n"),  # an indented code block
        # a longer fence around a fenced example closes only on its own length
        (at(CAP, "0 blocker, 1 major, 0 minor"), "````\n```\nCap: #99\n```\n````\n"),
        (
            at(CAP, "0 blocker, 1 major, 0 minor"),
            "```\nCap: #99\n",
        ),  # an unclosed block runs to the end
    ],
)
def test_the_cap_decision_never_lands_a_blocker_an_early_pass_or_a_quoted_line(
    review: dict[str, Any], body: str
) -> None:
    assert UNSATISFIED in verified(review, body)
