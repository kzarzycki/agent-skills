"""approvals.py: `resolve <pr> <comment id>… [--reply <text>]` replies to each thread's root comment and resolves the
thread, through the cloud proxy's `ccr/comments/<id>/resolve` route in a cloud session and GraphQL's
`resolveReviewThread` on a host; the adapter's `ready` goes through `ccr/ready_for_review` and `ccr/convert_to_draft`
in a cloud session and `gh pr ready` on a host (#1615)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import approvals

REPLIES = "repos/{owner}/{repo}/pulls/7/comments/ID/replies"
RESOLVE = "repos/{owner}/{repo}/pulls/7/ccr/comments/ID/resolve"
THREADS = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "nodes": [
                        {
                            "id": "T1",
                            "comments": {"nodes": [{"databaseId": 11}, {"databaseId": 13}]},
                        },
                        {"id": "T2", "comments": {"nodes": [{"databaseId": 12}]}},
                    ]
                }
            }
        }
    }
}


class Github:
    """`gh` as a fake: every call kept in `calls`, a body posted kept in `posted`, a route in `refused` answered with a
    403 and a GraphQL query answered with THREADS."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.posted: list[str] = []
        self.refused: set[str] = set()

    def __call__(self, *args: str, data: str | None = None) -> str:
        self.calls.append(args)
        if data is not None:
            self.posted.append(data)
        if any(route in " ".join(args) for route in self.refused):
            raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403: refused")
        return (
            json.dumps(THREADS) if "graphql" in args and "reviewThreads" in " ".join(args) else ""
        )

    def routes(self) -> list[str]:
        return [
            next(arg for arg in call if "repos/" in arg)
            for call in self.calls
            if "api" in call and any("repos/" in a for a in call)
        ]


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> Github:
    fake = Github()
    monkeypatch.setattr(approvals.github, "gh", fake)
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.delenv("LOOP_DENY_LIST", raising=False)
    return fake


def in_cloud(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    if on:
        monkeypatch.setenv(approvals.CLOUD, "true")
    else:
        monkeypatch.delenv(approvals.CLOUD, raising=False)


def test_a_cloud_session_replies_then_resolves_each_thread_through_the_proxy_route(
    github: Github, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    in_cloud(monkeypatch, True)
    assert approvals.main(["resolve", "7", "11", "12", "--reply", "Fixed in abc1234."]) == 0
    assert github.routes() == [
        REPLIES.replace("ID", "11"),
        RESOLVE.replace("ID", "11"),
        REPLIES.replace("ID", "12"),
        RESOLVE.replace("ID", "12"),
    ]
    assert not [call for call in github.calls if "graphql" in call]
    resolve = next(call for call in github.calls if RESOLVE.replace("ID", "11") in call)
    assert resolve[:3] == ("api", "-X", "POST")
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2 and "11" in out[0] and "12" in out[1]


def test_without_reply_a_thread_is_only_resolved(
    github: Github, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_cloud(monkeypatch, True)
    assert approvals.main(["resolve", "7", "11"]) == 0
    assert github.routes() == [RESOLVE.replace("ID", "11")]
    assert github.posted == []


def test_a_host_resolves_through_graphql_on_the_thread_holding_the_comment(
    github: Github, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_cloud(monkeypatch, False)
    assert approvals.main(["resolve", "7", "12", "--reply", "Fixed."]) == 0
    assert github.routes()[0] == REPLIES.replace("ID", "12")
    mutation = [call for call in github.calls if any("resolveReviewThread" in a for a in call)]
    assert len(mutation) == 1 and "t=T2" in mutation[0]
    assert not [call for call in github.calls if any("/ccr/" in a for a in call)]


def test_a_comment_in_no_thread_is_refused_on_a_host(
    github: Github, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    in_cloud(monkeypatch, False)
    assert approvals.main(["resolve", "7", "99"]) == 1
    assert "99" in capsys.readouterr().out


def test_a_refused_resolve_exits_1_naming_the_thread_and_the_others_still_resolve(
    github: Github, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    in_cloud(monkeypatch, True)
    github.refused.add(RESOLVE.replace("ID", "11"))
    assert approvals.main(["resolve", "7", "11", "12"]) == 1
    out = capsys.readouterr().out
    assert "11" in out and "refused" in out
    assert RESOLVE.replace("ID", "12") in github.routes()


def test_the_reply_goes_through_the_deny_list_before_anything_is_posted_or_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(
        approvals.subprocess,
        "run",
        lambda command, **_kw: calls.append(command) or subprocess.CompletedProcess(command, 0, ""),
    )
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    monkeypatch.setattr(approvals, "pack_behind", lambda _script: None)
    in_cloud(monkeypatch, True)
    deny = tmp_path / "deny.txt"
    deny.write_text("Acme-Widgets\n")
    monkeypatch.setenv("LOOP_DENY_LIST", str(deny))
    assert approvals.main(["resolve", "7", "11", "--reply", "Seen in Acme-Widgets."]) == 1
    assert "names `Acme-Widgets` from the deny list" in capsys.readouterr().out
    assert calls == []


def test_ready_uses_the_proxy_routes_in_a_cloud_session_and_gh_pr_ready_on_a_host(
    github: Github, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_cloud(monkeypatch, True)
    approvals.github.ready(7)
    approvals.github.ready(7, undo=True)
    assert github.routes() == [
        "repos/{owner}/{repo}/pulls/7/ccr/ready_for_review",
        "repos/{owner}/{repo}/pulls/7/ccr/convert_to_draft",
    ]
    assert not [call for call in github.calls if call[0] == "pr"]
    github.calls.clear()
    in_cloud(monkeypatch, False)
    approvals.github.ready(7)
    approvals.github.ready(7, undo=True)
    assert github.calls == [("pr", "ready", "7"), ("pr", "ready", "--undo", "7")]
