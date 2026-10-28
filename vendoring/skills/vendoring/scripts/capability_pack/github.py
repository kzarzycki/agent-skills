from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path


class GitHubError(RuntimeError):
    pass


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
    command_runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]] = _command,
) -> int:
    """Write a fixed automation branch and reconcile its one draft PR; return its number."""

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
        raise GitHubError(f"{code}: {error}") from error
    return number
