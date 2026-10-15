#!/usr/bin/env python3
"""Start an engineering-loop agent through Omnigent and wait for its report.

    python3 scripts/omnigent_agent.py run <claude|codex> <title> <brief-file> <report-path> [--role FILE]
    python3 scripts/omnigent_agent.py start <claude|codex> <title> <brief-file> <report-path> [--role FILE] [--top-level]
    python3 scripts/omnigent_agent.py send <session> <brief-file> <report-path>
    python3 scripts/omnigent_agent.py watch [<session>...] [--children <parent>]
    python3 scripts/omnigent_agent.py reap [<session>...] [--children <parent>]
    python3 scripts/omnigent_agent.py supervise <session>=<report>... [--silent-seconds N]
    python3 scripts/omnigent_agent.py supervise --registry <file> [--notify <session>] [<session>=<report>...]

``run`` is ``start`` then ``wait`` in one process: exit 0 prints the report path (a verifier's
only once it has its ``SATISFIED:`` line; ``send`` and ``wait`` take ``--verdict`` for that); exit 3 prints the
path of a question the child wrote (``<report>.question``) instead of a report; exit 1 prints the
reason and the child's last message (for a failed session, its ``last_task_error`` and runner log).
A report already at the path is a pass before: only one written after the launch counts. It counts
once final (``settled``): the child's turn has ended and the file is unchanged since, since a child
can rewrite its report until then. The first turn that ends with neither gets one nudge to write
it; a second fails. A lead launches it as one background command, so its
exit is the wake. ``send`` answers that question in the same session, also mid-turn, then waits the
same way. A session whose runner Omnigent reaped after its idle timeout (a send there answers
``queued`` and never arrives) it first revives in place with a ``retry_session`` event and sends
once the runner is online; exit 4 only when that revive fails, naming its reply.
``watch`` exits 0 as soon as one of the given sessions (or a parent's sub-agents) ends a turn, blocks on
a prompt or fails, printing each one's id, title, that change and its last message; it is how a
lead or chief of staff learns of a session no ``run``, ``send`` or ``wait`` is waiting on.
``supervise`` watches sessions that each owe a report for liveness, not only outcomes: it revives a
reaped runner in place, then sends it a line naming its brief files and the report, since a revive
can drop its context, and sends one resume line to a session silent past ``--silent-seconds``
(default 1800), printing a line for each and carrying on, and exits 0 with one line as soon as one
wrote its report or a question, blocks on a prompt, fails, or is given up on (silent after its resume
line or with an input undelivered, or a failed revive).
A report counts once newer than the session's last instruction, so one already written counts at once,
and only once ``settled``, as ``wait`` counts it.
``supervise --registry`` runs until stopped: each poll it re-reads the file's ``session=report``
lines, each optionally followed by the session's brief files after tabs and a ``verdict`` field
for a verifier, whose report then counts only with its ``SATISFIED:`` line, and checks each session
the same way, printing every line with the local time and, with ``--notify``, posting it into that
session as ``Supervisor: <line>`` (reviving it first when reaped). A terminal event drops the
session's line once posted; an error or an event-less ``--timeout`` is logged and the loop goes on.
``run``, ``start`` and ``send`` arm the registry given by ``--registry``, else
``$OMNIGENT_SUPERVISE_REGISTRY``, once their message is in the history (``start`` with its brief
file, ``send`` appending its message file, each marking a verifier's line as ``wait`` would
count its report); ``run``, ``send`` and ``wait`` disarm it when they
return the report or a question.
``run`` and ``wait`` finish the session whose report or verdict they return, not one that asked a
question; ``reap`` finishes each one that is done (not running, no prompt or input waiting) and keeps
the rest; it cannot tell a child still owing its report from a finished one, so it runs once every
report is in. Finishing archives a top-level session and only ends a sub-agent's terminals, since
archiving a sub-agent stops its parent's runner (kzarzycki/omnigent#5); either way the transcript
is kept, and nothing here deletes a session.

Uses the local Omnigent server's HTTP API (the ``omnigent`` CLI has no session create/send):
``POST /v1/sessions`` (created empty: a child created with queued ``initial_items`` can stay idle
for good), ``POST /v1/sessions/{id}/events`` with a ``message`` event, and
``GET /v1/sessions/{id}/items`` as the history. A send answers ``queued``/``launching`` even when
the child never gets it, so the start counts only once the one line naming the brief file is a
user message in the history. A create that fails may have made the session anyway, so ``start``
looks its title up among the parent's children (``GET /v1/sessions/{parent}/child_sessions``), or
with ``--top-level`` among the project's top-level sessions (``GET /v1/sessions?project=<name>``),
and briefs that one. ``start --top-level`` starts a lead: no parent session, so the owner sees it
in the sidebar and its own children report to it, under the lead preamble; ``run`` refuses it,
since a lead asks the owner in its own session and writes no question for ``run`` to return. A ``GET`` is retried on a timeout or reset; a ``POST`` never is. ``start`` refuses a
brief with an empty backtick span (a name an unquoted heredoc ran). Server and host come from ``~/.omnigent/config.yaml``; the bearer token from Omnigent's
own ``cli_auth`` (run in the omnigent tool venv), which refreshes and persists it. Stdlib only.
"""

from __future__ import annotations

import argparse
import fcntl
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

AGENTS = {"claude": "claude-native-ui", "codex": "codex-native-ui"}
CONFIG = Path.home() / ".omnigent" / "config.yaml"
AUTH_TOKENS = Path.home() / ".omnigent" / "auth_tokens.json"
RUNNING = {"running", "launching", "queued", "starting"}
POLL_SECONDS = 5.0
TOKEN_SECONDS = 30.0
HTTP_SECONDS = 30.0
# Idle with the brief last for this long: a turn that ended with no output. Shorter is not proof:
# claude-native was seen idle for 15 s mid-turn, with the brief last, before its reply came.
IDLE_GRACE_SECONDS = 30.0
# A report and history this quiet while the session still reads ``running``: a lost turn end
# (kzarzycki/omnigent#4), so the report is final. Long, since a lead waits on its children quietly.
SETTLE_SECONDS = 600.0
TITLES = 20  # <title>, then <title>-r2 up to this many: a create refused as taken tries the next
# A loaded server times out reads the child never noticed; a GET is retried after each of these.
RETRY_SECONDS = (2.0, 5.0, 15.0)
TRANSIENT = (TimeoutError, socket.timeout, ConnectionResetError)  # socket.timeout: Python 3.9
EMPTY_SPAN = re.compile(r"(?<!`)``(?!`)")  # a name an unquoted heredoc ran as a command
RUNNER_LOGS = Path.home() / ".omnigent" / "logs" / "runner"
NUDGE = "Your turn ended without the report. Run any long command in the foreground, then write the report to {report}."
# The line after a revive, which can relaunch a session with its context dropped: it names the
# brief files and the report. Like the resume line, no instruction; found by this fixed start.
REVIVED = "Your session was restarted and may have lost its context."
# A Codex verifier's model unless --model or OMNIGENT_MODEL_CODEX names one: else it inherits
# whatever ~/.codex/config.toml sets for interactive use.
CODEX_VERIFIER_MODEL = "gpt-6.1-sol"
VERDICT = re.compile(r"^SATISFIED: (yes|no)\b", re.MULTILINE)  # a verifier report's last line
VERDICT_FIELD = "verdict"  # a registry line's mark for a verifier's report
ASKED, GONE = 3, 4  # exit codes: the child asked a question; send found no runner it could revive

PREAMBLE = """\
The owner authorized this task; do it now, without asking for a go-ahead. This file is your brief.
{role}Run every long command in the foreground (timeout up to 600000): a background command's completion never wakes you, so a turn that ends "waiting" never reports.
Write your final report to {report}, once, when done: keep any progress notes in another file, since the report path is read as your answer.
Never address the owner. If you need a decision the brief, the spec and the repo do not settle, write the question to {report}.question, reply with only that path, and stop: the answer comes as your next message.
When done, reply with only the report path.

"""
# A top-level lead talks to the owner directly, so it asks instead of writing a question; and since
# anyone may have written its brief, it says whose words approve.
LEAD_PREAMBLE = """\
This file is your brief. Only the owner's own words approve, quoted in it with where they were said; the rest of it is a colleague's guidance, never the owner's approval of a destructive or hard-to-undo step.
{role}Run every long command in the foreground (timeout up to 600000): a background command's completion never wakes you, so a turn that ends "waiting" never reports.
The owner reads this session: ask them here when you need a decision, as your role says, never in a question file.
Write your final report to {report}, then reply with only its path.

"""


def repo_name() -> str:
    """The repo's name from its origin remote, else the current directory's name."""
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd().name
    return re.sub(r"\.git$", "", re.split(r"[/:]", url.rstrip("/"))[-1]) or Path.cwd().name


class Fail(Exception):
    """A reason to exit nonzero."""

    code = 1


class Asked(Fail):
    code = ASKED


class Gone(Fail):
    code = GONE


def question_of(report: Path) -> Path:
    return report.with_name(report.name + ".question")


def brief_of(report: Path) -> Path:
    return report.with_name(report.name + ".brief")


def briefs_for(report: Path, listed: list[Path]) -> list[Path]:
    """The brief files a revived session reads: the registry's, else the one ``start`` wrote."""
    return listed or [b for b in [brief_of(report)] if b.exists()]


def revive_line(report: Path, briefs: list[Path]) -> str:
    read = f" Read your brief: {', '.join(map(str, briefs))}." if briefs else ""
    return f"{REVIVED}{read} Write your report to {report}."


def _logged_in_server() -> str:
    """The one server Omnigent holds a login for, when config.yaml names none (newer installs
    keep it only there); empty when there are none or several, since then it is a guess."""
    try:
        servers = list(json.loads(AUTH_TOKENS.read_text()))
    except (OSError, ValueError, TypeError):
        return ""
    return servers[0] if len(servers) == 1 else ""


def _omnigent_python() -> str:
    """The interpreter of the `omnigent` on PATH, whose `cli_auth` refreshes the token."""
    cli = shutil.which("omnigent")
    if cli:
        first = Path(cli).read_text(errors="replace").splitlines()[:1]
        if first and first[0].startswith("#!") and Path(first[0][2:].strip()).exists():
            return first[0][2:].strip()
    return str(Path.home() / ".local/share/uv/tools/omnigent/bin/python")


class Omnigent:
    def __init__(self) -> None:
        text = CONFIG.read_text()
        server, host = (
            re.search(r"^server:\s*(\S+)", text, re.MULTILINE),
            re.search(r"^\s+host_id:\s*(\S+)", text, re.MULTILINE),
        )
        base = server.group(1) if server else _logged_in_server()
        if not base or not host:
            raise Fail(
                f"{CONFIG} lacks host.host_id, or no server: neither `server:` there nor one login in {AUTH_TOKENS}"
            )
        self.base, self.host_id = base.rstrip("/"), host.group(1)
        self._token = ""

    def token(self) -> str:
        code = f"from omnigent.cli_auth import refresh_stored_token as r, load_token as l; print(r({self.base!r}) or l({self.base!r}) or '')"
        try:  # refresh takes a blocking lock on Omnigent's auth file
            out = subprocess.run(
                [_omnigent_python(), "-c", code],
                capture_output=True,
                text=True,
                check=False,
                timeout=TOKEN_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise Fail(
                f"Omnigent token lookup for {self.base} timed out after {TOKEN_SECONDS:.0f}s"
                " (another process holding ~/.omnigent/auth_tokens.lock?)"
            ) from e
        if not out.stdout.strip():
            raise Fail(
                f"no Omnigent token for {self.base}; run `omnigent login` ({out.stderr.strip()[-300:]})"
            )
        return out.stdout.strip()

    def call(self, method: str, path: str, body: object = None) -> dict:
        """One request; a ``GET`` is retried on a timeout or reset. A ``POST`` never is: it may
        have taken effect."""
        retries = list(RETRY_SECONDS) if method == "GET" else []
        refreshed = False
        while True:
            self._token = self._token or self.token()
            req = Request(
                self.base + path,
                method=method,
                data=None if body is None else json.dumps(body).encode(),
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urlopen(req, timeout=HTTP_SECONDS) as resp:
                    return json.load(resp)
            except HTTPError as e:
                if e.code == 401 and not refreshed:
                    self._token, refreshed = "", True  # expired mid-run: refresh once
                    continue
                raise Fail(
                    f"{method} {path}: HTTP {e.code} {e.reason}"
                ) from e  # never read the body: it can stall past the timeout
            except (
                OSError,
                http.client.HTTPException,
            ) as e:  # URLError, timeout, reset, bad status line
                cause = e.reason if isinstance(e, URLError) else e
                if retries and isinstance(cause, TRANSIENT):
                    print(f"{method} {path}: {type(cause).__name__}; retrying", file=sys.stderr)
                    time.sleep(retries.pop(0))
                    continue
                if isinstance(e, URLError):
                    raise Fail(f"{method} {path}: {e.reason}") from e
                raise Fail(f"{method} {path}: {type(e).__name__}: {e}") from e

    def agent_id(self, name: str) -> str:
        agents = self.call("GET", "/v1/agents")
        for a in agents.get("data", agents) if isinstance(agents, dict) else agents:
            if a.get("name") == name:
                return str(a["id"])
        raise Fail(f"agent {name} not registered")

    def project_id(self, name: str) -> str | None:
        """The id of the project (a sidebar group) called ``name``, or None when there is none."""
        projects = self.call("GET", "/v1/projects")
        for p in projects.get("data", projects) if isinstance(projects, dict) else projects:
            if p.get("name") == name:
                return str(p["id"])
        return None

    def create(
        self, agent: str, title: str, model: str | None = None, top_level: bool = False
    ) -> str:
        body = {
            "agent_id": self.agent_id(AGENTS[agent]),
            "title": title,
            "host_id": self.host_id,
            "workspace": os.getcwd(),
        }
        # Filed under the repo's project, when one exists, so spawned sessions don't crowd the top level.
        if project := self.project_id(project_name()):
            body["project_id"] = project
        # A sub-agent of the runner's primary session (the lead, also when a child runs
        # this): hidden from the owner's sidebar and unread badge, and gone with it. Top level
        # with ``top_level`` or when not run from an Omnigent session.
        if (parent := parent_id()) and not top_level:
            body["parent_session_id"] = parent
        if model := model or os.environ.get(f"OMNIGENT_MODEL_{agent.upper()}"):
            body["model_override"] = model
        return str(self.call("POST", "/v1/sessions", body)["id"])

    def retry(self, sid: str) -> dict:
        return self.call(
            "POST", f"/v1/sessions/{sid}/events", {"type": "retry_session", "data": {}}
        )

    def send(self, sid: str, text: str) -> None:
        self.call(
            "POST",
            f"/v1/sessions/{sid}/events",
            {
                "type": "message",
                "data": {
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            },
        )

    def items(self, sid: str) -> list[dict]:
        page = self.call("GET", f"/v1/sessions/{sid}/items?limit=100&order=desc")
        return list(reversed(page.get("data", [])))

    def info(self, sid: str) -> dict:
        """Session snapshot: ``status`` and ``pending_elicitations`` (what ``sys_session_get_info`` reads)."""
        return self.call("GET", f"/v1/sessions/{sid}")

    def archive(self, sid: str) -> str:
        """Finish ``sid``: end its agent process, keep its transcript, and say how (``archived``
        or ``ended``). Never DELETE, which erases the transcript.

        A top-level session is archived, which stops its own runner. A sub-agent shares its
        parent's runner, and archiving it stops that runner too, taking the parent down: so only
        its terminals (its agent process) are ended and it stays unarchived. A codex child may
        still finish the turn it is in, then idles.
        """
        if self.info(sid).get("parent_session_id"):
            # ponytail: unbinding the runner before the archive does not help, since the child's
            # turn-end idle makes the server bind it back to the parent's runner before the
            # archive's delayed stop (kzarzycki/omnigent#5). Upgrade: archive sub-agents again
            # once the server no longer stops a runner a sub-agent shares.
            terminals = self.call("GET", f"/v1/sessions/{sid}/resources/terminals")
            for t in terminals.get("data", []):
                self.call("DELETE", f"/v1/sessions/{sid}/resources/terminals/{t['id']}")
            return "ended"
        self.call("PATCH", f"/v1/sessions/{sid}", {"archived": True})
        return "archived"

    def find(self, title: str, after: float, top_level: bool = False) -> str | None:
        """The parent's child called ``title`` created at or after ``after`` (epoch seconds): the
        session a create that failed in transit made anyway. None when there is no parent. With
        ``top_level``, the project's top-level session of that title instead (unfiled ones when the
        project does not exist, as ``create`` files them)."""
        if top_level:
            name = project_name()
            # the list filters by project name; "" is the unfiled sessions
            project = quote(name if self.project_id(name) else "")
            path = f"/v1/sessions?kind=default&project={project}&limit=100"
        elif parent := parent_id():
            path = f"/v1/sessions/{parent}/child_sessions?limit=100"
        else:
            return None
        page = self.call("GET", path)
        return next(
            (
                str(c["id"])
                for c in page.get("data", [])
                if c.get("title") == title and float(c.get("created_at") or 0) >= after
            ),
            None,
        )

    def children(self, sid: str) -> list[str]:
        page = self.call("GET", f"/v1/sessions/{sid}/child_sessions?limit=100")
        return [str(c["id"]) for c in page.get("data", [])]

    def active(self, sid: str) -> float:
        """When any live child of ``sid`` was last updated (archived ones are not listed), else 0.
        Not ``busy``: a child whose turn end was lost stays busy for good."""
        page = self.call("GET", f"/v1/sessions/{sid}/child_sessions?limit=100")
        return max((float(c.get("updated_at") or 0) for c in page.get("data", [])), default=0.0)


def project_name() -> str:
    return os.environ.get("OMNIGENT_PROJECT") or repo_name()


def parent_id() -> str:
    """The runner's primary session (the lead, also when a child runs this), else empty."""
    return os.environ.get("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "")


def runner_log(info: dict) -> str:
    """Where the session's runner logs: one file per primary session, children included."""
    root = info.get("parent_session_id") or info.get("id") or "*"
    logs = sorted(RUNNER_LOGS.glob(f"runner-{root}-*.log"), key=lambda f: f.stat().st_mtime)
    return str(logs[-1]) if logs else str(RUNNER_LOGS / f"runner-{root}-*.log")


def text_of(item: dict) -> str:
    return "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))


def last_message(items: list[dict]) -> dict | None:
    return next((i for i in reversed(items) if i.get("type") == "message"), None)


def prompts_of(info: dict) -> list[str]:
    """What each pending approval prompt asks: the tool call it holds, else its message."""
    return [
        str(p.get("content_preview") or p.get("message") or e)
        for e in info.get("pending_elicitations") or []
        for p in [e.get("params") or {}]
    ]


def delivered(
    og: Omnigent,
    sid: str,
    brief: str,
    seconds: float,
    old: frozenset[str] = frozenset(),
) -> bool:
    """Whether ``brief`` shows up as a user message in the history, other than the ``old`` item ids.

    Ids, not a count: the history is a rolling page of the newest 100 items.
    """
    deadline = time.monotonic() + seconds
    while True:
        if any(
            i.get("type") == "message" and i.get("role") == "user" and brief.strip() in text_of(i)
            for i in og.items(sid)
            if str(i.get("id")) not in old
        ):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)


def revive(og: Omnigent, sid: str, seconds: float = 120.0) -> None:
    """Relaunch a reaped session's runner in place (the web UI's "Resume session"); it keeps the
    whole conversation. Gone when the revive fails or the runner is not online within ``seconds``."""
    try:
        reply = og.retry(sid)
    except Fail as e:
        raise Gone(f"session {sid} has no live runner and the revive failed: {e}") from e
    print(f"session {sid} had no live runner; revive: {json.dumps(reply)}", file=sys.stderr)
    if not reply.get("recovered") and reply.get("recovery") != "already_connected":
        raise Gone(f"session {sid} has no live runner and the revive failed: {json.dumps(reply)}")
    deadline = time.monotonic() + seconds
    while not og.info(sid).get("runner_online", True):
        if time.monotonic() >= deadline:
            raise Gone(
                f"session {sid}: revived ({json.dumps(reply)}) but no runner online after {seconds:.0f}s"
            )
        time.sleep(POLL_SECONDS)


def send(og: Omnigent, sid: str, brief: str, report: Path, confirm_seconds: float) -> None:
    """Send a follow-up (an answer) to a session whose runner is still up, and wait until it lands.

    Omnigent hands a message to the harness at once, also mid-turn: that is steering (the web
    composer's queue and its "Always steer" live only in the browser). The session lists it under
    ``pending_inputs`` until the harness folds it in at its next tool boundary, which a long
    foreground command holds off for minutes. So pending is delivery under way, and the message is
    lost only once it has been neither pending nor in the history for ``confirm_seconds``. A retry
    finds the first copy pending, or in the history since the question was written, and sends
    nothing: a second post delivers twice.
    """
    text, question = brief.strip(), question_of(report)
    # Read once, first: the sender of the first copy deletes the question once that copy lands.
    try:
        asked: float | None = question.stat().st_mtime
    except FileNotFoundError:
        asked = None
    # History before info: Omnigent persists a copy before it drops it from pending_inputs, so a
    # copy seen pending is not among the ``old`` ids and its landing shows up as a new item.
    items = og.items(sid)
    old = frozenset(str(i.get("id")) for i in items)
    info = og.info(sid)
    if not info.get("runner_online", True):
        revive(og, sid)

    # A copy is the same text exactly (both harnesses store it verbatim): a different message that
    # merely contains it is a new one.
    def copies(items: list[dict]) -> list[dict]:
        return [
            i
            for i in items
            if i.get("type") == "message" and i.get("role") == "user" and text_of(i).strip() == text
        ]

    def pending(info: dict) -> bool:
        return any(text_of(p).strip() == text for p in info.get("pending_inputs") or [])

    # ponytail: compares the server's item clock with the local question file's; a skewed server
    # clock can resend an answer that already landed. Upgrade: a client id, once Omnigent has one.
    if asked is not None and any(float(i.get("created_at") or 0) >= asked for i in copies(items)):
        print(f"session {sid}: this answer already landed", file=sys.stderr)
        question.unlink(missing_ok=True)
        return
    # or it landed between the two reads
    if pending(info) or any(str(i.get("id")) not in old for i in copies(og.items(sid))):
        print(
            f"session {sid}: this message was already sent; waiting for that copy", file=sys.stderr
        )
    else:
        og.send(sid, brief)
    deadline, said = time.monotonic() + confirm_seconds, False
    while True:
        info = og.info(sid)  # before the history: a copy leaves pending only once it has landed
        if any(str(i.get("id")) not in old for i in copies(og.items(sid))):
            break
        if pending(info):
            if not said:
                print(
                    f"session {sid} is {info.get('status')}: message queued in its harness until"
                    " the current step ends",
                    file=sys.stderr,
                )
                said = True
            deadline = time.monotonic() + confirm_seconds
        elif time.monotonic() >= deadline:
            raise Gone(
                f"session {sid}: message neither pending nor in history for {confirm_seconds:.0f}s;"
                " start a fresh run instead"
            )
        time.sleep(POLL_SECONDS)
    question.unlink(missing_ok=True)  # kept until the answer lands, for the fresh run


def taken(e: Fail) -> bool:
    """Whether a create failed with 409: Omnigent refuses a title a sibling already holds."""
    return isinstance(e.__cause__, HTTPError) and e.__cause__.code == 409


def start(
    og: Omnigent,
    agent: str,
    title: str,
    brief: str,
    report: Path,
    role: str | None,
    confirm_seconds: float,
    attempts: int = 2,
    model: str | None = None,
    top_level: bool = False,
) -> tuple[str, list[str]]:
    """Return the confirmed session id and any abandoned sessions whose finish failed."""
    if span := EMPTY_SPAN.search(brief):
        line = brief[: span.start()].count("\n") + 1
        raise Fail(
            f"brief line {line} has an empty `` span: a name lost in an unquoted heredoc; quote it (<<'EOF')"
        )
    # The brief goes in a file beside the report and the message only names it: a child can receive
    # an inline brief as pasted text, which it will not take instructions from.
    brief_file = brief_of(report)
    brief_file.parent.mkdir(parents=True, exist_ok=True)
    brief_file.write_text(
        (LEAD_PREAMBLE if top_level else PREAMBLE).format(
            report=report,
            role=f"Your role file is {role}; read it first.\n" if role else "",
        )
        + brief
    )
    text = f"Your brief is the file {brief_file}. Read it now and do what it says."
    reasons: list[str] = []
    survivors: list[str] = []

    def abandon(sid: str) -> None:
        try:
            og.archive(sid)
        except Fail as e:
            survivors.append(sid)
            print(f"abandoned session {sid} survives: {e}", file=sys.stderr)

    def failed(reason: str) -> Fail:
        left = f"; abandoned sessions survive: {', '.join(survivors)}" if survivors else ""
        return Fail(reason + left)

    # Omnigent refuses a sibling with a title an earlier child holds, archived or not, abandoned
    # here or left by an earlier run: each refusal and each abandon moves to the next <title>-r<n>.
    n = 0
    for _ in range(attempts):
        # ponytail: whole seconds of the server's clock against this host's; a skewed server
        # misses the match and fails as before. Upgrade: an idempotency key, once Omnigent has one.
        began, found = int(time.time()), None
        while True:
            name = title if n == 0 else f"{title}-r{n + 1}"
            n += 1
            try:
                sid, error = og.create(agent, name, model, top_level), None
            except Fail as e:
                if not taken(e):
                    error = e
                elif n < TITLES:
                    print(f"title {name} is taken", file=sys.stderr)
                    continue
                else:
                    raise failed(f"start failed: titles {title} to {name} are taken") from e
            break
        if error:  # a timed-out create can have made the session: brief that one
            found = og.find(name, began, top_level)
            if not found:
                raise failed(f"start failed: {error}") from error
            print(
                f"create failed ({error}); briefing session {found}, made anyway", file=sys.stderr
            )
            sid = found
        if name != title:
            print(f"session {sid} is titled {name}", file=sys.stderr)
        try:
            if not (found and delivered(og, sid, text, 0)):  # a found one may hold the brief
                og.send(sid, text)
            if delivered(og, sid, text, confirm_seconds):
                return sid, survivors
        except Fail as e:
            abandon(sid)
            raise failed(f"start failed: {sid}: {e}") from e
        reasons.append(f"{sid}: brief not in history after {confirm_seconds:.0f}s")
        abandon(sid)
    raise failed("start failed: " + "; ".join(reasons))


def wait(
    og: Omnigent,
    sid: str,
    report: Path,
    timeout: float = 3 * 3600,
    verdict: bool = False,
    since: int | None = None,
) -> str:
    """Return the report path, or raise with the child's last message once it cannot deliver one.

    With ``verdict`` (a verifier), the report counts only once it has a ``SATISFIED:`` line: a
    verifier can write its findings before its gate run ends. Raises ``Asked`` with the question's
    path when the child wrote one instead. Fails when the turn ends without a report, when the
    child is blocked on an approval or input prompt (nothing answers it), or after ``timeout``
    seconds. With ``since`` (a follow-up), only a report modified after that ``st_mtime_ns``
    counts: the one from the earlier turn is still there. A report that counts is returned once
    ``settled``, read again first, since the child can rewrite it until its turn ends.
    """
    deadline = time.monotonic() + timeout
    idle_since, nudged = None, False
    question = question_of(report)
    missing = f"a verdict in {report}" if verdict else str(report)

    def counts() -> bool:
        try:
            mtime = report.stat().st_mtime_ns
        except FileNotFoundError:
            return False
        return (since is None or mtime > since) and (
            not verdict or bool(VERDICT.search(report.read_text()))
        )

    while True:
        if question.exists():
            raise Asked(str(question))
        info = og.info(sid)
        status = str(info.get("status"))
        items = og.items(sid)
        last = last_message(items)
        said = text_of(last) if last else "(none)"
        if counts() and settled(report, info, items) and counts():
            if status in RUNNING and not prompts_of(info):
                print(
                    f"session {sid} still reads {status}, but its report and history were quiet"
                    f" for {SETTLE_SECONDS:.0f}s: taking the report (a lost turn end)",
                    file=sys.stderr,
                )
            break
        prompts = prompts_of(info)
        if prompts:
            raise Fail(
                f"session {sid} is blocked on a prompt: {'; '.join(prompts)}\nlast message: {said}"
            )
        # Idle with the brief last is a turn that ended with no output (codex forwarder maps an
        # empty completed turn to idle), unless it is the launch idle, the gap before a follow-up's
        # turn or a mid-turn idle: so only once the idle outlasted IDLE_GRACE_SECONDS.
        idle_since = (idle_since or time.monotonic()) if status not in RUNNING else None
        empty_turn = idle_since is not None and time.monotonic() - idle_since >= IDLE_GRACE_SECONDS
        if status not in RUNNING and (
            status == "failed" or (last is not None and last.get("role") != "user") or empty_turn
        ):
            time.sleep(POLL_SECONDS)  # a report written just before the turn ended
            if counts():
                continue  # final at the next look
            if question.exists():
                raise Asked(str(question))
            if status == "failed":
                error = (info.get("last_task_error") or {}).get("message") or "(no last_task_error)"
                raise Fail(
                    f"session {sid} ended (failed): {error}\nrunner log: {runner_log(info)}\nlast message: {said}"
                )
            if not nudged:  # often a turn ended on a background command: one reminder
                nudge = NUDGE.format(report=report)
                print(
                    f"session {sid} ended ({status}) without {missing}; nudging once",
                    file=sys.stderr,
                )
                og.send(sid, nudge)
                delivered(og, sid, nudge, 60.0)  # else its old last message ends the wait at once
                idle_since, nudged = None, True
                continue
            raise Fail(f"session {sid} ended ({status}) without {missing}\nlast message: {said}")
        if time.monotonic() >= deadline:
            raise Fail(
                f"session {sid} gave no {'verdict' if verdict else 'report'} after {timeout:.0f}s\nlast message: {said}"
            )
        time.sleep(POLL_SECONDS)
    return str(report)


def reap(og: Omnigent, sessions: list[str], parent: str | None = None) -> list[str]:
    """Finish (``Omnigent.archive``) each finished session of ``sessions`` and, with ``parent``, of
    its sub-agents: not running, no prompt waiting and no input pending. Return a line per session
    saying which, and how: ``archived``, or ``ended`` for a sub-agent, which stays unarchived.

    An idle child whose report is still to come looks finished here too, so reap only once the
    reports are in; a child whose ``run`` died is re-attached with ``wait``, which finishes it."""
    lines = []
    for sid in dict.fromkeys(sessions + (og.children(parent) if parent else [])):
        info = og.info(sid)
        status = str(info.get("status"))
        if info.get("archived"):
            continue
        if status in RUNNING or prompts_of(info) or info.get("pending_inputs"):
            busy = (
                "blocked on a prompt"
                if prompts_of(info)
                else status
                if status in RUNNING
                else "input pending"
            )
            lines.append(f"{sid} {info.get('title') or ''}: kept ({busy})")
            continue
        try:
            how = og.archive(sid)
        except Fail as e:  # one refused finish leaves the rest to reap
            lines.append(f"{sid} {info.get('title') or ''}: finish failed: {e}")
            continue
        lines.append(f"{sid} {info.get('title') or ''}: {how} ({status})")
    return lines


def observe(
    og: Omnigent, sid: str, idle_since: dict[str, tuple], baseline: bool = False
) -> tuple[tuple, str]:
    """A session's state as a comparable key (``running``, ``blocked``, ``failed`` or ``ended``,
    with what makes this occurrence distinct) and the line that reports it.

    A turn has ended as ``wait`` judges it: not running, with the last message not the user's,
    or idle past ``IDLE_GRACE_SECONDS`` (an empty turn), so the launch idle wakes nobody. The
    grace runs from the last message's arrival, so a follow-up landing on an idle session gets
    its own. ``baseline`` starts a new idle already past the grace: idle at the start is no news.
    """
    info = og.info(sid)
    status = str(info.get("status"))
    last = last_message(og.items(sid))
    head = f"{sid} {info.get('title') or ''}".rstrip()
    tail = f"\nlast message: {text_of(last) if last else '(none)'}"
    lid = last.get("id") if last else None
    if status in RUNNING:
        idle_since.pop(sid, None)
    elif sid not in idle_since or idle_since[sid][0] != lid:  # (last message id, idle since)
        idle_since[sid] = (lid, time.monotonic() - (IDLE_GRACE_SECONDS if baseline else 0))
    if prompts := prompts_of(info):
        ids = tuple(str(e.get("elicitation_id") or e) for e in info["pending_elicitations"])
        return ("blocked", ids), f"{head}: blocked on a prompt: {'; '.join(prompts)}{tail}"
    if status == "failed":
        e = info.get("last_task_error") or {}  # an object of strings: title, message, code, ...
        error = e.get("message") or e.get("title") or "(no error recorded)"
        return ("failed", str(error)), f"{head}: failed: {error}{tail}"
    if status not in RUNNING and (
        (last is not None and last.get("role") != "user")
        or time.monotonic() - idle_since[sid][1] >= IDLE_GRACE_SECONDS
    ):
        return ("ended", str(last.get("id")) if last else ""), f"{head}: turn ended{tail}"
    return ("running",), head


def watch(
    og: Omnigent, sessions: list[str], parent: str | None = None, timeout: float = 3 * 3600
) -> list[str]:
    """Return a line per session that ended a turn, blocked on a prompt or failed since the call.

    Watches ``sessions`` and, with ``parent``, its sub-agents, re-listed each poll so one started
    later is watched too. A state already there at the first poll is not news, except a prompt: a
    block waits on someone until it is answered. A session first seen later starts as running, so
    its first end is reported.
    """
    # ponytail: polls GET /v1/sessions/{id} per session. /v1/sessions/{id}/stream (SSE) pushes the
    # same changes within a second, but per session, without replay, and it registers a viewer;
    # upgrade when a wake must beat POLL_SECONDS or rosters grow past a few dozen sessions.
    deadline = time.monotonic() + timeout
    seen: dict[str, tuple] = {}
    idle_since: dict[str, tuple] = {}
    first = True
    while True:
        ids = list(dict.fromkeys(sessions + (og.children(parent) if parent else [])))
        changes = []
        for sid in ids:
            # idle at the start, empty turn or not, is the baseline, not a turn ending later
            key, line = observe(og, sid, idle_since, baseline=first)
            before = seen.get(sid, None if first else ("running",))
            seen[sid] = key
            if (
                key != before
                and key[0] != "running"
                and (before is not None or key[0] == "blocked")
            ):
                changes.append(line)
        if changes:
            return changes
        first = False
        if time.monotonic() >= deadline:
            raise Fail(f"no session changed in {timeout:.0f}s: {', '.join(ids) or '(none)'}")
        time.sleep(POLL_SECONDS)


def from_user(item: dict) -> bool:
    return item.get("type") == "message" and item.get("role") == "user"


def instruction(item: dict, resume: str) -> bool:
    """A user message that tells the session its task: not the resume line, nor the revive line."""
    text = text_of(item).strip()
    return from_user(item) and text != resume and not text.startswith(REVIVED)


def instructed(items: list[dict], resume: str) -> tuple[float, float]:
    """When the session was last told to write its report, and when the resume line was sent
    since (0.0 when it was not). The instruction is its newest user message other than the resume
    or revive line, else the oldest item on the page, since the instruction is older still. The
    resume line is read from the history, so a supervisor restarted after sending one sends no
    second."""
    told = [float(i.get("created_at") or 0) for i in items if instruction(i, resume)]
    since = told[-1] if told else min((float(i.get("created_at") or 0) for i in items), default=0.0)
    resent = [
        float(i.get("created_at") or 0)
        for i in items
        if from_user(i)
        and text_of(i).strip() == resume
        and float(i.get("created_at") or 0) >= since
    ]
    return since, max(resent, default=0.0)


def settled(report: Path, info: dict, items: list[dict]) -> bool:
    """Whether ``report``, one that counts, is final: the session is out of its turn (not running,
    or blocked on a prompt nothing answers) and the file unchanged for a poll, or the file and the
    history were both quiet for ``SETTLE_SECONDS`` while it still reads running, a lost turn end.
    Until its turn ends a child can rewrite its report: a verifier revising its verdict, a lead
    writing progress there."""
    try:
        age = time.time() - report.stat().st_mtime
    except FileNotFoundError:
        return False
    if str(info.get("status")) not in RUNNING or prompts_of(info):
        return age >= POLL_SECONDS
    newest = max((float(i.get("created_at") or 0) for i in items), default=0.0)
    return min(age, time.time() - newest) >= SETTLE_SECONDS


def written(path: Path, since: float) -> bool:
    try:
        return path.stat().st_mtime > since
    except FileNotFoundError:
        return False


def check(
    og: Omnigent,
    sid: str,
    report: Path,
    silent: float,
    resumed: dict[str, float],
    unsent: set[str],
    say: Callable[[str], None],
    briefs: list[Path] | None = None,
    verdict: bool = False,
) -> tuple[str, float]:
    """One look at ``sid``, which owes ``report``: the line for its caller when it wrote its report
    (with ``verdict``, a verifier's, once it has its ``SATISFIED:`` line, as ``wait`` counts it)
    or a question, blocks on a prompt, failed, or is given up on, else empty, with the time of the
    instruction it measured from.

    Liveness, not only outcomes: Omnigent can lose a sub-agent's turn end (its status stays
    ``running``, its parent is never woken) or reap an idle runner. A session with no live runner is
    revived in place and sent the revive line, naming ``briefs`` (else ``<report>.brief`` when it
    exists) and the report, since a revive can drop its context; one with no history item for ``silent`` seconds gets the nudge once as its
    resume line, whatever its status says, and is given up on when silent that long again, or at
    once when an input already waits undelivered (a resume line would queue behind it). Each of
    those is told to ``say`` at once. ``resumed`` holds when this process sent each resume line,
    since one held in ``pending_inputs`` is not in the history yet; ``unsent`` the revived sessions
    whose revive line did not go out, sent again at their next look.
    """
    # ponytail: compares the server's item clock with local time and file times, as send does; a
    # skewed server clock shifts the silence and the report's baseline by the skew.
    info, items = og.info(sid), og.items(sid)
    head = f"{sid} {info.get('title') or ''}".rstrip()
    resume = NUDGE.format(report=report)
    since, resent = instructed(items, resume)
    if resumed.get(sid, since) < since:  # sent before a newer instruction
        del resumed[sid]
    if written(report, since) and (not verdict or VERDICT.search(report.read_text())):
        if settled(report, info, items):
            return f"{head}: report written: {report}", since
        return "", since  # still in its turn: it may rewrite the report
    if written(question_of(report), since):
        return f"{head}: asked: {question_of(report)}", since
    if prompts := prompts_of(info):
        return f"{head}: blocked on a prompt: {'; '.join(prompts)}", since
    if info.get("status") == "failed":
        e = info.get("last_task_error") or {}
        return (
            f"{head}: failed: {e.get('message') or e.get('title') or '(no error recorded)'}",
            since,
        )
    if not info.get("runner_online", True):
        try:
            revive(og, sid)
        except Gone as e:
            return f"{head}: {e}; gave up", since
        say(f"{head}: revived (no live runner)")
        unsent.add(sid)
    if sid in unsent:  # once online, the revived runner never comes this way again: retry here
        og.send(sid, revive_line(report, briefs_for(report, briefs or [])))
        unsent.discard(sid)
        return "", since
    resent = max(resent, resumed.get(sid, 0.0))
    last = max((float(i.get("created_at") or 0) for i in items), default=0.0)
    quiet = time.time() - max(last, resent)
    if quiet < silent:
        return "", since
    # a session waiting on its own worker or verifier writes nothing meanwhile: the subtree's activity
    # is its liveness too, read only once its own history is quiet
    quiet = min(quiet, time.time() - og.active(sid))
    if quiet < silent:
        return "", since
    if resent:
        return f"{head}: silent {quiet:.0f}s after the resume line; gave up", since
    if info.get("pending_inputs"):
        return f"{head}: silent {quiet:.0f}s with an input undelivered; gave up", since
    og.send(sid, resume)
    resumed[sid] = time.time()
    say(f"{head}: silent {quiet:.0f}s ({info.get('status')}), report owed; resume line sent")
    return "", since


def supervise(
    og: Omnigent, owed: dict[str, Path], silent: float = 1800.0, timeout: float = 3 * 3600
) -> str:
    """Print and return the first line for the caller about a session of ``owed`` (session to the
    report it owes), as ``check`` finds it, printing its revive and resume lines on the way. Its
    caller runs it again for the sessions still owing, which reports any other at once.
    """
    deadline = time.monotonic() + timeout
    resumed: dict[str, float] = {}
    unsent: set[str] = set()

    def say(line: str) -> None:
        print(line, flush=True)

    while True:
        for sid, report in owed.items():
            # wake the caller now: no other session's read, revive or resume first
            event, _ = check(og, sid, report, silent, resumed, unsent, say)
            if event:
                say(event)
                return event
        if time.monotonic() >= deadline:
            raise Fail(f"no event in {timeout:.0f}s: {', '.join(owed)}")
        time.sleep(POLL_SECONDS)


def pair(text: str) -> tuple[str, Path]:
    sid, eq, path = text.strip().partition("=")
    if not (sid.strip() and eq and path.strip()):
        raise Fail(f"{text}: expected <session>=<report>")
    return sid.strip(), Path(path.strip())


def edit_registry(path: Path, edit: Callable[[list[str]], list[str]] | None = None) -> list[str]:
    """The registry's lines, read under an exclusive lock; with ``edit``, rewritten in place to
    ``edit(lines)`` under the same lock, so a ``run`` arming while the supervisor drops another
    session loses neither line. A missing file reads as empty."""
    if edit:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "a+" if edit else "r") as f:  # closing releases the lock
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            lines = f.read().splitlines()
            if edit:
                lines = edit(lines)
                f.seek(0)
                f.truncate()
                f.write("".join(line + "\n" for line in lines))
            return lines
    except FileNotFoundError:  # only a read opens without creating
        return []


def entry(line: str) -> tuple[str, Path, list[Path], bool]:
    """A registry line: ``session=report``, then the session's brief files, each after a tab, and
    whether its report is a verifier's (a ``verdict`` field, which ``run``, ``start`` and ``send``
    write for one)."""
    head, *fields = line.split("\t")
    sid, report = pair(head)
    fields = [f.strip() for f in fields if f.strip()]
    return sid, report, [Path(f) for f in fields if f != VERDICT_FIELD], VERDICT_FIELD in fields


def registered(path: Path) -> tuple[dict[str, tuple[Path, list[Path], bool]], list[str]]:
    """The registry's sessions with the reports they owe, their brief files and verdict flags, the last line
    winning for a session listed twice, and its malformed lines. Blank lines and ``#`` comments
    are skipped."""
    owed, bad = {}, []
    for line in edit_registry(path):
        if line.strip() and not line.lstrip().startswith("#"):
            try:
                sid, *owes = entry(line)
            except Fail:
                bad.append(line)
            else:
                owed[sid] = tuple(owes)
    return owed, bad


def arm(
    path: Path,
    sid: str,
    report: Path | None = None,
    briefs: list[Path] | None = None,
    then: Path | None = None,
    unless: Callable[[], bool] = lambda: False,
    verdict: bool = False,
) -> None:
    """Replace ``sid``'s line in the registry with ``sid=report``, ``briefs`` and, with ``verdict``,
    the ``verdict`` field, or with ``report`` None drop it; unless ``unless()``, asked under the lock, is true. ``then`` (a follow-up's file)
    goes after the brief files the line had, else after the one ``start`` wrote."""

    def names(line: str) -> bool:
        return line.partition("=")[0].strip() == sid

    def edit(lines: list[str]) -> list[str]:
        if unless():
            return lines
        rest, mine = [x for x in lines if not names(x)], [x for x in lines if names(x)]
        if not report:
            return rest
        files = briefs or []
        if then:
            try:
                had = entry(mine[-1])[2] if mine else []
            except Fail:
                had = []
            files = [b for b in briefs_for(report, had) if b != then] + [then]
        flag = [VERDICT_FIELD] if verdict else []
        return rest + ["\t".join([f"{sid}={report}", *map(str, files), *flag])]

    edit_registry(path, edit)


def arm_quietly(
    path: Path | None,
    sid: str,
    report: Path | None = None,
    briefs: list[Path] | None = None,
    then: Path | None = None,
    verdict: bool = False,
) -> None:
    """``arm`` for a command with its own wait: a failure is a warning, since that wait still
    covers the session."""
    if path:
        try:
            arm(path, sid, report, briefs, then, verdict=verdict)
        except OSError as e:
            print(
                f"registry {path}: {sid} not {'armed' if report else 'disarmed'}: {e}",
                file=sys.stderr,
            )


def supervise_registry(
    og: Omnigent,
    registry: Path,
    notify: str | None = None,
    silent: float = 1800.0,
    timeout: float = 3 * 3600,
) -> NoReturn:
    """Run until stopped, checking each session ``registry`` lists as ``supervise`` does, re-read
    each poll. Every line goes to stdout with the local time and, with ``notify``, into that
    session as ``Supervisor: <line>``. Lines wait in order until posted, and each poll posts them
    first, stopping at the first failure. A terminal event drops the session's line once its own
    line is posted, and a session whose terminal line waits is not checked again. The drop keeps
    the line when the session was instructed since the event's instruction: the caller armed it
    again for a newer brief, once that brief was in the history. An error is
    logged to stderr, once until it clears, and never stops the loop; so is ``timeout`` with no
    event.
    """
    resumed: dict[str, float] = {}
    unsent: set[str] = set()  # ponytail: in memory, so a restart loses a revive line still unsent
    logged: dict[object, str] = {}  # the error last logged per session (or registry, post, drop)
    # Each line not yet posted (None once it is), with what a terminal line drops: its session,
    # report and the instruction its check measured from.
    # ponytail: in memory, so a restart loses the revive and resume lines waiting in it; a terminal
    # event keeps its registry line until posted, and the restarted supervisor finds it again.
    outbox: list[tuple[str | None, tuple[str, Path, float] | None]] = []
    window = time.monotonic()

    def stamp(line: str) -> str:
        return f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}"

    def log(key: object, error: str | None) -> None:
        if error is None:
            logged.pop(key, None)
        elif logged.get(key) != error:
            logged[key] = error
            print(stamp(error), file=sys.stderr, flush=True)

    def post(line: str) -> bool:
        if not notify:
            return True
        try:
            # a message to a reaped session answers `queued` and never arrives
            if not og.info(notify).get("runner_online", True):
                revive(og, notify)
            og.send(notify, f"Supervisor: {line}")
        except Exception as e:  # noqa: BLE001 - never fatal; the event is found again
            log("post", f"post to {notify} failed: {reason(e)}")
            return False
        log("post", None)
        return True

    def drop(sid: str, report: Path, since: float) -> bool:
        resume = NUDGE.format(report=report)

        def renewed() -> bool:
            return any(
                instruction(i, resume) and float(i.get("created_at") or 0) > since
                for i in og.items(sid)
            )

        try:
            arm(registry, sid, unless=renewed)
        except Exception as e:  # noqa: BLE001 - never fatal; the drop is retried
            log(("drop", sid), f"{registry}: {sid} not dropped: {reason(e)}")
            return False
        log(("drop", sid), None)
        resumed.pop(sid, None)
        unsent.discard(sid)
        return True

    def flush() -> None:
        while outbox:
            line, event = outbox[0]
            if line is not None and not post(line):
                return
            if event and not drop(*event):
                outbox[0] = (None, event)  # posted; only the drop is retried
                return
            outbox.pop(0)

    def say(line: str, event: tuple[str, Path, float] | None = None) -> None:
        print(stamp(line), flush=True)
        outbox.append((line, event))
        flush()

    while True:
        flush()
        try:
            owed, bad = registered(registry)
        except Exception as e:  # noqa: BLE001 - never fatal
            owed, bad = {}, []
            log("registry", f"{registry}: {reason(e)}")
        else:
            log("registry", None)
        for line in bad:
            log(("line", line), f"{registry}: {line!r}: expected <session>=<report>; skipped")
        for sid, (report, briefs, verdict) in owed.items():
            if any(e and e[0] == sid for _, e in outbox):
                continue  # its event is found; it waits to be posted
            try:
                event, since = check(og, sid, report, silent, resumed, unsent, say, briefs, verdict)
            except Exception as e:  # noqa: BLE001 - one session's error skips no other
                log(sid, f"{sid}: {reason(e)}")
                continue
            log(sid, None)
            if not event:
                continue
            window = time.monotonic()
            say(event, (sid, report, since))
        if time.monotonic() - window >= timeout:
            print(
                stamp(f"no event in {timeout:.0f}s: {', '.join(owed) or '(none)'}"),
                file=sys.stderr,
                flush=True,
            )
            window = time.monotonic()
        time.sleep(POLL_SECONDS)


def reason(e: Exception) -> str:
    return str(e) if isinstance(e, Fail) else f"{type(e).__name__}: {e}"


def archive_delivered(og: Omnigent, sid: str) -> None:
    """Finish a session whose report or verdict came back (``Omnigent.archive``): its agent process
    frees the runner's file descriptors. A failed finish is reported, not fatal."""
    try:
        og.archive(sid)
    except Fail as e:
        print(f"session {sid} delivered but was not finished: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "start"):
        p = sub.add_parser(name)
        p.add_argument("agent", choices=AGENTS)
        p.add_argument("title")
        p.add_argument("brief", type=Path, help="file with the task specifics")
        p.add_argument("report", type=Path)
        p.add_argument("--role", help="worker/verifier role file the child reads first")
        p.add_argument("--confirm-seconds", type=float, default=60.0)
        p.add_argument(
            "--model",
            help="model (default: $OMNIGENT_MODEL_<AGENT>, e.g. OMNIGENT_MODEL_CODEX, else the harness default)",
        )
        p.add_argument(
            "--author",
            choices=AGENTS,
            help="model family that wrote the diff; a verifier of the same family needs --same-family",
        )
        p.add_argument(
            "--same-family",
            action="store_true",
            help="verify with the author's own family when the other is unavailable; the PR body says so",
        )
        p.add_argument(
            "--top-level",
            action="store_true",
            help="start a lead: no parent session, under the lead preamble (start only)",
        )
    p = sub.add_parser("send")
    p.add_argument("session")
    p.add_argument("brief", type=Path, help="file with the answer or follow-up")
    p.add_argument("report", type=Path)
    p.add_argument("--confirm-seconds", type=float, default=60.0)
    p = sub.add_parser("watch")
    p.add_argument("sessions", nargs="*")
    p.add_argument("--children", metavar="PARENT", help="also watch this session's sub-agents")
    p = sub.add_parser("reap")
    p.add_argument("sessions", nargs="*")
    p.add_argument("--children", metavar="PARENT", help="also reap this session's sub-agents")
    p = sub.add_parser("supervise")
    p.add_argument(
        "owed", nargs="*", metavar="SESSION=REPORT", help="a session and the report it owes"
    )
    p.add_argument(
        "--registry",
        type=Path,
        help="run until stopped, supervising the session=report lines of this file, re-read each poll",
    )
    p.add_argument("--notify", metavar="SESSION", help="with --registry, post each line here too")
    p.add_argument(
        "--silent-seconds",
        type=float,
        default=1800.0,
        help="no history item for this long: one resume line, then given up (default 1800)",
    )
    p = sub.add_parser("wait")
    p.add_argument("session")
    p.add_argument("report", type=Path)
    for p in sub.choices.values():
        if p.prog.split()[-1] in ("send", "wait"):
            p.add_argument(
                "--verdict",
                action="store_true",
                help="a verifier's report: done only once it has a SATISFIED: line",
            )
        if p.prog.split()[-1] not in ("start", "reap"):
            p.add_argument("--timeout", type=float, default=3 * 3600, help="seconds (default 3h)")
        if p.prog.split()[-1] in ("run", "start", "send", "wait"):
            p.add_argument(
                "--registry",
                type=Path,
                default=os.environ.get("OMNIGENT_SUPERVISE_REGISTRY") or None,
                help="supervisor registry to arm with session=report (default: $OMNIGENT_SUPERVISE_REGISTRY)",
            )
    args = ap.parse_args(argv)
    sid, registry = getattr(args, "session", None), getattr(args, "registry", None)
    try:
        owed = {s: r.resolve() for s, r in map(pair, getattr(args, "owed", []))}
        if args.cmd == "supervise" and not (owed or args.registry):
            raise Fail("supervise needs <session>=<report> pairs or --registry")
        og = Omnigent()
        if args.cmd == "watch":
            if not args.sessions and not args.children:
                raise Fail("watch needs a session or --children <parent>")
            print("\n".join(watch(og, args.sessions, args.children, args.timeout)))
            return 0
        if args.cmd == "reap":
            if not args.sessions and not args.children:
                raise Fail("reap needs a session or --children <parent>")
            print("\n".join(reap(og, args.sessions, args.children)))
            return 0
        if args.cmd == "supervise":
            if args.registry:
                for s, r in owed.items():
                    arm(args.registry, s, r)
                supervise_registry(
                    og, args.registry, args.notify, args.silent_seconds, args.timeout
                )
            supervise(og, owed, args.silent_seconds, args.timeout)  # it prints each line
            return 0
        if args.cmd == "wait":
            print(wait(og, args.session, args.report.resolve(), args.timeout, args.verdict))
            # the caller has the result: the supervisor's line for it would be a second wake
            arm_quietly(registry, args.session)
            archive_delivered(og, args.session)
            return 0
        report = args.report.resolve()
        # The child's workspace is this directory; outside it a Codex sandbox refuses the write and
        # Claude Code prompts for the read (denies it in auto mode), which nobody answers. The child also
        # saves its repro files beside the report.
        if not report.is_relative_to(Path.cwd()):
            raise Fail(
                f"{report} is outside the child's workspace {Path.cwd()}; use tmp/loop/ in the worktree"
            )
        if args.cmd == "send":
            # A report older than the question the follow-up answers, else than the send, is the
            # turn before's. The question first: a rerun after the first send died must not take
            # the report that answer already produced as the old one.
            since = None
            for path in (question_of(report), report):
                try:
                    since = path.stat().st_mtime_ns
                    break
                except FileNotFoundError:
                    pass
            send(og, args.session, args.brief.read_text(), report, args.confirm_seconds)
            # armed once the message is in the history, as start arms: before it, the report or
            # question of the turn before reads as newer than the last instruction
            arm_quietly(
                registry, args.session, report, then=args.brief.resolve(), verdict=args.verdict
            )
            print(wait(og, args.session, report, args.timeout, args.verdict, since))
            arm_quietly(registry, args.session)
            return 0
        if args.cmd == "run" and args.top_level:
            raise Fail(
                "run --top-level: a lead asks the owner in its own session, so there is no question"
                " for run to return; use start --top-level, then watch <session>"
            )
        brief = args.brief.read_text()
        verifier = bool(args.role and "verifier" in args.role)
        if args.author == args.agent and verifier and not args.same_family:
            raise Fail(
                f"{args.agent} would verify {args.author}-written code; pass --same-family to allow it"
            )
        # A report already there is a pass before (a fix pass reuses the path): only a newer one counts.
        # `wait` after a separate `start` has no launch time to compare, so `start` refuses it.
        if args.cmd == "start" and report.exists():
            raise Fail(
                f"{report} already exists; wait would return at once (use run, or a new path)"
            )
        launched = time.time_ns()
        report.parent.mkdir(parents=True, exist_ok=True)
        sid, survivors = start(
            og,
            args.agent,
            args.title,
            brief,
            report,
            args.role,
            args.confirm_seconds,
            model=args.model
            or os.environ.get(f"OMNIGENT_MODEL_{args.agent.upper()}")
            or (CODEX_VERIFIER_MODEL if verifier and args.agent == "codex" else None),
            top_level=args.top_level,
        )
        arm_quietly(registry, sid, report, [brief_of(report)], verdict=verifier)
        print(sid, flush=True)
        if args.cmd == "run":
            print(wait(og, sid, report, args.timeout, verifier, launched))
            arm_quietly(registry, sid)
            archive_delivered(og, sid)
        if survivors:
            raise Fail(f"abandoned sessions survive: {', '.join(survivors)}")
        return 0
    except Fail as e:
        if e.code == ASKED and sid:  # the caller has the question
            arm_quietly(registry, sid)
        print(e, file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
