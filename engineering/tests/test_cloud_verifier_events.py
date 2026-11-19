"""A verifier pass writes the `verifier` event (events.md) on the branch it reviews: `waiting` from the head's fetch,
beating while it runs, then `ok` or `failed` by the report's `SATISFIED:` line, or `needs-owner` for a question."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import types

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


def test_an_exception_after_the_start_ends_the_event_failed(events, monkeypatch) -> None:
    """A fetch that raises leaves no `waiting` ref behind for a lead's `wait` to read as silent."""
    _, brief, _, wrote = events
    inner = cv.run

    def run(*cmd, **kw):
        if cmd[:2] == ("git", "fetch"):
            raise cv.subprocess.CalledProcessError(128, cmd)
        return inner(*cmd, **kw)

    monkeypatch.setattr(cv, "run", run)
    with pytest.raises(cv.subprocess.CalledProcessError):
        cv.verify(7, brief, None, None)
    assert [w[0] for w in wrote] == ["waiting", "failed"]


def test_a_checkout_that_shows_changes_ends_the_event_failed(events, monkeypatch) -> None:
    _, brief, _, wrote = events
    monkeypatch.setattr(cv, "showing", lambda report: " M a.txt")
    monkeypatch.setattr(cv, "returned", lambda was, report: "")
    with pytest.raises(cv.Refused, match="shows changes of its own"):
        cv.verify(7, brief, None, None)
    assert [w[0] for w in wrote] == ["waiting", "failed"]


def test_a_beat_in_flight_when_the_pass_ends_lands_before_the_end(monkeypatch) -> None:
    """The ref ends on the end state, never on a beat that was mid-push when the pass finished."""
    done: list[str] = []

    def emit(kind, branch, state, **kw):
        if state == "waiting" and threading.current_thread() is not threading.main_thread():
            time.sleep(0.3)  # a beat's ls-remote and push
        done.append(state)

    monkeypatch.setattr(cv, "EVENTS", types.SimpleNamespace(emit=emit, BEATS={"verifier": 0.1}))
    event = cv.PassEvent()
    event.start("loop/b")
    time.sleep(0.15)  # a beat is now mid-push
    event.state = "ok"
    event.finish()
    time.sleep(0.5)
    assert done[-1] == "ok" and done.count("ok") == 1


class Thread:
    """The Codex Cloud thread's side of `thread_verify`: what its VM answers to each call."""

    def __init__(self, monkeypatch, tmp_path, *, report: str, question: str = "") -> None:
        self.report, self.question = report, question
        monkeypatch.setattr(cv, "host_token", lambda: "t")
        monkeypatch.setattr(cv, "quota", lambda token: "ok")
        monkeypatch.setattr(cv, "Rpc", lambda token: object())
        monkeypatch.setattr(cv, "thread_start", lambda rpc, model, effort: ("th", "env"))
        monkeypatch.setattr(cv, "thread_exec", self.answer)
        monkeypatch.setattr(cv, "thread_turn", lambda *a: "final message")
        real = cv.run
        monkeypatch.setattr(
            cv,
            "run",
            lambda *cmd, **kw: (
                cv.subprocess.CompletedProcess(cmd, 0, "abc123 o/r feat/pr\n", "")
                if cmd[:3] == ("gh", "pr", "view")
                else real(*cmd, **kw)
            ),
        )
        self.brief = tmp_path / "brief.md"
        self.brief.write_text(f"Review.\n- Report: {tmp_path / 'out.md'}\n")

    def answer(self, rpc, thread, env, command):
        if not command.startswith("cat "):
            return 0, "/vm/pr7\n"  # the checkout, and the clearing of an earlier report
        asked = ".question" in command
        got = self.question if asked else self.report
        return (0, got) if got else (1, "")


@pytest.fixture
def thread(events, monkeypatch, tmp_path):
    _, _, _, wrote = events
    return lambda **kw: (Thread(monkeypatch, tmp_path, **kw), wrote)


@pytest.mark.parametrize(
    ("verdict", "end"), [("yes", "ok"), ("no", "failed")], ids=["satisfied", "unsatisfied"]
)
def test_a_thread_pass_emits_the_event_with_the_report_path_as_url(
    thread, tmp_path, verdict, end
) -> None:
    run, wrote = thread(report=REPORT.format(verdict))
    assert cv.thread_verify(7, run.brief, None, None, None, "env") == 0
    assert [w[0] for w in wrote] == ["waiting", end]
    assert wrote[-1][1] == str(tmp_path / "out.md")


def test_a_thread_pass_that_asks_is_needs_owner(thread, tmp_path) -> None:
    run, wrote = thread(report="", question="Which gate?\n")
    assert cv.thread_verify(7, run.brief, None, None, None, "env") == 3
    assert [w[0] for w in wrote] == ["waiting", "needs-owner"]
    assert wrote[-1][2] == "Which gate?\n" and wrote[-1][1].endswith("out.md.question")


def test_a_thread_pass_with_no_verdict_ends_failed(thread) -> None:
    run, wrote = thread(report="no verdict here")
    assert cv.thread_verify(7, run.brief, None, None, None, "env") == 1
    assert [w[0] for w in wrote] == ["waiting", "failed"]
