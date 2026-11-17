"""approvals.py: a verifier's newest review in a pass replaces its earlier ones there (#1257)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    HEAD,
    LOOP,
    added,  # noqa: F401
    approvals,
    approved,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    others_open,  # noqa: F401
    pull,
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
    verdict_on,
)

UNSATISFIED = f"PR #7: a verifier review on {HEAD} is not satisfied: fix and verify again"


def review(family: str, satisfied: str) -> dict[str, Any]:
    counts = "0 blocker, 0 major, 0 minor"
    return verdict_on(HEAD, counts, satisfied=satisfied, heading=f"Verifier ({family}), pass 2")


def verified(*reviews: dict[str, Any]) -> list[str]:
    return approvals.proofs("merge", pull(reviews=reviews), [approved(1, "area:web")], LOOP)


@pytest.mark.parametrize(
    ("reviews", "lines"),
    [
        # one family: the verdict written after its question was answered stands, whichever effort it names
        (
            [
                review("cc/opus-5.5/med, same-family", "no"),
                review("cc/opus-5.5/?, same-family", "yes"),
            ],
            [],
        ),
        ([review("claude", "no"), review("cc/sonnet/?", "yes")], []),
        ([review("claude", "yes"), review("claude", "no")], [UNSATISFIED]),
        # two families: each one's newest counts, and both must be satisfied
        (
            [review("claude", "no"), review("codex/terra-6.1/med", "yes"), review("claude", "yes")],
            [],
        ),
        (
            [review("claude", "yes"), review("codex/terra-6.1/med", "yes"), review("codex", "no")],
            [UNSATISFIED],
        ),
    ],
)
def test_each_familys_newest_review_in_the_pass_counts(
    reviews: list[dict[str, Any]], lines: list[str]
) -> None:
    assert verified(*reviews) == lines


def test_a_pass_at_the_cap_that_turned_satisfied_is_not_capped() -> None:
    reviews = (review("claude", "no"), review("claude", "yes"))
    assert not approvals.capped(pull(reviews=reviews), 2)
    assert approvals.capped(pull(reviews=reviews[::-1]), 2)
    # a later review on another commit replaces nothing: the older commit's unsatisfied pass at the cap stays
    older = verdict_on("c" * 40, satisfied="no", heading="Verifier (claude), pass 2")
    assert approvals.capped(pull(reviews=(older, review("claude", "yes"))), 2)
    # nor does a later pass on the same commit: its pass 2 stays unsatisfied at the cap
    later = verdict_on(HEAD, satisfied="yes", heading="Verifier (claude), pass 3")
    assert approvals.capped(pull(reviews=(review("claude", "no"), later)), 2)
