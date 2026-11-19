"""A verifier pass writes the `verifier` event (events.md) on the branch it reviews: `waiting` from the head's fetch,
beating while it runs, then `ok` or `failed` by the report's `SATISFIED:` line, or `needs-owner` for a question."""

from __future__ import annotations

import json
import subprocess
import time

import pytest
from test_cloud_verifier import checkout, cv  # noqa: F401 - `checkout` is a fixture

REF = "refs/loop/verifier/feat/pr"
REPORT = "# Report\n\nHead: x\nVERDICT: 0 blocker\nSATISFIED: {}\nRisk: low\n"


@pytest.fixture
def events(checkout, monkeypatch):  # noqa: F811 - the imported fixture, used by name
    """`checkout` with every emit recorded as (state, url, question)."""
    work, _, brief, _, seen = checkout
    wrote: list[tuple[str, str, str | None]] = []
    real = cv.EVENTS.emit

    def emit(kind, branch, state, *, url="", question=None, **kw):
        assert (kind, branch) == ("verifier", "feat/pr")
        wrote.append((state, url, question))
        return real(kind, branch, state, url=url, question=question, **kw)

    monkeypatch.setattr(cv.EVENTS, "emit", emit)
    return work, brief, seen, wrote


def on_origin(work, path: str) -> str:
    return subprocess.run(
        ["git", "-C", str(work), "show", f"{REF}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_verifier_pass_events(events) -> None:
    """`ok` for `SATISFIED: yes` and `failed` for `no` or no verdict, with the posted review as `url`."""
    work, brief, seen, wrote = events
    for report, code, end in [(REPORT.format("yes"), 0, "ok"), (REPORT.format("no"), 0, "failed")]:
        wrote.clear()
        seen["report"] = report
        assert cv.verify(7, brief, None, None) == code
        assert [w[0] for w in wrote] == ["waiting", end]
        assert wrote[-1][1] == "https://example.com/comment/1"
        got = json.loads(on_origin(work, "event.json"))
        assert got["state"] == end and got["url"] == wrote[-1][1] and got["beat_s"] == 300
    wrote.clear()
    seen.pop("report"), seen.update(final="no verdict here\n")
    assert cv.verify(7, brief, None, None) == 1
    assert [w[0] for w in wrote] == ["waiting", "failed"]


def test_a_question_is_needs_owner_with_the_whole_question(events) -> None:
    work, brief, seen, wrote = events
    seen["question"] = "Which gate?\nThe full one, or the narrowed?\n"
    assert cv.verify(7, brief, None, None) == 3
    assert [w[0] for w in wrote] == ["waiting", "needs-owner"]
    assert on_origin(work, "question.md") == seen["question"]


def test_the_event_beats_while_the_review_runs(events, monkeypatch) -> None:
    _, brief, seen, wrote = events
    monkeypatch.setitem(cv.EVENTS.BEATS, "verifier", 0.05)
    real = cv.codex_exec

    def slow(cmd, text):
        time.sleep(0.5)
        return real(cmd, text)

    monkeypatch.setattr(cv, "codex_exec", slow)
    seen["report"] = REPORT.format("yes")
    assert cv.verify(7, brief, None, None) == 0
    states = [w[0] for w in wrote]
    assert states[-1] == "ok" and states.count("waiting") >= 3 and "ok" not in states[:-1]


def test_a_failed_write_never_changes_the_pass(events, monkeypatch, capsys) -> None:
    _, brief, seen, _ = events

    def broken(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(cv.EVENTS, "emit", broken)
    seen["report"] = REPORT.format("yes")
    assert cv.verify(7, brief, None, None) == 0
    assert "verifier event not written" in capsys.readouterr().err
