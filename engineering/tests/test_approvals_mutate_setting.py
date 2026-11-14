"""approvals.py: the policy's `mutate.inconclusive_exit`, the exit code mutate.py reads as "setup failed" (#951)."""

from __future__ import annotations

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    gatekeeper_md,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)


def test_inconclusive_exit_is_a_whole_number_of_the_mutate_section() -> None:
    policy = approvals.Policy(gatekeeper_md("mutate:\n  inconclusive_exit: 66\n"))
    assert approvals.settings(policy) == {"mutate": {"inconclusive_exit": 66}}


def test_an_inconclusive_exit_that_is_not_a_whole_number_is_refused_naming_the_key() -> None:
    policy = approvals.Policy(gatekeeper_md("mutate:\n  inconclusive_exit: busy\n"))
    with pytest.raises(approvals.Refused, match="inconclusive_exit"):
        approvals.settings(policy)
