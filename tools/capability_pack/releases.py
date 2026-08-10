from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

STABLE_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ReleaseResolutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReleaseSelection:
    state: str
    tag: str | None
    commit: str | None
    previous_commit: str
    ignored_tags: tuple[str, ...] = ()


def _git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        timeout=120,
    )


def select_release(
    repository: Path, previous_commit: str, tag_pattern: str = STABLE_TAG.pattern
) -> ReleaseSelection:
    try:
        selector = re.compile(tag_pattern)
    except re.error as error:
        raise ReleaseResolutionError("invalid_tag_policy", str(error)) from error
    tags = _git(repository, "tag", "--list").stdout.splitlines()
    stable = []
    ignored = []
    for tag in tags:
        match = selector.fullmatch(tag)
        if match:
            stable.append((tuple(int(value) for value in match.groups()), tag))
        else:
            ignored.append(tag)
    if not stable:
        raise ReleaseResolutionError("no_stable_release", "upstream has no stable SemVer tag")
    _, tag = max(stable)
    try:
        commit = _git(repository, "rev-parse", f"{tag}^{{commit}}").stdout.strip()
        _git(repository, "cat-file", "-e", f"{previous_commit}^{{commit}}")
    except subprocess.CalledProcessError as error:
        raise ReleaseResolutionError(
            "release_history_unavailable", "release or pinned commit is unavailable"
        ) from error
    if commit == previous_commit:
        state = "no_update"
    elif (
        _git(
            repository, "merge-base", "--is-ancestor", previous_commit, commit, check=False
        ).returncode
        == 0
    ):
        state = "candidate"
    elif (
        _git(
            repository, "merge-base", "--is-ancestor", commit, previous_commit, check=False
        ).returncode
        == 0
    ):
        state = "no_eligible_update"
    else:
        state = "blocked"
    return ReleaseSelection(state, tag, commit, previous_commit, tuple(sorted(ignored)))


def resolve_release(
    repository_url: str,
    previous_commit: str,
    tag_pattern: str = STABLE_TAG.pattern,
) -> ReleaseSelection:
    temporary = Path(tempfile.mkdtemp(prefix="capability-pack-releases-"))
    repository = temporary / "upstream"
    try:
        _git(temporary, "init", "--quiet", repository.as_posix())
        try:
            _git(repository, "fetch", "--quiet", "--force", "--tags", repository_url)
            if _git(repository, "cat-file", "-e", previous_commit, check=False).returncode:
                _git(repository, "fetch", "--quiet", repository_url, previous_commit)
        except (OSError, subprocess.SubprocessError) as error:
            raise ReleaseResolutionError(
                "release_history_unavailable", "could not fetch complete upstream release history"
            ) from error
        selection = select_release(repository, previous_commit, tag_pattern)
        if selection.state == "blocked":
            raise ReleaseResolutionError(
                "release_history_diverged",
                f"highest stable release {selection.tag} diverges from the current pin",
            )
        return selection
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
