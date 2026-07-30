from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.capability_pack.qualify import ConfigurationError, validate_release_candidate


def _git(repo: Path, *arguments: str) -> None:
    environment = os.environ | {
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    subprocess.run(["git", *arguments], cwd=repo, env=environment, check=True)


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    engineering = repo / "engineering"
    (engineering / ".claude-plugin").mkdir(parents=True)
    (engineering / "apm.yml").write_text(
        yaml.safe_dump({"name": "engineering", "version": "0.2.0"})
    )
    (engineering / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "engineering", "version": "0.2.0"})
    )
    for package in ("research", "workflow"):
        manifest = repo / package / ".claude-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"name": package, "version": "1.0.0"}))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_release_candidate_accepts_matching_package_tag(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    marker = repo / "engineering" / "release.txt"
    marker.write_text("candidate\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "engineering release")

    validate_release_candidate(repo / "engineering", "engineering-v0.2.0")


@pytest.mark.parametrize("manifest", ["apm.yml", ".claude-plugin/plugin.json"])
def test_release_candidate_rejects_manifest_version_mismatch(
    tmp_path: Path,
    manifest: str,
) -> None:
    repo = _repository(tmp_path)
    path = repo / "engineering" / manifest
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        data["version"] = "0.2.1"
        path.write_text(json.dumps(data))
    else:
        data = yaml.safe_load(path.read_text())
        data["version"] = "0.2.1"
        path.write_text(yaml.safe_dump(data))

    with pytest.raises(ConfigurationError, match=Path(manifest).name):
        validate_release_candidate(repo / "engineering", "engineering-v0.2.0")


@pytest.mark.parametrize("other_package", ["research", "workflow"])
def test_release_candidate_rejects_other_package_manifest_change(
    tmp_path: Path,
    other_package: str,
) -> None:
    repo = _repository(tmp_path)
    manifest = repo / other_package / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text())
    data["version"] = "1.0.1"
    manifest.write_text(json.dumps(data))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "mixed release")

    with pytest.raises(ConfigurationError, match=other_package):
        validate_release_candidate(repo / "engineering", "engineering-v0.2.0")


@pytest.mark.parametrize(
    "tag",
    ["v0.2.0", "engineering-0.2.0", "engineering-v0.2", "engineering-v0.2.0-beta"],
)
def test_release_candidate_rejects_invalid_tag_shape(tmp_path: Path, tag: str) -> None:
    repo = _repository(tmp_path)

    with pytest.raises(ConfigurationError, match="tag"):
        validate_release_candidate(repo / "engineering", tag)
