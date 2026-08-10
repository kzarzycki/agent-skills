from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.capability_pack.outcome import PIPELINE, load_result, write_result

ISSUE_MARKER = f"<!-- {PIPELINE}:blocked -->"
ISSUE_TITLE = "Engineering upstream refresh blocked"


class GitHubError(RuntimeError):
    pass


def _run(arguments: list[str]) -> str:
    completed = subprocess.run(
        ["gh", *arguments], check=True, capture_output=True, text=True, timeout=60
    )
    return completed.stdout.strip()


def _command(arguments: list[str], repository: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def reconcile_draft_pr(
    repository: Path,
    *,
    branch: str,
    title: str,
    body: str,
    commit_message: str,
    result_path: Path | None = None,
    command_runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]] = _command,
) -> dict[str, Any]:
    """Write a fixed automation branch and reconcile its one draft PR."""
    result = load_result(result_path) if result_path else None

    def run(arguments: list[str], *, check: bool = True) -> str:
        completed = command_runner(arguments, repository)
        if check and completed.returncode:
            raise GitHubError((completed.stderr or completed.stdout or "command failed").strip())
        return completed.stdout.strip()

    branch_written = False
    try:
        run(["git", "config", "user.name", "engineering-updater[bot]"])
        run(["git", "config", "user.email", "engineering-updater[bot]@users.noreply.github.com"])
        run(["git", "add", "--all"])
        if command_runner(["git", "diff", "--cached", "--quiet"], repository).returncode:
            run(["git", "commit", "-m", commit_message])
        run(["gh", "auth", "setup-git"])
        run(
            ["git", "fetch", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"],
            check=False,
        )
        run(["git", "push", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch}"])
        branch_written = True
        matches = json.loads(
            run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--state",
                    "open",
                    "--head",
                    branch,
                    "--json",
                    "number,isDraft",
                ]
            )
            or "[]"
        )
        if len(matches) > 1:
            raise GitHubError("multiple open pull requests use the automation branch")
        if matches:
            number = int(matches[0]["number"])
            run(["gh", "pr", "edit", str(number), "--title", title, "--body", body])
            if not matches[0].get("isDraft"):
                run(["gh", "pr", "ready", "--undo", str(number)])
        else:
            created = run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--draft",
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ]
            )
            number = int(created.rstrip("/").split("/")[-1])
    except Exception as error:
        code = "branch_written_pr_failed" if branch_written else "branch_write_failed"
        if result is None:
            raise GitHubError(f"{code}: {error}") from error
        result.update(outcome="blocked", code=code, phase="publish")
        result["publication"].update(state=code, branch=branch, pull_request=None)
        result["publication"]["attempts"].append({"state": code, "branch": branch})
        result["diagnostics"].append({"code": code, "detail": str(error)})
        write_result(result_path.parent, result)
        return result
    publication = {"state": "draft_ready", "branch": branch, "pull_request": number}
    if result is not None:
        result["publication"].update(publication)
        result["publication"]["attempts"].append(publication.copy())
        write_result(result_path.parent, result)
        return result
    return {"publication": publication}


def issue_body(result: dict[str, Any], run_url: str, artifact_url: str) -> str:
    source = result.get("source_tag") or "unresolved"
    return "\n".join(
        [
            "# Engineering upstream refresh is blocked",
            "",
            f"- Failure: `{result['code']}` during `{result['phase']}`",
            f"- Source: `{source}` / `{result.get('source_commit') or 'unresolved'}`",
            f"- [Workflow run]({run_url})",
            f"- [Evidence artifact]({artifact_url})",
            "",
            "Resolve the diagnostic in the artifact and rerun the workflow.",
            "",
            ISSUE_MARKER,
        ]
    )


def reconcile_blocked_issue(
    result_path: Path,
    run_url: str,
    artifact_url: str,
    runner: Callable[[list[str]], str] = _run,
) -> dict[str, Any]:
    result = load_result(result_path)
    try:
        matches = json.loads(
            runner(
                [
                    "issue",
                    "list",
                    "--state",
                    "all",
                    "--search",
                    f'"{ISSUE_TITLE}" in:title',
                    "--json",
                    "number,state,title",
                ]
            )
            or "[]"
        )
        matches = [item for item in matches if item.get("title") == ISSUE_TITLE]
        if len(matches) > 1:
            raise GitHubError("multiple blocked-intake issues match the stable marker")
        issue = matches[0] if matches else None
        if result["outcome"] in {"blocked", "internal_error"}:
            body = issue_body(result, run_url, artifact_url)
            if issue:
                number = int(issue["number"])
                runner(
                    [
                        "issue",
                        "edit",
                        str(number),
                        "--title",
                        ISSUE_TITLE,
                        "--body",
                        body,
                    ]
                )
                if issue["state"] == "CLOSED":
                    runner(["issue", "reopen", str(number)])
                state = "updated"
            else:
                created = runner(
                    [
                        "issue",
                        "create",
                        "--title",
                        ISSUE_TITLE,
                        "--body",
                        body,
                    ]
                )
                number = int(created.rstrip("/").split("/")[-1])
                state = "created"
            result["reporting"] = {"issue": state, "issue_number": number}
        elif (
            issue
            and issue["state"] == "OPEN"
            and (
                result["outcome"] == "no_update" or result["publication"]["state"] == "draft_ready"
            )
        ):
            number = int(issue["number"])
            comment = (
                "No eligible upstream update remains."
                if result["outcome"] == "no_update"
                else "A qualified draft PR now owns this intake."
            )
            runner(["issue", "close", str(number), "--comment", comment])
            result["reporting"] = {"issue": "closed", "issue_number": number}
    except Exception as error:  # noqa: BLE001 - reporting failure must become durable evidence.
        result["reporting"] = {"issue": "failed", "issue_number": None}
        if result["outcome"] not in {"blocked", "internal_error"}:
            result.update(outcome="internal_error", code="issue_reporting_failed", phase="publish")
        result["diagnostics"].append({"code": "issue_reporting_failed", "detail": str(error)})
    write_result(result_path.parent, result)
    return result


def mark_publication(
    result_path: Path,
    state: str,
    *,
    branch: str | None = None,
    pull_request: int | None = None,
) -> dict[str, Any]:
    result = load_result(result_path)
    result["publication"].update(state=state, branch=branch, pull_request=pull_request)
    if state == "credentials_missing":
        result.update(outcome="blocked", code="app_credentials_missing", phase="publish")
        result["diagnostics"].append({"code": "app_credentials_missing"})
    write_result(result_path.parent, result)
    return result


def finalize_publication(
    result_path: Path,
    *,
    mode: str,
    candidate_outcome: str,
    token_outcome: str,
    token_present: bool,
    proposal_outcome: str,
    branch: str | None,
    pull_request: int | None,
) -> dict[str, Any]:
    result = load_result(result_path)
    if result["publication"]["state"] in {"draft_ready", "branch_written_pr_failed"}:
        write_result(result_path.parent, result)
        return result
    if result["outcome"] != "qualified" or mode in {"qualify", "smoke-fixture"}:
        write_result(result_path.parent, result)
        return result
    if candidate_outcome != "success":
        return _block_publication(result_path, result, "candidate_transfer_failed", "failed")
    if token_outcome == "failure":
        return _block_publication(result_path, result, "app_token_failed", "failed")
    if not token_present:
        return _block_publication(
            result_path, result, "app_credentials_missing", "credentials_missing"
        )
    if proposal_outcome == "failure":
        return _block_publication(result_path, result, "pr_publication_failed", "failed")
    if not pull_request:
        return _block_publication(result_path, result, "pr_not_created", "failed")
    result["publication"].update(state="draft_ready", branch=branch, pull_request=pull_request)
    write_result(result_path.parent, result)
    return result


def _block_publication(
    result_path: Path, result: dict[str, Any], code: str, state: str
) -> dict[str, Any]:
    result.update(outcome="blocked", code=code, phase="publish")
    result["publication"]["state"] = state
    result["diagnostics"].append({"code": code})
    write_result(result_path.parent, result)
    return result


def validate_final_state(result_path: Path, mode: str) -> bool:
    normalize_incomplete_publication(result_path, mode)
    result = load_result(result_path)
    valid = result["reporting"]["issue"] != "failed"
    if result["outcome"] == "no_update":
        valid = valid and result["code"] in {"no_update", "no_eligible_update"}
        valid = valid and bool(result["source_tag"] and result["source_commit"])
    elif result["outcome"] == "qualified":
        expected_gates = (
            ["smoke-marker"]
            if result["code"] in {"publish_smoke_qualified", "smoke_fixture_passed"}
            else ["locked-vendoring", "repository-tests", "package-tests", "whitespace"]
        )
        valid = valid and [gate["name"] for gate in result["gates"]] == expected_gates
        valid = valid and all(gate["status"] == "pass" for gate in result["gates"])
        if result["code"] == "candidate_qualified":
            valid = valid and bool(result["source_tag"] and result["source_commit"])
        if mode in {"publish", "publish-smoke"}:
            valid = valid and result["publication"]["state"] == "draft_ready"
            valid = valid and isinstance(result["publication"]["pull_request"], int)
        else:
            valid = valid and result["publication"]["state"] == "not_requested"
    else:
        valid = False
    if not valid and result["outcome"] not in {"blocked", "internal_error"}:
        result.update(outcome="internal_error", code="incomplete_finalization", phase="publish")
        result["diagnostics"].append({"code": "incomplete_finalization"})
        write_result(result_path.parent, result)
    return valid


def normalize_incomplete_publication(result_path: Path, mode: str) -> dict[str, Any]:
    result = load_result(result_path)
    if (
        result["outcome"] == "qualified"
        and mode in {"publish", "publish-smoke"}
        and (
            result["publication"]["state"] != "draft_ready"
            or not isinstance(result["publication"]["pull_request"], int)
        )
    ):
        result.update(outcome="internal_error", code="incomplete_publication", phase="publish")
        result["diagnostics"].append({"code": "incomplete_publication"})
        write_result(result_path.parent, result)
    return result
