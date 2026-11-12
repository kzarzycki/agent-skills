#!/usr/bin/env python3
"""Run a Codex verifier inside a Claude cloud session's VM, on a login the host seeds once (SKILL.md, Cloud worker).

On the host that starts cloud sessions:

    python3 scripts/cloud_verifier.py login            # once: a device login into a Codex home kept only for seeding
    python3 scripts/cloud_verifier.py seed [--env ID]  # before starting a session whose VM will verify

In the VM, from the checkout:

    python3 <skill>/scripts/cloud_verifier.py verify --pr N --brief FILE [--model M] [--effort E]

`login` runs `codex login --device-auth` with CODEX_HOME at the seed home (`$CODEX_CLOUD_HOME`, else
`~/.codex-cloud`), so the host's own Codex login is never copied: one login used from two machines breaks when
either refreshes it.

`seed` keeps that login fresh and stores a copy of it in the cloud environment, as the variable CODEX_AUTH_JSON
(base64). When the access token has under `--min-days` left (default 5 of its 10), it refreshes the login the way
the Codex CLI does and writes the new tokens back to the seed home. The stored copy carries no refresh token, so no
VM can rotate the seed's, and a VM whose copy has expired fails with a 401 instead of breaking the login for the
others. It also adds OpenAI's hosts to the environment's allowed hosts. The environment is `--env`, else the
checkout's `.claude/settings.local.json` pin (`remote.defaultEnvironmentId`), read from the main checkout when run
in a worktree. A variable is set when a session starts, so seed before starting the session. Exit 2 means the owner
has to run `login` again (no seed login, or its refresh token was refused).

`verify` installs the Codex CLI when the VM lacks it, writes the seeded login to `~/.codex/auth.json` when Codex is
not logged in, and refuses a tree with uncommitted changes, since a verifier reviews a pushed head only (files in the
report's own folder pass: a fresh clone ignores `tmp/loop/` only where the project's own .gitignore does). It checks
out the PR's head detached, so nothing the verifier does moves the worker's branch, runs `codex exec` on the brief with Codex's own sandbox
off (the VM is the sandbox, and the verifier needs Docker and the network), under an `AGENT_SIGNATURE=` line
naming the model and effort it was given, and posts the report as one comment on
the PR through REST, unchanged, printing the comment's URL as its last line. The report is the file the brief's
`- Report: <path>` line names (approvals.py brief), else Codex's final message; one without a `SATISFIED:` line is
not posted, and a report or question file counts only when this pass wrote it, so an earlier pass's file is never
posted again and none is deleted. A verifier that stops on a question (`<report>.question`, verifier.md) gets that file posted
instead, headed `## Verifier question`. It returns the checkout to where it was. When the verifier left
a change outside that folder, the script deletes and restores nothing, since git can't say which leftover hides an
older file: the checkout stays as it is, the changes are named on stderr, and the exit is 4.
Neither checkout replaces an ignored file: where one is in the way, the first is refused (exit 2) and the second
leaves the checkout as it is (exit 4).
Where the checkout of the PR's head itself shows changes (a submodule the PR moved, a file only the worker's branch
ignores), the pass is refused and the checkout returned (exit 2), since an edit to one of those could not be told
apart. A change is what `git status` shows: an edit to a file git ignores can't be seen and is not reported.
Exit 0 report posted, 1 the pass failed (Codex failed, wrote no report, or the comment could not be posted), 2 a
precondition is missing and nothing was touched, 3 a question posted, 4 the checkout needs a look, whatever else the
pass did (a posted comment's URL is still printed).
The carrier session runs it detached and polls, since a foreground command in the VM stops at 10 minutes.

Standard library only, plus `gh`, `git` and `npm` in the VM and `codex` and the Claude Code login on the host.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

VAR = "CODEX_AUTH_JSON"
HOSTS = ["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com"]
# ponytail: the refresh call mirrors the Codex CLI's own (codex-rs/login/src/auth/manager.rs: the endpoint, the
# CLI's public client id, a JSON body), because the CLI only refreshes a token within 5 minutes of expiry and a
# seed has to refresh days earlier. If OpenAI changes the call, `seed` exits 2 and `login` starts over.
REFRESH_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CLAUDE_API = os.environ.get("CLAUDE_CLOUD_API_BASE", "https://api.anthropic.com")


class Refused(Exception):
    """A precondition is missing; the message says what to do."""


def seed_home() -> Path:
    return Path(os.environ.get("CODEX_CLOUD_HOME") or Path.home() / ".codex-cloud")


def run(*cmd: str, check: bool = True, **kw) -> subprocess.CompletedProcess:
    done = subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)
    if check and done.returncode:
        raise Refused(
            f"`{' '.join(cmd)}` exited {done.returncode}: {(done.stderr or done.stdout).strip()[-600:]}"
        )
    return done


def expires_at(access_token: str) -> float:
    """The `exp` claim of a JWT, in epoch seconds."""
    payload = access_token.split(".")[1]
    return float(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"])


def reader_copy(auth: dict) -> dict:
    """The login as a VM gets it: the same tokens without the refresh token."""
    return {**auth, "tokens": {**auth["tokens"], "refresh_token": ""}}


def post_json(url: str, body: dict | None, headers: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)


# ── host: login and seed ─────────────────────────────────────────────────────────────────────────────────────────


def login() -> int:
    home = seed_home()
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    return subprocess.run(
        ["codex", "login", "--device-auth"],
        env={**os.environ, "CODEX_HOME": str(home)},
        check=False,
    ).returncode


def refreshed(auth: dict) -> dict:
    """The login with new tokens from OpenAI's auth service, as the Codex CLI's refresh makes them."""
    try:
        new = post_json(
            REFRESH_URL,
            {
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": auth["tokens"]["refresh_token"],
            },
            {},
        )
    except urllib.error.HTTPError as e:
        # the body may echo credential material: report the status and the error code only
        try:
            code = json.loads(e.read()).get("error")
        except ValueError:
            code = None
        code = code.get("code") if isinstance(code, dict) else code
        raise Refused(
            f"the seed login's refresh was refused (HTTP {e.code}, {code}): run `cloud_verifier.py login`"
        )
    tokens = {**auth["tokens"], **{k: v for k, v in new.items() if k in auth["tokens"] and v}}
    return {
        **auth,
        "tokens": tokens,
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
    }


def claude_headers() -> dict:
    """Headers for Claude's environment API, on the Claude Code login this host already has."""
    raw = ""
    if sys.platform == "darwin":
        user = os.environ.get("USER") or run("id", "-un").stdout.strip()
        raw = run(
            "security",
            "find-generic-password",
            "-a",
            user,
            "-s",
            "Claude Code-credentials",
            "-w",
            check=False,
        ).stdout
    if not raw and (path := Path.home() / ".claude" / ".credentials.json").exists():
        raw = path.read_text()
    if not raw:
        raise Refused("no Claude Code login on this host: run `claude auth login`")
    oauth = json.loads(raw)["claudeAiOauth"]
    if oauth.get("expiresAt", 0) / 1000 < time.time() + 60:
        raise Refused(
            "the Claude Code login's token has expired: run `claude` once to refresh it, then seed again"
        )
    org = json.loads(run("claude", "auth", "status", "--json").stdout)["orgId"]
    return {
        "Authorization": f"Bearer {oauth['accessToken']}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "ccr-byoc-2025-07-29",
        "x-organization-uuid": org,
    }


def pinned_environment() -> str:
    common = Path(
        run("git", "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    )
    for root in (Path(run("git", "rev-parse", "--show-toplevel").stdout.strip()), common.parent):
        pin = root / ".claude" / "settings.local.json"
        if pin.exists() and (
            env := json.loads(pin.read_text()).get("remote", {}).get("defaultEnvironmentId")
        ):
            return env
    raise Refused("no cloud environment: pass --env, or pin one in .claude/settings.local.json")


def seed(env: str | None, min_days: float) -> int:
    path = seed_home() / "auth.json"
    if not path.exists():
        raise Refused(f"no seed login at {path}: run `cloud_verifier.py login`")
    auth = json.loads(path.read_text())
    if not (auth.get("tokens") or {}).get("refresh_token"):
        raise Refused(
            f"{path} is not a ChatGPT login with a refresh token: run `cloud_verifier.py login`"
        )
    if expires_at(auth["tokens"]["access_token"]) - time.time() < min_days * 86400:
        auth = refreshed(auth)
        tmp = path.with_suffix(".tmp")
        tmp.touch(mode=0o600)
        tmp.write_text(json.dumps(auth, indent=2))
        tmp.replace(path)  # the new refresh token replaces the spent one in one step
        print("refreshed the seed login")
    env = env or pinned_environment()
    headers = claude_headers()
    url = f"{CLAUDE_API}/v1/environment_providers/{env}"
    current = post_json(url, None, headers)
    config = current["config"]
    config["environment"] = {
        **(config.get("environment") or {}),
        VAR: base64.b64encode(json.dumps(reader_copy(auth)).encode()).decode(),
    }
    net = config.setdefault("network_config", {})
    net["allowed_hosts"] = sorted(set(net.get("allowed_hosts") or []) | set(HOSTS))
    post_json(
        url,
        {"name": current["name"], "description": current.get("description", ""), "config": config},
        headers,
    )
    days = (expires_at(auth["tokens"]["access_token"]) - time.time()) / 86400
    print(f"seeded {current['name']} ({env}): the login there lasts {days:.1f} more days")
    return 0


# ── VM: verify ───────────────────────────────────────────────────────────────────────────────────────────────────


def ensure_codex() -> None:
    if not shutil.which("codex"):
        run("npm", "install", "-g", "-s", "@openai/codex")
    if run("codex", "login", "status", check=False).returncode == 0:
        return
    if not (seeded := os.environ.get(VAR)):
        raise Refused(
            f"Codex is not logged in and ${VAR} is not set: run `cloud_verifier.py seed` on the host, then start a new session"
        )
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    auth = home / "auth.json"
    auth.touch(mode=0o600)
    auth.write_bytes(base64.b64decode(seeded))
    if run("codex", "login", "status", check=False).returncode:
        raise Refused(f"Codex does not accept the login in ${VAR}: seed again on the host")


def report_path(brief: str) -> Path | None:
    found = re.search(r"^- Report: (\S+)$", brief, re.MULTILINE)
    return Path(found[1]) if found else None


def signature(model: str | None, effort: str | None) -> str:
    """`codex/<model>/<effort>` as orchestrating-agents' launcher writes it atop a brief (`gpt-6.1-terra` is
    `terra-6.1`, `medium` is `med`, `?` for the CLI's own default), so the report's `Verifier:` line names what ran."""
    short = re.sub(r"^gpt-", "", model or "")
    if found := re.fullmatch(r"(\d+)[.-](\d+)-([a-z]+)", short):
        short = f"{found[3]}-{found[1]}.{found[2]}"
    return f"codex/{short or '?'}/{ {'medium': 'med'}.get(effort or '', effort) or '?' }"


def changes(report: Path | None) -> list[tuple[str, str]]:
    """(status, path) of every uncommitted path but the pass's own: the report, its question and the untracked
    files in the report's folder, where the proof logs live and which a fresh clone ignores only where the project's
    .gitignore does. Run from the top of the checkout, since git names paths from there."""
    own, keep = set(), None
    if report and not report.is_absolute():
        own = {report.as_posix(), f"{report.as_posix()}.question"}
        keep = f"{report.parent.as_posix()}/" if report.parent != Path() else None
    fields = iter(
        run("git", "status", "--porcelain", "-z", "--untracked-files=all").stdout.split("\0")
    )
    found = []
    for field in fields:
        if not field:
            continue
        status, path = field[:2], field[3:]
        if status[0] in "RC":
            next(fields, None)  # a rename's or copy's source follows as a field of its own
        if not (status == "??" and (path in own or (keep and path.startswith(keep)))):
            found.append((status, path))
    return found


def uncommitted(report: Path | None) -> str:
    return "\n".join(f"{status} {path}" for status, path in changes(report))


def showing(report: Path | None) -> str:
    """What git shows as changed, or why it could not say: a status that fails is a tree to look at, not a clean one."""
    try:
        return uncommitted(report)
    except Refused as e:
        return str(e)


def returned(was: str, report: Path | None) -> str:
    """Check out where the pass started: '' when the tree is back there and clean, else what stands in the way."""
    back = run("git", "checkout", "-q", "--no-overwrite-ignore", was, check=False)
    if back.returncode:
        return back.stderr.strip() or f"`git checkout {was}` exited {back.returncode}"
    return showing(report)  # clean there before the pass, so a change still showing is the pass's


def written(path: Path) -> int | None:
    """When the file was last written, or None when there is none."""
    return path.stat().st_mtime_ns if path.is_file() else None


def text(path: Path) -> str:
    """The file as it is, line ends included; a byte that is no UTF-8 is shown as such instead of failing the pass."""
    return path.read_bytes().decode("utf-8", "replace") if path.is_file() else ""


def codex_exec(cmd: list[str], brief: str) -> int:
    return subprocess.run(cmd, input=brief, text=True, check=False).returncode


def needs_a_look(why: str, what: str) -> None:
    print(
        f"cloud_verifier: {why}; look and put it back before the next pass:\n{what}",
        file=sys.stderr,
    )


def verify(pr: int, brief_file: Path, model: str | None, effort: str | None) -> int:
    brief = brief_file.read_text()
    if not brief.startswith("AGENT_SIGNATURE="):
        brief = f"AGENT_SIGNATURE={signature(model, effort)}\n{brief}"
    os.chdir(run("git", "rev-parse", "--show-toplevel").stdout.strip())
    ensure_codex()
    report = report_path(brief)
    question = report.with_name(report.name + ".question") if report else None
    final = Path(tempfile.mkdtemp(prefix="cloud-verifier-")) / "final.md"
    if dirty := uncommitted(report):
        raise Refused(
            f"the tree has uncommitted changes, and a verifier reviews a pushed head only:\n{dirty[:600]}"
        )
    pull = json.loads(run("gh", "api", f"repos/{{owner}}/{{repo}}/pulls/{pr}").stdout)
    head, ref = pull["head"]["sha"], pull["head"]["ref"]
    was = (
        run("git", "symbolic-ref", "-q", "--short", "HEAD", check=False).stdout.strip()
        or run("git", "rev-parse", "HEAD").stdout.strip()
    )
    if run("git", "rev-parse", "HEAD").stdout.strip() != head:
        run("git", "fetch", "-q", "origin", ref)
    # always detached, so a commit or a branch switch by the verifier never moves the worker's branch; and never
    # over an ignored file, which git's checkout replaces by default and the status above can't see
    went = run("git", "checkout", "-q", "--no-overwrite-ignore", "--detach", head, check=False)
    if went.returncode:
        why = went.stderr.strip() or f"exit {went.returncode}"
        if half := showing(report):  # it failed part way, as a filter or a full disk makes it
            needs_a_look(f"`git checkout {head}` failed part way ({why[-300:]})", half)
            return 4
        raise Refused(f"`git checkout {head}` was refused: {why[-600:]}")
    # The tree must be clean at the head too, so that any change after the pass is the verifier's. Comparing with
    # what the checkout itself shows (a submodule the PR moved, a file only the worker's branch ignores) would
    # miss an edit to one of those, so such a checkout is returned and refused instead.
    if shown := showing(report):
        if still := returned(was, report):
            needs_a_look("the checkout could not be returned", still)
            return 4
        raise Refused(
            "at the PR's head this checkout shows changes of its own, and a verifier reviews the pushed head only; "
            f"put them right (update a submodule, move a file aside) and run the pass again:\n{shown[:600]}"
        )
    cmd = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-o", str(final)]
    cmd += ["-m", model] if model else []
    cmd += ["-c", f"model_reasoning_effort={effort}"] if effort else []
    # an earlier pass's file is not this pass's answer: one counts only when this pass wrote it
    before = {p: written(p) for p in (report, question) if p}
    code, wrote, stuck = 1, {}, ""
    try:
        started = time.time()
        code = codex_exec([*cmd, "-"], brief)
        print(f"codex exited {code} after {time.time() - started:.0f} s", flush=True)
        # read before the checkout back, which rewrites a report path that both commits track
        wrote = {
            p: text(p) for p in (report, question) if p and written(p) not in (None, before[p])
        }
        wrote[final] = text(final)
    finally:
        # The script never deletes or restores a file: git can't say which leftover hides something older (an
        # ignored file, a folder with its own repository), so a tree the verifier changed stays as it is,
        # detached at the PR's head, for someone to look at.
        stuck = showing(report) or returned(was, report)
        if stuck:
            needs_a_look("the pass left the checkout changed, so it stays as it is", stuck)
    ask, body = (
        wrote.get(question, ""),
        wrote.get(report, "").strip() and wrote[report] or wrote[final],
    )
    try:
        if not code and ask.strip():
            # verifier.md: a verifier that needs something from the lead writes <report>.question and stops
            print(post(pr, f"## Verifier question\n\n{ask}"))
            return 4 if stuck else 3
        if code or not re.search(r"^SATISFIED:", body, re.MULTILINE):
            print(
                f"no report with a SATISFIED: line (codex exit {code}); the last of what it wrote:\n{body[-1500:]}"
            )
            return 4 if stuck else 1
        print(post(pr, body))
    except (Refused, OSError, ValueError) as e:  # not posted, so a failed pass
        print(f"cloud_verifier: {e}", file=sys.stderr)
        return 4 if stuck else 1
    return 4 if stuck else 0


def post(pr: int, body: str) -> str:
    """Post one comment on the PR through REST (GraphQL answers 403 in the VM) and return its URL."""
    posted = run(
        "gh",
        "api",
        f"repos/{{owner}}/{{repo}}/issues/{pr}/comments",
        "-F",
        "body=@-",  # from stdin: a long report does not fit an argument
        "--jq",
        ".html_url",
        input=body,
    )
    return posted.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="device login into the seed home (host, once)")
    s = sub.add_parser(
        "seed", help="refresh the seed login and store a copy in the cloud environment (host)"
    )
    s.add_argument("--env", help="environment id; default: the checkout's pinned one")
    s.add_argument(
        "--min-days",
        type=float,
        default=5,
        help="refresh when the access token has fewer days left",
    )
    v = sub.add_parser(
        "verify", help="run a Codex verifier pass on the PR and post its report (VM)"
    )
    v.add_argument("--pr", type=int, required=True)
    v.add_argument("--brief", type=Path, required=True)
    v.add_argument("--model")
    v.add_argument("--effort")
    args = parser.parse_args(argv)
    try:
        if args.command == "login":
            return login()
        if args.command == "seed":
            return seed(args.env, args.min_days)
        return verify(args.pr, args.brief, args.model, args.effort)
    except Refused as e:
        print(f"cloud_verifier: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
