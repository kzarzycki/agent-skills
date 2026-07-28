from __future__ import annotations

import hashlib
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
    "setup-engineering-workflow-for-apm",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_package(package: Path, upstream: Path) -> None:
    package.mkdir()
    skills = package / "skills"
    skills.mkdir()
    for name in OWNED_SKILLS:
        skill = skills / name
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"# Owned {name}\n")
    for category, name in (("engineering", "alpha"), ("productivity", "grilling")):
        shutil.copytree(upstream / "skills" / category / name, skills / name)
    licenses = package / "LICENSES"
    licenses.mkdir()
    shutil.copy2(upstream / "LICENSE", licenses / "mattpocock-skills-LICENSE")
    (package / "patches").mkdir()
    (package / "patches" / "series").write_text("")

    (package / "vendir.yml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "vendir.k14s.io/v1alpha1",
                "kind": "Config",
                "directories": [
                    {
                        "path": "skills",
                        "contents": [
                            {
                                "path": ".",
                                "git": {
                                    "url": "https://example.invalid/upstream.git",
                                    "ref": "origin/main",
                                },
                                "includePaths": ["skills/engineering/***"],
                                "excludePaths": ["skills/engineering/setup-matt-pocock-skills/***"],
                                "legalPaths": ["LICENSE"],
                                "newRootPath": "skills/engineering",
                                "ignorePaths": [
                                    *(f"{name}/***" for name in OWNED_SKILLS),
                                    "grilling/***",
                                ],
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        )
    )
    (package / "vendir.grilling.yml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "vendir.k14s.io/v1alpha1",
                "kind": "Config",
                "directories": [
                    {
                        "path": "skills/grilling",
                        "contents": [
                            {
                                "path": ".",
                                "git": {
                                    "url": "https://example.invalid/upstream.git",
                                    "ref": "origin/main",
                                },
                                "includePaths": ["skills/productivity/grilling/***"],
                                "excludePaths": [],
                                "legalPaths": [],
                                "newRootPath": "skills/productivity/grilling",
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        )
    )
    for lock_name, directory_path in (
        ("vendir.lock.yml", "skills"),
        ("vendir.grilling.lock.yml", "skills/grilling"),
    ):
        (package / lock_name).write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "vendir.k14s.io/v1alpha1",
                    "kind": "LockConfig",
                    "directories": [
                        {
                            "path": directory_path,
                            "contents": [{"path": ".", "git": {"sha": OLD_COMMIT}}],
                        }
                    ],
                },
                sort_keys=False,
            )
        )
    output_files = [
        {"path": f"skills/{name}/SKILL.md", "sha256": sha256(skills / name / "SKILL.md")}
        for name in ("alpha", "grilling")
    ]
    license_path = licenses / "mattpocock-skills-LICENSE"
    (package / "provenance.yml").write_text(
        yaml.safe_dump(
            {
                "source_commit": OLD_COMMIT,
                "included_skills": ["alpha", "grilling"],
                "excluded_skills": ["setup-matt-pocock-skills"],
                "source_files": output_files,
                "patch_files": [],
                "license_files": [
                    {
                        "path": "LICENSES/mattpocock-skills-LICENSE",
                        "sha256": sha256(license_path),
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
import shutil
import sys
from pathlib import Path

stage = Path(sys.argv[sys.argv.index("--chdir") + 1])
upstream = Path(os.environ["FAKE_VENDIR_UPSTREAM"])
manifest = sys.argv[sys.argv.index("--file") + 1]
lock_name = sys.argv[sys.argv.index("--lock-file") + 1]
skills = stage / "skills"
if manifest == "vendir.yml":
    preserved = {"audit-third-party-software", "context-extractor", "operating-omnigent", "setup-engineering-workflow-for-apm", "grilling"}
    for child in skills.iterdir():
        if child.is_dir() and child.name not in preserved:
            shutil.rmtree(child)
    for source in (upstream / "skills" / "engineering").iterdir():
        if source.name != "setup-matt-pocock-skills" and source.name not in preserved:
            shutil.copytree(source, skills / source.name)
elif manifest == "vendir.grilling.yml":
    shutil.rmtree(skills / "grilling", ignore_errors=True)
    shutil.copytree(upstream / "skills" / "productivity" / "grilling", skills / "grilling")
else:
    raise SystemExit(f"unexpected manifest: {manifest}")
if "--locked" not in sys.argv:
    lock = stage / lock_name
    lock.write_text(lock.read_text().replace("1111111111111111111111111111111111111111", os.environ.get("FAKE_VENDIR_COMMIT", "2222222222222222222222222222222222222222")))
"""
    )
    vendir.chmod(0o755)
    monkeypatch.setenv("FAKE_VENDIR_UPSTREAM", str(upstream))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return vendir
