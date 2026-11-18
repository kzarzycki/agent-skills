#!/usr/bin/env python3
"""A wait's state, written where a reader finds it in a typed field: a commit status on a PR's head.

    loop_status.py post [--repo OWNER/NAME] <sha> <context> <state> [--url URL] [--desc TEXT]
    loop_status.py read [--repo OWNER/NAME] <sha|PR-number> [--context loop/x] [--cache FILE]
    loop_status.py wait [--repo OWNER/NAME] <pr> <context> [--beat S] [--budget S] [--every S]

The contract (contexts, what each state means, beat intervals, what ``target_url`` points to) is
``loop-status.md`` beside ``SKILL.md``. ``post`` never fails its caller: a failed call prints one
warning and exits 0, so reporting state costs a step nothing. ``read`` asks with ``If-None-Match``,
and a 304 answers from the cache and costs no quota; an unreachable API prints one warning and
reads as unknown. ``wait`` exits 0 ``success``, 1 ``failure``, 2 ``error``, 3 timeout, 4 ``pending``
and silent for more than twice the beat; it re-reads the PR's head each poll, since a push moves it.

Standard library only, plus ``gh`` and its login (a ``repo``-scope token).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, NamedTuple

STATES = ("pending", "success", "failure", "error")
EXIT = {"success": 0, "failure": 1, "error": 2}
TIMEOUT, SILENT = 3, 4
DESCRIPTION_MAX = 140  # GitHub's limit on a status description
BEAT = 300.0  # seconds between a pending status's refreshes, unless the context says otherwise
BEATS = {"loop/probe": 60.0}  # ponytail: one default beat; a context gets its own when a producer needs it
EVERY = 20.0  # seconds between polls of ``wait``; a 304 poll costs no quota
CALL_SECONDS = 30.0


class Reply(NamedTuple):
    """One REST answer: the HTTP status (0 when none came), its headers (lowercase names) and body."""

    status: int
    headers: dict[str, str]
    body: str


Api = Callable[[str, str, dict[str, str], str | None], Reply]
"""``api(method, path, fields, etag)``: a REST call, ``fields`` the POST body, ``etag`` an ``If-None-Match``."""


def gh_api(method: str, path: str, fields: dict[str, str], etag: str | None) -> Reply:
    """``gh api -i``: the answer with its headers. A 304 and an error status come back as a ``Reply``;
    a missing ``gh`` or a hang is status 0."""
    argv = ["gh", "api", "-i", "-X", method, path]
    for key, value in fields.items():
        argv += ["-f", f"{key}={value}"]
    if etag:
        argv += ["-H", f"If-None-Match: {etag}"]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=CALL_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        return Reply(0, {}, str(e))
    head, _, body = out.stdout.replace("\r\n", "\n").partition("\n\n")
    lines = head.splitlines()
    parts = lines[0].split() if lines else []
    if len(parts) < 2 or not parts[1].isdigit():
        return Reply(0, {}, (out.stderr or out.stdout).strip())
    headers = {k.strip().lower(): v.strip() for k, _, v in (x.partition(":") for x in lines[1:])}
    return Reply(int(parts[1]), headers, body if out.returncode == 0 or body else out.stderr)


def warn(text: str) -> None:
    print(f"warning: loop-status: {text}", file=sys.stderr)


def post(
    sha: str,
    context: str,
    state: str,
    url: str = "",
    description: str = "",
    repo: str = "{owner}/{repo}",
    api: Api = gh_api,
) -> bool:
    """Post ``state`` for ``context`` on ``sha``. A failed post prints one warning and returns False;
    it never raises, so a loop step reports state for free."""
    if state not in STATES:
        warn(f"not posted: state {state!r} is none of {', '.join(STATES)}")
        return False
    fields = {"state": state, "context": context, "description": description[:DESCRIPTION_MAX]}
    if url:
        fields["target_url"] = url
    reply = api("POST", f"repos/{repo}/statuses/{sha}", fields, None)
    if reply.status == 201:
        return True
    warn(f"{context} on {sha[:12]} not posted (HTTP {reply.status or 'none'}): {reply.body[:120]}")
    return False


class Cache:
    """ETag and body of each path read, kept in ``file`` when given so a later process also gets a 304."""

    def __init__(self, file: Path | None = None) -> None:
        self.file = file
        self.data: dict[str, dict[str, str]] = {}
        try:
            self.data = json.loads(file.read_text()) if file else {}
        except (OSError, ValueError):
            self.data = {}

    def save(self) -> None:
        if self.file:
            try:
                self.file.parent.mkdir(parents=True, exist_ok=True)
                self.file.write_text(json.dumps(self.data))
            except OSError:
                pass  # a cache that can't be written only costs the next call a full answer


def get(path: str, cache: Cache, api: Api) -> object | None:
    """JSON at ``path``, from the cache on a 304; None (unknown) after one warning when the call fails."""
    held = cache.data.get(path)
    reply = api("GET", path, {}, held["etag"] if held else None)
    if reply.status == 304 and held:
        return json.loads(held["body"])
    if reply.status == 200:
        try:
            body = json.loads(reply.body)
        except ValueError:
            warn(f"{path}: an answer that is not JSON")
            return None
        if etag := reply.headers.get("etag"):
            cache.data[path] = {"etag": etag, "body": reply.body}
            cache.save()
        return body
    warn(f"{path}: HTTP {reply.status or 'none'}: {reply.body[:120]}")
    return None


def read(
    sha: str, repo: str = "{owner}/{repo}", cache: Cache | None = None, api: Api = gh_api
) -> dict | None:
    """The combined status of ``sha`` (its newest status per context), or None for unknown."""
    body = get(f"repos/{repo}/commits/{sha}/status", cache or Cache(), api)
    return body if isinstance(body, dict) else None


def head_of(pr: int, repo: str, cache: Cache, api: Api) -> str | None:
    """PR ``pr``'s current head sha, or None for unknown."""
    body = get(f"repos/{repo}/pulls/{pr}", cache, api)
    sha = body.get("head", {}).get("sha") if isinstance(body, dict) else None
    return sha if isinstance(sha, str) else None


def stamp(when: str) -> float:
    return datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()


def settled(status: dict, beat: float, now: float) -> tuple[int, str] | None:
    """The exit code and line of one context's status once it is settled: its state's code, or
    ``SILENT`` for a pending one not refreshed within twice ``beat``; None while pending and fresh."""
    state, url = status.get("state"), status.get("target_url") or ""
    said = " ".join(x for x in (status.get("description"), url) if x)
    if state in EXIT:
        return EXIT[state], f"{status.get('context')} {state}: {said}".strip()
    age = now - stamp(status.get("updated_at") or status.get("created_at"))
    if age > 2 * beat:
        return SILENT, f"{status.get('context')} pending but silent for {age:.0f}s (beat {beat:.0f}s): {said}"
    return None


def wait(
    pr: int,
    context: str,
    beat: float | None = None,
    budget: float = 570.0,
    every: float = EVERY,
    repo: str = "{owner}/{repo}",
    cache: Cache | None = None,
    api: Api = gh_api,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[int, str]:
    """Block until ``context`` on PR ``pr``'s head leaves ``pending`` (``settled``'s codes), or
    ``budget`` seconds pass (``TIMEOUT``). The head is read again each poll. A context not posted
    yet, or a read that fails, is waited through, so a producer that starts late is not an error."""
    cache = cache or Cache()
    beat = beat or BEATS.get(context, BEAT)
    end = clock() + budget
    while True:
        head = head_of(pr, repo, cache, api)
        combined = read(head, repo, cache, api) if head else None
        for status in (combined or {}).get("statuses", []):
            if status.get("context") == context and (out := settled(status, beat, clock())):
                return out[0], f"PR #{pr} head {head}: {out[1]}"
        if clock() >= end:
            return TIMEOUT, f"PR #{pr}: {context} still pending after {budget:.0f}s"
        sleep(min(every, max(0.0, end - clock())))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("post", "read", "wait"):
        s = sub.add_parser(name)
        s.add_argument("--repo", default="{owner}/{repo}", help="OWNER/NAME (default: this clone's)")
        if name == "post":
            s.add_argument("sha")
            s.add_argument("context")
            s.add_argument("state", choices=STATES)
            s.add_argument("--url", default="")
            s.add_argument("--desc", default="")
        elif name == "read":
            s.add_argument("target", help="a commit sha, or a PR number (its head)")
            s.add_argument("--context")
            s.add_argument("--cache", type=Path, help="file holding ETags, so a later read can be a 304")
        else:
            s.add_argument("pr", type=int)
            s.add_argument("context")
            s.add_argument("--beat", type=float)
            s.add_argument("--budget", type=float, default=570.0)
            s.add_argument("--every", type=float, default=EVERY)
    args = p.parse_args(argv)
    if args.cmd == "post":
        post(args.sha, args.context, args.state, args.url, args.desc, args.repo)
        return 0  # a post never changes the caller's exit code
    if args.cmd == "read":
        cache = Cache(args.cache)
        sha = args.target
        if sha.isdigit() and (sha := head_of(int(sha), args.repo, cache, gh_api)) is None:
            print("unknown")
            return 0
        combined = read(sha, args.repo, cache)
        if combined is None:
            print("unknown")
            return 0
        statuses = combined.get("statuses", [])
        if args.context:
            statuses = [s for s in statuses if s.get("context") == args.context]
        for s in statuses:
            print(f"{s['context']}\t{s['state']}\t{s.get('target_url') or ''}\t{s.get('description') or ''}")
        return 0
    code, line = wait(args.pr, args.context, args.beat, args.budget, args.every, args.repo)
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
