"""omnigent_agent.py: a Codex verifier start with no model or effort named runs Terra at medium effort, and a second Codex
start on a head that already has a pass is refused, naming it (#2870)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from test_omnigent_agent import FakeOmnigent, omnigent_agent


def start(tmp_path: Path, role_file: Callable[[str], str], *more: str) -> list[str]:
    (tmp_path / "b.md").write_text("review")
    argv = [
        "start",
        "codex",
        "t",
        "b.md",
        str(tmp_path / "r.md"),
        "--role",
        role_file("verifier.md"),
    ]
    return [*argv, *more]


def test_a_codex_verifier_start_with_no_model_or_effort_runs_terra_at_medium(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    assert omnigent_agent.main(start(tmp_path, role_file)) == 0
    assert (og.overrides["s0"], og.efforts["s0"]) == ("gpt-6.1-terra", "medium")


def test_the_effort_variable_outranks_the_default_effort(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setenv("OMNIGENT_EFFORT_CODEX", "high")
    monkeypatch.chdir(tmp_path)
    assert omnigent_agent.main(start(tmp_path, role_file)) == 0
    assert og.efforts["s0"] == "high"


def test_a_start_that_names_a_model_and_effort_keeps_them(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    argv = start(tmp_path, role_file, "--model", "gpt-6.1-sol", "--effort", "high")
    assert omnigent_agent.main(argv) == 0
    assert (og.overrides["s0"], og.efforts["s0"]) == ("gpt-6.1-sol", "high")


def test_a_pass_already_on_the_head_is_found_in_a_review_or_a_comment() -> None:
    head = "a" * 40
    review = {"commit_id": head, "body": "**Verifier (codex/terra-6.1/med), pass 1**"}
    comment = {"body": f"Head: {head}\n\nVerifier: codex/sol-6.1/high, pass 2\n"}
    assert omnigent_agent.earlier_codex_pass([review], [comment], head) == (
        "codex/sol-6.1/high",
        "2",
    )
    assert omnigent_agent.earlier_codex_pass([review], [], "b" * 40) is None  # a fix was pushed
    claude = {"commit_id": head, "body": "Verifier (claude, same-family), pass 1"}
    assert omnigent_agent.earlier_codex_pass([claude], [], head) is None


def test_the_refusal_names_the_earlier_pass_and_a_forge_that_cannot_answer_refuses_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "c" * 40
    answers = {
        "repos/{owner}/{repo}/pulls/7": json.dumps({"head": {"sha": head}}),
        "repos/{owner}/{repo}/pulls/7/reviews": json.dumps(
            [{"commit_id": head, "body": "**Verifier (codex/terra-6.1/med), pass 3**"}]
        ),
        "repos/{owner}/{repo}/issues/7/comments": "[]",
    }

    def gh(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, answers[cmd[-1]], "")

    monkeypatch.setattr(omnigent_agent.subprocess, "run", gh)
    why = omnigent_agent.codex_pass_on_head(7)
    assert why and "codex/terra-6.1/med, pass 3" in why and head[:12] in why
    assert omnigent_agent.codex_pass_on_head(None) is None

    def down(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(omnigent_agent.subprocess, "run", down)
    assert omnigent_agent.codex_pass_on_head(7) is None


def test_the_terra_tier_is_the_newest_generations_else_its_closest_higher_tier() -> None:
    pick = omnigent_agent.tier_model
    assert pick(["gpt-6.1-sol", "gpt-6.1-terra", "gpt-6.1-luna"], "terra") == "gpt-6.1-terra"
    # 6.2 lists only sol and astra: Sol, never 6.1's Terra, which an older generation start refuses
    assert pick(["gpt-6.1-terra", "gpt-6.2-sol", "gpt-6.2-astra"], "terra") == "gpt-6.2-sol"
    assert pick(["gpt-6.2-astra", "gpt-6.1-sol"], "terra") == "gpt-6.2-astra"
    assert pick(["claude-opus-5-5", "opus"], "terra") is None


def test_a_codex_verifier_start_follows_the_newest_generation(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.listed = ["gpt-6.1-terra", "gpt-6.2-sol", "gpt-6.2-astra"]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.delenv("OMNIGENT_MODEL_CODEX", raising=False)
    monkeypatch.chdir(tmp_path)
    assert omnigent_agent.main(start(tmp_path, role_file)) == 0
    assert og.overrides["s0"] == "gpt-6.2-sol"


def test_the_model_variable_outranks_the_terra_tier(
    tmp_path: Path, role_file: Callable[[str], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.listed = ["gpt-6.1-terra", "gpt-6.2-sol", "gpt-6.2-astra"]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setenv("OMNIGENT_MODEL_CODEX", "gpt-6.2-astra")
    monkeypatch.chdir(tmp_path)
    assert omnigent_agent.main(start(tmp_path, role_file)) == 0
    assert og.overrides["s0"] == "gpt-6.2-astra"
