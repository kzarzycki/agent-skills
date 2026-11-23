from __future__ import annotations

import json
import subprocess
import sys
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


# an identity no GitHub account holds: a gatekeeper `bot` section with `branch` counts its commits as the PR author's
UPDATER_NAME = "Pack bump workflow"
UPDATER_EMAIL = "pack-bump-workflow@users.noreply.invalid"


def reconcile_pr(
    repository: Path,
    *,
    branch: str,
    title: str,
    body: str,
    commit_message: str,
    base: str = "main",
    draft: bool = True,
    labels: tuple[str, ...] = (),
    auto_merge: bool = False,
    supersede_prefix: str | None = None,
    command_runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]] = _command,
) -> int:
    """Write `branch` and reconcile its one open PR into `base`; return its number.

    A draft PR stays a draft (an open ready one goes back to draft); a ready one (`draft=False`) is opened ready, or
    marked ready. `labels` are added, `auto_merge` turns on GitHub's auto-merge (squash) where the repository allows
    it, a refusal there only warns, and every other open PR whose head starts with `supersede_prefix` is closed as
    superseded by this one, so one bump at a time stays open."""

    def run(arguments: list[str], *, check: bool = True) -> str:
        completed = command_runner(arguments, repository)
        if check and completed.returncode:
            raise GitHubError((completed.stderr or completed.stdout or "command failed").strip())
        return completed.stdout.strip()

    branch_written = False
    try:
        run(["git", "config", "user.name", UPDATER_NAME])
        run(["git", "config", "user.email", UPDATER_EMAIL])
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
            if draft and not matches[0].get("isDraft"):
                run(["gh", "pr", "ready", "--undo", str(number)])
            elif not draft and matches[0].get("isDraft"):
                run(["gh", "pr", "ready", str(number)])
        else:
            created = run(
                [
                    "gh",
                    "pr",
                    "create",
                    *(["--draft"] if draft else []),
                    "--base",
                    base,
                    "--head",
                    branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ]
            )
            number = int(created.rstrip("/").split("/")[-1])
        for label in labels:
            run(["gh", "pr", "edit", str(number), "--add-label", label])
        if auto_merge:
            merged = command_runner(
                ["gh", "pr", "merge", "--auto", "--squash", str(number)], repository
            )
            if merged.returncode:
                print(
                    f"warning: auto-merge not enabled on #{number}: "
                    f"{(merged.stderr or merged.stdout).strip()}",
                    file=sys.stderr,
                )
        if supersede_prefix:
            others = json.loads(
                run(["gh", "pr", "list", "--state", "open", "--json", "number,headRefName"]) or "[]"
            )
            for other in others:
                if (
                    other["headRefName"].startswith(supersede_prefix)
                    and int(other["number"]) != number
                ):
                    run(
                        [
                            "gh",
                            "pr",
                            "close",
                            str(other["number"]),
                            "--comment",
                            f"Superseded by #{number}.",
                        ]
                    )
    except Exception as error:
        code = "branch_written_pr_failed" if branch_written else "branch_write_failed"
        raise GitHubError(f"{code}: {error}") from error
    return number


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
    return reconcile_pr(
        repository,
        branch=branch,
        title=title,
        body=body,
        commit_message=commit_message,
        command_runner=command_runner,
    )
