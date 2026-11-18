"""The supervisor reads loop events (#1377): a beating wait is live, a silent one raises its deadline, an end is told once.

The seam is `supervise_registry` with the fake fleet of test_omnigent_agent and a real bare remote holding
`refs/loop/*`, written by engineering-loop's events.py."""

import json
import subprocess
from pathlib import Path

import pytest
from test_omnigent_agent import (
    Lead,
    ending,
    events_of,
    following,
    omnigent_agent,
    posted,
    skewed,
    supervised,
    told,
)

EVENTS = omnigent_agent._load_events()
WAIT = "STILL WORKING: waiting on #12"
GREEN = (
    0,
    "PR #12 checks green (1)",
    "s1",
)  # its checks are in: only a required check can keep it live


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone of a temporary bare remote, the supervisor's working directory; PRs 12 and 13 sit on `feat` and `feat2`."""
    bare, work = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(tmp_path, "clone", "-q", str(bare), str(work))
    monkeypatch.chdir(work)
    monkeypatch.setattr(omnigent_agent, "EVENT_SECONDS", 0.0)
    branches = {12: "feat", 13: "feat2"}
    monkeypatch.setattr(
        omnigent_agent,
        "pr_info",
        lambda pr, repo="": {"state": "open", "branch": branches[pr], "sha": "s1", "base": "main"},
    )
    monkeypatch.setattr(omnigent_agent, "pr_settled", lambda pr, repo="": GREEN)
    monkeypatch.setattr(omnigent_agent, "required_pending", lambda info, repo="": False)
    return work


def deadlines(registry: Path) -> list[str]:
    log = registry.with_suffix(".events.jsonl")
    return [
        e["line"] for e in (events_of(registry) if log.exists() else []) if e["kind"] == "deadline"
    ]


def wait_run(where: Path, monkeypatch: pytest.MonkeyPatch, skew: float) -> list[str]:
    """One lead waiting on PR 12, quiet for 25 minutes, polled once `skew` seconds after the events were written."""
    where.mkdir(exist_ok=True)
    registry = following(where)
    offset = skewed(monkeypatch)
    offset[0] = skew
    og = Lead(told("brief", 4000), ending(WAIT, 1500))
    og.snap = {"status": "running"}
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True, fyi="post")
    return deadlines(registry)


def test_beating_wait_raises_no_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: Path
) -> None:
    assert (
        len(wait_run(tmp_path / "ref", monkeypatch, 60.0)) == 1
    )  # the same history without events
    EVENTS.emit("land", "feat", "waiting", cwd=clone)
    # rewritten a minute ago: twice a 300 s beat is 600 s
    assert wait_run(tmp_path / "beat", monkeypatch, 60.0) == []


def test_silent_wait_raises_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: Path
) -> None:
    EVENTS.emit("land", "feat", "waiting", cwd=clone)
    lines = wait_run(tmp_path, monkeypatch, 900.0)  # unchanged for 15 minutes
    assert len(lines) == 1 and "land event silent 15m" in lines[0]


@pytest.mark.parametrize(("pending", "deadline"), [(True, 0), (False, 1)])
def test_pending_required_check_is_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: Path, pending: bool, deadline: int
) -> None:
    monkeypatch.setattr(omnigent_agent, "required_pending", lambda info, repo="": pending)
    assert len(wait_run(tmp_path, monkeypatch, 0.0)) == deadline


def test_required_pending_reads_the_rules_and_the_heads_check_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = {
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": "gate"}]},
    }
    runs = {
        "check_runs": [
            {"name": "gate", "status": "queued"},
            {"name": "lint", "status": "completed"},
        ]
    }
    answers = {"rules/branches/main": [rule], "commits/s1/check-runs": runs}
    monkeypatch.setattr(
        omnigent_agent,
        "gh",
        lambda *args, **kw: json.dumps(next(v for k, v in answers.items() if args[-1].endswith(k))),
    )
    info = {"state": "open", "sha": "s1", "base": "main"}
    assert omnigent_agent.required_pending(info, "o/r") is True
    runs["check_runs"][0]["status"] = "completed"
    assert omnigent_agent.required_pending(info, "o/r") is False
    runs["check_runs"][0]["status"] = "queued"
    assert omnigent_agent.required_pending({**info, "state": "closed"}, "o/r") is False


def test_owner_question_sorts_before_news(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: Path
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending(WAIT, 30))
    og.snap = {
        "status": "idle",
        "labels": {omnigent_agent.PR_LABEL: "o/r#13"},
    }  # its own PR: branch feat2
    question = "May the gate be skipped?\nThe whole text.\n"

    def write(poll: int) -> None:
        for kind, branch, state in [
            ("land", "feat", "ok"),
            ("gate", "feat", "failed"),
            ("verifier", "feat", "ok"),
            ("land", "feat2", "ok"),
            ("gate", "feat2", "failed"),
        ]:
            EVENTS.emit(kind, branch, "waiting", cwd=clone)
            EVENTS.emit(kind, branch, state, cwd=clone)  # a beat before the end: one news per ref
        EVENTS.emit("lead", "feat", "needs-owner", question=question, cwd=clone)

    supervised(og, registry, monkeypatch, 3, write, notify="cos", console=True, fyi="post")
    told_ = [
        e
        for e in events_of(registry)
        if e["kind"] in ("loop-owner", "news") and " on feat" in e["line"]
    ]
    assert [e["kind"] for e in told_] == ["loop-owner"] + ["news"] * 5
    assert "needs the owner: May the gate be skipped?" in told_[0]["line"]
    assert [e["line"].split(": ", 1)[1].split(" on ")[0] for e in told_[1:]] == [
        "gate failed",
        "gate failed",
        "land ok",
        "land ok",
        "verifier ok",
    ]


def test_unchanged_poll_is_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: Path
) -> None:
    EVENTS.emit(
        "land", "feat", "ok", cwd=clone
    )  # ended before this supervisor started: recorded, not news
    EVENTS.emit("gate", "feat", "waiting", cwd=clone)
    registry = following(tmp_path)
    skewed(monkeypatch)[0] = 100.0
    og = Lead(told("brief", 60), ending(WAIT, 30))
    og.snap = {"status": "idle"}
    supervised(og, registry, monkeypatch, 4, notify="cos", console=True, fyi="post")
    log = registry.with_suffix(".events.jsonl")
    assert not [e for e in (events_of(registry) if log.exists() else []) if " on feat" in e["line"]]
    assert not [t for t in posted(og) if " on feat" in t]


def test_an_unreadable_poll_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: Path
) -> None:
    monkeypatch.setattr(omnigent_agent, "read_loop_events", lambda cwd=None: None)
    assert len(wait_run(tmp_path, monkeypatch, 0.0)) == 1  # no events known: today's deadline
