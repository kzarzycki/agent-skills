"""scripts/loop_metrics.py: the weekly ready->merged time and runner-minutes per merged PR (#2233), on recorded API
responses served by a fake `gh api`."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

SCRIPT = (
    Path(__file__).resolve().parents[1] / "skills" / "gatekeeper" / "scripts" / "loop_metrics.py"
)
spec = importlib.util.spec_from_file_location("loop_metrics", SCRIPT)
assert spec and spec.loader
loop_metrics = importlib.util.module_from_spec(spec)
sys.modules["loop_metrics"] = loop_metrics
spec.loader.exec_module(loop_metrics)

REPO = "acme/widgets"
SINCE = dt.date(2026, 11, 17)


def job(minutes: int, start: str = "2026-11-18T10:00:00Z") -> dict[str, str]:
    begin = loop_metrics.parse_time(start)
    return {
        "started_at": start,
        "completed_at": (begin + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def search_item(number: int, created: str, merged: str, body: str = "") -> dict[str, Any]:
    return {
        "number": number,
        "created_at": created,
        "body": body,
        "pull_request": {"merged_at": merged},
    }


# #1: a draft first (last ready event 1h before merge, created a day earlier), one head (a run with no PR list), one 10-minute job.
# #2: never a draft (created 1h before merge); its run was rerun: attempts of 10 and 6 minutes.
# #3 and #4: merged through one queue batch whose run took 20 minutes: 10 minutes each.
# #5: merged the week before, one 4-minute job on its head.
RECORDED: dict[str, Any] = {
    "repos/acme/widgets/actions/workflows": {"total_count": 1},
    "search/issues|is:pr is:merged": {
        "items": [
            search_item(1, "2026-11-17T08:00:00Z", "2026-11-18T12:00:00Z"),
            search_item(2, "2026-11-19T09:00:00Z", "2026-11-19T10:00:00Z"),
            search_item(3, "2026-11-20T08:00:00Z", "2026-11-20T10:00:00Z"),
            search_item(4, "2026-11-20T08:00:00Z", "2026-11-20T10:00:00Z"),
            search_item(6, "2026-11-17T08:30:00Z", "2026-11-17T09:00:00Z"),
            search_item(5, "2026-11-12T08:00:00Z", "2026-11-12T09:00:00Z"),
        ]
    },
    "search/issues|head:mergify/merge-queue/": {
        "items": [
            {
                "number": 90,
                "created_at": "2026-11-20T09:00:00Z",
                "body": "Speculative check of #3, #4",
                "pull_request": {},
            },
        ]
    },
    "repos/acme/widgets/issues/1/timeline": [
        {"event": "ready_for_review", "created_at": "2026-11-18T09:00:00Z"},
        {"event": "ready_for_review", "created_at": "2026-11-18T11:00:00Z"},
        {"event": "committed", "sha": "aaa"},
    ],
    "repos/acme/widgets/issues/2/timeline": [{"event": "committed", "sha": "bbb"}],
    "repos/acme/widgets/issues/3/timeline": [{"event": "committed", "sha": "ccc"}],
    "repos/acme/widgets/issues/4/timeline": [{"event": "committed", "sha": "ddd"}],
    "repos/acme/widgets/issues/6/timeline": [],
    "repos/acme/widgets/issues/5/timeline": [{"event": "committed", "sha": "eee"}],
    "repos/acme/widgets/actions/runs": {
        "workflow_runs": [
            {"id": 11, "head_sha": "aaa", "pull_requests": []},
            {"id": 12, "head_sha": "bbb", "pull_requests": [{"number": 2}]},
            {"id": 13, "head_sha": "zzz", "pull_requests": [{"number": 90}]},
            {"id": 14, "head_sha": "eee", "pull_requests": [{"number": 5}]},
            {"id": 15, "head_sha": "unrelated", "pull_requests": []},
        ]
    },
    "repos/acme/widgets/actions/runs/11/jobs": {"jobs": [job(10)]},
    "repos/acme/widgets/actions/runs/12/jobs": {"jobs": [job(10), job(6, "2026-11-19T10:30:00Z")]},
    "repos/acme/widgets/actions/runs/13/jobs": {
        "jobs": [job(12), job(8), {"started_at": None, "completed_at": None}]
    },
    "repos/acme/widgets/actions/runs/14/jobs": {
        "jobs": [job(4), {"started_at": "2026-11-12T08:00:00Z", "completed_at": None}]
    },
}


class FakeGh:
    def __init__(self, recorded: dict[str, Any]) -> None:
        self.recorded = recorded
        self.calls: list[str] = []

    def __call__(self, path: str) -> Any:
        self.calls.append(path)
        route = unquote(path.replace("+", " "))
        base = route.split("?")[0]
        if base == "search/issues":
            for key, body in self.recorded.items():
                if key.startswith("search/issues|") and key.split("|", 1)[1] in route:
                    return body if "page=1" in route else {"items": []}
        if base in self.recorded:
            body = self.recorded[base]
            return (
                body
                if "page=1" in route or "page=" not in route
                else ([] if isinstance(body, list) else {k: [] for k in body})
            )
        raise RuntimeError(f"no recorded response for {path}")


def test_week_line_counts_median_minutes_and_the_week_before() -> None:
    gh = FakeGh(RECORDED)
    text = loop_metrics.line(gh, REPO, SINCE)
    # week: #1 1h from its last ready event, #2 1h from creation, #3 and #4 2h, #6 (merged on the first day) 30m: median 1h
    # minutes: #1 10, #2 16 (both attempts), #3 and #4 (12+8)/2 = 10 each: (10+16+10+10+0)/5 = 9.2
    assert text.startswith(
        f"{REPO} 2026-11-17..2026-11-23: merged 5, median ready->merged 1h00m, runner-min/PR 9.2"
    )
    assert (
        "| week before 2026-11-10..2026-11-16: merged 1, median ready->merged 1h00m, runner-min/PR 4.0"
        in text
    )
    assert "batch minutes split evenly across each queue batch's PRs" in text
    assert text.count("\n") == 0


def test_runs_are_listed_in_bulk_and_jobs_once_per_attributed_run() -> None:
    gh = FakeGh(RECORDED)
    loop_metrics.line(gh, REPO, SINCE)
    searches = [c for c in gh.calls if c.startswith("search/issues") and "merged" in unquote(c)]
    assert len(searches) == 1
    assert len([c for c in gh.calls if "/actions/runs?" in c]) == 1
    assert all("filter=all" in c for c in gh.calls if "/jobs" in c)  # every attempt of a rerun
    jobs = [c.split("?")[0] for c in gh.calls if "/jobs" in c]
    assert sorted(jobs) == [
        f"repos/acme/widgets/actions/runs/{n}/jobs" for n in (11, 12, 13, 14)
    ]  # run 15 is nobody's
    assert len([c for c in gh.calls if "/timeline" in c]) == 6


def test_a_repo_with_no_actions_is_skipped_with_a_line_saying_so() -> None:
    gh = FakeGh({"repos/acme/widgets/actions/workflows": {"total_count": 0}})
    assert loop_metrics.line(gh, REPO, SINCE) == f"{REPO}: skipped, no Actions workflows"
    assert gh.calls == ["repos/acme/widgets/actions/workflows?per_page=1"]


def test_main_prints_one_line_per_repo(capsys) -> None:
    assert loop_metrics.main([REPO, "--since", "2026-11-17"], FakeGh(RECORDED)) == 0
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_a_week_with_no_merges_prints_zero() -> None:
    gh = FakeGh(
        {
            "repos/acme/widgets/actions/workflows": {"total_count": 1},
            "search/issues|is:pr is:merged": {"items": []},
            "search/issues|head:mergify": {"items": []},
        }
    )
    gh.recorded["search/issues|head:mergify/merge-queue/"] = {"items": []}
    assert "merged 0 | week before" in loop_metrics.line(gh, REPO, SINCE)
