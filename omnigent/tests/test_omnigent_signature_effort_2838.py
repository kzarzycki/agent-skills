"""The `Verifier:` line's effort comes from the start, the model's name, or the harness's own config (#2838)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from test_omnigent_agent import FakeOmnigent, omnigent_agent


def test_codex_effort_comes_from_its_config_when_the_start_names_none(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/config.toml").write_text(
        'model = "gpt-6.1-sol"\nmodel_reasoning_effort = "high"\n'
    )
    sig = omnigent_agent.signature("codex", "gpt-6.1-sol", None, ({}, tmp_path))
    assert sig == "codex/sol-6.1/high"
    # the start's own effort outranks the config
    assert (
        omnigent_agent.signature("codex", "gpt-6.1-sol", "low", ({}, tmp_path))
        == "codex/sol-6.1/low"
    )


def test_claude_effort_comes_from_its_settings_when_the_start_names_none(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text(json.dumps({"effortLevel": "xhigh"}))
    sig = omnigent_agent.signature("acp:claude-cloud", "claude-sonnet-5-5", None, ({}, tmp_path))
    assert sig == "cc/sonnet-5.5/xhigh"
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / "other")}
    assert (
        omnigent_agent.signature("claude", "claude-sonnet-5-5", None, (env, tmp_path))
        == "cc/sonnet-5.5/?"
    )


def test_agy_effort_comes_from_the_model_in_its_settings(tmp_path: Path) -> None:
    sig = omnigent_agent.signature(
        "antigravity-native", "Gemini 3.8 Flash (Low)", None, ({}, tmp_path)
    )
    assert sig == "agy/Gemini 3.8 Flash (Low)/low"


def test_an_agy_model_id_that_carries_its_effort_gives_it() -> None:
    sig = omnigent_agent.signature("antigravity-native", "gemini-4-hydrogen-medium", None)
    assert sig == "agy/gemini-4-hydrogen-medium/med"


def test_a_verifier_start_whose_effort_cannot_be_resolved_is_refused(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    og = FakeOmnigent()
    with pytest.raises(
        omnigent_agent.Fail, match=r"effort can't be resolved on codex.*config\.toml"
    ):
        omnigent_agent.start(
            og,
            "codex",
            "v",
            "review",
            tmp_path / "r.md",
            role_file("verifier.md"),
            0,
            model="gpt-6.1-sol",
        )
    assert og.archived == ["s0"]
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/config.toml").write_text('model_reasoning_effort = "medium"\n')
    omnigent_agent.start(
        og,
        "codex",
        "v",
        "review",
        tmp_path / "r.md",
        role_file("verifier.md"),
        0,
        model="gpt-6.1-sol",
    )
    assert "AGENT_SIGNATURE=codex/sol-6.1/med\n" in (tmp_path / "r.md.brief").read_text()


def test_an_agy_verifier_started_with_no_model_is_refused_with_a_hint_that_works(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """agy keeps its effort in its model id: right after create a session has none, so the hint names --model."""
    og = FakeOmnigent()
    og.harnesses["agy"] = "antigravity-native"
    with pytest.raises(
        omnigent_agent.Fail, match=r"antigravity-native.*--model with an id that carries"
    ):
        omnigent_agent.start(
            og,
            "agy",
            "v",
            "review",
            tmp_path / "r.md",
            role_file("verifier.md"),
            0,
            permission_mode="bypassPermissions",
        )
    assert og.archived == ["s0"]
    omnigent_agent.start(
        og,
        "agy",
        "v",
        "review",
        tmp_path / "r.md",
        role_file("verifier.md"),
        0,
        permission_mode="bypassPermissions",
        model="gemini-4-hydrogen-medium",
    )
    assert (
        "AGENT_SIGNATURE=agy/gemini-4-hydrogen-medium/med\n"
        in (tmp_path / "r.md.brief").read_text()
    )


def test_a_verifier_on_another_host_never_reads_this_machines_config(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fixture home holds a Codex config at medium, which is this machine's, not the far host's."""
    og = FakeOmnigent()
    with pytest.raises(omnigent_agent.Fail, match=r"codex.*not readable from here.*Pass --effort"):
        omnigent_agent.start(
            og,
            "codex",
            "v",
            "review",
            tmp_path / "r.md",
            role_file("verifier.md"),
            0,
            host_id="far",
            model="gpt-6.1-sol",
        )
    omnigent_agent.start(
        og,
        "codex",
        "v",
        "review",
        tmp_path / "r.md",
        role_file("verifier.md"),
        0,
        host_id="far",
        model="gpt-6.1-sol",
        effort="high",
    )
    assert "s1" in og.sessions and og.archived == ["s0"]
