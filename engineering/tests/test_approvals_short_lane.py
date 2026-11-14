"""approvals.py: the policy's `loop.short_seconds`, the host short lane's bound, which mutate.py reads (#978)."""

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


def test_short_seconds_is_a_whole_number_of_the_loop_section() -> None:
    policy = approvals.Policy(gatekeeper_md("loop:\n  short_seconds: 30\n"))
    assert approvals.settings(policy) == {"short_seconds": 30}


def test_short_seconds_that_is_not_a_whole_number_is_refused_naming_the_key() -> None:
    policy = approvals.Policy(gatekeeper_md("loop:\n  short_seconds: fast\n"))
    with pytest.raises(approvals.Refused, match="short_seconds"):
        approvals.settings(policy)
