from __future__ import annotations

import hashlib
import importlib
import os
import shutil
from pathlib import Path

import pytest
import yaml

FIXTURE_UPSTREAM = Path(__file__).parents[1] / "fixtures" / "upstreams" / "mattpocock-skills"
OLD_COMMIT = "1" * 40
OWNED_SKILLS = (
    "audit-third-party-software",
    "context-extractor",
    "operating-omnigent",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_leaf(destination: str, source: str) -> dict:
    return {
        "path": destination,
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


def lock_leaf(destination: str) -> dict:
    return {
        "path": destination,
        "contents": [{"path": ".", "git": {"sha": OLD_COMMIT}}],
    }


def write_package(package: Path, upstream: Path) -> None:
    package.mkdir()
    skills = package / "skills"
    skills.mkdir()
    for name in OWNED_SKILLS:
        skill = skills / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"# Owned {name}\n")
    for source, destination in (
        ("skills/engineering/alpha", "alpha"),
        ("skills/engineering/setup-matt-pocock-skills", "setup-engineering-workflow-for-apm"),
        ("skills/productivity/grilling", "grilling"),
    ):
        shutil.copytree(upstream / source, skills / destination)
    licenses = package / "LICENSES" / "mattpocock-skills"
    licenses.mkdir(parents=True)
    shutil.copy2(upstream / "LICENSE", licenses / "LICENSE")
    (package / "patches").mkdir()
    (package / "patches" / "series").write_text("")

    destinations = [
        ("skills/alpha", "skills/engineering/alpha"),
        (
            "skills/setup-engineering-workflow-for-apm",
            "skills/engineering/setup-matt-pocock-skills",
        ),
        ("skills/grilling", "skills/productivity/grilling"),
    ]
    (package / "vendir.yml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "vendir.k14s.io/v1alpha1",
                "kind": "Config",
                "minimumRequiredVersion": "0.46.0",
                "directories": [
                    *(git_leaf(destination, source) for destination, source in destinations),
                    {
                        "path": "LICENSES/mattpocock-skills",
                        "contents": [
                            {
                                "path": ".",
                                "git": {
                                    "url": "https://github.com/mattpocock/skills.git",
                                    "ref": "origin/main",
                                },
                                "includePaths": ["LICENSE"],
                                "excludePaths": [],
                                "legalPaths": ["LICENSE"],
                            }
                        ],
                    },
                ],
            },
            sort_keys=False,
        )
    )
    (package / "vendir.lock.yml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "vendir.k14s.io/v1alpha1",
                "kind": "LockConfig",
                "directories": [
                    *(lock_leaf(destination) for destination, _ in destinations),
                    lock_leaf("LICENSES/mattpocock-skills"),
                ],
            },
            sort_keys=False,
        )
    )
    imported = ("alpha", "grilling", "setup-engineering-workflow-for-apm")
    output_files = [
        {
            "path": path.relative_to(package).as_posix(),
            "sha256": sha256(path),
            "mode": "100755" if path.stat().st_mode & 0o111 else "100644",
        }
        for name in imported
        for path in sorted((skills / name).rglob("*"))
        if path.is_file()
    ]
    license_path = licenses / "LICENSE"
    (package / "provenance.yml").write_text(
        yaml.safe_dump(
            {
                "source_commit": OLD_COMMIT,
                "included_skills": list(imported),
                "excluded_skills": ["setup-matt-pocock-skills"],
                "source_mappings": [
                    {
                        "source_repository": "https://github.com/mattpocock/skills.git",
                        "source_commit": OLD_COMMIT,
                        "source_path": source,
                        "destination_path": destination,
                    }
                    for destination, source in sorted(destinations)
                ],
                "source_files": output_files,
                "patch_files": [],
                "license_files": [
                    {
                        "path": "LICENSES/mattpocock-skills/LICENSE",
                        "sha256": sha256(license_path),
                        "mode": "100644",
                    }
                ],
                "output_files": output_files,
            },
            sort_keys=False,
        )
    )


@pytest.fixture
def upstream(tmp_path: Path) -> Path:
    path = tmp_path / "upstream"
    shutil.copytree(FIXTURE_UPSTREAM, path)
    return path


@pytest.fixture
def package(tmp_path: Path, upstream: Path) -> Path:
    path = tmp_path / "engineering"
    write_package(path, upstream)
    return path


@pytest.fixture
def fake_vendir(tmp_path: Path, upstream: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    vendir = bin_dir / "vendir"
    vendir.write_text(
        """#!/usr/bin/env python3
import os
import re
import shutil
import sys
from pathlib import Path

import yaml

stage = Path(sys.argv[sys.argv.index("--chdir") + 1])
upstream = Path(os.environ["FAKE_VENDIR_UPSTREAM"])
config = yaml.safe_load((stage / "vendir.yml").read_text())
refs = {
    content["git"]["ref"]
    for directory in config["directories"]
    for content in directory["contents"]
    if "git" in content
}
if ref_log := os.environ.get("FAKE_VENDIR_REF_LOG"):
    Path(ref_log).write_text("\\n".join(sorted(refs)) + "\\n")
for directory in config["directories"]:
    destination = stage / directory["path"]
    content = directory["contents"][0]
    source_root = content.get("newRootPath")
    if source_root:
        shutil.rmtree(destination, ignore_errors=True)
        source = upstream / source_root
        if source.exists():
            shutil.copytree(source, destination)
    elif directory["path"] == "LICENSES/mattpocock-skills":
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(upstream / "LICENSE", destination / "LICENSE")
if "--locked" not in sys.argv:
    pinned = next(iter(refs)) if len(refs) == 1 else ""
    commit = (
        pinned
        if re.fullmatch(r"[0-9a-f]{40}", pinned)
        else os.environ.get("FAKE_VENDIR_COMMIT", "2" * 40)
    )
    lock = stage / "vendir.lock.yml"
    lock.write_text(lock.read_text().replace(
        "1111111111111111111111111111111111111111",
        commit,
    ))
"""
    )
    vendir.chmod(0o755)
    qualify_module = importlib.import_module("tools.capability_pack.qualify")
    reconcile = qualify_module._reconcile_inventory
    validate_source_policy = qualify_module._validate_source_policy

    def reconcile_fixture(stage: Path, config: dict, owned: tuple[str, ...]):
        urls = {
            content["git"]["url"]
            for directory in config["directories"]
            for content in directory["contents"]
            if "git" in content
        }
        if urls == {"https://github.com/mattpocock/skills.git"}:
            return config, None
        return reconcile(stage, config, owned)

    def validate_fixture_source_policy(package: Path, config: dict) -> None:
        urls = {
            content["git"]["url"]
            for directory in config["directories"]
            for content in directory["contents"]
            if "git" in content
        }
        if urls and all(Path(url).is_dir() for url in urls):
            return
        validate_source_policy(package, config)

    monkeypatch.setattr(qualify_module, "_reconcile_inventory", reconcile_fixture)
    monkeypatch.setattr(qualify_module, "_validate_source_policy", validate_fixture_source_policy)
    monkeypatch.setenv("FAKE_VENDIR_UPSTREAM", str(upstream))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return vendir
