from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.capability_pack import cli, release
from tools.capability_pack.qualify import validate_release_candidate

CHANGELOG = """# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.4.1 - 2026-11-01

- An older entry (#7).
"""

ENTRIES = {
    "120": "- Entry of issue 120 (#120).\n",
    "9": "- Entry of issue 9 (#9).\n",
    "45": "- Entry of issue 45, line one\n  continued (#45).\n",
}


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    package = repository / "engineering"
    (package / ".claude-plugin").mkdir(parents=True)
    (package / "tests" / "consumer").mkdir(parents=True)
    (package / "changelog.d").mkdir()
    (package / "apm.yml").write_text(
        yaml.safe_dump({"name": "engineering", "version": "0.4.1"}, sort_keys=False)
    )
    (package / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "engineering", "version": "0.4.1"}, indent=2) + "\n"
    )
    (package / "tests" / "consumer" / "apm.yml").write_text(
        yaml.safe_dump(
            {
                "name": "engineering-consumer",
                "dependencies": {
                    "apm": [{"git": "kzarzycki/agent-skills/engineering", "ref": "^0.4.1"}]
                },
            },
            sort_keys=False,
        )
    )
    (package / "CHANGELOG.md").write_text(CHANGELOG)
    (package / "changelog.d" / "README.md").write_text("# Unreleased changelog entries\n")
    for issue, text in ENTRIES.items():
        (package / "changelog.d" / f"{issue}.md").write_text(text)
    _git(repository, "init", "-q", "-b", "main")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "base")
    return package


def _snapshot(package: Path) -> dict[str, str]:
    return {
        str(path.relative_to(package)): path.read_text()
        for path in sorted(package.rglob("*"))
        if path.is_file()
    }


FOLDED = (
    "## 0.4.2 - 2026-11-21\n\n"
    "- Entry of issue 9 (#9).\n"
    "- Entry of issue 45, line one\n  continued (#45).\n"
    "- Entry of issue 120 (#120).\n"
)


def _run(package: Path, *arguments: str) -> int:
    return cli.main(["cut-release", str(package), *arguments])


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    original = release.cut_release

    def dated(*args, **kwargs):
        kwargs.setdefault("today", datetime.date(2026, 11, 21))
        return original(*args, **kwargs)

    monkeypatch.setattr(cli, "cut_release", dated)


def test_dry_run_prints_version_and_section_and_writes_nothing(
    package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catch a dry run that writes, or that prints something other than what a real run folds."""
    _git(package.parent, "tag", "engineering-v0.4.1")
    before = _snapshot(package)

    assert _run(package, "--dry-run") == 0

    assert _snapshot(package) == before
    assert capsys.readouterr().out == "version: 0.4.2\n" + FOLDED


def test_cut_release_folds_in_issue_order_deletes_entries_and_sets_version(
    package: Path,
) -> None:
    """Catch entries folded in name order, left behind, or a version release-check refuses."""
    _git(package.parent, "tag", "engineering-v0.4.1")

    assert _run(package) == 0

    changelog = (package / "CHANGELOG.md").read_text()
    unreleased, rest = changelog.split("## 0.4.2", 1)
    assert "them here.\n\n" in unreleased
    assert "## 0.4.2" + rest == FOLDED + "\n## 0.4.1 - 2026-11-01\n\n- An older entry (#7).\n"
    assert sorted(path.name for path in (package / "changelog.d").iterdir()) == ["README.md"]
    assert yaml.safe_load((package / "apm.yml").read_text())["version"] == "0.4.2"
    plugin = json.loads((package / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == "0.4.2"
    consumer = yaml.safe_load((package / "tests" / "consumer" / "apm.yml").read_text())
    assert consumer["dependencies"]["apm"][0]["ref"] == "^0.4.2"
    _git(package.parent, "add", "-A")
    _git(package.parent, "commit", "-q", "-m", "release")
    validate_release_candidate(package, "engineering-v0.4.2")


def test_entries_still_under_unreleased_stay_above_the_release(package: Path) -> None:
    """Catch a fold that lands above a bullet the README says stays under Unreleased."""
    changelog = CHANGELOG.replace("them here.\n", "them here.\n\n- Still unreleased (#3).\n")
    (package / "CHANGELOG.md").write_text(changelog)

    assert _run(package, "--version", "0.5.0") == 0

    text = (package / "CHANGELOG.md").read_text()
    assert text.index("- Still unreleased (#3).") < text.index("## 0.5.0 - 2026-11-21")
    assert text.index("## 0.5.0") < text.index("## 0.4.1")


def test_empty_changelog_d_refuses_and_writes_nothing(
    package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catch a release cut with nothing to release."""
    for issue in ENTRIES:
        (package / "changelog.d" / f"{issue}.md").unlink()
    before = _snapshot(package)

    assert _run(package) != 0

    assert _snapshot(package) == before
    error = capsys.readouterr().err
    assert "nothing to release" in error
    assert len(error.strip().splitlines()) == 1


def test_untagged_version_is_kept_and_tagged_version_bumps_patch(package: Path) -> None:
    """Catch a second bump over a version the routine already set, or a reuse of a shipped one."""
    assert release.release_version(package) == "0.4.1"
    _git(package.parent, "tag", "engineering-v0.4.1")
    assert release.release_version(package) == "0.4.2"
    assert release.release_version(package, "1.0.0") == "1.0.0"
    with pytest.raises(release.ConfigurationError, match="already tagged"):
        release.release_version(package, "0.4.1")
