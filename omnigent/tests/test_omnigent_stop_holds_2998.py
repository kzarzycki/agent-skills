"""A stop order puts `loop:hold` on every PR the stopped sessions own, before the message goes out (#2998): the label,
not the message, is what a lead mid-turn is refused on."""

import pytest
from test_omnigent_pr_stall import omnigent_agent


class Og:
    def info(self, sid):
        if sid == "bad":
            raise RuntimeError("gone")
        return {"labels": {"omni.pr": "o/r#12,o/r#13"}} if sid == "lead" else {"labels": {}}


def test_hold_prs_labels_each_owned_pr_and_says_a_session_that_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(omnigent_agent, "gh", lambda *a, **k: calls.append(a) or "")
    lines = omnigent_agent.hold_prs(Og(), [("lead", "L"), ("bad", "B"), ("none", "N")])
    assert [c[1] for c in calls] == ["repos/o/r/issues/12/labels", "repos/o/r/issues/13/labels"]
    assert all("labels[]=loop:hold" in c for c in calls)
    assert lines[0] == "o/r#12: held (loop:hold) for session lead"
    assert any(line.startswith("session bad: no PR held") for line in lines)
