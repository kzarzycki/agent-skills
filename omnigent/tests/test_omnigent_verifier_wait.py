"""A lead that ends waiting on a verifier nothing started goes to its manager (#2618).

The seam: the supervisor over a faked fleet (``test_omnigent_queue_rejects.fleet``): lead ``a`` followed in the
registry whose last turn waits on the verifier of PR o/r#12, and the other sessions listed with their labels."""

from pathlib import Path

import pytest
from test_omnigent_agent import ending, omnigent_agent, skewed, told
from test_omnigent_queue_rejects import GitHub, acts, fleet, run

WAIT = "STILL WORKING: waiting on the verifier for #12 (head abc1234, gated)."
LABELS = {"omni.pr": "o/r#12", "omni.role": "lead"}


def waiting(tmp_path: Path, offset: list[float], text: str = WAIT, **sessions: dict):
    """The lead ended its turn on ``text``; the clock (``offset``) passes the turn-end hold as the polls go on."""
    registry, og = fleet(tmp_path, **sessions)
    og.histories["a"] = [told("brief", 60), ending(text, 1)]
    og.snaps["a"] = {"labels": LABELS}
    return registry, og, lambda p: offset.__setitem__(0, 40.0 * p)


def test_a_verifier_wait_with_no_verifier_running_goes_to_the_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, og, end = waiting(tmp_path, skewed(monkeypatch))
    GitHub(monkeypatch)
    run(og, registry, monkeypatch, 3, end)
    [post] = acts(og, "no verifier running")
    assert "lead gated #12 abc1234, no verifier running: start one" in post


@pytest.mark.parametrize(
    "verifier",
    [
        {"labels": {"omni.pr": "o/r#12", "omni.role": "verifier"}, "status": "running"},
        # the registry records no head for a verifier: one on an older head holds the wait too
        {"labels": {"omni.pr": "o/r#11,o/r#12", "omni.role": "verifier"}, "status": "running"},
    ],
)
def test_a_verifier_wait_with_a_running_verifier_on_the_pr_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verifier: dict
) -> None:
    registry, og, end = waiting(tmp_path, skewed(monkeypatch), v=verifier)
    GitHub(monkeypatch)
    run(og, registry, monkeypatch, 3, end)
    assert not acts(og, "no verifier running")


@pytest.mark.parametrize(
    "verifier",
    [
        {
            "labels": {"omni.pr": "o/r#13", "omni.role": "verifier"},
            "status": "running",
        },  # another PR
        {"labels": {"omni.pr": "o/r#12", "omni.role": "verifier"}, "status": "idle"},  # finished
        {
            "labels": {"omni.pr": "o/r#12", "omni.role": "verifier"},
            "status": "running",
            "archived": True,
        },
        {
            "labels": {"omni.pr": "o/r#12", "omni.role": "worker"},
            "status": "running",
        },  # no verifier
    ],
)
def test_a_session_that_is_no_running_verifier_of_the_pr_holds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verifier: dict
) -> None:
    registry, og, end = waiting(tmp_path, skewed(monkeypatch), v=verifier)
    GitHub(monkeypatch)
    run(og, registry, monkeypatch, 3, end)
    assert acts(og, "no verifier running")


def test_a_wait_that_names_no_pr_is_held_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, og, end = waiting(
        tmp_path, skewed(monkeypatch), "STILL WORKING: waiting on the verifier."
    )
    GitHub(monkeypatch)
    run(og, registry, monkeypatch, 3, end)
    assert not acts(og, "no verifier running")


def test_verifier_wait_reads_the_pr_and_head_of_the_turn_s_own_wait() -> None:
    assert omnigent_agent.verifier_wait(WAIT) == ("", 12, "abc1234")
    assert omnigent_agent.verifier_wait(
        "STILL WORKING: verifier for o/r#7 on 0123456789abcdef"
    ) == (
        "o/r",
        7,
        "0123456789abcdef",
    )
    assert omnigent_agent.verifier_wait("> STILL WORKING: waiting on #3\nDONE") == ("", 0, "")
