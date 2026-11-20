"""Loop pollers spend few GitHub REST calls and sleep through a rate limit (#1537)."""

import json
import subprocess

import pytest
from test_omnigent_agent import omnigent_agent as oa

HOUR = 3600


def test_intervals_pinned():
    assert oa.WAIT_FOR_PR_EVERY == 120.0
    assert oa.HEAD_SECONDS == 300.0


def test_rate_limit_sleeps_to_reset(monkeypatch):
    """A fake 403 whose bucket resets in 90 s makes wait-for sleep ~91 s once, not retry."""
    now = 1_000_000.0
    monkeypatch.setattr(oa.time, "time", lambda: now)

    def run(cmd, **kw):
        if cmd[:3] == ["gh", "api", "rate_limit"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{int(now) + 90}\n")
        raise subprocess.CalledProcessError(1, cmd, stderr="gh: API rate limit exceeded (HTTP 403)")

    monkeypatch.setattr(oa.subprocess, "run", run)
    with pytest.raises(oa.RateLimited) as e:
        oa.gh("api", "x")
    assert e.value.wait == 91.0
    assert oa.rate_wait("HTTP 429 Retry-After: 17") == 17.0
    assert oa.rate_wait("HTTP 404 not found") is None


def test_wait_for_sleeps_instead_of_retrying(monkeypatch, capsys):
    calls, slept = [], []

    def gate(pr, end, since=None):
        calls.append(1)
        if len(calls) == 1:
            raise oa.RateLimited("403", 77.0)
        return 0, "passed"

    monkeypatch.setattr(oa, "gate_outcome", gate)
    monkeypatch.setattr(oa.time, "sleep", slept.append)
    assert oa.wait_for(None, None, 5, "gate", 1000.0) == (0, "passed")
    assert slept == [77.0] and "rate limit" in capsys.readouterr().err


def test_unchanged_pr_hour_is_bounded(monkeypatch):
    """One simulated hour of an unchanged PR: verdict polls read the PR only; gate polls reuse cached commits."""
    asked = []
    pr = {"head": {"sha": "a" * 40}, "updated_at": "t0"}

    def fake_gh(*args, **kw):
        path = args[1] if args[1] != "--paginate" else args[2]
        asked.append(path)
        if path.endswith("pulls/5"):
            return json.dumps(pr)
        if "git/commits/" in path:
            return json.dumps({"tree": {"sha": "t"}, "committer": {"date": "2026-01-01T00:00:00Z"}})
        if "matching-refs" in path or "statuses" in path:
            return "[]"
        return ""

    monkeypatch.setattr(oa, "gh", fake_gh)
    monkeypatch.setattr(oa, "COMMITS", {})
    polls = int(HOUR / oa.WAIT_FOR_PR_EVERY)
    seen: dict = {}
    for _ in range(polls):
        assert oa.verdict_outcome(5, oa.time.monotonic() + 30, None, seen) is None
    verdict_calls = len(asked)
    asked.clear()
    for _ in range(polls):
        assert oa.gate_outcome(5, oa.time.monotonic() + 30) is None
    # was 4+ calls every 30 s (480+/h); now at most 1 per poll for verdict (+ one full look), 3 for gate
    assert verdict_calls <= polls + 4
    assert len(asked) <= 3 * polls + 1


def test_head_read_uses_shared_cache(monkeypatch):
    seen = []
    monkeypatch.setattr(oa, "gh", lambda *a, **k: seen.append(a) or "b" * 40)
    oa.default_head("o/r")
    assert "--cache" in seen[0] and "300s" in seen[0]
