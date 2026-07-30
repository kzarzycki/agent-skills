from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

from tools.capability_pack.qualify import BreakingDriftError, QualificationError, qualify


def _add_leaf(package: Path, destination: str, source: str) -> None:
    manifest = package / "vendir.yml"
    config = yaml.safe_load(manifest.read_text())
    config["directories"].append(
        {
            "path": f"skills/{destination}",
            "contents": [
                {
                    "path": ".",
                    "git": {
                        "url": "https://example.invalid/upstream.git",
                        "ref": "origin/main",
                    },
                    "includePaths": [f"{source}/**/*"],
                    "excludePaths": [],
                    "legalPaths": [],
                    "newRootPath": source,
                }
            ],
        }
    )
    manifest.write_text(yaml.safe_dump(config, sort_keys=False))
    lock = package / "vendir.lock.yml"
    locked = yaml.safe_load(lock.read_text())
    locked["directories"].append(
        {
            "path": f"skills/{destination}",
            "contents": [{"path": ".", "git": {"sha": "1" * 40}}],
        }
    )
    lock.write_text(yaml.safe_dump(locked, sort_keys=False))


def test_new_upstream_skill_is_reported_and_promoted(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch silently importing a new skill without update evidence."""
    beta = upstream / "skills" / "engineering" / "beta"
    beta.mkdir()
    (beta / "SKILL.md").write_text("# Beta\n")
    _add_leaf(package, "beta", "skills/engineering/beta")

    result = qualify(package, "update")

    assert result.added_skills == ("beta",)
    assert (package / "skills" / "beta" / "SKILL.md").read_text() == "# Beta\n"


def test_removed_upstream_skill_is_breaking_drift(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch treating an upstream removal or rename as an ordinary update."""
    shutil.rmtree(upstream / "skills" / "engineering" / "alpha")

    with pytest.raises(
        BreakingDriftError, match=r"alpha.*1111111111111111111111111111111111111111"
    ):
        qualify(package, "update")


def test_missing_recorded_legal_file_fails_qualification(package: Path, fake_vendir: Path) -> None:
    """Catch publishing a reconstructed payload without its required license."""
    (package / "LICENSES" / "mattpocock-skills" / "LICENSE").unlink()

    with pytest.raises(QualificationError, match="legal file"):
        qualify(package, "locked")


def test_undeclared_owned_sibling_is_preserved_on_upstream_collision(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch an upstream same-name skill replacing repository-owned behavior."""
    colliding = upstream / "skills" / "engineering" / "context-extractor"
    colliding.mkdir()
    (colliding / "SKILL.md").write_text("# Upstream collision\n")
    owned = (package / "skills" / "context-extractor" / "SKILL.md").read_bytes()

    qualify(package, "update")

    assert (package / "skills" / "context-extractor" / "SKILL.md").read_bytes() == owned


@pytest.mark.parametrize("change", ["added", "deleted"])
def test_file_addition_or_deletion_marks_existing_skill_changed(
    package: Path, upstream: Path, fake_vendir: Path, change: str
) -> None:
    """Catch changed-skill detection considering only shared file paths."""
    legacy = package / "skills" / "alpha" / "legacy.txt"
    upstream_legacy = upstream / "skills" / "engineering" / "alpha" / "legacy.txt"
    if change == "added":
        (upstream / "skills" / "engineering" / "alpha" / "new.txt").write_text("new\n")
    else:
        legacy.write_text("legacy\n")
        upstream_legacy.write_text("legacy\n")
        provenance = package / "provenance.yml"
        data = yaml.safe_load(provenance.read_text())
        digest = hashlib.sha256(b"legacy\n").hexdigest()
        item = {"path": "skills/alpha/legacy.txt", "sha256": digest}
        data["source_files"].append(item)
        data["output_files"].append(item)
        provenance.write_text(yaml.safe_dump(data, sort_keys=False))
        upstream_legacy.unlink()

    result = qualify(package, "update")

    assert "Changed skills: alpha" in result.summary


def test_all_matt_leaf_locks_must_resolve_to_same_commit(package: Path, fake_vendir: Path) -> None:
    """Catch combining imported leaf content from different Matt commits."""
    lock = package / "vendir.lock.yml"
    data = yaml.safe_load(lock.read_text())
    data["directories"][-1]["contents"][0]["git"]["sha"] = "9" * 40
    lock.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(QualificationError, match="different commits"):
        qualify(package, "locked")


@pytest.mark.parametrize("invalid", ["missing", "duplicate"])
def test_manifest_source_mappings_must_be_complete_and_unique(
    package: Path, fake_vendir: Path, invalid: str
) -> None:
    """Catch ambiguous or incomplete imported leaf provenance."""
    manifest = package / "vendir.yml"
    data = yaml.safe_load(manifest.read_text())
    if invalid == "missing":
        del data["directories"][0]["contents"][0]["newRootPath"]
    else:
        data["directories"][1]["contents"][0]["newRootPath"] = data["directories"][0]["contents"][
            0
        ]["newRootPath"]
    manifest.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(QualificationError, match="source mapping"):
        qualify(package, "locked")
