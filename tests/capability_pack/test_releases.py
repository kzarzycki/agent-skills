from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.capability_pack.releases import select_release


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def releases(tmp_path: Path) -> tuple[Path, list[str]]:
    repository = tmp_path / "upstream"
    repository.mkdir()
    git(repository, "init", "-q")
    git(repository, "config", "user.email", "fixture@example.test")
    git(repository, "config", "user.name", "Fixture")
    commits = []
    for index in range(4):
        (repository / "content").write_text(str(index))
        git(repository, "add", "content")
        git(repository, "commit", "-qm", f"commit {index}")
        commits.append(git(repository, "rev-parse", "HEAD"))
    # Creation order intentionally differs from SemVer order; exercise both tag kinds.
    git(repository, "tag", "v1.3.0", commits[2])
    git(repository, "tag", "-a", "v1.2.0", "-m", "annotated", commits[1])
    git(repository, "tag", "v2.0.0-rc.1", commits[3])
    return repository, commits


def test_selects_highest_stable_semver_and_peels_tags(releases) -> None:
    repository, commits = releases
    selected = select_release(repository, commits[0])
    assert (selected.state, selected.tag, selected.commit) == (
        "candidate",
        "v1.3.0",
        commits[2],
    )
    assert selected.ignored_tags == ("v2.0.0-rc.1",)


def test_pin_ahead_of_highest_stable_release_never_rolls_back(releases) -> None:
    repository, commits = releases
    selected = select_release(repository, commits[3])
    assert selected.state == "no_eligible_update"
    assert selected.commit == commits[2]


def test_newest_stable_annotated_tag_is_peeled(releases) -> None:
    repository, commits = releases
    git(repository, "tag", "-a", "v1.4.0", "-m", "newest annotated", commits[3])
    selected = select_release(repository, commits[0])
    assert (selected.state, selected.tag, selected.commit) == (
        "candidate",
        "v1.4.0",
        commits[3],
    )


def test_divergent_highest_release_blocks(tmp_path: Path, releases) -> None:
    repository, commits = releases
    git(repository, "checkout", "-qb", "other", commits[0])
    (repository / "other").write_text("other")
    git(repository, "add", "other")
    git(repository, "commit", "-qm", "diverge")
    divergent = git(repository, "rev-parse", "HEAD")
    git(repository, "tag", "v9.0.0")
    selected = select_release(repository, commits[3])
    assert selected.state == "blocked"
    assert selected.commit == divergent
