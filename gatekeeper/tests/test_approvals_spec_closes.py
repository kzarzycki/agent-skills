"""approvals.py: a spec approval newer than a not-satisfied verdict, naming its findings, lands without a new pass (#2992)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
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
Posted = Callable[..., dict[str, Any]]


@pytest.fixture
def posted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Posted:
    """A factory of the pass-1 review that is not satisfied, as `verdict` posts it for a report with one finding per id
    (an inline comment, or in the body for a file outside the diff), read back as GitHub returns it."""

    def make(
        *findings: str,
        counts: str = "0 blocker, 1 major, 0 minor",
        inside: bool = True,
        family: str = "claude",
        extra: str = "",
    ) -> dict[str, Any]:
        report = tmp_path / f"{family}.md"
        report.write_text(
            f"Verifier: {family}, pass 1\n\n## Criteria\n\n- c\n\n"
            + "## Correctness\n\n"
            + "".join(
                f"### {name} (major) a.py:1: the spec lacks a line\n\nbody\n\n" for name in findings
            )
            + f"Head: {HEAD}\nVERDICT: {counts}\nSATISFIED: no\n{extra}Risk: low — whole diff\n"
        )
        sent: list[dict[str, Any]] = []
        monkeypatch.setattr(approvals, "diff_lines", lambda *_: {"a.py": [1]} if inside else {})
        monkeypatch.setattr(approvals, "post_review", lambda _pr, review: sent.append(review))
        monkeypatch.setattr(approvals, "pull_request", lambda _n: pull())
        monkeypatch.setattr(approvals, "hand_over", lambda _n: None)
        assert approvals.verdict(7, report) == 0
        return {
            **verdict_on(HEAD, counts, satisfied="no", heading=f"Verifier ({family}), pass 1"),
            "body": sent[0]["body"],
            "comments": {"nodes": [{"body": c["body"]} for c in sent[0]["comments"]]},
            "submittedAt": POSTED,
        }

    return make


def spec(
    closes: str | None, at: str = LATER, text: str = AS_WRITTEN, author: str | None = None
) -> Any:
    """The linked issue, its spec approved by the owner with a record at `at` that closes `closes`."""
    extra = {"closes": closes} if closes else {}
    body = record("spec", "owner", spec=text, **extra)
    fields = {"author": {"login": author}} if author else {}
    return issue(
        1, "area:web", "size:S", "approved:spec", comments=(note(body, createdAt=at, **fields),)
    )


def lines(*reviews: dict[str, Any], linked: Any) -> list[str]:
    return approvals.proofs("merge", pull(reviews=reviews), [linked], LOOP)


@pytest.mark.parametrize("inside", [True, False], ids=["inline comment", "file outside the diff"])
def test_a_newer_spec_approval_naming_the_only_finding_lands_the_head_without_a_new_pass(
    posted: Posted, capsys: pytest.CaptureFixture[str], inside: bool
) -> None:
    """The review is the one `verdict` writes: its findings are inline comments, not headings of the body."""
    assert lines(posted("F1", inside=inside), linked=spec(NAMES_F1)) == []
    said = capsys.readouterr().out
    assert f"F1 of the pass-1 verdict on {HEAD} is closed by owner's spec approval on #1" in said
    assert LATER in said


def test_two_findings_closed_by_one_approval_land(posted: Posted) -> None:
    both = f"F1, F2 of the pass-1 verdict on {HEAD}"
    review = posted("F1", "F2", counts="0 blocker, 2 major, 0 minor")
    assert lines(review, linked=spec(both)) == []


@pytest.mark.parametrize(
    "linked",
    [
        # recorded before the verdict
        spec(NAMES_F1, at=EARLIER),
        # names no finding
        spec(None),
        spec("the line was missing"),
        # names another finding, another pass or another commit
        spec(f"F2 of the pass-1 verdict on {HEAD}"),
        spec(f"F1 of the pass-2 verdict on {HEAD}"),
        spec("F1 of the pass-1 verdict on " + "b" * 40),
        # a record of an older spec text
        spec(NAMES_F1, text="as written 2026-09-01 09:00:00 UTC"),
    ],
)
def test_an_approval_that_does_not_close_the_finding_still_blocks(
    posted: Posted, linked: Any
) -> None:
    assert UNSATISFIED in lines(posted("F1"), linked=linked)


def test_a_second_open_finding_still_blocks(posted: Posted) -> None:
    review = posted("F1", "F2", counts="0 blocker, 2 major, 0 minor")
    assert UNSATISFIED in lines(review, linked=spec(NAMES_F1))


def test_a_verdict_whose_findings_do_not_add_up_to_its_counts_stays_open(posted: Posted) -> None:
    review = posted("F1")  # the writer refuses a mismatch, so the count is edited after the post
    review["body"] = review["body"].replace("1 major", "2 major")
    assert UNSATISFIED in lines(review, linked=spec(NAMES_F1))


def test_a_verdict_naming_a_run_never_made_stays_open(posted: Posted) -> None:
    review = posted("F1", extra="Not run: the e2e\n")
    assert UNSATISFIED in lines(review, linked=spec(NAMES_F1))


def test_a_record_by_an_account_with_no_authority_closes_nothing(posted: Posted) -> None:
    """The `By: owner` line is only what the comment says: its author is whom the gate trusts."""
    assert UNSATISFIED in lines(posted("F1"), linked=spec(NAMES_F1, author="stranger"))


def test_a_finding_id_two_verifiers_of_the_pass_both_used_is_not_closed_by_one_approval(
    posted: Posted,
) -> None:
    claude, codex = posted("F1", family="claude"), posted("F1", family="codex")
    assert UNSATISFIED in lines(claude, codex, linked=spec(NAMES_F1))
