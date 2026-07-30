from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
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
WAYFINDER_FACTS = (
    "paused subscriptions",
    "active=False",
    "test_cancel_deactivates_subscription",
)
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
    activation_skills: tuple[str, ...]
    response_text: str


@dataclass(frozen=True)
class AgentHarness:
    agent: AgentName
    root: Path
    environment: dict[str, str]

    @classmethod
    def create(cls, agent: AgentName, root: Path) -> AgentHarness:
        home = root / "home"
        config = root / "config"
        bin_dir = root / "bin"
        for directory in (home, config, bin_dir):
            directory.mkdir(parents=True)
        shutil.copy2(FAKE_GH, bin_dir / "gh")
        (bin_dir / "gh").chmod(0o755)
        fake_mise = bin_dir / "mise"
        fake_mise.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            'with open(os.environ["FAKE_MISE_LOG"], "a") as log:\n'
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            'raise SystemExit(0 if sys.argv[1:] == ["run", "agent-sync"] else 2)\n'
        )
        fake_mise.chmod(0o755)

        environment = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(config / "claude"),
            "CODEX_HOME": str(config / "codex"),
            "FAKE_GH_LOG": str(root / "gh.log"),
            "FAKE_GH_STATE": str(root / "gh-state.json"),
            "FAKE_MISE_LOG": str(root / "mise.log"),
        }
        for variable in PASSTHROUGH_CREDENTIALS[agent]:
            if value := os.environ.get(variable):
                environment[variable] = value
        return cls(agent=agent, root=root, environment=environment)

    @property
    def mise_calls(self) -> tuple[tuple[str, ...], ...]:
        path = Path(self.environment["FAKE_MISE_LOG"])
        if not path.exists():
            return ()
        return tuple(tuple(json.loads(line)) for line in path.read_text().splitlines())

    @property
    def github_calls(self) -> tuple[tuple[str, ...], ...]:
        path = Path(self.environment["FAKE_GH_LOG"])
        if not path.exists():
            return ()
        return tuple(tuple(json.loads(line)) for line in path.read_text().splitlines())

    @property
    def github_mutations(self) -> tuple[tuple[str, ...], ...]:
        read_only = {("issue", "list"), ("issue", "view")}
        return tuple(call for call in self.github_calls if call[:2] not in read_only)


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


def _json_events(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _relative_evidence(raw_path: str, repo: Path) -> str | None:
    path = Path(raw_path)
    candidate = path if path.is_absolute() else repo / path
    try:
        return candidate.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None


def _claude_trace(events: list[dict], repo: Path) -> tuple[list[str], list[str], list[str]]:
    skills: list[str] = []
    paths: list[str] = []
    messages: list[str] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                messages.append(block["text"])
            if block.get("type") != "tool_use":
                continue
            tool_input = block.get("input", {})
            if block.get("name") == "Skill":
                skill = tool_input.get("skill") or tool_input.get("name")
                if isinstance(skill, str):
                    skills.append(skill)
            if block.get("name") == "Read":
                path = tool_input.get("file_path")
                if isinstance(path, str) and (relative := _relative_evidence(path, repo)):
                    paths.append(relative)
    return skills, paths, messages


def _codex_trace(events: list[dict], repo: Path) -> tuple[list[str], list[str], list[str]]:
    skills: list[str] = []
    paths: list[str] = []
    messages: list[str] = []
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "agent_message" and isinstance(item.get("text"), str):
            messages.append(item["text"])
        if item_type == "command_execution" and isinstance(item.get("command"), str):
            for token in shlex.split(item["command"]):
                candidate = token.removesuffix(":")
                if (repo / candidate).is_file() and (
                    relative := _relative_evidence(candidate, repo)
                ):
                    parts = Path(relative).parts
                    if (
                        len(parts) == 4
                        and parts[:2] == (".agents", "skills")
                        and parts[3] == "SKILL.md"
                    ):
                        skills.append(parts[2])
                    else:
                        paths.append(relative)
    return skills, paths, messages


def _result(
    agent: AgentName,
    completed: subprocess.CompletedProcess[str],
    repo: Path,
) -> AgentResult:
    events = _json_events(completed.stdout)
    trace = _claude_trace(events, repo) if agent == "claude" else _codex_trace(events, repo)
    skills, paths, messages = trace
    return AgentResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        activation_skills=tuple(dict.fromkeys(skills)),
        evidence_paths=tuple(dict.fromkeys(paths)),
        response_text="\n".join(messages),
    )


def run_agent(
    agent: AgentName,
    prompt: str,
    repo: Path,
    *,
    harness: AgentHarness | None = None,
) -> AgentResult:
    if harness is not None:
        completed = subprocess.run(
            _command(agent, prompt, repo),
            cwd=repo,
            env=harness.environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        return _result(agent, completed, repo)

    with tempfile.TemporaryDirectory(prefix=f"engineering-{agent}-") as temporary:
        isolated = AgentHarness.create(agent, Path(temporary))
        completed = subprocess.run(
            _command(agent, prompt, repo),
            cwd=repo,
            env=isolated.environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        return _result(agent, completed, repo)


def _require_live_agent(agent: AgentName) -> None:
    flag = "CLAUDE_CODE_E2E" if agent == "claude" else "CODEX_E2E"
    if os.environ.get(flag) != "1":
        pytest.skip(f"{flag}=1 is required for the protected live-agent conformance test")
    if shutil.which(agent) is None:
        pytest.fail(f"{flag}=1 but the {agent} executable is absent")
    credentials = PASSTHROUGH_CREDENTIALS[agent]
    if not any(os.environ.get(variable) for variable in credentials):
        pytest.fail(f"{flag}=1 but credentials are absent; set one of: {', '.join(credentials)}")


def require_live_probes(probe_count: int) -> None:
    assert probe_count > 0, "strict qualification executed zero live probes"


def _tree_manifest(root: Path) -> dict[str, bytes]:
    excluded = {".agents", ".claude", ".git", ".pytest_cache", "__pycache__"}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not any(part in excluded for part in path.relative_to(root).parts)
    }


def _activation_prompt(agent: AgentName, skill_name: str) -> str:
    invocation = f"/{skill_name}" if agent == "claude" else f"${skill_name}"
    return (PROMPTS / "discover-skill.txt").read_text().format(invocation=invocation)


def _setup_prompt(agent: AgentName) -> str:
    invocation = (
        "/setup-engineering-workflow-for-apm"
        if agent == "claude"
        else "$setup-engineering-workflow-for-apm"
    )
    return f"""Invoke {invocation} in this disposable conformance fixture.
Use GitHub Issues as the tracker. E2E_SOURCE_CHANGES_APPROVED is my explicit
approval for the proposal produced in this run: write only the protocol source
files, then run its required compiler. Do not mutate issue-tracker state.
"""


def _wayfinder_prompt(agent: AgentName) -> str:
    invocation = "/wayfinder" if agent == "claude" else "$wayfinder"
    return (PROMPTS / "wayfinder-orient.txt").read_text().format(invocation=invocation)


def exercise_live_agent(agent: AgentName) -> None:
    _require_live_agent(agent)
    probe_count = 0
    with tempfile.TemporaryDirectory(prefix=f"engineering-{agent}-fixture-") as temporary:
        fixture = install_fixture(Path(temporary))
        repo = fixture.consumer
        harness = AgentHarness.create(agent, Path(temporary) / "agent-harness")

        for skill_name in sorted(fixture.expected_skills):
            result = run_agent(
                agent,
                _activation_prompt(agent, skill_name),
                repo,
                harness=harness,
            )
            probe_count += 1
            assert result.exit_code == 0, result.stderr
            assert skill_name in result.activation_skills

        before_setup = _tree_manifest(repo)
        setup = run_agent(agent, _setup_prompt(agent), repo, harness=harness)
        probe_count += 1
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
        assert harness.mise_calls == (("run", "agent-sync"),)
        assert harness.github_mutations == ()

        wayfinder = run_agent(agent, _wayfinder_prompt(agent), repo, harness=harness)
        probe_count += 1
        assert wayfinder.exit_code == 0, wayfinder.stderr
        assert "wayfinder" in wayfinder.activation_skills
        assert wayfinder.evidence_paths == EVIDENCE_PATHS
        assert all(fact in wayfinder.response_text for fact in WAYFINDER_FACTS)
        assert harness.github_mutations == ()

    require_live_probes(probe_count)
