"""Every package split out of engineering (#615) publishes one consistent package in both formats, is in the
marketplace, declares the same dependencies to APM and to Claude Code, and packs and installs for Claude Code and
Codex with the skills of the packages it depends on beside its own."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
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
    "loop": [
        "skills/engineering-loop/scripts/loop.py",
        *(f"skills/engineering-loop/scripts/{name}.py" for name in ("approvals", "gatekeeper")),
        *(f"skills/engineering-loop/scripts/{name}.py" for name in ("board", "labels", "browse")),
    ],
    "github": ["skills/github-tracker/scripts/board.py", "skills/github-tracker/scripts/labels.py"],
    "chief-of-staff": ["skills/chief-of-staff/scripts/cos_page.py"],
    "omnigent": [],
    "engineering": ["skills/orchestrating-agents/scripts/omnigent_agent.py"],
}
# Each script path engineering 0.25.0 shipped that moved, an unchanged consumer command on it, and the script it now
# runs, as a skills directory holds them. The old path stays for one release line (user story 6).
FORWARDED = [
    (
        "engineering-loop/scripts/approvals.py",
        ["check", "build", "--help"],
        "gatekeeper/scripts/gatekeeper.py",
    ),
    (
        "engineering-loop/scripts/approvals.py",
        ["brief", "--help"],
        "engineering-loop/scripts/loop.py",
    ),
    (
        "engineering-loop/scripts/approvals.py",
        ["release", "--help"],
        "engineering-loop/scripts/loop.py",
    ),
    # stdin and a refusal's exit code pass through: an unfinished report is refused with 1
    (
        "engineering-loop/scripts/approvals.py",
        ["report", "/dev/stdin"],
        "gatekeeper/scripts/gatekeeper.py",
    ),
    (
        "engineering-loop/scripts/gatekeeper.py",
        ["check", "build", "--help"],
        "gatekeeper/scripts/gatekeeper.py",
    ),
    ("engineering-loop/scripts/board.py", ["--help"], "github-tracker/scripts/board.py"),
    ("engineering-loop/scripts/labels.py", ["--help"], "github-tracker/scripts/labels.py"),
    ("engineering-loop/scripts/browse.py", ["--help"], "browsing/scripts/browse.py"),
    (
        "orchestrating-agents/scripts/omnigent_agent.py",
        ["--help"],
        "omnigent-agents/scripts/omnigent_agent.py",
    ),
]


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


def resolver(path: Path) -> str:
    found = re.search(r"^def installed\(.*?(?=^\S)", path.read_text(), re.MULTILINE | re.DOTALL)
    assert found, f"{path}: no installed()"
    return found.group()


COPIES = [f"{name}/{script}" for name, scripts in RESOLVER.items() for script in scripts]


def test_every_copy_of_the_resolver_is_the_same() -> None:
    copies = {copy: resolver(REPOSITORY / copy) for copy in COPIES}
    assert len(set(copies.values())) == 1, sorted(copies)


@pytest.mark.parametrize("copy", COPIES)
def test_the_resolver_finds_a_skill_in_claude_codes_cache(copy: str, tmp_path: Path) -> None:
    """Claude Code installs each plugin at `<marketplace>/<plugin>/<version>/` in its cache and marks a version an
    update replaced with `.orphaned_at`: the newest version that isn't orphaned wins, and with none the script exits
    naming the skill."""
    package, script = copy.split("/", 1)
    marketplace = tmp_path / "cache" / "kzarzycki-agent-skills"
    copied = marketplace / package / "0.1.0" / script
    copied.parent.mkdir(parents=True)
    for version, age in (("0.1.0", 300), ("0.2.0", 200), ("0.3.0", 100)):
        skill = marketplace / "gatekeeper" / version / "skills" / "gatekeeper"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("gatekeeper")
        os.utime(skill, (time.time() - age,) * 2)
    (marketplace / "gatekeeper" / "0.3.0" / ".orphaned_at").write_text("0")
    # the resolver alone, at the copy's path: the script itself would resolve its dependencies on import
    copied.write_text("import sys\nfrom pathlib import Path\n\n\n" + resolver(REPOSITORY / copy))
    spec = importlib.util.spec_from_file_location("resolver", copied)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert (
        module.installed("gatekeeper")
        == (marketplace / "gatekeeper" / "0.2.0" / "skills" / "gatekeeper" / "scripts").resolve()
    )
    for version in ("0.1.0", "0.2.0"):
        (marketplace / "gatekeeper" / version / ".orphaned_at").write_text("0")
    with pytest.raises(SystemExit, match="needs the `gatekeeper` skill"):
        module.installed("gatekeeper")


def test_a_project_pinned_to_engineering_keeps_the_old_script_paths(tmp_path: Path) -> None:
    """Each old path runs its new script with the same arguments, stdin, output and exit code, after one deprecation
    line, in both APM targets; the new path prints none, so no forwarder was imported in its place."""
    env = _isolated_env(tmp_path)
    source = tmp_path / "source"
    _copy_package(source)
    _publish(tmp_path, env, source)
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    version = yaml.safe_load((source / "engineering" / "apm.yml").read_text())["version"]
    _write_manifest(consumer / "apm.yml", {"git": f"{SLUG}/engineering", "ref": f"^{version}"})
    _run(["apm", "install"], cwd=consumer, env=env)

    def run(path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(path), *args],
            cwd=consumer,
            env=env,
            input="an unfinished report\n",
            capture_output=True,
            text=True,
            check=False,
        )

    for target in (".claude", ".agents"):
        skills = consumer / target / "skills"
        for old, args, new in FORWARDED:
            was, now = run(skills / old, args), run(skills / new, args)
            deprecation = f"{old} is deprecated: run the `{new.split('/')[0]}` skill's {new.split('/', 1)[1]}\n"
            assert (was.returncode, was.stdout, was.stderr) == (
                now.returncode,
                now.stdout,
                deprecation + now.stderr,
            ), f"{target}/skills/{old} {' '.join(args)}"
            assert "deprecated" not in now.stderr


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
