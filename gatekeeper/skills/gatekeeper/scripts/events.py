#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Loop events (engineering-loop): a step's state written as a small git ref, where a reader finds it in a typed field.

    uv run scripts/events.py emit <kind> <branch> <state> [--url U] [--question FILE] [--beat S]   # always exit 0
    uv run scripts/events.py read [<kind>] [--json]       # every event on origin, one line each (exit 0)
    uv run scripts/events.py wait <kind> <branch> [--timeout S] [--poll S]   # block until the state leaves waiting
    uv run scripts/events.py clear <branch>               # remove the branch's refs here and on origin (exit 0)

The contract (kinds, states, beat intervals, what `url` points to, the `event.json` fields) is
[../events.md](../events.md); this file is its writer and reader. Only `git` and an `origin` are needed: no PyYAML, no
gh, no Omnigent. `emit` writes the local ref `refs/loop/<kind>/<branch>` first and then pushes it; a push that fails
prints one warning and the exit stays 0, since an event reports a step and is not part of it.

`wait` exit codes: 0 `ok`, 1 `failed`, 2 `needs-owner` (its question is printed), 3 timeout, 4 silent (`waiting` and
unchanged for twice the beat). A ref that cannot be read or parsed is "unknown", never an end: `wait` keeps waiting
and the timeout is the net."""

from __future__ import annotations

import argparse
import calendar
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# kind -> beat interval in seconds (events.md); a wait is live while its ref changed within twice its kind's beat
BEATS = {"lead": 300, "land": 300, "gate": 120, "verifier": 300, "probe": 60}
STATES = ("waiting", "ok", "failed", "needs-owner")
# `wait`'s exit code for each state that ends it; 3 is the timeout and 4 the silent wait
ENDS = {"ok": 0, "failed": 1, "needs-owner": 2}
TIMEOUT, SILENT = 3, 4
NAMESPACE = "refs/loop"
# where `read` and `wait` keep the last fetch of a remote event, so it never overwrites the ref a local producer wrote
MIRROR = "refs/loop-remote"
# the variable Claude Code sets to `true` in a cloud session's VM; `in_cloud` below is the twin of gatekeeper.py's
# `in_cloud()`, repeated here since this script imports nothing
CLOUD = "CLAUDE_CODE_REMOTE"
# the branch form of an event, `refs/heads/<prefix>/<kind>/<branch>`, which a cloud session's proxy lets a VM push where
# it refuses `refs/loop/` (events.md, Cloud sessions). `emit` writes the first prefix, the bare one a probe from a
# cloud VM found the proxy accepts; `read`, `wait` and `clear` take both, so a `claude/loop-event/` branch counts too
BRANCH_PREFIXES = ("loop-event", "claude/loop-event")
# a gate record's name under refs/loop/gate/, `<tree>-<gate key>`, which no event's branch is
RECORD_NAME = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?-[0-9a-f]{12}")
# the seen-sha file `read` keeps, in the git dir: {ref: {"sha": ..., "changed": <epoch seconds>}}
SEEN = "loop-events-seen.json"
# seconds one git call that reaches origin may take before it counts as a failed push or read
NETWORK = 60
# what a git call that reaches origin raises when origin can't be read or answers too slowly
UNREACHABLE = (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError)
# the commit's author and committer: no person's name or address reaches the repo through an event
IDENTITY = {
    "GIT_AUTHOR_NAME": "loop",
    "GIT_AUTHOR_EMAIL": "loop@invalid",
    "GIT_COMMITTER_NAME": "loop",
    "GIT_COMMITTER_EMAIL": "loop@invalid",
}


def run(
    cwd: Path | str | None,
    *args: str,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> str:
    """One git call in `cwd`; its stdout, or CalledProcessError (TimeoutExpired past `timeout`)."""
    # ponytail: a small runner here, not gatekeeper.git: that module imports PyYAML and its signing state at load,
    # and this one is stdlib-only so a native lead with plain git can run it
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=stdin,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})},
    ).stdout


def ref_of(kind: str, branch: str) -> str:
    return f"{NAMESPACE}/{kind}/{branch}"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_at(text: Any) -> float | None:
    try:
        return calendar.timegm(time.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def blob(cwd: Path | str | None, rev: str, name: str) -> str | None:
    """The text of file `name` in the tree of commit `rev`, or None."""
    try:
        return run(cwd, "show", f"{rev}:{name}")
    except subprocess.CalledProcessError:
        return None


def event_at(cwd: Path | str | None, rev: str) -> dict[str, Any]:
    """The event commit `rev` holds, with its `question` text when it has one. A commit that is no event, or whose
    `event.json` is malformed, reads as state `unknown` (never an end)."""
    text = blob(cwd, rev, "event.json")
    try:
        data = json.loads(text) if text is not None else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or data.get("state") not in STATES:
        return {"state": "unknown", "sha": rev}
    question = blob(cwd, rev, "question.md")
    return {**data, "sha": rev, **({"question": question} if question is not None else {})}


def local_sha(cwd: Path | str | None, ref: str) -> str | None:
    try:
        return run(cwd, "rev-parse", "--verify", "-q", ref).strip() or None
    except subprocess.CalledProcessError:
        return None


FORGE_SETTING = re.compile(r"^\s*forge_remote:\s*[\"']?([\w.-]+)", re.MULTILINE)


def forge_remote(cwd: Path | str | None = None, git: Callable[..., str] | None = None) -> str:
    """The remote the forge's repo is on, for the checkout at `cwd`: the current branch's upstream's remote
    (`git rev-parse --abbrev-ref @{u}`), else `forge_remote` in docs/agents/gatekeeper.md's policy as origin's default branch holds it (never the working tree's), else `origin`.
    A worktree whose branch tracks a fork then fetches, pushes and reads policy from the fork's repo, whatever
    `origin` is. Both the gatekeeper and omnigent-agents' `claude-cloud-run` call it, so they agree. A name that is
    no remote of the checkout is passed over. `git` runs one git call and returns its output (default: `run` in
    `cwd`), so a caller with its own git runner keeps it."""
    ask = git or (lambda *args: run(cwd, *args))
    try:
        remotes = ask("remote").split()
    except (OSError, subprocess.SubprocessError):
        return "origin"
    # the one remote there is, or none: every rule below ends in `origin`, so skip its git calls (#1400)
    if set(remotes) <= {"origin"}:
        return "origin"
    try:
        upstream = ask("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip()
    except (OSError, subprocess.SubprocessError):
        upstream = ""
    if not upstream:  # the tracking ref may be gone (pruned, or not fetched yet) while the branch still names its remote
        try:
            branch = ask("symbolic-ref", "--short", "HEAD").strip()
            upstream = ask("config", f"branch.{branch}.remote").strip() + "/"
        except (OSError, subprocess.SubprocessError):
            upstream = ""
    for name in sorted(remotes, key=len, reverse=True):  # a remote's name may hold a slash
        if upstream.startswith(f"{name}/"):
            return name
    # the setting is read from origin's default branch, which a PR cannot edit: a PR's own working-tree copy would let it
    # choose the remote its base and policy are judged against
    found = None
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main"):
        try:
            found = FORGE_SETTING.search(ask("show", f"{ref}:docs/agents/gatekeeper.md"))
        except (OSError, subprocess.SubprocessError):
            continue
        break
    if found and found.group(1) in remotes:
        return found.group(1)
    return "origin"


def sha_by_ref(listing: str) -> dict[str, str]:
    """The `<sha> <ref>` lines of `ls-remote` or `for-each-ref --format='%(objectname) %(refname)'` as {ref: sha}."""
    words = listing.split()
    return dict(zip(words[1::2], words[0::2]))


def remote_refs(cwd: Path | str | None, *patterns: str) -> dict[str, str]:
    """`git ls-remote origin <patterns>` as {ref: sha}; UNREACHABLE's errors when origin can't be read."""
    return sha_by_ref(run(cwd, "ls-remote", forge_remote(cwd), *patterns, timeout=NETWORK))


def in_cloud() -> bool:
    return os.environ.get(CLOUD) == "true"


def branch_refs(kind: str, branch: str) -> list[str]:
    """The branch forms of the event `<kind>/<branch>`, one per prefix."""
    return [f"refs/heads/{prefix}/{kind}/{branch}" for prefix in BRANCH_PREFIXES]


def canonical(ref: str) -> str:
    """The `refs/loop/<kind>/<branch>` an event ref, in either form, stands for."""
    for prefix in BRANCH_PREFIXES:
        if ref.startswith(f"refs/heads/{prefix}/"):
            return f"{NAMESPACE}/{ref.removeprefix(f'refs/heads/{prefix}/')}"
    return ref


def local_refs(cwd: Path | str | None, prefix: str) -> dict[str, str]:
    """The refs here under `prefix` (a path up to a slash: for-each-ref's `*` stops at one) as {ref: sha}."""
    return sha_by_ref(run(cwd, "for-each-ref", "--format=%(objectname) %(refname)", prefix))


def mirror_of(ref: str) -> str:
    """Where `read` and `wait` keep the last fetch of the remote event `ref`."""
    return MIRROR + ref.removeprefix(NAMESPACE)


def warn(what: str, exc: Exception) -> None:
    """One stderr line: `what` and the error's text, whitespace folded and cut at 300 characters."""
    reason = " ".join((getattr(exc, "stderr", None) or str(exc)).split())[:300]
    print(f"events: {what}: {reason}", file=sys.stderr)


def push(cwd: Path | str | None, *refspecs: str, lease: str | None = None) -> None:
    """Push `refspecs` to origin (hooks skipped), under `--force-with-lease=<lease>` when given."""
    run(
        cwd,
        "push",
        "-q",
        "--no-verify",
        *([f"--force-with-lease={lease}"] if lease else []),
        forge_remote(cwd),
        *refspecs,
        timeout=NETWORK,
    )


def emit(
    kind: str,
    branch: str,
    state: str,
    *,
    url: str = "",
    question: str | None = None,
    beat: float | None = None,
    cwd: Path | str | None = None,
) -> str:
    """Write the event to `refs/loop/<kind>/<branch>` here, then push it to origin, and return the commit. The commit
    is parentless, so a beat (emit again) rewrites the same ref with a new root and history never grows. A push that
    fails prints one warning and returns as a success: the local ref stays, and another host sees it when a later
    push goes through."""
    ref = ref_of(kind, branch)
    old = local_sha(cwd, ref)
    seq = 1
    if old:
        previous = event_at(cwd, old).get("seq")
        seq = previous + 1 if isinstance(previous, int) else 1
    data = {
        "state": state,
        "seq": seq,
        "at": now(),
        "beat_s": beat if beat is not None else BEATS[kind],
        "url": url,
    }
    files = {"event.json": json.dumps(data, sort_keys=True) + "\n"} | (
        {"question.md": question} if question is not None else {}
    )
    entries = "".join(
        f"100644 blob {run(cwd, 'hash-object', '-w', '--stdin', stdin=text).strip()}\t{name}\n"
        for name, text in files.items()
    )
    tree = run(cwd, "mktree", stdin=entries).strip()
    # [skip ci]: a ref outside refs/heads/ starts no workflow, but a host that mirrors it should not either
    commit = run(
        cwd,
        "commit-tree",
        "-m",
        f"loop event {kind} {branch}: {state} [skip ci]",
        tree,
        env=IDENTITY,
    ).strip()
    run(cwd, "update-ref", ref, commit)
    # the ref first; a cloud session's proxy refuses it but takes a branch, which the record workflow moves to the
    # ref and deletes (#2821), so a refused push falls back to the branch
    first: Exception | None = None
    for target in [ref, *branch_refs(kind, branch)[:1]]:
        try:
            # the lease is the sha origin holds now: this writer rewrites its own ref, and only a push that races
            # another writer between the two calls is refused
            # ponytail: one ls-remote per beat, not a lease on a remembered sha, so a producer restarted on another
            # host takes the ref over instead of failing for good
            held = remote_refs(cwd, target).get(target, "")
            push(cwd, f"{commit}:{target}", lease=f"{target}:{held}")
        except UNREACHABLE as exc:
            text = str(getattr(exc, "stderr", ""))
            if (
                "stale info" in text
            ):  # a lost race is no refusal: a branch would only be a stale copy
                warn(f"{ref} written here, not pushed", exc)
                break
            first = first or exc
            continue
        break
    else:
        warn(f"{ref} written here, not pushed", first or RuntimeError("no push made"))
    return commit


def seen_path(cwd: Path | str | None) -> Path:
    return Path(run(cwd, "rev-parse", "--absolute-git-dir").strip()) / SEEN


def load_seen(cwd: Path | str | None) -> dict[str, Any]:
    with contextlib.suppress(OSError, ValueError):
        data = json.loads(seen_path(cwd).read_text())
        if isinstance(data, dict):
            return data
    return {}


def fetch_event(cwd: Path | str | None, ref: str) -> dict[str, Any]:
    """The event origin's `ref` (either form) holds: fetched into the event's mirror, then parsed. A failed fetch:
    state `unknown`."""
    mirror = mirror_of(canonical(ref))
    try:
        run(
            cwd,
            "fetch",
            "-q",
            "--no-tags",
            "--no-write-fetch-head",
            forge_remote(cwd),
            f"+{ref}:{mirror}",
            timeout=NETWORK,
        )
    except UNREACHABLE:
        return {"state": "unknown"}
    return event_at(cwd, mirror)


def split(ref: str) -> tuple[str, str]:
    kind, _, branch = canonical(ref).removeprefix(NAMESPACE + "/").partition("/")
    return kind, branch


def read(kind: str | None = None, *, cwd: Path | str | None = None) -> list[dict[str, Any]]:
    """Every event on origin (of `kind`, when given) as dicts: kind, branch, ref, sha, the event's own fields, and
    `changed`, the epoch second this clone first saw the ref at that sha. One `ls-remote`; a blob is fetched only for
    a ref whose sha moved since the last read, and the rest come from the cache. Origin unreachable: one warning, and
    the local refs are returned instead. Only the kinds in BEATS are events: the gatekeeper's own refs under
    `refs/loop/` (`records/*`, `landing`) are skipped."""
    prefix = f"{NAMESPACE}/{kind}/" if kind else f"{NAMESPACE}/"
    try:
        # the branch forms of a cloud session's events come in the same call (events.md, Cloud sessions)
        shas = remote_refs(
            cwd,
            prefix + "*",
            *(f"refs/heads/{p}/{prefix.removeprefix(NAMESPACE + '/')}*" for p in BRANCH_PREFIXES),
        )
        remote = True
    except UNREACHABLE as exc:
        warn("origin not read, showing the local refs", exc)
        shas = local_refs(cwd, prefix)
        remote = False
    sources: dict[
        str, list[tuple[str, str]]
    ] = {}  # the event's refs/loop/ name -> (ref on origin, sha) of each form
    for ref, sha in sorted(shas.items()):
        kind_of, branch_of = split(ref)
        # refs/loop/gate/ also holds the gate's records, named `<tree>-<key>` (gatekeeper.py's RECORD_REF)
        if kind_of in BEATS and not (kind_of == "gate" and RECORD_NAME.fullmatch(branch_of)):
            sources.setdefault(canonical(ref), []).append((ref, sha))
    seen = load_seen(cwd)
    found = []
    for name, forms in sorted(sources.items()):
        candidates = []
        for ref, sha in forms:
            note = seen.get(ref, {})
            if remote:
                moved = note.get("sha") != sha
                event = fetch_event(cwd, ref) if moved or "event" not in note else note["event"]
                if event.get("state") != "unknown":
                    seen[ref] = {
                        "sha": sha,
                        "changed": time.time() if moved else note.get("changed", time.time()),
                        "event": event,
                    }
                changed = seen.get(ref, {}).get("changed", time.time())
            else:
                event, changed = event_at(cwd, sha), time.time()
            candidates.append((event, sha, changed))
        # the newer event wins when both forms exist; an unreadable one only when nothing else is
        event, sha, changed = max(
            candidates,
            key=lambda c: (
                c[0].get("state") != "unknown",
                str(c[0].get("at", "")),
                int(c[0].get("seq", 0)),
            ),
        )
        found.append(
            {
                **event,
                "kind": split(name)[0],
                "branch": split(name)[1],
                "ref": name,
                "sha": sha,
                "changed": changed,
            }
        )
    if remote:
        with contextlib.suppress(OSError):
            # what this listing did not cover (another kind, after a filtered read) stays cached as it was
            kept = {r: note for r, note in seen.items() if not canonical(r).startswith(prefix)}
            now_seen = {
                ref: seen[ref] for forms in sources.values() for ref, _ in forms if ref in seen
            }
            seen_path(cwd).write_text(json.dumps(kept | now_seen))
    return found


def wait(
    kind: str,
    branch: str,
    *,
    timeout: float = 7200,
    poll: float = 15,
    cwd: Path | str | None = None,
    out: Any = None,
) -> int:
    """Block until the event leaves `waiting`; return its exit code (the module docstring). Each poll reads the local
    ref, then origin, and takes the later `at` of the two, so a producer in this clone and one on another host both
    count. A `waiting` event unchanged for twice its beat (counted from its `at` on the first sight, then from the
    moment its sha moved) ends the wait with 4."""
    out = out or sys.stdout
    ref = ref_of(kind, branch)
    deadline = time.monotonic() + timeout
    watched: tuple[str, float] | None = None  # (sha, when this wait saw it first, in time.time())
    while True:
        events = []
        if sha := local_sha(cwd, ref):
            events.append(event_at(cwd, sha))
        with contextlib.suppress(*UNREACHABLE):
            forms = branch_refs(kind, branch)
            for there, remote in remote_refs(cwd, ref, *forms).items():
                if there in (ref, *forms) and remote != sha:
                    events.append(fetch_event(cwd, there))
        known = [e for e in events if e["state"] != "unknown"]
        # ponytail: the later `at` wins, so two hosts' clocks decide a tie; a producer has one writer per ref
        event = (
            max(known, key=lambda e: (str(e.get("at", "")), int(e.get("seq", 0))))
            if known
            else None
        )
        if event is not None:
            if event["state"] in ENDS:
                print(
                    f"{kind} {branch}: {event['state']}"
                    + (f" {event['url']}" if event.get("url") else ""),
                    file=out,
                )
                if event.get("question"):
                    print(event["question"], file=out)
                return ENDS[event["state"]]
            if watched is None or watched[0] != event["sha"]:
                at = parse_at(event.get("at"))
                watched = (event["sha"], min(time.time(), at) if at is not None else time.time())
            if time.time() - watched[1] > 2 * float(event.get("beat_s", BEATS.get(kind, 300))):
                print(
                    f"{kind} {branch}: silent, waiting and unchanged for more than twice its beat",
                    file=out,
                )
                return SILENT
        if time.monotonic() >= deadline:
            print(f"{kind} {branch}: still waiting after {timeout:g}s", file=out)
            return TIMEOUT
        time.sleep(max(0.0, min(poll, deadline - time.monotonic())))


def clear(branch: str, *, cwd: Path | str | None = None) -> None:
    """Remove the refs of `branch` (one per kind, and each branch form) here and on origin. A delete origin refuses prints one warning."""
    mine = [ref_of(kind, branch) for kind in BEATS]
    for ref in mine:
        if local_sha(cwd, ref):
            run(cwd, "update-ref", "-d", ref)
        mirror = mirror_of(ref)
        if local_sha(cwd, mirror):
            run(cwd, "update-ref", "-d", mirror)
    mine += [
        form for kind in BEATS for form in branch_refs(kind, branch)
    ]  # a cloud session's branch forms go too
    try:
        listed = remote_refs(
            cwd, f"{NAMESPACE}/*/{branch}", *(f"refs/heads/{p}/*/{branch}" for p in BRANCH_PREFIXES)
        )
        there = [ref for ref in mine if ref in listed]
        if there:
            push(cwd, *(f":{ref}" for ref in there))
    except UNREACHABLE as exc:
        warn(f"origin's refs of {branch} not removed", exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--repo", default=None, help="run git in this directory (default: the current one)"
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("emit")
    p.add_argument("kind", choices=sorted(BEATS))
    p.add_argument("branch")
    p.add_argument("state", choices=STATES)
    p.add_argument("--url", default="")
    p.add_argument("--question", metavar="FILE", help="the whole text of a request to the owner")
    p.add_argument(
        "--beat",
        type=float,
        default=None,
        help="seconds between this producer's beats (default: the kind's)",
    )
    p = sub.add_parser("read")
    p.add_argument("kind", nargs="?", choices=sorted(BEATS))
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("wait")
    p.add_argument("kind", choices=sorted(BEATS))
    p.add_argument("branch")
    p.add_argument("--timeout", type=float, default=7200)
    p.add_argument("--poll", type=float, default=15)
    p = sub.add_parser("clear")
    p.add_argument("branch")
    args = parser.parse_args(argv)
    try:
        if args.verb == "emit":
            question = Path(args.question).read_text() if args.question else None
            print(
                emit(
                    args.kind,
                    args.branch,
                    args.state,
                    url=args.url,
                    question=question,
                    beat=args.beat,
                    cwd=args.repo,
                )
            )
        elif args.verb == "read":
            found = read(args.kind, cwd=args.repo)
            for event in found:
                print(
                    json.dumps(event, sort_keys=True)
                    if args.json
                    else f"{event['ref']} {event['state']} {event.get('url', '')}".rstrip()
                )
        elif args.verb == "wait":
            return wait(args.kind, args.branch, timeout=args.timeout, poll=args.poll, cwd=args.repo)
        else:
            clear(args.branch, cwd=args.repo)
    except (subprocess.CalledProcessError, OSError) as exc:
        # the local half failed (not a git repo, an unreadable question file): the one case that is a real error
        print(
            f"events: {' '.join((getattr(exc, 'stderr', None) or str(exc)).split())}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
