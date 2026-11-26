"""One `apm install` across a hook move leaves Bash working (#2773).

A release that moves its hooks to another package leaves, after one install, the new entries beside the old ones in
`.claude/settings.json`, whose scripts the same install deleted. The fixture is the pack before such a move (its
hooks in `engineering`, wired with the pack's fail-open commands) and after it (the hooks in `engineering-hooks`).
Every hook command the consumer then holds, stale or new, must let a Bash call through."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from engineering.tests.test_consumer_e2e import (
    PACKAGE,
    SLUG,
    _copy_package,
    _isolated_env,
    _run,
)
from engineering.tests.test_two_target_install import HOOKS_PACKAGE, _apm

pytestmark = pytest.mark.slow

SCRIPTS = ("heavy_run_guard.py", "secret_env_guard.py")


def _tag_new(source: Path, env: dict[str, str]) -> None:
    for manifest in source.glob("*/apm.yml"):
        tag = f"{manifest.parent.name}-v{yaml.safe_load(manifest.read_text())['version']}"
        known = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
            cwd=source,
            env=env,
            check=False,
        )
        if known.returncode:
            _run(["git", "tag", tag], cwd=source, env=env)


def _set_version(manifest: Path, version: str, *, drop: str | None = None) -> None:
    data = yaml.safe_load(manifest.read_text())
    data["version"] = version
    if drop:
        data["dependencies"]["apm"] = [
            d for d in data["dependencies"]["apm"] if drop not in d["git"]
        ]
    manifest.write_text(yaml.safe_dump(data, sort_keys=False))


@pytest.mark.needs_tool("uv")
@pytest.mark.parametrize("release", ["0.30.0", "latest"])
def test_one_install_across_the_hook_move_leaves_bash_working(tmp_path: Path, release: str) -> None:
    apm = _apm(tmp_path, release)
    env = _isolated_env(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    engineering = _copy_package(source)

    # before the move: the guards are engineering's own
    _set_version(engineering / "apm.yml", "9.0.0", drop="engineering-hooks")
    (engineering / "hooks").mkdir()
    for name in SCRIPTS:
        shutil.copy(HOOKS_PACKAGE / "hooks" / name, engineering / "hooks" / name)
    commands = json.loads((HOOKS_PACKAGE / "hooks" / "hooks-claude.json").read_text())
    commands["hooks"]["PreToolUse"][0]["hooks"] = commands["hooks"]["PreToolUse"][0]["hooks"][:2]
    (engineering / "hooks" / "hooks-claude.json").write_text(json.dumps(commands))
    shutil.rmtree(source / "engineering-hooks")
    _run(["git", "init", "-q"], cwd=source, env=env)
    _run(["git", "add", "."], cwd=source, env=env)
    _run(["git", "commit", "-q", "-m", "before the move"], cwd=source, env=env)
    _tag_new(source, env)

    # after it: the guards are engineering-hooks'
    shutil.rmtree(engineering / "hooks")
    shutil.copytree(
        HOOKS_PACKAGE, source / "engineering-hooks", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy(PACKAGE / "apm.yml", engineering / "apm.yml")
    _set_version(engineering / "apm.yml", "9.1.0")
    _run(["git", "add", "."], cwd=source, env=env)
    _run(["git", "commit", "-q", "-m", "after the move"], cwd=source, env=env)
    _tag_new(source, env)
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

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    for version in ("9.0.0", "9.1.0"):  # an upgrade is one install of the new release
        (consumer / "apm.yml").write_text(
            yaml.safe_dump(
                {
                    "name": "upgrading-consumer",
                    "version": "1.0.0",
                    "targets": ["claude"],
                    "dependencies": {
                        "apm": [{"git": f"{SLUG}/engineering", "ref": f"engineering-v{version}"}],
                        "mcp": [],
                    },
                },
                sort_keys=False,
            )
        )
        _run([str(apm), "install"], cwd=consumer, env=env)

    settings = json.loads((consumer / ".claude" / "settings.json").read_text())
    commands = [h["command"] for e in settings["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("/.claude/hooks/engineering-hooks/" in c for c in commands)
    call = '{"tool_name": "Bash", "tool_input": {"command": "echo hi"}}'
    for command in commands:  # a stale entry may be left; whatever is left lets the call through
        result = subprocess.run(
            ["sh", "-c", command],
            env={"PATH": env["PATH"], "CLAUDE_PROJECT_DIR": str(consumer)},
            input=call,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{command}\n{result.stderr}"
