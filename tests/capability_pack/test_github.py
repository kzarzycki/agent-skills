from __future__ import annotations

import subprocess

import pytest

from tools.capability_pack.github import GitHubError, reconcile_draft_pr


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
