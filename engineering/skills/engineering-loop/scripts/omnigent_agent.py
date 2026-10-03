#!/usr/bin/env python3
"""Start an engineering-loop agent through Omnigent and wait for its report.

    python3 scripts/omnigent_agent.py run <claude|codex> <title> <brief-file> <report-path> [--role FILE]
    python3 scripts/omnigent_agent.py send <session> <brief-file> <report-path>

``run`` is ``start`` then ``wait`` in one process: exit 0 prints the report path (a verifier's
only once it has its ``SATISFIED:`` line; ``send`` and ``wait`` take ``--verdict`` for that); exit 3 prints the
path of a question the child wrote (``<report>.question``) instead of a report; exit 1 prints the
reason and the child's last message. A coordinator launches it as one background command, so its
exit is the wake. ``send`` answers that question in the same session, then waits the same way; it
refuses (exit 4) a session whose runner Omnigent reaped after its idle timeout, since a send there
answers ``queued`` and never arrives: start a fresh run whose brief carries the question and answer.

Uses the local Omnigent server's HTTP API (the ``omnigent`` CLI has no session create/send):
``POST /v1/sessions`` (created empty: a child created with queued ``initial_items`` can stay idle
for good), ``POST /v1/sessions/{id}/events`` with a ``message`` event, and
``GET /v1/sessions/{id}/items`` as the history. A send answers ``queued``/``launching`` even when
the child never gets it, so the start counts only once the one line naming the brief file is a
user message in the history. Server and host come from ``~/.omnigent/config.yaml``; the bearer token from Omnigent's
own ``cli_auth`` (run in the omnigent tool venv), which refreshes and persists it. Stdlib only.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AGENTS = {"claude": "claude-native-ui", "codex": "codex-native-ui"}
CONFIG = Path.home() / ".omnigent" / "config.yaml"
AUTH_TOKENS = Path.home() / ".omnigent" / "auth_tokens.json"
RUNNING = {"running", "launching", "queued", "starting"}
POLL_SECONDS = 5.0
TOKEN_SECONDS = 30.0
HTTP_SECONDS = 30.0
IDLE_GRACE_SECONDS = 30.0  # idle with the brief last: a turn that ended with no output
VERDICT = re.compile(r"^SATISFIED: (yes|no)\b", re.MULTILINE)  # a verifier report's last line
ASKED, GONE = 3, 4  # exit codes: the child asked a question; send found no live runner

PREAMBLE = """\
The owner authorized this task; do it now, without asking for a go-ahead. This file is your brief.
{role}Run every long command in the foreground (timeout up to 600000): a background command's completion never wakes you, so a turn that ends "waiting" never reports.
Write your report to {report}.
Never address the owner. If you need a decision the brief, the spec and the repo do not settle, write the question to {report}.question, reply with only that path, and stop: the answer comes as your next message.
When done, reply with only the report path.

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
            raise Fail(f"{CONFIG} lacks host.host_id, or no server: neither `server:` there nor one login in {AUTH_TOKENS}")
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
        for attempt in (0, 1):
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
                if e.code == 401 and attempt == 0:
                    self._token = ""  # expired mid-run: refresh once
                    continue
                raise Fail(
                    f"{method} {path}: HTTP {e.code} {e.reason}"
                ) from e  # never read the body: it can stall past the timeout
            except URLError as e:
                raise Fail(f"{method} {path}: {e.reason}") from e
            except (
                OSError,
                http.client.HTTPException,
            ) as e:  # socket timeout, reset, bad status line
                raise Fail(f"{method} {path}: {type(e).__name__}: {e}") from e
        raise AssertionError("unreachable")

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

    def create(self, agent: str, title: str, model: str | None = None) -> str:
        body = {
            "agent_id": self.agent_id(AGENTS[agent]),
            "title": title,
            "host_id": self.host_id,
            "workspace": os.getcwd(),
        }
        # Filed under the repo's project, when one exists, so spawned sessions don't crowd the top level.
        if project := self.project_id(os.environ.get("OMNIGENT_PROJECT") or repo_name()):
            body["project_id"] = project
        # A sub-agent of the runner's primary session (the coordinator, also when a child runs
        # this): hidden from the owner's sidebar and unread badge, and gone with it. Top level
        # when not run from an Omnigent session.
        if parent := os.environ.get("OMNIGENT_RUNNER_PRIMARY_SESSION_ID"):
            body["parent_session_id"] = parent
        if model := model or os.environ.get(f"OMNIGENT_MODEL_{agent.upper()}"):
            body["model_override"] = model
        return str(self.call("POST", "/v1/sessions", body)["id"])

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

    def delete(self, sid: str) -> None:
        self.call("DELETE", f"/v1/sessions/{sid}")


def text_of(item: dict) -> str:
    return "".join(c.get("text", "") for c in item.get("content") or [] if isinstance(c, dict))


def last_message(items: list[dict]) -> dict | None:
    return next((i for i in reversed(items) if i.get("type") == "message"), None)


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


def send(og: Omnigent, sid: str, brief: str, report: Path, confirm_seconds: float) -> None:
    """Send a follow-up (an answer) to a session whose runner is still up, and confirm it arrived."""
    if not og.info(sid).get("runner_online", True):
        raise Gone(f"session {sid} has no live runner; start a fresh run instead")
    old = frozenset(str(i.get("id")) for i in og.items(sid))
    og.send(sid, brief)
    if not delivered(og, sid, brief, confirm_seconds, old):
        raise Gone(
            f"session {sid}: message not in history after {confirm_seconds:.0f}s; start a fresh run instead"
        )
    question_of(report).unlink(missing_ok=True)  # kept until the answer lands, for the fresh run


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
) -> tuple[str, list[str]]:
    """Return the confirmed session id and any abandoned sessions whose delete failed."""
    # The brief goes in a file beside the report and the message only names it: a child can receive
    # an inline brief as pasted text, which it will not take instructions from.
    brief_file = report.with_name(report.name + ".brief")
    brief_file.parent.mkdir(parents=True, exist_ok=True)
    brief_file.write_text(
        PREAMBLE.format(
            report=report,
            role=f"Your role file is {role}; read it first.\n" if role else "",
        )
        + brief
    )
    text = f"Your brief from the coordinator is the file {brief_file}. Read it now and do what it says."
    reasons: list[str] = []
    survivors: list[str] = []

    def abandon(sid: str) -> None:
        try:
            og.delete(sid)
        except Fail as e:
            survivors.append(sid)
            print(f"abandoned session {sid} survives: {e}", file=sys.stderr)

    def failed(reason: str) -> Fail:
        left = f"; abandoned sessions survive: {', '.join(survivors)}" if survivors else ""
        return Fail(reason + left)

    for n in range(attempts):
        # a surviving abandoned child keeps its title, and Omnigent refuses a sibling with the same one
        sid = og.create(agent, title if n == 0 else f"{title}-r{n + 1}", model)
        try:
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
    og: Omnigent, sid: str, report: Path, timeout: float = 3 * 3600, verdict: bool = False
) -> str:
    """Return the report path, or raise with the child's last message once it cannot deliver one.

    With ``verdict`` (a verifier), the report counts only once it has a ``SATISFIED:`` line: a
    verifier can write its findings before its gate run ends. Raises ``Asked`` with the question's
    path when the child wrote one instead. Fails when the turn ends without a report, when the
    child is blocked on an approval or input prompt (nothing answers it), or after ``timeout``
    seconds.
    """
    deadline = time.monotonic() + timeout
    seen_running, idle_since = False, None
    question = question_of(report)
    missing = f"a verdict in {report}" if verdict else str(report)

    def done() -> bool:
        return report.exists() and (not verdict or bool(VERDICT.search(report.read_text())))

    while not done():
        if question.exists():
            raise Asked(str(question))
        info = og.info(sid)
        status = str(info.get("status"))
        last = last_message(og.items(sid))
        said = text_of(last) if last else "(none)"
        prompts = [
            str((e.get("params") or {}).get("message") or e)
            for e in info.get("pending_elicitations") or []
        ]
        if prompts:
            raise Fail(
                f"session {sid} is blocked on a prompt: {'; '.join(prompts)}\nlast message: {said}"
            )
        seen_running |= status in RUNNING
        # Idle with the brief last is a turn that ended with no output (codex forwarder maps an
        # empty completed turn to idle), unless it is the launch idle: so only once this wait saw
        # the session run, or the idle outlasted IDLE_GRACE_SECONDS.
        idle_since = (idle_since or time.monotonic()) if status not in RUNNING else None
        empty_turn = seen_running or (
            idle_since is not None and time.monotonic() - idle_since >= IDLE_GRACE_SECONDS
        )
        if status not in RUNNING and (
            status == "failed" or (last is not None and last.get("role") != "user") or empty_turn
        ):
            time.sleep(POLL_SECONDS)  # a report written just before the turn ended
            if done():
                break
            if question.exists():
                raise Asked(str(question))
            raise Fail(f"session {sid} ended ({status}) without {missing}\nlast message: {said}")
        if time.monotonic() >= deadline:
            raise Fail(
                f"session {sid} gave no {'verdict' if verdict else 'report'} after {timeout:.0f}s\nlast message: {said}"
            )
        time.sleep(POLL_SECONDS)
    return str(report)


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
    p = sub.add_parser("send")
    p.add_argument("session")
    p.add_argument("brief", type=Path, help="file with the answer or follow-up")
    p.add_argument("report", type=Path)
    p.add_argument("--confirm-seconds", type=float, default=60.0)
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
        if p.prog.split()[-1] != "start":
            p.add_argument("--timeout", type=float, default=3 * 3600, help="seconds (default 3h)")
    args = ap.parse_args(argv)
    try:
        og = Omnigent()
        if args.cmd == "wait":
            print(wait(og, args.session, args.report.resolve(), args.timeout, args.verdict))
            return 0
        report = args.report.resolve()
        # The child's workspace is this directory; its Read of a file outside it raises an approval
        # prompt nobody answers, and it saves its repro files beside the report.
        if not report.is_relative_to(Path.cwd()):
            raise Fail(
                f"{report} is outside the child's workspace {Path.cwd()}; use tmp/loop/ in the worktree"
            )
        if args.cmd == "send":
            send(og, args.session, args.brief.read_text(), report, args.confirm_seconds)
            print(wait(og, args.session, report, args.timeout, args.verdict))
            return 0
        brief = args.brief.read_text()
        verifier = bool(args.role and "verifier" in args.role)
        if args.author == args.agent and verifier and not args.same_family:
            raise Fail(
                f"{args.agent} would verify {args.author}-written code; pass --same-family to allow it"
            )
        if report.exists():
            raise Fail(f"{report} already exists; wait would return at once")
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
        )
        print(sid, flush=True)
        if args.cmd == "run":
            print(wait(og, sid, report, args.timeout, verifier))
        if survivors:
            raise Fail(f"abandoned sessions survive: {', '.join(survivors)}")
        return 0
    except Fail as e:
        print(e, file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
