"""approvals.py: a setting or section this pack doesn't know warns and the run goes on (#2475), where a near match
to a known key, or a wrong type, is still refused. A repo's main may set a key only a newer pack knows, and every
branch still on an older pack would otherwise refuse every command until it merged main."""

from __future__ import annotations

import pytest
from approvals_harness import approvals, loop_md
from test_approvals import gatekeeper_md


@pytest.fixture(autouse=True)
def fresh() -> None:
    """No line said yet this run: each is said once per run."""
    approvals.DEPRECATED.clear()


FAR = "levels:\n  high:\n    merge: go\n    approve_by_vote: true\n"


def parsed(settings: str) -> dict[str, object]:
    return approvals.settings(loop_md(settings))


def test_an_unknown_key_far_from_every_known_one_warns_once_and_is_left_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parsed("loop:\n  cap: 3\n  burst_budget: 9\n") == parsed("loop:\n  cap: 3\n")
    first = capsys.readouterr().err
    assert first.count("\n") == 1 and first.startswith(
        "loop.md sets `loop.burst_budget`, which this gatekeeper ("
    )
    assert approvals.pack_version() in first
    assert first.endswith("doesn't know: this repo's policy needs a newer pack; merge main\n") or (
        "): this repo's policy needs a newer pack; merge main" in first
    )
    parsed("loop:\n  cap: 3\n  burst_budget: 9\n")
    assert capsys.readouterr().err == ""  # said once per run


def test_a_command_goes_on_as_without_the_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert approvals.levels(loop_md(FAR)) == approvals.levels(
        loop_md("levels:\n  high:\n    merge: go\n")
    )
    assert "`levels.high.approve_by_vote`" in capsys.readouterr().err


def test_a_key_one_edit_from_a_known_key_is_refused_naming_it() -> None:
    with pytest.raises(approvals.Refused) as refused:
        parsed("levels:\n  high:\n    rerunn: true\n")
    assert "`levels.high.rerunn`" in str(refused.value) and "`rerun`" in str(refused.value)


def test_an_unknown_section_warns_the_same_way_and_a_misspelt_one_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert parsed("loop:\n  cap: 3\nfeature_flags:\n  a: 1\n") == parsed("loop:\n  cap: 3\n")
    err = capsys.readouterr().err
    assert "sets `feature_flags`, which this gatekeeper (" in err
    with pytest.raises(approvals.Refused, match="did you mean `levels`"):
        parsed("level:\n  high:\n    merge: go\n")


def test_a_wrong_type_on_a_known_key_is_still_refused() -> None:
    with pytest.raises(approvals.Refused, match="must be a whole number"):
        parsed("loop:\n  cap: three\n  burst_budget: 9\n")


def test_an_unknown_key_under_levels_warns_and_the_command_goes_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Under `levels` too (the case reported): the older pack runs its own rules for the key it doesn't know."""
    same = approvals.levels(loop_md("levels:\n  high:\n    merge: go\n"))["high"]
    assert approvals.levels(loop_md(FAR))["high"] == same
    assert "`levels.high.approve_by_vote`" in capsys.readouterr().err
    approvals.settings(approvals.Policy(gatekeeper_md(FAR)))
