"""scripts/omnigent_agent.py with the Omnigent server faked."""

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "omnigent_agent",
    Path(__file__).resolve().parents[1]
    / "skills"
    / "engineering-loop"
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
        self.deleted: list[str] = []
        self.prompts: list[dict] = []
        self.fail: set[str] = set()  # method names that raise Fail

    def create(self, agent: str, title: str, model: str | None = None) -> str:
        sid = f"s{len(self.sessions)}"
        self.sessions[sid] = [{"type": "resource_event"}]
        return sid

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
        return {"status": status, "pending_elicitations": self.prompts, "pending_inputs": pending}

    def delete(self, sid: str) -> None:
        if "delete" in self.fail:
            raise omnigent_agent.Fail(f"DELETE {sid}: HTTP 503")
        self.deleted.append(sid)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(omnigent_agent, "POLL_SECONDS", 0)


def test_start_sends_preamble_and_confirms(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid, _ = omnigent_agent.start(
        og, "claude", "t", "do X", tmp_path / "r.md", "roles/worker.md", 0
    )
    message = omnigent_agent.text_of(og.sessions[sid][1])
    brief_file = tmp_path / "r.md.brief"
    assert str(brief_file) in message and "do X" not in message
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
    assert og.deleted == ["s0"]


def test_start_fails_after_two_deaf_sessions(tmp_path: Path) -> None:
    with pytest.raises(
        omnigent_agent.Fail, match="s0: brief not in history.*s1: brief not in history"
    ):
        omnigent_agent.start(
            FakeOmnigent(deaf={0, 1}), "claude", "t", "do X", tmp_path / "r.md", None, 0
        )


def test_wait_returns_report(tmp_path: Path) -> None:
    (tmp_path / "r.md").write_text("ok")
    assert omnigent_agent.wait(FakeOmnigent(), "s0", tmp_path / "r.md") == str(tmp_path / "r.md")


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
            report.write_text(report.read_text() + "SATISFIED: no\n")
        return {"status": "running", "pending_elicitations": []}

    og.info = info  # type: ignore[method-assign]
    assert omnigent_agent.wait(og, sid, report, verdict=True) == str(report)
    assert polls == 3


def test_verifier_wait_fails_when_turn_ends_without_verdict(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="done")
    report = tmp_path / "r.md"
    sid, _ = omnigent_agent.start(og, "codex", "t", "do X", report, None, 0)
    report.write_text("VERDICT: 0 blocker, 0 major, 0 minor\n")
    with pytest.raises(omnigent_agent.Fail, match=r"ended \(idle\) without a verdict"):
        omnigent_agent.wait(og, sid, report, verdict=True)


def test_worker_wait_needs_no_verdict(tmp_path: Path) -> None:
    og = FakeOmnigent(reply="checking", status="running")
    (tmp_path / "r.md").write_text("partial")
    assert omnigent_agent.wait(og, "s0", tmp_path / "r.md", timeout=0) == str(tmp_path / "r.md")


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


def test_wait_fails_when_turn_ends_idle_with_no_output(tmp_path: Path) -> None:
    og = FakeOmnigent(status="idle")  # the brief is the last item and nothing follows
    sid, _ = omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    statuses = iter(["running", "idle"])
    og.info = lambda s: {"status": next(statuses), "pending_elicitations": []}  # type: ignore[method-assign]
    with pytest.raises(omnigent_agent.Fail, match=r"ended \(idle\)"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md")


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


def test_failed_delete_is_reported_and_retry_proceeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og = FakeOmnigent(deaf={0})
    og.fail.add("delete")
    assert omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0) == (
        "s1",
        ["s0"],
    )
    assert "abandoned session s0 survives" in capsys.readouterr().err


def test_send_failure_after_create_deletes_session(tmp_path: Path) -> None:
    og = FakeOmnigent()
    og.fail.add("send")
    with pytest.raises(omnigent_agent.Fail, match="s0: POST events: HTTP 503"):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.deleted == ["s0"]


def test_main_exits_nonzero_when_abandoned_session_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent(deaf={0})
    og.fail.add("delete")
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
            self.base, self._token, self.deleted = base, "synthetic", []

        def create(self, agent: str, title: str, model: str | None = None) -> str:
            return "s0"

        def delete(self, sid: str) -> None:
            self.deleted.append(sid)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stall)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        og = Local(f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(omnigent_agent, "HTTP_SECONDS", 0.05)
        with pytest.raises(omnigent_agent.Fail, match="s0: POST .*TimeoutError"):
            omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
        assert og.deleted == ["s0"]
    finally:
        server.shutdown()


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
            self.base, self._token, self.deleted = base, "synthetic", []

        def create(self, agent: str, title: str, model: str | None = None) -> str:
            return "s0"

        def delete(self, sid: str) -> None:
            self.deleted.append(sid)

    server = ThreadingHTTPServer(("127.0.0.1", 0), StallBody)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        og = Local(f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(omnigent_agent, "HTTP_SECONDS", 0.05)
        with pytest.raises(omnigent_agent.Fail, match="s0: POST .*HTTP 503"):
            omnigent_agent.start(og, "codex", "t", "do X", tmp_path / "r.md", None, 0)
        assert og.deleted == ["s0"]
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


def test_send_refuses_reaped_runner(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    og.info = lambda s: {"status": "idle", "runner_online": False}  # type: ignore[method-assign]
    with pytest.raises(omnigent_agent.Gone):
        omnigent_agent.send(og, sid, "use main", tmp_path / "r.md", 0)
    assert og.sessions[sid] == [{"type": "resource_event"}]


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
    og.create = lambda agent, title, model=None: titles.append(title) or create(agent, title)  # type: ignore[method-assign]
    og.fail.add("delete")
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
