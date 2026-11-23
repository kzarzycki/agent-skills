"""A PR's REST file list is read once per run, not once per caller: `loop.py brief` on the REST path called
`pulls/N/files` 30 to 60 times, since each `gh pr list` or GraphQL call emptied the read cache and rest_pull, paths()
and overlaps() each asked again. Only a write, or a wait's read_afresh(), makes the next ask GitHub's."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from approvals_harness import approvals

github = approvals.github


class Hub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        args = tuple(cmd[1:])
        self.calls.append(args)
        path = " ".join(args)
        if "pulls/7/files" in path:
            out = json.dumps({"filename": "a.py", "status": "modified"})
        elif "pulls/7/reviews" in path or "timeline" in path:
            out = ""
        elif path.endswith("pulls/7"):
            out = json.dumps(
                {
                    "node_id": "n", "number": 7, "title": "t", "state": "open", "head": {"ref": "h", "sha": "a" * 40,
                    "repo": {"full_name": "o/r"}}, "base": {"ref": "main", "sha": "b" * 40, "repo": {"full_name": "o/r"}},
                }
            )
        else:
            out = "[]"
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def files(self) -> int:
        return sum("pulls/7/files" in " ".join(call) for call in self.calls)


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> Hub:
    fake = Hub()
    monkeypatch.setattr(github.subprocess, "run", fake)
    monkeypatch.setattr(github, "wait_until", None)
    github.read_afresh()
    return fake


def test_many_callers_in_one_run_read_a_prs_files_once(hub: Hub) -> None:
    for _ in range(5):
        github.pr_changes(7)
        github.gh("pr", "list", "--state", "open")  # empties `reads`, which used to forget the files too
        github.gh("api", "graphql", "-f", "query=query { viewer { login } }")
        try:
            github.rest_pull(7)
        except (KeyError, TypeError):
            pass  # the fake PR answers no more than the files and the PR need
    assert hub.files() == 1, hub.calls


def test_a_write_or_a_wait_makes_the_next_read_github_s(hub: Hub) -> None:
    github.pr_changes(7)
    github.gh("api", "-X", "POST", "repos/{owner}/{repo}/issues/7/comments", "-f", "body=x")
    github.pr_changes(7)
    assert hub.files() == 2
    github.read_afresh()
    github.pr_changes(7)
    assert hub.files() == 3
