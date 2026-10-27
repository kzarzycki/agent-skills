"""scripts/omnigent_agent.py with the Omnigent server faked."""

import importlib.util
import inspect
import io
import json
import os
import re
import ssl
import subprocess
import sys
import threading
import time
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

spec = importlib.util.spec_from_file_location(
    "omnigent_agent",
    Path(__file__).resolve().parents[1]
    / "skills"
    / "orchestrating-agents"
    / "scripts"
    / "omnigent_agent.py",
)
assert spec and spec.loader
omnigent_agent = importlib.util.module_from_spec(spec)
sys.modules["omnigent_agent"] = omnigent_agent
spec.loader.exec_module(omnigent_agent)


class FakeOmnigent:
    """Sessions whose sends land only when `deaf` is not set for that session number."""

    def __init__(
        self, deaf: set[int] = frozenset(), reply: str = "", status: str = "idle", hold: int = 0
    ) -> None:
        self.deaf, self.reply, self.final = deaf, reply, status
        self.hold = hold  # polls of info() a send stays pending: a turn busy in a long tool call
        self.held: list[tuple[str, str, int]] = []
        self.posts = 0
        self.sessions: dict[str, list[dict]] = {}
        self.archived: list[str] = []
        self.prompts: list[dict] = []
        self.fail: set[str] = set()  # method names that raise Fail
        self.titles: dict[str, str] = {}
        self.created: dict[str, float] = {}  # when each session was made, as child_sessions says
        self.top_level: list[bool] = []  # per create, and per lookup after a failed one
        self.roles: list[str | None] = []  # per create
        self.workspaces: list[str | None] = []
        self.taken: set[str] = set()  # titles an earlier child holds: create answers 409
        self.subscriptions: list[tuple[str, str]] = []
        self.resolved: list[tuple[str, str, str, dict | None]] = []
        self.host_id = "h"  # this host
        self.harnesses: dict[str, str] = {}  # a registered agent's harness, by its name

    def harness(self, agent: str) -> str:
        return self.harnesses.get(agent, "")

    def create(
        self,
        agent: str,
        title: str,
        model: str | None = None,
        top_level: bool = False,
        workspace: str | None = None,
        permission_mode: str | None = None,
        host_id: str | None = None,
        role: str | None = None,
    ) -> str:
        if title in self.taken:
            error = HTTPError("http://x/v1/sessions", 409, "Conflict", Message(), None)
            raise omnigent_agent.Fail("POST /v1/sessions: HTTP 409 Conflict") from error
        sid = f"s{len(self.sessions)}"
        self.top_level.append(top_level)
        self.roles.append(role)
        self.workspaces.append(workspace)
        self.sessions[sid] = [{"type": "resource_event"}]
        self.titles[sid] = title
        self.created[sid] = time.time()
        if "create" in self.fail:  # the server made it; the answer timed out
            raise omnigent_agent.Fail("POST /v1/sessions: TimeoutError: timed out")
        return sid

    def siblings(self, title: str) -> list[dict]:
        if not omnigent_agent.parent_id():
            return []
        return [
            {"id": sid, "title": t, "created_at": self.created.get(sid, 0)}
            for sid, t in self.titles.items()
            if sid not in self.archived and (t == title or t.startswith(f"{title}-r"))
        ]

    def subscribe(self, subscriber: str, sid: str) -> None:
        if "subscribe" in self.fail:
            raise omnigent_agent.Fail("POST subscriptions: HTTP 404 Not Found")
        self.subscriptions.append((subscriber, sid))

    def find(self, title: str, after: float, top_level: bool = False) -> str | None:
        self.top_level.append(top_level)
        return next((s for s, t in self.titles.items() if t == title), None)

    def send(self, sid: str, text: str) -> None:
        if "send" in self.fail:
            raise omnigent_agent.Fail("POST events: HTTP 503")
        self.posts += 1
        if int(sid[1:]) in self.deaf:
            return
        if self.hold:
            self.held.append((sid, text, self.hold))
            return
        self.land(sid, text)

    def land(self, sid: str, text: str) -> None:
        self.sessions[sid].append(
            {
                "id": f"i{len(self.sessions[sid])}",
                "type": "message",
                "role": "user",
                "created_at": time.time(),
                "content": [{"type": "input_text", "text": text}],
            }
        )
        if self.reply:
            self.sessions[sid].append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": self.reply}],
                }
            )

    def items(self, sid: str) -> list[dict]:
        return self.sessions[sid]

    def info(self, sid: str) -> dict:
        for held in list(self.held):
            self.held.remove(held)
            if held[2] > 1:
                self.held.append((held[0], held[1], held[2] - 1))
            else:
                self.land(held[0], held[1])
        pending = [
            {"content": [{"type": "input_text", "text": t}]} for s, t, _ in self.held if s == sid
        ]
        status = "running" if pending else self.final
        info = {"status": status, "pending_elicitations": self.prompts, "pending_inputs": pending}
        if sid in self.archived:
            info["archived"] = True
        if sid[1:].isdigit() and int(sid[1:]) < len(self.workspaces):
            info["workspace"] = self.workspaces[int(sid[1:])]
        return info

    def resolve(self, sid: str, eid: str, action: str, content: dict | None = None) -> None:
        if eid in self.fail:
            raise omnigent_agent.Fail(f"POST resolve {eid}: HTTP 404 Not Found")
        self.resolved.append((sid, eid, action, content))
        self.prompts = [e for e in self.prompts if e["elicitation_id"] != eid]

    def archive(self, sid: str) -> None:
        if "archive" in self.fail:
            raise omnigent_agent.Fail(f"PATCH {sid}: HTTP 503")
        self.archived.append(sid)


REAL_TRIAGE = omnigent_agent.triage


@pytest.fixture(autouse=True)
def no_model(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The small model faked: never a real call. Each event it is asked about is recorded, and
    it answers ``none`` (mid-work)."""
    asked: list[str] = []
    monkeypatch.setattr(
        omnigent_agent, "triage", lambda event, decisions: asked.append(event) or ("none", "fake")
    )
    return asked


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(omnigent_agent, "POLL_SECONDS", 0)
    monkeypatch.setattr(omnigent_agent, "TURN_END_SECONDS", 0)
    monkeypatch.delenv("OMNIGENT_SUPERVISE_REGISTRY", raising=False)  # else run arms a real one
    monkeypatch.setattr(omnigent_agent, "capacity", lambda: (True, ""))  # else a busy host waits


def test_start_sends_preamble_and_confirms(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid, _ = omnigent_agent.start(
        og, "claude", "t", "do X", tmp_path / "r.md", "roles/worker.md", 0
    )
    message = omnigent_agent.text_of(og.sessions[sid][1])
    brief_file = tmp_path / "r.md.brief"
    assert message.startswith("Work on t:") and str(brief_file) in message and "do X" not in message
    text = brief_file.read_text()
    assert sid == "s0" and text.endswith("do X")
    assert (
        "owner authorized" in text
        and "setsid; exec @ARGV" in text
        and str(tmp_path / "r.md") in text
        and "roles/worker.md" in text
    )


@pytest.mark.parametrize(
    ("agent", "model", "env", "expected"),
    [
        ("claude", "claude-sonnet-5-5", None, "cc/sonnet-5.5/?"),
        ("codex", "gpt-6.1-terra", None, "codex/terra-6.1/?"),
        ("codex", None, "gpt-6.1-sol", "codex/sol-6.1/?"),
        ("claude", None, None, "cc/?/?"),
    ],
)
def test_start_gives_the_child_its_signature_from_what_it_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
    model: str | None,
    env: str | None,
    expected: str,
) -> None:
    monkeypatch.delenv(f"OMNIGENT_MODEL_{agent.upper()}", raising=False)
    if env:
        monkeypatch.setenv(f"OMNIGENT_MODEL_{agent.upper()}", env)
    og = FakeOmnigent()
    omnigent_agent.start(og, agent, "t", "do X", tmp_path / "r.md", None, 0, model=model)
    assert f"AGENT_SIGNATURE={expected}\n" in (tmp_path / "r.md.brief").read_text()


def test_a_running_session_reads_its_signature_without_launch_arguments(tmp_path: Path) -> None:
    """A session started with no model or effort (Omnigent's own tools, a default model) still signs in full."""
    rollout = tmp_path / ".codex/sessions/2026/10/27/rollout-2026-10-27T11-53-35-T1.jsonl"
    rollout.parent.mkdir(parents=True)
    turns = [
        {"model": "gpt-6.1-terra", "effort": "high"},
        {"model": "gpt-6.1-sol", "effort": "medium"},
    ]
    rollout.write_text(
        '{"type":"session_meta","payload":{}}\nnot json\n'
        + "".join(json.dumps({"type": "turn_context", "payload": t}) + "\n" for t in turns)
    )
    transcript = tmp_path / ".claude/projects/-repo/S1.jsonl"
    transcript.parent.mkdir(parents=True)
    replies = [
        {"type": "assistant", "message": {"model": "claude-opus-5-5"}},
        {"type": "user", "message": {}},
    ]
    transcript.write_text("".join(json.dumps(r) + "\n" for r in replies))
    read = omnigent_agent.running_signature
    assert read({"CODEX_THREAD_ID": "T1"}, tmp_path) == "codex/sol-6.1/med"
    assert read(
        {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "S1", "CLAUDE_EFFORT": "xhigh"}, tmp_path
    ) == ("cc/opus-5.5/xhigh")
    assert read({"CLAUDECODE": "1"}, tmp_path) == "cc/?/?"
    assert read({"CODEX_THREAD_ID": "gone"}, tmp_path) == "codex/?/?"
    assert read({}, tmp_path) == "?/?/?"


def test_start_abandons_deaf_session_and_retries(tmp_path: Path) -> None:
    og = FakeOmnigent(deaf={0})
    assert omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0) == (
        "s1",
        [],
    )
    assert og.archived == ["s0"]


def test_start_fails_after_two_deaf_sessions(tmp_path: Path) -> None:
    with pytest.raises(
        omnigent_agent.Fail, match="s0: brief not in history.*s1: brief not in history"
    ):
        omnigent_agent.start(
            FakeOmnigent(deaf={0, 1}), "claude", "t", "do X", tmp_path / "r.md", None, 0
        )


def test_wait_returns_report(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    (tmp_path / "r.md").write_text("ok")
    assert omnigent_agent.wait(og, sid, tmp_path / "r.md") == str(tmp_path / "r.md")


def test_verifier_wait_returns_only_after_the_verdict(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="checking", status="running")
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "codex", "t", "do X", report, None, 0)
    report.write_text("## Standards\n\nFULL_GATE_PENDING\n")
    with pytest.raises(omnigent_agent.Fail, match="no verdict after 0s"):
        omnigent_agent.wait(og, sid, report, timeout=0, verdict=True)
    polls = 0

    def info(s: str) -> dict:
        nonlocal polls
        polls += 1
        if polls == 3:
            report.write_text(report.read_text() + "SATISFIED: yes\n")
        if polls == 4:  # it revises the verdict before its turn ends
            report.write_text(report.read_text().replace("yes", "no"))
        return {"status": "running" if polls < 5 else "idle", "pending_elicitations": []}

    og.info = info  # type: ignore[method-assign]
    assert omnigent_agent.wait(og, sid, report, verdict=True) == str(report)
    assert polls == 5
    assert report.read_text().endswith("SATISFIED: no\n")


def test_a_report_written_while_the_turn_runs_waits_for_the_turn_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="landed #1", status="running")
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", report, None, 0)
    report.write_text("progress: #1 landed")  # a lead writing progress at its report path
    with pytest.raises(omnigent_agent.Fail, match="no report after 0s"):
        omnigent_agent.wait(og, sid, report, timeout=0)
    og.final = "idle"
    assert omnigent_agent.wait(og, sid, report, timeout=0) == str(report)


def test_one_idle_look_is_no_turn_end_and_the_deadline_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="checking")  # reads idle mid-turn, its draft long written
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "codex", "t", "do X", report, None, 0)
    report.write_text("draft\nSATISFIED: yes\n")
    old = time.time() - 120
    os.utime(report, (old, old))
    monkeypatch.setattr(omnigent_agent, "TURN_END_SECONDS", 60)
    looks = 0
    info = og.info

    def rewriting(s: str) -> dict:
        nonlocal looks
        looks += 1
        assert looks < 5, "the wait ran past its deadline"
        report.write_text(f"draft {looks}\nSATISFIED: yes\n")  # still revising
        return info(s)

    og.info = rewriting  # type: ignore[method-assign]
    with pytest.raises(omnigent_agent.Fail, match="no verdict after 0s"):
        omnigent_agent.wait(og, sid, report, timeout=0, verdict=True)
    og.info = info  # type: ignore[method-assign]
    monkeypatch.setattr(omnigent_agent, "TURN_END_SECONDS", 0)
    assert omnigent_agent.wait(og, sid, report, timeout=0, verdict=True) == str(report)


def test_a_lost_turn_end_counts_the_report_once_it_and_the_history_are_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(reply="done", status="running")  # Omnigent never shows the turn end
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", report, None, 0)
    report.write_text("final")
    old = time.time() - 120
    os.utime(report, (old, old))
    for item in og.sessions[sid]:
        item["created_at"] = old
    monkeypatch.setattr(omnigent_agent, "SETTLE_SECONDS", 180)
    with pytest.raises(omnigent_agent.Fail, match="no report after 0s"):
        omnigent_agent.wait(og, sid, report, timeout=0)
    monkeypatch.setattr(omnigent_agent, "SETTLE_SECONDS", 60)
    og.sessions[sid].append({"type": "message", "role": "assistant", "created_at": time.time()})
    with pytest.raises(omnigent_agent.Fail, match="no report after 0s"):  # its history is not
        omnigent_agent.wait(og, sid, report, timeout=0)
    og.sessions[sid][-1]["created_at"] = old
    assert omnigent_agent.wait(og, sid, report, timeout=0) == str(report)
    assert "a lost turn end" in capsys.readouterr().err


def test_verifier_wait_fails_when_turn_ends_without_verdict(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="done")
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "codex", "t", "do X", report, None, 0)
    report.write_text("VERDICT: 0 blocker, 0 major, 0 minor\n")
    with pytest.raises(omnigent_agent.Fail, match=r"ended \(idle\) without a verdict"):
        omnigent_agent.wait(og, sid, report, verdict=True)


def test_worker_wait_needs_no_verdict(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="checking")
    sid = og.create("claude", "t")
    (tmp_path / "r.md").write_text("partial")
    assert omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=0) == str(tmp_path / "r.md")


def test_wait_fails_with_last_message_when_turn_ends_without_report(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent(reply="Shall I go ahead?")
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    with pytest.raises(omnigent_agent.Fail, match="(?s)without .*Shall I go ahead"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md")


def test_wait_fails_on_failed_session_before_reply(tmp_path: Path) -> None:
    og = FakeOmnigent(status="failed")
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    with pytest.raises(omnigent_agent.Fail, match=r"ended \(failed\)"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md")


def test_wait_fails_at_once_on_pending_prompt(tmp_path: Path) -> None:
    og = FakeOmnigent(status="running")
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    og.prompts = [
        {
            "type": "response.elicitation_request",
            "params": {"message": "Allow Bash: rm -rf x?"},
        }
    ]
    with pytest.raises(omnigent_agent.Fail, match="blocked on a prompt: Allow Bash: rm -rf x"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md")


def test_wait_times_out_with_last_message(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="still working", status="running")
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    with pytest.raises(omnigent_agent.Fail, match="(?s)no report after 0s.*still working"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=0)


def test_wait_keeps_waiting_through_a_mid_turn_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(status="idle")  # the brief is the last item while the child works
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", report, None, 0)
    monkeypatch.setattr(omnigent_agent, "IDLE_GRACE_SECONDS", 3600)
    statuses = iter(["running", "idle", "idle", "running"])

    def info(s: str) -> dict:
        status = next(statuses, None)
        if status is None and not report.exists():
            report.write_text("done")
            status = "running"
        return {"status": status or "idle", "pending_elicitations": []}

    og.info = info  # type: ignore[method-assign]
    assert omnigent_agent.wait(og, sid, report, timeout=5) == str(report)


def test_wait_keeps_waiting_through_launch_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(status="idle")
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    monkeypatch.setattr(omnigent_agent, "IDLE_GRACE_SECONDS", 3600)
    with pytest.raises(omnigent_agent.Fail, match="no report after 0s"):  # timeout, not "ended"
        omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=0)
    monkeypatch.setattr(omnigent_agent, "IDLE_GRACE_SECONDS", 0)
    with pytest.raises(omnigent_agent.Fail, match=r"ended \(idle\)"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md")


def test_a_taken_title_moves_to_the_next_free_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    og.taken = {"t", "t-r2"}  # an earlier pass's children, archived or not
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.titles[sid] == "t-r3"
    err = capsys.readouterr().err
    assert "title t is taken" in err and f"session {sid} is titled t-r3" in err


def test_a_taken_title_and_a_deaf_session_share_one_suffix_sequence(tmp_path: Path) -> None:
    og = FakeOmnigent(deaf={0})
    og.taken = {"t-r2"}
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert [og.titles[s] for s in og.sessions] == ["t", "t-r3"]
    assert og.titles[sid] == "t-r3"


@pytest.mark.parametrize("inline", [False, True])
def test_a_second_start_of_the_same_brief_attaches_to_the_live_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    inline: bool,
) -> None:
    """A rerun after a `run` that failed on its own while the child worked on: one pass, paid once."""
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "lead")
    monkeypatch.setattr(omnigent_agent, "briefed_by_file", lambda *_: not inline)
    og = FakeOmnigent()
    first, _ = omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
    og.taken = {"t"}  # Omnigent's 409 would retitle a second create t-r2
    assert omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0) == (first, [])
    assert list(og.sessions) == [first]
    assert f"session {first} already holds this brief" in capsys.readouterr().err


@pytest.mark.parametrize(
    "change", ["brief", "archived", "failed", "report path", "top level", "no parent"]
)
def test_a_changed_brief_or_a_gone_child_starts_a_new_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "lead")
    og = FakeOmnigent()
    first, _ = omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
    brief, report, top = "do X", tmp_path / "r.md", False
    if change == "brief":
        brief = "do X on the new head"
    elif change == "archived":
        og.archived.append(first)
    elif change == "failed":
        monkeypatch.setattr(og, "final", "failed")
    elif change == "report path":
        report = tmp_path / "r2.md"
    elif change == "top level":
        top = True
    else:
        monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID")
    second, _ = omnigent_agent.start(og, "codex", "t", brief, report, None, 0, top_level=top)
    assert second != first


@pytest.mark.parametrize("inline", [False, True])
def test_a_rerun_attaches_to_the_child_briefed_with_that_text_not_an_earlier_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inline: bool
) -> None:
    """Brief A, then B, then B again: the file now holds B and both children are live."""
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "lead")
    monkeypatch.setattr(omnigent_agent, "briefed_by_file", lambda *_: not inline)
    og = FakeOmnigent()
    report = tmp_path / "r.md"
    a, _ = omnigent_agent.start(og, "codex", "t", "review A and check speed", report, None, 0)
    og.taken = {"t"}
    b, _ = omnigent_agent.start(og, "codex", "t", "review A", report, None, 0)  # a prefix of A
    assert b != a
    assert omnigent_agent.start(og, "codex", "t", "review A", report, None, 0) == (b, [])


def test_a_child_whose_brief_left_its_history_page_is_still_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "lead")
    og = FakeOmnigent()
    first, _ = omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
    og.sessions[first] = [{"type": "resource_event"}] * 100  # the newest page, no brief in it
    og.taken = {"t"}
    assert omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0) == (first, [])


def test_a_child_that_already_wrote_the_report_is_not_waited_on_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "lead")
    og = FakeOmnigent()
    first, _ = omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
    og.created[first] -= 10
    (tmp_path / "r.md").write_text("done")
    with pytest.raises(omnigent_agent.Fail, match=f"session {first} already wrote .*: read it"):
        omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
    assert list(og.sessions) == [first]


def test_start_gives_up_when_every_title_is_taken(tmp_path: Path) -> None:
    og = FakeOmnigent()
    og.taken = {"t"} | {f"t-r{n}" for n in range(2, omnigent_agent.TITLES + 1)}
    with pytest.raises(
        omnigent_agent.Fail, match=f"titles t to t-r{omnigent_agent.TITLES} are taken"
    ):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.sessions == {}


def test_failed_archive_is_reported_and_retry_proceeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(deaf={0})
    og.fail.add("archive")
    assert omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0) == (
        "s1",
        ["s0"],
    )
    assert "abandoned session s0 survives" in capsys.readouterr().err


def test_send_failure_after_create_archives_session(tmp_path: Path) -> None:
    og = FakeOmnigent()
    og.fail.add("send")
    with pytest.raises(omnigent_agent.Fail, match="s0: POST events: HTTP 503"):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.archived == ["s0"]


def test_main_exits_nonzero_when_abandoned_session_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(deaf={0})
    og.fail.add("archive")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    assert (
        omnigent_agent.main(
            [
                "start",
                "claude",
                "t",
                str(tmp_path / "b.md"),
                str(tmp_path / "r.md"),
                "--confirm-seconds",
                "0",
            ]
        )
        == 1
    )


def test_token_lookup_timeout_is_a_clear_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def hang(*a: object, **k: object) -> None:
        raise omnigent_agent.subprocess.TimeoutExpired("python", k["timeout"])  # type: ignore[arg-type]

    monkeypatch.setattr(omnigent_agent.subprocess, "run", hang)
    og = object.__new__(omnigent_agent.Omnigent)
    og.base = "https://omnigent.test"
    with pytest.raises(omnigent_agent.Fail, match="timed out after 30s"):
        og.token()


def test_stalled_server_timeout_reaches_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Stall(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            time.sleep(0.3)  # accepted the event, answers after the client gave up
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    class Local(omnigent_agent.Omnigent):
        def __init__(self, base: str) -> None:
            self.base, self._token, self.archived = base, "synthetic", []

        def create(self, *args: object) -> str:
            return "s0"

        def archive(self, sid: str) -> None:
            self.archived.append(sid)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stall)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        og = Local(f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(omnigent_agent, "HTTP_SECONDS", 0.05)
        # the timed-out POST leaves delivery to the history, which this server cannot show
        with pytest.raises(omnigent_agent.Fail, match="s0: GET .*HTTP 501"):
            omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
        assert og.archived == ["s0"]
    finally:
        server.shutdown()


def test_a_start_whose_send_timed_out_keeps_the_session_the_history_shows_took_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from urllib.error import URLError

    class Late(FakeOmnigent):
        def send(self, sid: str, text: str) -> None:
            super().send(sid, text)  # the server took it, after the client gave up
            raise omnigent_agent.Fail("POST events: timed out") from URLError(
                TimeoutError("timed out")
            )

    og = Late()
    sid = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)[0]
    assert og.archived == [] and og.posts == 1

    # a timeout only: a reset still fails, as Omnigent.send itself does on any error (the
    # supervisor's sends advance their state on its return)
    def reset(sid: str, text: str) -> None:
        raise omnigent_agent.Fail("POST events: reset") from ConnectionResetError("reset")

    monkeypatch.setattr(og, "send", reset)
    with pytest.raises(omnigent_agent.Fail, match="reset"):
        omnigent_agent.send_to_confirm(og, sid, "go")


def test_start_waits_while_the_host_is_over_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.undo()  # the real capacity check, on a faked host
    monkeypatch.setattr(omnigent_agent, "POLL_SECONDS", 0)
    monkeypatch.setattr(omnigent_agent, "TURN_END_SECONDS", 0)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 16000000 kB\nMemAvailable: 1048576 kB\n")
    monkeypatch.setattr(omnigent_agent, "MEMINFO", meminfo)
    monkeypatch.setattr(omnigent_agent.os, "getloadavg", lambda: (300.0, 0.0, 0.0))  # not CPU
    monkeypatch.setattr(omnigent_agent, "cpu_idle", lambda: 40.0)
    assert omnigent_agent.main(["capacity"]) == 1  # short of memory
    assert capsys.readouterr().out == "cpu 40% idle (min 10), 1024 MB available (min 1536)\n"
    meminfo.write_text("MemAvailable: 4194304 kB\n")
    assert omnigent_agent.main(["capacity"]) == 0  # a high load average with idle CPU has room
    monkeypatch.setattr(omnigent_agent, "cpu_idle", lambda: 3.0)
    monkeypatch.setattr(omnigent_agent, "CAPACITY_WAIT_SECONDS", 0)
    og = FakeOmnigent()
    with pytest.raises(omnigent_agent.Fail, match="host over capacity for 0s: cpu 3% idle"):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.sessions == {}

    idles = iter([3.0, 25.0])
    monkeypatch.setattr(omnigent_agent, "cpu_idle", lambda: next(idles))
    monkeypatch.setattr(omnigent_agent, "CAPACITY_WAIT_SECONDS", 60)
    omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert "host over capacity, waiting: cpu 3% idle" in capsys.readouterr().err
    assert og.sessions  # started once the CPU freed up


def test_capacity_reads_macos_memory_or_says_it_is_not_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the real capacity check, on a faked host
    monkeypatch.setattr(omnigent_agent, "MEMINFO", tmp_path / "absent")
    monkeypatch.setattr(omnigent_agent, "cpu_idle", lambda: None)  # load decides
    monkeypatch.setattr(omnigent_agent.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(omnigent_agent.os, "getloadavg", lambda: (8.0, 0.0, 0.0))
    sysctl = subprocess.CompletedProcess([], 0, stdout="4\n34359738368\n")
    monkeypatch.setattr(omnigent_agent.subprocess, "run", lambda *a, **k: sysctl)
    assert omnigent_agent.capacity() == (
        False,
        "load 1.0 per core (max 4), 1311 MB available (min 1536)",
    )
    sysctl.stdout = ""
    assert omnigent_agent.capacity() == (
        True,
        "load 1.0 per core (max 4), memory not measured (min 1536)",
    )


def test_cpu_idle_reads_proc_stat_or_iostats_second_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the real measurement, on a faked host
    stat = tmp_path / "stat"
    stat.write_text("cpu 100 0 100 700 100 0 0 0 50 0\ncpu0 1 2 3 4 5 6 7 8\n")
    monkeypatch.setattr(omnigent_agent, "PROC_STAT", stat)
    later = "cpu 160 0 140 760 140 0 0 0 90 0\n"  # a second later; guest is counted in user
    monkeypatch.setattr(omnigent_agent.time, "sleep", lambda _: stat.write_text(later))
    assert omnigent_agent.cpu_idle() == 50.0  # (60 idle + 40 iowait) of 200 ticks
    monkeypatch.setattr(omnigent_agent, "PROC_STAT", tmp_path / "absent")
    head = "      cpu    load average\n us sy id   1m   5m   15m\n 33 19 48  131.50 100.60 107.07\n"
    iostat = subprocess.CompletedProcess([], 0, stdout=head)
    monkeypatch.setattr(omnigent_agent.subprocess, "run", lambda *a, **k: iostat)
    assert omnigent_agent.cpu_idle() is None  # one sample counts since boot: not measured
    iostat.stdout += " 41 21 38  131.50 100.60 107.07\n"
    assert omnigent_agent.cpu_idle() == 38.0


def test_stalled_error_body_reaches_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class StallBody(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(503)
            self.send_header("Content-Length", "100")
            self.end_headers()
            time.sleep(0.3)  # the error body never arrives before the client's timeout

        def log_message(self, *args: object) -> None:
            pass

    class Local(omnigent_agent.Omnigent):
        def __init__(self, base: str) -> None:
            self.base, self._token, self.archived = base, "synthetic", []

        def create(self, *args: object) -> str:
            return "s0"

        def archive(self, sid: str) -> None:
            self.archived.append(sid)

    server = ThreadingHTTPServer(("127.0.0.1", 0), StallBody)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        og = Local(f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(omnigent_agent, "HTTP_SECONDS", 0.05)
        with pytest.raises(omnigent_agent.Fail, match="s0: POST .*HTTP 503"):
            omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
        assert og.archived == ["s0"]
    finally:
        server.shutdown()


def test_create_files_the_session_under_the_project(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        calls.append((method, path, body))
        return {
            "/v1/agents": [{"name": omnigent_agent.AGENTS["claude"], "id": "a1"}],
            "/v1/agents?scope=user": [],
            "/v1/projects": {"data": [{"name": "other", "id": "p0"}, {"name": "shop", "id": "p1"}]},
            "/v1/sessions": {"id": "s1"},
            "/v1/sessions/coord": {},  # a lead filed nowhere
        }[path]

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    monkeypatch.setattr(omnigent_agent, "repo_name", lambda: "shop")
    monkeypatch.delenv("OMNIGENT_PROJECT", raising=False)
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)
    assert omnigent_agent.Omnigent().create("claude", "t") == "s1"
    assert calls[-1][2] and calls[-1][2]["project_id"] == "p1"
    assert "parent_session_id" not in calls[-1][2]  # run outside a session: top level
    assert capsys.readouterr().err == ""

    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "coord")
    omnigent_agent.Omnigent().create("claude", "t")
    assert calls[-1][2] and calls[-1][2]["parent_session_id"] == "coord"

    monkeypatch.setenv("OMNIGENT_PROJECT", "no-such-group")  # projects are only sidebar groups
    assert omnigent_agent.Omnigent().create("claude", "t") == "s1"
    assert calls[-1][2] and "project_id" not in calls[-1][2]
    assert capsys.readouterr().err == ""  # a child hides under its lead: no warning

    omnigent_agent.Omnigent().create("claude", "t", top_level=True)
    assert calls[-1][2] and "project_id" not in calls[-1][2]
    err = capsys.readouterr().err
    assert "'no-such-group'" in err and "OMNIGENT_PROJECT" in err

    # as the repo voice_note files under "Voice note"
    monkeypatch.setenv("OMNIGENT_PROJECT", "S_hop")
    omnigent_agent.Omnigent().create("claude", "t")
    assert calls[-1][2] and calls[-1][2]["project_id"] == "p1"


def test_create_files_the_session_under_its_caller_s_project(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scheduled run is filed in its task's project, whose name its repo's need not match."""
    bodies: list[dict] = []
    sessions = {"lead": {"project_id": "p1"}, "child": {}}

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        if method == "POST":
            bodies.append(body or {})
            return {"id": "s1"}
        if path.startswith("/v1/sessions/"):
            sid = path.removeprefix("/v1/sessions/")
            if sid not in sessions:
                raise omnigent_agent.Fail(f"GET {path}: HTTP 404 Not Found")
            return sessions[sid]
        return {
            "/v1/agents": [{"name": omnigent_agent.AGENTS["claude"], "id": "a1"}],
            "/v1/agents?scope=user": [],
            "/v1/projects": {"data": [{"name": "other", "id": "p0"}, {"name": "eng", "id": "p1"}]},
        }[path]

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    monkeypatch.setattr(omnigent_agent, "repo_name", lambda: "eng-repo")  # matches no project
    monkeypatch.delenv("OMNIGENT_PROJECT", raising=False)
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "lead")
    omnigent_agent.Omnigent().create("claude", "t", top_level=True)
    assert bodies[-1]["project_id"] == "p1"
    assert capsys.readouterr().err == ""

    monkeypatch.setenv("OMNIGENT_SESSION_ID", "child")  # filed nowhere itself: its lead's
    omnigent_agent.Omnigent().create("claude", "t")
    assert bodies[-1]["project_id"] == "p1"

    monkeypatch.setenv("OMNIGENT_SESSION_ID", "gone")  # unreadable: falls through to its lead
    omnigent_agent.Omnigent().create("claude", "t")
    assert bodies[-1]["project_id"] == "p1"

    monkeypatch.setenv("OMNIGENT_SESSION_ID", "child")
    sessions["child"] = {"project_id": "p0"}  # its own project comes first
    omnigent_agent.Omnigent().create("claude", "t")
    assert bodies[-1]["project_id"] == "p0"

    monkeypatch.setenv("OMNIGENT_PROJECT", "eng")  # the override wins over both
    omnigent_agent.Omnigent().create("claude", "t")
    assert bodies[-1]["project_id"] == "p1"


def test_create_labels_the_session_with_its_loop_role_from_the_role_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies: list[dict] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        bodies.append(body or {})
        agents = [{"name": n, "id": a} for a, n in omnigent_agent.AGENTS.items()]
        return {
            "/v1/agents": agents,
            "/v1/agents?scope=user": [],
            "/v1/projects": {"data": []},
            "/v1/sessions": {"id": "s1"},
        }[path]

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    og = omnigent_agent.Omnigent()
    for role in ("lead", "worker", "verifier"):
        og.create("codex", "t", role=f"/x/engineering-loop/{role}.md")
        assert bodies[-1]["labels"] == {"omni.role": role}
    for role in (None, "/x/reviewer.md"):
        og.create("codex", "t", role=role)
        assert "labels" not in bodies[-1]


def test_create_sets_a_claude_session_s_permission_mode_from_the_flag_or_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bodies: list[dict] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        bodies.append(body or {})
        agents = [{"name": n, "id": a} for a, n in omnigent_agent.AGENTS.items()]
        return {
            "/v1/agents": agents,
            "/v1/agents?scope=user": [],
            "/v1/projects": {"data": []},
            "/v1/sessions": {"id": "s1"},
        }[path]

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    monkeypatch.delenv("OMNIGENT_PERMISSION_MODE", raising=False)
    og = omnigent_agent.Omnigent()
    og.create("claude", "t")
    assert "terminal_launch_args" not in bodies[-1]  # the harness default
    og.create("claude", "t", permission_mode="plan")
    assert bodies[-1]["terminal_launch_args"] == ["--permission-mode", "plan"]
    monkeypatch.setenv("OMNIGENT_PERMISSION_MODE", "acceptEdits")
    og.create("claude", "t")
    assert bodies[-1]["terminal_launch_args"] == ["--permission-mode", "acceptEdits"]
    og.create("codex", "t")  # codex-native would hand it to the codex CLI, which fails to start
    assert "terminal_launch_args" not in bodies[-1]
    with pytest.raises(omnigent_agent.Fail, match="for claude sessions"):
        omnigent_agent.start(
            FakeOmnigent(), "codex", "t", "do X", tmp_path / "r.md", None, 0, permission_mode="plan"
        )


@pytest.mark.parametrize(
    ("names", "name", "picked"),
    [
        (["Voice-note", "voice_note"], "voice_note", 1),  # the exact name wins over a loose one
        (["工程", "日本語"], "日本語", 1),  # letters in any script count
        (["café"], "caf", None),
        (["!!"], "--", None),  # nothing left to compare matches nothing
        (["Voice note"], "voice_note", 0),
    ],
)
def test_a_project_matches_its_exact_name_first_then_loosely(
    monkeypatch: pytest.MonkeyPatch, names: list[str], name: str, picked: int | None
) -> None:
    projects = [{"name": n, "id": f"p{i}"} for i, n in enumerate(names)]
    monkeypatch.setattr(omnigent_agent.Omnigent, "call", lambda *a: {"data": projects})
    found = object.__new__(omnigent_agent.Omnigent).project(name)
    assert found == (None if picked is None else projects[picked])


def test_two_loose_project_matches_fail_rather_than_pick_by_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects = [{"name": "Voice-note", "id": "p0"}, {"name": "Voice note", "id": "p1"}]
    monkeypatch.setattr(omnigent_agent.Omnigent, "call", lambda *a: {"data": projects})
    with pytest.raises(omnigent_agent.Fail, match="OMNIGENT_PROJECT"):
        object.__new__(omnigent_agent.Omnigent).project("voice_note")


def test_the_model_is_the_flag_else_the_agents_environment_variable_else_the_harness_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies: list[dict] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        if body is not None:
            bodies.append(body)
        return {
            "/v1/agents": [{"name": "codex-native-ui", "id": "a1"}],
            "/v1/agents?scope=user": [],
            "/v1/projects": [],
        }.get(path, {"id": "s1"})

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    monkeypatch.delenv("OMNIGENT_MODEL_CODEX", raising=False)
    omnigent_agent.Omnigent().create("codex", "t")
    monkeypatch.setenv("OMNIGENT_MODEL_CODEX", "from-env")
    monkeypatch.setenv("OMNIGENT_MODEL_CLAUDE", "not-codex")
    omnigent_agent.Omnigent().create("codex", "t")
    omnigent_agent.Omnigent().create("codex", "t", "from-flag")
    assert [body.get("model_override") for body in bodies] == [None, "from-env", "from-flag"]


@pytest.mark.parametrize(
    ("origin", "name"),
    [
        ("git@github.com:example/shop.git", "shop"),
        ("https://github.com/example/shop", "shop"),
        ("https://github.com/example/shop.git/", "shop"),
        (None, "checkout"),
    ],
)
def test_the_project_defaults_to_the_repo_name(
    origin: str | None, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if origin:
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", origin], check=True)
    monkeypatch.chdir(repo)
    assert omnigent_agent.repo_name() == name


def test_wait_returns_question_instead_of_failing(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="r.md.question")
    report = tmp_path / "r.md"
    og.send(og.create("claude", "t"), "brief")
    omnigent_agent.question_of(report).write_text("which base?")
    with pytest.raises(omnigent_agent.Asked, match=r"r\.md\.question"):
        omnigent_agent.wait(og, "s0", report, timeout=5)


def test_send_answers_live_session_and_clears_question(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    report = tmp_path / "r.md"
    omnigent_agent.question_of(report).write_text("which base?")
    omnigent_agent.send(og, sid, "use main", report, 0)
    assert not omnigent_agent.question_of(report).exists()
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "use main"


def reaped(og: FakeOmnigent, reply: dict, online_after: int = 1) -> list[str]:
    """Make every session reaped until a retry_session answering ``reply``, then online after
    ``online_after`` more info() reads; returns the retried session ids."""
    retried: list[str] = []
    polls = [0]
    info = og.info

    def reaped_info(s: str) -> dict:
        polls[0] += 1
        return {**info(s), "runner_online": bool(retried) and polls[0] > online_after}

    def retry(s: str) -> dict:
        retried.append(s)
        polls[0] = 0
        return reply

    og.info, og.retry = reaped_info, retry  # type: ignore[method-assign,attr-defined]
    return retried


def test_send_revives_a_reaped_runner_then_sends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "POLL_SECONDS", 0)
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    retried = reaped(og, {"queued": False, "recovered": True, "recovery": "runner_relaunched"}, 2)
    omnigent_agent.send(og, sid, "use main", tmp_path / "r.md", 0)
    assert retried == [sid]
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "use main"


def test_send_exits_gone_naming_the_reply_when_the_revive_fails(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    reaped(og, {"queued": False, "recovered": False, "recovery": "no_runner"})
    with pytest.raises(omnigent_agent.Gone, match='revive failed: .*"no_runner"'):
        omnigent_agent.send(og, sid, "use main", tmp_path / "r.md", 0)
    assert og.sessions[sid] == [{"type": "resource_event"}]


def test_a_revive_whose_runner_never_comes_online_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "POLL_SECONDS", 0)
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    reaped(og, {"recovered": True, "recovery": "runner_relaunched"}, online_after=10**9)
    with pytest.raises(omnigent_agent.Gone, match="no runner online after 0s"):
        omnigent_agent.revive(og, sid, seconds=0)


def test_send_fails_when_answer_never_arrives(tmp_path: Path) -> None:
    og = FakeOmnigent(deaf={0})
    sid = og.create("claude", "t")
    with pytest.raises(omnigent_agent.Gone, match="neither pending nor in history"):
        omnigent_agent.send(og, sid, "use main", tmp_path / "r.md", 0)


def test_send_to_a_busy_session_waits_while_the_harness_holds_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=5)  # pending longer than confirm_seconds: a long tool call
    sid = og.create("claude", "t")
    report = tmp_path / "r.md"
    omnigent_agent.question_of(report).write_text("which base?")
    omnigent_agent.send(og, sid, "use main", report, 0)
    assert "queued" in capsys.readouterr().err
    assert not omnigent_agent.question_of(report).exists()
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "use main"


def test_a_retried_send_never_delivers_twice(tmp_path: Path) -> None:
    og = FakeOmnigent(hold=3)
    sid = og.create("claude", "t")
    report = tmp_path / "r.md"
    omnigent_agent.question_of(report).write_text("which base?")
    og.send(sid, "use main")  # the first send, still pending when it gave up
    omnigent_agent.send(og, sid, "use main", report, 0)  # retry while pending
    omnigent_agent.question_of(report).write_text(
        "which base?"
    )  # as if the first send's unlink never ran
    og.sessions[sid][-1]["created_at"] = time.time() + 1  # the answer landed after the question
    omnigent_agent.send(og, sid, "use main", report, 0)  # retry after it landed
    assert og.posts == 1
    assert [omnigent_agent.text_of(i) for i in og.sessions[sid][1:]] == ["use main"]
    assert not omnigent_agent.question_of(report).exists()


def test_an_answer_inside_an_older_message_is_still_sent(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    report = tmp_path / "r.md"
    omnigent_agent.question_of(report).write_text("which base?")
    og.land(sid, "Do not use main; use the release branch")
    og.sessions[sid][-1]["created_at"] = time.time() + 1
    omnigent_agent.send(og, sid, "use main", report, 0)
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "use main"


def test_a_retry_sends_nothing_when_the_first_copy_lands_between_its_reads(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent(hold=1)  # lands at the retry's first info() call
    sid = og.create("claude", "t")
    og.send(sid, "use main")  # the first send; its process already removed the question
    omnigent_agent.send(og, sid, "use main", tmp_path / "r.md", 0)
    assert og.posts == 1


def test_a_retry_keeps_its_question_time_when_the_first_sender_removes_it(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    report = tmp_path / "r.md"
    question = omnigent_agent.question_of(report)
    question.write_text("which base?")
    og.land(sid, "use main")
    og.sessions[sid][-1]["created_at"] = time.time() + 1
    info = og.info
    og.info = lambda s: (question.unlink(missing_ok=True), info(s))[1]  # type: ignore[method-assign]
    omnigent_agent.send(og, sid, "use main", report, 0)
    assert og.posts == 0


def test_a_different_message_containing_the_answer_does_not_confirm_it(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent(deaf={0})
    sid = og.create("claude", "t")
    items = og.items
    og.items = (
        lambda s: (  # type: ignore[method-assign]
            og.posts
            and not og.sessions[s][1:]
            and og.land(s, "Do not use main; use the release branch"),
            items(s),
        )[1]
    )
    with pytest.raises(omnigent_agent.Gone):
        omnigent_agent.send(og, sid, "use main", tmp_path / "r.md", 0)


def test_send_ignores_the_report_of_the_turn_before(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    sid = og.create("claude", "t")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    report = tmp_path / "r.md"
    report.write_text("old findings\nSATISFIED: yes\n")
    os.utime(report, (1, 1))
    (tmp_path / "a.md").write_text("fix C1")
    argv = ["send", sid, "a.md", "r.md", "--verdict"]
    assert omnigent_agent.main(argv) == 1  # the turn ended and only the stale report is there
    assert "without a verdict" in capsys.readouterr().err

    info = og.info
    og.info = lambda s: (report.write_text("new\nSATISFIED: yes\n"), info(s))[1]  # type: ignore[method-assign]
    assert omnigent_agent.main(argv) == 0
    assert capsys.readouterr().out.strip() == str(report)


def test_a_rerun_after_the_answer_landed_returns_the_report_it_produced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    sid = og.create("claude", "t")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    report = tmp_path / "r.md"
    question = omnigent_agent.question_of(report)
    question.write_text("which base?")
    os.utime(question, (1, 1))
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "cos")
    og.send(sid, "[relayed by cos]\nuse main")  # the first send died before it removed the question
    report.write_text("done\nSATISFIED: yes\n")  # and the child answered with its report
    (tmp_path / "a.md").write_text("use main")
    assert omnigent_agent.main(["send", sid, "a.md", "r.md", "--verdict"]) == 0
    assert og.posts == 1


def test_a_follow_up_is_marked_as_posted_so_owner_said_skips_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    sid = og.create("claude", "t")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "cos")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("yes, force-push the branch")
    (tmp_path / "r.md").write_text("")
    os.utime(tmp_path / "r.md", (1, 1))
    omnigent_agent.main(["send", sid, "a.md", "r.md", "--timeout", "0"])
    sent = [omnigent_agent.text_of(i) for i in og.sessions[sid] if i.get("role") == "user"]
    follow_up = next(t for t in sent if "force-push" in t)
    assert follow_up == "[relayed by cos]\nyes, force-push the branch"
    assert omnigent_agent.agent_posted(follow_up)  # owner-said rejects a quote found only here


def test_a_follow_up_sent_as_the_turn_before_ends_is_waited_for(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    report = tmp_path / "r.md"
    og.sessions[sid].append({"type": "message", "role": "assistant", "content": []})
    # the turn before ends, the follow-up lands in the idle gap, then its own turn runs
    script = iter(["running", "idle", "idle", "running", "running"])

    def info(s: str) -> dict:
        status = next(script, "idle")
        if status == "idle" and og.sessions[s][-1].get("role") != "user":
            og.land(s, "fix C1")
        if (
            status == "running"
            and og.sessions[s][-1].get("role") == "user"
            and not next(iter([report.exists()]))
        ):
            report.write_text("done")
        return {"status": status, "pending_elicitations": []}

    og.info = info  # type: ignore[method-assign]
    assert omnigent_agent.wait(og, sid, report, timeout=5) == str(report)


def test_same_family_verifier_needs_break_glass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = tmp_path / "b.md"
    brief.write_text("review")
    argv = [
        "run",
        "claude",
        "t",
        str(brief),
        str(tmp_path / "r.md"),
        "--role",
        "verifier.md",
        "--author",
        "claude",
    ]
    monkeypatch.setattr(omnigent_agent, "Omnigent", FakeOmnigent)
    monkeypatch.chdir(tmp_path)
    assert omnigent_agent.main(argv) == 1
    assert "--same-family" in capsys.readouterr().err

    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    assert omnigent_agent.main(["start", *argv[1:], "--same-family"]) == 0
    brief = (tmp_path / "r.md.brief").read_text()
    assert (
        brief.endswith("\n\nreview") and "same-family" not in brief.lower()
    )  # who wrote it, and why, stay out


def test_report_outside_the_workspace_is_refused_before_a_session_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    (tmp_path / "b.md").write_text("do X")
    argv = ["run", "claude", "t", str(tmp_path / "b.md"), str(tmp_path / "r.md")]
    assert omnigent_agent.main(argv) == 1
    assert "outside the child's workspace" in capsys.readouterr().err
    assert og.sessions == {}


def test_workspace_names_the_child_s_directory_and_bounds_its_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A lead for a change across two repos works in their parent; its report sits in the
    # starter's own tmp/loop/, inside both workspaces.
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    (tmp_path / "a" / "tmp").mkdir(parents=True)
    (tmp_path / "b").mkdir()
    monkeypatch.chdir(tmp_path / "a")
    (tmp_path / "brief.md").write_text("do X")
    argv = ["start", "claude", "t", str(tmp_path / "brief.md"), "tmp/lead.md", "--top-level"]
    assert omnigent_agent.main([*argv, "--workspace", ".."]) == 0
    assert og.workspaces == [str(tmp_path.resolve())]
    outside = [
        "start",
        "claude",
        "t2",
        str(tmp_path / "brief.md"),
        "tmp/x.md",
        "--workspace",
        "../b",
    ]
    assert omnigent_agent.main(outside) == 1
    assert f"outside the child's workspace {(tmp_path / 'b').resolve()}" in capsys.readouterr().err
    assert len(og.sessions) == 1


def test_send_bounds_the_report_by_the_session_s_own_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A follow-up sent from another repo's checkout: the child works where it was started.
    og = FakeOmnigent(reply="ok")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    (tmp_path / "child").mkdir()
    (tmp_path / "elsewhere").mkdir()
    sid = og.create("claude", "t", workspace=str(tmp_path / "child"))
    monkeypatch.chdir(tmp_path / "elsewhere")
    (tmp_path / "m.md").write_text("fix it")
    report = tmp_path / "child" / "r.md"
    monkeypatch.setattr(
        omnigent_agent, "wait", lambda *a, **k: (report.write_text("done"), str(report))[1]
    )
    assert omnigent_agent.main(["send", sid, str(tmp_path / "m.md"), str(report)]) == 0
    outside = tmp_path / "elsewhere" / "r.md"
    assert omnigent_agent.main(["send", sid, str(tmp_path / "m.md"), str(outside)]) == 1
    assert (
        f"outside the child's workspace {(tmp_path / 'child').resolve()}" in capsys.readouterr().err
    )


def test_send_confirms_answer_on_a_full_rolling_page(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    og.sessions[sid] = [{"id": f"old{n}", "type": "function_call"} for n in range(100)]
    newest = og.items
    og.items = lambda s: newest(s)[-100:]  # type: ignore[method-assign]
    report = tmp_path / "r.md"
    omnigent_agent.question_of(report).write_text("which base?")
    omnigent_agent.send(og, sid, "use main", report, 0)
    assert not omnigent_agent.question_of(report).exists()


def test_undelivered_answer_keeps_the_question(tmp_path: Path) -> None:
    og = FakeOmnigent(deaf={0})
    sid = og.create("claude", "t")
    report = tmp_path / "r.md"
    omnigent_agent.question_of(report).write_text("which base?")
    with pytest.raises(omnigent_agent.Gone):
        omnigent_agent.send(og, sid, "use main", report, 0)
    assert omnigent_agent.question_of(report).read_text() == "which base?"


def test_retry_after_surviving_child_uses_a_new_title(tmp_path: Path) -> None:
    og = FakeOmnigent(deaf={0})
    titles: list[str] = []
    create = og.create
    og.create = (
        lambda agent, title, model=None, top_level=False, workspace=None, permission_mode=None, host_id=None, role=None: (
            titles.append(title) or create(agent, title)
        )
    )  # type: ignore[method-assign]
    og.fail.add("archive")
    omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert titles == ["t", "t-r2"]


def test_outside_a_session_the_server_is_named_or_the_one_login_never_config_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, tokens = tmp_path / "config.yaml", tmp_path / "auth_tokens.json"
    config.write_text("host:\n  host_id: host_1\nlocal_server_port: 6767\n")
    monkeypatch.setattr(omnigent_agent, "CONFIG", config)
    monkeypatch.setattr(omnigent_agent, "AUTH_TOKENS", tokens)
    monkeypatch.delenv("RUNNER_SERVER_URL", raising=False)
    tokens.write_text('{"https://omnigent.example/": {}}')
    assert omnigent_agent.Omnigent().base == "https://omnigent.example"
    tokens.write_text('{"https://a.example": {}, "https://b.example": {}}')  # a guess: refuse
    config.write_text("server: https://named.example\nhost:\n  host_id: host_1\n")
    with pytest.raises(omnigent_agent.Fail, match="which Omnigent server"):
        omnigent_agent.Omnigent()  # config.yaml's server: is a default, not an answer
    assert omnigent_agent.Omnigent("https://a.example").base == "https://a.example"


def test_a_session_acts_on_its_own_server_over_the_config_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, tokens = tmp_path / "config.yaml", tmp_path / "auth_tokens.json"
    config.write_text("server: https://personal.example\nhost:\n  host_id: host_1\n")
    tokens.write_text('{"https://login.example": {}}')  # a lone login loses to the session too
    monkeypatch.setattr(omnigent_agent, "CONFIG", config)
    monkeypatch.setattr(omnigent_agent, "AUTH_TOKENS", tokens)
    monkeypatch.setenv("RUNNER_SERVER_URL", "https://work.example/")
    assert omnigent_agent.Omnigent().base == "https://work.example"
    assert omnigent_agent.Omnigent("https://personal.example").base == "https://personal.example"


def test_a_get_that_times_out_once_is_retried_and_wait_returns_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io
    import json

    report = tmp_path / "r.md"
    answers = iter(
        [
            TimeoutError("timed out"),
            {"status": "running", "pending_elicitations": []},
            {"data": [{"type": "message", "role": "user", "content": []}]},
        ]
    )

    def urlopen(req: object, timeout: float) -> io.BytesIO:
        answer = next(answers, None)
        if isinstance(answer, Exception):
            raise answer
        report.write_text("done")  # written while the read was retried
        return io.BytesIO(json.dumps(answer or {}).encode())

    monkeypatch.setattr(omnigent_agent, "urlopen", urlopen)
    monkeypatch.setattr(omnigent_agent, "RETRY_SECONDS", (0, 0))
    og = object.__new__(omnigent_agent.Omnigent)
    og.base, og._token = "http://omnigent.test", "synthetic"
    assert omnigent_agent.wait(og, "s0", report, timeout=5) == str(report)


def test_a_post_that_times_out_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = []

    def urlopen(req: object, timeout: float) -> None:
        posts.append(req)
        raise TimeoutError("timed out")

    monkeypatch.setattr(omnigent_agent, "urlopen", urlopen)
    monkeypatch.setattr(omnigent_agent, "RETRY_SECONDS", (0, 0))
    og = object.__new__(omnigent_agent.Omnigent)
    og.base, og._token = "http://omnigent.test", "synthetic"
    with pytest.raises(omnigent_agent.Fail, match="POST /x: TimeoutError"):
        og.call("POST", "/x", {})
    assert len(posts) == 1


@pytest.mark.parametrize(
    "error",
    [
        ssl.SSLEOFError(8, "EOF occurred in violation of protocol"),
        URLError(ConnectionRefusedError(61, "Connection refused")),
        HTTPError("http://omnigent.test/x", 503, "Service Unavailable", Message(), None),
    ],
)
def test_a_get_retries_a_server_restarting_and_a_post_does_not(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    calls: list[str] = []

    def urlopen(req: Request, timeout: float) -> io.BytesIO:
        calls.append(req.get_method())
        if len(calls) == 1:
            raise error
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(omnigent_agent, "urlopen", urlopen)
    monkeypatch.setattr(omnigent_agent, "RETRY_SECONDS", (0, 0))
    og = object.__new__(omnigent_agent.Omnigent)
    og.base, og._token = "http://omnigent.test", "synthetic"
    assert og.call("GET", "/x") == {"ok": True}
    calls.clear()
    with pytest.raises(omnigent_agent.Fail):
        og.call("POST", "/x", {})
    assert calls == ["POST"]


def test_a_get_answered_404_fails_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def urlopen(req: Request, timeout: float) -> None:
        calls.append(req)
        raise HTTPError("http://omnigent.test/x", 404, "Not Found", Message(), None)

    monkeypatch.setattr(omnigent_agent, "urlopen", urlopen)
    monkeypatch.setattr(omnigent_agent, "RETRY_SECONDS", (0, 0))
    og = object.__new__(omnigent_agent.Omnigent)
    og.base, og._token = "http://omnigent.test", "synthetic"
    with pytest.raises(omnigent_agent.Fail, match="HTTP 404"):
        og.call("GET", "/x")
    assert len(calls) == 1


def test_an_http_error_shows_its_body_s_reason_and_a_stalled_body_costs_only_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stall = threading.Event()

    class Stalled(io.RawIOBase):
        def readable(self) -> bool:
            return True

        def readinto(self, b: bytearray) -> int:
            stall.wait(5)
            return 0

    for body, line in (
        (b'{"error": {"code": "invalid_input", "message": "bad role path"}}', "bad role path"),
        (b'{"detail": [{"loc": ["body", "agent_id"]}]}', '[{"loc": ["body", "agent_id"]}]'),
        (b"plain\n  text " + b"x" * 3000, "plain text " + "x" * (2048 - 13)),
        (b"", None),
        (None, "(body not read within 0.3s)"),
    ):
        fp = io.BufferedReader(Stalled()) if body is None else io.BytesIO(body)

        def urlopen(req: Request, timeout: float, fp: object = fp) -> None:
            raise HTTPError("http://omnigent.test/x", 400, "Bad Request", Message(), fp)

        monkeypatch.setattr(omnigent_agent, "urlopen", urlopen)
        monkeypatch.setattr(omnigent_agent, "ERROR_BODY_SECONDS", 0.3)
        og = object.__new__(omnigent_agent.Omnigent)
        og.base, og._token = "http://omnigent.test", "synthetic"
        began = time.monotonic()
        with pytest.raises(omnigent_agent.Fail) as e:
            og.call("POST", "/v1/sessions", {})
        assert time.monotonic() - began < 1.5
        head = "POST /v1/sessions: HTTP 400 Bad Request"
        assert str(e.value) == (
            head if line is None else f"{head}{':' * (body is not None)} {line}"
        )
    stall.set()


def test_a_create_that_failed_after_the_server_made_the_session_briefs_that_session(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent()
    og.fail.add("create")
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert sid == "s0" and list(og.sessions) == ["s0"] and og.posts == 1


def test_a_failed_create_with_no_session_made_fails_the_start(tmp_path: Path) -> None:
    og = FakeOmnigent()
    og.fail.add("create")
    og.find = lambda title, after, top_level=False: None  # type: ignore[method-assign]
    with pytest.raises(omnigent_agent.Fail, match="start failed: POST /v1/sessions"):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.posts == 0


@pytest.mark.parametrize(
    ("helpers", "subscriptions_fail", "expected"),
    [
        (
            {"cloud": (300, False)},
            False,
            300.0,
        ),  # a running cloud worker, no child: its updates count
        (
            {"cloud": (50, False)},
            False,
            100.0,
        ),  # an idle helper holds nothing off: the child is newer
        ({"done": (500, True)}, False, 100.0),  # an archived helper counts for nothing
        ({"gone": (500, False)}, False, 100.0),  # a deleted one too
        ({"cloud": (300, False)}, True, 100.0),  # no subscriptions endpoint: the children alone
    ],
)
def test_active_counts_a_subscribed_top_level_helper_like_a_child(
    monkeypatch: pytest.MonkeyPatch,
    helpers: dict[str, tuple[int, bool]],
    subscriptions_fail: bool,
    expected: float,
) -> None:
    def call(self, method: str, path: str, body: object = None) -> object:
        if path == "/v1/sessions/lead/child_sessions?limit=100":
            return {"data": [{"id": "kid", "updated_at": 100}]}
        if path == "/v1/sessions/lead/subscriptions":
            if subscriptions_fail:
                raise omnigent_agent.Fail("GET subscriptions: HTTP 404 Not Found")
            return {"data": [{"subscriber_id": "lead", "session_id": h} for h in helpers]}
        sid = path.removeprefix("/v1/sessions/")
        if sid == "gone":
            raise omnigent_agent.Gone("GET: HTTP 404 Not Found")
        updated, archived = helpers[sid]
        return {"id": sid, "updated_at": updated, "archived": archived}

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    assert object.__new__(omnigent_agent.Omnigent).active("lead") == expected  # no login read


def test_the_lookup_matches_the_title_under_the_parent_created_after_the_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def call(self, method: str, path: str, body: object = None) -> object:
        assert path == "/v1/sessions/coord/child_sessions?limit=100"
        return {
            "data": [
                {"id": "old", "title": "t", "created_at": 99},
                {"id": "other", "title": "t-x", "created_at": 200},
                {"id": "new", "title": "t", "created_at": 100},
            ]
        }

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    og = object.__new__(omnigent_agent.Omnigent)
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "coord")
    assert og.find("t", 100) == "new"
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID")
    assert og.find("t", 100) is None  # top level: no parent to look under


def test_a_top_level_lookup_reads_the_projects_top_level_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths: list[str] = []

    def call(self, method: str, path: str, body: object = None) -> object:
        paths.append(path)
        if path == "/v1/projects":
            return {"data": [{"name": "my shop", "id": "p1"}]}
        return {
            "data": [
                {"id": "old", "title": "t", "created_at": 99},
                {"id": "new", "title": "t", "created_at": 100},
            ]
        }

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "coord")
    og = object.__new__(omnigent_agent.Omnigent)
    monkeypatch.setenv("OMNIGENT_PROJECT", "my_shop")  # lists under the project's exact name
    assert og.find("t", 100, top_level=True) == "new"
    assert paths[-1] == "/v1/sessions?kind=default&project=my%20shop&limit=100"
    monkeypatch.setenv("OMNIGENT_PROJECT", "no-such-group")  # created unfiled: look there
    og.find("t", 100, top_level=True)
    assert paths[-1] == "/v1/sessions?kind=default&project=&limit=100"


# The default preamble as it was before --top-level existed: a worker's or verifier's brief.
DEFAULT_PREAMBLE = """\
The owner authorized this task; do it now, without asking for a go-ahead. This file is your brief.
{role}A long run starts detached (in its own session, `perl -MPOSIX=setsid -e 'fork and exit; setsid; exec @ARGV' <cmd>`, since macOS has no `setsid`; log, pid and exit code in files; a gate your role file says to run bare is the exception, since an allow rule matches only a plain command) and is waited on up to a total budget you state, in as few calls as you can, each blocking close to the tool's limit (the longest yield the harness allows on a running command, or a sleep loop that checks the log for its exit line), never short polls, since each call re-reads the whole context: a held lock can outlast a foreground call, and a low-memory reaper stops in-session background shells. Never end a turn saying you wait, since a background command's completion never wakes you.
Write your final report to {report}, once, when done: keep any progress notes in another file, since the report path is read as your answer.
Never address the owner. If you need a decision the brief, the spec and the repo do not settle, write the question to {report}.question, reply with only that path, and stop: the answer comes as your next message.
When done, reply with only the report path.

"""


def create_bodies(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    bodies: list[dict] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        if body is not None:
            bodies.append(body)
        return {
            "/v1/agents": [{"name": omnigent_agent.AGENTS["claude"], "id": "a1"}],
            "/v1/agents?scope=user": [],
            "/v1/projects": {"data": [{"name": "shop", "id": "p1"}]},
        }.get(path, {"id": "s1"})

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    monkeypatch.setattr(omnigent_agent, "repo_name", lambda: "shop")
    monkeypatch.delenv("OMNIGENT_PROJECT", raising=False)
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "coord")
    return bodies


def test_without_top_level_the_create_body_and_brief_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bodies = create_bodies(monkeypatch)
    omnigent_agent.Omnigent().create("claude", "t")
    omnigent_agent.Omnigent().create("claude", "t", workspace="/w")
    assert bodies[1]["workspace"] == "/w" and bodies.pop()["project_id"] == "p1"
    assert bodies == [
        {
            "agent_id": "a1",
            "title": "t",
            "host_id": "h",
            "workspace": os.getcwd(),
            "project_id": "p1",
            "parent_session_id": "coord",
        }
    ]
    assert omnigent_agent.PREAMBLE == DEFAULT_PREAMBLE
    og = FakeOmnigent()
    omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", "roles/worker.md", 0)
    assert (
        tmp_path / "r.md.brief"
    ).read_text() == "AGENT_SIGNATURE=cc/?/?\n" + DEFAULT_PREAMBLE.format(
        report=tmp_path / "r.md", role="Your role file is roles/worker.md; read it first.\n"
    ) + "do X"
    assert og.top_level == [False] and og.roles == ["roles/worker.md"]


def test_a_top_level_start_has_no_parent_and_the_lead_preamble(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bodies = create_bodies(monkeypatch)
    omnigent_agent.Omnigent().create("claude", "t", top_level=True)
    assert "parent_session_id" not in bodies[-1] and bodies[-1]["project_id"] == "p1"
    og = FakeOmnigent()
    og.fail.add("create")  # the lookup after a failed create is the top-level one too
    sid, _ = omnigent_agent.start(
        og, "claude", "t", "do X", tmp_path / "r.md", None, 0, top_level=True
    )
    assert og.top_level == [True, True]
    text = (tmp_path / "r.md.brief").read_text()
    assert (
        text
        == "AGENT_SIGNATURE=cc/?/?\n"
        + omnigent_agent.LEAD_PREAMBLE.format(report=tmp_path / "r.md", role="")
        + "do X"
    )
    assert "owner's own words" in text and "ask them here" in text
    assert "USER NEEDED" not in text and "needs-owner" not in text
    assert "setsid; exec @ARGV" in text and f"final report to {tmp_path / 'r.md'}" in text
    assert "authorized" not in text and "Never address" not in text and ".question" not in text
    assert omnigent_agent.text_of(og.sessions[sid][1]).startswith("Work on t: read ")


def test_a_top_level_start_subscribes_its_starter_to_the_lead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("OMNIGENT_SESSION_ID", "OMNIGENT_TERMINAL_LAUNCH_SESSION_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "chief")
    og = FakeOmnigent()
    lead, _ = omnigent_agent.start(
        og, "claude", "t", "do X", tmp_path / "a.md", None, 0, top_level=True
    )
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "child")  # a child of the chief: it, not the chief
    own, _ = omnigent_agent.start(
        og, "codex", "s", "do V", tmp_path / "e.md", None, 0, top_level=True
    )
    assert og.subscriptions.pop() == ("child", own)
    monkeypatch.delenv("OMNIGENT_SESSION_ID")
    omnigent_agent.start(og, "claude", "w", "do Y", tmp_path / "b.md", None, 0)
    assert og.subscriptions == [("chief", lead)]  # a child's parent hears it already
    og.fail.add("subscribe")  # an Omnigent without subscriptions: the lead still starts
    other, _ = omnigent_agent.start(
        og, "claude", "u", "do Z", tmp_path / "c.md", None, 0, top_level=True
    )
    assert other in og.sessions and og.archived == []
    assert f"not subscribed to {other}" in capsys.readouterr().err
    # started from no session, or from a shell that does not name it (a native Codex one)
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID")
    og.fail.discard("subscribe")
    last, _ = omnigent_agent.start(
        og, "claude", "v", "do W", tmp_path / "d.md", None, 0, top_level=True
    )
    assert og.subscriptions == [("chief", lead)]
    assert f"not subscribed to {last}" in capsys.readouterr().err


def test_run_refuses_top_level_before_a_session_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    argv = ["run", "claude", "t", str(tmp_path / "b.md"), str(tmp_path / "r.md"), "--top-level"]
    assert omnigent_agent.main(argv) == 1
    assert not og.sessions and "use start --top-level" in capsys.readouterr().err


def test_a_found_session_that_already_has_the_brief_is_not_briefed_twice(tmp_path: Path) -> None:
    og = FakeOmnigent()
    og.fail.add("create")
    find = og.find

    def briefed(title: str, after: float, top_level: bool = False) -> str | None:
        sid = find(title, after)
        brief = tmp_path / "r.md.brief"
        og.land(
            sid,
            f"Work on t: read {brief} and do what it says.",
        )
        return sid

    og.find = briefed  # type: ignore[method-assign]
    omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.posts == 0


def test_a_turn_that_ends_without_the_report_is_nudged_once_then_the_report_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(status="idle")  # the brief stays last: the turn ended with no output
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", report, None, 0)
    monkeypatch.setattr(omnigent_agent, "IDLE_GRACE_SECONDS", 0)
    send = og.send

    def answer(s: str, text: str) -> None:
        send(s, text)
        report.write_text("done")

    og.send = answer  # type: ignore[method-assign]
    assert omnigent_agent.wait(og, sid, report) == str(report)
    assert og.posts == 2
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == omnigent_agent.NUDGE.format(
        report=report
    )


def test_a_second_turn_that_ends_without_the_report_fails(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="waiting for the background command")
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", report, None, 0)
    with pytest.raises(omnigent_agent.Fail, match="(?s)ended \\(idle\\) without .*background"):
        omnigent_agent.wait(og, sid, report)
    assert og.posts == 2  # the brief and one nudge


def fake_gh(monkeypatch: pytest.MonkeyPatch, comments: dict[str, dict]) -> list[tuple[str, ...]]:
    """``gh`` faked for a checkout of ``o/r``: ``repo view`` names it, ``api`` answers a comment
    of ``comments`` by its id. Returns the calls."""
    calls: list[tuple[str, ...]] = []

    def gh(*args: str) -> str:
        calls.append(args)
        if args[:2] == ("repo", "view"):
            return "o/r\n"
        return json.dumps(comments[args[1].rsplit("/", 1)[1]])

    monkeypatch.setattr(omnigent_agent, "gh", gh)
    return calls


def on_pr(n: int, body: str = "", repo: str = "o/r") -> dict:
    return {"issue_url": f"https://api.github.com/repos/{repo}/issues/{n}", "body": body}


def test_a_cloud_worker_s_report_is_the_pr_comment_its_last_message_links(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="https://github.com/o/r/pull/7#issuecomment-42")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    calls = fake_gh(monkeypatch, {"42": on_pr(7, "Head: abc\nGates: 0\n")})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    argv = ["run", "claude-cloud", "t", "b.md", "r.md", "--pr", "7", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == 0
    assert capsys.readouterr().out.splitlines()[-1] == str(tmp_path / "r.md")
    assert (tmp_path / "r.md").read_text() == "Head: abc\nGates: 0\n"
    assert ("api", "repos/o/r/issues/comments/42") in calls and og.posts == 1  # no nudge
    brief = omnigent_agent.text_of(og.sessions["s0"][1])
    assert "PR #7" in brief and "gh api repos/{owner}/{repo}/issues/7/comments" in brief
    assert "setsid; exec @ARGV" in brief  # long runs start detached
    for nudge in (omnigent_agent.NUDGE, omnigent_agent.PR_NUDGE):
        assert "detached" in nudge and "foreground" not in nudge
    assert str(tmp_path / "r.md") not in brief  # a host path the cloud can't write


def checkout_with_worktree(tmp_path: Path, pin: dict | None) -> tuple[Path, Path]:
    """A main checkout, with ``pin`` as its settings.local.json when given, and a worktree of it."""
    main, tree = (
        tmp_path / "main checkout",
        tmp_path / "the tree",
    )  # spaces: paths split on lines only
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(main)]
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "i"], check=True)
    subprocess.run([*git, "worktree", "add", "-q", "-b", "w", str(tree)], check=True)
    if pin is not None:
        (main / ".claude").mkdir()
        (main / ".claude" / "settings.local.json").write_text(json.dumps(pin))
    return main, tree


def start_cloud(
    og: FakeOmnigent, workspace: Path, agent: str = "claude-cloud", title: str = "t"
) -> int:
    (workspace / "b.md").write_text("do X")
    argv = ["start", agent, title, "b.md", f"tmp/{title}.md", "--confirm-seconds", "0"]
    return omnigent_agent.main([*argv, "--workspace", str(workspace)])


def test_a_cloud_start_from_a_worktree_takes_its_main_checkout_s_environment_pin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.harnesses = {"claude-cloud": "acp:claude-cloud"}
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    _, tree = checkout_with_worktree(tmp_path, {"remote": {"defaultEnvironmentId": "env_a"}})
    monkeypatch.chdir(tree)
    assert start_cloud(og, tree) == 0
    settings = tree / ".claude" / "settings.local.json"
    assert json.loads(settings.read_text()) == {"remote": {"defaultEnvironmentId": "env_a"}}
    assert "env_a" in capsys.readouterr().err and len(og.sessions) == 1
    # a worktree already pinned keeps its own pin
    settings.write_text(json.dumps({"remote": {"defaultEnvironmentId": "env_b"}}))
    assert start_cloud(og, tree, title="t2") == 0
    assert json.loads(settings.read_text()) == {"remote": {"defaultEnvironmentId": "env_b"}}


def test_a_worktree_s_other_settings_stay_when_it_gains_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.harnesses = {"claude-cloud": "acp:claude-cloud"}
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    _, tree = checkout_with_worktree(tmp_path, {"remote": {"defaultEnvironmentId": "env_a"}})
    (tree / ".claude").mkdir()
    settings = tree / ".claude" / "settings.local.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "remote": {"x": 1}}))
    monkeypatch.chdir(tree)
    assert start_cloud(og, tree) == 0
    assert json.loads(settings.read_text()) == {
        "permissions": {"allow": ["Bash(ls)"]},
        "remote": {"x": 1, "defaultEnvironmentId": "env_a"},
    }


def test_a_cloud_start_with_no_environment_pin_is_refused_before_a_session_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.harnesses = {"claude-cloud": "acp:claude-cloud"}
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    main, tree = checkout_with_worktree(tmp_path, None)
    for workspace in (tree, main):  # a worktree, then a checkout that is no worktree
        monkeypatch.chdir(workspace)
        assert start_cloud(og, workspace) == 1
        err = capsys.readouterr().err
        assert "default environment" in err and "defaultEnvironmentId" in err
        assert not (workspace / ".claude" / "settings.local.json").exists()
    assert og.sessions == {}


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_a_native_start_needs_no_environment_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, agent: str
) -> None:
    og = FakeOmnigent()
    og.harnesses = {"claude-cloud": "acp:claude-cloud"}
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    _, tree = checkout_with_worktree(tmp_path, {"remote": {"defaultEnvironmentId": "env_a"}})
    monkeypatch.chdir(tree)
    assert start_cloud(og, tree, agent) == 0
    assert not (tree / ".claude").exists() and len(og.sessions) == 1


@pytest.mark.parametrize(
    "marker", ["UNPOSTED REPORT", "`UNPOSTED REPORT`", "**UNPOSTED REPORT**", "__UNPOSTED REPORT__"]
)
def test_a_cloud_worker_that_could_not_post_its_report_has_it_posted_from_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    # the report links an earlier comment on its PR, as a pass-2 report does
    body = "Rerun https://github.com/o/r/pull/7#issuecomment-5\nBranch: claude/x at abc\nGates: 0\n"
    og = FakeOmnigent(reply=f"{marker}\n{body}")
    calls = fake_gh(
        monkeypatch,
        {
            "5": on_pr(7, "an old report"),
            "comments": "https://github.com/o/r/pull/7#issuecomment-9",
        },
    )
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude-cloud", "t", "do X", report, None, 0, pr=7)
    brief = omnigent_agent.text_of(og.sessions[sid][1])
    assert "`claude/…` branch this session started on" in brief and omnigent_agent.UNPOSTED in brief
    assert omnigent_agent.wait(og, sid, report, pr=7) == str(report)
    assert report.read_text() == body and og.posts == 1  # no nudge
    assert calls[-1] == (
        "api",
        "repos/o/r/issues/7/comments",
        "-f",
        f"body={body}",
        "--jq",
        ".html_url",
    )
    posted = len(calls)
    assert omnigent_agent.wait(og, sid, report, pr=7) == str(report)  # a re-attached wait
    assert len(calls) == posted  # posts nothing again


@pytest.mark.parametrize(
    "link",
    [
        "https://github.com/o/r/pull/8#issuecomment-1",  # another PR
        "https://github.com/another/repo/pull/7#issuecomment-2",  # another repo, the same number
        "https://github.com/o/r/pull/7#issuecomment-3",  # a comment GitHub files on PR 8
    ],
)
def test_a_cloud_worker_s_second_turn_without_a_comment_on_its_pr_fails(
    link: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply=f"pushed; see {link}")
    fake_gh(monkeypatch, {"1": on_pr(8), "2": on_pr(7, repo="another/repo"), "3": on_pr(8)})
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude-cloud", "t", "do X", report, None, 0, pr=7)
    with pytest.raises(omnigent_agent.Fail, match="without a report comment on PR #7"):
        omnigent_agent.wait(og, sid, report, pr=7)
    assert og.posts == 2 and not report.exists()
    assert omnigent_agent.PR_NUDGE.format(pr=7) in [
        omnigent_agent.text_of(i) for i in og.sessions[sid]
    ]


@pytest.mark.parametrize(
    "reply, code",
    [
        ("fixed; https://github.com/o/r/pull/7#issuecomment-42", 1),  # the turn before's comment
        ("fixed, pushed", 1),  # no comment
        ("https://github.com/o/r/pull/7#issuecomment-43", 0),  # a fresh one
    ],
)
def test_a_cloud_worker_s_follow_up_takes_only_a_report_comment_newer_than_its_report(
    reply: str, code: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply=reply)
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    old, fresh = on_pr(7, "the first report"), on_pr(7, "the fix report")
    old["created_at"], fresh["created_at"] = "2001-01-01T00:00:00Z", "2001-09-09T02:00:00Z"
    fake_gh(monkeypatch, {"42": old, "43": fresh})
    monkeypatch.chdir(tmp_path)
    sid = og.create("claude-cloud", "t")
    report = tmp_path / "r.md"
    report.write_text("the first report")
    os.utime(report, (1e9, 1e9))  # 2001-09-09T01:46:40Z, written by the first turn's wait
    (tmp_path / "fix.md").write_text("fix ST1, read the review on PR #7")
    argv = ["send", sid, "fix.md", "r.md", "--pr", "7", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == code
    assert report.read_text() == ("the fix report" if code == 0 else "the first report")
    assert og.posts == 1 + code  # the follow-up, and a nudge for a turn without a fresh one


def test_a_top_level_cloud_worker_on_another_host_gets_the_pr_preamble_and_reports_on_its_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # started from a host without the cloud harness: --host needs --top-level, which kept the lead
    # preamble and refused --pr
    og = FakeOmnigent(reply="https://github.com/o/r/pull/7#issuecomment-42")
    og.host = lambda name: "far"  # type: ignore[method-assign]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    fake_gh(monkeypatch, {"42": on_pr(7, "Branch: claude/x at abc\n")})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    argv = ["start", "claude-cloud", "t", "b.md", "r.md", "--top-level", "--host", "box"]
    argv += ["--workspace", "/there/repo", "--pr", "7", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == 0
    assert og.top_level == [True] and og.workspaces == ["/there/repo"]
    brief = omnigent_agent.text_of(og.sessions["s0"][1])
    assert brief.startswith("Work on t. Your brief:") and "issues/7/comments" in brief
    assert "owner's own words" not in brief  # not the lead preamble
    # the two VM facts: what the clone holds, and the foreground limit
    assert "checked out in the workspace this session started from" in brief
    assert "git fetch origin pull/7/head" in brief and "stops at 10 minutes" in brief
    # its report is the PR comment, written here although the session runs there
    assert omnigent_agent.main(["wait", "s0", "r.md", "--pr", "7"]) == 0
    assert (tmp_path / "r.md").read_text() == "Branch: claude/x at abc\n"


def test_wait_keep_leaves_a_delivered_worker_open_for_a_relay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(reply="https://github.com/o/r/pull/7#issuecomment-42")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    fake_gh(monkeypatch, {"42": on_pr(7, "done")})
    monkeypatch.chdir(tmp_path)
    relay = ["relay", "fix the finding", "--confirm-seconds", "0"]
    for title, keep, archived, code in (
        ("t0", ["--keep"], [], 0),
        ("t1", [], ["s1"], omnigent_agent.GONE),
    ):
        sid, _ = omnigent_agent.start(
            og, "claude-cloud", title, "do X", tmp_path / "r", None, 0, pr=7
        )
        assert omnigent_agent.main(["wait", sid, f"{title}.md", "--pr", "7", *keep]) == 0
        assert og.archived == archived
        assert omnigent_agent.main([relay[0], sid, *relay[1:]]) == code
    assert "s1 is archived" in capsys.readouterr().err


def test_run_keep_leaves_a_delivered_worker_open_for_a_relay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="https://github.com/o/r/pull/7#issuecomment-42")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    fake_gh(monkeypatch, {"42": on_pr(7, "done")})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    for title, keep, archived in (("t0", ["--keep"], []), ("t1", [], ["s1"])):
        argv = ["run", "claude-cloud", title, "b.md", f"{title}.md", "--pr", "7", *keep]
        assert omnigent_agent.main([*argv, "--confirm-seconds", "0"]) == 0
        assert og.archived == archived


def test_send_pr_delivers_to_a_session_whose_workspace_is_on_another_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="https://github.com/o/r/pull/7#issuecomment-43")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    fake_gh(monkeypatch, {"43": on_pr(7, "the fix report")})
    monkeypatch.chdir(tmp_path)
    sid = og.create("claude-cloud", "t", workspace="/home/elsewhere/repo")  # no such path here
    (tmp_path / "fix.md").write_text("fix ST1")
    argv = ["send", sid, "fix.md", "tmp/r.md", "--pr", "7", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == 0
    assert (tmp_path / "tmp" / "r.md").read_text() == "the fix report"


def test_a_start_on_another_host_does_not_wait_on_this_host_s_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "capacity", lambda: (False, "cpu 2% idle"))
    monkeypatch.setattr(omnigent_agent, "CAPACITY_WAIT_SECONDS", 0)
    og = FakeOmnigent()
    sid, _ = omnigent_agent.start(
        og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0, top_level=True, host_id="far"
    )
    assert sid in og.sessions
    with pytest.raises(omnigent_agent.Fail, match="host over capacity"):
        omnigent_agent.start(
            og, "claude", "u", "do Y", tmp_path / "u.md", None, 0, top_level=True, host_id="h"
        )


def test_run_with_a_report_older_than_the_launch_waits_for_a_new_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    report = tmp_path / "r.md"
    report.write_text("the pass before")
    os.utime(report, (1, 1))
    (tmp_path / "b.md").write_text("fix C1")
    argv = ["run", "claude", "t", "b.md", "r.md", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == 1  # the old report is not taken
    assert "without" in capsys.readouterr().err

    info = og.info
    og.info = lambda s: (report.write_text("fixed"), info(s))[1]  # type: ignore[method-assign]
    assert omnigent_agent.main(argv) == 0
    assert capsys.readouterr().out.splitlines()[-1] == str(report)


def test_run_takes_a_report_written_within_a_clock_tick_of_the_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The kernel stamps files from a coarse clock that lags time.time_ns() by up to a tick.
    monkeypatch.setattr(omnigent_agent.time, "time_ns", lambda: 2**62)
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    info = og.info
    og.info = lambda s: ((tmp_path / "r.md").write_text("ok"), info(s))[1]  # type: ignore[method-assign]
    argv = ["run", "claude", "t", "b.md", "r.md", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == 0


def test_a_brief_with_an_empty_backtick_span_is_refused_before_a_session_exists(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent()
    with pytest.raises(omnigent_agent.Fail, match="line 2 has an empty `` span"):
        omnigent_agent.start(og, "claude", "t", "edit\nthe `` file", tmp_path / "r.md", None, 0)
    assert og.sessions == {}
    omnigent_agent.start(og, "claude", "t", "```sh\nls\n```", tmp_path / "r.md", None, 0)


def test_a_failed_session_reports_its_last_task_error_and_runner_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(status="failed")
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    info = og.info
    og.info = lambda s: {  # type: ignore[method-assign]
        **info(s),
        "id": s,
        "parent_session_id": "coord",
        "last_task_error": {"message": "claude exited: too many open files"},
    }
    monkeypatch.setattr(omnigent_agent, "RUNNER_LOGS", tmp_path)
    (tmp_path / "runner-coord-1.log").write_text("")
    with pytest.raises(
        omnigent_agent.Fail,
        match=f"(?s)ended \\(failed\\): claude exited: too many open files.*{tmp_path}/runner-coord-1.log",
    ):
        omnigent_agent.wait(og, sid, tmp_path / "r.md")
    assert og.posts == 1  # a failed session is not nudged


def test_a_codex_verifier_defaults_to_its_model_unless_one_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models = []
    og = FakeOmnigent(reply="done")
    create = og.create
    og.create = lambda a, t, m=None, top=False, w=None, p=None, h=None, r=None: (
        models.append(m),
        create(a, t, m),
    )[1]  # type: ignore[method-assign]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.delenv("OMNIGENT_MODEL_CODEX", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("verify")
    base = ["start", "codex", "t", "b.md", "r.md", "--confirm-seconds", "0"]
    omnigent_agent.main([*base, "--role", "verifier.md"])
    omnigent_agent.main([*base[:2], "t2", *base[3:]])
    monkeypatch.setenv("OMNIGENT_MODEL_CODEX", "named")
    omnigent_agent.main([*base[:2], "t3", *base[3:], "--role", "verifier.md"])
    omnigent_agent.main([*base[:2], "t4", *base[3:], "--role", "verifier.md", "--model", "flag"])
    assert models == [None, None, None, "flag"]  # Omnigent.create reads OMNIGENT_MODEL_CODEX
    assert not hasattr(omnigent_agent, "CODEX_VERIFIER_MODEL")


def test_start_refuses_a_report_already_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "r.md").write_text("the pass before")
    (tmp_path / "b.md").write_text("fix C1")
    argv = ["start", "claude", "t", "b.md", "r.md", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == 1  # its `wait` would take the old report
    assert "already exists" in capsys.readouterr().err and og.sessions == {}


def test_the_nudge_is_awaited_before_the_next_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(status="idle")
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", report, None, 0)
    monkeypatch.setattr(omnigent_agent, "IDLE_GRACE_SECONDS", 0)
    monkeypatch.setattr(omnigent_agent, "POLL_SECONDS", 0)
    late: list[str] = []
    og.send = lambda s, text: late.append(text)  # type: ignore[method-assign]
    items = og.items

    def landing(s: str) -> list[dict]:  # the nudge shows up a few reads after its send
        if late and len(late) < 4:
            late.append("")
        elif late:
            og.land(s, late.pop(0))
            late.clear()
            report.write_text("done")
        return items(s)

    og.items = landing  # type: ignore[method-assign]
    assert omnigent_agent.wait(og, sid, report) == str(report)


class Roster:
    """Sessions for `watch`, each a script of info() snapshots; the last one repeats."""

    def __init__(self, **scripts: list[dict]) -> None:
        self.scripts = {sid: list(s) for sid, s in scripts.items()}
        self.kids: list[str] = []

    def info(self, sid: str) -> dict:
        script = self.scripts[sid]
        return dict(script.pop(0) if len(script) > 1 else script[0], title=f"t-{sid}")

    def items(self, sid: str) -> list[dict]:
        return []

    def children(self, parent: str) -> list[str]:
        return list(self.kids)


def said(role: str, text: str, i: str) -> dict:
    return {"id": i, "type": "message", "role": role, "content": [{"type": "x", "text": text}]}


def test_watch_wakes_on_a_turn_end_with_title_and_last_message() -> None:
    og = Roster(a=[{"status": "running"}, {"status": "running"}, {"status": "idle"}])
    msgs = [[said("user", "go", "1")], [said("user", "go", "1")], [said("assistant", "done", "2")]]
    og.items = lambda sid: msgs.pop(0) if len(msgs) > 1 else msgs[0]  # type: ignore[method-assign]
    assert omnigent_agent.watch(og, ["a"], timeout=5) == ["a t-a: turn ended\nlast message: done"]


def test_watch_ignores_states_it_starts_in_and_the_launch_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(omnigent_agent, "IDLE_GRACE_SECONDS", 3600)
    og = Roster(
        a=[{"status": "idle"}], b=[{"status": "failed", "last_task_error": {"message": "boom"}}]
    )
    with pytest.raises(omnigent_agent.Fail, match="no session changed in 0s: a, b"):
        omnigent_agent.watch(og, ["a", "b"], timeout=0)


def test_watch_reports_an_end_only_once_it_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    # A native Claude session reads idle while quiet mid-turn: the end it shows then is not one.
    monkeypatch.setattr(omnigent_agent, "TURN_END_SECONDS", 30)
    now = [0.0]
    monkeypatch.setattr(omnigent_agent.time, "monotonic", lambda: now[0])
    states = iter(["running", "idle", "running", "idle", "idle", "idle"])
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    og.info = lambda s: {"status": next(states), "title": "lead"}  # type: ignore[method-assign]
    og.items = lambda s: [{"id": "m1", "type": "message", "role": "assistant", "content": []}]  # type: ignore[method-assign]

    def tick(seconds: float) -> None:
        now[0] += 20

    monkeypatch.setattr(omnigent_agent.time, "sleep", tick)
    assert omnigent_agent.watch(og, [sid]) == [f"{sid} lead: turn ended\nlast message: "]
    assert now[0] == 100  # the first idle passed; the second held for 40s


def test_watch_reports_a_prompt_at_once_with_the_tool_call() -> None:
    prompt = {
        "elicitation_id": "e1",
        "params": {"message": "Claude wants to call **Bash**", "content_preview": "Bash(rm x)"},
    }
    og = Roster(a=[{"status": "running", "pending_elicitations": [prompt]}])
    assert omnigent_agent.watch(og, ["a"], timeout=0) == [
        "a t-a: blocked on a prompt: Bash(rm x)\nlast message: (none)"
    ]


def test_watch_reports_a_failure_with_its_error() -> None:
    og = Roster(
        a=[
            {"status": "running"},
            {"status": "failed", "last_task_error": {"code": "x", "message": "runner died"}},
        ]
    )
    assert omnigent_agent.watch(og, ["a"], timeout=5)[0].startswith("a t-a: failed: runner died")


def test_watch_picks_up_a_child_started_after_it(monkeypatch: pytest.MonkeyPatch) -> None:
    og = Roster(k=[{"status": "idle"}])
    og.items = lambda sid: [said("assistant", "report at r.md", "9")]  # type: ignore[method-assign]
    polls = iter([[], ["k"]])
    og.children = lambda parent: next(polls, ["k"])  # type: ignore[method-assign]
    assert omnigent_agent.watch(og, [], parent="p", timeout=5) == [
        "k t-k: turn ended\nlast message: report at r.md"
    ]


class Clock:
    """`time.monotonic` for `watch`, moved on by each poll's sleep."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, step: float) -> None:
        self.now = 1000.0
        monkeypatch.setattr(omnigent_agent.time, "monotonic", lambda: self.now)
        monkeypatch.setattr(
            omnigent_agent.time, "sleep", lambda s: setattr(self, "now", self.now + step)
        )


def test_watch_keeps_an_idle_it_starts_in_past_the_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    Clock(monkeypatch, step=20)
    og = Roster(a=[{"status": "idle"}])
    og.items = lambda sid: [said("user", "go", "1")]  # type: ignore[method-assign]
    with pytest.raises(omnigent_agent.Fail, match="no session changed"):
        omnigent_agent.watch(og, ["a"], timeout=200)


def test_watch_ignores_a_launch_idle_within_the_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    Clock(monkeypatch, step=5)
    flap = [{"status": "running"}, {"status": "idle"}, {"status": "idle"}, {"status": "running"}]
    og = Roster(a=flap)
    og.items = lambda sid: [said("user", "go", "1")]  # type: ignore[method-assign]
    with pytest.raises(omnigent_agent.Fail, match="no session changed"):
        omnigent_agent.watch(og, ["a"], timeout=100)


def test_watch_reports_an_empty_turn_once_past_the_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    Clock(monkeypatch, step=20)
    og = Roster(a=[{"status": "running"}, {"status": "idle"}])
    og.items = lambda sid: [said("user", "go", "1")]  # type: ignore[method-assign]
    assert omnigent_agent.watch(og, ["a"], timeout=200) == [
        "a t-a: turn ended\nlast message: (none)"
    ]


def test_watch_gives_a_follow_up_to_an_idle_baseline_its_own_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Clock(monkeypatch, step=5)
    # idle after a turn (baseline); the follow-up lands while still idle; running; its answer.
    og = Roster(
        a=[{"status": "idle"}, {"status": "idle"}, {"status": "running"}, {"status": "idle"}]
    )
    done = [said("user", "go", "1"), said("assistant", "report at r.md", "2")]
    follow_up = [*done, said("user", "pass 2: fix F1", "3")]
    history = [done, follow_up, follow_up, [*follow_up, said("assistant", "fixed", "4")]]
    og.items = lambda sid: history.pop(0) if len(history) > 1 else history[0]  # type: ignore[method-assign]
    assert omnigent_agent.watch(og, ["a"], timeout=100) == [
        "a t-a: turn ended\nlast message: fixed"
    ]


def test_watch_wakes_when_a_running_session_gains_a_prompt() -> None:
    prompt = {"elicitation_id": "e2", "params": {"message": "Claude wants to call **Bash**"}}
    og = Roster(a=[{"status": "running"}, {"status": "running", "pending_elicitations": [prompt]}])
    assert omnigent_agent.watch(og, ["a"], timeout=5) == [
        "a t-a: blocked on a prompt: Claude wants to call **Bash**\nlast message: (none)"
    ]


def test_a_sub_agent_is_archived_like_a_top_level_session(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(omnigent_agent.Omnigent, "call", lambda self, *c: calls.append(c) or {})
    og = object.__new__(omnigent_agent.Omnigent)
    og.archive("kid")  # the server leaves the parent's shared runner up (omnigent 4dd0af32)
    assert calls == [("PATCH", "/v1/sessions/kid", {"archived": True})]


def test_reap_finishes_done_children_and_keeps_the_busy_ones() -> None:
    prompt = {"elicitation_id": "e1", "params": {"message": "Claude wants to call **Bash**"}}
    states = {
        "idle": {"status": "idle"},
        "failed": {"status": "failed"},
        "running": {"status": "running"},
        "blocked": {"status": "idle", "pending_elicitations": [prompt]},
        "queued": {"status": "idle", "pending_inputs": [{"content": []}]},
        "gone": {"status": "idle", "archived": True},
    }
    og = FakeOmnigent()
    og.info = lambda s: dict(states[s], title=f"t-{s}")  # type: ignore[method-assign]
    og.children = lambda p: list(states)  # type: ignore[attr-defined]
    lines, failed = omnigent_agent.reap(og, [], parent="p")
    assert not failed
    assert og.archived == ["idle", "failed"]
    assert lines == [
        "idle t-idle: archived (idle)",
        "failed t-failed: archived (failed)",
        "running t-running: kept (running)",
        "blocked t-blocked: kept (blocked on a prompt)",
        "queued t-queued: kept (input pending)",
    ]


def test_reap_goes_on_past_a_finish_that_fails() -> None:
    og = FakeOmnigent()
    og.info = lambda s: {"status": "idle", "title": f"t-{s}"}  # type: ignore[method-assign]
    archive = og.archive

    def refuse_a(s: str) -> str:
        if s == "a":
            raise omnigent_agent.Fail("PATCH a: HTTP 503")
        return archive(s)

    og.archive = refuse_a  # type: ignore[method-assign]
    assert omnigent_agent.reap(og, ["a", "b"]) == (
        ["a t-a: finish failed: PATCH a: HTTP 503", "b t-b: archived (idle)"],
        True,
    )
    assert og.archived == ["b"]


def test_reap_exits_1_when_a_finish_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    title = "investigate: finish failed: PATCH"  # a title is not an outcome
    og.info = lambda s: {"status": "idle", "title": title}  # type: ignore[method-assign]
    assert omnigent_agent.main(["reap", "b"]) == 0
    og.info = lambda s: {"status": "idle", "title": f"t-{s}"}  # type: ignore[method-assign]
    capsys.readouterr()
    archive = og.archive

    def refuse_a(s: str) -> None:
        if s == "a":
            raise omnigent_agent.Fail("PATCH a: HTTP 503")
        archive(s)

    og.archive = refuse_a  # type: ignore[method-assign]
    assert omnigent_agent.main(["reap", "a", "c"]) == 1
    assert og.archived == ["b", "c"]
    assert capsys.readouterr().out.splitlines() == [
        "a t-a: finish failed: PATCH a: HTTP 503",
        "c t-c: archived (idle)",
    ]


def test_reap_drops_each_session_it_finishes_from_the_registry_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supervisor would post `archived` into the session that ran the reap (#249)."""
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    states = {"done": "idle", "busy": "running", "env": "idle"}
    og.info = lambda s: {"status": states[s], "title": f"t-{s}"}  # type: ignore[method-assign]
    registry = tmp_path / "registry"
    registry.write_text("".join(f"{s}=/r/{s}.md\tfollow\n" for s in [*states, "other"]))
    at_archive: list[str] = []
    archive = og.archive

    def archiving(s: str) -> None:
        at_archive.append(registry.read_text())
        archive(s)

    og.archive = archiving  # type: ignore[method-assign]
    assert omnigent_agent.main(["reap", "done", "busy", "--registry", str(registry)]) == 0
    assert "done=" not in at_archive[0]
    monkeypatch.setenv("OMNIGENT_SUPERVISE_REGISTRY", str(registry))
    assert omnigent_agent.main(["reap", "env"]) == 0
    assert og.archived == ["done", "env"]
    assert registry.read_text() == "busy=/r/busy.md\tfollow\nother=/r/other.md\tfollow\n"


def test_run_archives_on_its_report_but_not_on_a_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    info = og.info
    og.info = lambda s: ((tmp_path / "r.md").write_text("ok"), info(s))[1]  # type: ignore[method-assign]
    assert (
        omnigent_agent.main(["run", "claude", "t", "b.md", "r.md", "--confirm-seconds", "0"]) == 0
    )
    assert og.archived == ["s0"]
    og.info = lambda s: ((tmp_path / "q.md.question").write_text("which?"), info(s))[1]  # type: ignore[method-assign]
    argv = ["run", "claude", "t2", "b.md", "q.md", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == omnigent_agent.ASKED
    assert og.archived == ["s0"]  # the answer goes to s1


def test_wait_archives_the_session_whose_report_it_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    sid = og.create("claude", "t")
    (tmp_path / "r.md").write_text("ok")
    assert omnigent_agent.main(["wait", sid, "r.md"]) == 0
    assert og.archived == [sid]


class Owing:
    """One session, ``a``, owing a report: ``info`` is a script of snapshots whose last one repeats,
    and its history is ``items``, to which a send appends a user message."""

    def __init__(self, items: list[dict], *infos: dict) -> None:
        self.items_, self.infos, self.sent, self.retried = items, list(infos), [], []
        self.kids = 0.0  # when a child of the session was last updated

    def active(self, sid: str) -> float:
        return self.kids

    def info(self, sid: str) -> dict:
        snap = self.infos.pop(0) if len(self.infos) > 1 else self.infos[0]
        return {"status": "idle", "runner_online": True, "title": "coord", **snap}

    def items(self, sid: str) -> list[dict]:
        return self.items_

    def send(self, sid: str, text: str) -> None:
        self.sent.append(text)
        self.items_.append({**said("user", text, f"r{len(self.sent)}"), "created_at": time.time()})

    def retry(self, sid: str) -> dict:
        self.retried.append(sid)
        return {"recovered": True, "recovery": "runner_relaunched"}


def told(text: str, ago: float) -> dict:
    return {**said("user", text, text), "created_at": time.time() - ago}


def aged(path: Path, ago: float) -> Path:
    path.write_text("x")
    os.utime(path, (time.time() - ago, time.time() - ago))
    return path


def test_supervise_returns_a_report_written_since_the_last_instruction(tmp_path: Path) -> None:
    report = aged(tmp_path / "r.md", 60)
    og = Owing([told("brief", 120)], {})
    assert (
        omnigent_agent.supervise(og, {"a": report}, timeout=0)
        == f"a coord: report written: {report}"
    )
    # an earlier phase's report at the same path is not the one owed
    og = Owing([told("brief", 120), told("next phase", 30)], {})
    with pytest.raises(omnigent_agent.Fail, match="no event in 0s: a"):
        omnigent_agent.supervise(og, {"a": report}, timeout=0)


def test_settled_needs_the_turn_ended_at_every_look_for_turn_end_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "TURN_END_SECONDS", 60)
    report = aged(tmp_path / "r.md", 120)  # a draft written long before
    idle, running = {"status": "idle"}, {"status": "running"}
    ended: dict[str, float] = {}
    assert not omnigent_agent.settled(report, idle, [], ended, "a")  # one idle look is no turn end
    ended["a"] = time.time() - 61
    assert omnigent_agent.settled(report, idle, [], ended, "a")
    assert not omnigent_agent.settled(report, running, [told("x", 0)], ended, "a")
    assert "a" not in ended  # a running look restarts the count
    assert not omnigent_agent.settled(report, idle, [], ended, "a")
    ended["a"] = time.time() - 61
    aged(report, 10)  # rewritten while out of its turn
    assert not omnigent_agent.settled(report, idle, [], ended, "a")


def test_check_reads_the_report_again_after_it_settled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "r.md"
    report.write_text("SATISFIED: yes\n")
    og = Owing([told("brief", 120)], {})

    def rewritten(r: Path, *_: object) -> bool:
        r.write_text("revising")  # the verdict is gone by the time it settled
        return True

    monkeypatch.setattr(omnigent_agent, "settled", rewritten)
    event, _ = omnigent_agent.check(og, "a", report, 3600, {}, set(), print, verdict=True)
    assert event == ""


def test_supervise_counts_a_report_only_once_its_turn_ended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = aged(tmp_path / "r.md", 60)  # progress, while the lead still works
    og = Owing(
        [told("brief", 120), told("progress", 1) | {"role": "assistant"}], {"status": "running"}
    )
    with pytest.raises(omnigent_agent.Fail, match="no event in 0s: a"):
        omnigent_agent.supervise(og, {"a": report}, timeout=0)
    og.infos = [{"status": "idle"}]
    assert (
        omnigent_agent.supervise(og, {"a": report}, timeout=0)
        == f"a coord: report written: {report}"
    )


def test_supervise_returns_a_question_a_prompt_and_a_failure(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    aged(tmp_path / "r.md.question", 10)
    og = Owing([told("brief", 60)], {})
    assert (
        omnigent_agent.supervise(og, {"a": report}, timeout=0)
        == f"a coord: asked: {tmp_path / 'r.md.question'}"
    )
    report = tmp_path / "s.md"
    prompt = {"params": {"content_preview": "Bash(rm x)"}}
    og = Owing([told("brief", 60)], {"pending_elicitations": [prompt]})
    assert (
        omnigent_agent.supervise(og, {"a": report}, timeout=0)
        == "a coord: blocked on a prompt: Bash(rm x)"
    )
    og = Owing([told("brief", 60)], {"status": "failed", "last_task_error": {"message": "boom"}})
    assert omnigent_agent.supervise(og, {"a": report}, timeout=0) == "a coord: failed: boom"


def test_supervise_revives_a_reaped_runner_and_carries_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "r.md"
    og = Owing([told("brief", 60)], {"runner_online": False}, {"runner_online": True}, {})
    og.infos.append({"status": "failed", "last_task_error": {"message": "later"}})
    assert omnigent_agent.supervise(og, {"a": report}, timeout=5) == "a coord: failed: later"
    assert og.retried == ["a"]
    assert "a coord: revived (no live runner)" in capsys.readouterr().out


def test_supervise_gives_up_when_the_revive_fails(tmp_path: Path) -> None:
    og = Owing([told("brief", 60)], {"runner_online": False})
    og.retry = lambda sid: {"recovered": False, "recovery": "no_host"}  # type: ignore[method-assign]
    line = omnigent_agent.supervise(og, {"a": tmp_path / "r.md"}, timeout=0)
    assert line.startswith("a coord: session a has no live runner and the revive failed")
    assert line.endswith("; gave up")


def test_supervise_resumes_a_silent_session_once_then_gives_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "r.md"
    # silent for an hour, its status still `running`: a turn end Omnigent lost
    og = Owing([told("brief", 3600)], {"status": "running"})
    clock = [time.time()]
    monkeypatch.setattr(omnigent_agent.time, "time", lambda: clock[0])

    def later(_: float) -> None:
        clock[0] += 600

    monkeypatch.setattr(omnigent_agent.time, "sleep", later)
    line = omnigent_agent.supervise(og, {"a": report}, silent=1800, timeout=3600)
    assert og.sent == [omnigent_agent.NUDGE.format(report=report)]
    assert (
        "a coord: silent 3600s (running), report owed; resume line sent" in capsys.readouterr().out
    )
    assert line == "a coord: silent 1800s after the resume line; gave up"


def test_supervise_never_nudges_a_busy_session_and_the_resume_line_is_no_instruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "r.md"
    og = Owing(
        [told("brief", 3600), {**said("assistant", "gates", "g"), "created_at": time.time()}], {}
    )
    with pytest.raises(omnigent_agent.Fail):
        omnigent_agent.supervise(og, {"a": report}, silent=1800, timeout=0)
    assert og.sent == []
    # the report written before the resume line still counts: the resume line asked for it again
    aged(report, 1800)
    og = Owing([told("brief", 3600), told(omnigent_agent.NUDGE.format(report=report), 60)], {})
    assert (
        omnigent_agent.supervise(og, {"a": report}, timeout=0)
        == f"a coord: report written: {report}"
    )


def test_supervise_cli_needs_session_report_pairs(capsys: pytest.CaptureFixture[str]) -> None:
    assert omnigent_agent.main(["supervise", "a"]) == 1
    assert "a: expected <session>=<report>" in capsys.readouterr().err


def test_supervise_gives_up_when_the_resume_line_stays_undelivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A harness stuck mid-step holds the resume line in pending_inputs: that is silence too."""
    report = tmp_path / "r.md"
    og = Owing([told("brief", 3600)], {"status": "running"})
    og.send = lambda sid, text: og.sent.append(text)  # type: ignore[method-assign]
    info = og.info
    og.info = lambda sid: {  # type: ignore[method-assign]
        **info(sid),
        "pending_inputs": [said("user", t, "p") for t in og.sent],
    }
    clock = [time.time()]
    monkeypatch.setattr(omnigent_agent.time, "time", lambda: clock[0])
    monkeypatch.setattr(
        omnigent_agent.time, "sleep", lambda _: clock.__setitem__(0, clock[0] + 600)
    )
    assert (
        omnigent_agent.supervise(og, {"a": report}, silent=1800, timeout=3700)
        == "a coord: silent 1800s after the resume line; gave up"
    )
    assert len(og.sent) == 1


def test_supervise_gives_up_at_once_on_a_silence_with_an_input_already_undelivered(
    tmp_path: Path,
) -> None:
    og = Owing([told("brief", 3600)], {"pending_inputs": [said("user", "answer", "p")]})
    assert (
        omnigent_agent.supervise(og, {"a": tmp_path / "r.md"}, silent=1800, timeout=0)
        == "a coord: silent 3600s with an input undelivered; gave up"
    )
    assert og.sent == []


def test_supervise_wakes_its_caller_before_reviving_another_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = aged(tmp_path / "a.md", 10)
    og = Owing([told("brief", 60)], {})
    info = og.info
    og.info = lambda sid: {**info(sid), "runner_online": sid == "a"}  # type: ignore[method-assign]
    line = omnigent_agent.supervise(og, {"a": report, "b": tmp_path / "b.md"}, timeout=0)
    assert line == f"a coord: report written: {report}"
    assert og.retried == []
    assert capsys.readouterr().out == f"a coord: report written: {report}\n"


def test_supervise_reads_no_other_session_after_a_caller_event(tmp_path: Path) -> None:
    """#156: the event wakes its caller at once, not after another session's read stalls."""
    report = aged(tmp_path / "a.md", 10)
    og = Owing([told("brief", 60)], {})
    reads: list[str] = []
    info, items = og.info, og.items
    og.info = lambda sid: (reads.append(sid), info(sid))[1]  # type: ignore[method-assign]
    og.items = lambda sid: (reads.append(sid), items(sid))[1]  # type: ignore[method-assign]
    line = omnigent_agent.supervise(og, {"a": report, "b": tmp_path / "b.md"}, timeout=0)
    assert line == f"a coord: report written: {report}"
    assert "b" not in reads


def test_a_restarted_supervisor_gives_up_on_a_silence_after_the_resume_line_in_the_history(
    tmp_path: Path,
) -> None:
    report = tmp_path / "r.md"
    resume = omnigent_agent.NUDGE.format(report=report)
    og = Owing([told("brief", 7200), told(resume, 3600)], {"status": "running"})
    assert (
        omnigent_agent.supervise(og, {"a": report}, silent=1800, timeout=0)
        == "a coord: silent 3600s after the resume line; gave up"
    )
    assert og.sent == []


class Fleet:
    """Sessions owing reports, each with its own history. A session in ``broken`` raises on every
    read; one in ``offline`` has no live runner until retried, and a message to it is lost.
    Messages that land go to ``inbox``; the next ``refuse`` sends fail."""

    def __init__(self, **histories: list[dict]) -> None:
        self.histories, self.reads, self.inbox, self.retried = histories, [], [], []
        self.kids: dict[str, float] = {}  # when a child of each session was last updated
        self.broken: dict[str, Exception] = {}
        self.offline: set[str] = set()
        self.refuse = 0
        self.labels: list[tuple[str, dict]] = []  # each label write
        self.unlabelled = 0  # the next label writes that fail
        self.files: dict[str, str] = {}  # what read_file finds, by path
        self.written: dict[str, float | Exception] = {}  # what modified finds (or raises), by path
        self.stats: list[str] = []  # each modified read
        self.pages = 0  # history pages read back

    def read_file(self, sid: str, path: str) -> str:
        if path not in self.files:
            raise omnigent_agent.Gone(f"{path}: not found")
        return self.files[path]

    def modified(self, sid: str, path: str) -> float:
        self.stats.append(path)
        at = self.written.get(path, 0.0)
        if isinstance(at, Exception):
            raise at
        return at

    def older(self, sid: str, after: str = "") -> dict:
        self.pages += 1
        newest = list(reversed(self.histories.get(sid, [])))
        ids = [str(i.get("id")) for i in newest]
        start = ids.index(after) + 1 if after else 0
        data = newest[start : start + 100]
        more = start + 100 < len(newest)
        return {"data": data, "last_id": data[-1]["id"] if data else None, "has_more": more}

    def active(self, sid: str) -> float:
        return self.kids.get(sid, 0.0)

    def hosts(self) -> dict[str, str]:
        return {"h": "here"}

    def label(self, sid: str, labels: dict[str, str]) -> None:
        if self.unlabelled:
            self.unlabelled -= 1
            raise omnigent_agent.Fail(f"PATCH /v1/sessions/{sid}: HTTP 503")
        self.labels.append((sid, labels))

    def info(self, sid: str) -> dict:
        self.reads.append(sid)
        if sid in self.broken:
            raise self.broken[sid]
        return {"status": "idle", "runner_online": sid not in self.offline, "title": f"t-{sid}"}

    def items(self, sid: str) -> list[dict]:
        return self.histories.get(sid, [])

    def send(self, sid: str, text: str) -> None:
        if self.refuse:
            self.refuse -= 1
            raise omnigent_agent.Fail(f"POST /v1/sessions/{sid}/events: HTTP 503")
        if sid not in self.offline:
            self.inbox.append((sid, text))

    def retry(self, sid: str) -> dict:
        self.retried.append(sid)
        self.offline.discard(sid)
        return {"recovered": True, "recovery": "runner_relaunched"}


class Stop(BaseException):
    """Ends the supervisor's loop: not an Exception, which the loop logs and survives."""


def supervised(
    og: Fleet,
    registry: Path,
    monkeypatch: pytest.MonkeyPatch,
    polls: int,
    between=lambda poll: None,
    **kwargs: object,
) -> None:
    """Run ``supervise_registry`` for ``polls`` polls, calling ``between`` after each but the last."""
    count = [0]

    def sleep(_: float) -> None:
        count[0] += 1
        if count[0] >= polls:
            raise Stop
        between(count[0])

    monkeypatch.setattr(omnigent_agent.time, "sleep", sleep)
    with pytest.raises(Stop):
        omnigent_agent.supervise_registry(og, registry, **kwargs)  # type: ignore[arg-type]


STAMP = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d "


def test_a_session_added_to_the_registry_between_polls_is_supervised_from_the_next_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "registry"
    registry.write_text(f"a={tmp_path / 'a.md'}\n")
    report = aged(tmp_path / "b.md", 10)
    og = Fleet(a=[told("brief", 60)], b=[told("brief", 60)])
    with_b = lambda poll: registry.write_text(registry.read_text() + f"b={report}\n")
    supervised(og, registry, monkeypatch, 2, with_b)
    assert og.reads == ["a", "a", "b"]
    assert re.fullmatch(f"{STAMP}b t-b: report written: {report}\n", capsys.readouterr().out)


def test_a_verifier_line_counts_its_report_only_once_it_has_its_satisfied_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "registry"
    verdict, plain = aged(tmp_path / "v.md", 10), aged(tmp_path / "w.md", 10)
    for report in (verdict, plain):
        report.write_text("Head: abc\nVERDICT: approve\n")
    registry.write_text(f"v={verdict}\tverdict\nw={plain}\n")
    og = Fleet(v=[told("brief", 60)], w=[told("brief", 60)])
    finish = lambda poll: verdict.write_text(verdict.read_text() + "SATISFIED: yes\n")
    supervised(og, registry, monkeypatch, 2, finish)
    out = capsys.readouterr().out
    assert re.fullmatch(
        f"{STAMP}w t-w: report written: {plain}\n{STAMP}v t-v: report written: {verdict}\n", out
    )


def test_a_terminal_event_is_posted_to_the_notify_session_and_drops_only_its_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "registry"
    report = aged(tmp_path / "a.md", 10)
    registry.write_text(f"# leads\na={report}\nb={tmp_path / 'b.md'}\n")
    og = Fleet(a=[told("brief", 60)], b=[told("brief", 60)])
    supervised(og, registry, monkeypatch, 1, notify="cos")
    assert og.inbox == [("cos", f"Supervisor: a t-a: report written: {report}")]
    assert registry.read_text() == f"# leads\nb={tmp_path / 'b.md'}\n"
    assert re.fullmatch(f"{STAMP}a t-a: report written: {report}\n", capsys.readouterr().out)


class Lead(Fleet):
    """One followed lead, ``a``, whose ``snap`` fields (status, prompts, error, archived) the test sets."""

    def __init__(self, *items: dict) -> None:
        super().__init__(a=list(items))
        self.snap: dict = {}

    def info(self, sid: str) -> dict:
        return {**super().info(sid), **self.snap}

    def send(self, sid: str, text: str) -> None:  # a message to a lead lands in its history
        super().send(sid, text)
        if sid in self.histories and sid not in self.offline:
            n = len(self.histories[sid])
            self.histories[sid].append({**said("user", text, f"u{n}"), "created_at": time.time()})


def ending(text: str, ago: float) -> dict:
    return {**said("assistant", text, f"m{text}{ago}"), "created_at": time.time() - ago}


def following(tmp_path: Path) -> Path:
    registry = tmp_path / "registry"
    registry.write_text(f"a={tmp_path / 'a.md'}\t{tmp_path / 'a.md.brief'}\tfollow\n")
    return registry


def posted(og: Fleet) -> list[str]:
    return [t for s, t in og.inbox if s == "cos"]


def fyis(og: Fleet) -> list[str]:
    """The lines posted as without --console, which --fyi post keeps."""
    return [t for t in posted(og) if t.startswith("Supervisor: ")]


def skewed(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The wall and monotonic clocks, ahead of the real ones by the number in the returned list."""
    offset, real, mono = [0.0], time.time, time.monotonic
    monkeypatch.setattr(omnigent_agent.time, "time", lambda: real() + offset[0])
    monkeypatch.setattr(omnigent_agent.time, "monotonic", lambda: mono() + offset[0])
    return offset


def test_a_followed_lead_that_ends_still_working_is_news_only_after_it_is_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    # its last message is 600 s old when the end is seen: quiet counts from that end, not from it
    og = Lead(told("brief", 800), ending("STILL WORKING: verifier running", 600))
    # it writes again at 100 s: the quiet count restarts, so 301 s from the first end is not news
    at = {1: 100.0, 2: 301.0, 3: 401.0, 4: 402.0}

    def later(poll: int) -> None:
        offset[0] = at[poll]
        if poll == 1:
            og.histories["a"].append(ending("STILL WORKING: verifier running", 0))

    supervised(og, registry, monkeypatch, 5, later, notify="cos")
    assert len(posted(og)) == 1  # once for the message, not once per poll
    assert re.fullmatch(
        r"Supervisor: a t-a: turn ended, quiet 30\ds\nlast message: STILL WORKING: verifier running",
        posted(og)[0],
    )
    assert "follow" in registry.read_text()


@pytest.mark.parametrize("word", ["DONE", "USER NEEDED", "PARKED"])
def test_a_followed_lead_ending_with_a_named_ending_is_news_at_once_and_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, word: str
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending(f"**{word}** the result", 1))
    supervised(og, registry, monkeypatch, 3, notify="cos")
    assert posted(og) == [f"Supervisor: a t-a: turn ended\nlast message: **{word}** the result"]


def test_a_live_child_updated_within_the_window_keeps_a_followed_lead_quiet_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 800), ending("STILL WORKING: its worker runs", 400))
    og.kids["a"] = time.time() + 100  # its worker wrote at 100, after the end seen at 0
    at = {1: 350.0, 2: 399.0, 3: 401.0}  # 250 s, then 299 s, then 301 s since the worker wrote
    before: list[int] = []  # notices after the looks at 0, 350 and 399

    def later(poll: int) -> None:
        before.append(len(posted(og)))
        offset[0] = at[poll]

    supervised(og, registry, monkeypatch, 4, later, notify="cos")
    assert before == [0, 0, 0]  # past the end's 300 s at 350 and 399, but the child is younger
    assert len(posted(og)) == 1  # news only at 401: the child, not the end, held it


def test_a_named_ending_already_told_stays_told_while_the_runner_flaps_to_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("DONE: finished", 1))
    states = {1: "running", 2: "idle", 3: "idle"}

    def flap(poll: int) -> None:
        og.snap = {"status": states.get(poll, "idle")}
        if poll == 4:
            og.histories["a"].append(ending("DONE: again", 0))  # a new message, a new ending

    supervised(og, registry, monkeypatch, 6, flap, notify="cos")
    assert [p.splitlines()[1] for p in posted(og)] == [
        "last message: DONE: finished",
        "last message: DONE: again",
    ]


def test_a_followed_leads_prompt_posts_once_it_holds_a_failure_at_once_and_archived_drops_its_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING", 5))
    blocked = {
        "status": "running",
        "pending_elicitations": [{"elicitation_id": "e1", "message": "ok?"}],
    }
    og.snap = blocked
    steps = [
        blocked,
        {"status": "running"},
        {"status": "failed", "last_task_error": {"message": "boom"}},
        {"status": "running"},
        {"status": "idle", "archived": True},
    ]

    def next_state(poll: int) -> None:
        og.snap = steps[poll - 1]
        if poll == 1:
            offset[0] = omnigent_agent.PROMPT_CONFIRM_SECONDS

    supervised(og, registry, monkeypatch, 6, next_state, notify="cos")
    lines = posted(og)
    assert len(lines) == 3
    assert "blocked on a prompt" in lines[0] and ": failed: boom" in lines[1]
    assert ": archived" in lines[2]
    assert registry.read_text() == ""  # archived dropped it; the other events kept it


def blocked_on(eid: str) -> dict:
    prompt = {"elicitation_id": eid, "params": {"content_preview": "Bash(ls)"}}
    return {"status": "running", "pending_elicitations": [prompt]}


def test_a_prompt_that_clears_within_the_confirm_wait_is_never_posted_nor_routed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a child's prompt Omnigent mirrors onto its lead, which the lead answers itself
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: its worker runs", 5))
    og.snap = blocked_on("e1")
    at = {1: 30.0, 2: 200.0}

    def later(poll: int) -> None:
        offset[0] = at[poll]
        og.snap = {"status": "running"}

    supervised(og, registry, monkeypatch, 3, later, notify="cos", console=True)
    assert posted(og) == []
    events = registry.with_suffix(".events.jsonl")
    assert not events.exists() or "blocked" not in events.read_text()


def test_a_prompt_still_pending_after_the_confirm_wait_is_posted_to_the_owner_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: its worker runs", 5))
    og.snap = blocked_on("e1")
    wait = omnigent_agent.PROMPT_CONFIRM_SECONDS
    at = {1: 30.0, 2: wait - 1, 3: wait, 4: wait + 600}
    before: list[int] = []

    def later(poll: int) -> None:
        before.append(len(posted(og)))
        offset[0] = at[poll]

    supervised(og, registry, monkeypatch, 5, later, notify="cos", console=True)
    assert before == [0, 0, 0, 1]
    [post] = posted(og)
    assert "[owner] a t-a: blocked on a prompt: Bash(ls) (an approval prompt" in post


def test_a_new_prompt_id_restarts_the_confirm_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a lead blocked on e1, then on e2 after e1 was answered: e2 is timed from when it is first seen
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: its worker runs", 5))
    og.snap = blocked_on("e1")
    wait = omnigent_agent.PROMPT_CONFIRM_SECONDS
    at = {1: 90.0, 2: 90 + wait - 1, 3: 90 + wait, 4: 90 + wait + 600}
    before: list[int] = []

    def later(poll: int) -> None:
        before.append(len(posted(og)))
        offset[0] = at[poll]
        og.snap = blocked_on("e2")

    supervised(og, registry, monkeypatch, 5, later, notify="cos", console=True)
    assert before == [0, 0, 0, 1]  # e2's wait, not e1's, which would have passed by poll 3
    assert len(posted(og)) == 1


def test_without_console_the_supervisor_writes_no_state_labels_or_deadline_and_reposts_on_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    report = aged(tmp_path / "b.md", 10)
    registry.write_text(registry.read_text() + f"b={report}\n")
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: on it", 50))
    og.histories["b"] = [told("brief", 60)]
    og.snap = {"status": "running"}  # stuck: --console would raise its deadline at 1300 s
    supervised(og, registry, monkeypatch, 2, lambda poll: offset.__setitem__(0, 1300), notify="cos")
    assert posted(og) == [f"Supervisor: b t-b: report written: {report}"]
    og.inbox.clear()
    og.snap = {"status": "idle"}
    og.histories["a"].append(ending("DONE: shipped", 0))
    for _ in range(2):  # a restart posts an end it finds again
        supervised(og, registry, monkeypatch, 1, notify="cos")
    assert posted(og) == ["Supervisor: a t-a: turn ended\nlast message: DONE: shipped"] * 2
    assert og.labels == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.md", "registry"]


def state_of(registry: Path) -> dict:
    return json.loads(registry.with_suffix(".state.json").read_text())


def test_one_poll_writes_the_state_and_labels_and_an_unchanged_poll_within_a_minute_writes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    owing = tmp_path / "b.md"
    registry.write_text(registry.read_text() + f"b={owing}\n")
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("DONE: shipped\nPR #1 merged", 5))
    og.histories["b"] = [told("brief", 60)]
    og.snap = {"host_id": "h"}
    at = {1: 30.0, 2: 61.0}
    snapshots: list[dict] = []

    def later(poll: int) -> None:
        snapshots.append(state_of(registry))
        offset[0] = at[poll]

    supervised(og, registry, monkeypatch, 3, later, console=True)
    first = snapshots[0]
    assert first["schema"] == "cos-state/1" and first["written_at"] >= time.time() - 120
    lead = first["leads"]["a"]
    assert {k: lead[k] for k in ("title", "host", "report", "follow", "state", "wait")} == {
        "title": "t-a",
        "host": "here",
        "report": str(tmp_path / "a.md"),
        "follow": True,
        "state": "idle",
        "wait": "unknown",
    }
    assert (lead["ending"], lead["last_line"], lead["waits_on"]) == ("DONE", "DONE: shipped", [])
    assert (lead["nudges"], lead["revives"], lead["briefs"]) == (
        0,
        0,
        [str(tmp_path / "a.md.brief")],
    )
    assert first["leads"]["b"]["report"] == str(owing) and first["leads"]["b"]["follow"] is False
    assert first["settled"]["a"] == ["ended:a:mDONE: shipped\nPR #1 merged5"]
    assert (first["intents"], first["attention"], first["pending_posts"]) == ([], [], [])
    assert first["rate"]["next_post_at"] > time.time()  # its DONE printed as a post would go
    a_labels = [labels for sid, labels in og.labels if sid == "a"]
    assert [labels["status.line"] for labels in a_labels] == ["turn ended: DONE: shipped"] * 2
    assert int(a_labels[1]["status.at"]) - int(a_labels[0]["status.at"]) >= 60  # none at 30 s
    assert lead["label"] == {"line": a_labels[0]["status.line"], "at": a_labels[0]["status.at"]}
    events = [json.loads(e) for e in registry.with_suffix(".events.jsonl").read_text().splitlines()]
    assert [(e["id"], e["session"], e["kind"], e["settled"], e["action"]) for e in events] == [
        (first["settled"]["a"][0], "a", "ended", "rule", "done")
    ]


def test_the_console_labels_its_own_session_as_the_chief_of_staff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "cos1")
    og = Lead(told("brief", 60))
    og.snap = {"host_id": "h"}
    supervised(og, following(tmp_path), monkeypatch, 1, console=True)
    assert og.labels[0] == ("cos1", {"omni.role": "cos"})

    og = Lead(told("brief", 60))
    og.snap, og.unlabelled = {"host_id": "h"}, 1
    supervised(og, following(tmp_path), monkeypatch, 2, console=True)  # a failed write: it runs on
    assert "cos1: role label not written" in capsys.readouterr().err


def test_a_status_line_stays_under_200_characters() -> None:
    lead = {"state": "idle", "wait": "verifier", "last_line": "x" * 300}
    line = omnigent_agent.status_line(lead)
    assert len(line) == 199 and line.startswith("turn ended · waits on verifier: xx")


def test_a_restart_raises_no_settled_event_again_and_keeps_budgets_and_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 800), ending("STILL WORKING: carrying on", 600))
    at = {1: 301.0, 2: 601.0}  # its last message was 600 s old at the start
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda poll: offset.__setitem__(0, at[poll]),
        notify="cos",
        console=True,
        fyi="post",
    )
    assert [p.split("\n")[0] for p in fyis(og)] == [
        "Supervisor: a t-a: turn ended, quiet 301s",
        "Supervisor: a t-a: no progress 20m (unknown)",
    ]
    state = state_of(registry)
    progress = state["leads"]["a"]["progress_at"]
    state["leads"]["a"].update(nudges=1, revives=1)  # what the routing will count
    registry.with_suffix(".state.json").write_text(json.dumps(state))
    og.inbox.clear()
    at = {1: 1205.0, 2: 1210.0}  # the end found again at 601; at 1205, 30 min since the progress
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda poll: offset.__setitem__(0, at[poll]),
        notify="cos",
        console=True,
        fyi="post",
    )
    assert [p.split("\n")[0] for p in fyis(og)] == [
        "Supervisor: a t-a: no progress 30m after a nudge (unknown)"
    ]
    lead = state_of(registry)["leads"]["a"]
    assert (lead["nudges"], lead["revives"], lead["progress_at"]) == (1, 1, progress)


def test_a_lead_stuck_running_raises_one_deadline_for_its_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: on it", 0))
    og.snap = {"status": "running"}
    at = {1: 1199.0, 2: 1201.0, 3: 1300.0, 4: 2500.0}

    def later(poll: int) -> None:
        offset[0] = at[poll]
        og.refuse = 2 if poll == 1 else og.refuse  # its post fails at two polls: it waits, once

    supervised(og, registry, monkeypatch, 5, later, notify="cos", console=True, fyi="post")
    assert fyis(og) == [  # raised once each: the deadline, then (nudged at it) the one after
        "Supervisor: a t-a: no progress 20m (unknown)\nlast message: STILL WORKING: on it",
        "Supervisor: a t-a: no progress 42m after a nudge (unknown)\nlast message: STILL WORKING: on it",
    ]
    assert state_of(registry)["settled"]["a"][0].startswith("deadline:a:")


@pytest.mark.parametrize(
    ("said_ago", "child_ago", "deadline"),
    [
        (3600.0, 0.0, "no progress 60m (unknown)"),
        (3600.0, 1300.0, "no progress 22m (unknown)"),
        (0.0, 0.0, None),  # no activity at all: progress counts from first sight
    ],
)
def test_progress_starts_from_the_leads_real_activity_not_from_first_sight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    said_ago: float,
    child_ago: float,
    deadline: str | None,
) -> None:
    registry = following(tmp_path)
    items = [ending("STILL WORKING: building", said_ago)] if said_ago else []
    og = Lead(told("brief", 4000), *items)
    og.snap = {"status": "running"}
    if child_ago:
        og.kids["a"] = time.time() - child_ago
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True, fyi="post")
    assert [p.split("\n")[0] for p in fyis(og)] == (
        [f"Supervisor: a t-a: {deadline}"] if deadline else []
    )
    progress = state_of(registry)["leads"]["a"]["progress_at"]
    if items:
        assert progress == max(items[-1]["created_at"], og.kids.get("a", 0.0))
    else:
        assert time.time() - 60 < progress <= time.time()


@pytest.mark.parametrize(
    ("written_ago", "deadline"),
    [
        (1300.0, "no progress 22m (merge)"),  # written after its last message: counts from then
        (100.0, None),  # written while its messages were quiet: progress, no deadline
        (None, "no progress 60m (merge)"),  # not listed
        (omnigent_agent.Fail("GET: HTTP 409"), "no progress 60m (merge)"),  # its host is offline
    ],
)
def test_a_report_being_written_is_progress_once_the_lead_is_due(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    written_ago: float | Exception | None,
    deadline: str | None,
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 4000), ending("STILL WORKING: merge queue", 3600))
    og.snap = {"status": "running"}
    report = str(tmp_path / "a.md")
    if written_ago is not None:
        og.written[report] = (
            written_ago if isinstance(written_ago, Exception) else time.time() - written_ago
        )
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True, fyi="post")
    assert [p.split("\n")[0] for p in fyis(og)] == (
        [f"Supervisor: a t-a: {deadline}"] if deadline else []
    )
    assert og.stats == [report]
    if written_ago == 100.0:
        assert state_of(registry)["leads"]["a"]["progress_at"] == og.written[report]


def test_a_lead_not_yet_due_has_its_report_left_unread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 120), ending("STILL WORKING: merge queue", 60))
    og.snap = {"status": "running"}
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True, fyi="post")
    assert og.stats == [] and fyis(og) == []


LIVE_TIMED = (
    "STILL WORKING: waiting on the day of real traffic that measures CoS wakes per lead event. A timer"
    " (`cos-measure-day1`) runs the count at 2026-10-21 23:17 UTC and wakes this session"
)


@pytest.mark.parametrize(("due_in", "deadline"), [(3600.0, False), (-1300.0, True)])
def test_a_timed_wait_holds_off_the_deadline_until_its_time_and_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, due_in: float, deadline: bool
) -> None:
    assert omnigent_agent.wait_of(LIVE_TIMED) == "until 2026-10-21T23:17Z"
    # its named wait, not "lead" from "per lead event"
    assert omnigent_agent.wait_of(LIVE_TIMED.split(". A timer")[0]) == "day"
    # the lead's real last message: a bare time, and "lead" in "wakes this lead"
    real = "/r/a.md\n\nSTILL WORKING: waiting on the timer (2026-10-21 23:17 UTC), which wakes this lead"
    assert omnigent_agent.wait_of(real) == "until 2026-10-21T23:17Z"
    assert (
        omnigent_agent.wait_of(real.replace(" (2026-10-21 23:17 UTC)", "")) == "timer"
    )  # not "lead"
    assert (
        omnigent_agent.wait_of("STILL WORKING: until 2026-10-21T23:17:59Z")
        == "until 2026-10-21T23:17:59Z"
    )
    assert omnigent_agent.wait_of("STILL WORKING: until 2026-02-30T23:17Z") == "unknown"
    # lead 99a79f4d's message: a rule's "Until <time>" comes before the time its wait names
    rule = (
        "STILL WORKING: I've recorded the temporary review rule in the run notes. Until 2026-10-27"
        " 06:32 UTC, new verifiers run as Claude Opus with `--same-family`. I'm waiting on the"
        " measurement timer `cos-measure-day1`, which fires at 2026-10-21 23:17 UTC."
    )
    assert omnigent_agent.wait_of(rule) == "until 2026-10-21T23:17Z"
    # no sentence says "wait": the earliest still to come when written, else the earliest
    two = "STILL WORKING: a timer wakes me at 2026-10-21 23:17 UTC. The trial ends 2026-10-27 06:32 UTC."
    written = 1792540800.0  # 2026-10-21 00:00Z
    assert omnigent_agent.wait_of(two, written) == "until 2026-10-21T23:17Z"
    assert omnigent_agent.wait_of(two) == "until 2026-10-21T23:17Z"
    past = "STILL WORKING: a timer wakes me at 2026-10-27 06:32 UTC. The last run ended 2026-10-21 10:00 UTC."
    assert omnigent_agent.wait_of(past, written + 12 * 3600) == "until 2026-10-27T06:32Z"
    item = {**ending(past, 0), "created_at": written + 12 * 3600}  # fixed: no wall clock
    status = omnigent_agent.lead_status({"status": "idle"}, [item])
    assert status["wait"] == "until 2026-10-27T06:32Z"  # judged at its created_at, not later
    listed = "STILL WORKING:\n- the rule holds until 2026-10-27 06:32 UTC\n- waiting on the timer at 2026-10-21 23:17 UTC"
    assert omnigent_agent.wait_of(listed) == "until 2026-10-21T23:17Z"  # a line is a sentence
    assert omnigent_agent.wait_of("At 2026-10-21 23:17 UTC. STILL WORKING on CI") == "CI"
    due = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + due_in))
    registry = following(tmp_path)
    og = Lead(told("brief", 4000), ending(f"STILL WORKING: a timer wakes me until {due}", 3600))
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True, fyi="post")
    assert [p.split("\n")[0] for p in fyis(og)] == (
        [f"Supervisor: a t-a: no progress 60m (until {due})"] if deadline else []
    )


def test_a_background_task_id_is_a_named_wait() -> None:
    """`b` and 8 lowercase letters and digits, one a digit at least, opening the wait or after "on"/"for"."""
    assert omnigent_agent.wait_of("STILL WORKING bz3jp5aod") == "bz3jp5aod"
    assert omnigent_agent.wait_of("STILL WORKING bz3jp5aod: the queue runs for #12") == "bz3jp5aod"
    assert omnigent_agent.wait_of("STILL WORKING: waiting on bz3jp5aod") == "bz3jp5aod"
    assert omnigent_agent.wait_of("STILL WORKING: on it") == "unknown"
    assert omnigent_agent.wait_of("STILL WORKING backports") == "unknown"
    # ten characters: no task id
    assert omnigent_agent.wait_of("STILL WORKING on bz3jp5aodx") == "unknown"


def test_a_childs_activity_reaches_the_state_once_a_minute_before_any_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: waiting on worker", 50))
    og.snap = {"status": "running"}
    start, reads, progress = time.time(), [], []
    real = og.active
    og.active = lambda sid: reads.append(sid) or real(sid)  # type: ignore[method-assign]
    at = {1: 30.0, 2: 61.0}

    def later(poll: int) -> None:
        progress.append(state_of(registry)["leads"]["a"]["progress_at"])
        offset[0] = at[poll]
        og.kids["a"] = start + 20 * poll  # its worker writes at 20, then at 40

    supervised(og, registry, monkeypatch, 3, later, console=True)
    progress.append(state_of(registry)["leads"]["a"]["progress_at"])
    assert reads == ["a", "a"]  # at 0 and at 61, none at 30
    assert progress[1] == progress[0] and progress[2] == start + 40


def test_the_same_failure_again_after_a_recovery_is_news_and_a_restart_posts_neither_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("STILL WORKING: building", 50))
    og.snap = {"status": "failed", "last_task_error": {"message": "runner lost"}}

    def recover_then_fail(poll: int) -> None:
        og.snap["status"] = "running" if poll == 1 else "failed"

    supervised(
        og, registry, monkeypatch, 3, recover_then_fail, notify="cos", console=True, fyi="post"
    )
    failures = [p.split("\n")[0] for p in fyis(og)]
    assert failures == ["Supervisor: a t-a: failed: runner lost"] * 2
    og.inbox.clear()
    supervised(
        og, registry, monkeypatch, 2, notify="cos", console=True, fyi="post"
    )  # a restart, still failed
    assert fyis(og) == []
    assert [i for i in state_of(registry)["settled"]["a"] if i.startswith("failed:")] == [
        "failed:a:1:runner lost",
        "failed:a:2:runner lost",
    ]


def test_a_second_quiet_spell_with_the_same_ending_raises_a_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 800), ending("STILL WORKING: waiting on the verifier", 600))
    steps = {1: (301.0, "idle"), 2: (400.0, "running"), 3: (500.0, "idle"), 4: (601.0, "idle")}

    def later(poll: int) -> None:
        offset[0], status = steps[poll]
        og.snap = {"status": status}

    supervised(og, registry, monkeypatch, 5, later, notify="cos", console=True, fyi="post")
    assert [p.split("\n")[0] for p in fyis(og)] == [
        "Supervisor: a t-a: turn ended, quiet 301s",  # the first spell, told once
        "Supervisor: a t-a: no progress 20m (verifier)",  # the second, the same message
    ]


@pytest.mark.parametrize("status", ["idle", "running"])  # running: its turn end was lost
def test_a_parked_lead_has_no_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("PARKED: the host is full", 5))
    og.snap = {"status": status}
    at = {1: 1300.0, 2: 5000.0}
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda poll: offset.__setitem__(0, at[poll]),
        notify="cos",
        console=True,
        fyi="post",
    )
    ends = ["Supervisor: a t-a: turn ended"] if status == "idle" else []
    assert [p.split("\n")[0] for p in fyis(og)] == ends
    assert state_of(registry)["leads"]["a"]["wait"] == "parked"


def test_a_live_child_is_progress_and_the_deadline_counts_from_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: its worker runs", 50))
    og.snap = {"status": "running"}
    og.kids["a"] = time.time() + 1100  # its worker wrote at 1100
    at = {1: 1201.0, 2: 2299.0, 3: 2301.0}
    before: list[int] = []

    def later(poll: int) -> None:
        before.append(len(fyis(og)))
        offset[0] = at[poll]

    supervised(og, registry, monkeypatch, 4, later, notify="cos", console=True, fyi="post")
    assert before == [0, 0, 0]
    assert [p.split("\n")[0] for p in fyis(og)] == ["Supervisor: a t-a: no progress 20m (worker)"]


def path_only_lead(tmp_path: Path, report: str | None) -> tuple[Path, Lead, list[str]]:
    """A followed lead whose last message is only its report's path; ``report`` is the file's text,
    or None for one that cannot be read. The list holds each read of the file."""
    registry = following(tmp_path)
    path = str(tmp_path / "a.md")
    og = Lead(told("brief", 60), ending(path, 5))
    reads: list[str] = []
    if report is not None:
        og.files[path] = report
    real = og.read_file

    def read_file(sid: str, p: str) -> str:
        reads.append(p)
        return real(sid, p)

    og.read_file = read_file  # type: ignore[method-assign]
    return registry, og, reads


def test_a_path_only_lead_whose_report_says_done_raises_no_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, og, _ = path_only_lead(tmp_path, "DONE: merged\nmore")
    offset = skewed(monkeypatch)
    supervised(
        og,
        registry,
        monkeypatch,
        4,
        lambda poll: offset.__setitem__(0, 1300.0 * poll),
        notify="cos",
        console=True,
    )
    assert "deadline" not in [e["kind"] for e in events_of(registry)]
    assert state_of(registry)["leads"]["a"]["ending"] == "DONE"


def test_a_path_only_lead_whose_report_names_its_wait_shows_it_in_state_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, og, reads = path_only_lead(tmp_path, "STILL WORKING: waiting on the verifier\n")
    supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    lead = state_of(registry)["leads"]["a"]
    assert lead["wait"] == "verifier"
    assert "waits on verifier" in lead["label"]["line"]
    assert len(reads) == 1


def test_a_reports_wait_is_judged_from_when_its_path_was_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    later = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(time.time() + 6 * 86400))
    past = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(time.time() - 2 * 3600))
    report = f"STILL WORKING: a timer wakes me at {later}. The last run ended {past}.\n"
    registry, og, _ = path_only_lead(tmp_path, report)
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    due = later.replace(" ", "T", 1).replace(" UTC", "Z")
    assert state_of(registry)["leads"]["a"]["wait"] == f"until {due}"


def test_a_new_last_message_is_read_again_and_an_unread_report_stays_unknown_and_is_logged_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry, og, reads = path_only_lead(tmp_path, None)
    supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert state_of(registry)["leads"]["a"]["wait"] == "unknown"
    assert capsys.readouterr().err.count("not found") == 1
    assert len(reads) == 1
    path = str(tmp_path / "a.md")
    og.files[path] = "STILL WORKING: waiting on CI"
    og.histories["a"].append(ending(path + " ", 1))  # a new last message, the same path
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)
    assert state_of(registry)["leads"]["a"]["wait"] == "CI"
    assert len(reads) == 2


def test_a_failed_read_stands_for_routing_too_and_the_quiet_end_acts_without_reading_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, og, reads = path_only_lead(tmp_path, None)
    offset = skewed(monkeypatch)

    def later(poll: int) -> None:
        og.files[str(tmp_path / "a.md")] = "DONE: merged"  # readable after the first failure
        offset[0] = 301.0

    supervised(og, registry, monkeypatch, 3, later, console=True)
    assert len(reads) == 2  # track's failed one, and the post's own report lines; routing's none
    assert state_of(registry)["leads"]["a"]["wait"] == "unknown"
    [ended] = [e for e in events_of(registry) if e["kind"] == "ended"]
    assert ended["action"] == "act" and "not read" in ended["why"]


def test_without_console_a_path_only_lead_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, og, reads = path_only_lead(tmp_path, "DONE: merged")
    supervised(og, registry, monkeypatch, 2, notify="cos")
    assert reads == []


def test_a_reader_never_sees_a_half_written_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("DONE: shipped", 5))
    real, renames = os.replace, []

    def replace(src: Path, dst: Path) -> None:
        assert Path(src).parent == Path(dst).parent  # a rename, never a copy across filesystems
        json.loads(Path(src).read_text())  # complete before it takes the name
        if Path(dst).exists():
            json.loads(Path(dst).read_text())  # what a reader sees meanwhile: the old one, whole
        renames.append(dst)
        real(src, dst)

    monkeypatch.setattr(omnigent_agent.os, "replace", replace)
    supervised(og, registry, monkeypatch, 2, console=True)
    assert set(renames) == {registry.with_suffix(".state.json")} and len(renames) >= 2
    assert not list(tmp_path.glob("*.tmp"))


def test_a_failed_label_write_is_logged_once_and_the_poll_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("DONE: shipped", 5))
    og.unlabelled = 2
    supervised(og, registry, monkeypatch, 3, notify="cos", console=True, fyi="post")
    assert [p.split("\n")[0] for p in fyis(og)] == ["Supervisor: a t-a: turn ended"]
    assert og.labels == [
        (
            "a",
            {"status.line": "turn ended: DONE: shipped", "status.at": og.labels[0][1]["status.at"]},
        )
    ]
    err = capsys.readouterr().err
    assert err.count("a: labels not written: PATCH /v1/sessions/a: HTTP 503") == 1


def test_a_followed_lead_is_never_revived_or_nudged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 9000))  # silent far past --silent-seconds, its runner gone
    og.offline.add("a")
    supervised(og, registry, monkeypatch, 3, notify="cos", silent=1)
    assert og.inbox == [] and og.retried == []


def test_a_top_level_start_with_a_registry_arms_a_follow_line_and_does_not_subscribe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "own_id", lambda: "chief")
    monkeypatch.chdir(tmp_path)
    registry, brief = tmp_path / "registry", tmp_path / "b.md"
    brief.write_text("do X")
    args = ["start", "claude", "t", str(brief), str(tmp_path / "a.md"), "--top-level"]
    assert omnigent_agent.main([*args, "--registry", str(registry)]) == 0
    assert registry.read_text() == f"s0={tmp_path / 'a.md'}\t{tmp_path / 'a.md.brief'}\tfollow\n"
    assert og.subscriptions == []
    args[4] = str(tmp_path / "c.md")
    assert omnigent_agent.main(args) == 0  # no registry: subscribes as before
    assert og.subscriptions == [("chief", "s1")] and "s1" not in registry.read_text()


def test_a_failed_post_keeps_the_line_and_the_event_is_posted_once_when_a_post_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "registry"
    report = aged(tmp_path / "a.md", 10)
    registry.write_text(f"a={report}\n")
    og = Fleet(a=[told("brief", 60)])
    og.refuse = 2
    kept: list[str] = []
    supervised(
        og, registry, monkeypatch, 3, lambda poll: kept.append(registry.read_text()), notify="cos"
    )
    assert kept == [f"a={report}\n"] * 2
    assert og.inbox == [("cos", f"Supervisor: a t-a: report written: {report}")]
    assert registry.read_text() == ""
    out, err = capsys.readouterr()
    assert out.count("report written") == 1
    assert re.fullmatch(f"{STAMP}post to cos failed: POST /v1/sessions/cos/events: HTTP 503\n", err)


def test_a_revive_line_whose_post_failed_is_posted_at_the_next_poll_before_newer_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry"
    report = tmp_path / "a.md"
    registry.write_text(f"a={report}\n")
    og = Fleet(a=[told("brief", 60)])
    og.offline.add("a")
    og.refuse = 1
    supervised(og, registry, monkeypatch, 2, lambda poll: report.write_text("x"), notify="cos")
    assert [m for m in og.inbox if m[0] == "cos"] == [
        ("cos", "Supervisor: a t-a: revived (no live runner)"),
        ("cos", f"Supervisor: a t-a: report written: {report}"),
    ]
    assert registry.read_text() == ""


def test_a_brief_armed_while_the_last_event_is_posted_keeps_its_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry"
    report = aged(tmp_path / "a.md", 10)
    registry.write_text(f"a={report}\n")
    og = Fleet(a=[told("brief", 60)])
    post = og.send

    def send(sid: str, text: str) -> None:  # the next brief lands and is armed mid-post
        post(sid, text)
        og.histories["a"].append(told("next brief", 0))
        omnigent_agent.arm(registry, "a", report)

    og.send = send  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 2, notify="cos")
    assert registry.read_text() == f"a={report}\n"
    assert og.inbox == [("cos", f"Supervisor: a t-a: report written: {report}")]


def test_a_revived_session_gets_the_revive_line_naming_its_brief_files_and_its_report_still_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry, report = tmp_path / "registry", tmp_path / "a.md"
    first, then = tmp_path / "a.md.brief", tmp_path / "answer.md"
    registry.write_text(f"a={report}\t{first}\t{then}\n")
    og = Fleet(a=[told("brief", 60)])
    og.offline.add("a")

    def written_before_the_revive_line(poll: int) -> None:
        aged(report, 30)  # the report its brief asked for, then the runner was reaped
        og.histories["a"] += [told(text, 0) for sid, text in og.inbox if sid == "a"]

    supervised(og, registry, monkeypatch, 2, written_before_the_revive_line, notify="cos")
    assert [text for sid, text in og.inbox if sid == "a"] == [
        (
            "Your session was restarted and may have lost its context."
            f" Read your brief: {first}, {then}. Write your report to {report}."
        )
    ]
    assert og.inbox[-1] == ("cos", f"Supervisor: a t-a: report written: {report}")
    assert registry.read_text() == ""  # the revive line renews nothing


def test_a_revive_line_whose_send_failed_is_sent_at_the_next_poll_once_the_runner_is_online(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, report = tmp_path / "registry", tmp_path / "a.md"
    registry.write_text(f"a={report}\n")
    og = Fleet(a=[told("brief", 60)])
    og.offline.add("a")
    og.refuse = 1  # the revive succeeds, the revive line's send answers 503
    supervised(og, registry, monkeypatch, 3)
    assert [text for sid, text in og.inbox if sid == "a"] == [
        f"Your session was restarted and may have lost its context. Write your report to {report}."
    ]


@pytest.mark.parametrize("child_ago", [600, 3600])
def test_a_session_waiting_on_a_working_child_is_not_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, child_ago: int
) -> None:
    """Its own history quiet for an hour: a child updated 10 min ago keeps it live, one quiet for an
    hour too lets the resume line go."""
    registry, report = tmp_path / "registry", tmp_path / "a.md"
    registry.write_text(f"a={report}\n")
    og = Fleet(a=[told("brief", 3600)])
    og.kids["a"] = time.time() - child_ago
    supervised(og, registry, monkeypatch, 1, silent=1800)
    sent = [text for sid, text in og.inbox if sid == "a"]
    assert sent == ([] if child_ago < 1800 else [omnigent_agent.NUDGE.format(report=report)])


@pytest.mark.parametrize("brief", [True, False])
def test_one_shot_supervise_names_the_brief_start_wrote_in_the_revive_line(
    tmp_path: Path, brief: bool
) -> None:
    report = tmp_path / "r.md"
    if brief:
        (tmp_path / "r.md.brief").write_text("do X")
    og = Owing([told("brief", 60)], {"runner_online": False}, {"runner_online": True}, {})
    og.infos.append({"status": "failed", "last_task_error": {"message": "later"}})
    omnigent_agent.supervise(og, {"a": report}, timeout=5)
    read = f" Read your brief: {tmp_path / 'r.md.brief'}." if brief else ""
    assert og.sent == [
        (
            f"Your session was restarted and may have lost its context.{read}"
            f" Write your report to {report}."
        )
    ]


def test_an_error_reading_one_session_is_logged_once_and_the_others_are_still_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "registry"
    report = aged(tmp_path / "b.md", 10)
    registry.write_text(f"a={tmp_path / 'a.md'}\njunk\nb={report}\n")
    og = Fleet(a=[told("brief", 60)], b=[told("brief", 60)])
    og.broken["a"] = omnigent_agent.Fail("GET /v1/sessions/a: HTTP 404 Not Found")
    supervised(og, registry, monkeypatch, 3)
    assert og.reads.count("a") == 3  # the loop went on
    assert registry.read_text() == f"a={tmp_path / 'a.md'}\njunk\n"
    out, err = capsys.readouterr()
    assert out.count("b t-b: report written") == 1
    assert err.count("a: GET /v1/sessions/a: HTTP 404 Not Found") == 1
    assert err.count("'junk': expected <session>=<report>; skipped") == 1


def test_a_quiet_timeout_window_is_logged_and_the_loop_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "registry"
    registry.write_text(f"a={tmp_path / 'a.md'}\n")
    og = Fleet(a=[told("brief", 60)])
    supervised(og, registry, monkeypatch, 2, timeout=0)
    assert og.reads == ["a", "a"]
    assert re.fullmatch(f"({STAMP}no event in 0s: a\n){{2}}", capsys.readouterr().err)


def test_a_notify_session_with_no_live_runner_is_revived_before_the_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry"
    report = aged(tmp_path / "a.md", 10)
    registry.write_text(f"a={report}\n")
    og = Fleet(a=[told("brief", 60)])
    og.offline.add("cos")
    supervised(og, registry, monkeypatch, 1, notify="cos")
    assert og.retried == ["cos"]
    assert og.inbox == [("cos", f"Supervisor: a t-a: report written: {report}")]
    assert registry.read_text() == ""


def test_start_and_run_arm_the_registry_with_their_brief_file_and_run_disarms_it_on_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    argv = ["start", "claude", "t", "b.md", "r.md", "--confirm-seconds", "0"]
    assert omnigent_agent.main(argv) == 0
    assert not (tmp_path / "registry").exists()  # no registry configured: nothing armed
    monkeypatch.setenv("OMNIGENT_SUPERVISE_REGISTRY", str(tmp_path / "registry"))
    assert (
        omnigent_agent.main(["start", "claude", "t2", "b.md", "s.md", "--confirm-seconds", "0"])
        == 0
    )
    s1 = f"s1={tmp_path / 's.md'}\t{tmp_path / 's.md.brief'}\n"
    assert (tmp_path / "registry").read_text() == s1
    verifier = ["start", "codex", "v", "b.md", "v.md", "--confirm-seconds", "0"]
    assert omnigent_agent.main([*verifier, "--role", "verifier.md", "--author", "claude"]) == 0
    v = f"s2={tmp_path / 'v.md'}\t{tmp_path / 'v.md.brief'}\tverdict\n"
    assert (tmp_path / "registry").read_text() == s1 + v
    s1 += v
    seen: list[str] = []
    info = og.info

    def reporting(sid: str) -> dict:
        seen.append((tmp_path / "registry").read_text())
        (tmp_path / "u.md").write_text("ok")
        return info(sid)

    og.info = reporting  # type: ignore[method-assign]
    assert (
        omnigent_agent.main(["run", "claude", "t3", "b.md", "u.md", "--confirm-seconds", "0"]) == 0
    )
    assert seen[0] == s1 + f"s3={tmp_path / 'u.md'}\t{tmp_path / 'u.md.brief'}\n"
    assert (tmp_path / "registry").read_text() == s1


def test_send_arms_the_registry_appending_its_message_file_and_disarms_it_on_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    registry, report = tmp_path / "registry", tmp_path / "r.md"
    monkeypatch.setenv("OMNIGENT_SUPERVISE_REGISTRY", str(registry))
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    sid = og.create("claude", "t")
    brief = tmp_path / "old.md.brief"
    registry.write_text(f"{sid}={tmp_path / 'old.md'}\t{brief}\nx={tmp_path / 'x.md'}\n")
    (tmp_path / "a.md").write_text("use main")
    seen: list[str] = []
    info = og.info

    def reporting(s: str) -> dict:
        if f"{sid}={report}" in registry.read_text():
            seen.append(registry.read_text())
            report.write_text("ok")
        return info(s)

    og.info = reporting  # type: ignore[method-assign]
    assert omnigent_agent.main(["send", sid, "a.md", "r.md", "--confirm-seconds", "0"]) == 0
    assert seen[0] == f"x={tmp_path / 'x.md'}\n{sid}={report}\t{brief}\t{tmp_path / 'a.md'}\n"
    assert registry.read_text() == f"x={tmp_path / 'x.md'}\n"


def test_wait_disarms_on_a_report_or_a_question_and_a_failed_wait_keeps_the_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "registry"
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    a, b, c = (og.create("claude", t) for t in "abc")
    registry.write_text(
        f"{a}={tmp_path / 'a.md'}\n{b}={tmp_path / 'b.md'}\n{c}={tmp_path / 'c.md'}\n"
    )
    (tmp_path / "a.md").write_text("ok")
    (tmp_path / "b.md.question").write_text("which?")
    flag = ["--registry", str(registry)]
    assert omnigent_agent.main(["wait", a, "a.md", *flag]) == 0
    assert omnigent_agent.main(["wait", b, "b.md", *flag]) == omnigent_agent.ASKED
    assert omnigent_agent.main(["wait", c, "c.md", "--timeout", "0", *flag]) == 1
    assert registry.read_text() == f"{c}={tmp_path / 'c.md'}\n"


def test_send_arms_only_once_its_message_is_in_the_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Armed before, the report left from the previous brief would count as written and the
    supervisor would drop the session at once."""
    monkeypatch.chdir(tmp_path)
    registry, report = tmp_path / "registry", aged(tmp_path / "r.md", 60)
    monkeypatch.setenv("OMNIGENT_SUPERVISE_REGISTRY", str(registry))
    og = FakeOmnigent(reply="done")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    sid = og.create("claude", "t")
    og.sessions[sid].append(told("brief", 120))
    (tmp_path / "a.md").write_text("fix it")
    at_send: list[str] = []
    stale: list[bool] = []
    send, info = og.send, og.info

    def sending(s: str, text: str) -> None:
        at_send.append(registry.read_text() if registry.exists() else "")
        send(s, text)

    def reporting(s: str) -> dict:
        if not stale and f"{sid}=" in (registry.read_text() if registry.exists() else ""):
            since, _ = omnigent_agent.instructed(og.items(sid), "")
            stale.append(omnigent_agent.written(report, since))  # the supervisor's view once armed
            report.write_text("fixed")
        return info(s)

    og.send, og.info = sending, reporting  # type: ignore[method-assign]
    assert omnigent_agent.main(["send", sid, "a.md", "r.md", "--confirm-seconds", "0"]) == 0
    assert at_send == [""]
    assert stale == [False]


QUESTION = {
    "elicitation_id": "e1",
    "params": {
        "content_preview": 'AskUserQuestion({"questions": [{"question": "Which base?"}]})',
        "ask_user_question": {"questions": [{"question": "Which base?"}]},
    },
}
APPROVAL = {"elicitation_id": "e2", "params": {"content_preview": "Bash(rm -rf build)"}}


def relay(
    og: FakeOmnigent,
    sid: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    text: str = "go",
    *flags: str,
) -> int:
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "QUEUED_SECONDS", 0)
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "cos")  # the relaying session its header names
    (tmp_path / "m.md").write_text(text)
    return omnigent_agent.main(["relay", sid, str(tmp_path / "m.md"), *flags])


def test_relay_to_an_idle_session_is_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    assert relay(og, sid, tmp_path, monkeypatch) == 0
    assert capsys.readouterr().out.strip() == f"session {sid}: delivered"
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "[relayed by cos]\ngo"


def test_relay_to_a_session_in_a_long_step_returns_queued_and_a_rerun_sends_no_second_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)  # a foreground command that outlasts the call
    sid = og.create("claude", "lead")
    assert relay(og, sid, tmp_path, monkeypatch) == omnigent_agent.QUEUED
    assert "queued until the session's current step ends; it lands then" in capsys.readouterr().err
    assert relay(og, sid, tmp_path, monkeypatch) == omnigent_agent.QUEUED
    assert og.posts == 1


def test_relay_rerun_after_the_copy_landed_unanswered_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    relay(og, sid, tmp_path, monkeypatch)
    assert relay(og, sid, tmp_path, monkeypatch) == 0
    assert capsys.readouterr().out.splitlines()[-1] == f"session {sid}: already delivered"
    assert og.posts == 1


def test_relay_of_the_same_words_after_the_session_replied_is_a_new_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="STILL WORKING")
    sid = og.create("claude", "lead")
    relay(og, sid, tmp_path, monkeypatch, "carry on")
    assert relay(og, sid, tmp_path, monkeypatch, "carry on") == 0
    assert og.posts == 2


def test_relay_holds_behind_an_open_question_unless_told_to_answer_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)  # the question holds every message behind it
    sid = og.create("claude", "cos")
    og.prompts = [QUESTION]
    assert relay(og, sid, tmp_path, monkeypatch, "sync done") == omnigent_agent.QUEUED
    assert og.resolved == []
    assert "Which base?" in capsys.readouterr().err


def test_relay_answers_a_question_with_the_message_instead_of_posting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)  # an interrupt would leave it held (omnigent#14)
    sid = og.create("claude", "lead")
    og.prompts = [QUESTION]
    assert relay(og, sid, tmp_path, monkeypatch, "use main\n", "--answer") == 0
    assert og.resolved == [(sid, "e1", "accept", {"Which base?": "use main"})]
    assert og.posts == 0
    assert "answered its open question" in capsys.readouterr().out


def test_relay_rerun_answers_a_question_raised_behind_its_own_pending_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Its own copy is no other input: waiting on it would exit 5 behind the question for good."""
    og = FakeOmnigent(hold=10**6)
    sid = og.create("claude", "lead")
    assert relay(og, sid, tmp_path, monkeypatch) == omnigent_agent.QUEUED
    og.prompts = [QUESTION]
    assert relay(og, sid, tmp_path, monkeypatch, "go", "--answer") == 0
    assert og.resolved == [(sid, "e1", "accept", {"Which base?": "go"})]
    assert og.posts == 1
    assert "answered its open question" in capsys.readouterr().out


def test_relay_revives_a_reaped_runner_then_delivers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    retried = reaped(og, {"recovered": True, "recovery": "runner_relaunched"}, 2)
    assert relay(og, sid, tmp_path, monkeypatch) == 0
    assert retried == [sid]
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "[relayed by cos]\ngo"


def test_relay_of_a_message_neither_pending_nor_landed_is_not_deliverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(deaf={0})
    sid = og.create("claude", "lead")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    (tmp_path / "m.md").write_text("go")
    args = ["relay", sid, str(tmp_path / "m.md"), "--confirm-seconds", "0"]
    assert omnigent_agent.main(args) == omnigent_agent.GONE
    assert "neither pending nor in history" in capsys.readouterr().err


def test_relay_never_answers_an_approval_prompt_and_says_what_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)
    sid = og.create("claude", "lead")
    og.prompts = [QUESTION, APPROVAL]
    assert relay(og, sid, tmp_path, monkeypatch) == omnigent_agent.QUEUED
    assert og.resolved == []
    assert capsys.readouterr().err.strip() == (
        f"session {sid}: queued behind an approval prompt (`approve` answers it): Bash(rm -rf build)"
        f" and a question: {QUESTION['params']['content_preview']}; {LANDS_AFTER_A_QUESTION}"
    )


# Nothing withdraws a queued input, so the line never invites a rerun of this message with
# --answer: the queued copy would land after the answer, the same words twice.
LANDS_AFTER_A_QUESTION = (
    "this message stays queued and lands once the question is answered (next time, to answer a"
    " question, use `relay --answer` instead of a plain relay, never after one)"
)


def test_relay_behind_only_a_question_names_relay_answer_for_next_time_not_approve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)
    sid = og.create("claude", "lead")
    og.prompts = [QUESTION]
    assert relay(og, sid, tmp_path, monkeypatch) == omnigent_agent.QUEUED
    assert capsys.readouterr().err.strip() == (
        f"session {sid}: queued behind a question: {QUESTION['params']['content_preview']};"
        f" {LANDS_AFTER_A_QUESTION}"
    )
    assert [omnigent_agent.text_of(p) for p in og.info(sid)["pending_inputs"]] == [
        f"{omnigent_agent.RELAYED.format(who='cos')}\ngo"
    ]  # the copy that lands once the question is answered


def test_relay_from_a_task_behind_a_question_says_only_the_owner_answers_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)
    sid = og.create("claude", "lead")
    og.prompts = [QUESTION]
    assert relay(og, sid, tmp_path, monkeypatch, "synced", "--from", "nightly") == (
        omnigent_agent.QUEUED
    )
    assert capsys.readouterr().err.strip() == (
        f"session {sid}: queued behind a question: {QUESTION['params']['content_preview']};"
        " this message stays queued and lands once the question is answered"
        " (only the owner's own relay answers a question)"
    )


def test_approve_resolves_each_approval_prompt_never_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    og.prompts = [QUESTION, APPROVAL]
    assert omnigent_agent.main(["approve", sid]) == 0
    assert og.resolved == [(sid, "e2", "accept", None)]
    assert capsys.readouterr().out == f"session {sid}: accepted Bash(rm -rf build)\n"
    assert omnigent_agent.main(["approve", sid]) == 1  # only the question is left
    assert "no approval prompt pending" in capsys.readouterr().err
    og.prompts = [APPROVAL, {**APPROVAL, "elicitation_id": "e3"}]
    og.fail = {"e2"}
    assert omnigent_agent.main(["approve", sid, "--decline"]) == 1  # e3 still answered
    assert og.resolved[-1] == (sid, "e3", "decline", None)
    out = capsys.readouterr().out
    assert "not answered: Bash(rm -rf build): POST resolve e2: HTTP 404" in out
    assert f"session {sid}: declined Bash(rm -rf build)" in out


def test_approve_with_only_a_question_pending_names_it_and_relay_answer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    og.prompts = [QUESTION]
    assert omnigent_agent.main(["approve", sid]) == 1
    assert og.resolved == []
    err = capsys.readouterr().err
    assert "only a question (`relay --answer` answers it): " in err
    assert QUESTION["params"]["content_preview"] in err


def test_relay_to_an_archived_session_is_not_deliverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    og.archive(sid)
    assert relay(og, sid, tmp_path, monkeypatch) == omnigent_agent.GONE
    assert f"session {sid} is archived" in capsys.readouterr().err
    assert og.posts == 0


class BroadcastFake(FakeOmnigent):
    """Sessions with a project, a host and an update time, listed as ``GET /v1/sessions`` lists
    them: top-level, archived ones left out."""

    def __init__(self, **kw: object) -> None:
        super().__init__(**kw)
        self.meta: dict[str, dict] = {}

    def add(self, title: str, project: str = "p1", age_hours: float = 0, **meta: object) -> str:
        sid = self.create("claude", title)
        self.meta[sid] = {
            "id": sid,
            "title": title,
            "project_id": project,
            "host_id": "h",
            "updated_at": time.time() - age_hours * 3600,
            **meta,
        }
        return sid

    project = omnigent_agent.Omnigent.project

    def info(self, sid: str) -> dict:
        if sid not in self.sessions:
            raise omnigent_agent.Fail(f"GET /v1/sessions/{sid}: TimeoutError: timed out")
        return {**self.meta.get(sid, {}), **super().info(sid)}

    def call(self, method: str, path: str, body: object = None) -> dict:
        if path.startswith("/v1/projects"):
            names = {"p1": "Agent skills", "p2": "Omnigent", "p3": "Omnigent · automations"}
            return {"data": [{"id": k, "name": v} for k, v in names.items()]}
        assert path.startswith("/v1/sessions?") and "sort_by=updated_at" in path
        assert "visibility=mine" in path  # never a session another user shared
        live = [self.info(s) for s in self.meta if s not in self.archived]
        return {"data": [s for s in live if not s.get("parent_session_id")]}

    def hosts(self) -> dict[str, str]:
        return {"h": "cc-experiments", "h2": "macbook"}


def broadcast(
    og: FakeOmnigent,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    text: str = "rule",
) -> int:
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "QUEUED_SECONDS", 0)
    (tmp_path / "m.md").write_text(text)
    return omnigent_agent.main(["broadcast", str(tmp_path / "m.md"), *args])


def test_broadcast_targets_followed_leads_and_recent_sessions_never_its_own_archived_or_automations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = BroadcastFake()
    lead, old_lead = og.add("lead"), og.add("old lead", age_hours=30)
    worker = og.add("worker", age_hours=30)  # owes a report: never followed, too old to be recent
    child = og.add("child", parent_session_id=lead)
    recent, stale = og.add("recent", "p2", 1), og.add("stale", "p2", 10)
    me, auto, gone = og.add("me"), og.add("cron", "p3"), og.add("gone lead")
    remote, extra = og.add("remote", host_id="h2"), og.add("extra", age_hours=30)
    og.archive(gone)
    monkeypatch.setenv("OMNIGENT_SESSION_ID", me)
    registry = tmp_path / "leads.registry"
    registry.write_text(
        f"{lead}=r.md\tfollow\n{worker}=w.md\n{old_lead}=o.md\tfollow\n{gone}=g.md\tfollow\n"
    )
    assert (
        broadcast(
            og,
            tmp_path,
            monkeypatch,
            "--registry",
            str(registry),
            "--dry-run",
            "--active-hours",
            "6",
        )
        == 0
    )
    out = capsys.readouterr().out
    assert og.posts == 0
    listed = {line.split()[0]: line for line in out.splitlines()}
    assert set(listed) == {lead, old_lead, recent, me, auto, gone, remote}
    assert listed[lead] == f"{lead} lead (Agent skills, cc-experiments)"
    assert listed[remote] == f"{remote} remote (Agent skills, macbook)"
    assert listed[me].endswith(": skipped: this session")
    assert listed[gone].endswith(": skipped: archived")
    assert listed[auto].endswith(": skipped: automations project 'Omnigent · automations'")
    assert stale not in out

    args = [
        "--registry",
        str(registry),
        "--active-hours",
        "6",
        "--project",
        "agent_skills",
        "--host",
        "cc-experiments",
        "--exclude",
        old_lead,
        "--include",
        extra,
        "--include",
        stale,
        "--include",
        child,
    ]
    assert broadcast(og, tmp_path, monkeypatch, *args) == 0
    lines = capsys.readouterr().out.splitlines()
    assert sorted(lines) == sorted(
        [
            f"{lead} lead (Agent skills, cc-experiments): delivered",
            f"{extra} extra (Agent skills, cc-experiments): delivered",
            f"{me} me (Agent skills, cc-experiments): skipped: this session",
            f"{gone} gone lead (Agent skills, cc-experiments): skipped: archived",
            f"{child} child (Agent skills, cc-experiments): skipped: a sub-agent",
        ]
    )
    assert omnigent_agent.text_of(og.sessions[lead][-1]) == f"[relayed by {me}]\nrule"
    assert og.posts == 2

    assert broadcast(og, tmp_path, monkeypatch, "--include", lead, "--project", "nope") == 1
    assert "--project nope names no project" in capsys.readouterr().err
    assert og.posts == 2


def test_broadcast_counts_a_target_it_could_not_read_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = BroadcastFake()
    lead = og.add("lead")
    for args in ([], ["--dry-run"], ["--project", "Agent skills"]):
        assert (
            broadcast(og, tmp_path, monkeypatch, "--include", lead, "--include", "s9", *args) == 1
        )
        out = capsys.readouterr().out
        assert "s9  (no project, ): failed: GET /v1/sessions/s9: TimeoutError: timed out\n" in out


def test_broadcast_relays_concurrently_one_line_each_and_exits_1_on_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = BroadcastFake(deaf={0})
    lost, *slow = [og.add(f"s{n}") for n in range(5)]
    send = og.send

    def slow_send(sid: str, text: str) -> None:
        time.sleep(0.5)
        send(sid, text)

    og.send = slow_send  # type: ignore[method-assign]
    started = time.monotonic()
    ids = [a for s in [lost, *slow] for a in ("--include", s)]
    assert broadcast(og, tmp_path, monkeypatch, *ids, "--confirm-seconds", "0") == 1
    assert time.monotonic() - started < 1.5  # five sends of 0.5 s, at once
    lines = {line.split()[0]: line for line in capsys.readouterr().out.splitlines()}
    assert lines[lost].endswith("neither pending nor in history for 0s; start a fresh run instead")
    assert ": failed: session " in lines[lost]
    assert all(lines[s].endswith(": delivered") for s in slow)


def test_broadcast_reports_a_held_message_queued_and_skips_a_pending_prompt_unanswered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = BroadcastFake(hold=10**6)
    sid = og.add("busy")
    assert broadcast(og, tmp_path, monkeypatch, "--include", sid) == 0
    assert capsys.readouterr().out.endswith(
        ": queued until the session's current step ends; it lands then\n"
    )
    for prompts in ([QUESTION], [APPROVAL], [QUESTION, APPROVAL]):
        asked = BroadcastFake()
        sid = asked.add("asking")
        asked.prompts = prompts
        assert broadcast(asked, tmp_path, monkeypatch, "--include", sid) == 0
        assert capsys.readouterr().out.endswith(": skipped: waiting on a question\n")
        assert asked.resolved == [] and asked.posts == 0


def test_status_prints_each_session_s_state_queued_inputs_and_last_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(reply="DONE: #12 merged")
    ended, busy, gone = og.create("claude", "a"), og.create("codex", "b"), og.create("claude", "c")
    og.send(ended, "go")
    og.archive(gone)
    og.hold = 10**6
    og.send(busy, "go")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    assert omnigent_agent.main(["status", ended, busy, gone]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"{ended}: turn ended",
        "last message: DONE: #12 merged",
        f"{busy} (1 queued input): running",
        "last message: (none)",
        f"{gone}: archived",
        "last message: (none)",
    ]


def test_status_never_prints_a_user_message_as_the_last_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    og.send(sid, "<system-reminder>be brief</system-reminder>")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    assert omnigent_agent.main(["status", sid]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "last message: (none)"
    og.reply = "on it"
    og.send(sid, "go")
    assert omnigent_agent.main(["status", sid]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "last message: on it"


HOSTS = {
    "hosts": [
        {"host_id": "h", "name": "here", "status": "online"},
        {"host_id": "m1", "name": "mac", "status": "online"},
        {"host_id": "t1", "name": "twin", "status": "offline"},
        {"host_id": "t2", "name": "twin", "status": "online"},
    ]
}


def test_host_resolves_a_name_or_an_id_and_refuses_none_or_several(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(omnigent_agent.Omnigent, "call", lambda self, m, p, b=None: HOSTS)
    og = object.__new__(omnigent_agent.Omnigent)
    assert og.host("mac") == og.host("m1") == "m1"
    with pytest.raises(omnigent_agent.Fail, match=r"names no host; hosts: here \(online\), mac"):
        og.host("nosuch")
    with pytest.raises(omnigent_agent.Fail, match="names several hosts"):
        og.host("twin")


def test_a_lead_on_another_host_gets_its_host_and_the_brief_inline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bodies = create_bodies(monkeypatch)
    omnigent_agent.Omnigent().create("claude", "t", top_level=True, host_id="m1")
    assert bodies[-1]["host_id"] == "m1"
    og = FakeOmnigent()
    sid, _ = omnigent_agent.start(
        og, "claude", "t", "do X", tmp_path / "r.md", None, 0, top_level=True, host_id="m1"
    )
    text = omnigent_agent.text_of(og.sessions[sid][1])
    assert text.startswith("Work on t. Your brief:") and text.endswith("do X")
    assert not (tmp_path / "r.md.brief").exists()
    omnigent_agent.start(
        og, "claude", "u", "do Y", tmp_path / "u.md", None, 0, top_level=True, host_id="h"
    )
    assert (tmp_path / "u.md.brief").exists()  # this host: the brief stays a file


def test_host_needs_top_level_and_another_host_needs_a_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(omnigent_agent.Omnigent, "call", lambda self, m, p, b=None: HOSTS)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    argv = ["start", "claude", "t", "b.md", "r.md", "--host", "mac"]
    assert omnigent_agent.main(argv) == 1
    assert "--host needs --top-level" in capsys.readouterr().err
    assert omnigent_agent.main([*argv, "--top-level"]) == 1
    assert "absolute paths there" in capsys.readouterr().err


def test_a_remote_start_neither_resolves_nor_checks_its_paths_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent.Omnigent, "call", lambda self, m, p, b=None: HOSTS)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    started: list[tuple[str, str]] = []
    monkeypatch.setattr(
        omnigent_agent,
        "start",
        lambda og, a, t, b, report, *rest, workspace=None, **kw: (
            started.append((str(report), str(workspace))) or ("s1", [])
        ),
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    (tmp_path / "w").symlink_to(tmp_path)  # a link here must not rewrite the path there
    (tmp_path / "w" / "r.md").write_text("an unrelated file here")
    w = tmp_path / "w"
    argv = ["start", "claude", "t", "b.md", str(w / "r.md"), "--top-level", "--host", "mac"]
    assert omnigent_agent.main([*argv, "--workspace", "w"]) == 1  # relative: whose cwd?
    assert omnigent_agent.main([*argv, "--workspace", str(w)]) == 0
    assert started == [(str(w / "r.md"), str(w))]


def test_resolve_posts_the_verdict_to_omnigent_s_elicitation_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict | None]] = []
    monkeypatch.setattr(omnigent_agent.Omnigent, "__init__", lambda self: None)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "call", lambda self, *a: calls.append(a) or {"queued": False}
    )
    omnigent_agent.Omnigent().resolve("s1", "e1", "accept", {"Which base?": "main"})
    omnigent_agent.Omnigent().resolve("s1", "e2", "decline")
    assert calls == [
        (
            "POST",
            "/v1/sessions/s1/elicitations/e1/resolve",
            {"action": "accept", "content": {"Which base?": "main"}},
        ),
        ("POST", "/v1/sessions/s1/elicitations/e2/resolve", {"action": "decline"}),
    ]


def serve_files(monkeypatch: pytest.MonkeyPatch, files: dict[str, dict]) -> list[str]:
    """A file API on localhost answering `files` by request path (404 for the rest); returns the
    request paths it saw. `main` talks to it through the real `Omnigent.call`."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    seen: list[str] = []
    real = omnigent_agent.Omnigent

    class Files(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            body = files.get(self.path)
            self.send_response(404 if body is None else 200)
            self.end_headers()
            self.wfile.write(json.dumps(body or {}).encode())

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Files)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def make() -> omnigent_agent.Omnigent:
        og = object.__new__(real)
        og.base, og._token = f"http://127.0.0.1:{server.server_port}", "synthetic"
        return og

    monkeypatch.setattr(omnigent_agent, "Omnigent", make)
    return seen


FS = "/v1/sessions/s9/resources/environments/default/filesystem"


def test_report_reads_an_absolute_path_from_the_host_with_each_segment_encoded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = f"{FS}/Users/k/my%20dir/r%23.md?limit=1000&base=host"
    seen = serve_files(monkeypatch, {path: {"content": "# done\n"}})
    assert omnigent_agent.main(["report", "s9", "/Users/k/my dir/r#.md"]) == 0
    assert seen[-1:] == [path]  # no leading %2F, '/' kept between segments
    assert capsys.readouterr().out == "# done\n\n"


def test_report_reads_a_relative_path_in_the_workspace_without_base(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = serve_files(monkeypatch, {f"{FS}/tmp/r.md?limit=1000": {"content": "hi"}})
    assert omnigent_agent.main(["report", "s9", "tmp/r.md"]) == 0
    assert seen == [f"{FS}/tmp/r.md?limit=1000"]


def test_report_reads_an_absolute_path_inside_the_workspace_relative_to_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # a host on an older Omnigent answers 404 to an absolute file read it serves relative
    files = {
        "/v1/sessions/s9": {"workspace": "/Users/k/ws"},
        f"{FS}/tmp/r.md?limit=1000": {"content": "ok"},
    }
    seen = serve_files(monkeypatch, files)
    assert omnigent_agent.main(["report", "s9", "/Users/k/ws/tmp/r.md"]) == 0
    assert seen == ["/v1/sessions/s9", f"{FS}/tmp/r.md?limit=1000"]
    assert (
        omnigent_agent.main(["report", "s9", "/Users/k/wsx/r.md"]) == 4
    )  # a sibling stays absolute
    assert seen[-1] == f"{FS}/Users/k/wsx/r.md?limit=1000&base=host"


def test_report_lists_a_directory_one_entry_per_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listing = {"data": [{"name": "a.md", "type": "file"}, {"name": "sub", "type": "directory"}]}
    serve_files(monkeypatch, {f"{FS}/tmp?limit=1000&base=host": listing})
    assert omnigent_agent.main(["report", "s9", "/tmp"]) == 0
    assert capsys.readouterr().out == "a.md\nsub/\n"


def test_modified_reads_the_files_time_from_its_folders_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [{"name": "r.md.brief", "modified_at": 5}, {"name": "r.md", "modified_at": 7}]
    seen = serve_files(monkeypatch, {f"{FS}/tmp/loop?limit=1000&base=host": {"data": entries}})
    og = omnigent_agent.Omnigent()
    assert og.modified("s9", "/tmp/loop/r.md") == 7.0
    assert seen[-1] == f"{FS}/tmp/loop?limit=1000&base=host"  # one listing, not the file
    assert og.modified("s9", "/tmp/loop/gone.md") == 0.0


def test_report_exits_4_naming_a_missing_file_and_1_for_other_statuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    serve_files(monkeypatch, {})
    assert omnigent_agent.main(["report", "s9", "/nope.md"]) == 4
    assert "/nope.md" in capsys.readouterr().err
    monkeypatch.setattr(omnigent_agent, "RETRY_SECONDS", ())
    og = omnigent_agent.Omnigent()
    og.base = "http://127.0.0.1:1"  # nothing listens: not a 404
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    assert omnigent_agent.main(["report", "s9", "/x.md"]) == 1


def test_report_without_a_path_reads_the_registry_line_else_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = tmp_path / "leads.registry"
    registry.write_text("s9=/Users/k/r.md\n")
    path = f"{FS}/Users/k/r.md?limit=1000&base=host"
    seen = serve_files(monkeypatch, {path: {"content": "x"}})
    assert omnigent_agent.main(["report", "s9", "--registry", str(registry)]) == 0
    assert seen[-1:] == [path]
    assert omnigent_agent.main(["report", "s8", "--registry", str(registry)]) == 2
    assert omnigent_agent.main(["report", "s9"]) == 2
    assert "OMNIGENT_SUPERVISE_REGISTRY" in capsys.readouterr().err


# Every row of the design's routing table (§ Routing an event): the event, what the small model
# would answer if asked, and the expected (settled by, action). None: the model is never asked.
ROUTES = [
    ("archived", {"kind": "archived"}, None, ("rule", "absorb")),
    ("parked", {"kind": "ended", "last": "PARKED: the host is full"}, None, ("rule", "record")),
    (
        "still working, named wait",
        {"kind": "ended", "last": "STILL WORKING: waiting on the verifier"},
        None,
        ("rule", "record"),
    ),
    ("exact repeat", {"kind": "ended", "last": "on it", "repeat": True}, None, ("rule", "record")),
    (
        "quiet again after a nudge, the same words",
        {"kind": "ended", "last": "on it", "repeat": True, "nudged": True},
        None,
        ("rule", "act"),
    ),
    ("quiet, mid-work", {"kind": "ended", "last": "on it"}, "none", ("model", "record")),
    ("quiet, stalled", {"kind": "ended", "last": "on it"}, "act", ("model", "nudge")),
    ("quiet, for the owner", {"kind": "ended", "last": "hm"}, "owner", ("model", "owner")),
    ("quiet, no model answer", {"kind": "ended", "last": "hm"}, "unsure", ("model", "act")),
    ("deadline, unknown", {"kind": "deadline", "last": "on it"}, None, ("rule", "nudge")),
    (
        "deadline, after a nudge",
        {"kind": "deadline", "last": "on it", "nudged": True},
        None,
        ("rule", "act"),
    ),
    (
        "deadline, named wait",
        {"kind": "deadline", "last": "STILL WORKING: CI is running"},
        None,
        ("rule", "act"),
    ),
    ("deadline, parked", {"kind": "deadline", "last": "PARKED: full"}, None, ("rule", "record")),
    (
        "quiet again after a nudge",
        {"kind": "ended", "last": "on it", "nudged": True},
        None,
        ("rule", "act"),
    ),
    ("failed, first", {"kind": "failed"}, None, ("rule", "revive")),
    ("failed, again", {"kind": "failed", "revived": True}, None, ("rule", "act")),
    ("done", {"kind": "ended", "last": "**DONE** PR #1 merged"}, None, ("rule", "done")),
    ("report path", {"kind": "ended", "last": "/r/a.md"}, None, ("rule", "read-report")),
    (
        "report head, done",
        {"kind": "ended", "last": "/r/a.md", "head": "DONE: merged"},
        None,
        ("rule", "done"),
    ),
    (
        "report head, still working on CI",
        {"kind": "ended", "last": "/r/a.md", "head": "STILL WORKING: CI running"},
        None,
        ("rule", "record"),
    ),
    (
        "report head, no ending",
        {"kind": "ended", "last": "/r/a.md", "head": "BLOCKED: no access"},
        None,
        ("rule", "act"),
    ),
    (
        "user needed, covered",
        {"kind": "ended", "last": "USER NEEDED: merge?", "decisions": True},
        "act",
        ("model", "act"),
    ),
    (
        "user needed, not covered",
        {"kind": "ended", "last": "USER NEEDED: delete prod?", "decisions": True},
        "owner",
        ("model", "owner"),
    ),
    (
        "user needed, the model unsure",
        {"kind": "ended", "last": "USER NEEDED: x", "decisions": True},
        "none",
        ("model", "act"),
    ),
    (
        "user needed, no standing decisions",
        {"kind": "ended", "last": "USER NEEDED: x"},
        None,
        ("rule", "owner"),
    ),
    ("approval prompt", {"kind": "blocked"}, None, ("rule", "owner")),
    ("question", {"kind": "blocked", "question": True}, None, ("rule", "act")),
    (
        "owed report, outcome",
        {"kind": "terminal", "line": "a t: report written: /r.md"},
        None,
        ("rule", "act"),
    ),
    (
        "owed report, prompt",
        {"kind": "terminal", "line": "a t: blocked on a prompt: Bash(x)"},
        None,
        ("rule", "owner"),
    ),
    ("owed report, a notice", {"kind": "notice"}, None, ("rule", "record")),
]


@pytest.mark.parametrize(("row", "event", "answer", "routed"), ROUTES, ids=[r[0] for r in ROUTES])
def test_each_row_of_the_routing_table_settles_its_event(
    row: str, event: dict, answer: str | None, routed: tuple[str, str]
) -> None:
    asked: list[bool] = []

    def ask() -> tuple[str, str]:
        asked.append(True)
        return answer or "act", "the model's why"

    by, action, why = omnigent_agent.route(event, ask)
    assert (by, action) == routed and why
    assert asked == ([True] if answer else [])


@pytest.mark.parametrize("answer", ["none", "act", "owner"])
def test_no_model_answer_routes_an_approval_prompt_anywhere_but_the_owner(answer: str) -> None:
    for event in ({"kind": "blocked"}, {"kind": "terminal", "line": "a: blocked on a prompt: x"}):
        assert omnigent_agent.route(event, lambda: (answer, "x"))[1] == "owner"


def model_answers(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[dict]:
    """``claude -p`` faked: each call is recorded; ``answer`` is its stdout, an exit code, or an
    exception to raise."""
    calls: list[dict] = []

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess:
        calls.append({"cmd": cmd, **kw})
        if isinstance(answer, BaseException):
            raise answer
        code, out = (answer, "") if isinstance(answer, int) else (0, str(answer))
        return subprocess.CompletedProcess(cmd, code, out, "")

    monkeypatch.setattr(omnigent_agent.subprocess, "run", run)
    return calls


def test_the_small_model_is_one_headless_call_with_the_event_cut_on_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = model_answers(monkeypatch, 'thinking\n{"route": "none", "why": "mid-work"}\n')
    assert REAL_TRIAGE("x" * 5000, "- merge on green") == ("none", "mid-work")
    cmd, kw = calls[0]["cmd"], calls[0]
    assert cmd[:4] == ["claude", "-p", "--model", "claude-haiku-5-5"]
    for flag, value in (("--tools", ""), ("--setting-sources", "")):
        assert cmd[cmd.index(flag) + 1] == value
    assert "--strict-mcp-config" in cmd
    assert "- merge on green" in cmd[cmd.index("--system-prompt") + 1]
    assert kw["input"] == "x" * 4000 and kw["timeout"] == 20
    assert kw["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "1000"
    monkeypatch.setenv("OMNIGENT_SMALL_MODEL", "claude-other")
    REAL_TRIAGE("e", "")
    assert calls[1]["cmd"][3] == "claude-other"
    assert "(none)" in calls[1]["cmd"][calls[1]["cmd"].index("--system-prompt") + 1]


@pytest.mark.parametrize(
    "answer",
    [
        "route: none",
        '{"route": "approve"}',
        '["none"]',
        "",
        1,
        subprocess.TimeoutExpired("claude", 20),
        FileNotFoundError("claude"),
    ],
    ids=[
        "unparseable",
        "no such route",
        "not an object",
        "empty",
        "failed",
        "timed out",
        "missing",
    ],
)
def test_an_unparseable_failed_or_timed_out_model_answer_routes_to_act(
    monkeypatch: pytest.MonkeyPatch, answer: object
) -> None:
    model_answers(monkeypatch, answer)
    route, why = REAL_TRIAGE("an event", "")
    assert route == "unsure" and why
    ask = lambda: REAL_TRIAGE("an event", "d")
    for last in ("USER NEEDED: x", "on it"):  # a question, a quiet end: act, never a nudge
        event = {"kind": "ended", "last": last, "decisions": True}
        assert omnigent_agent.route(event, ask)[:2] == ("model", "act")


def test_standing_decisions_are_their_section_else_the_whole_file_else_none(
    tmp_path: Path,
) -> None:
    board = tmp_path / "board.md"
    board.write_text("# Board\n## Standing decisions (owner's)\n- merge on green\n## Next\nx\n")
    assert omnigent_agent.standing(board) == "- merge on green"
    board.write_text("- approve reversible progress\n")
    assert omnigent_agent.standing(board) == "- approve reversible progress"
    assert omnigent_agent.standing(None) == "" == omnigent_agent.standing(tmp_path / "gone.md")


class Leads(Lead):
    """Followed leads, each with its own history and ``snaps`` fields (status, prompts, ...)."""

    def __init__(self, **histories: list[dict]) -> None:
        Fleet.__init__(self, **histories)
        self.snap: dict = {}
        self.snaps: dict[str, dict] = {}

    def info(self, sid: str) -> dict:
        return {**Fleet.info(self, sid), **self.snaps.get(sid, {})}


def follows(tmp_path: Path, *sids: str, after: dict[str, str] | None = None) -> Path:
    registry = tmp_path / "registry"
    after = after or {}
    registry.write_text(
        "".join(
            f"{s}={tmp_path / s}.md\tfollow" + (f"\tafter={after[s]}" if s in after else "") + "\n"
            for s in sids
        )
    )
    return registry


def events_of(registry: Path) -> list[dict]:
    lines = registry.with_suffix(".events.jsonl").read_text().splitlines()
    return [json.loads(e) for e in lines]


def test_a_second_stall_without_progress_escalates_and_sends_no_second_nudge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    monkeypatch.setattr(omnigent_agent, "triage", lambda event, decisions: ("act", "stalled"))
    og = Lead(told("brief", 60), ending("Looked at the logs.", 0))
    # quiet 300 s: the model says stalled, so the nudge; it lands, and the lead stays quiet
    at = {1: 301.0, 2: 302.0, 3: 333.0, 4: 634.0}
    supervised(
        og,
        registry,
        monkeypatch,
        5,
        lambda p: offset.__setitem__(0, at[p]),
        notify="cos",
        console=True,
    )
    assert [t for s, t in og.inbox if s == "a"] == [omnigent_agent.LEAD_NUDGE]
    [post] = posted(og)
    assert post.startswith("Supervisor [act] b-")
    assert "[act] a t-a: turn ended, quiet 301s (quiet again after its nudge)" in post
    assert [(e["settled"], e["action"]) for e in events_of(registry)] == [
        ("model", "nudge"),
        ("rule", "act"),
    ]
    lead = state_of(registry)["leads"]["a"]
    assert lead["nudges"] == 1 and lead["nudged_at"] == lead["progress_at"]
    assert [i["status"] for i in state_of(registry)["intents"]] == ["done"]


def test_a_quiet_lead_the_model_finds_mid_work_is_recorded_and_not_posted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_model: list[str]
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("Reading the diff.", 0))
    supervised(
        og,
        registry,
        monkeypatch,
        2,
        lambda p: offset.__setitem__(0, 301.0),
        notify="cos",
        console=True,
    )
    assert og.inbox == [] and len(no_model) == 1 and "Reading the diff." in no_model[0]
    assert [(e["settled"], e["action"], e["why"]) for e in events_of(registry)] == [
        ("model", "record", "fake")
    ]


@pytest.mark.parametrize("landed", [True, False])
def test_a_crash_between_an_actions_send_and_done_never_sends_it_again_after_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, landed: bool
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: on it", 0))
    og.snap = {"status": "running"}
    real = og.send

    def crash(sid: str, text: str) -> None:
        if sid == "a":
            if landed:
                real(sid, text)
            raise Stop  # the supervisor dies before it marks the nudge done
        real(sid, text)

    og.send = crash  # type: ignore[method-assign]
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda p: offset.__setitem__(0, 1201.0),
        notify="cos",
        console=True,
    )
    [intent] = state_of(registry)["intents"]
    assert (intent["action"], intent["status"]) == ("nudge", "open")
    assert state_of(registry)["leads"]["a"]["nudges"] == 1  # counted before the send
    og.send = real  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)  # the restart
    assert [t for s, t in og.inbox if s == "a"] == [omnigent_agent.LEAD_NUDGE] * landed
    [intent] = state_of(registry)["intents"]
    assert intent["status"] == ("done" if landed else "escalated")
    escalated = [p for p in posted(og) if "may not have reached it" in p]
    assert len(escalated) == (0 if landed else 1)


@pytest.mark.parametrize("landed", [True, False])
def test_a_crash_right_after_a_post_is_accepted_posts_it_once_after_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, landed: bool
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("DONE: shipped", 5))
    og.histories["cos"] = []
    real = og.send

    def crash(sid: str, text: str) -> None:
        if sid == "cos":
            if landed:
                real(sid, text)
                for n in range(150):  # newer items push it past the newest page of 100
                    og.histories["cos"].append(
                        {**said("assistant", "ok", f"c{n}"), "created_at": time.time()}
                    )
            raise Stop  # accepted, and the supervisor dies before it marks it delivered
        real(sid, text)

    og.send = crash  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)
    [pending] = state_of(registry)["pending_posts"]
    assert pending["id"].startswith("b-") and state_of(registry)["attention"]
    og.send = real  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)  # the restart
    posts = posted(og)
    assert len(posts) == 1 and posts[0].startswith(f"Supervisor [act] {pending['id']}: 1 event")
    if landed:
        assert og.pages >= 2  # found on the second page of the history
    state = state_of(registry)
    assert (state["pending_posts"], state["attention"]) == ([], [])


def test_a_restart_inside_the_post_window_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = follows(tmp_path, "a", "b")
    offset = skewed(monkeypatch)
    og = Leads(
        a=[told("brief", 60), ending("DONE: one", 5)],
        b=[told("brief", 60), ending("STILL WORKING: waiting on CI", 5)],
    )
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert len(posted(og)) == 1
    offset[0] = 60.0
    og.histories["b"].append(ending("DONE: two", 0))
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)  # a restart at 60 s
    assert len(posted(og)) == 1  # the window from the first post holds across it
    assert [e["session"] for e in state_of(registry)["attention"]] == ["b"]
    offset[0] = 301.0
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert len(posted(og)) == 2 and "[act] b t-b: turn ended" in posted(og)[1]


def test_a_restart_inside_the_model_window_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_model: list[str]
) -> None:
    registry = follows(tmp_path, "a", "b")
    board = tmp_path / "board.md"
    board.write_text("## Standing decisions\n- merge on green\n")
    offset = skewed(monkeypatch)
    og = Leads(a=[told("brief", 60)], b=[told("brief", 60)])
    supervised(og, registry, monkeypatch, 1, console=True, decisions=board)
    state = state_of(registry)
    state["rate"]["model_calls"] = [time.time() - 3500] * 30  # the hour's calls, spent
    registry.with_suffix(".state.json").write_text(json.dumps(state))
    og.histories["a"].append(ending("USER NEEDED: merge it?", 0))
    supervised(og, registry, monkeypatch, 1, console=True, decisions=board)  # the restart
    assert no_model == []
    assert events_of(registry)[-1]["why"] == "over 30 small-model calls an hour"
    offset[0] = 101.0  # the oldest calls are past the hour
    og.histories["b"].append(ending("USER NEEDED: merge it?", 0))
    supervised(og, registry, monkeypatch, 1, console=True, decisions=board)
    assert len(no_model) == 1 and len(state_of(registry)["rate"]["model_calls"]) == 1


def test_twenty_events_in_a_minute_make_one_post_then_one_combined_post_with_every_owner_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sids = [f"l{i}" for i in range(20)]
    registry = follows(tmp_path, *sids)
    offset = skewed(monkeypatch)
    monkeypatch.setattr(omnigent_agent, "PROMPT_CONFIRM_SECONDS", 0.0)  # batching, not the wait
    og = Leads(**{s: [told("brief", 60), ending("STILL WORKING: on it", 50)] for s in sids})

    def blocked(i: int) -> dict:  # an approval prompt for an even lead, a question for an odd one
        params = (
            {"ask_user_question": {"questions": [{"question": "which?"}]}, "message": "which?"}
            if i % 2
            else {"content_preview": f"Bash(rm {i})"}
        )
        return {"pending_elicitations": [{"elicitation_id": f"e{i}", "params": params}]}

    og.snaps["l0"] = blocked(0)
    waiting: list[str] = []

    def later(poll: int) -> None:
        if poll < 20:
            offset[0] = poll * 3.0
            og.snaps[f"l{poll}"] = blocked(poll)
        else:
            waiting.extend(line["status.line"] for s, line in og.labels if s == "cos")
            offset[0] = 301.0

    supervised(og, registry, monkeypatch, 21, later, notify="cos", console=True)
    first, combined = posted(og)
    assert first.startswith("Supervisor [owner] b-") and "1 event\n" in first
    assert combined.startswith("Supervisor [owner] b-") and "19 events\n" in combined
    for i in range(1, 20):
        to = "act" if i % 2 else "owner"
        assert f"[{to}] l{i} t-l{i}: blocked on a prompt: " in combined
    assert waiting[-1] == "needs you: 9"  # the owner events waiting for the second post
    assert [line["status.line"] for s, line in og.labels if s == "cos"][-1] == ""
    assert state_of(registry)["attention"] == []


def test_the_supervisor_never_approves_a_prompt() -> None:
    source = inspect.getsource(omnigent_agent.supervise_registry)
    assert "approve(" not in source and "resolve(" not in source


def test_an_archived_lead_is_absorbed_with_no_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("DONE: shipped", 5))
    og.snap = {"archived": True}
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)
    assert posted(og) == [] and registry.read_text() == ""
    assert state_of(registry)["leads"] == {}
    assert [(e["kind"], e["action"]) for e in events_of(registry)] == [("archived", "absorb")]


def test_a_done_is_told_to_each_lead_waiting_on_it_and_posted_with_its_report_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = follows(tmp_path, "a", "b", "c", after={"b": "a"})
    og = Leads(
        a=[told("brief", 60), ending("DONE: PR #7 merged\nmore", 5)],
        b=[told("brief", 60), ending("STILL WORKING: waiting on lead a", 5)],
        c=[told("brief", 60), ending("STILL WORKING: waiting on CI", 5)],
    )
    og.files[f"{tmp_path / 'a'}.md"] = "DONE: merged\n" + "".join(f"l{n}\n" for n in range(9))
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)
    told_b = "Supervisor: a t-a, the lead you wait on, ended: DONE: PR #7 merged"
    assert [(s, t) for s, t in og.inbox if s != "cos"] == [("b", told_b)]
    [post] = posted(og)
    assert (
        f"a t-a: turn ended: DONE: PR #7 merged\nreport {tmp_path / 'a'}.md:\nDONE: merged\n"
        in post
    )
    assert post.endswith("l3")  # the report's first 5 lines
    assert state_of(registry)["leads"]["b"]["waits_on"] == ["a"]


def test_a_failed_lead_is_revived_once_then_goes_to_the_chief_of_staff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("STILL WORKING: building", 50))
    og.snap = {"status": "failed", "last_task_error": {"message": "runner lost"}}
    states = {1: "running", 2: "failed"}
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda p: og.snap.update(status=states[p]),
        notify="cos",
        console=True,
    )
    assert [t for s, t in og.inbox if s == "a"] == [omnigent_agent.LEAD_REVIVE]
    [post] = posted(og)
    assert "[act] a t-a: failed: runner lost (failed again after its revive)" in post
    assert state_of(registry)["leads"]["a"]["revives"] == 1


def test_fyi_and_decisions_need_console_and_after_needs_a_top_level_start_with_a_registry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = str(tmp_path / "registry")
    assert omnigent_agent.main(["supervise", "--registry", registry, "--fyi", "post"]) == 1
    assert "--fyi and --decisions need --console" in capsys.readouterr().err
    brief = tmp_path / "b.md"
    brief.write_text("x")
    args = ["start", "claude", "t", str(brief), str(tmp_path / "a.md"), "--after", "s9"]
    assert omnigent_agent.main(args) == 1
    assert "--after needs --top-level and a registry" in capsys.readouterr().err


def test_a_top_level_start_after_another_lead_writes_the_after_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    registry, brief = tmp_path / "registry", tmp_path / "b.md"
    brief.write_text("do X")
    args = ["start", "claude", "t", str(brief), str(tmp_path / "a.md"), "--top-level"]
    assert omnigent_agent.main([*args, "--registry", str(registry), "--after", "s9"]) == 0
    line = registry.read_text().strip()
    assert line.endswith("\tfollow\tafter=s9")
    assert omnigent_agent.entry(line)[2:] == ([tmp_path / "a.md.brief"], False, True, "s9", False)


def test_a_waiting_lead_on_a_question_is_not_told_so_its_question_gets_no_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = follows(tmp_path, "a", "b", after={"b": "a"})
    og = Leads(a=[told("brief", 60), ending("DONE: merged", 5)], b=[told("brief", 60)])
    question = {"ask_user_question": {"questions": [{"question": "go?"}]}, "message": "go?"}
    og.snaps["b"] = {"pending_elicitations": [{"elicitation_id": "e", "params": question}]}
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert [s for s, t in og.inbox] == ["cos"]
    assert "the supervisor's tell was not delivered: it waits on a prompt" in posted(og)[0]


@pytest.mark.parametrize("why", ["model failed", "allowance spent"])
def test_a_quiet_end_the_model_could_not_route_goes_to_the_chief_of_staff_not_a_nudge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, why: str
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    monkeypatch.setattr(omnigent_agent, "triage", REAL_TRIAGE)
    model_answers(monkeypatch, FileNotFoundError("claude"))
    if why == "allowance spent":
        state = omnigent_agent.fresh_state()
        state["rate"]["model_calls"] = [time.time()] * 30
        registry.with_suffix(".state.json").write_text(json.dumps(state))
    og = Lead(told("brief", 60), ending("Reading code.", 0))
    supervised(
        og,
        registry,
        monkeypatch,
        2,
        lambda p: offset.__setitem__(0, 301.0),
        notify="cos",
        console=True,
    )
    assert [s for s, t in og.inbox] == ["cos"]  # no nudge to the lead
    assert events_of(registry)[-1]["action"] == "act"
    assert "[act] a t-a: turn ended, quiet 301s" in posted(og)[0]


@pytest.mark.parametrize("needed_by", ["action", "model call", "post"])
def test_a_failed_state_write_stops_the_side_effect_it_guards_and_the_next_poll_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_model: list[str], needed_by: str
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    last = {"action": "STILL WORKING: on it", "model call": "Reading code.", "post": "DONE: x"}
    og = Lead(told("brief", 60), ending(last[needed_by], 0))
    og.snap = {"status": "running"} if needed_by == "action" else {}
    real, full = omnigent_agent.write_state, [False]

    def write_state(path: Path, state: dict) -> None:
        if full[0]:
            raise OSError("disk full")
        real(path, state)

    monkeypatch.setattr(omnigent_agent, "write_state", write_state)
    at = {"action": 1201.0, "model call": 301.0, "post": 0.0}[needed_by]
    seen: list[tuple] = []

    def later(poll: int) -> None:
        seen.append((list(og.inbox), list(no_model)))
        offset[0] = at
        full[0] = poll == 1  # the disk is full for the poll that needs the write

    if needed_by == "post":
        full[0] = True
    supervised(og, registry, monkeypatch, 4, later, notify="cos", console=True)
    if needed_by == "post":
        assert seen[0] == ([], [])  # the post's pending write failed: nothing sent
        assert posted(og)[0].startswith("Supervisor [act] b-") and len(posted(og)) == 1
    else:
        assert seen[1] == ([], [])  # the poll with the full disk sent nothing, asked nothing
        if needed_by == "action":
            assert [t for s, t in og.inbox if s == "a"] == [omnigent_agent.LEAD_NUDGE]
        else:
            assert len(no_model) == 1  # asked once the write succeeds
    assert [i["status"] for i in state_of(registry)["intents"]] == ["done"] * (
        needed_by == "action"
    )


def test_a_crash_while_telling_the_first_waiting_lead_leaves_the_others_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = follows(tmp_path, "a", "b", "c", after={"b": "a", "c": "a"})
    og = Leads(
        a=[told("brief", 60), ending("DONE: shipped", 5)],
        b=[told("brief", 60)],
        c=[told("brief", 60)],
    )
    real = og.send

    def crash(sid: str, text: str) -> None:
        real(sid, text)
        if sid == "b":
            raise Stop  # b was told; the supervisor dies before c's turn

    og.send = crash  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert sorted(i["session"] for i in state_of(registry)["intents"]) == ["b", "c"]
    og.send = real  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 2, notify="cos", console=True)  # the restart
    assert [s for s, t in og.inbox if s != "cos"] == ["b"]  # never sent again
    status = {i["session"]: i["status"] for i in state_of(registry)["intents"]}
    assert status == {"b": "done", "c": "escalated"}
    assert re.search(
        r"^\[act\] c( t-c)?: the supervisor's tell may not have reached it",
        posted(og)[0],
        re.MULTILINE,
    )


def test_a_late_retry_of_a_pending_post_reserves_its_own_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = follows(tmp_path, "a", "b")
    offset = skewed(monkeypatch)
    og = Leads(a=[told("brief", 60), ending("DONE: one", 5)], b=[told("brief", 60)])
    og.histories["cos"] = []
    real, at = og.send, []

    def crash(sid: str, text: str) -> None:
        if sid == "cos":
            raise Stop  # the first attempt never lands

    og.send = crash  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)

    def record(sid: str, text: str) -> None:
        at.append(offset[0]) if sid == "cos" else None
        real(sid, text)

    og.send = record  # type: ignore[method-assign]
    offset[0] = 299.0
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)  # the restart: a retry
    og.histories["b"].append(ending("DONE: two", 0))
    for t in (301.0, 598.0, 600.0):
        offset[0] = t
        supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert at == [299.0, 600.0]


def test_a_crash_right_after_a_terminal_line_is_dropped_keeps_its_owner_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry"
    registry.write_text(f"a={tmp_path / 'a.md'}\n")
    og = Lead(told("brief", 60))
    prompt = {"elicitation_id": "e1", "params": {"content_preview": "Bash(rm example)"}}
    og.snap = {"pending_elicitations": [prompt]}
    arm = omnigent_agent.arm

    def crash(*args: object, **kwargs: object) -> None:
        arm(*args, **kwargs)  # type: ignore[arg-type]
        raise Stop  # the line is gone; the supervisor dies before the poll's end

    monkeypatch.setattr(omnigent_agent, "arm", crash)
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert registry.read_text() == ""
    monkeypatch.setattr(omnigent_agent, "arm", arm)
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)  # the restart
    [post] = posted(og)
    assert post.startswith("Supervisor [owner] b-")
    assert "[owner] a t-a: blocked on a prompt: Bash(rm example)" in post


def test_an_older_identical_message_does_not_close_an_open_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told(omnigent_agent.LEAD_NUDGE, 600), ending("STILL WORKING: waiting on CI", 5))
    state = omnigent_agent.fresh_state()
    intent = {"id": "nudge:a:e2", "session": "a", "action": "nudge", "event": "e2"}
    intent.update(text=omnigent_agent.LEAD_NUDGE, at=time.time(), status="open")
    state["intents"] = [intent]  # a crash before its send; the nudge in the history is 10 min old
    registry.with_suffix(".state.json").write_text(json.dumps(state))
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert state_of(registry)["intents"][0]["status"] == "escalated"
    assert "the supervisor's nudge may not have reached it" in "\n".join(posted(og))
    assert [s for s, t in og.inbox if s == "a"] == []  # never sent again


@pytest.mark.parametrize("held", ["post", "intent"])
def test_a_copy_still_pending_after_a_crash_counts_as_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, held: str
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("DONE: shipped" if held == "post" else "on it", 5))
    og.histories["cos"] = []
    to = "cos" if held == "post" else "a"
    pending: list[dict] = []  # the session took the copy and has not folded it in yet

    def hold(sid: str, text: str) -> None:
        assert sid == to  # nothing else is sent
        pending.append(
            {"pending_id": f"p{len(pending)}", "content": [{"type": "input_text", "text": text}]}
        )
        raise Stop

    if held == "intent":
        state = omnigent_agent.fresh_state()
        intent = {"id": "nudge:a:e1", "session": "a", "action": "nudge", "event": "e1"}
        intent.update(text=omnigent_agent.LEAD_NUDGE, at=time.time(), status="open")
        state["intents"] = [intent]  # a crash after its send
        registry.with_suffix(".state.json").write_text(json.dumps(state))
        pending.append(
            {"pending_id": "p0", "content": [{"type": "input_text", "text": intent["text"]}]}
        )
    info = og.info
    og.info = lambda sid: {**info(sid), **({"pending_inputs": pending} if sid == to else {})}  # type: ignore[method-assign]
    og.send = hold  # type: ignore[method-assign]
    for _ in range(2 if held == "post" else 1):  # a post: the crash, then the restart
        supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert len(pending) == 1
    final = state_of(registry)
    assert final["pending_posts"] == [] and final["attention"] == []
    if held == "intent":
        assert final["intents"][0]["status"] == "done"


def test_a_write_failing_after_the_model_answered_keeps_the_spent_call_and_its_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    state = omnigent_agent.fresh_state()
    state["rate"]["model_calls"] = [time.time()] * 29
    registry.with_suffix(".state.json").write_text(json.dumps(state))
    og = Lead(told("brief", 60), ending("Reading code.", 0))
    calls: list[tuple] = []
    monkeypatch.setattr(
        omnigent_agent, "triage", lambda *args: calls.append(args) or ("act", "stalled")
    )
    real, failed = omnigent_agent.write_state, []

    def write_state(path: Path, state: dict) -> None:
        if state["intents"] and not failed:  # the nudge's intent, once: the model has answered
            failed.append(path)
            raise OSError("disk full")
        real(path, state)

    monkeypatch.setattr(omnigent_agent, "write_state", write_state)
    seen: list[tuple] = []

    def later(poll: int) -> None:
        seen.append((len(calls), len(state_of(registry)["rate"]["model_calls"]), list(og.inbox)))
        offset[0] = 301.0

    supervised(og, registry, monkeypatch, 3, later, notify="cos", console=True)
    assert seen[1] == (1, 30, [])  # the write failed: one call, spent and kept, nothing sent
    assert len(calls) == 1  # the retry acts on the answer it has
    assert [t for s, t in og.inbox] == [omnigent_agent.LEAD_NUDGE]
    assert len(state_of(registry)["rate"]["model_calls"]) == 30


def test_an_ask_after_a_done_line_is_the_ending_and_goes_to_the_owner() -> None:
    text = "DONE: #271 merged.\nUSER NEEDED: pick option A or B"
    assert omnigent_agent.ending_of(text) == "USER NEEDED"
    assert omnigent_agent.ending_of("DONE: merged\nPARKED: later") == "DONE"
    assert omnigent_agent.ending_of("no ending") is None
    assert (
        omnigent_agent.lead_status({"status": "idle"}, [ending(text, 0)])["ending"] == "USER NEEDED"
    )
    event = {"kind": "ended", "last": text}
    assert omnigent_agent.route(event, lambda: ("none", "x")) == (
        "rule",
        "owner",
        "no standing decision to cover it",
    )


def _agent_server(monkeypatch: pytest.MonkeyPatch, pages: dict[str, object]) -> list[tuple]:
    """``Omnigent.call`` answering from ``pages`` by path; the calls it saw are returned."""
    calls: list[tuple] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        calls.append((method, path, body))
        return pages[path]

    monkeypatch.setattr(omnigent_agent.Omnigent, "call", call)
    monkeypatch.setattr(
        omnigent_agent.Omnigent, "__init__", lambda self: setattr(self, "host_id", "h")
    )
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)
    return calls


def test_a_users_own_agent_is_found_after_the_server_s_pages_and_gets_its_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _agent_server(
        monkeypatch,
        {
            "/v1/agents": {"data": [{"name": "s1", "id": "x"}], "has_more": True, "last_id": "x"},
            "/v1/agents?after=x": {"data": [{"name": "s2", "id": "y"}], "has_more": False},
            "/v1/agents?scope=user": {
                "data": [{"name": "mine0", "id": "m0"}],
                "has_more": True,
                "last_id": "m0",
            },
            "/v1/agents?scope=user&after=m0": {"data": [{"name": "claude-cloud", "id": "cc"}]},
            "/v1/projects": {"data": []},
            "/v1/sessions": {"id": "s1"},
        },
    )
    omnigent_agent.Omnigent().create("claude-cloud", "t", permission_mode="plan")
    assert calls[-1][2]["agent_id"] == "cc"
    assert "terminal_launch_args" not in calls[-1][2]  # a claude flag, not this agent's


def test_an_unknown_agent_fails_naming_it_before_any_session_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _agent_server(
        monkeypatch, {"/v1/agents": {"data": []}, "/v1/agents?scope=user": {"data": []}}
    )
    with pytest.raises(omnigent_agent.Fail, match="agent nope not registered"):
        omnigent_agent.Omnigent().create("nope", "t")
    assert all(path != "/v1/sessions" for _, path, _ in calls)


def _copies(
    config_b: dict, listed: tuple[str, str] = ("c1", "c2"), record_b: dict | None = None
) -> dict[str, object]:
    """Pages for agents c1 (older) and c2 (newer), both called claude-cloud, listed in
    ``listed`` order across the server's and the user's pages, c2's config and record carrying
    ``config_b`` and ``record_b`` on top of c1's."""
    same = {"policies": [], "skills": ["s"], "terminals": [], "mcp_servers_editable": True}
    record = {
        "c1": {"created_at": 100, **same},
        "c2": {"created_at": 200, **same, **(record_b or {})},
    }
    first, second = ({"name": "claude-cloud", "id": i, **record[i]} for i in listed)
    config = {"name": "claude-cloud", "harness": "acp:claude-cloud", "instructions": None}
    return {
        "/v1/agents": {"data": [first]},
        "/v1/agents?scope=user": {"data": [second, {"name": "solo", "id": "c3"}]},
        "/v1/agents/c1/config": {"id": "c1", "version": 1, **config},
        "/v1/agents/c2/config": {"id": "c2", "version": 2, **config, **config_b},
        "/v1/projects": {"data": []},
        "/v1/sessions": {"id": "s1"},
    }


def test_a_name_held_by_identical_copies_resolves_to_the_newest_in_any_listing_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for listed in (("c1", "c2"), ("c2", "c1")):
        calls = _agent_server(monkeypatch, _copies({}, listed))
        omnigent_agent.Omnigent().create("claude-cloud", "t")
        assert calls[-1][2]["agent_id"] == "c2"
    bookkeeping = {"updated_at": 300, "object": "agent"}
    for config_b, record_b in (({"created_at": 200, "updated_at": 300}, {}), ({}, bookkeeping)):
        calls = _agent_server(monkeypatch, _copies(config_b, record_b=record_b))
        omnigent_agent.Omnigent().create("claude-cloud", "t")
        assert calls[-1][2]["agent_id"] == "c2"


def test_a_name_held_by_agents_that_differ_is_refused_with_their_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for config_b, record_b in (
        ({"instructions": "other"}, {}),
        ({"harness": "claude-native"}, {}),
        (
            {},
            {"policies": [{"name": "p"}]},
        ),  # policies, skills and terminals are only on the record
        ({}, {"skills": ["s", "t"]}),
        ({}, {"mcp_servers_editable": False}),  # a server flag, not bookkeeping
    ):
        calls = _agent_server(monkeypatch, _copies(config_b, record_b=record_b))
        with pytest.raises(omnigent_agent.Fail, match="agents c1, c2 are all called claude-cloud"):
            omnigent_agent.Omnigent().create("claude-cloud", "t")
        assert all(path != "/v1/sessions" for _, path, _ in calls)


def test_an_agent_is_taken_by_its_id_even_when_others_share_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _agent_server(monkeypatch, _copies({}))
    omnigent_agent.Omnigent().create("c1", "t")
    assert calls[-1][2]["agent_id"] == "c1"
    omnigent_agent.Omnigent().create("solo", "t")
    assert calls[-1][2]["agent_id"] == "c3"
    assert all("/config" not in path for _, path, _ in calls)  # configs only for an ambiguous name


def test_an_agent_outside_the_aliases_gets_its_brief_inline(tmp_path: Path) -> None:
    og = FakeOmnigent()
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "claude-cloud", "t", "do X", report, None, 0)
    sent = next(i for i in og.items(sid) if i["type"] == "message")["content"][0]["text"]
    assert sent.startswith("Work on t. Your brief:") and sent.endswith("do X")
    assert not omnigent_agent.brief_of(report).exists()
    with pytest.raises(omnigent_agent.Fail, match="for claude sessions"):
        omnigent_agent.start(og, "claude-cloud", "t", "x", report, None, 0, permission_mode="plan")


def test_antigravity_runs_a_role_only_with_its_approvals_bypassed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OMNIGENT_PERMISSION_MODE", raising=False)
    og = FakeOmnigent()
    og.harnesses["agy"] = "antigravity-native"
    with pytest.raises(omnigent_agent.Fail, match="blocks unattended"):
        omnigent_agent.start(og, "agy", "t", "x", tmp_path / "r.md", "verifier.md", 0)
    with pytest.raises(omnigent_agent.Fail, match="for claude sessions"):
        omnigent_agent.start(
            og, "agy", "t", "x", tmp_path / "r.md", None, 0, permission_mode="plan"
        )
    omnigent_agent.start(
        og,
        "agy",
        "t",
        "x",
        tmp_path / "r.md",
        "verifier.md",
        0,
        permission_mode="bypassPermissions",
    )
    calls = _agent_server(
        monkeypatch,
        {
            "/v1/agents": {"data": [{"name": "agy", "id": "a", "harness": "antigravity-native"}]},
            "/v1/agents?scope=user": [],
            "/v1/projects": {"data": []},
            "/v1/sessions": {"id": "s1"},
        },
    )
    omnigent_agent.Omnigent().create("agy", "t", permission_mode="bypassPermissions")
    assert calls[-1][2]["terminal_launch_args"] == ["--dangerously-skip-permissions"]
    # Effort is the user's agy settings; the launcher passes none, whatever the environment says.
    monkeypatch.setenv("OMNIGENT_EFFORT_ANTIGRAVITY", "high")
    omnigent_agent.Omnigent().create("agy", "t")
    assert "terminal_launch_args" not in calls[-1][2]


def test_a_native_agent_outside_the_aliases_reads_its_brief_from_a_file(tmp_path: Path) -> None:
    og = FakeOmnigent()
    og.harnesses["antigravity-native-ui"] = "antigravity-native"
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "antigravity-native-ui", "t", "do X", report, None, 0)
    sent = next(i for i in og.items(sid) if i["type"] == "message")["content"][0]["text"]
    brief = omnigent_agent.brief_of(report)
    assert sent == f"Work on t: read {brief} and do what it says."
    assert brief.read_text().endswith("do X")


def test_reloadable_takes_a_replaced_script_once_it_is_stable_and_compiles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "omnigent_agent.py"
    script.write_text("x = 1\n")
    ran = script.stat().st_mtime_ns
    seen = {"ran": ran, "last": ran}
    assert not omnigent_agent.reloadable(script, seen)  # unchanged
    os.utime(script, ns=(ran + 10**9, ran + 10**9))
    assert not omnigent_agent.reloadable(script, seen)  # changed: wait one look
    assert omnigent_agent.reloadable(script, seen)  # stable and compiles
    script.write_text("def broken(:\n")
    os.utime(script, ns=(ran + 2 * 10**9, ran + 2 * 10**9))
    assert not omnigent_agent.reloadable(script, seen)
    assert not omnigent_agent.reloadable(script, seen)
    assert "does not load" in capsys.readouterr().err
    assert not omnigent_agent.reloadable(script, seen)  # logged once, kept running
    assert capsys.readouterr().err == ""
    script.unlink()
    assert not omnigent_agent.reloadable(script, seen)  # an install replacing it


def test_the_supervisor_re_executes_itself_when_its_script_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "omnigent_agent.py"
    script.write_text("x = 1\n")
    registry = following(tmp_path)
    og = Lead(told("brief", 60))
    execs: list[tuple[str, list[str]]] = []

    def execv(path: str, argv: list[str]) -> None:
        execs.append((path, argv))
        raise Stop

    monkeypatch.setattr(omnigent_agent.os, "execv", execv)
    monkeypatch.setattr(omnigent_agent.sys, "argv", ["agent.py", "supervise", "--registry", "r"])
    bump = lambda poll: os.utime(script, ns=(10**18, 10**18)) if poll == 1 else None
    supervised(og, registry, monkeypatch, 5, bump, console=True, script=script)
    assert execs == [
        (sys.executable, [sys.executable, str(script), "supervise", "--registry", "r"])
    ]
    assert f"restarting: {script} changed" in capsys.readouterr().out
    assert state_of(registry)["leads"]["a"]  # written before the exec


def test_a_failed_state_write_before_the_restart_keeps_the_old_process_until_one_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "omnigent_agent.py"
    script.write_text("x = 1\n")
    registry = following(tmp_path)
    og = Lead(told("brief", 60))
    real_reload, real_write = omnigent_agent.reloadable, omnigent_agent.write_state
    ready, seen_order = [False], []  # "fail", "ok" per write once the script changed, "exec"

    def reloadable(path: Path, seen: dict[str, int]) -> bool:
        ready[0] = real_reload(path, seen)
        return ready[0]

    def write_state(path: Path, state: dict) -> None:
        if ready[0] and "fail" not in seen_order:  # the first write at the restart fails
            seen_order.append("fail")
            raise OSError("disk full")
        real_write(path, state)
        if "fail" in seen_order:
            seen_order.append("ok")

    def execv(path: str, argv: list[str]) -> None:
        seen_order.append("exec")
        raise Stop

    monkeypatch.setattr(omnigent_agent, "reloadable", reloadable)
    monkeypatch.setattr(omnigent_agent, "write_state", write_state)
    monkeypatch.setattr(omnigent_agent.os, "execv", execv)
    bump = lambda poll: os.utime(script, ns=(10**18, 10**18)) if poll == 1 else None
    supervised(og, registry, monkeypatch, 6, bump, console=True, script=script)
    assert seen_order[0] == "fail"  # the restart's write failed once
    assert seen_order[-1] == "exec" and seen_order.count("exec") == 1
    assert seen_order[-2] == "ok"  # no exec after the failure; one right after a write succeeded


def test_the_supervisor_restarts_only_once_its_unposted_lines_are_posted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "omnigent_agent.py"
    script.write_text("x = 1\n")
    registry = tmp_path / "registry"
    report = aged(tmp_path / "a.md", 10)
    registry.write_text(f"a={report}\n")
    og = Fleet(a=[told("brief", 60)])
    og.refuse = 4  # the notify session refuses the posts of the first polls
    inbox_at_exec: list[list[tuple[str, str]]] = []

    def execv(path: str, argv: list[str]) -> None:
        inbox_at_exec.append(list(og.inbox))
        raise Stop

    monkeypatch.setattr(omnigent_agent.os, "execv", execv)
    bump = lambda poll: os.utime(script, ns=(10**18, 10**18)) if poll == 1 else None
    supervised(og, registry, monkeypatch, 10, bump, notify="cos", script=script)
    assert og.refuse == 0
    assert inbox_at_exec == [[("cos", f"Supervisor: a t-a: report written: {report}")]]


def test_a_re_exec_drops_the_session_pairs_its_registry_already_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, report = tmp_path / "registry", tmp_path / "a.md"
    argv = ["agent.py", "supervise", "--registry", str(registry), f"a={report}"]
    monkeypatch.setattr(omnigent_agent.sys, "argv", argv)
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: Fleet())
    replayed: list[list[str]] = []

    def supervise_registry(*_: object) -> None:  # it never returns
        replayed.append(sys.argv[1:])
        raise Stop

    monkeypatch.setattr(omnigent_agent, "supervise_registry", supervise_registry)
    with pytest.raises(Stop):
        omnigent_agent.main(argv[1:])
    assert f"a={report.resolve()}" in registry.read_text()  # armed
    assert replayed == [["supervise", "--registry", str(registry)]]  # a restart re-arms nothing


def test_relay_from_a_task_never_answers_an_open_question_and_says_whose_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)  # the question holds every message behind it
    sid = og.create("claude", "cos")
    og.prompts = [QUESTION]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "QUEUED_SECONDS", 0)
    (tmp_path / "m.md").write_text("ACTION NEEDED: the sync printed a note")
    argv = ["relay", sid, str(tmp_path / "m.md"), "--from", "skills-sync", "--answer"]
    assert omnigent_agent.main(argv) == omnigent_agent.QUEUED
    assert og.resolved == []
    assert og.posts == 1
    header = omnigent_agent.RELAY_FROM.format(source="skills-sync")
    assert "Which base?" in capsys.readouterr().err  # it names the question that holds it
    sent = [omnigent_agent.text_of(p) for p in og.info(sid)["pending_inputs"]]
    assert sent == [f"{header}\nACTION NEEDED: the sync printed a note"]


def test_relay_from_a_task_to_an_idle_session_is_delivered_with_its_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "cos")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    (tmp_path / "m.md").write_text("synced")
    assert omnigent_agent.main(["relay", sid, str(tmp_path / "m.md"), "--from", "sync"]) == 0
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == (
        omnigent_agent.RELAY_FROM.format(source="sync") + "\nsynced"
    )


def deadlines(registry: Path) -> list[dict]:
    log = registry.with_suffix(".events.jsonl")
    return [e for e in events_of(registry) if e["kind"] == "deadline"] if log.exists() else []


def direct_lead(tmp_path: Path) -> Path:
    registry = following(tmp_path)
    assert omnigent_agent.mark_direct(registry, "a")
    return registry


def test_a_lead_the_owner_drives_directly_gets_no_deadline_and_no_nudge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = direct_lead(tmp_path)
    og = Lead(told("brief", 4000), ending("STILL WORKING: building", 3600))
    og.snap = {"status": "running"}
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True, fyi="post", timeout=0)
    assert fyis(og) == []
    assert deadlines(registry) == []
    assert "no event in" not in capsys.readouterr().err  # only a direct lead is registered
    assert state_of(registry)["leads"]["a"]["direct"] is True


def test_a_direct_lead_still_reports_done_and_records_a_quiet_end() -> None:
    def route(last: str) -> tuple[str, str, str]:
        event = {"kind": "ended", "last": last, "direct": True, "decisions": True}
        return omnigent_agent.route(event, lambda: pytest.fail("no small model for it"))

    assert route("DONE: merged #5")[1] == "done"
    assert route("Here is what I found.")[:2] == ("rule", "record")
    assert route("Which one?\n\nUSER NEEDED")[:2] == ("rule", "record")
    deadline = {"kind": "deadline", "last": "", "direct": True}
    assert omnigent_agent.route(deadline, lambda: ("act", ""))[1] == "record"


def test_a_direct_lead_s_question_and_quiet_report_stay_with_the_owner() -> None:
    no_model = lambda: pytest.fail("no model call")
    question = {"kind": "blocked", "question": True, "direct": True}
    assert omnigent_agent.route(question, no_model)[1] == "record"
    prompt = {"kind": "blocked", "direct": True}
    assert omnigent_agent.route(prompt, no_model)[1] == "owner"
    quiet = {"kind": "ended", "direct": True, "last": "/tmp/f.md", "head": "Here is what I found."}
    assert omnigent_agent.route(quiet, no_model)[1] == "record"
    done = {"kind": "ended", "direct": True, "last": "/tmp/f.md", "head": "DONE: shipped"}
    assert omnigent_agent.route(done, no_model)[1] == "done"


def test_a_later_instruction_to_a_lead_with_no_output_starts_a_new_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 4000))
    og.snap = {"status": "running"}

    def later(poll: int) -> None:
        offset[0] = {1: 1140.0, 2: 1201.0}[poll]
        if poll == 1:
            og.histories["a"].append(told("carry on with the revised task", 0))

    supervised(og, registry, monkeypatch, 3, later, notify="cos", console=True, fyi="post")
    assert deadlines(registry) == []


def test_direct_marks_and_clears_a_registry_line_keeping_its_other_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = following(tmp_path)
    before = registry.read_text()
    argv = ["direct", "a", "--registry", str(registry)]
    assert omnigent_agent.main(argv) == 0
    assert registry.read_text() == before.rstrip("\n") + "\tdirect\n"
    assert omnigent_agent.entry(registry.read_text().strip())[6] is True
    omnigent_agent.arm(registry, "a", tmp_path / "a.md", followed=True)  # a re-arm keeps it
    assert omnigent_agent.entry(registry.read_text().strip())[6] is True
    assert omnigent_agent.main([*argv, "--off"]) == 0
    assert omnigent_agent.entry(registry.read_text().strip())[6] is False
    capsys.readouterr()
    assert omnigent_agent.main(["direct", "zz", "--registry", str(registry)]) == 1
    assert "no line for zz" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("message", "deadline"),
    [
        ("Owner's answer: free the disk, then carry on.", False),  # a relay: a new chain
        (omnigent_agent.LEAD_NUDGE, True),  # the supervisor's own line: no progress
        (omnigent_agent.NUDGE.format(report="/r/a.md"), True),  # wait's nudge, the same
        (omnigent_agent.PR_NUDGE.format(pr=7), True),
    ],
)
def test_a_new_instruction_to_an_idle_lead_starts_a_new_progress_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str, deadline: bool
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 40000), ending("Disk full.\n\nUSER NEEDED", 34000), told(message, 5))
    og.snap = {"status": "running"}  # the relay woke it
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True, fyi="post")
    assert bool(deadlines(registry)) is deadline


def typed(text: str, n: int, **extra: object) -> dict:
    """A user message as the server stores it: ``created_by`` on a typed and a posted one alike."""
    return {**said("user", text, f"i{n}"), "created_at": 1792961740 + n, "created_by": "o", **extra}


QUOTE = "yes, force-push the branch for #35"


@pytest.mark.parametrize(
    "message",
    [
        f"Work on fix-35. Your brief:\n\n{QUOTE}",
        f"Work on fix-35: read /tmp/b.md and do what it says.\n{QUOTE}",
        f"Supervisor: a t-a: {QUOTE}",
        f"Supervisor [act] b-1: 1 event\n{QUOTE}",
        f"{omnigent_agent.RELAY_FROM.format(source='sync')}\n{QUOTE}",
        f"{omnigent_agent.RELAYED.format(who='cos')}\n{QUOTE}",
        f"[System: sub-agent b finished] {QUOTE}",
        f"{omnigent_agent.REVIVED} {QUOTE}",
        f"{omnigent_agent.NUDGE.format(report='r.md')} {QUOTE}",
    ],
)
def test_owner_said_rejects_the_quote_behind_every_posted_opening(
    message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = Fleet(cos=[typed(message, 1)])
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    assert omnigent_agent.main(["owner-said", "cos", QUOTE]) == 1


def test_owner_said_rejects_a_message_without_an_author_and_takes_the_owners_work_on(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = Fleet(cos=[typed(QUOTE, 1, created_by=None)])
    og.base = "https://omnigent.test"
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    assert omnigent_agent.main(["owner-said", "cos", QUOTE]) == 1
    og.histories["cos"].append(typed(f"Work on #35 next. {QUOTE}", 2))  # typed by the owner
    assert omnigent_agent.main(["owner-said", "cos", QUOTE]) == 0
    assert f"> Work on #35 next. {QUOTE}" in capsys.readouterr().out


def test_owner_said_finds_the_owners_own_message_and_rejects_posted_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    filler = [typed(f"note {n}", n) for n in range(150)]  # the owner's words sit past one page
    og = Fleet(
        cos=[
            typed("yes, force-push\nKuba's branch for #35", 999),
            *filler,
            typed("Supervisor [act] b-1: owner said yes, force-push Kuba's branch for #35", 1001),
            typed("[relayed by cos]\nyes, force-push Kuba's branch for #35", 1002),
            typed("yes, force-push Kuba's branch for #35", 1003, is_meta=True),  # a harness notice
        ]
    )
    og.base = "https://omnigent.test"
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    quote = tmp_path / "q.md"
    quote.write_text("yes, force-push Kuba's branch for #35\n")  # a line break collapsed
    assert omnigent_agent.main(["owner-said", "cos", str(quote)]) == 0
    assert capsys.readouterr().out.strip() == (
        "owner said it: https://omnigent.test/c/cos item i999 at 2026-10-25T21:12Z by o\n"
        "> yes, force-push Kuba's branch for #35"
    )
    og.histories["cos"].pop(0)  # only the posted copies are left
    assert omnigent_agent.main(["owner-said", "cos", str(quote)]) == 1
    assert "only in a message an agent or Omnigent posted (item i1003" in capsys.readouterr().out
    quote.write_text("approve the deploy")
    assert omnigent_agent.main(["owner-said", "cos", str(quote)]) == 1
    assert "in no message of its history" in capsys.readouterr().out


def test_a_broadcast_is_marked_as_a_relay_so_owner_said_rejects_its_quote(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    monkeypatch.setattr(omnigent_agent, "QUEUED_SECONDS", 0)
    assert omnigent_agent.broadcast(og, [(sid, "lead")], "yes, force-push", 0, "cos") is False
    posted = og.sessions[sid][-1]
    assert omnigent_agent.text_of(posted) == "[relayed by cos]\nyes, force-push"
    assert omnigent_agent.agent_posted(omnigent_agent.text_of(posted))  # owner-said skips it
    capsys.readouterr()


def test_a_plain_relay_is_marked_as_a_relay_by_the_sending_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    assert relay(og, sid, tmp_path, monkeypatch, "Owner (cos, 22:10): yes") == 0
    assert (
        omnigent_agent.text_of(og.sessions[sid][-1]) == "[relayed by cos]\nOwner (cos, 22:10): yes"
    )


def test_a_message_argument_is_a_file_or_the_text_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "cos")
    assert omnigent_agent.main(["relay", sid, "carry on with step 3"]) == 0
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "[relayed by cos]\ncarry on with step 3"
    long = "Do X.\n" + "word " * 100  # past NAME_MAX: OSError File name too long before
    assert omnigent_agent.main(["relay", sid, long]) == 0
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == f"[relayed by cos]\n{long}"
    (tmp_path / "m.md").write_text("from a file")
    assert omnigent_agent.main(["relay", sid, "m.md"]) == 0
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "[relayed by cos]\nfrom a file"
    capsys.readouterr()
    assert omnigent_agent.main(["relay", sid, "missing.md"]) == 2
    assert capsys.readouterr().err.strip() == (
        "missing.md: no such file; pass a file or the text itself"
    )


def test_send_given_text_lists_it_as_a_followup_file_in_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(reply="done")
    sid = og.create("claude", "lead")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    report, registry = tmp_path / "r.md", tmp_path / "leads.registry"
    seen: list[str] = []
    monkeypatch.setattr(
        omnigent_agent,
        "wait",
        lambda *a, **k: seen.append(registry.read_text()) or str(report),
    )
    argv = ["send", sid, "use main as the base", str(report), "--registry", str(registry)]
    assert omnigent_agent.main(argv) == 0
    followup = tmp_path / "r.md.followup"
    assert followup.read_text() == "use main as the base"
    assert str(followup) in seen[0]


def test_a_report_s_ending_is_read_past_its_title_and_a_report_without_one_still_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = omnigent_agent.report_head
    assert head("# Report\n\nDONE: merged #1\n- notes") == "DONE: merged #1"
    assert head("# R\n\nbody\n\nSTILL WORKING: waiting on\nthe worker\n\nlater") == (
        "STILL WORKING: waiting on\nthe worker\n\nlater"
    )
    assert head("# R\n\nbody") == "# R" and head("") == ""
    for report, action in (
        ("# Report\n\nDONE: merged", "done"),
        ("# Report\n\nnotes\n\nSTILL WORKING on the verifier", "record"),
        ("# Report\n\nBLOCKED: no access", "act"),
    ):
        event = {"kind": "ended", "last": "/r/a.md", "head": head(report)}
        assert omnigent_agent.route(event, lambda: ("act", ""))[1] == action, report
    registry, og, _ = path_only_lead(tmp_path, "# Title\n\nDONE: merged\nmore")
    supervised(og, registry, monkeypatch, 1, notify="cos", console=True)
    assert state_of(registry)["leads"]["a"]["ending"] == "DONE"


def test_a_child_s_session_id_is_a_named_wait() -> None:
    sid = "ef38cdf6" + "0" * 24
    assert (
        omnigent_agent.wait_of("STILL WORKING: waiting on ef38cdf6 (s1806-r3: round 2)")
        == "ef38cdf6"
    )
    assert omnigent_agent.wait_of(f"STILL WORKING on {sid}") == sid
    assert omnigent_agent.wait_of("STILL WORKING: on deadbeefcafe-ish things") == "unknown"


def test_a_failed_small_model_call_names_what_it_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    said = "API Error: Claude's response exceeded the 1000 output token maximum."
    monkeypatch.setattr(
        omnigent_agent.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, said + "\n", ""),
    )
    assert REAL_TRIAGE("an event", "") == ("unsure", f"small model: exit 1: {said}")
    monkeypatch.setattr(
        omnigent_agent.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", ""),
    )
    assert REAL_TRIAGE("an event", "") == ("unsure", "small model: exit 2")


def test_a_top_level_start_from_a_followed_lead_subscribes_that_lead_and_arms_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "own_id", lambda: "lead")
    monkeypatch.chdir(tmp_path)
    registry, brief = tmp_path / "registry", tmp_path / "b.md"
    registry.write_text(f"lead={tmp_path / 'l.md'}\tfollow\n")
    brief.write_text("do X")
    args = ["start", "claude", "t", str(brief), str(tmp_path / "a.md"), "--top-level"]
    assert omnigent_agent.main([*args, "--registry", str(registry)]) == 0
    assert registry.read_text() == f"lead={tmp_path / 'l.md'}\tfollow\n"
    assert og.subscriptions == [("lead", "s0")]
    assert "started from lead lead" in capsys.readouterr().err
    registry.write_text(
        f"lead={tmp_path / 'l.md'}\n"
    )  # owes a report, not followed: arms as before
    args[4] = str(tmp_path / "c.md")
    assert omnigent_agent.main([*args, "--registry", str(registry)]) == 0
    assert "s1=" in registry.read_text() and og.subscriptions == [("lead", "s0")]


def test_a_helper_started_from_a_followed_leads_child_subscribes_the_lead_not_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "own_id", lambda: "child")
    monkeypatch.setattr(omnigent_agent, "parent_id", lambda: "lead")
    monkeypatch.chdir(tmp_path)
    registry, brief = tmp_path / "registry", tmp_path / "b.md"
    registry.write_text(f"lead={tmp_path / 'l.md'}\tfollow\n")
    brief.write_text("do X")
    args = ["start", "claude", "t", str(brief), str(tmp_path / "a.md"), "--top-level"]
    assert omnigent_agent.main([*args, "--registry", str(registry)]) == 0
    assert og.subscriptions == [("lead", "s0")]
    assert registry.read_text() == f"lead={tmp_path / 'l.md'}\tfollow\n"


@pytest.mark.parametrize(
    ("text", "wait"),
    [
        ("STILL WORKING: waiting on deployment", "deployment"),
        ("STILL WORKING: the gate waits for the database", "database"),
        ("STILL WORKING: waiting on the verifier", "verifier"),  # a wait word still wins
        ("STILL WORKING: on it", "unknown"),  # a bare "on" names nothing
        ("STILL WORKING: waiting on ef38cdf6 (s1806-r3)", "ef38cdf6"),  # a child's session id
        ("STILL WORKING: verifier pass 2 on 188a4278", "verifier"),  # a commit is not the wait
        ("STILL WORKING: worker fixing R3 on 68cafc1a", "worker"),
        ("STILL WORKING: rebased on 188a4278 and running the gate", "unknown"),
        ("STILL WORKING: waiting on it", "unknown"),
    ],
)
def test_a_wait_named_after_waiting_on_or_for_is_that_wait(text: str, wait: str) -> None:
    assert omnigent_agent.wait_of(text) == wait


@pytest.mark.parametrize(
    ("report", "ending", "wait"),
    [
        # a quoted example ending is not the report's
        (
            "# R\n\nThe test uses:\n```text\nDONE: merged\n```\n\nSTILL WORKING: waiting on the verifier\n",
            "STILL WORKING",
            "verifier",
        ),
        (
            "# R\n\nThe old route printed:\n~~~\nUSER NEEDED: x\n~~~\n\nDONE: merged\n",
            "DONE",
            "unknown",
        ),
        (
            "# R\n\n> DONE: an old pass\n\n`USER NEEDED: quoted`\n\n**PARKED:** no slot\n",
            "PARKED",
            "parked",
        ),
        # a quoted ending inside the STILL WORKING tail is not the report's
        (
            (
                "# R\n\nSTILL WORKING: waiting on the verifier. The old route printed:\n\n"
                "`USER NEEDED: no standing decision`\n\nso the test now pins it.\n"
            ),
            "STILL WORKING",
            "verifier",
        ),
        (
            (
                "# R\n\nThe old supervisor post read:\n\n> STILL WORKING: checking\n"
                "> USER NEEDED: pick a base\n\nDONE: merged #12\n"
            ),
            "DONE",
            "unknown",
        ),
        # a wait named after a paragraph break still counts
        ("# R\n\nSTILL WORKING: checking status\n\nWaiting on worker\n", "STILL WORKING", "worker"),
    ],
)
def test_report_head_routes_the_reports_own_ending_and_wait(
    report: str, ending: str, wait: str
) -> None:
    head = omnigent_agent.report_head(report)
    assert (omnigent_agent.ending_of(head) or "STILL WORKING") == ending
    assert omnigent_agent.wait_of(head) == wait


def test_report_head_keeps_little_of_a_long_report() -> None:
    report = "# R\n\nSTILL WORKING: waiting on the verifier\n" + "- proof detail\n" * 5000
    head = omnigent_agent.report_head(report)
    assert len(head) <= omnigent_agent.REPORT_WAIT_CHARS and head.endswith("- proof detail")
    assert omnigent_agent.wait_of(head) == "verifier"


def test_the_preambles_detach_runs_here_and_records_its_exit_code(tmp_path: Path) -> None:
    """The launcher the preambles name starts the command in its own session and returns at once."""
    for preamble in (
        omnigent_agent.PREAMBLE,
        omnigent_agent.PR_PREAMBLE,
        omnigent_agent.LEAD_PREAMBLE,
    ):
        assert f"`{omnigent_agent.DETACH} <cmd>`" in preamble
        assert "never short polls, since each call re-reads the whole context" in preamble
        assert "up to a total budget you state" in preamble
    pid, log = tmp_path / "pid", tmp_path / "log"
    script = f'echo $$ > {pid}; sleep 1; (exit 3); echo "exit $?" > {log}'
    began = time.monotonic()
    subprocess.run(
        ["sh", "-c", f"{omnigent_agent.DETACH} sh -c '{script}'"], check=True, timeout=10
    )
    assert time.monotonic() - began < 1  # the caller's shell is gone before the run ends
    deadline = time.monotonic() + 10
    while not (log.is_file() and log.read_text()) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert log.read_text() == "exit 3\n"
    assert int(pid.read_text()) != os.getpid()
