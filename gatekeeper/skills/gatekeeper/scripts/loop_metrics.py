#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""loop-metrics: one weekly number pair per repo, so a migration that makes the loop slower or dearer shows
within a week (#2233, part of #2143). Read-only: it prints and posts nothing.

    uv run scripts/loop_metrics.py <owner/repo> [<owner/repo> ...] --since <YYYY-MM-DD>

One line per repo for the 7 days from `--since`, with the 7 days before it beside it:

    owner/repo 2026-11-17..2026-11-23: merged 12, median ready->merged 1h12m, runner-min/PR 34.5 | week before 2026-11-10..2026-11-16: merged 9, ...

- merged: PRs merged in the week.
- median ready->merged: from the PR's last `ready_for_review` event (else its creation, when it was never a
  draft) to its merge.
- runner-min/PR: the sum of job durations (every attempt of a rerun counted) of every run on the PR's heads,
  on its queue entries and on the push of its merge commit, divided by the merged PRs. A queue batch (a
  Mergify draft PR from a `mergify/merge-queue/` branch) tests several PRs: its minutes split evenly over
  the batch's PRs that merged in the two weeks, and a line that holds such minutes says
  `batch minutes split evenly`.

A repo with no Actions workflows is skipped with a line that says so.

Quota, per repo: one search for the two weeks' merged PRs (a page per 100), one search for the queue-batch
PRs, one `timeline` call per merged PR (the only source of its ready events, heads and merge commit; never
per job), the runs listing once in bulk (a page per 100 runs, indexed here by `head_sha`), and one jobs
listing per attributed run (`filter=all`, so every attempt). Needs `gh`, nothing else.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

BATCH_PREFIX = "mergify/merge-queue/"
BATCH_PRS = re.compile(r"#(\d+)")
Gh = Callable[[str], Any]


def real_gh(path: str) -> Any:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path}: {out.stderr.strip() or out.stdout.strip()}")
    return json.loads(out.stdout)


def parse_time(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def pages(gh: Gh, path: str, key: str | None = None) -> list[Any]:
    """Every item of a paginated listing (`key` names the list inside an object), 100 a page."""
    sep = "&" if "?" in path else "?"
    items: list[Any] = []
    page = 1
    while True:
        body = gh(f"{path}{sep}per_page=100&page={page}")
        chunk = body[key] if key else body
        items.extend(chunk)
        if len(chunk) < 100:
            return items
        page += 1


def has_actions(gh: Gh, repo: str) -> bool:
    try:
        return gh(f"repos/{repo}/actions/workflows?per_page=1").get("total_count", 0) > 0
    except RuntimeError:
        return False


def merged_prs(gh: Gh, repo: str, first: dt.date, last: dt.date) -> dict[int, dict[str, Any]]:
    query = f"repo:{repo} is:pr is:merged merged:{first}..{last}"
    found = pages(gh, "search/issues?q=" + query.replace(" ", "+"), "items")
    return {
        item["number"]: {
            "created": parse_time(item["created_at"]),
            "merged": parse_time(item["pull_request"]["merged_at"]),
        }
        for item in found
        if (item.get("pull_request") or {}).get("merged_at")
    }


def batches(gh: Gh, repo: str, first: dt.date) -> dict[int, list[int]]:
    """Queue-batch draft PR number -> the PR numbers its body names."""
    query = f"repo:{repo} is:pr head:{BATCH_PREFIX} updated:>={first}"
    found = pages(gh, "search/issues?q=" + query.replace(" ", "+"), "items")
    return {
        item["number"]: sorted(
            {int(n) for n in BATCH_PRS.findall(item.get("body") or "")} - {item["number"]}
        )
        for item in found
    }


def read_timeline(gh: Gh, repo: str, number: int) -> dict[str, Any]:
    ready = None
    shas: set[str] = set()
    for event in pages(gh, f"repos/{repo}/issues/{number}/timeline"):
        kind = event.get("event")
        if kind == "ready_for_review":
            when = parse_time(event["created_at"])
            ready = when if ready is None or when > ready else ready
        elif kind == "committed" and event.get("sha"):
            shas.add(event["sha"])
        elif kind in ("head_ref_force_pushed", "merged") and event.get("commit_id"):
            shas.add(event["commit_id"])
    return {"ready": ready, "shas": shas}


def job_minutes(gh: Gh, repo: str, run_id: int) -> float:
    total = 0.0
    for job in pages(gh, f"repos/{repo}/actions/runs/{run_id}/jobs?filter=all", "jobs"):
        if job.get("started_at") and job.get("completed_at"):
            total += (
                parse_time(job["completed_at"]) - parse_time(job["started_at"])
            ).total_seconds() / 60
    return total


def collect(gh: Gh, repo: str, since: dt.date) -> dict[str, Any]:
    """Per merged PR (the week and the week before): merged-at, ready->merged seconds, runner-minutes."""
    first, last = since - dt.timedelta(days=7), since + dt.timedelta(days=6)
    prs = merged_prs(gh, repo, first, last)
    batch_prs = batches(gh, repo, first)
    with ThreadPoolExecutor(8) as pool:  # the same calls, 8 at a time
        timelines = dict(zip(prs, pool.map(lambda n: read_timeline(gh, repo, n), prs)))
    owner_of_sha: dict[str, set[int]] = {}
    for number, timeline in timelines.items():
        for sha in timeline["shas"]:
            owner_of_sha.setdefault(sha, set()).add(number)
    since_created = min((p["created"] for p in prs.values()), default=None)
    runs: list[dict[str, Any]] = []
    if since_created is not None:
        floor = (since_created - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        runs = pages(gh, f"repos/{repo}/actions/runs?created=%3E%3D{floor}", "workflow_runs")
    minutes = {n: 0.0 for n in prs}
    batched = False
    for run in runs:
        owners = set(owner_of_sha.get(run.get("head_sha", ""), ()))
        share: list[int] = []
        for pull in run.get("pull_requests") or []:
            number = pull["number"]
            if number in prs:
                owners.add(number)
            elif number in batch_prs:
                share += [n for n in batch_prs[number] if n in prs]
        if not owners and not share:
            continue
        spent = job_minutes(gh, repo, run["id"])
        for number in owners:
            minutes[number] += spent
        for number in set(share):
            minutes[number] += spent / len(set(share))
            batched = True
    rows = []
    for number, pr in prs.items():
        ready = timelines[number]["ready"] or pr["created"]
        rows.append(
            {
                "number": number,
                "merged": pr["merged"],
                "seconds": (pr["merged"] - ready).total_seconds(),
                "minutes": minutes[number],
            }
        )
    return {"rows": rows, "batched": batched}


def duration(seconds: float) -> str:
    whole = round(seconds)
    hours, rest = divmod(whole, 3600)
    mins = rest // 60
    return f"{hours}h{mins:02d}m" if hours else f"{mins}m"


def summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "merged 0"
    median = duration(statistics.median(r["seconds"] for r in rows))
    per_pr = sum(r["minutes"] for r in rows) / len(rows)
    return f"merged {len(rows)}, median ready->merged {median}, runner-min/PR {per_pr:.1f}"


def line(gh: Gh, repo: str, since: dt.date) -> str:
    if not has_actions(gh, repo):
        return f"{repo}: skipped, no Actions workflows"
    data = collect(gh, repo, since)
    week = [r for r in data["rows"] if since <= r["merged"].date() < since + dt.timedelta(days=7)]
    before = [r for r in data["rows"] if since - dt.timedelta(days=7) <= r["merged"].date() < since]
    one = since + dt.timedelta(days=6)
    prior = since - dt.timedelta(days=7)
    text = f"{repo} {since}..{one}: " + summary(week)
    text += f" | week before {prior}..{since - dt.timedelta(days=1)}: " + summary(before)
    if data["batched"]:
        text += " (batch minutes split evenly across each queue batch's PRs)"
    return text


def main(argv: list[str] | None = None, gh: Gh = real_gh) -> int:
    parser = argparse.ArgumentParser(
        prog="loop-metrics",
        description="Weekly ready->merged time and runner-minutes per merged PR.",
    )
    parser.add_argument("repos", nargs="+", metavar="owner/repo")
    parser.add_argument(
        "--since",
        required=True,
        type=dt.date.fromisoformat,
        help="first day of the week, YYYY-MM-DD",
    )
    args = parser.parse_args(argv)
    code = 0
    for repo in args.repos:
        try:
            print(line(gh, repo, args.since))
        except RuntimeError as error:
            print(f"{repo}: error, {error}", file=sys.stderr)
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
