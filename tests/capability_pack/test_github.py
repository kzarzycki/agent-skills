from __future__ import annotations

import json
import subprocess

import pytest

from tools.capability_pack.github import (
    UPDATER_EMAIL,
    GitHubError,
    reconcile_draft_pr,
    reconcile_pr,
)


def _completed(arguments, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


def test_draft_reconciliation_commits_pushes_and_returns_created_pr(tmp_path) -> None:
    calls = []

    def runner(arguments, repository):
        calls.append((arguments, repository))
        if arguments[:4] == ["git", "diff", "--cached", "--quiet"]:
            return _completed(arguments, 1)
        if arguments[:4] == ["gh", "pr", "list", "--state"]:
            return _completed(arguments, stdout="[]")
        if arguments[:3] == ["gh", "pr", "create"]:
            return _completed(arguments, stdout="https://github.test/pull/31\n")
        return _completed(arguments)

    number = reconcile_draft_pr(
        tmp_path,
        branch="automation/engineering-consumer-sync",
        title="adopt",
        body="body",
        commit_message="adopt",
        command_runner=runner,
    )
    assert number == 31
    commands = [arguments for arguments, _ in calls]
    assert ["git", "commit", "-m", "adopt"] in commands
    assert any(arguments[:2] == ["git", "push"] for arguments in commands)
    assert any(arguments[:3] == ["gh", "pr", "create"] for arguments in commands)


def test_pr_failure_after_branch_write_fails_closed(tmp_path) -> None:
    def runner(arguments, _repository):
        if arguments[:4] == ["git", "diff", "--cached", "--quiet"]:
            return _completed(arguments, 0)
        if arguments[:4] == ["gh", "pr", "list", "--state"]:
            return _completed(arguments, stdout="[]")
        if arguments[:3] == ["gh", "pr", "create"]:
            return _completed(arguments, 1, stderr="API offline")
        return _completed(arguments)

    with pytest.raises(GitHubError, match="branch_written_pr_failed: API offline"):
        reconcile_draft_pr(
            tmp_path,
            branch="automation/engineering-consumer-sync",
            title="adopt",
            body="body",
            commit_message="adopt",
            command_runner=runner,
        )


def test_existing_pr_is_updated_and_returned_to_draft_without_new_commit(tmp_path) -> None:
    calls = []

    def runner(arguments, _repository):
        calls.append(arguments)
        if arguments[:4] == ["git", "diff", "--cached", "--quiet"]:
            return _completed(arguments, 0)
        if arguments[:4] == ["gh", "pr", "list", "--state"]:
            return _completed(arguments, stdout='[{"number":44,"isDraft":false}]')
        return _completed(arguments)

    number = reconcile_draft_pr(
        tmp_path,
        branch="automation/engineering-consumer-sync",
        title="adopt",
        body="body",
        commit_message="adopt",
        command_runner=runner,
    )
    assert number == 44
    assert not any(arguments[:2] == ["git", "commit"] for arguments in calls)
    assert ["gh", "pr", "edit", "44", "--title", "adopt", "--body", "body"] in calls
    assert ["gh", "pr", "ready", "--undo", "44"] in calls


def _ready_runner(calls, *, existing="[]", others="[]", merge_code=0):
    def runner(arguments, _repository):
        calls.append(arguments)
        if arguments[:4] == ["git", "diff", "--cached", "--quiet"]:
            return _completed(arguments, 1)
        if arguments[:5] == ["gh", "pr", "list", "--state", "open"] and "--head" in arguments:
            return _completed(arguments, stdout=existing)
        if arguments[:5] == ["gh", "pr", "list", "--state", "open"]:
            return _completed(arguments, stdout=others)
        if arguments[:3] == ["gh", "pr", "create"]:
            return _completed(arguments, stdout="https://github.test/pull/50\n")
        if arguments[:3] == ["gh", "pr", "merge"]:
            return _completed(arguments, merge_code, stderr="auto-merge is not allowed")
        return _completed(arguments)

    return runner


def test_a_ready_bump_is_opened_ready_labelled_queued_and_supersedes_older_bumps(
    tmp_path, capsys
) -> None:
    calls = []
    others = json.dumps(
        [
            {"number": 41, "headRefName": "claude/ready-pack-bump-engineering-v0.35.2"},
            {"number": 50, "headRefName": "claude/ready-pack-bump-engineering-v0.35.3"},
            {"number": 9, "headRefName": "claude/ready-other"},
        ]
    )
    number = reconcile_pr(
        tmp_path,
        branch="claude/ready-pack-bump-engineering-v0.35.3",
        base="trunk",
        title="adopt",
        body="body",
        commit_message="adopt",
        draft=False,
        labels=("loop:queued",),
        auto_merge=True,
        supersede_prefix="claude/ready-pack-bump-",
        command_runner=_ready_runner(calls, others=others, merge_code=1),
    )
    assert number == 50
    create = next(arguments for arguments in calls if arguments[:3] == ["gh", "pr", "create"])
    assert "--draft" not in create and create[create.index("--base") + 1] == "trunk"
    assert ["gh", "pr", "edit", "50", "--add-label", "loop:queued"] in calls
    assert ["gh", "pr", "merge", "--auto", "--squash", "50"] in calls
    assert (
        "auto-merge not enabled on #50" in capsys.readouterr().err
    )  # a repo that disallows it only warns
    closed = [arguments[3] for arguments in calls if arguments[:3] == ["gh", "pr", "close"]]
    assert closed == ["41"]
    assert ["git", "config", "user.email", UPDATER_EMAIL] in calls
    assert UPDATER_EMAIL.endswith(".invalid")


def test_an_open_draft_bump_is_marked_ready(tmp_path) -> None:
    calls = []
    reconcile_pr(
        tmp_path,
        branch="b",
        title="t",
        body="x",
        commit_message="m",
        draft=False,
        command_runner=_ready_runner(calls, existing='[{"number":44,"isDraft":true}]'),
    )
    assert ["gh", "pr", "ready", "44"] in calls
    assert not any(arguments[:3] == ["gh", "pr", "close"] for arguments in calls)
