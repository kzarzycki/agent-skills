from __future__ import annotations

import json
import subprocess

from tools.capability_pack.github import (
    ISSUE_MARKER,
    ISSUE_TITLE,
    finalize_publication,
    normalize_incomplete_publication,
    reconcile_blocked_issue,
    reconcile_draft_pr,
    validate_final_state,
)
from tools.capability_pack.outcome import new_attempt, write_result


def test_blocked_issue_is_created_then_updated_without_duplication(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="blocked", code="patch_rejected", phase="patch")
    write_result(tmp_path, result)
    calls = []
    existing = []

    def runner(arguments):
        calls.append(arguments)
        if arguments[:2] == ["issue", "list"]:
            return json.dumps(existing)
        if arguments[:2] == ["issue", "create"]:
            existing.append({"number": 17, "state": "OPEN", "title": ISSUE_TITLE})
            return "https://github.test/issues/17"
        return ""

    reconcile_blocked_issue(tmp_path / "result.json", "run", "artifact", runner)
    reconcile_blocked_issue(tmp_path / "result.json", "run-2", "artifact-2", runner)
    assert sum(call[:2] == ["issue", "create"] for call in calls) == 1
    assert sum(call[:2] == ["issue", "edit"] for call in calls) == 1
    assert ISSUE_MARKER in next(
        call[call.index("--body") + 1] for call in calls if call[:2] == ["issue", "create"]
    )


def test_no_update_closes_stale_blocked_issue(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="no_update", code="no_update")
    write_result(tmp_path, result)
    calls = []

    def runner(arguments):
        calls.append(arguments)
        return (
            json.dumps([{"number": 17, "state": "OPEN", "title": ISSUE_TITLE}])
            if arguments[:2] == ["issue", "list"]
            else ""
        )

    stored = reconcile_blocked_issue(tmp_path / "result.json", "run", "artifact", runner)
    assert stored["reporting"] == {"issue": "closed", "issue_number": 17}
    assert any(call[:2] == ["issue", "close"] for call in calls)


def test_reporting_failure_is_finalized_and_fails_allowlist(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="no_update", code="no_update")
    write_result(tmp_path, result)

    def fail(_arguments):
        raise OSError("offline")

    stored = reconcile_blocked_issue(tmp_path / "result.json", "run", "artifact", fail)
    assert stored["outcome"] == "internal_error"
    assert stored["code"] == "issue_reporting_failed"
    assert validate_final_state(tmp_path / "result.json", "qualify") is False


def test_publication_state_machine_blocks_token_and_pr_failures(tmp_path) -> None:
    for candidate_outcome, token_outcome, token_present, proposal_outcome, code in (
        ("failure", "skipped", False, "skipped", "candidate_transfer_failed"),
        ("success", "failure", False, "skipped", "app_token_failed"),
        ("success", "success", False, "skipped", "app_credentials_missing"),
        ("success", "success", True, "failure", "pr_publication_failed"),
        ("success", "success", True, "success", "pr_not_created"),
    ):
        result = new_attempt("1" * 40)
        result.update(
            outcome="qualified",
            code="candidate_qualified",
            gates=[{"name": "tests", "status": "pass", "detail": None}],
        )
        write_result(tmp_path, result)
        stored = finalize_publication(
            tmp_path / "result.json",
            mode="publish",
            candidate_outcome=candidate_outcome,
            token_outcome=token_outcome,
            token_present=token_present,
            proposal_outcome=proposal_outcome,
            branch=None,
            pull_request=None,
        )
        assert stored["outcome"] == "blocked"
        assert stored["code"] == code


def test_incomplete_publication_is_normalized_before_reporting(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="qualified", code="candidate_qualified")
    write_result(tmp_path, result)
    stored = normalize_incomplete_publication(tmp_path / "result.json", "publish")
    assert stored["outcome"] == "internal_error"
    assert stored["code"] == "incomplete_publication"


def test_issue_search_filters_to_the_exact_stable_title(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="blocked", code="patch_rejected", phase="patch")
    write_result(tmp_path, result)
    calls = []

    def runner(arguments):
        calls.append(arguments)
        if arguments[:2] == ["issue", "list"]:
            return json.dumps([{"number": 8, "state": "OPEN", "title": f"{ISSUE_TITLE} old"}])
        if arguments[:2] == ["issue", "create"]:
            return "https://github.test/issues/9"
        return ""

    stored = reconcile_blocked_issue(tmp_path / "result.json", "run", "artifact", runner)
    assert stored["reporting"] == {"issue": "created", "issue_number": 9}
    assert any(call[:2] == ["issue", "create"] for call in calls)


def test_draft_is_the_only_publishing_success_state(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(
        outcome="qualified",
        code="candidate_qualified",
        source_tag="v1.2.4",
        source_commit="2" * 40,
        gates=[
            {"name": name, "status": "pass", "detail": None}
            for name in (
                "locked-vendoring",
                "repository-tests",
                "package-tests",
                "whitespace",
            )
        ],
    )
    write_result(tmp_path, result)
    finalize_publication(
        tmp_path / "result.json",
        mode="publish",
        candidate_outcome="success",
        token_outcome="success",
        token_present=True,
        proposal_outcome="success",
        branch="automation/engineering-upstream",
        pull_request=23,
    )
    assert validate_final_state(tmp_path / "result.json", "publish") is True


def _completed(arguments, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)


def test_draft_reconciliation_commits_pushes_and_records_created_pr(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="qualified", code="candidate_qualified")
    write_result(tmp_path, result)
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

    stored = reconcile_draft_pr(
        tmp_path,
        branch="automation/engineering-upstream",
        title="refresh",
        body="body",
        commit_message="refresh",
        result_path=tmp_path / "result.json",
        command_runner=runner,
    )
    assert stored["publication"]["state"] == "draft_ready"
    assert stored["publication"]["pull_request"] == 31
    assert stored["publication"]["attempts"] == [
        {
            "state": "draft_ready",
            "branch": "automation/engineering-upstream",
            "pull_request": 31,
        }
    ]
    commands = [arguments for arguments, _ in calls]
    assert ["git", "commit", "-m", "refresh"] in commands
    assert any(arguments[:2] == ["git", "push"] for arguments in commands)
    assert any(arguments[:3] == ["gh", "pr", "create"] for arguments in commands)


def test_pr_failure_after_branch_write_is_durable_and_fails_closed(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="qualified", code="candidate_qualified")
    write_result(tmp_path, result)

    def runner(arguments, _repository):
        if arguments[:4] == ["git", "diff", "--cached", "--quiet"]:
            return _completed(arguments, 0)
        if arguments[:4] == ["gh", "pr", "list", "--state"]:
            return _completed(arguments, stdout="[]")
        if arguments[:3] == ["gh", "pr", "create"]:
            return _completed(arguments, 1, stderr="API offline")
        return _completed(arguments)

    stored = reconcile_draft_pr(
        tmp_path,
        branch="automation/engineering-upstream",
        title="refresh",
        body="body",
        commit_message="refresh",
        result_path=tmp_path / "result.json",
        command_runner=runner,
    )
    assert stored["outcome"] == "blocked"
    assert stored["code"] == "branch_written_pr_failed"
    assert stored["publication"]["state"] == "branch_written_pr_failed"
    assert stored["publication"]["attempts"][0]["state"] == "branch_written_pr_failed"
    finalized = finalize_publication(
        tmp_path / "result.json",
        mode="publish",
        candidate_outcome="success",
        token_outcome="success",
        token_present=True,
        proposal_outcome="failure",
        branch=None,
        pull_request=None,
    )
    assert finalized["code"] == "branch_written_pr_failed"


def test_existing_pr_is_updated_and_returned_to_draft_without_new_commit(tmp_path) -> None:
    calls = []

    def runner(arguments, _repository):
        calls.append(arguments)
        if arguments[:4] == ["git", "diff", "--cached", "--quiet"]:
            return _completed(arguments, 0)
        if arguments[:4] == ["gh", "pr", "list", "--state"]:
            return _completed(arguments, stdout='[{"number":44,"isDraft":false}]')
        return _completed(arguments)

    stored = reconcile_draft_pr(
        tmp_path,
        branch="automation/engineering-consumer-sync",
        title="adopt",
        body="body",
        commit_message="adopt",
        command_runner=runner,
    )
    assert stored["publication"]["pull_request"] == 44
    assert not any(arguments[:2] == ["git", "commit"] for arguments in calls)
    assert ["gh", "pr", "edit", "44", "--title", "adopt", "--body", "body"] in calls
    assert ["gh", "pr", "ready", "--undo", "44"] in calls
