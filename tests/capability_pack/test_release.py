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
from tools.capability_pack.release import (
    check_changelog_names,
    cut_release,
    release_tags,
    verify_release,
)

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


def test_a_commit_tagged_only_next_passes_the_tag_check_and_counts_as_the_last_release(
    tmp_path: Path,
) -> None:
    """#2678: `-next` tags are releases: the tag check accepts them, and the next version moves past them."""
    from tools.capability_pack.qualify import validate_release_candidate
    from tools.capability_pack.release import released_versions

    repo = _repository(tmp_path)
    _cut_and_commit(repo, "minor")
    _git(repo, "tag", "alpha-v0.2.0-next")
    with pytest.raises(ConfigurationError, match="beta-v0.3.0 is not tagged"):
        validate_release_candidate(repo / "alpha", "alpha-v0.2.0-next")
    _git(repo, "tag", "beta-v0.3.0-next")
    validate_release_candidate(repo / "alpha", "alpha-v0.2.0-next")
    validate_release_candidate(repo / "beta", "beta-v0.3.0-next")
    assert released_versions(repo)["alpha"] == "0.2.0"
    with pytest.raises(ConfigurationError, match="must match"):
        validate_release_candidate(repo / "alpha", "alpha-v0.2.0-rc")


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


def _adopt_repository(tmp_path: Path, with_adopt: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    entry = "- alpha: new key (#5)"
    if with_adopt:
        entry += "\nadopt: In docs/agents/gatekeeper.md add `select:`.\n  Then run `mise run sync`."
    _package(repo, "alpha", "0.1.0", {"5": entry})
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "tag", "alpha-v0.1.0")
    return repo


def test_cut_release_dry_run_prints_the_section_and_writes_nothing(tmp_path: Path, capsys) -> None:
    repo = _adopt_repository(tmp_path, with_adopt=False)
    assert cli.main(["cut-release", "--root", str(repo), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "alpha 0.1.1 (5)" in out and "- alpha: new key (#5)" in out
    assert _git(repo, "status", "--porcelain") == ""


def test_an_adopt_part_becomes_an_adopt_in_projects_section(tmp_path: Path, capsys) -> None:
    repo = _adopt_repository(tmp_path, with_adopt=True)
    assert cli.main(["cut-release", "--root", str(repo), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert (
        "- alpha: new key (#5)\n\n### Adopt in projects\n\n"
        "- In docs/agents/gatekeeper.md add `select:`.\n  Then run `mise run sync`."
    ) in out
    assert "adopt:" not in out
    assert _git(repo, "status", "--porcelain") == ""
    cut_release(repo, today=TODAY)
    assert "### Adopt in projects" in (repo / "alpha" / "CHANGELOG.md").read_text()


def test_no_adopt_part_means_no_adopt_section(tmp_path: Path, capsys) -> None:
    repo = _adopt_repository(tmp_path, with_adopt=False)
    cut_release(repo, today=TODAY)
    assert "Adopt in projects" not in (repo / "alpha" / "CHANGELOG.md").read_text()


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


def test_an_apm_only_package_on_its_first_release_is_cut_and_tagged(tmp_path: Path) -> None:
    """`engineering-hooks` has no plugin manifest and was never tagged, so no release moves its version (#2683):
    the release still folds it, tags it and passes the release check, since `engineering` depends on its tag."""
    from tools.capability_pack.qualify import validate_release_candidate

    repo = _repository(tmp_path)
    hooks = repo / "hooks"
    _package(repo, "hooks", "0.1.0", {"5": "- hooks: first (#5)"})
    (hooks / ".claude-plugin" / "plugin.json").unlink()
    (hooks / ".claude-plugin").rmdir()
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add an apm-only package")
    base = _git(repo, "rev-parse", "HEAD")
    _cut_and_commit(repo)

    releases = verify_release(repo, base)
    assert ("hooks", "0.1.0") in [(r.package, r.version) for r in releases]
    assert "- hooks: first (#5)" in (hooks / "CHANGELOG.md").read_text()
    tags = release_tags(repo)
    assert "hooks-v0.1.0" in tags
    for tag in tags:
        _git(repo, "tag", tag)
    validate_release_candidate(hooks, "hooks-v0.1.0")


def test_an_apm_only_package_is_found_versioned_bumped_and_tagged_beside_its_dependent(
    tmp_path: Path,
) -> None:
    """A package with no plugin manifest keeps its version in `apm.yml` alone: a later release bumps it there, and
    every release tags the dependent and the package on one commit, so `^0.1.0` resolves (#2683)."""
    from tools.capability_pack.release import packages

    repo = _repository(tmp_path)
    _package(repo, "hooks", "0.1.0", {"5": "- hooks: first (#5)"})
    (repo / "hooks" / ".claude-plugin" / "plugin.json").unlink()
    (repo / "hooks" / ".claude-plugin").rmdir()
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add")
    assert "hooks" in [p.name for p in packages(repo)]
    _cut_and_commit(repo)
    assert {"alpha-v0.1.1", "hooks-v0.1.0"} <= set(
        release_tags(repo)
    )  # first cut: the version no cut moves
    _git(repo, "tag", "hooks-v0.1.0")
    (repo / "hooks" / "changelog.d" / "9.md").write_text("- hooks: later (#9)\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "entry")
    _cut_and_commit(repo)
    assert "version: 0.1.1  # bumped by the release" in (repo / "hooks" / "apm.yml").read_text()
    assert "hooks-v0.1.1" in release_tags(repo)


def test_release_tags_skips_a_plugin_only_package(tmp_path: Path) -> None:
    """A directory with a plugin manifest and no `apm.yml` is no APM release: its manifest change names no tag and
    raises nothing, where reading its version would fail (#2683)."""
    repo = _repository(tmp_path)
    plugin_only = repo / "pluginonly" / ".claude-plugin"
    plugin_only.mkdir(parents=True)
    (plugin_only / "plugin.json").write_text(json.dumps({"name": "pluginonly", "version": "1.0.0"}))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "a plugin-only package")
    assert release_tags(repo) == []


def test_changelog_check_refuses_a_misnamed_entry_with_the_cuts_message(
    tmp_path: Path, capsys
) -> None:
    repo = _repository(tmp_path)
    assert cli.main(["changelog-check", "--root", str(repo)]) == 0
    (repo / "gamma" / "changelog.d" / "foo.md").write_text("- gamma: stray\n")
    assert cli.main(["changelog-check", "--root", str(repo)]) == 2
    message = "gamma/changelog.d entries must be named <issue>.md: foo.md"
    assert message in capsys.readouterr().err
    with pytest.raises(ConfigurationError, match="must be named <issue>.md: foo.md"):
        cut_release(repo)  # the cut refuses with the same rule


def test_the_repos_own_changelog_entries_are_named_for_issues() -> None:
    check_changelog_names(Path(__file__).resolve().parents[2])
