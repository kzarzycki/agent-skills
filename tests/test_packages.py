"""Every package split out of engineering (#615) publishes one consistent package in both formats, is in the
marketplace, declares the same dependencies to APM and to Claude Code, and packs and installs for Claude Code and
Codex with the skills of the packages it depends on beside its own."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from engineering.tests.test_consumer_e2e import (
    SLUG,
    _copy_package,
    _dependencies,
    _file_manifest,
    _isolated_env,
    _publish,
    _run,
    _write_manifest,
)

REPOSITORY = Path(__file__).resolve().parents[1]
PACKAGES = ("gatekeeper", "loop", "github", "chief-of-staff", "omnigent")
# The copies of loop.py's resolver for a skill another package ships: each script must run alone, so none imports it.
RESOLVER = {
    "gatekeeper": [],
    "loop": ["skills/engineering-loop/scripts/loop.py"],
    "github": ["skills/github-tracker/scripts/board.py", "skills/github-tracker/scripts/labels.py"],
    "chief-of-staff": ["skills/chief-of-staff/scripts/cos_page.py"],
    "omnigent": [],
}


def manifests(name: str) -> tuple[dict, dict]:
    package = REPOSITORY / name
    return (
        yaml.safe_load((package / "apm.yml").read_text()),
        json.loads((package / ".claude-plugin" / "plugin.json").read_text()),
    )


def skills(package: Path) -> set[str]:
    return {path.parent.name for path in package.glob("skills/*/SKILL.md")}


@pytest.mark.parametrize("name", PACKAGES)
def test_both_formats_publish_the_same_package(name: str) -> None:
    apm, plugin = manifests(name)
    assert apm["name"] == plugin["name"] == name
    assert apm["version"] == plugin["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", apm["version"])
    assert apm["description"] == plugin["description"]
    assert apm["targets"] == ["claude", "codex"]
    assert skills(REPOSITORY / name)
    assert list((REPOSITORY / name / "changelog.d").glob("*.md")), (
        "each package keeps its own changelog.d"
    )


@pytest.mark.parametrize("name", (*PACKAGES, "engineering"))
def test_apm_and_claude_code_declare_the_same_dependencies(name: str) -> None:
    """APM names a sibling by its subdirectory of this repo and a range of its own `<name>-v` tags; Claude Code by its
    plugin name, resolved in the same marketplace."""
    apm, plugin = manifests(name)
    assert all(
        item["git"].startswith(f"{SLUG}/") and item["ref"].startswith("^")
        for item in apm["dependencies"]["apm"]
    )
    assert [item["git"].removeprefix(f"{SLUG}/") for item in apm["dependencies"]["apm"]] == (
        plugin.get("dependencies", [])
    )
    assert set(plugin.get("dependencies", [])) <= set(PACKAGES)


@pytest.mark.parametrize("name", PACKAGES)
def test_the_marketplace_lists_the_package(name: str) -> None:
    marketplace = json.loads((REPOSITORY / ".claude-plugin" / "marketplace.json").read_text())
    assert [p["source"] for p in marketplace["plugins"] if p["name"] == name] == [f"./{name}"]


@pytest.mark.parametrize("name", PACKAGES)
def test_every_scripts_folder_with_python_has_a_pycache_file(name: str) -> None:
    """Without the file an importer writes bytecode there, which an installed skill's lock counts (#428)."""
    package = REPOSITORY / name
    folders = {path.parent for path in package.glob("skills/**/*.py")}
    assert (
        sorted(str(f.relative_to(package)) for f in folders if not (f / "__pycache__").is_file())
        == []
    )


def test_every_copy_of_the_resolver_is_the_same() -> None:
    def resolver(path: Path) -> str:
        found = re.search(r"^def installed\(.*?(?=^\S)", path.read_text(), re.MULTILINE | re.DOTALL)
        assert found, f"{path}: no installed()"
        return found.group()

    copies = {
        f"{name}/{script}": resolver(REPOSITORY / name / script)
        for name, scripts in RESOLVER.items()
        for script in scripts
    }
    assert len(set(copies.values())) == 1, sorted(copies)


@pytest.mark.parametrize("name", PACKAGES)
def test_the_package_packs_and_installs_for_claude_and_codex(name: str, tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    source = tmp_path / "source"
    _copy_package(source)
    _publish(tmp_path, env, source)
    package = source / name

    packed = tmp_path / "packed"
    _run(["apm", "pack", "--output", str(packed)], cwd=package, env=env)
    [bundle] = [path.parent for path in packed.rglob("plugin.json")]
    assert _file_manifest(bundle / "skills") == _file_manifest(package / "skills")

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    version = manifests(name)[0]["version"]
    _write_manifest(consumer / "apm.yml", {"git": f"{SLUG}/{name}", "ref": f"^{version}"})
    _run(["apm", "install"], cwd=consumer, env=env)
    expected = skills(package).union(*(skills(dep) for dep in _dependencies(package)))
    for target in (".claude", ".agents"):
        assert skills(consumer / target) == expected
    lock = (consumer / "apm.lock.yaml").read_text()
    _run(["apm", "install", "--frozen"], cwd=consumer, env=env)
    assert (consumer / "apm.lock.yaml").read_text() == lock
