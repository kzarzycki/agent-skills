from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

FIXTURES = Path(__file__).parents[1] / "fixtures"


def run(*args: str, cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)
    assert result.returncode == 0, f"{' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"


def sync_manifest(package: Path, *, locked: bool = False) -> None:
    command = ["vendir", "sync"]
    if locked:
        command.append("--locked")
    command.extend(["--chdir", str(package)])
    run(*command, cwd=package)


def configure_upstream(package: Path, upstream: Path) -> None:
    config_path = package / "vendir.yml"
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


def tree_state(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o777)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_leaf_vendir_sync_converges_and_preserves_owned_siblings(tmp_path: Path) -> None:
    """Catch collection ownership, setup nesting, mode loss, and locked non-convergence."""
    upstream = tmp_path / "upstream"
    package = tmp_path / "package"
    shutil.copytree(FIXTURES / "vendir-upstream", upstream)
    shutil.copytree(FIXTURES / "vendir-package", package)
    initialize_upstream(upstream)
    configure_upstream(package, upstream)
    owned_root = package / "skills" / "audit-third-party-software"
    owned_executable = owned_root / "scripts" / "executable.sh"
    owned_executable.chmod(0o755)
    owned_before = tree_state(owned_root)

    sync_manifest(package)

    skills = package / "skills"
    assert (skills / "alpha" / "SKILL.md").is_file()
    assert (skills / "beta" / "SKILL.md").is_file()
    assert (skills / "grilling" / "SKILL.md").is_file()
    assert (skills / "setup-engineering-workflow-for-apm" / "SKILL.md").is_file()
    assert not (skills / "setup-matt-pocock-skills").exists()
    assert tree_state(owned_root) == owned_before
    assert (skills / "alpha" / "scripts" / "run.sh").stat().st_mode & 0o111

    imported_before = {
        name: tree_state(skills / name)
        for name in ("alpha", "beta", "grilling", "setup-engineering-workflow-for-apm")
    }
    lock_before = (package / "vendir.lock.yml").read_bytes()
    sync_manifest(package, locked=True)

    assert tree_state(owned_root) == owned_before
    assert {
        name: tree_state(skills / name)
        for name in ("alpha", "beta", "grilling", "setup-engineering-workflow-for-apm")
    } == imported_before
    assert (package / "vendir.lock.yml").read_bytes() == lock_before


def test_undeclared_owned_sibling_is_untouched_by_upstream_collision(tmp_path: Path) -> None:
    """Catch an upstream same-name skill becoming owned without a destination declaration."""
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
    owned = package / "skills" / "audit-third-party-software"
    owned_before = tree_state(owned)

    sync_manifest(package)

    assert tree_state(owned) == owned_before
    assert (package / "skills" / "alpha" / "SKILL.md").is_file()
