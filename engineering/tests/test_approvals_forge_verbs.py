"""approvals.py: `threads`, `comment`, `show` and `edit`, every forge call a cloud agent makes, each one command on a
host and in a cloud session, where GraphQL answers 403; and a commit-status write in a cloud session fails at once,
naming the host, with no call made (#1637)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from approvals_harness import approvals

CCR_THREADS = "repos/{owner}/{repo}/pulls/7/ccr/review_threads"
COMMENTS = "repos/{owner}/{repo}/pulls/7/comments?per_page=100"
HOST_THREADS = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "totalCount": 2,
                    "nodes": [
                        {
                            "isResolved": False,
                            "path": "a.py",
                            "line": 3,
                            "comments": {
                                "nodes": [{"databaseId": 11, "body": "F1 (major): x\nmore"}]
                            },
                        },
                        {
                            "isResolved": True,
                            "path": "b.py",
                            "line": None,
                            "comments": {"nodes": [{"databaseId": 12, "body": "F2: y"}]},
                        },
                    ],
                }
            }
        }
    }
}


class Github:
    """`gh` as a fake: every call kept in `calls`; the proxy's thread route, the PR's review comments and GraphQL's
    thread query answered; any other call answered with `{}`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str, data: str | None = None) -> str:
        self.calls.append(args)
        joined = " ".join(args)
        if "graphql" in args:
            return json.dumps(HOST_THREADS)
        if CCR_THREADS in joined:
            return json.dumps(
                [
                    {"resolved": False, "path": "a.py", "line": 3, "comment_ids": [11, 13]},
                    {"resolved": True, "path": "b.py", "line": None, "comment_ids": [12]},
                ]
            )
        if COMMENTS in joined:
            return "\n".join(
                json.dumps(each)
                for each in (
                    {"id": 11, "body": "F1 (major): x\nmore", "path": "a.py", "line": 3},
                    {"id": 12, "body": "F2: y", "path": "b.py", "original_line": 9},
                    {"id": 13, "body": "Fixed.", "path": "a.py", "line": 3},
                )
            )
        if "issues/7" in joined and "comments" not in joined:
            return json.dumps({"number": 7, "pull_request": {}})
        if "pulls/7" in joined:
            return json.dumps({"number": 7, "merged": True, "merge_commit_sha": "abc"})
        # the comment's post asks `--jq .html_url`, which gh answers with the URL alone
        return "https://github.com/o/r/pull/7#issuecomment-1\n" if ".html_url" in args else "{}"


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> Github:
    fake = Github()
    monkeypatch.setattr(approvals.github, "gh", fake)
    monkeypatch.setattr(approvals, "one_repo", lambda: None)
    # the harness stubs these two in the gatekeeper's namespace; here they go through the adapter, as in a run
    monkeypatch.setattr(approvals, "comment", approvals.through("tracker", "comment"))
    monkeypatch.setattr(approvals, "post_status", approvals.through("evidence", "post_status"))
    monkeypatch.delenv("LOOP_DENY_LIST", raising=False)
    return fake


def in_cloud(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    if on:
        monkeypatch.setenv(approvals.CLOUD, "true")
    else:
        monkeypatch.delenv(approvals.CLOUD, raising=False)


@pytest.mark.parametrize("cloud", [True, False])
def test_threads_lists_the_open_threads_by_root_comment_id_with_no_graphql_in_the_cloud(
    github: Github, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cloud: bool
) -> None:
    in_cloud(monkeypatch, cloud)
    assert approvals.main(["threads", "7"]) == 0
    assert capsys.readouterr().out.splitlines() == ["11\topen\ta.py:3\tF1 (major): x"]
    graphql = [call for call in github.calls if "graphql" in call]
    assert (not graphql) if cloud else graphql


def test_threads_all_shows_resolved_ones_too(
    github: Github, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    in_cloud(monkeypatch, True)
    assert approvals.main(["threads", "7", "--all"]) == 0
    assert capsys.readouterr().out.splitlines()[1] == "12\tresolved\tb.py:9\tF2: y"


def test_comment_posts_the_file_over_rest_and_prints_its_url(
    github: Github,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    in_cloud(monkeypatch, True)
    report = tmp_path / "report.md"
    report.write_text("DONE: it works.\n")
    assert approvals.main(["comment", "7", str(report)]) == 0
    assert github.calls[-1][:2] == ("api", "repos/{owner}/{repo}/issues/7/comments")
    assert capsys.readouterr().out.strip().endswith("#issuecomment-1")


def test_an_empty_comment_is_refused_before_any_call(
    github: Github, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("\n")
    assert approvals.main(["comment", "7", str(empty)]) == 1
    assert github.calls == []


def test_show_reads_a_pr_over_rest_alone(
    github: Github, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    in_cloud(monkeypatch, False)
    assert approvals.main(["show", "7"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["pull"]["merge_commit_sha"] == "abc"
    assert not [call for call in github.calls if "graphql" in call or call[0] != "api"]


def test_edit_retargets_requests_a_review_drafts_and_closes_over_rest_in_the_cloud(
    github: Github, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_cloud(monkeypatch, True)
    args = ["edit", "7", "--base", "main", "--reviewer", "someone", "--draft", "--close"]
    assert approvals.main(args) == 0
    routes = [next(a for a in call if "repos/" in a) for call in github.calls]
    assert routes == [
        "repos/{owner}/{repo}/pulls/7",
        "repos/{owner}/{repo}/pulls/7/requested_reviewers",
        "repos/{owner}/{repo}/pulls/7/ccr/convert_to_draft",
        "repos/{owner}/{repo}/issues/7",
    ]
    assert ("-f", "base=main") == github.calls[0][4:6]
    assert "state=closed" in github.calls[-1]


def test_edit_without_a_change_is_refused(github: Github) -> None:
    assert approvals.main(["edit", "7"]) == 1
    assert github.calls == []


def test_a_cloud_status_write_makes_no_call_and_names_the_host(
    github: Github, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_cloud(monkeypatch, True)
    with pytest.raises(subprocess.CalledProcessError) as raised:
        approvals.github.post_status("a" * 40, "gate", "Passed")
    assert raised.value.stderr == (
        "a cloud session can't write commit statuses (its GitHub proxy answers 403): the host writes `gate` on "
        + "a" * 40
    )
    assert github.calls == []


def test_the_gate_status_line_says_the_host_writes_it(
    github: Github, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_cloud(monkeypatch, True)
    why = approvals.shown(
        "b" * 40, {"tree": "t" * 40, "head": "b" * 40, "command": "mise run check"}
    )
    assert why is not None and "the host writes `gate`" in why
    assert github.calls == []


def test_a_host_status_write_still_calls_github(
    github: Github, monkeypatch: pytest.MonkeyPatch
) -> None:
    in_cloud(monkeypatch, False)
    approvals.github.post_status("a" * 40, "gate", "Passed")
    assert github.calls[0][1] == "repos/{owner}/{repo}/statuses/" + "a" * 40
