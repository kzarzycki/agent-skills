from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.capability_pack.qualify import (
    BreakingDriftError,
    ConfigurationError,
    QualificationError,
    qualify,
)


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
                        "url": "https://github.com/mattpocock/skills.git",
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


def _commit(upstream: Path, message: str) -> str:
    env = os.environ | {
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=upstream, env=env, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _enable_inventory_reconciliation(
    package: Path,
    upstream: Path,
) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=upstream, check=True)
    _commit(upstream, "initial")
    manifest = package / "vendir.yml"
    config = yaml.safe_load(manifest.read_text())
    for directory in config["directories"]:
        for content in directory["contents"]:
            if "git" in content:
                content["git"]["url"] = str(upstream)
    manifest.write_text(yaml.safe_dump(config, sort_keys=False))


def _package_bytes(package: Path) -> dict[str, bytes]:
    return {
        path.relative_to(package).as_posix(): path.read_bytes()
        for path in package.rglob("*")
        if path.is_file()
    }


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


def test_refresh_reconciles_new_upstream_leaf_and_converges(
    package: Path,
    upstream: Path,
    fake_vendir: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_inventory_reconciliation(package, upstream)
    beta = upstream / "skills" / "engineering" / "beta"
    beta.mkdir()
    (beta / "SKILL.md").write_text("# Beta\n")
    candidate = _commit(upstream, "add beta")
    ref_log = tmp_path / "vendir-refs.txt"
    monkeypatch.setenv("FAKE_VENDIR_REF_LOG", str(ref_log))
    summary = tmp_path / "summary.md"

    result = qualify(package, "update", summary)

    config = yaml.safe_load((package / "vendir.yml").read_text())
    beta_entry = next(
        directory for directory in config["directories"] if directory["path"] == "skills/beta"
    )
    setup_entry = next(
        directory
        for directory in config["directories"]
        if directory["path"] == "skills/setup-engineering-workflow-for-apm"
    )
    assert beta_entry["contents"][0]["newRootPath"] == "skills/engineering/beta"
    assert beta_entry["contents"][0]["git"]["ref"] == "origin/main"
    assert (
        setup_entry["contents"][0]["newRootPath"] == "skills/engineering/setup-matt-pocock-skills"
    )
    assert result.source_commit == candidate
    assert result.added_skills == ("beta",)
    assert "Added skills: beta" in summary.read_text()
    assert ref_log.read_text().splitlines() == [candidate]
    first = _package_bytes(package)

    qualify(package, "update", summary)

    assert _package_bytes(package) == first


def test_refresh_blocks_removed_configured_leaf_before_mutation(
    package: Path,
    upstream: Path,
    fake_vendir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_inventory_reconciliation(package, upstream)
    shutil.rmtree(upstream / "skills" / "engineering" / "alpha")
    candidate = _commit(upstream, "remove alpha")
    before = _package_bytes(package)

    with pytest.raises(BreakingDriftError, match=rf"alpha.*{candidate}"):
        qualify(package, "update")

    assert _package_bytes(package) == before


def test_missing_recorded_legal_file_fails_qualification(package: Path, fake_vendir: Path) -> None:
    """Catch publishing a reconstructed payload without its required license."""
    (package / "LICENSES" / "mattpocock-skills" / "LICENSE").unlink()

    with pytest.raises(QualificationError, match="legal file"):
        qualify(package, "locked")


def test_undeclared_owned_sibling_collision_blocks_update(
    package: Path,
    upstream: Path,
    fake_vendir: Path,
) -> None:
    _enable_inventory_reconciliation(package, upstream)
    colliding = upstream / "skills" / "engineering" / "context-extractor"
    colliding.mkdir()
    (colliding / "SKILL.md").write_text("# Upstream collision\n")
    candidate = _commit(upstream, "add owned-name collision")
    before = _package_bytes(package)

    with pytest.raises(BreakingDriftError, match=rf"context-extractor.*{candidate}"):
        qualify(package, "update")

    assert _package_bytes(package) == before


def test_setup_payload_change_blocks_version_proposal(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    setup = upstream / "skills" / "engineering" / "setup-matt-pocock-skills" / "SKILL.md"
    setup.write_text(setup.read_text() + "\nChanged contract.\n")

    result = qualify(package, "update")

    assert "Changed skills: setup-engineering-workflow-for-apm" in result.summary
    assert "Proposed version: BLOCKED" in result.summary


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "https://example.invalid/upstream.git"),
        ("ref", "origin/feature"),
    ],
)
def test_engineering_source_policy_rejects_unapproved_source_or_ref(
    package: Path, field: str, value: str
) -> None:
    manifest = package / "vendir.yml"
    config = yaml.safe_load(manifest.read_text())
    for directory in config["directories"]:
        for content in directory["contents"]:
            if "git" in content:
                content["git"][field] = value
    manifest.write_text(yaml.safe_dump(config, sort_keys=False))

    with pytest.raises(ConfigurationError, match="source policy"):
        qualify(package, "locked")


@pytest.mark.parametrize("claim", ["destination", "source_alias"])
def test_engineering_source_policy_rejects_claiming_owned_skill(package: Path, claim: str) -> None:
    manifest = package / "vendir.yml"
    config = yaml.safe_load(manifest.read_text())
    entry = config["directories"][0]
    if claim == "destination":
        entry["path"] = "skills/context-extractor"
    else:
        content = entry["contents"][0]
        content["newRootPath"] = "skills/engineering/context-extractor"
        content["includePaths"] = ["skills/engineering/context-extractor/**/*"]
    manifest.write_text(yaml.safe_dump(config, sort_keys=False))

    with pytest.raises(ConfigurationError, match="repository-owned"):
        qualify(package, "locked")


def test_engineering_source_policy_rejects_missing_owned_skill(package: Path) -> None:
    shutil.rmtree(package / "skills" / "context-extractor")

    with pytest.raises(ConfigurationError, match=r"repository-owned.*missing.*context-extractor"):
        qualify(package, "locked")


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
