"""`brief --since <sha>` is a reused verifier's brief (#1595): the new head, the diff since its last head and the lead's
triage replies since its last pass, with no findings list and no rerun list, since its conversation holds those."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from approvals_harness import approvals, pull, verdict_on


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@e.x", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_the_delta_brief_has_the_head_the_diff_and_only_the_replies_after_the_last_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("one\n")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-qm", "a")
    since = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "a.txt").write_text("two\n")
    git(tmp_path, "commit", "-qam", "b")
    head = git(tmp_path, "rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    review = verdict_on(since, heading="Verifier (codex), pass 1") | {
        "submittedAt": "2026-01-02T00:00:00Z"
    }
    found = pull(reviews=(review,))
    found["headRefOid"] = head
    lead, other = (
        {"login": approvals.viewer()},
        {"login": "stranger"},
    )  # the account that posts the verdicts
    finding = {
        "body": "**Verifier (codex), pass 1 · F1** (major): a gap\n\nit fails",
        "author": lead,
    }
    found["reviewThreads"] = {
        "nodes": [
            {
                "isResolved": False,
                "comments": {
                    "nodes": [
                        finding,
                        {"body": "old reply", "createdAt": "2026-01-01T00:00:00Z", "author": lead},
                        {
                            "body": "fixed in abc: now bounded",
                            "createdAt": "2026-01-03T00:00:00Z",
                            "author": lead,
                        },
                        {
                            "body": "stranger noise",
                            "createdAt": "2026-01-03T00:00:00Z",
                            "author": other,
                        },
                        {"body": "no time", "author": lead},
                    ]
                },
            },
            {  # a thread that is no finding's: its replies are not triage
                "isResolved": False,
                "comments": {
                    "nodes": [
                        {"body": "nit", "author": lead},
                        {
                            "body": "unrelated reply",
                            "createdAt": "2026-01-03T00:00:00Z",
                            "author": lead,
                        },
                    ]
                },
            },
        ]
    }
    found["comments"] = {
        "nodes": [
            {
                "body": "Unrelated status update",
                "createdAt": "2026-01-03T00:00:00Z",
                "author": lead,
            },
            {
                "body": "Triage of pass 1: F1 fixed",
                "createdAt": "2026-01-03T00:00:00Z",
                "author": lead,
            },
            {"body": "Triage by a stranger", "createdAt": "2026-01-03T00:00:00Z", "author": other},
        ]
    }
    monkeypatch.setattr(approvals, "pull_request", lambda _n: found)
    assert approvals.main(["brief", "7", "--since", since]) == 0
    out = capsys.readouterr().out
    assert f"- Reviewed head: {head}" in out and "pass 2" in out
    assert "-one\n+two" in out
    assert "fixed in abc: now bounded" in out and "Triage of pass 1: F1 fixed" in out
    for left_out in (
        "old reply",
        "stranger noise",
        "no time",
        "unrelated reply",
        "Unrelated status",
        "by a stranger",
    ):
        assert left_out not in out, left_out
    assert "the lead's claims" in out
    assert "Previous findings" not in out and "a gap" not in out and "Rerun" not in out


def test_a_review_with_no_time_shows_no_replies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no timestamp on the last pass's review, a reply can't be told from one the verifier saw: none is shown."""
    monkeypatch.setattr(approvals, "viewer", lambda: "lead")
    found = {
        "comments": {
            "nodes": [
                {
                    "body": "Triage: x",
                    "createdAt": "2026-01-03T00:00:00Z",
                    "author": {"login": "lead"},
                }
            ]
        }
    }
    assert approvals.triage_replies(found, None) == []
    assert approvals.triage_replies(found, "2026-01-01T00:00:00Z") == ["Triage: x"]
