from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

FIXTURES = Path(__file__).parents[1] / "fixtures"


def run(*args: str, cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)
    assert result.returncode == 0, f"{' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"


def promote_staged_skills(package: Path) -> None:
    staging = package / "skills" / ".upstream"
    for selected_root in staging.iterdir():
        for skill in selected_root.iterdir():
            shutil.copytree(skill, package / "skills" / skill.name, dirs_exist_ok=True)


def test_vendir_flattens_selected_skill_roots_and_preserves_owned_skills(tmp_path: Path) -> None:
    """Catch nested upstream roots, setup-skill leakage, and owned-skill replacement."""
    upstream = tmp_path / "upstream"
    package = tmp_path / "package"
    shutil.copytree(FIXTURES / "vendir-upstream", upstream)
    shutil.copytree(FIXTURES / "vendir-package", package)

    run("git", "init", "-b", "main", cwd=upstream)
    run("git", "config", "user.name", "Vendir Probe", cwd=upstream)
    run("git", "config", "user.email", "vendir-probe@example.invalid", cwd=upstream)
    run("git", "add", ".", cwd=upstream)
    run("git", "commit", "-m", "fixture", cwd=upstream)

    config_path = package / "vendir.yml"
    config = yaml.safe_load(config_path.read_text())
    for content in config["directories"][0]["contents"]:
        if "git" in content:
            content["git"]["url"] = upstream.as_uri()
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))

    owned_path = package / "skills" / "audit-third-party-software" / "SKILL.md"
    owned_text = owned_path.read_text()

    run("vendir", "sync", "--chdir", str(package), cwd=package)
    promote_staged_skills(package)

    skills = package / "skills"
    assert (skills / "alpha" / "SKILL.md").is_file()
    assert (skills / "grilling" / "SKILL.md").is_file()
    assert not (skills / "setup-matt-pocock-skills").exists()
    assert (skills / "audit-third-party-software" / "SKILL.md").read_text() == owned_text
