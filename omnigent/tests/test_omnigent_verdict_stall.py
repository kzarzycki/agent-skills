"""A followed lead's PR with a verdict and no push or go for over an hour wakes its lead (waste audit, finding 7)."""

import json
import time
from datetime import UTC, datetime

import pytest
from test_omnigent_agent import (
    Lead,
    ending,
    following,
    in_checkout,
    omnigent_agent,
    supervised,
    told,
)

HEAD = "a" * 40


def iso(ago: float) -> str:
    return datetime.fromtimestamp(time.time() - ago, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def report(head: str, word: str) -> str:
    return f"## Verifier report\n\nHead: {head}\nVERDICT: 0 blocker\nSATISFIED: {word}\nRisk: low"


def github(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ago: float = 7200,
    word: str = "no",
    head: str = HEAD,
    state: str = "open",
    labels: tuple[str, ...] = (),
    statuses: tuple[dict, ...] = (),
    as_review: bool = False,
) -> list[tuple[str, ...]]:
    """``gh`` faked for PR o/r#12: its view, one verifier report ``ago`` seconds old naming ``head``, and its head's
    statuses; any other call answers an empty list. Each call is recorded."""
    calls: list[tuple[str, ...]] = []
    said = {"body": report(head, word), "html_url": "https://github.com/o/r/pull/12#x"}

    def gh(*args: str, timeout: float = 0) -> str:
        calls.append(args)
        path = next((a for a in args if a.startswith("repos/")), "")
        if path == "repos/o/r/pulls/12":
            return json.dumps(
                {"state": state, "head": {"sha": HEAD}, "labels": [{"name": n} for n in labels]}
            )
        if path.startswith("repos/o/r/issues/12/comments") and not as_review:
            return json.dumps({**said, "created_at": iso(ago)}) + "\n"
        if path.startswith("repos/o/r/pulls/12/reviews") and as_review:
            return json.dumps({**said, "submitted_at": iso(ago)}) + "\n"
        if path.startswith(f"repos/o/r/commits/{HEAD}/statuses"):
            return "".join(json.dumps(s) + "\n" for s in statuses)
        return ""

    monkeypatch.setattr(omnigent_agent, "gh", gh)
    return calls


@pytest.mark.parametrize("word", ["yes", "no"])
def test_a_verdict_over_an_hour_old_with_no_push_or_go_is_a_stall(monkeypatch, word) -> None:
    github(monkeypatch, word=word)
    head, line = omnigent_agent.verdict_stall(12, "o/r")
    assert head == HEAD and "PR #12" in line and f"SATISFIED: {word}" in line and "120m old" in line
    assert ("the go and `land`" if word == "yes" else "a fix round") in line


def test_a_verdict_posted_as_a_review_counts_too(monkeypatch) -> None:
    github(monkeypatch, as_review=True)
    assert omnigent_agent.verdict_stall(12, "o/r")


@pytest.mark.parametrize(
    "case",
    [
        {"ago": 1800},  # under an hour
        {"head": "b" * 40},  # the head moved since: a push
        {"state": "closed"},
        {"word": "yes", "labels": ("loop:queued",)},  # handed to the queue
        {"word": "yes", "statuses": ({"context": "owner", "state": "success"},)},  # the go
        {"word": "yes", "statuses": ({"context": "land", "state": "success"},)},
    ],
)
def test_no_stall_under_an_hour_after_a_push_a_go_or_a_hand_over(monkeypatch, case) -> None:
    github(monkeypatch, **case)
    assert omnigent_agent.verdict_stall(12, "o/r") is None


def test_an_unsatisfied_verdict_is_a_stall_whatever_go_its_head_holds(monkeypatch) -> None:
    github(monkeypatch, word="no", statuses=({"context": "owner", "state": "success"},))
    assert omnigent_agent.verdict_stall(12, "o/r")


def test_the_supervisor_wakes_the_lead_once_per_stalled_head(tmp_path, monkeypatch) -> None:
    """Through the supervisor: a followed lead idle on its PR's verdict is told, once, in its own session."""
    registry = following(tmp_path)
    og = Lead(told("brief", 9000), ending("STILL WORKING: waiting on CI\nWaits: CI", 8000))
    og.snap = {"labels": {omnigent_agent.PR_LABEL: "o/r#12"}}
    in_checkout(og)
    github(monkeypatch)
    monkeypatch.setattr(omnigent_agent, "VERDICT_STALL_POLL", 0.0)
    supervised(og, registry, monkeypatch, 4, notify="cos", console=True)
    told_lead = [t for s, t in og.inbox if s == "a" and "SATISFIED: no" in t]
    assert len(told_lead) == 1 and "a fix round" in told_lead[0]
