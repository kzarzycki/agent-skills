"""scripts/omnigent_agent.py with the Omnigent server faked."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

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
        self.top_level: list[bool] = []  # per create, and per lookup after a failed one
        self.workspaces: list[str | None] = []
        self.taken: set[str] = set()  # titles an earlier child holds: create answers 409
        self.subscriptions: list[tuple[str, str]] = []
        self.resolved: list[tuple[str, str, str, dict | None]] = []
        self.host_id = "h"  # this host

    def create(
        self,
        agent: str,
        title: str,
        model: str | None = None,
        top_level: bool = False,
        workspace: str | None = None,
        permission_mode: str | None = None,
        host_id: str | None = None,
    ) -> str:
        if title in self.taken:
            error = HTTPError("http://x/v1/sessions", 409, "Conflict", Message(), None)
            raise omnigent_agent.Fail("POST /v1/sessions: HTTP 409 Conflict") from error
        sid = f"s{len(self.sessions)}"
        self.top_level.append(top_level)
        self.workspaces.append(workspace)
        self.sessions[sid] = [{"type": "resource_event"}]
        self.titles[sid] = title
        if "create" in self.fail:  # the server made it; the answer timed out
            raise omnigent_agent.Fail("POST /v1/sessions: TimeoutError: timed out")
        return sid

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
        and "foreground" in text
        and str(tmp_path / "r.md") in text
        and "roles/worker.md" in text
    )


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
    monkeypatch.setattr(omnigent_agent.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(omnigent_agent.os, "getloadavg", lambda: (300.0, 0.0, 0.0))
    assert omnigent_agent.main(["capacity"]) == 1
    assert capsys.readouterr().out == "load 37.5 per core (max 4), 1024 MB available (min 1536)\n"
    monkeypatch.setattr(omnigent_agent, "CAPACITY_WAIT_SECONDS", 0)
    og = FakeOmnigent()
    with pytest.raises(omnigent_agent.Fail, match="host over capacity for 0s: load 37.5"):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.sessions == {}

    loads = iter([300.0, 8.0])
    monkeypatch.setattr(omnigent_agent.os, "getloadavg", lambda: (next(loads), 0.0, 0.0))
    meminfo.write_text("MemAvailable: 4194304 kB\n")
    monkeypatch.setattr(omnigent_agent, "CAPACITY_WAIT_SECONDS", 60)
    omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert "host over capacity, waiting: load 37.5" in capsys.readouterr().err
    assert og.sessions  # started once the load fell


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        calls.append((method, path, body))
        return {
            "/v1/agents": [{"name": omnigent_agent.AGENTS["claude"], "id": "a1"}],
            "/v1/projects": {"data": [{"name": "other", "id": "p0"}, {"name": "shop", "id": "p1"}]},
            "/v1/sessions": {"id": "s1"},
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

    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "coord")
    omnigent_agent.Omnigent().create("claude", "t")
    assert calls[-1][2] and calls[-1][2]["parent_session_id"] == "coord"

    monkeypatch.setenv("OMNIGENT_PROJECT", "no-such-group")  # projects are only sidebar groups
    assert omnigent_agent.Omnigent().create("claude", "t") == "s1"
    assert calls[-1][2] and "project_id" not in calls[-1][2]

    # as the repo voice_note files under "Voice note"
    monkeypatch.setenv("OMNIGENT_PROJECT", "S_hop")
    omnigent_agent.Omnigent().create("claude", "t")
    assert calls[-1][2] and calls[-1][2]["project_id"] == "p1"


def test_create_sets_a_claude_session_s_permission_mode_from_the_flag_or_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bodies: list[dict] = []

    def call(self, method: str, path: str, body: dict | None = None) -> object:
        bodies.append(body or {})
        agents = [{"name": n, "id": a} for a, n in omnigent_agent.AGENTS.items()]
        return {"/v1/agents": agents, "/v1/projects": {"data": []}, "/v1/sessions": {"id": "s1"}}[
            path
        ]

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
        return {"/v1/agents": [{"name": "codex-native-ui", "id": "a1"}], "/v1/projects": []}.get(
            path, {"id": "s1"}
        )

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
    og.send(sid, "use main")  # the first send died before it removed the question
    report.write_text("done\nSATISFIED: yes\n")  # and the child answered with its report
    (tmp_path / "a.md").write_text("use main")
    assert omnigent_agent.main(["send", sid, "a.md", "r.md", "--verdict"]) == 0
    assert og.posts == 1


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
        lambda agent, title, model=None, top_level=False, workspace=None, permission_mode=None, host_id=None: (
            titles.append(title) or create(agent, title)
        )
    )  # type: ignore[method-assign]
    og.fail.add("archive")
    omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert titles == ["t", "t-r2"]


def test_the_server_comes_from_the_one_login_when_config_names_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, tokens = tmp_path / "config.yaml", tmp_path / "auth_tokens.json"
    config.write_text("host:\n  host_id: host_1\nlocal_server_port: 6767\n")
    monkeypatch.setattr(omnigent_agent, "CONFIG", config)
    monkeypatch.setattr(omnigent_agent, "AUTH_TOKENS", tokens)
    tokens.write_text('{"https://omnigent.example/": {}}')
    assert omnigent_agent.Omnigent().base == "https://omnigent.example"
    tokens.write_text('{"https://a.example": {}, "https://b.example": {}}')  # a guess: refuse
    with pytest.raises(omnigent_agent.Fail, match="no server"):
        omnigent_agent.Omnigent()
    config.write_text("server: https://named.example\nhost:\n  host_id: host_1\n")
    assert omnigent_agent.Omnigent().base == "https://named.example"


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
{role}Run every long command in the foreground (timeout up to 600000): a background command's completion never wakes you, so a turn that ends "waiting" never reports.
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
    assert (tmp_path / "r.md.brief").read_text() == DEFAULT_PREAMBLE.format(
        report=tmp_path / "r.md", role="Your role file is roles/worker.md; read it first.\n"
    ) + "do X"
    assert og.top_level == [False]


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
    assert text == omnigent_agent.LEAD_PREAMBLE.format(report=tmp_path / "r.md", role="") + "do X"
    assert "owner's own words" in text and "ask them here" in text
    assert "USER NEEDED" not in text and "needs-owner" not in text
    assert "foreground" in text and f"final report to {tmp_path / 'r.md'}" in text
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
    og.create = lambda a, t, m=None, top=False, w=None, p=None, h=None: (
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


def ending(text: str, ago: float) -> dict:
    return {**said("assistant", text, f"m{text}{ago}"), "created_at": time.time() - ago}


def following(tmp_path: Path) -> Path:
    registry = tmp_path / "registry"
    registry.write_text(f"a={tmp_path / 'a.md'}\t{tmp_path / 'a.md.brief'}\tfollow\n")
    return registry


def posted(og: Fleet) -> list[str]:
    return [t for s, t in og.inbox if s == "cos"]


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


def test_a_followed_leads_prompt_and_failure_post_at_once_and_archived_drops_its_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("STILL WORKING", 5))
    og.snap = {
        "status": "running",
        "pending_elicitations": [{"elicitation_id": "e1", "message": "ok?"}],
    }
    steps = [
        {"status": "running"},
        {"status": "failed", "last_task_error": {"message": "boom"}},
        {"status": "running"},
        {"status": "idle", "archived": True},
    ]

    def next_state(poll: int) -> None:
        og.snap = steps[poll - 1]

    supervised(og, registry, monkeypatch, 5, next_state, notify="cos")
    lines = posted(og)
    assert len(lines) == 3
    assert "blocked on a prompt" in lines[0] and ": failed: boom" in lines[1]
    assert ": archived" in lines[2]
    assert registry.read_text() == ""  # archived dropped it; the other events kept it


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
    assert first["rate"]["next_post_at"] == 0
    a_labels = [labels for sid, labels in og.labels if sid == "a"]
    assert [labels["status.line"] for labels in a_labels] == ["turn ended: DONE: shipped"] * 2
    assert int(a_labels[1]["status.at"]) - int(a_labels[0]["status.at"]) >= 60  # none at 30 s
    assert lead["label"] == {"line": a_labels[0]["status.line"], "at": a_labels[0]["status.at"]}
    events = [json.loads(e) for e in registry.with_suffix(".events.jsonl").read_text().splitlines()]
    assert [(e["id"], e["session"], e["kind"], e["settled"]) for e in events] == [
        (first["settled"]["a"][0], "a", "ended", "printed")
    ]


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
    at = {1: 301.0, 2: 1201.0}
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda poll: offset.__setitem__(0, at[poll]),
        notify="cos",
        console=True,
    )
    assert [p.split("\n")[0] for p in posted(og)] == [
        "Supervisor: a t-a: turn ended, quiet 301s",
        "Supervisor: a t-a: no progress 20m (unknown)",
    ]
    state = state_of(registry)
    progress = state["leads"]["a"]["progress_at"]
    state["leads"]["a"].update(nudges=1, revives=1)  # what the routing will count
    registry.with_suffix(".state.json").write_text(json.dumps(state))
    og.inbox.clear()
    at = {1: 1210.0, 2: 1801.0}  # the end found again; then 30 min since the progress
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda poll: offset.__setitem__(0, at[poll]),
        notify="cos",
        console=True,
    )
    assert [p.split("\n")[0] for p in posted(og)] == [
        "Supervisor: a t-a: no progress 30m after a nudge (unknown)"
    ]
    lead = state_of(registry)["leads"]["a"]
    assert (lead["nudges"], lead["revives"], lead["progress_at"]) == (1, 1, progress)


def test_a_lead_stuck_running_raises_one_deadline_for_its_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("STILL WORKING: on it", 50))
    og.snap = {"status": "running"}
    at = {1: 1199.0, 2: 1201.0, 3: 1300.0, 4: 2500.0}

    def later(poll: int) -> None:
        offset[0] = at[poll]
        og.refuse = 2 if poll == 1 else og.refuse  # its post fails at two polls: it waits, once

    supervised(og, registry, monkeypatch, 5, later, notify="cos", console=True)
    assert posted(og) == [
        "Supervisor: a t-a: no progress 20m (unknown)\nlast message: STILL WORKING: on it"
    ]
    assert state_of(registry)["settled"]["a"][0].startswith("deadline:a:")


def test_a_second_quiet_spell_with_the_same_ending_raises_a_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 800), ending("STILL WORKING: waiting on the verifier", 600))
    steps = {1: (301.0, "idle"), 2: (400.0, "running"), 3: (500.0, "idle"), 4: (1201.0, "idle")}

    def later(poll: int) -> None:
        offset[0], status = steps[poll]
        og.snap = {"status": status}

    supervised(og, registry, monkeypatch, 5, later, notify="cos", console=True)
    assert [p.split("\n")[0] for p in posted(og)] == [
        "Supervisor: a t-a: turn ended, quiet 301s",  # the first spell, told once
        "Supervisor: a t-a: no progress 20m (verifier)",  # the second, the same message
    ]


def test_a_parked_lead_has_no_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = following(tmp_path)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("PARKED: the host is full", 5))
    at = {1: 1300.0, 2: 5000.0}
    supervised(
        og,
        registry,
        monkeypatch,
        3,
        lambda poll: offset.__setitem__(0, at[poll]),
        notify="cos",
        console=True,
    )
    assert [p.split("\n")[0] for p in posted(og)] == ["Supervisor: a t-a: turn ended"]
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
        before.append(len(posted(og)))
        offset[0] = at[poll]

    supervised(og, registry, monkeypatch, 4, later, notify="cos", console=True)
    assert before == [0, 0, 0]
    assert [p.split("\n")[0] for p in posted(og)] == ["Supervisor: a t-a: no progress 20m (worker)"]


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
    assert renames == [registry.with_suffix(".state.json")] * 2
    assert not list(tmp_path.glob("*.tmp"))


def test_a_failed_label_write_is_logged_once_and_the_poll_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = following(tmp_path)
    og = Lead(told("brief", 60), ending("DONE: shipped", 5))
    og.unlabelled = 2
    supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert [p.split("\n")[0] for p in posted(og)] == ["Supervisor: a t-a: turn ended"]
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
    og: FakeOmnigent, sid: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str = "go"
) -> int:
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "QUEUED_SECONDS", 0)
    (tmp_path / "m.md").write_text(text)
    return omnigent_agent.main(["relay", sid, str(tmp_path / "m.md")])


def test_relay_to_an_idle_session_is_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    assert relay(og, sid, tmp_path, monkeypatch) == 0
    assert capsys.readouterr().out.strip() == f"session {sid}: delivered"
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "go"


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


def test_relay_answers_a_question_with_the_message_instead_of_posting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(hold=10**6)  # an interrupt would leave it held (omnigent#14)
    sid = og.create("claude", "lead")
    og.prompts = [QUESTION]
    assert relay(og, sid, tmp_path, monkeypatch, "use main\n") == 0
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
    assert relay(og, sid, tmp_path, monkeypatch) == 0
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
    assert omnigent_agent.text_of(og.sessions[sid][-1]) == "go"


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
    assert "queued behind a prompt (`approve` answers an approval): " in capsys.readouterr().err


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


def test_relay_to_an_archived_session_is_not_deliverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "lead")
    og.archive(sid)
    assert relay(og, sid, tmp_path, monkeypatch) == omnigent_agent.GONE
    assert f"session {sid} is archived" in capsys.readouterr().err
    assert og.posts == 0


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
    path = f"{FS}/Users/k/my%20dir/r%23.md?base=host"
    seen = serve_files(monkeypatch, {path: {"content": "# done\n"}})
    assert omnigent_agent.main(["report", "s9", "/Users/k/my dir/r#.md"]) == 0
    assert seen[-1:] == [path]  # no leading %2F, '/' kept between segments
    assert capsys.readouterr().out == "# done\n\n"


def test_report_reads_a_relative_path_in_the_workspace_without_base(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = serve_files(monkeypatch, {f"{FS}/tmp/r.md": {"content": "hi"}})
    assert omnigent_agent.main(["report", "s9", "tmp/r.md"]) == 0
    assert seen == [f"{FS}/tmp/r.md"]


def test_report_reads_an_absolute_path_inside_the_workspace_relative_to_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # a host on an older Omnigent answers 404 to an absolute file read it serves relative
    files = {"/v1/sessions/s9": {"workspace": "/Users/k/ws"}, f"{FS}/tmp/r.md": {"content": "ok"}}
    seen = serve_files(monkeypatch, files)
    assert omnigent_agent.main(["report", "s9", "/Users/k/ws/tmp/r.md"]) == 0
    assert seen == ["/v1/sessions/s9", f"{FS}/tmp/r.md"]
    assert (
        omnigent_agent.main(["report", "s9", "/Users/k/wsx/r.md"]) == 4
    )  # a sibling stays absolute
    assert seen[-1] == f"{FS}/Users/k/wsx/r.md?base=host"


def test_report_lists_a_directory_one_entry_per_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listing = {"data": [{"name": "a.md", "type": "file"}, {"name": "sub", "type": "directory"}]}
    serve_files(monkeypatch, {f"{FS}/tmp?base=host": listing})
    assert omnigent_agent.main(["report", "s9", "/tmp"]) == 0
    assert capsys.readouterr().out == "a.md\nsub/\n"


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
    path = f"{FS}/Users/k/r.md?base=host"
    seen = serve_files(monkeypatch, {path: {"content": "x"}})
    assert omnigent_agent.main(["report", "s9", "--registry", str(registry)]) == 0
    assert seen[-1:] == [path]
    assert omnigent_agent.main(["report", "s8", "--registry", str(registry)]) == 2
    assert omnigent_agent.main(["report", "s9"]) == 2
    assert "OMNIGENT_SUPERVISE_REGISTRY" in capsys.readouterr().err
