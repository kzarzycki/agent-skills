from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY / "engineering"


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
        # apm resolves a ref through the GitHub API when it can reach it, which bypasses the
        # git insteadOf below and installs the real release instead of the fixture (#166);
        # an unreachable proxy keeps every HTTP call local, so only git, on file URLs, works
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "HTTP_PROXY": "http://127.0.0.1:9",
        # no background repack of a fixture repo while a local clone copies its loose objects (#144)
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "maintenance.auto",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "gc.auto",
        "GIT_CONFIG_VALUE_1": "0",
    }


SLUG = "kzarzycki/agent-skills"


def _dependencies(package: Path = PACKAGE) -> list[Path]:
    """The packages of this repo that `package` pulls in (`git: kzarzycki/agent-skills/<name>` in its apm.yml), the
    siblings beside it, and theirs."""
    found: list[Path] = []
    for item in yaml.safe_load((package / "apm.yml").read_text())["dependencies"]["apm"]:
        if str(item.get("git", "")).startswith(f"{SLUG}/"):
            dependency = package.parent / item["git"].removeprefix(f"{SLUG}/")
            found += [dependency, *_dependencies(dependency)]
    return list(dict.fromkeys(found))


def _copy_package(root: Path) -> Path:
    """engineering and the packages it depends on, copied as siblings under root, as a release tag holds them."""
    for package in (PACKAGE, *_dependencies()):
        shutil.copytree(package, root / package.name, ignore=_no_bytecode)
    return root / PACKAGE.name


def _publish(tmp_path: Path, env: dict[str, str], source: Path) -> Path:
    """Commit source as this repo, tag each package's release `<name>-v<version>` and serve it as the GitHub repo
    through git's insteadOf, so a package's git dependencies on its siblings resolve offline. Returns the origin."""
    _run(["git", "init", "-q"], cwd=source, env=env)
    _run(["git", "add", "."], cwd=source, env=env)
    _run(["git", "commit", "-q", "-m", "fixture"], cwd=source, env=env)
    for manifest in source.glob("*/apm.yml"):
        version = yaml.safe_load(manifest.read_text())["version"]
        _run(["git", "tag", f"{manifest.parent.name}-v{version}"], cwd=source, env=env)
    origin = tmp_path / "agent-skills.git"
    _run(["git", "clone", "-q", "--bare", str(source), str(origin)], cwd=tmp_path, env=env)
    _run(
        [
            "git",
            "config",
            "--global",
            f"url.{origin.as_uri()}.insteadOf",
            f"https://github.com/{SLUG}.git",
        ],
        cwd=tmp_path,
        env=env,
    )
    return origin


def _expected_skills() -> set[str]:
    """engineering's own skills and every skill of the packages it depends on, all installed beside them."""
    provenance = yaml.safe_load((PACKAGE / "provenance.yml").read_text())
    policy = yaml.safe_load((PACKAGE / "upstream.yml").read_text())
    overlays = {Path(item["destination"]).name for item in policy["owned_overlays"]}
    pulled = {path.parent.name for dep in _dependencies() for path in dep.glob("skills/*/SKILL.md")}
    return set(provenance["included_skills"]) | set(policy["owned_skills"]) | overlays | pulled


def _file_manifest(root: Path) -> dict[str, str]:
    """Every file under root by its sha256, leaving out the bytecode Python caches, as git and the install do: a
    script imported from a skill folder writes it there."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parent.parts and path.suffix != ".pyc"
    }


def _no_bytecode(directory: str, names: list[str]) -> set[str]:
    """Bytecode a local run left in the package; a `__pycache__` file, which stops it, is kept."""
    return {
        name
        for name in names
        if name.endswith(".pyc") or (name == "__pycache__" and Path(directory, name).is_dir())
    }


def test_every_scripts_folder_with_python_has_a_pycache_file() -> None:
    """Without the file an importer writes bytecode there, which an installed skill's lock counts (#428)."""
    folders = {
        path.parent
        for path in (PACKAGE / "skills").rglob("*.py")
        if not {"test", "tests"} & set(path.parts)
    }
    assert folders
    assert (
        sorted(
            f.relative_to(PACKAGE).as_posix() for f in folders if not (f / "__pycache__").is_file()
        )
        == []
    )


def test_file_manifest_leaves_out_python_bytecode(tmp_path: Path) -> None:
    (tmp_path / "s" / "__pycache__").mkdir(parents=True)
    (tmp_path / "s" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"x")
    (tmp_path / "s" / "b.pyc").write_bytes(b"x")
    (tmp_path / "s" / "a.py").write_text("")
    assert list(_file_manifest(tmp_path)) == ["s/a.py"]


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
    package_copy = _copy_package(tmp_path / "source")
    _publish(tmp_path, env, tmp_path / "source")

    pack_dir = tmp_path / "packed"
    _run(["apm", "pack", "--output", str(pack_dir)], cwd=package_copy, env=env)
    packed_manifests = list(pack_dir.rglob("plugin.json"))
    assert len(packed_manifests) == 1
    bundle = packed_manifests[0].parent
    assert bundle.resolve().is_relative_to(pack_dir.resolve())
    assert _file_manifest(bundle / "skills") == _file_manifest(package_copy / "skills")
    # the bundle holds engineering's own skills; an install pulls in its dependencies' beside them
    assert {path.parent.name for path in (bundle / "skills").glob("*/SKILL.md")} == (
        _expected_skills()
        - {p.parent.name for d in _dependencies() for p in d.glob("skills/*/SKILL.md")}
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
    _copy_package(source)
    _publish(tmp_path, env, source)
    version = yaml.safe_load((PACKAGE / "apm.yml").read_text())["version"]
    tag = f"engineering-v{version}"

    consumer = tmp_path / "git-consumer"
    shutil.copytree(PACKAGE / "tests" / "consumer", consumer)
    fixture = yaml.safe_load((consumer / "apm.yml").read_text())
    dependency = fixture["dependencies"]["apm"][0]
    assert dependency == {
        "git": "kzarzycki/agent-skills/engineering",
        "ref": f"^{version}",
    }

    _run(["apm", "install"], cwd=consumer, env=env)
    _run(["apm", "compile", "--validate"], cwd=consumer, env=env)
    lock = (consumer / "apm.lock.yaml").read_text()
    # A script run, or an agent importing a sibling module, writes no bytecode into the installed skills (#428).
    scripts = consumer / ".agents" / "skills"
    _run(
        [sys.executable, "-c", "import approvals, board, labels, loop, omnigent_agent"],
        cwd=consumer,
        env={
            **env,
            "PYTHONPATH": os.pathsep.join(
                str(scripts / name / "scripts")
                for name in ("gatekeeper", "github-tracker", "engineering-loop", "omnigent-agents")
            ),
        },
    )
    assert not [path for path in consumer.rglob("*.pyc")]
    _run(["apm", "audit", "--ci", "--no-policy"], cwd=consumer, env=env)
    _run(["apm", "install", "--frozen"], cwd=consumer, env=env)
    assert (consumer / "apm.lock.yaml").read_text() == lock
    _assert_deployed_inventory(consumer)

    lockfile = yaml.safe_load((consumer / "apm.lock.yaml").read_text())
    serialized_lock = json.dumps(lockfile, sort_keys=True)
    assert f"^{version}" in serialized_lock
    assert tag in serialized_lock

    # The markers reach a fresh clone when the consumer ignores only cache folders, as `__pycache__/` does (#428).
    gitignore = consumer / ".gitignore"
    gitignore.write_text((gitignore.read_text() if gitignore.exists() else "") + "__pycache__/\n")
    _run(["git", "init", "-q"], cwd=consumer, env=env)
    _run(["git", "add", "."], cwd=consumer, env=env)
    _run(["git", "commit", "-q", "-m", "consumer"], cwd=consumer, env=env)
    clone = tmp_path / "git-consumer-clone"
    _run(["git", "clone", "-q", str(consumer), str(clone)], cwd=tmp_path, env=env)
    _run(["apm", "install", "--frozen"], cwd=clone, env=env)
    assert _run(["git", "status", "--porcelain"], cwd=clone, env=env).stdout == ""
