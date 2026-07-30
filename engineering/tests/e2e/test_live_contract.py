from __future__ import annotations

import json
from pathlib import Path

import pytest

from engineering.tests.e2e.live_contract import (
    EVIDENCE_PATHS,
    WAYFINDER_FACTS,
    _activation_prompt,
    _require_live_agent,
    _wayfinder_prompt,
    require_live_probes,
    run_agent,
)


def _event_lines(agent: str, repo: Path) -> str:
    if agent == "claude":
        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "input": {"skill": "wayfinder"},
                        },
                        *[
                            {
                                "type": "tool_use",
                                "name": "Read",
                                "input": {"file_path": str(repo / path)},
                            }
                            for path in EVIDENCE_PATHS
                        ],
                        {"type": "text", "text": " ".join(WAYFINDER_FACTS)},
                    ]
                },
            }
        ]
    else:
        events = [
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "cat .agents/skills/wayfinder/SKILL.md",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "sed -n 1,160p " + " ".join(EVIDENCE_PATHS),
                },
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": " ".join(WAYFINDER_FACTS)},
            },
        ]
    return "\n".join(json.dumps(event) for event in events)


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_structured_agent_events_are_the_only_activation_and_evidence_oracle(
    agent: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    skill = repo / ".agents" / "skills" / "wayfinder" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Wayfinder\n")
    for relative in EVIDENCE_PATHS:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture: {relative}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / agent
    payload = _event_lines(agent, repo)
    executable.write_text(f"#!/bin/sh\nprintf '%s\\n' '{payload}'\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

    result = run_agent(agent, "prompt without result literals", repo)

    assert result.activation_skills == ("wayfinder",)
    assert result.evidence_paths == EVIDENCE_PATHS
    assert all(fact in result.response_text for fact in WAYFINDER_FACTS)


def test_exact_echo_probe_cannot_fake_activation_or_wayfinder_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").symlink_to("/bin/echo")
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")

    activation = run_agent("claude", _activation_prompt("claude", "wayfinder"), repo)
    wayfinder = run_agent("claude", _wayfinder_prompt("claude"), repo)

    assert activation.activation_skills == ()
    assert wayfinder.evidence_paths == ()
    assert wayfinder.response_text == ""


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_live_prompts_do_not_contain_result_oracles(agent: str) -> None:
    activation = _activation_prompt(agent, "wayfinder")
    wayfinder = _wayfinder_prompt(agent)

    assert "ACTIVATED_SKILL:" not in activation
    for expected in (*EVIDENCE_PATHS, *WAYFINDER_FACTS):
        assert expected not in wayfinder


@pytest.mark.parametrize(
    ("agent", "flag", "credential"),
    [
        ("claude", "CLAUDE_CODE_E2E", "ANTHROPIC_API_KEY"),
        ("codex", "CODEX_E2E", "OPENAI_API_KEY"),
    ],
)
def test_explicit_live_request_fails_without_credentials(
    agent: str,
    flag: str,
    credential: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(flag, "1")
    monkeypatch.delenv(credential, raising=False)
    monkeypatch.setattr("shutil.which", lambda _: f"/usr/bin/{agent}")

    with pytest.raises(BaseException) as raised:
        _require_live_agent(agent)
    assert isinstance(raised.value, pytest.fail.Exception)
    assert "credentials are absent" in str(raised.value)


@pytest.mark.parametrize(
    ("agent", "flag", "credential"),
    [
        ("claude", "CLAUDE_CODE_E2E", "ANTHROPIC_API_KEY"),
        ("codex", "CODEX_E2E", "OPENAI_API_KEY"),
    ],
)
def test_explicit_live_request_fails_without_agent_command(
    agent: str,
    flag: str,
    credential: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(flag, "1")
    monkeypatch.setenv(credential, "fixture-credential")
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(BaseException) as raised:
        _require_live_agent(agent)
    assert isinstance(raised.value, pytest.fail.Exception)
    assert "executable is absent" in str(raised.value)


def test_strict_live_gate_rejects_zero_probes() -> None:
    with pytest.raises(AssertionError, match="zero live probes"):
        require_live_probes(0)
