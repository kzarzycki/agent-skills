"""The one-run release (#1861): `cut-release` folds every package, `release-verify` refuses anything but that fold."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.capability_pack import cli
from tools.capability_pack.qualify import ConfigurationError
from tools.capability_pack.release import cut_release, release_tags, verify_release

TODAY = datetime.date(2026, 11, 22)


def _git(repo: Path, *arguments: str) -> str:
    environment = os.environ | {
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    return subprocess.run(
        ["git", *arguments], cwd=repo, env=environment, check=True, capture_output=True, text=True
    ).stdout.strip()


def _package(repo: Path, name: str, version: str, entries: dict[str, str]) -> None:
    package = repo / name
    (package / ".claude-plugin").mkdir(parents=True)
    (package / "changelog.d").mkdir()
    # a comment and key order a YAML dump would lose: the version writer changes the version line only
    (package / "apm.yml").write_text(
        f"name: {name}\nversion: {version}  # bumped by the release\ndescription: '{name} package'\n"
    )
    (package / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": version, "description": "x"}, indent=2) + "\n"
    )
    (package / "README.md").write_text(
        f"dependencies:\n  apm:\n    - git: kzarzycki/agent-skills/{name}\n      ref: ^{version}\n"
    )
    (package / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## Unreleased\n\nNew entries are files in changelog.d/.\n\n## {version} - 2026-01-01\n\n- old\n"
    )
    (package / "changelog.d" / "README.md").write_text("# Unreleased changelog entries\n")
    for issue, text in entries.items():
        (package / "changelog.d" / f"{issue}.md").write_text(text + "\n")


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _package(repo, "alpha", "0.1.0", {"12": "- alpha: second (#12)", "3": "- alpha: first (#3)"})
    _package(repo, "beta", "0.2.0", {"7": "- beta: only (#7)"})
    _package(repo, "gamma", "1.0.0", {})  # nothing pending: left alone
    (repo / "other.txt").write_text("not a package\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    for tag in ("alpha-v0.1.0", "beta-v0.2.0", "gamma-v1.0.0"):
        _git(repo, "tag", tag)
    return repo


def _cut_and_commit(repo: Path, magnitude: str = "patch") -> str:
    cut_release(repo, magnitude=magnitude, today=TODAY)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "chore(release): alpha, beta")
    return _git(repo, "rev-parse", "HEAD")


def test_cut_release_folds_every_package_with_entries(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    releases = cut_release(repo, today=TODAY)

    assert [(r.package, r.version, r.entries) for r in releases] == [
        ("alpha", "0.1.1", ("3", "12")),
        ("beta", "0.2.1", ("7",)),
    ]
    alpha = repo / "alpha"
    assert (alpha / "CHANGELOG.md").read_text() == (
        "# Changelog\n\n## Unreleased\n\nNew entries are files in changelog.d/.\n\n"
        "## 0.1.1 - 2026-11-22\n\n- alpha: first (#3)\n- alpha: second (#12)\n\n"
        "## 0.1.0 - 2026-01-01\n\n- old\n"
    )
    assert sorted(p.name for p in (alpha / "changelog.d").iterdir()) == ["README.md"]
    assert (alpha / "apm.yml").read_text() == (
        "name: alpha\nversion: 0.1.1  # bumped by the release\ndescription: 'alpha package'\n"
    )
    assert json.loads((alpha / ".claude-plugin" / "plugin.json").read_text())["version"] == "0.1.1"
    assert "ref: ^0.1.1" in (alpha / "README.md").read_text()
    gamma = repo / "gamma"
    assert "version: 1.0.0" in (gamma / "apm.yml").read_text()
    assert "1.0.1" not in (gamma / "CHANGELOG.md").read_text()


def test_cut_release_minor_and_refusals(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    assert [r.version for r in cut_release(repo, magnitude="minor", dry_run=True)] == [
        "0.2.0",
        "0.3.0",
    ]
    assert _git(repo, "status", "--porcelain") == ""  # a dry run writes nothing
    _cut_and_commit(repo)
    with pytest.raises(ConfigurationError, match="nothing to release"):
        cut_release(repo)


def test_verify_accepts_the_fold_and_its_tags_pass_release_check(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _cut_and_commit(repo, "minor")

    releases = verify_release(repo, base)
    assert [(r.package, r.version) for r in releases] == [("alpha", "0.2.0"), ("beta", "0.3.0")]
    tags = release_tags(repo)
    assert tags == ["alpha-v0.2.0", "beta-v0.3.0"]

    from tools.capability_pack.qualify import validate_release_candidate

    _git(repo, "tag", "alpha-v0.2.0")
    with pytest.raises(ConfigurationError, match="beta-v0.3.0 is not tagged"):
        validate_release_candidate(repo / "alpha", "alpha-v0.2.0")
    _git(repo, "tag", "beta-v0.3.0")
    for tag in tags:
        validate_release_candidate(repo / tag.split("-v")[0], tag)


@pytest.mark.parametrize(
    "edit",
    [
        "other.txt",  # a file outside any package
        "alpha/CHANGELOG.md",  # a reworded release section
        "alpha/apm.yml",  # a version no fold picks, set in both manifests
        "beta/changelog.d/7.md",  # an entry left behind
    ],
)
def test_verify_refuses_a_hand_edit_beyond_the_fold(tmp_path: Path, edit: str) -> None:
    repo = _repository(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    cut_release(repo, today=TODAY)
    path = repo / edit
    if edit.endswith("apm.yml"):
        for manifest in (path, path.parent / ".claude-plugin" / "plugin.json"):
            manifest.write_text(manifest.read_text().replace("0.1.1", "0.1.5"))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((path.read_text() if path.exists() else "") + "hand edit\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "chore(release): edited")

    with pytest.raises(ConfigurationError, match="is not the release cut"):
        verify_release(repo, base)


def test_verify_refuses_a_release_that_leaves_a_package_out(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    cut_release(repo, today=TODAY)
    _git(repo, "add", "alpha")  # beta's fold is not committed
    _git(repo, "commit", "-m", "chore(release): alpha only")
    _git(repo, "stash", "--include-untracked")

    with pytest.raises(ConfigurationError, match="beta/"):
        verify_release(repo, base)


def test_cli_cut_and_verify(tmp_path: Path, capsys) -> None:
    repo = _repository(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    assert cli.main(["cut-release", "--root", str(repo), "--magnitude", "minor"]) == 0
    assert capsys.readouterr().out.splitlines() == ["alpha 0.2.0 (3 12)", "beta 0.3.0 (7)"]
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "chore(release)")
    assert cli.main(["release-verify", "--root", str(repo), "--base", base]) == 0
    assert "is the release cut of" in capsys.readouterr().out
    (repo / "other.txt").write_text("edit\n")
    _git(repo, "commit", "-am", "hand edit")
    assert cli.main(["release-verify", "--root", str(repo), "--base", base]) == 2
    assert "other.txt" in capsys.readouterr().err
