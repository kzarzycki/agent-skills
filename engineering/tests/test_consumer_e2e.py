from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY / "engineering"
OWNED_SKILLS = {
    "audit-third-party-software",
    "context-extractor",
    "operating-omnigent",
}


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{' '.join(command)} failed with {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    claude_config = tmp_path / "claude-config"
    codex_home = tmp_path / "codex-home"
    for directory in (home, claude_config, codex_home):
        directory.mkdir()

    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(claude_config),
        "CODEX_HOME": str(codex_home),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "GIT_AUTHOR_NAME": "Package Test",
        "GIT_AUTHOR_EMAIL": "package-test@example.invalid",
        "GIT_COMMITTER_NAME": "Package Test",
        "GIT_COMMITTER_EMAIL": "package-test@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _expected_skills() -> set[str]:
    provenance = yaml.safe_load((PACKAGE / "provenance.yml").read_text())
    return set(provenance["included_skills"]) | OWNED_SKILLS


def _file_manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _installed_skills(consumer: Path, target: str) -> set[str]:
    root = consumer / target / "skills"
    return {path.parent.name for path in root.glob("*/SKILL.md")}


def _assert_deployed_inventory(consumer: Path) -> None:
    expected = _expected_skills()
    assert _installed_skills(consumer, ".claude") == expected
    assert _installed_skills(consumer, ".agents") == expected

    serialized_lock = (consumer / "apm.lock.yaml").read_text()
    assert "kzarzycki/dotagents" not in serialized_lock


def _write_manifest(path: Path, dependency: dict[str, str]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "name": "engineering-consumer",
                "version": "1.0.0",
                "targets": ["claude", "codex"],
                "dependencies": {"apm": [dependency], "mcp": []},
            },
            sort_keys=False,
        )
    )


def test_local_package_packs_and_installs_for_claude_and_codex(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    package_copy = tmp_path / "engineering"
    shutil.copytree(PACKAGE, package_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    pack_dir = tmp_path / "packed"
    _run(["apm", "pack", "--output", str(pack_dir)], cwd=package_copy, env=env)
    packed_manifests = list(pack_dir.rglob("plugin.json"))
    assert len(packed_manifests) == 1
    bundle = packed_manifests[0].parent
    assert bundle.resolve().is_relative_to(pack_dir.resolve())
    assert _file_manifest(bundle / "skills") == _file_manifest(package_copy / "skills")
    assert {path.parent.name for path in (bundle / "skills").glob("*/SKILL.md")} == (
        _expected_skills()
    )

    consumer = tmp_path / "local-consumer"
    consumer.mkdir()
    _write_manifest(consumer / "apm.yml", {"path": str(package_copy)})

    _run(["apm", "install"], cwd=consumer, env=env)
    _run(["apm", "compile", "--validate"], cwd=consumer, env=env)
    _assert_deployed_inventory(consumer)


def test_virtual_subdirectory_release_installs_and_replays_frozen(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    _write_manifest(
        source / "apm.yml",
        {"git": "kzarzycki/dotagents", "path": "toolkits/agents"},
    )
    shutil.copytree(
        PACKAGE,
        source / "engineering",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    _run(["git", "init", "-q"], cwd=source, env=env)
    _run(["git", "add", "."], cwd=source, env=env)
    _run(["git", "commit", "-q", "-m", "fixture"], cwd=source, env=env)
    _run(["git", "tag", "engineering-v0.3.0"], cwd=source, env=env)

    origin = tmp_path / "agent-skills.git"
    _run(["git", "clone", "-q", "--bare", str(source), str(origin)], cwd=tmp_path, env=env)
    _run(
        [
            "git",
            "config",
            "--global",
            f"url.{origin.as_uri()}.insteadOf",
            "https://github.com/kzarzycki/agent-skills.git",
        ],
        cwd=tmp_path,
        env=env,
    )

    consumer = tmp_path / "git-consumer"
    shutil.copytree(PACKAGE / "tests" / "consumer", consumer)
    fixture = yaml.safe_load((consumer / "apm.yml").read_text())
    dependency = fixture["dependencies"]["apm"][0]
    assert dependency == {
        "git": "kzarzycki/agent-skills/engineering",
        "ref": "^0.3.0",
    }

    _run(["apm", "install"], cwd=consumer, env=env)
    _run(["apm", "compile", "--validate"], cwd=consumer, env=env)
    _run(["apm", "audit", "--ci", "--no-policy"], cwd=consumer, env=env)
    _run(["apm", "install", "--frozen"], cwd=consumer, env=env)
    _assert_deployed_inventory(consumer)

    lockfile = yaml.safe_load((consumer / "apm.lock.yaml").read_text())
    serialized_lock = json.dumps(lockfile, sort_keys=True)
    assert "^0.3.0" in serialized_lock
    assert "engineering-v0.3.0" in serialized_lock
