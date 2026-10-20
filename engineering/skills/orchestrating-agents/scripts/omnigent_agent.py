#!/usr/bin/env python3
"""Start an engineering-loop agent through Omnigent and wait for its report.

    python3 scripts/omnigent_agent.py run <claude|codex> <title> <brief-file> <report-path> [--role FILE]
    python3 scripts/omnigent_agent.py start <claude|codex> <title> <brief-file> <report-path> [--role FILE] [--top-level [--host NAME|ID]] [--workspace DIR]
    python3 scripts/omnigent_agent.py send <session> <brief-file> <report-path>
    python3 scripts/omnigent_agent.py relay <session> <message-file>
    python3 scripts/omnigent_agent.py approve <session> [--decline]
    python3 scripts/omnigent_agent.py status <session>...
    python3 scripts/omnigent_agent.py report <session> [<path>] [--registry <file>]
    python3 scripts/omnigent_agent.py watch [<session>...] [--children <parent>]
    python3 scripts/omnigent_agent.py reap [<session>...] [--children <parent>] [--registry <file>]
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
``relay`` posts a message that owes no report (an owner's words for a lead) and returns at once:
exit 0 once it is in the history (or a copy the session has not answered yet already is: no second
one), 5 while the session holds it (a step, or an approval prompt, in progress), 4 when it cannot be
delivered (archived, a failed revive, neither pending nor in the history). A session blocked only
on questions (``ask_user_question``) gets the message as each question's answer instead, exit 0,
since its pending inputs wait on the answer; an approval prompt it never answers. ``approve``
accepts (``--decline``: declines) every pending approval prompt, never a question, printing each
tool call it answered; exit 1 when none was pending or a resolve failed. Whether an agent may
approve is the project's policy, not this script's. ``status`` prints one line per session:
its state, queued inputs and last assistant message (``(none)`` before its first).
``report`` prints a file through the session's file API, from any host: an absolute ``<path>`` is
read on the session's host, a relative one in its workspace, and no path is the report in its
registry line (``--registry``, else ``$OMNIGENT_SUPERVISE_REGISTRY``; neither, or no line: exit 2).
A directory prints its entries one per line; exit 4 for a missing file, 1 for any other failure.
``watch`` exits 0 as soon as one of the given sessions (or a parent's sub-agents) ends a turn, blocks on
a prompt or fails, printing each one's id, title, that change and its last assistant message; it is how a
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
Each poll it writes ``<registry stem>.state.json`` (schema ``cos-state/1``, loaded on start, so a
restart re-posts no event it settled), appends each event to ``<registry stem>.events.jsonl``,
labels each session with ``status.line`` and ``status.at``, and raises ``deadline`` for a
followed lead with no progress for 20 minutes.
``run``, ``start`` and ``send`` arm the registry given by ``--registry``, else
``$OMNIGENT_SUPERVISE_REGISTRY``, once their message is in the history (``start`` with its brief
file, ``send`` appending its message file, each marking a verifier's line as ``wait`` would
count its report); ``run``, ``send`` and ``wait`` disarm it when they
return the report or a question; ``reap`` drops the line of each session it finishes, before
finishing it, so the supervisor posts no ``archived`` for a finish its notified session ran.
``run`` and ``wait`` finish the session whose report or verdict they return, not one that asked a
question; ``reap`` finishes each one that is done (not running, no prompt or input waiting) and keeps
the rest, exiting 1 when a finish failed; it cannot tell a child still owing its report from a finished one, so it runs once every
report is in. Finishing archives the session, which keeps its transcript; nothing here deletes a
session.

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
since a lead asks the owner in its own session and writes no question for ``run`` to return.
``--workspace`` gives the child a workspace other than this directory, such as one holding
several repos' checkouts for a change across them; its report must be inside it. ``--host``
starts a ``--top-level`` lead on another Omnigent host, by name or id (``GET /v1/hosts``); a
child always runs on its parent's runner. On a host other than this one ``--workspace`` and the
report are absolute paths there, unchecked here, the brief goes inline in the first message since
its file would be here, and the report is written there, so follow the lead with ``watch``. A ``GET`` is retried on a timeout or reset; a ``POST`` never is. ``start`` refuses a
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
# Out of its turn this long, the report unchanged as long: the turn has ended. One idle look is no
# proof, since a session can read idle mid-turn (IDLE_GRACE_SECONDS above).
TURN_END_SECONDS = 30.0
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
VERDICT = re.compile(r"^SATISFIED: (yes|no)\b", re.MULTILINE)  # a verifier report's last line
VERDICT_FIELD = "verdict"  # a registry line's mark for a verifier's report
FOLLOW_FIELD = "follow"  # a registry line's mark for a lead followed, not owed a report
# A followed lead's turn end that names one of these is news at once; any other waits for quiet.
ENDING = re.compile(r"^\W*(DONE|USER NEEDED|PARKED)\b", re.MULTILINE)
# A followed lead and its live children writing nothing for this long since a turn end: the end
# is news. Shorter, and a lead between its own workers' turns wakes the chief of staff for nothing.
FOLLOW_QUIET_SECONDS = 300.0
# A followed lead with no progress (its own history, its live children) this long: a ``deadline``
# event, whatever its status reads; this much more once it was nudged.
DEADLINE_SECONDS = 1200.0
NUDGED_SECONDS = 600.0
# What a lead's ``STILL WORKING`` message says it waits on, for its status and its deadline.
# ponytail: one regex over the lead's own words; a wait named any other way reads as unknown, which
# only adds the nudge step. Upgrade: a structured wait line in the lead's report.
WAIT = re.compile(r"STILL WORKING\b.*?\b((?i:verifier|worker|lead|merge)|CI)s?\b", re.DOTALL)
STATE_SCHEMA = "cos-state/1"
# A lead's unchanged status labels are written again once the last write is this old.
# ponytail: a knob; the browser marks a line stale past 10 min, so keep it well under that.
LABEL_SECONDS = 60.0
SETTLED_KEPT = 20  # the newest settled event ids kept per session, enough to cover its live ones
ASKED, GONE, QUEUED = 3, 4, 5  # exit codes: the child asked a question; send found no runner it
# could revive, or relay could not deliver; relay left the message queued in the session
# A relayed copy pending this long is queued, not landing: a step or a prompt holds it.
QUEUED_SECONDS = 10.0
# A host over either limit has no room for another session: they time out and fail there. Knobs,
# since what a host carries depends on its hardware and what else runs on it.
MAX_LOAD_PER_CORE = float(os.environ.get("OMNIGENT_MAX_LOAD_PER_CORE") or 4)
MIN_AVAILABLE_MB = float(os.environ.get("OMNIGENT_MIN_AVAILABLE_MB") or 1536)
CAPACITY_WAIT_SECONDS = 600.0  # start waits this long for room, then fails
MEMINFO = Path("/proc/meminfo")

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


class Queued(Fail):
    code = QUEUED


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

    def project(self, name: str) -> dict | None:
        """The project (a sidebar group) called ``name``, or None when there is none. Case, spaces
        and punctuation don't count: the repo ``voice_note`` files under the project "Voice note".
        An exact name wins; two loose matches and no exact one fail rather than pick by order."""
        projects = self.call("GET", "/v1/projects")
        projects = projects.get("data", projects) if isinstance(projects, dict) else projects
        if exact := [p for p in projects if p.get("name") == name]:
            return exact[0]
        key = loose(name)
        matches = [p for p in projects if key and loose(p.get("name") or "") == key]
        if len(matches) > 1:
            names = ", ".join(repr(p.get("name")) for p in matches)
            raise Fail(
                f"projects {names} all match {name!r}: set OMNIGENT_PROJECT to the exact one"
            )
        return matches[0] if matches else None

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
        body = {
            "agent_id": self.agent_id(AGENTS[agent]),
            "title": title,
            "host_id": host_id or self.host_id,
            "workspace": workspace or os.getcwd(),
        }
        # Filed under the repo's project, when one exists, so spawned sessions don't crowd the top level.
        if project := self.project(project_name()):
            body["project_id"] = str(project["id"])
        # A sub-agent of the runner's primary session (the lead, also when a child runs
        # this): hidden from the owner's sidebar and unread badge, and gone with it. Top level
        # with ``top_level`` or when not run from an Omnigent session.
        if (parent := parent_id()) and not top_level:
            body["parent_session_id"] = parent
        if model := model or os.environ.get(f"OMNIGENT_MODEL_{agent.upper()}"):
            body["model_override"] = model
        # Only claude-native applies it: codex-native passes it to the codex CLI, which then never
        # starts its terminal (the session fails "Codex native bridge state is missing").
        if agent == "claude" and (
            mode := permission_mode or os.environ.get("OMNIGENT_PERMISSION_MODE")
        ):
            body["terminal_launch_args"] = ["--permission-mode", mode]
        return str(self.call("POST", "/v1/sessions", body)["id"])

    def host(self, name: str) -> str:
        """The ``host_id`` of the one host whose id or name is ``name``."""
        hosts = self.call("GET", "/v1/hosts")["hosts"]
        ids = [h["host_id"] for h in hosts if name in (h["host_id"], h["name"])]
        if len(ids) != 1:
            known = ", ".join(f"{h['name']} ({h['status']})" for h in hosts)
            why = "names several hosts" if ids else "names no host"
            raise Fail(f"--host {name} {why}; hosts: {known}")
        return ids[0]

    def hosts(self) -> dict[str, str]:
        """Each host's name by its ``host_id``."""
        return {h["host_id"]: h["name"] for h in self.call("GET", "/v1/hosts")["hosts"]}

    def label(self, sid: str, labels: dict[str, str]) -> None:
        """Upsert ``labels`` on ``sid``; an empty value clears one."""
        self.call("PATCH", f"/v1/sessions/{sid}", {"labels": labels})

    def subscribe(self, subscriber: str, sid: str) -> None:
        """Have Omnigent tell ``subscriber`` each time ``sid`` ends a turn or waits on a prompt."""
        self.call("POST", f"/v1/sessions/{subscriber}/subscriptions", {"session_id": sid})

    def retry(self, sid: str) -> dict:
        return self.call(
            "POST", f"/v1/sessions/{sid}/events", {"type": "retry_session", "data": {}}
        )

    def resolve(self, sid: str, eid: str, action: str, content: dict | None = None) -> None:
        """Answer a pending prompt: ``accept`` or ``decline``; a question's ``content`` maps each
        question's text to its answer (Claude reads it as ``tool_input.answers``, Codex by question
        id with the text as fallback)."""
        body = {"action": action, **({"content": content} if content else {})}
        self.call("POST", f"/v1/sessions/{sid}/elicitations/{eid}/resolve", body)

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

    def read_file(self, sid: str, path: str) -> str:
        """``path`` through ``sid``'s file API, whichever host the session runs on: an absolute
        path is read from the host (``base=host``), a relative one from the session's workspace.
        A file's text, or a directory's entries one per line (``/`` after a subdirectory); a
        missing file is ``Gone``. Each segment is encoded alone, with no leading ``%2F``. An
        absolute path inside the session's workspace is read relative to it, since a host on an
        older Omnigent answers 404 to an absolute file read (``base=host``) it serves relative."""
        if path.startswith("/"):
            try:  # no workspace known: the absolute read reports its own error
                root = str(self.info(sid).get("workspace") or "").rstrip("/") + "/"
            except Fail:
                root = "/"
            path = path[len(root) :] if root != "/" and path.startswith(root) else path
        segments = "/".join(quote(s, safe="") for s in path.split("/") if s)
        url = f"/v1/sessions/{sid}/resources/environments/default/filesystem/{segments}"
        try:
            out = self.call("GET", url + ("?base=host" if path.startswith("/") else ""))
        except Fail as e:
            if isinstance(e.__cause__, HTTPError) and e.__cause__.code == 404:
                raise Gone(f"{path}: not found") from e
            raise
        if "content" in out:
            return out["content"]
        return "\n".join(
            e["name"] + ("/" if e.get("type") == "directory" else "") for e in out.get("data", [])
        )

    def archive(self, sid: str) -> None:
        """Finish ``sid``: archive it, which ends its agent process and keeps its transcript. Never
        DELETE, which erases the transcript. A sub-agent's archive leaves the runner it shares
        with its parent up (kzarzycki/omnigent 4dd0af32)."""
        self.call("PATCH", f"/v1/sessions/{sid}", {"archived": True})

    def find(self, title: str, after: float, top_level: bool = False) -> str | None:
        """The parent's child called ``title`` created at or after ``after`` (epoch seconds): the
        session a create that failed in transit made anyway. None when there is no parent. With
        ``top_level``, the project's top-level session of that title instead (unfiled ones when the
        project does not exist, as ``create`` files them)."""
        if top_level:
            # the list filters by the project's exact name; "" is the unfiled sessions
            project = quote((self.project(project_name()) or {}).get("name", ""))
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


def loose(name: str) -> str:
    """``name`` without case, spaces or punctuation; letters and digits in any script stay."""
    return "".join(c for c in name.casefold() if c.isalnum())


def parent_id() -> str:
    """The runner's primary session (the lead, also when a child runs this), else empty."""
    return os.environ.get("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "")


def own_id() -> str:
    """The session this runs in: a child's own id, not its lead's. Codex names it in
    OMNIGENT_SESSION_ID, a Claude pane in OMNIGENT_TERMINAL_LAUNCH_SESSION_ID; else the primary."""
    env = os.environ
    return (
        env.get("OMNIGENT_SESSION_ID")
        or env.get("OMNIGENT_TERMINAL_LAUNCH_SESSION_ID")
        or parent_id()
    )


def runner_log(info: dict) -> str:
    """Where the session's runner logs: one file per primary session, children included."""
    root = info.get("parent_session_id") or info.get("id") or "*"
    logs = sorted(RUNNER_LOGS.glob(f"runner-{root}-*.log"), key=lambda f: f.stat().st_mtime)
    return str(logs[-1]) if logs else str(RUNNER_LOGS / f"runner-{root}-*.log")


def text_of(item: dict) -> str:
    return "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))


def last_message(items: list[dict]) -> dict | None:
    return next((i for i in reversed(items) if i.get("type") == "message"), None)


def last_said(items: list[dict]) -> str:
    """What the session last said: a user message is a brief, a nudge or an injected reminder."""
    said = [i for i in items if i.get("type") == "message" and i.get("role") == "assistant"]
    return text_of(said[-1]) if said else "(none)"


def prompts_of(info: dict) -> list[str]:
    """What each pending approval prompt asks: the tool call it holds, else its message."""
    return [
        str(p.get("content_preview") or p.get("message") or e)
        for e in info.get("pending_elicitations") or []
        for p in [e.get("params") or {}]
    ]


def questions_of(info: dict) -> list[str]:
    """What each pending question asks (Claude's AskUserQuestion, Codex's requestUserInput, both
    marked ``ask_user_question``): prompts an answer settles, unlike an approval."""
    return [
        str(p.get("content_preview") or p.get("message") or e)
        for e in info.get("pending_elicitations") or []
        for p in [e.get("params") or {}]
        if p.get("ask_user_question")
    ]


def send_to_confirm(og: Omnigent, sid: str, text: str) -> None:
    """Send a message the caller then looks for in the history. A timeout is no failure here: a slow
    server takes the message after the client gave up, and the history decides."""
    try:
        og.send(sid, text)
    except Fail as e:
        if not isinstance(getattr(e.__cause__, "reason", e.__cause__), TimeoutError):
            raise
        print(f"{e}; confirming from the history", file=sys.stderr)


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


def send(
    og: Omnigent,
    sid: str,
    brief: str,
    report: Path | None,
    confirm_seconds: float,
    queued_after: float | None = None,
) -> str:
    """Send a follow-up (an answer) to a session whose runner is still up, and wait until it lands:
    ``delivered``, or ``already`` when a copy had landed before. With ``queued_after`` (a relay),
    ``queued`` once the copy has been pending that long instead.

    Omnigent hands a message to the harness at once, also mid-turn: that is steering (the web
    composer's queue and its "Always steer" live only in the browser). The session lists it under
    ``pending_inputs`` until the harness folds it in at its next tool boundary, which a long
    foreground command holds off for minutes. So pending is delivery under way, and the message is
    lost only once it has been neither pending nor in the history for ``confirm_seconds``. A retry
    finds the first copy pending, or in the history since the question was written, and sends
    nothing: a second post delivers twice. With no ``report`` (a relay), a copy the session has
    not replied to yet is that first copy.
    """
    text, question = brief.strip(), question_of(report) if report else None
    # Read once, first: the sender of the first copy deletes the question once that copy lands.
    try:
        asked: float | None = question.stat().st_mtime if question else None
    except FileNotFoundError:
        asked = None
    # History before info: Omnigent persists a copy before it drops it from pending_inputs, so a
    # copy seen pending is not among the ``old`` ids and its landing shows up as a new item.
    items = og.items(sid)
    old = frozenset(str(i.get("id")) for i in items)
    info = og.info(sid)
    if info.get("archived"):
        raise Gone(f"session {sid} is archived")
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
    replied = max(
        (n for n, i in enumerate(items) if i.get("type") == "message" and i.get("role") != "user"),
        default=-1,
    )
    if (
        asked is not None and any(float(i.get("created_at") or 0) >= asked for i in copies(items))
    ) or (question is None and copies(items[replied + 1 :])):
        print(f"session {sid}: this message already landed", file=sys.stderr)
        if question:
            question.unlink(missing_ok=True)
        return "already"
    # or it landed between the two reads
    if pending(info) or any(str(i.get("id")) not in old for i in copies(og.items(sid))):
        print(
            f"session {sid}: this message was already sent; waiting for that copy", file=sys.stderr
        )
    else:
        send_to_confirm(og, sid, brief)
    deadline, held = time.monotonic() + confirm_seconds, None
    while True:
        info = og.info(sid)  # before the history: a copy leaves pending only once it has landed
        if any(str(i.get("id")) not in old for i in copies(og.items(sid))):
            break
        if pending(info):
            if held is None and queued_after is None:  # relay says it once it returns queued
                print(
                    f"session {sid} is {info.get('status')}: message queued in its harness until"
                    " the current step ends",
                    file=sys.stderr,
                )
            held = held or time.monotonic()
            if queued_after is not None and time.monotonic() - held >= queued_after:
                return "queued"
            deadline = time.monotonic() + confirm_seconds
        elif time.monotonic() >= deadline:
            raise Gone(
                f"session {sid}: message neither pending nor in history for {confirm_seconds:.0f}s;"
                " start a fresh run instead"
            )
        time.sleep(POLL_SECONDS)
    if question:
        question.unlink(missing_ok=True)  # kept until the answer lands, for the fresh run
    return "delivered"


def relay(og: Omnigent, sid: str, text: str, confirm_seconds: float) -> str:
    """Post ``text`` to ``sid`` and return the line saying it was delivered; raise ``Queued`` while
    the session holds it, ``Gone`` when it cannot be delivered. A session blocked only on questions
    gets ``text`` as each one's answer instead: its pending inputs wait on the answer, and an
    interrupt would drop them and hold input until the question's hook marker goes stale
    (kzarzycki/omnigent#14). An approval prompt it never answers."""
    info = og.info(sid)
    pending = info.get("pending_elicitations") or []
    asks = questions_of(info)
    if asks and len(asks) == len(pending):
        for e in pending:
            questions = e["params"]["ask_user_question"].get("questions") or []
            answer = text.strip()  # a message file's trailing newline would reach the answer
            og.resolve(
                sid, e["elicitation_id"], "accept", {q["question"]: answer for q in questions}
            )
        return f"session {sid}: answered its open question: {'; '.join(asks)}"
    outcome = send(og, sid, text, None, confirm_seconds, QUEUED_SECONDS)
    if outcome == "queued":
        prompts = prompts_of(og.info(sid))
        if prompts:
            why = f"behind a prompt (`approve` answers an approval): {'; '.join(prompts)}"
        else:
            why = "until the session's current step ends"
        raise Queued(f"session {sid}: queued {why}; it lands then")
    return f"session {sid}: {'already delivered' if outcome == 'already' else 'delivered'}"


def approve(og: Omnigent, sid: str, decline: bool = False) -> tuple[list[str], bool]:
    """Resolve each pending approval prompt of ``sid``, never a question (``relay`` answers those):
    a line per prompt, and whether a resolve failed. Fail when none is pending."""
    info, lines, failed = og.info(sid), [], False
    for e, what in zip(info.get("pending_elicitations") or [], prompts_of(info)):
        if (e.get("params") or {}).get("ask_user_question"):
            continue
        try:
            og.resolve(sid, str(e["elicitation_id"]), "decline" if decline else "accept")
            lines.append(f"session {sid}: {'declined' if decline else 'accepted'} {what}")
        except Fail as x:
            failed = True
            lines.append(f"session {sid}: not answered: {what}: {x}")
    if not lines:
        raise Fail(f"session {sid}: no approval prompt pending")
    return lines, failed


def capacity() -> tuple[bool, str]:
    """Whether this host has room for another session, and a line saying what it carries."""
    load = os.getloadavg()[0] / (os.cpu_count() or 1)
    # ponytail: this host only, the one start's config names; no /proc (macOS) leaves load alone.
    found = (
        re.search(r"^MemAvailable:\s+(\d+) kB", MEMINFO.read_text(), re.MULTILINE)
        if MEMINFO.exists()
        else None
    )
    mb = int(found.group(1)) / 1024 if found else float("inf")
    line = f"load {load:.1f} per core (max {MAX_LOAD_PER_CORE:g}), {mb:.0f} MB available (min {MIN_AVAILABLE_MB:g})"
    return load <= MAX_LOAD_PER_CORE and mb >= MIN_AVAILABLE_MB, line


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
    workspace: str | None = None,
    permission_mode: str | None = None,
    host_id: str | None = None,
    subscribe: bool = True,
) -> tuple[str, list[str]]:
    """Return the confirmed session id and any abandoned sessions whose finish failed. A top-level
    lead subscribes its starter unless ``subscribe`` is false: a supervisor follows it instead."""
    if permission_mode and agent != "claude":
        raise Fail(
            f"--permission-mode is for claude sessions; a {agent} session fails to launch with it"
        )
    deadline = time.monotonic() + CAPACITY_WAIT_SECONDS
    while not (room := capacity())[0]:
        if time.monotonic() >= deadline:
            raise Fail(f"host over capacity for {CAPACITY_WAIT_SECONDS:.0f}s: {room[1]}")
        print(f"host over capacity, waiting: {room[1]}", file=sys.stderr)
        time.sleep(POLL_SECONDS * 6)
    if span := EMPTY_SPAN.search(brief):
        line = brief[: span.start()].count("\n") + 1
        raise Fail(
            f"brief line {line} has an empty `` span: a name lost in an unquoted heredoc; quote it (<<'EOF')"
        )
    full = (LEAD_PREAMBLE if top_level else PREAMBLE).format(
        report=report,
        role=f"Your role file is {role}; read it first.\n" if role else "",
    ) + brief
    # Omnigent labels a child by a model summary of this first message, not by its title, so the
    # title leads: a generic line gets labels like "Read Brief and Execute".
    if host_id and host_id != og.host_id:
        # A file here is not on that host; inline, a Claude lead may read it as pasted text and
        # ask its starter for a go-ahead.
        text = f"Work on {title}. Your brief:\n\n{full}"
    else:
        # The brief goes in a file beside the report and the message only names it: a child can
        # receive an inline brief as pasted text, which it will not take instructions from.
        brief_file = brief_of(report)
        brief_file.parent.mkdir(parents=True, exist_ok=True)
        brief_file.write_text(full)
        text = f"Work on {title}: read {brief_file} and do what it says."
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
                sid, error = (
                    og.create(agent, name, model, top_level, workspace, permission_mode, host_id),
                    None,
                )
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
        if top_level and subscribe:
            # A top-level lead has no parent to tell: the session starting it hears its turn ends
            # and prompts instead, revived for them if its runner was reaped.
            try:
                if not (me := own_id()):
                    raise Fail("this shell does not name its Omnigent session")
                og.subscribe(me, sid)
            except Fail as e:
                print(f"not subscribed to {sid} ({e}); follow it with watch", file=sys.stderr)
        try:
            if not (found and delivered(og, sid, text, 0)):  # a found one may hold the brief
                send_to_confirm(og, sid, text)
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
    ended: dict[str, float] = {}
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
        said = last_said(items)
        if counts() and settled(report, info, items, ended, sid) and counts():
            if status in RUNNING and not prompts_of(info):
                print(
                    f"session {sid} still reads {status}, but its report and history were quiet"
                    f" for {SETTLE_SECONDS:.0f}s: taking the report (a lost turn end)",
                    file=sys.stderr,
                )
            break
        prompts = prompts_of(info)
        if prompts and not counts():  # a report that counts is taken once settled
            raise Fail(
                f"session {sid} is blocked on a prompt: {'; '.join(prompts)}\nlast message: {said}"
            )
        # Idle with the brief last is a turn that ended with no output (codex forwarder maps an
        # empty completed turn to idle), unless it is the launch idle, the gap before a follow-up's
        # turn or a mid-turn idle: so only once the idle outlasted IDLE_GRACE_SECONDS.
        idle_since = (idle_since or time.monotonic()) if status not in RUNNING else None
        empty_turn = idle_since is not None and time.monotonic() - idle_since >= IDLE_GRACE_SECONDS
        turn_ended = status not in RUNNING and (
            status == "failed" or (last is not None and last.get("role") != "user") or empty_turn
        )
        if turn_ended and not counts():
            time.sleep(POLL_SECONDS)  # a report written just before the turn ended
        # a report that counts is final once settled, at a later look, within the deadline
        if turn_ended and not counts():
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
                send_to_confirm(og, sid, nudge)
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


def reap(
    og: Omnigent, sessions: list[str], parent: str | None = None, registry: Path | None = None
) -> tuple[list[str], bool]:
    """Finish (``Omnigent.archive``) each finished session of ``sessions`` and, with ``parent``, of
    its sub-agents: not running, no prompt waiting and no input pending. Return a line per session
    saying which: ``archived``, or kept and why, and whether any finish failed. Each session it
    finishes first leaves ``registry``: the caller is the one the supervisor would tell.

    An idle child whose report is still to come looks finished here too, so reap only once the
    reports are in; a child whose ``run`` died is re-attached with ``wait``, which finishes it."""
    lines, failed = [], False
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
        # ponytail: a supervisor that read the registry just before this drop can still post
        # `archived` once, and a finish that then fails leaves the session unfollowed; reap again.
        arm_quietly(registry, sid)
        try:
            og.archive(sid)
        except Fail as e:  # one refused finish leaves the rest to reap
            lines.append(f"{sid} {info.get('title') or ''}: finish failed: {e}")
            failed = True
            continue
        lines.append(f"{sid} {info.get('title') or ''}: archived ({status})")
    return lines, failed


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
    items = og.items(sid)
    last = last_message(items)
    head = f"{sid} {info.get('title') or ''}".rstrip()
    if queued := len(info.get("pending_inputs") or []):
        head += f" ({queued} queued input{'s' if queued > 1 else ''})"
    tail = f"\nlast message: {last_said(items)}"
    lid = last.get("id") if last else None
    if info.get("archived"):
        return ("archived",), f"{head}: archived{tail}"
    if status in RUNNING:
        idle_since.pop(sid, None)
    elif sid not in idle_since or idle_since[sid][0] != lid:  # (last message id, idle since)
        idle_since[sid] = (lid, time.monotonic() - (IDLE_GRACE_SECONDS if baseline else 0))
    if prompts := prompts_of(info):
        ids = ",".join(str(e.get("elicitation_id") or e) for e in info["pending_elicitations"])
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
    return ("running",), f"{head}: {status}{tail}"


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
    ending: dict[str, tuple[tuple, float]] = {}  # an end seen, not yet held TURN_END_SECONDS
    first = True
    while True:
        ids = list(dict.fromkeys(sessions + (og.children(parent) if parent else [])))
        changes = []
        for sid in ids:
            # idle at the start, empty turn or not, is the baseline, not a turn ending later
            key, line = observe(og, sid, idle_since, baseline=first)
            before = seen.get(sid, None if first else ("running",))
            # ponytail: a native Claude session reads idle while quiet mid-turn, and its last
            # message then is one from the middle of the turn, so an end counts once it holds.
            # A tool call quiet for longer still wakes early. Upgrade: Omnigent's session
            # subscriptions, which deliver only a confirmed turn end.
            if key[0] == "ended" and key != before and before is not None:
                held = ending.get(sid)
                if not held or held[0] != key:
                    held = ending[sid] = (key, time.monotonic())
                if time.monotonic() - held[1] < TURN_END_SECONDS:
                    continue
            ending.pop(sid, None)
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


def settled(report: Path, info: dict, items: list[dict], ended: dict[str, float], sid: str) -> bool:
    """Whether ``report``, one that counts, is final: the session has been out of its turn (not
    running, or blocked on a prompt nothing answers) at every look for ``TURN_END_SECONDS`` and the
    file unchanged as long, or the file and the history were both quiet for ``SETTLE_SECONDS``
    while it still reads running, a lost turn end. ``ended`` holds when each session was first seen
    out of its turn, the caller's across looks; a look that finds it running clears it. Until its
    turn ends a child can rewrite its report: a verifier revising its verdict, a lead writing
    progress there."""
    try:
        mtime = report.stat().st_mtime
    except FileNotFoundError:
        return False
    now = time.time()
    if str(info.get("status")) not in RUNNING or prompts_of(info):
        out = ended.setdefault(sid, now)
        return now - max(out, mtime) >= TURN_END_SECONDS
    ended.pop(sid, None)
    newest = max((float(i.get("created_at") or 0) for i in items), default=0.0)
    return now - max(mtime, newest) >= SETTLE_SECONDS


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
    ended: dict[str, float] | None = None,
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
    whose revive line did not go out, sent again at their next look; ``ended`` when each session
    was first seen out of its turn (``settled``), across looks.
    """
    # ponytail: compares the server's item clock with local time and file times, as send does; a
    # skewed server clock shifts the silence and the report's baseline by the skew.
    info, items = og.info(sid), og.items(sid)
    head = f"{sid} {info.get('title') or ''}".rstrip()
    resume = NUDGE.format(report=report)
    since, resent = instructed(items, resume)
    if resumed.get(sid, since) < since:  # sent before a newer instruction
        del resumed[sid]

    def counts() -> bool:
        return written(report, since) and (not verdict or bool(VERDICT.search(report.read_text())))

    if counts():
        if settled(report, info, items, {} if ended is None else ended, sid) and counts():
            return f"{head}: report written: {report}", since
        return "", since  # in its turn, or not out of it for long: it may rewrite the report
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
    ended: dict[str, float] = {}

    def say(line: str) -> None:
        print(line, flush=True)

    while True:
        for sid, report in owed.items():
            # wake the caller now: no other session's read, revive or resume first
            event, _ = check(og, sid, report, silent, resumed, unsent, say, ended=ended)
            if event:
                say(event)
                return event
        if time.monotonic() >= deadline:
            raise Fail(f"no event in {timeout:.0f}s: {', '.join(owed)}")
        time.sleep(POLL_SECONDS)


def follow(
    og: Omnigent,
    sid: str,
    idle_since: dict[str, tuple],
    told: dict,
    holding: dict[str, tuple[tuple, float]],
    quiet_seconds: float = FOLLOW_QUIET_SECONDS,
) -> tuple[str, tuple]:
    """One look at a followed lead: the line for its follower, else empty, and the lead's state as
    ``observe`` keys it. A prompt or a failure is news once per occurrence; a turn end naming
    ``DONE``, ``USER NEEDED`` or ``PARKED`` once it holds as ``watch`` counts an end; any other
    turn end only once the lead and its live children wrote nothing for ``quiet_seconds`` since it. Each is told once
    per message, so ``told`` keeps the ending last told per lead (kept while the runner flaps to
    running, since only a new message is a new ending) and the prompt or failure last told, and
    ``holding`` the end not yet held; all are the caller's across looks.
    """
    key, line = observe(og, sid, idle_since)
    if key[0] == "archived":
        return line, key
    if key[0] != "ended":
        holding.pop(sid, None)
        if key[0] == "running":
            told.pop(("occurrence", sid), None)
        elif told.get(("occurrence", sid)) != key:
            told[("occurrence", sid)] = key
            return line, key
        return "", key
    if told.get(sid) == key:
        return "", key
    held = holding.get(sid)
    if not held or held[0] != key:
        held = holding[sid] = (key, time.monotonic())
    if time.monotonic() - held[1] < TURN_END_SECONDS:
        return "", key
    items = og.items(sid)
    last = last_message(items)
    if not (last and last.get("role") != "user" and ENDING.search(text_of(last))):
        # ponytail: item and child clocks against the local one, as check does; the end is when
        # this loop first saw it, so a poll interval late. Upgrade: the turn's end time, if Omnigent
        # reports one.
        written = max((float(i.get("created_at") or 0) for i in items), default=0.0)
        ended_at = time.time() - (time.monotonic() - held[1])
        quiet = time.time() - max(written, og.active(sid), ended_at)
        if quiet < quiet_seconds:
            return "", key
        line = line.replace(": turn ended\n", f": turn ended, quiet {quiet:.0f}s\n", 1)
    told[sid] = key
    return line, key


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


def entry(line: str) -> tuple[str, Path, list[Path], bool, bool]:
    """A registry line: ``session=report``, then the session's brief files, each after a tab,
    whether its report is a verifier's (a ``verdict`` field, which ``run``, ``start`` and ``send``
    write for one) and whether it is a lead followed (a ``follow`` field, which ``start
    --top-level`` writes), whose report ``follow`` never reads."""
    head, *fields = line.split("\t")
    sid, report = pair(head)
    fields = [f.strip() for f in fields if f.strip()]
    marks = (VERDICT_FIELD, FOLLOW_FIELD)
    return (
        sid,
        report,
        [Path(f) for f in fields if f not in marks],
        VERDICT_FIELD in fields,
        FOLLOW_FIELD in fields,
    )


def registered(path: Path) -> tuple[dict[str, tuple[Path, list[Path], bool, bool]], list[str]]:
    """The registry's sessions with the reports they owe, their brief files, verdict and follow flags, the last line
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
    followed: bool = False,
) -> None:
    """Replace ``sid``'s line in the registry with ``sid=report``, ``briefs`` and, with ``verdict``
    or ``followed``, that field, or with ``report`` None drop it; unless ``unless()``, asked under the lock, is true. ``then`` (a follow-up's file)
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
        flag = [VERDICT_FIELD] * verdict + [FOLLOW_FIELD] * followed
        return rest + ["\t".join([f"{sid}={report}", *map(str, files), *flag])]

    edit_registry(path, edit)


def arm_quietly(
    path: Path | None,
    sid: str,
    report: Path | None = None,
    briefs: list[Path] | None = None,
    then: Path | None = None,
    verdict: bool = False,
    followed: bool = False,
) -> None:
    """``arm`` for a command with its own wait: a failure is a warning, since that wait still
    covers the session."""
    if path:
        try:
            arm(path, sid, report, briefs, then, verdict=verdict, followed=followed)
        except OSError as e:
            print(
                f"registry {path}: {sid} not {'armed' if report else 'disarmed'}: {e}",
                file=sys.stderr,
            )


class Recorded:
    """``og`` keeping the last ``info`` and ``items`` it returned per session, so the supervisor's
    state is built from what its look just read, with no second read."""

    def __init__(self, og: Omnigent) -> None:
        self.og, self.seen = og, {}

    def __getattr__(self, name: str) -> object:
        return getattr(self.og, name)

    def info(self, sid: str) -> dict:
        self.seen.setdefault(sid, {})["info"] = info = self.og.info(sid)
        return info

    def items(self, sid: str) -> list[dict]:
        self.seen.setdefault(sid, {})["items"] = items = self.og.items(sid)
        return items


def fresh_state() -> dict:
    """An empty ``state.json``. ``intents``, ``attention``, ``pending_posts`` and ``rate`` are kept
    for the routing that fills them."""
    return {
        "schema": STATE_SCHEMA,
        "written_at": 0,
        "leads": {},
        "settled": {},
        "intents": [],
        "attention": [],
        "pending_posts": [],
        "rate": {"next_post_at": 0, "model_calls": {"hour": 0, "count": 0}},
    }


def load_state(path: Path) -> dict:
    """``path``'s state, else a fresh one: missing, unreadable or of another schema, with a warning
    for the last two, since a fresh state only re-posts what the old one had settled."""
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        return fresh_state()
    except (OSError, ValueError) as e:
        print(f"{path}: {type(e).__name__}: {e}; starting fresh", file=sys.stderr)
        return fresh_state()
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        print(f"{path}: not {STATE_SCHEMA}; starting fresh", file=sys.stderr)
        return fresh_state()
    return {**fresh_state(), **state}


def write_state(path: Path, state: dict) -> None:
    """Write ``state`` atomically: a temp file in the same directory, then a rename, so a reader
    sees the old file or the new one, never half of one."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n")
    os.replace(tmp, path)


def lead_status(info: dict, items: list[dict]) -> dict:
    """A session's state (``running``, ``idle``, ``blocked``, ``failed``, ``archived``), its last
    message's ending and first line, and what it waits on: ``parked``, the wait its ``STILL
    WORKING`` names, else ``unknown``."""
    said = [i for i in items if i.get("type") == "message" and i.get("role") == "assistant"]
    text = text_of(said[-1]).strip() if said else ""
    e = info.get("last_task_error") or {}
    if info.get("archived"):
        state = "archived"
    elif prompts_of(info):
        state = "blocked"
    elif str(info.get("status")) == "failed":
        state = "failed"
    else:
        state = "running" if str(info.get("status")) in RUNNING else "idle"
    ending = m.group(1) if (m := ENDING.search(text)) else None
    wait = "parked" if ending == "PARKED" else "unknown"
    if wait == "unknown" and (m := WAIT.search(text)):
        wait = m.group(1) if m.group(1) == "CI" else m.group(1).lower()
    error = e.get("message") or e.get("title") or "(no error recorded)"
    return {
        "state": state,
        "error": error if state == "failed" else None,
        "ending": ending,
        "wait": wait,
        "last_line": text.splitlines()[0][:200] if text else "",
    }


def status_line(lead: dict) -> str:
    """A lead's ``status.line`` label: its state in one short line, under 200 characters, since
    Omnigent cuts a label value to its first 256 without an error."""
    if lead["state"] == "blocked":
        line = "blocked on a prompt"
    elif lead["state"] == "failed":
        line = f"failed: {lead['error']}"
    else:
        line = "running" if lead["state"] == "running" else "turn ended"
        if lead["wait"] not in ("unknown", "parked"):
            line += f" · waits on {lead['wait']}"
        if lead["state"] != "running" and lead["last_line"]:
            line += f": {lead['last_line']}"
    return line if len(line) < 200 else line[:198] + "…"


def supervise_registry(
    og: Omnigent,
    registry: Path,
    notify: str | None = None,
    silent: float = 1800.0,
    timeout: float = 3 * 3600,
) -> NoReturn:
    """Run until stopped, checking each session ``registry`` lists as ``supervise`` does, re-read
    each poll. Every line goes to stdout with the local time and, with ``notify``, into that
    session as ``Supervisor: <line>``. A line marked ``follow`` is a lead followed, not owed a
    report: ``follow`` says when it is news, a lead with no progress past its deadline raises a
    ``deadline`` event, and only ``archived`` drops its line. Lines wait in order until posted, and each poll posts them
    first, stopping at the first failure. A terminal event drops the session's line once its own
    line is posted, and a session whose terminal line waits is not checked again. The drop keeps
    the line when the session was instructed since the event's instruction: the caller armed it
    again for a newer brief, once that brief was in the history. An error is
    logged to stderr, once until it clears, and never stops the loop; so is ``timeout`` with no
    event.

    Each poll writes ``<registry>.state.json`` (``fresh_state``, one entry per registry session)
    and labels each session with its ``status.line`` and ``status.at``; every event posted (or
    printed, without ``notify``) is settled there by its id and appended to
    ``<registry>.events.jsonl``. The state is loaded on start, so a restart re-raises no settled
    event and keeps each lead's ``progress_at``, budgets and last labels.
    """
    rec = Recorded(og)
    state_path = registry.with_suffix(".state.json")
    events_path = registry.with_suffix(".events.jsonl")
    state = load_state(state_path)
    hosts: dict[str, str] | None = None  # ponytail: read once; a host added later shows its id
    ended: dict[str, float] = {}
    resumed: dict[str, float] = {}
    idle_since: dict[str, tuple] = {}  # followed leads, as ``follow`` keeps them
    told: dict = {}
    holding: dict[str, tuple[tuple, float]] = {}
    unsent: set[str] = set()  # ponytail: in memory, so a restart loses a revive line still unsent
    logged: dict[object, str] = {}  # the error last logged per session (or registry, post, drop)
    # Each line not yet posted (None once it is), with what a terminal line drops (its session,
    # report and the instruction its check measured from), its event id, session and kind.
    # ponytail: in memory, so a restart loses the revive and resume lines waiting in it; a terminal
    # event keeps its registry line until posted, and the restarted supervisor finds it again.
    outbox: list[tuple[str | None, tuple[str, Path, float] | None, str, str, str]] = []
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

    def settle(eid: str, sid: str, kind: str, line: str) -> None:
        kept = state["settled"].setdefault(sid, [])
        kept.append(eid)
        del kept[:-SETTLED_KEPT]
        how = "posted" if notify else "printed"
        event = {"at": int(time.time()), "id": eid, "session": sid, "kind": kind, "line": line}
        try:
            with open(events_path, "a") as f:
                f.write(json.dumps({**event, "settled": how}) + "\n")
        except OSError as e:
            log("events", f"{events_path}: {reason(e)}")
        else:
            log("events", None)

    def flush() -> None:
        while outbox:
            line, event, eid, sid, kind = outbox[0]
            if line is not None:
                if not post(line):
                    return
                settle(eid, sid, kind, line)
            if event and not drop(*event):
                outbox[0] = (None, event, eid, sid, kind)  # posted; only the drop is retried
                return
            outbox.pop(0)

    def say(
        line: str,
        sid: str,
        eid: str = "",
        kind: str = "notice",
        event: tuple[str, Path, float] | None = None,
    ) -> None:
        """Print and post ``line``, unless its event ``eid`` is settled (then only drop ``event``'s
        line) or already waits to be posted."""
        if any(o[2] == eid for o in outbox):
            return
        if eid in state["settled"].get(sid, ()):
            if event:
                outbox.append((None, event, eid, sid, kind))
                flush()
            return
        print(stamp(line), flush=True)
        outbox.append((line, event, eid or f"notice:{sid}:{time.time():.0f}", sid, kind))
        flush()

    def track(sid: str, report: Path, briefs: list[Path], followed: bool) -> dict:
        """``sid``'s state entry, updated from what its look just read."""
        nonlocal hosts
        seen = rec.seen.pop(sid, {})
        lead = state["leads"].setdefault(
            sid,
            {"progress_at": time.time(), "nudges": 0, "revives": 0, "waits_on": [], "label": {}},
        )
        if "info" not in seen or "items" not in seen:
            return lead
        info, items = seen["info"], seen["items"]
        if hosts is None:
            try:
                hosts = og.hosts()
            except Exception as e:  # noqa: BLE001 - a host shows as its id meanwhile
                log("hosts", f"hosts: {reason(e)}")
            else:
                log("hosts", None)
        host = str(info.get("host_id") or "")
        lead.update(
            title=info.get("title") or "",
            host=(hosts or {}).get(host, host),
            report=str(report),
            briefs=[str(b) for b in briefs],
            follow=followed,
            **lead_status(info, items),
        )
        # its own history counts, not a message to it: a nudge is no progress
        own = [
            float(i.get("created_at") or 0)
            for i in items
            if not from_user(i) and i.get("type") != "resource_event"
        ]
        lead["progress_at"] = max([lead["progress_at"], *own])
        return lead

    def label(sid: str, lead: dict) -> None:
        """Write ``sid``'s status labels when the line changed or the last write is
        ``LABEL_SECONDS`` old, so a quiet poll writes nothing."""
        if lead.get("state") in (None, "archived"):
            return
        line, now = status_line(lead), time.time()
        last = lead["label"]
        if line == last.get("line") and now - float(last.get("at") or 0) < LABEL_SECONDS:
            return
        at = str(int(now))
        try:
            og.label(sid, {"status.line": line, "status.at": at})
        except Exception as e:  # noqa: BLE001 - display only; written again next poll
            log(("label", sid), f"{sid}: labels not written: {reason(e)}")
            return
        log(("label", sid), None)
        lead["label"] = {"line": line, "at": at}

    def overdue(sid: str, lead: dict) -> None:
        """Raise a followed lead's ``deadline`` events: ``DEADLINE_SECONDS`` with no progress, and
        for a lead whose wait is unknown and that was nudged, ``NUDGED_SECONDS`` more. Each is one
        event per ``progress_at``, so new progress starts a new chain."""
        if lead["state"] in ("blocked", "failed", "archived") or (
            lead["state"] == "idle" and lead["ending"]
        ):
            return  # its follower was told and it waits on them, or a parked one waits on capacity
        if time.time() - lead["progress_at"] < DEADLINE_SECONDS:
            return
        lead["progress_at"] = max(lead["progress_at"], og.active(sid))  # read only once due
        quiet = time.time() - lead["progress_at"]
        steps = [(DEADLINE_SECONDS, "")]
        if lead["wait"] == "unknown" and lead["nudges"]:
            steps.append((DEADLINE_SECONDS + NUDGED_SECONDS, ":nudged"))
        for after, nudged in steps:
            if quiet >= after:
                head = f"{sid} {lead['title']}".rstrip()
                why = f"no progress {quiet / 60:.0f}m{' after a nudge' * bool(nudged)}"
                line = f"{head}: {why} ({lead['wait']})\nlast message: {lead['last_line']}"
                say(line, sid, f"deadline:{sid}:{lead['progress_at']:.0f}{nudged}", "deadline")

    while True:
        flush()
        try:
            owed, bad = registered(registry)
        except Exception as e:  # noqa: BLE001 - never fatal
            owed, bad, read = {}, [], False
            log("registry", f"{registry}: {reason(e)}")
        else:
            read = True
            log("registry", None)
        for line in bad:
            log(("line", line), f"{registry}: {line!r}: expected <session>=<report>; skipped")
        for sid, (report, briefs, verdict, followed) in owed.items():
            if any(o[1] and o[1][0] == sid for o in outbox):
                continue  # its event is found; it waits to be posted
            try:
                if followed:  # never revived or nudged: its lead owes no report
                    event, key = follow(rec, sid, idle_since, told, holding)
                    lead = track(sid, report, briefs, followed)
                    since, eid, kind = time.time(), ":".join((key[0], sid, *key[1:])), key[0]
                    if kind != "archived":
                        log(sid, None)
                        label(sid, lead)
                        if event:
                            window = time.monotonic()
                            say(event, sid, eid, kind)
                        overdue(sid, lead)
                        continue
                else:

                    def notice(line: str, sid: str = sid) -> None:
                        say(line, sid)

                    event, since = check(
                        rec, sid, report, silent, resumed, unsent, notice, briefs, verdict, ended
                    )
                    label(sid, track(sid, report, briefs, followed))
                    eid, kind = f"terminal:{sid}:{since}", "terminal"
            except Exception as e:  # noqa: BLE001 - one session's error skips no other
                log(sid, f"{sid}: {reason(e)}")
                continue
            log(sid, None)
            if not event:
                continue
            window = time.monotonic()
            say(event, sid, eid, kind, (sid, report, since))
        if read:  # a session gone from the registry leaves the state with it
            for part in ("leads", "settled"):
                state[part] = {s: v for s, v in state[part].items() if s in owed}
        state["written_at"] = int(time.time())
        try:
            write_state(state_path, state)
        except OSError as e:
            log("state", f"{state_path}: {reason(e)}")
        else:
            log("state", None)
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
        p = sub.add_parser(
            name,
            description="start a child and wait for its report in one process; a lead (--top-level)"
            " uses start, then watch"
            if name == "run"
            else "start a child, or a lead with --top-level, and return once its brief landed",
        )
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
            "--permission-mode",
            help="a claude session's mode, as claude --permission-mode takes it (default: $OMNIGENT_PERMISSION_MODE,"
            " else the harness default); codex sessions take none",
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
        p.add_argument(
            "--workspace",
            type=Path,
            help="the child's workspace (default: this directory); the report must be inside it",
        )
        p.add_argument(
            "--host",
            help="with --top-level, the Omnigent host (name or id) to start the lead on",
        )
    p = sub.add_parser("send")
    p.add_argument("session")
    p.add_argument("brief", type=Path, help="file with the answer or follow-up")
    p.add_argument("report", type=Path)
    p.add_argument("--confirm-seconds", type=float, default=60.0)
    p = sub.add_parser("relay")
    p.add_argument("session")
    p.add_argument("message", type=Path, help="file with the message; it owes no report")
    p.add_argument("--confirm-seconds", type=float, default=60.0)
    sub.add_parser("capacity", description="exit 0 when this host has room for another session")
    p = sub.add_parser("approve")
    p.add_argument("session")
    p.add_argument("--decline", action="store_true", help="decline instead of accept")
    p = sub.add_parser("status")
    p.add_argument("sessions", nargs="+")
    p = sub.add_parser("report", description="print a file of a session's workspace or host")
    p.add_argument("session")
    p.add_argument("path", nargs="?", help="default: the report in the session's registry line")
    p.add_argument(
        "--registry", type=Path, default=os.environ.get("OMNIGENT_SUPERVISE_REGISTRY") or None
    )
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
        if p.prog.split()[-1] not in ("start", "reap", "relay", "approve", "status"):
            p.add_argument("--timeout", type=float, default=3 * 3600, help="seconds (default 3h)")
        if p.prog.split()[-1] in ("run", "start", "send", "wait", "reap"):
            p.add_argument(
                "--registry",
                type=Path,
                default=os.environ.get("OMNIGENT_SUPERVISE_REGISTRY") or None,
                help="supervisor registry to arm with session=report, or for reap to drop each"
                " finished session from (default: $OMNIGENT_SUPERVISE_REGISTRY)",
            )
    args = ap.parse_args(argv)
    sid, registry = getattr(args, "session", None), getattr(args, "registry", None)
    try:
        owed = {s: r.resolve() for s, r in map(pair, getattr(args, "owed", []))}
        if args.cmd == "supervise" and not (owed or args.registry):
            raise Fail("supervise needs <session>=<report> pairs or --registry")
        if args.cmd == "capacity":
            ok, line = capacity()
            print(line)
            return 0 if ok else 1
        if args.cmd == "report" and not args.path:
            line = registry and registered(registry)[0].get(sid)
            if not line:
                usage = Fail(
                    f"report {sid} needs a path: no --registry / $OMNIGENT_SUPERVISE_REGISTRY line for it"
                )
                usage.code = 2  # argparse's usage exit
                raise usage
            args.path = str(line[0])
        og = Omnigent()
        if args.cmd == "report":
            print(og.read_file(sid, args.path))
            return 0
        if args.cmd == "relay":
            print(relay(og, args.session, args.message.read_text(), args.confirm_seconds))
            return 0
        if args.cmd == "approve":
            lines, failed = approve(og, args.session, args.decline)
            print("\n".join(lines))
            return 1 if failed else 0
        if args.cmd == "status":
            # a snapshot: an idle look reads as a turn ended, which a notice has confirmed
            print("\n".join(observe(og, s, {}, baseline=True)[1] for s in args.sessions))
            return 0
        if args.cmd == "watch":
            if not args.sessions and not args.children:
                raise Fail("watch needs a session or --children <parent>")
            print("\n".join(watch(og, args.sessions, args.children, args.timeout)))
            return 0
        if args.cmd == "reap":
            if not args.sessions and not args.children:
                raise Fail("reap needs a session or --children <parent>")
            lines, failed = reap(og, args.sessions, args.children, args.registry)
            print("\n".join(lines))
            return 1 if failed else 0
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
        host = og.host(args.host) if getattr(args, "host", None) else og.host_id
        remote = host != og.host_id  # paths on another host: neither resolved nor checked here
        report = args.report if remote else args.report.resolve()
        if args.cmd != "send" and args.host and not args.top_level:
            raise Fail("--host needs --top-level: Omnigent runs a child on its parent's runner")
        if remote and not (
            args.workspace and args.workspace.is_absolute() and report.is_absolute()
        ):
            raise Fail(
                f"--host {args.host} is another host: --workspace and the report are absolute paths there"
            )
        if args.cmd == "send":  # a live session keeps its own workspace, wherever this runs
            workspace = Path(og.info(args.session).get("workspace") or Path.cwd()).resolve()
        else:
            workspace = getattr(args, "workspace", None) or Path.cwd()
            if not remote:
                workspace = workspace.resolve()
            if not remote and not workspace.is_dir():
                raise Fail(f"--workspace {workspace} is not a directory")
        # A new child's workspace is this directory unless --workspace names one; outside it a Codex
        # sandbox refuses the write and Claude Code prompts for the read (denies it in auto mode),
        # which nobody answers. The child also saves its repro files beside the report.
        if not remote and not report.is_relative_to(workspace):
            raise Fail(
                f"{report} is outside the child's workspace {workspace}; use tmp/loop/ in the worktree"
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
        if args.cmd == "start" and not remote and report.exists():
            raise Fail(
                f"{report} already exists; wait would return at once (use run, or a new path)"
            )
        # The file's own mtime, never the clock: the kernel stamps files from a coarse clock that
        # lags time.time_ns() by up to a tick, so a report written that soon would read as older.
        launched = report.stat().st_mtime_ns if not remote and report.exists() else None
        if not remote:  # a remote lead's report is written on its host, never read here
            report.parent.mkdir(parents=True, exist_ok=True)
        sid, survivors = start(
            og,
            args.agent,
            args.title,
            brief,
            report,
            args.role,
            args.confirm_seconds,
            model=args.model,
            permission_mode=args.permission_mode,
            top_level=args.top_level,
            workspace=str(workspace),
            host_id=host,
            subscribe=not (registry and args.top_level),  # the supervisor follows it instead
        )
        if not remote or (registry and args.top_level):
            arm_quietly(
                registry,
                sid,
                report,
                [brief_of(report)] if not remote else None,
                verdict=verifier,
                followed=args.top_level,
            )
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
