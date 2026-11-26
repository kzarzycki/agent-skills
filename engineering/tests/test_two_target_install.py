"""The pack installs into a project that targets both Claude and Codex on every apm a consumer runs, and its hooks
reach Claude only (#2683).

apm 0.36 removed hook filename routing: every hook file in a package reaches every target the package serves, and an
install is refused when Codex would newly activate `hooks/hooks-claude.json`. The hooks therefore live in
`engineering-hooks`, whose `apm.yml` says `target: claude`; `engineering` depends on it."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import pytest
import yaml

from engineering.tests.test_consumer_e2e import (
    PACKAGE,
    _copy_package,
    _expected_skills,
    _installed_skills,
    _isolated_env,
    _publish,
    _run,
)

pytestmark = pytest.mark.slow

# the apm releases consumers pin (their mise.toml) and the newest one, which `uv tool install` resolves
APM_RELEASES = ["0.30.0", "0.33.0", "latest"]
HOOKS_PACKAGE = PACKAGE.parent / "engineering-hooks"


def _apm(tmp_path: Path, release: str) -> Path:
    """One apm release in a tool directory of its own. It is fetched with this machine's network, before the
    install's isolated environment cuts it off."""
    requirement = "apm-cli" if release == "latest" else f"apm-cli=={release}"
    tools, bin_dir = tmp_path / "uv-tools", tmp_path / "uv-bin"
    _run(
        ["uv", "tool", "install", requirement],
        cwd=tmp_path,
        env={**os.environ, "UV_TOOL_DIR": str(tools), "UV_TOOL_BIN_DIR": str(bin_dir)},
    )
    return bin_dir / "apm"


def test_the_hooks_package_serves_claude_only_and_engineering_depends_on_it() -> None:
    hooks = yaml.safe_load((HOOKS_PACKAGE / "apm.yml").read_text())
    assert hooks["target"] == "claude"
    assert (HOOKS_PACKAGE / "hooks" / "hooks-claude.json").is_file()
    engineering = yaml.safe_load((PACKAGE / "apm.yml").read_text())
    assert engineering["targets"] == ["claude", "codex"]
    assert {"git": "kzarzycki/agent-skills/engineering-hooks", "ref": "^0.1.0"} in engineering[
        "dependencies"
    ]["apm"]
    assert not (PACKAGE / "hooks").exists(), (
        "a hook file in engineering would reach Codex on apm 0.36+"
    )


@pytest.mark.needs_tool("uv")
@pytest.mark.parametrize("release", APM_RELEASES)
def test_engineering_installs_into_a_two_target_project(tmp_path: Path, release: str) -> None:
    apm = _apm(tmp_path, release)
    env = _isolated_env(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    _copy_package(source)
    if HOOKS_PACKAGE.exists():  # main has none, and the test is red there: its point
        shutil.copytree(HOOKS_PACKAGE, source / "engineering-hooks", dirs_exist_ok=True)
    _publish(tmp_path, env, source)
    version = yaml.safe_load((PACKAGE / "apm.yml").read_text())["version"]

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "apm.yml").write_text(
        yaml.safe_dump(
            {
                "name": "two-target-consumer",
                "version": "1.0.0",
                "targets": ["claude", "codex"],
                "dependencies": {
                    "apm": [{"git": "kzarzycki/agent-skills/engineering", "ref": f"^{version}"}],
                    "mcp": [],
                },
            },
            sort_keys=False,
        )
    )
    installed = _run([str(apm), "install"], cwd=consumer, env=env)
    assert "newly activate" not in installed.stdout + installed.stderr

    expected = _expected_skills()
    assert _installed_skills(consumer, ".agents") == expected  # Codex gets every skill
    # Claude gets each one loose, or, on an apm that deploys a package as a native plugin, through that plugin
    loose = _installed_skills(consumer, ".claude")
    settings = json.loads((consumer / ".claude" / "settings.json").read_text())
    native = {name.split("@")[0] for name in settings.get("enabledPlugins", {})}
    through_plugins = {
        path.parent.name for name in native for path in (source / name).glob("skills/*/SKILL.md")
    }
    assert loose | through_plugins == expected
    assert "engineering-hooks" not in native  # a native plugin would skip the settings.json hooks
    commands = [h["command"] for e in settings["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert sorted(re.search(r"[\w-]+\.py", c).group() for c in commands) == [
        "heavy_run_guard.py",
        "push_merge_guard.py",
        "secret_env_guard.py",
    ]
    assert all("/.claude/hooks/" in c for c in commands)
    # hooks reach .claude/ only: no hook file, script or manifest anywhere Codex reads
    codex_side = [
        path
        for root in (consumer / ".codex", consumer / ".agents")
        if root.exists()
        for path in root.rglob("*")
        if path.is_file() and ("hook" in path.name or path.suffix == ".py" and "guard" in path.name)
    ]
    assert codex_side == []
