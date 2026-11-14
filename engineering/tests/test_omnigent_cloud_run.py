"""A cloud session's run must finish inside its turn (#1002): its VM may not outlive the turn."""

import pytest
from test_omnigent_agent import (
    CLOUD_RECORD,
    CloudFake,
    Lead,
    ending,
    following,
    omnigent_agent,
    skewed,
    supervised,
    told,
)

DETACH_LINE = "A long or locked run is detached"
IN_TURN = "A run must finish inside the turn that started it"


@pytest.mark.parametrize(("top_level", "pr"), [(True, None), (False, None)])
def test_a_cloud_brief_carries_the_in_turn_rule_and_not_the_detach_line(
    tmp_path, monkeypatch, top_level, pr
) -> None:
    monkeypatch.delenv("LOOP_DENY_LIST", raising=False)
    og = CloudFake()
    sid, _ = omnigent_agent.start(
        og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0, top_level=top_level, pr=pr
    )
    brief = omnigent_agent.text_of(og.sessions[sid][1])
    assert IN_TURN in brief and "never ending the turn while the run lives" in brief
    assert "loop on `omnigent_agent.py wait-for --log <log> --pid <pid>`" in brief
    assert "`still running` (exit 6)" in brief and "never with a plain `sleep`" in brief
    assert "Monitor" not in brief and "in the foreground" not in brief
    assert "`STILL WORKING` that names only your own background run is not a valid ending" in brief
    assert DETACH_LINE not in brief


def test_the_pr_cloud_preamble_carries_the_in_turn_rule() -> None:
    brief = omnigent_agent.cloud_preamble(omnigent_agent.PR_PREAMBLE, 7)
    assert IN_TURN in brief and DETACH_LINE not in brief


@pytest.mark.parametrize("preamble", ["PREAMBLE", "PR_PREAMBLE", "LEAD_PREAMBLE"])
def test_a_host_brief_keeps_the_detach_line(preamble: str) -> None:
    text = getattr(omnigent_agent, preamble)
    assert DETACH_LINE in text and IN_TURN not in text
    assert omnigent_agent.DETACH_LINE in text  # the line a cloud brief replaces


def test_the_cloud_nudges_name_the_restart_and_the_host_nudge_keeps_polling() -> None:
    for nudge in (omnigent_agent.CLOUD_NUDGE, omnigent_agent.PR_NUDGE, omnigent_agent.HELD_NUDGE):
        assert "restart it" in nudge and "detached" not in nudge
    assert "Poll any long run you started detached" in omnigent_agent.NUDGE


def test_the_supervisor_nudge_of_a_cloud_lead_names_the_restart(tmp_path, monkeypatch) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    monkeypatch.setattr(omnigent_agent, "triage", lambda event, decisions: ("act", "stalled"))
    og = Lead(told("brief", 60), ending("STILL WORKING: waiting on my background run", 0))
    og.snap = dict(CLOUD_RECORD)
    og.harnesses = {"claude-cloud": omnigent_agent.CLOUD_HARNESS}
    at = {1: 301.0, 2: 302.0}
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda p: offset.__setitem__(0, at[p]),
        notify="cos",
        console=True,
    )
    assert [t for s, t in og.inbox if s == "a"] == [omnigent_agent.LEAD_NUDGE_CLOUD]
    assert "restart it" in omnigent_agent.LEAD_NUDGE_CLOUD
