from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from engineering.tests.e2e.conformance import install_fixture

AgentName = Literal["claude", "codex"]
PROMPTS = Path(__file__).parent / "prompts"
FAKE_GH = Path(__file__).parents[1] / "fixtures" / "fake-gh"
EVIDENCE_PATHS = ("README.md", "src/domain.py", "tests/test_domain.py")
PASSTHROUGH_CREDENTIALS = {
    "claude": ("ANTHROPIC_API_KEY",),
    "codex": ("OPENAI_API_KEY",),
}


@dataclass(frozen=True)
class AgentResult:
    exit_code: int
    stdout: str
    stderr: str
    evidence_paths: tuple[str, ...]


def _agent_environment(agent: AgentName, root: Path) -> dict[str, str]:
    home = root / "home"
    config = root / "config"
    bin_dir = root / "bin"
    for directory in (home, config, bin_dir):
        directory.mkdir(parents=True)
    shutil.copy2(FAKE_GH, bin_dir / "gh")
    (bin_dir / "gh").chmod(0o755)
    fake_mise = bin_dir / "mise"
    fake_mise.write_text(
        '#!/bin/sh\ntest "$#" -eq 2 && test "$1" = "run" && test "$2" = "agent-sync"\n'
    )
    fake_mise.chmod(0o755)

    environment = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(config / "claude"),
        "CODEX_HOME": str(config / "codex"),
        "FAKE_GH_LOG": str(root / "gh.log"),
        "FAKE_GH_STATE": str(root / "gh-state.json"),
    }
    for variable in PASSTHROUGH_CREDENTIALS[agent]:
        if value := os.environ.get(variable):
            environment[variable] = value
    return environment


def _command(agent: AgentName, prompt: str, repo: Path) -> list[str]:
    if agent == "claude":
        return [
            "claude",
            "-p",
            "--bare",
            "--output-format",
            "stream-json",
            "--no-session-persistence",
            "--permission-mode",
            "acceptEdits",
            prompt,
        ]
    return [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(repo),
        prompt,
    ]


def run_agent(agent: AgentName, prompt: str, repo: Path) -> AgentResult:
    with tempfile.TemporaryDirectory(prefix=f"engineering-{agent}-") as temporary:
        environment = _agent_environment(agent, Path(temporary))
        result = subprocess.run(
            _command(agent, prompt, repo),
            cwd=repo,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
    evidence_paths = tuple(path for path in EVIDENCE_PATHS if path in result.stdout)
    return AgentResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        evidence_paths=evidence_paths,
    )


def _require_live_agent(agent: AgentName) -> None:
    flag = "CLAUDE_CODE_E2E" if agent == "claude" else "CODEX_E2E"
    if os.environ.get(flag) != "1":
        pytest.skip(f"{flag}=1 is required for the protected live-agent conformance test")
    if shutil.which(agent) is None:
        pytest.skip(f"{agent} executable is not installed")
    credentials = PASSTHROUGH_CREDENTIALS[agent]
    if not any(os.environ.get(variable) for variable in credentials):
        pytest.skip(f"{flag}=1 but credentials are absent; set one of: {', '.join(credentials)}")


def _tree_manifest(root: Path) -> dict[str, bytes]:
    excluded = {".agents", ".claude", ".git", ".pytest_cache", "__pycache__"}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not any(part in excluded for part in path.relative_to(root).parts)
    }


def _activation_prompt(agent: AgentName, skill_name: str) -> str:
    invocation = f"/{skill_name}" if agent == "claude" else f"${skill_name}"
    return (
        (PROMPTS / "discover-skill.txt")
        .read_text()
        .format(
            invocation=invocation,
            skill_name=skill_name,
        )
    )


def _setup_prompt(agent: AgentName) -> str:
    invocation = (
        "/setup-engineering-workflow-for-apm"
        if agent == "claude"
        else "$setup-engineering-workflow-for-apm"
    )
    return f"""Invoke {invocation} in this disposable conformance fixture.
Use GitHub Issues as the tracker. E2E_SOURCE_CHANGES_APPROVED is my explicit
approval for the proposal produced in this run: write only the two protocol
source files, then invoke exactly `mise run agent-sync`. The harness replaces
that compiler command with a no-op. Do not create, edit, or close any issue.
"""


def exercise_live_agent(agent: AgentName) -> None:
    _require_live_agent(agent)
    with tempfile.TemporaryDirectory(prefix=f"engineering-{agent}-fixture-") as temporary:
        fixture = install_fixture(Path(temporary))
        repo = fixture.consumer

        for skill_name in sorted(fixture.expected_skills):
            result = run_agent(agent, _activation_prompt(agent, skill_name), repo)
            assert result.exit_code == 0, result.stderr
            assert f"ACTIVATED_SKILL: {skill_name}" in result.stdout

        before_setup = _tree_manifest(repo)
        setup = run_agent(agent, _setup_prompt(agent), repo)
        assert setup.exit_code == 0, setup.stderr
        after_setup = _tree_manifest(repo)
        changed = {
            path
            for path in before_setup.keys() | after_setup.keys()
            if before_setup.get(path) != after_setup.get(path)
        }
        assert changed == {
            ".apm/instructions/engineering-workflow.md",
            "docs/agents/issue-tracker.md",
        }
        assert all(path.startswith((".apm/instructions/", "docs/agents/")) for path in changed)

        wayfinder_prompt = (
            (PROMPTS / "wayfinder-orient.txt")
            .read_text()
            .format(invocation="/wayfinder" if agent == "claude" else "$wayfinder")
        )
        wayfinder = run_agent(agent, wayfinder_prompt, repo)
        assert wayfinder.exit_code == 0, wayfinder.stderr
        assert wayfinder.evidence_paths == EVIDENCE_PATHS
