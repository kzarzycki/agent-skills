"""A downstream fork vendors a package from this repository by lock and keeps its own overlay.

Real git and vendir, no fakes: the origin is a local repository laid out like this one
(`engineering/skills/<name>`), and the fork's pack declares that origin in its upstream.yml.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from capability_pack.cli import main
from engineering.tests.test_consumer_e2e import (
    SLUG,
    _isolated_env,
    _no_bytecode,
    _publish,
    _run,
    _write_manifest,
)

REPOSITORY = Path(__file__).resolve().parents[2]

OVERLAY = "# Alpha, as the fork tunes it\n"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _origin(tmp_path: Path) -> Path:
    origin = tmp_path / "agent-skills"
    _write(origin / "engineering" / "skills" / "alpha" / "SKILL.md", "# Alpha upstream\n")
    _write(origin / "engineering" / "skills" / "beta" / "SKILL.md", "# Beta, first cut\n")
    _git("init", "--quiet", "-b", "main", cwd=origin)
    _git("add", "-A", cwd=origin)
    _git("commit", "--quiet", "-m", "initial", cwd=origin)
    return origin


def _leaf(origin: Path, name: str) -> dict:
    source = f"engineering/skills/{name}"
    return {
        "path": f"skills/{name}",
        "contents": [
            {
                "path": ".",
                "git": {"url": str(origin), "ref": "origin/main"},
                "includePaths": [f"{source}/**/*"],
                "excludePaths": [],
                "legalPaths": [],
                "newRootPath": source,
            }
        ],
    }


def _fork(tmp_path: Path, origin: Path, name: str = "engineering") -> Path:
    pack = tmp_path / "fork" / name
    (pack / "skills").mkdir(parents=True)
    _write(pack / "overlays" / "skills" / "alpha" / "SKILL.md", OVERLAY)
    _write(pack / "apm.yml", "name: engineering\nversion: 1.0.0\n")
    _write(
        pack / ".claude-plugin" / "plugin.json",
        json.dumps({"name": "engineering", "version": "1.0.0"}),
    )
    policy = {
        "schema_version": 1,
        "repository": str(origin),
        "tracked_ref": "origin/main",
        "removal_policy": "block",
        "skills_path": "engineering/skills",
        "exclusions": [],
        "aliases": {},
        "owned_skills": [],
        "owned_overlays": [{"source": "overlays/skills/alpha", "destination": "skills/alpha"}],
    }
    _write(pack / "upstream.yml", yaml.safe_dump(policy, sort_keys=False))
    config = {
        "apiVersion": "vendir.k14s.io/v1alpha1",
        "kind": "Config",
        "directories": [_leaf(origin, "alpha"), _leaf(origin, "beta")],
    }
    _write(pack / "vendir.yml", yaml.safe_dump(config, sort_keys=False))
    # The fork starts its lock the way vendir makes one.
    subprocess.run(
        ["vendir", "sync", "--chdir", str(pack)], check=True, capture_output=True, text=True
    )
    return pack


def _version(pack: Path) -> str:
    return yaml.safe_load((pack / "apm.yml").read_text())["version"]


def test_a_fork_updates_and_checks_a_pack_vendored_from_this_repository(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    pack = _fork(tmp_path, origin)

    assert main(["update", str(pack)]) == 0
    assert main(["check", str(pack)]) == 0
    assert (pack / "skills" / "alpha" / "SKILL.md").read_text() == OVERLAY

    _write(origin / "engineering" / "skills" / "beta" / "SKILL.md", "# Beta, second cut\n")
    _write(origin / "engineering" / "skills" / "gamma" / "SKILL.md", "# Gamma\n")
    _git("add", "-A", cwd=origin)
    _git("commit", "--quiet", "-m", "beta changes, gamma joins", cwd=origin)

    assert main(["update", str(pack)]) == 0
    assert main(["check", str(pack)]) == 0
    assert (pack / "skills" / "alpha" / "SKILL.md").read_text() == OVERLAY
    assert (pack / "skills" / "beta" / "SKILL.md").read_text() == "# Beta, second cut\n"
    assert (pack / "skills" / "gamma" / "SKILL.md").read_text() == "# Gamma\n"
    provenance = yaml.safe_load((pack / "provenance.yml").read_text())
    assert provenance["source_commit"] == _git("rev-parse", "HEAD", cwd=origin)
    assert _version(pack) == "1.1.0"


def test_a_pack_of_any_name_is_held_to_the_upstream_it_declares(tmp_path: Path) -> None:
    pack = _fork(tmp_path, _origin(tmp_path), name="team-skills")
    assert main(["update", str(pack)]) == 0
    policy = yaml.safe_load((pack / "upstream.yml").read_text())
    policy["repository"] = str(tmp_path / "elsewhere")
    (pack / "upstream.yml").write_text(yaml.safe_dump(policy, sort_keys=False))

    assert main(["check", str(pack)]) == 2


def test_the_installed_launcher_runs_without_the_authors_environment(tmp_path: Path) -> None:
    """A consumer installs vendoring through APM and runs its launcher with no Python project of
    its own: the launcher's PEP 723 header is the only thing that provides PyYAML."""
    env = _isolated_env(tmp_path)
    source = tmp_path / "source"
    shutil.copytree(REPOSITORY / "vendoring", source / "vendoring", ignore=_no_bytecode)
    _publish(tmp_path, env, source)
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    version = yaml.safe_load((source / "vendoring" / "apm.yml").read_text())["version"]
    _write_manifest(consumer / "apm.yml", {"git": f"{SLUG}/vendoring", "ref": f"^{version}"})
    _run(["apm", "install"], cwd=consumer, env=env)
    launcher = consumer / ".agents" / "skills" / "vendoring" / "scripts" / "vendor.py"

    # The real HOME keeps uv's cache; the author's virtualenv leaves PATH.
    runtime = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "PYTHONPATH"}}
    venvs = {str(Path(sys.executable).parent), str(REPOSITORY / ".venv" / "bin")}
    runtime["PATH"] = os.pathsep.join(
        p for p in runtime["PATH"].split(os.pathsep) if p not in venvs
    )
    pack = _fork(tmp_path, _origin(tmp_path))
    for args in (["--help"], ["update", str(pack)], ["check", str(pack)]):
        _run(["uv", "run", str(launcher), *args], cwd=consumer, env=runtime)
    assert (pack / "skills" / "alpha" / "SKILL.md").read_text() == OVERLAY
