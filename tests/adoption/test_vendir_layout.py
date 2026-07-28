from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

FIXTURES = Path(__file__).parents[1] / "fixtures"
MANIFESTS = (
    ("vendir.yml", "vendir.lock.yml"),
    ("vendir.grilling.yml", "vendir.grilling.lock.yml"),
)


def run(*args: str, cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)
    assert result.returncode == 0, f"{' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"


def sync_manifests(package: Path) -> None:
    for manifest, lock in MANIFESTS:
        run(
            "vendir",
            "sync",
            "--file",
            manifest,
            "--lock-file",
            lock,
            "--chdir",
            str(package),
            cwd=package,
        )


def configure_upstream(package: Path, upstream: Path) -> None:
    for manifest, _ in MANIFESTS:
        config_path = package / manifest
        config = yaml.safe_load(config_path.read_text())
        for directory in config["directories"]:
            for content in directory["contents"]:
                if "git" in content:
                    content["git"]["url"] = upstream.as_uri()
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))


def initialize_upstream(upstream: Path) -> None:
    run("git", "init", "-b", "main", cwd=upstream)
    run("git", "config", "user.name", "Vendir Probe", cwd=upstream)
    run("git", "config", "user.email", "vendir-probe@example.invalid", cwd=upstream)
    run("git", "add", ".", cwd=upstream)
    run("git", "commit", "-m", "fixture", cwd=upstream)


def test_sequential_vendir_sync_writes_final_paths_and_preserves_owned_skills(
    tmp_path: Path,
) -> None:
    """Catch Python promotion, nested upstream roots, and owned-skill replacement."""
    upstream = tmp_path / "upstream"
    package = tmp_path / "package"
    shutil.copytree(FIXTURES / "vendir-upstream", upstream)
    shutil.copytree(FIXTURES / "vendir-package", package)
    initialize_upstream(upstream)
    configure_upstream(package, upstream)
    owned_path = package / "skills" / "audit-third-party-software" / "SKILL.md"
    owned_text = owned_path.read_text()

    sync_manifests(package)

    skills = package / "skills"
    assert (skills / "alpha" / "SKILL.md").is_file()
    assert (skills / "grilling" / "SKILL.md").is_file()
    assert not (skills / ".upstream").exists()
    assert not (skills / "setup-matt-pocock-skills").exists()
    assert owned_path.read_text() == owned_text
    assert (package / "vendir.lock.yml").is_file()
    assert (package / "vendir.grilling.lock.yml").is_file()


def test_primary_ignore_paths_preserve_owned_skill_on_upstream_collision(
    tmp_path: Path,
) -> None:
    """Catch an upstream same-name skill replacing repository-owned behavior."""
    upstream = tmp_path / "upstream"
    package = tmp_path / "package"
    shutil.copytree(FIXTURES / "vendir-upstream", upstream)
    shutil.copytree(
        FIXTURES / "vendir-upstream-collision" / "skills" / "engineering",
        upstream / "skills" / "engineering",
        dirs_exist_ok=True,
    )
    shutil.copytree(FIXTURES / "vendir-package", package)
    initialize_upstream(upstream)
    configure_upstream(package, upstream)
    owned = package / "skills" / "audit-third-party-software" / "SKILL.md"
    owned_bytes = owned.read_bytes()

    sync_manifests(package)

    assert owned.read_bytes() == owned_bytes
    assert (package / "skills" / "alpha" / "SKILL.md").is_file()
