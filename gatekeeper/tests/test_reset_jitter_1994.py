"""A land --wait that waited on a rate-limit reset resumes up to a few minutes after it, at random, so the lands that
waited on one reset do not all spend the fresh bucket in its first second (#1994)."""

from approvals_harness import approvals

github = approvals.github


def test_a_reset_wait_spreads_over_minutes() -> None:
    assert (
        github.JITTER >= 120
    )  # the quota guard's and gh()'s reset waits both add up to JITTER random seconds
