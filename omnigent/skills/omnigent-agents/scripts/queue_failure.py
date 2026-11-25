#!/usr/bin/env python3
"""A Mergify queue failure, read from its status comment and its jobs' logs: shared by the supervisor
(``omnigent_agent.py``, which sends it to the lead that owns the PR) and the ``queue-failure`` workflow (which
writes it on the PR as a ``Queue failure`` record, so both teams of a project read the same evidence, #2497).

Standard library only. Mergify queue only: ponytail: epic #2458 open question "does the queue story work with the
GitHub merge queue as well as Mergify": no, this reads Mergify's status comment; GitHub's own merge queue is not
covered.

As a command, run by the workflow for one Mergify comment: ``python3 queue_failure.py``, reading the repo, PR,
comment and its author from ``REPO``, ``PR``, ``COMMENT_ID``, ``COMMENT_URL``, ``AUTHOR`` and ``BODY``, and
using ``gh``. It posts one record per Mergify comment, only for a ``CHECKS_*`` dequeue, and prints why when it
posts nothing. Exit 0 when it posted or had nothing to post; exit 1 when the post failed."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime

MERGIFY_LOGIN = "mergify[bot]"
MERGIFY_PAYLOAD = re.compile(
    r"-\*- Mergify Payload -\*-\s*(\{.*?\})\s*-\*- Mergify Payload End -\*-", re.DOTALL
)
# a failing check's line under `Failing checks:`: its name and job URL, whose last number is the job id
FAILING_CHECK = re.compile(r"^- \S+ \[`([^`]+)`\]\((https://github\.com/[^)\s]*/job/(\d+))\)")
QUEUE_FAULT = re.compile(r"^\*\*The failure is in this pull request\.\*\*.*$", re.MULTILINE)
# pytest's summary line for a failed test, behind the Actions log's timestamp
PYTEST_FAILED = re.compile(r"^(?:\d{4}-\d\d-\d\dT[\d:.]+Z )?FAILED (\S+)", re.MULTILINE)
RECORD_FIRST = (
    "Queue failure"  # the first line of the record, as `Queued for Mergify` is of the hand-over's
)
COMMENT_LINE = (
    "Mergify comment: "  # the record's line naming the comment it reports: one record per comment
)


def stamp(when: str) -> float:
    """A GitHub ISO time as seconds."""
    return datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()


def queue_comment(comment: dict) -> dict | None:
    """One merge-queue entry from a Mergify status comment (a row of GitHub's issue comments): the PR, ``state``
    (``merged``, ``dequeued``, or one not yet final), ``left_at`` (seconds, 0 while in the queue), the
    dequeue ``code``, the ``checks`` under ``Failing checks:`` as ``[name, job URL, job id]`` and Mergify's ``fault``
    line when it named this PR as the failure, else empty. None for a comment not from Mergify or holding no
    payload."""
    if str((comment.get("user") or {}).get("login")) != MERGIFY_LOGIN:
        return None
    body = str(comment.get("body") or "")
    found = MERGIFY_PAYLOAD.search(body)
    pr = re.search(r"/issues/(\d+)$", str(comment.get("issue_url") or ""))
    if not found or not pr:
        return None
    try:
        payload = json.loads(found[1])
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    reason_ = payload.get("dequeue_reason") or {}
    _, _, failing = body.partition("\nFailing checks:\n")
    checks = []
    for line in failing.splitlines():
        if not line.strip():
            break  # the list ends at its blank line
        if m := FAILING_CHECK.match(line.strip()):
            checks.append([m[1], m[2], m[3]])
    fault = QUEUE_FAULT.search(body)
    return {
        "pr": int(pr[1]),
        "state": str(payload.get("state") or ""),
        "left_at": stamp(payload["left_at"]) if payload.get("left_at") else 0.0,
        "code": str(reason_.get("code") or "") if isinstance(reason_, dict) else "",
        "checks": checks,
        "fault": fault[0].replace("**", "") if fault else "",
    }


def failed_tests(log: str) -> list[str]:
    """The test ids of pytest's ``FAILED <id>`` lines in an Actions job log, the timestamp each line opens with
    stripped, once each, in order."""
    return list(dict.fromkeys(PYTEST_FAILED.findall(log)))


def failure_lines(entry: dict, flakes: dict | None = None) -> list[str]:
    """The evidence of a dequeue ``entry`` (``queue_comment``'s, with ``tests`` the failing test ids the jobs' logs
    held): one line per failing check with its job URL, the failing tests (a test in ``flakes`` marked a known
    flake), and Mergify's fault line when it named the PR. The supervisor's message and the record share these."""
    flakes = flakes or {}
    lines = [f"Failing check: {name} {url}" for name, url, _ in entry["checks"]]
    tests = entry.get("tests") or []
    if tests:
        lines.append(
            "Failing tests: " + ", ".join(f"{t}{' (a known flake)' * (t in flakes)}" for t in tests)
        )
    if entry.get("fault"):
        lines.append(entry["fault"])
    return lines


# the most failing tests one record lists, each cut to 300 characters by span(): GitHub refuses a comment over
# 65,536 characters, and a record lost to a noisy log would be lost in the case with the most failures
MAX_TESTS = 50


def span(text: str) -> str:
    """``text`` as one inline code span: a test name or a check name comes from a PR's own log, so a backtick or a
    line break in it must not close the span and post the rest as live markdown."""
    clean = re.sub(r"[`\r\n]+", "'", text)
    return f"`{clean[:300]}`"


def record(
    entry: dict, comment_id: str, comment_url: str = "", unread: tuple[str, ...] = ()
) -> str:
    """The ``Queue failure`` record for a ``CHECKS_*`` dequeue ``entry``: its first line is ``RECORD_FIRST``; then
    the PR, the dequeue code, whether Mergify named this PR the cause (``fault``), each failing check as a link to its
    job, the failing tests, and under the details the Mergify comment it reports, which keeps one record per
    comment. ``unread`` names the checks whose log could not be read, so a missing test list is not read as no failing
    test."""
    n = entry["pr"]
    fault = entry.get("fault")
    lines = [
        RECORD_FIRST,
        f"#{n} left the merge queue: {entry['code'] or 'dequeued'}.",
        (
            "At fault: this pull request (Mergify: it failed tested alone on top of the base)."
            if fault
            else "At fault: Mergify did not name this pull request as the cause."
        ),
        "",
        "Failing checks:",
    ]
    lines += [f"- [{span(name)}]({url})" for name, url, _ in entry["checks"]] or ["- none listed"]
    lines += ["", "Failing tests:"]
    tests = entry.get("tests") or []
    lines += [f"- {span(t)}" for t in tests[:MAX_TESTS]] or [
        "- none found in the failing jobs' logs"
    ]
    if len(tests) > MAX_TESTS:
        lines.append(f"- and {len(tests) - MAX_TESTS} more in the failing jobs' logs")
    if unread:
        lines += ["", "Log not read for: " + ", ".join(span(u) for u in unread)]
    lines += ["", "<details><summary>Details</summary>", ""]
    if comment_url:
        lines.append(f"Mergify's comment: {comment_url}")
    lines += [f"{COMMENT_LINE}{comment_id}", "", "</details>", ""]
    return "\n".join(lines)


def reported(bodies: list[str], comment_id: str) -> bool:
    """Whether one of ``bodies`` (a PR's comments) is a ``Queue failure`` record of Mergify comment ``comment_id``."""
    return any(
        b.split("\n", 1)[0].strip() == RECORD_FIRST and f"\n{COMMENT_LINE}{comment_id}\n" in b
        for b in bodies
    )


def run_gh(*args: str, stdin: str | None = None) -> str:
    """``gh <args>``'s stdout; raises ``RuntimeError`` naming the call when it exits non-zero."""
    done = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {done.stderr.strip()[:200]}")
    return done.stdout


def write(env: dict[str, str], gh: Callable[..., str], out=sys.stdout) -> int:
    """The workflow's whole job for one Mergify comment, given by ``env`` (see the module docstring): read it as a
    queue entry, read the failing jobs' logs through ``gh``, and post the record once. 0 when it posted or had
    nothing to post (a comment that is not Mergify's, not a ``CHECKS_*`` dequeue, or already reported), 1 when
    the post failed."""
    repo, pr, cid = env["REPO"], env["PR"], env["COMMENT_ID"]
    comment = {
        "user": {"login": env.get("AUTHOR", "")},
        "body": env.get("BODY", ""),
        "issue_url": f"https://api.github.com/repos/{repo}/issues/{pr}",
    }
    entry = queue_comment(comment)
    if not entry or entry["state"] != "dequeued" or not entry["code"].startswith("CHECKS_"):
        print("not a Mergify dequeue over failing checks: no record", file=out)
        return 0
    try:
        pages = json.loads(
            gh("api", "--paginate", "--slurp", f"repos/{repo}/issues/{pr}/comments") or "[]"
        )
        bodies = [str(c.get("body") or "") for page in pages for c in page]
    except (RuntimeError, ValueError) as e:
        print(f"the PR's comments were not read: {e}", file=out)
        return 1
    if reported(bodies, cid):
        print(f"comment {cid} is already reported: no second record", file=out)
        return 0
    entry["tests"], unread = [], []
    for name, _, job in entry["checks"]:
        try:
            log = gh("api", f"repos/{repo}/actions/jobs/{job}/logs")
        except RuntimeError as e:  # gone or unreadable: the check's name stands for it
            print(f"job {job} ({name}) log not read: {e}", file=out)
            unread.append(name)
            continue
        entry["tests"] += [t for t in failed_tests(log) if t not in entry["tests"]]
    body = record(entry, cid, env.get("COMMENT_URL", ""), tuple(unread))
    try:
        gh("api", "-X", "POST", f"repos/{repo}/issues/{pr}/comments", "-F", "body=@-", stdin=body)
    except RuntimeError as e:
        print(f"the record was not posted: {e}", file=out)
        return 1
    print(f"posted the queue failure of PR #{pr} for comment {cid}", file=out)
    return 0


def main() -> int:
    return write(dict(os.environ), run_gh)


if __name__ == "__main__":
    sys.exit(main())
