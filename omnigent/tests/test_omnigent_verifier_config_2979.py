"""omnigent_agent.py: a Codex verifier's model and effort come from configuration, never from code (#2979): flags, then
loop.md's `verifier:` section, then the setup's values file, then Codex's own config; `models` maps the PR's risk level
to a model id."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_omnigent_agent import FakeOmnigent, omnigent_agent

LOW, HIGH, OTHER = "gpt-6.1-luna", "gpt-6.1-terra", "gpt-6.1-sol"
SETUP = f"verifier:\n  route: codex\n  models: {{low: {LOW}, default: {HIGH}}}\n  effort: low\n"
SCRIPTS = (
    "omnigent/skills/omnigent-agents/scripts/omnigent_agent.py",
    "loop/skills/engineering-loop/scripts/cloud_verifier.py",
)


def project(tmp_path: Path, block: str) -> None:
    """loop.md's settings block, holding `block` (the lines under `verifier:`)."""
    (tmp_path / "docs/agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs/agents/loop.md").write_text(
        f"# Loop\n\n## Settings\n\n```yaml\nverifier:\n{block}```\n"
    )


def started(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    setup: str | None = None,
    level: str | None = None,
    extra: tuple[str, ...] = (),
) -> tuple[FakeOmnigent, str]:
    """A Codex verifier start of a PR the gate rates `level` (None: it can't be rated); the fake server and the
    stderr the start printed."""
    og = FakeOmnigent()
    og.listed = [LOW, HIGH, OTHER]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "codex_pass_on_head", lambda _pr: None)
    monkeypatch.setattr(omnigent_agent, "verifier_risk", lambda _pr, _policy: level)
    for name in ("OMNIGENT_MODEL_CODEX", "OMNIGENT_EFFORT_CODEX", "OMNIGENT_VERIFIER_ROUTE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("COS_VALUES", raising=False)
    monkeypatch.chdir(tmp_path)
    if setup is not None:
        (tmp_path / "cos-values.yml").write_text(setup)
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
    assert omnigent_agent.main([*argv, *extra]) == 0
    return og, ""


def run(
    capsys: pytest.CaptureFixture[str], *args: object, **kwargs: object
) -> tuple[tuple[str | None, str | None], str]:
    og, _ = started(*args, **kwargs)  # type: ignore[arg-type]
    return (og.overrides["s0"], og.efforts["s0"]), capsys.readouterr().err


def test_the_setups_models_run_the_low_model_on_a_low_pr_and_the_default_on_the_rest(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for level, model in (("low", LOW), ("high", HIGH), ("critical", HIGH), (None, HIGH)):
        got, err = run(capsys, tmp_path, role_file, monkeypatch, setup=SETUP, level=level)
        assert got[0] == model, level
        assert f"verifier model: {model} (setup)" in err


def test_the_projects_models_override_the_setups_key_by_key(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project(tmp_path, f"  models:\n    low: {OTHER}\n")
    low, err = run(capsys, tmp_path, role_file, monkeypatch, setup=SETUP, level="low")
    assert low[0] == OTHER and f"verifier model: {OTHER} (project)" in err
    high, err = run(capsys, tmp_path, role_file, monkeypatch, setup=SETUP, level="high")
    assert high[0] == HIGH and f"verifier model: {HIGH} (setup)" in err


def test_a_flag_overrides_the_project_and_the_setup(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project(tmp_path, f"  models:\n    default: {LOW}\n  effort: high\n")
    got, err = run(
        capsys,
        tmp_path,
        role_file,
        monkeypatch,
        setup=SETUP,
        level="low",
        extra=("--model", OTHER, "--effort", "medium"),
    )
    assert got == (OTHER, "medium")
    assert f"verifier model: {OTHER} (flag), effort: medium (flag)" in err


def test_the_effort_follows_the_same_precedence(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    got, err = run(capsys, tmp_path, role_file, monkeypatch, setup=SETUP, level="high")
    assert got[1] == "low" and "effort: low (setup)" in err
    project(tmp_path, "  effort: high\n")
    got, err = run(capsys, tmp_path, role_file, monkeypatch, setup=SETUP, level="high")
    assert got[1] == "high" and "effort: high (project)" in err
    got, err = run(
        capsys,
        tmp_path,
        role_file,
        monkeypatch,
        setup=SETUP,
        level="high",
        extra=("--effort", "medium"),
    )
    assert got[1] == "medium" and "effort: medium (flag)" in err


def test_with_no_setting_the_start_sends_no_model_or_effort_and_says_codex_config(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    got, err = run(capsys, tmp_path, role_file, monkeypatch, level="low")
    assert got == (None, None)
    assert "verifier model: codex config, effort: codex config" in err


def test_models_wins_over_model_and_the_start_says_model_is_ignored(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    both = f"verifier:\n  route: codex\n  model: {OTHER}\n  models: {{default: {HIGH}}}\n"
    got, err = run(capsys, tmp_path, role_file, monkeypatch, setup=both, level="low")
    assert got[0] == HIGH
    ignored = [line for line in err.splitlines() if "is ignored" in line]
    assert len(ignored) == 1 and OTHER in ignored[0] and "verifier.models" in ignored[0]


def test_the_setups_keys_apply_to_the_codex_route_only(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = f"verifier:\n  route: gemini\n  models: {{default: {HIGH}}}\n  effort: low\n"
    got, err = run(
        capsys,
        tmp_path,
        role_file,
        monkeypatch,
        setup=other,
        level="low",
        extra=("--verifier-route", "codex"),
    )
    assert got == (None, None) and "codex config" in err


@pytest.mark.parametrize(
    "text",
    [
        f"verifier:\n  route: codex\n  models:\n    low: {LOW}\n    default: {HIGH}\n  effort: medium\n",
        f"verifier: {{route: codex, models: {{low: {LOW}, default: {HIGH}}}, effort: medium}}\n",
        f"verifier:\n  route: codex\n  models: {{low: '{LOW}', default: \"{HIGH}\"}}  # ids\n  effort: medium\n",
    ],
    ids=["block", "flow", "mixed"],
)
def test_the_setup_reads_models_and_effort_in_block_and_flow_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    monkeypatch.delenv("COS_VALUES", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cos-values.yml").write_text(text + "hygiene:\n  repos: [a/b]\n")
    assert omnigent_agent.verifier_setting() == {
        "route": "codex",
        "models": {"low": LOW, "default": HIGH},
        "effort": "medium",
    }


def test_the_projects_section_is_read_by_the_gatekeepers_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert omnigent_agent.project_verifier() == ({}, None)
    project(tmp_path, f"  models:\n    default: {HIGH}\n  effort: high\n")
    section, policy = omnigent_agent.project_verifier()
    assert section == {"models": {"default": HIGH}, "effort": "high"} and policy


def test_the_risk_is_the_one_the_gate_rates_and_a_rating_that_cannot_be_read_is_unrated(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[object] = []

    def risk_level(pull: object, issues: object, policy: object) -> str:
        seen.append((pull, issues, policy))
        return "high"

    gk = SimpleNamespace(
        pull_request=lambda n: {"number": n},
        rated_issues=lambda pull: [pull["number"]],
        risk_level=risk_level,
    )
    monkeypatch.setattr(omnigent_agent, "_load_gatekeeper", lambda: gk)
    assert omnigent_agent.verifier_risk(7, "policy") == "high"
    assert seen == [({"number": 7}, [7], "policy")]
    assert omnigent_agent.verifier_risk(None, "policy") is None

    def down(_n: int) -> dict:
        raise RuntimeError("no forge")

    gk.pull_request = down  # type: ignore[assignment]
    assert omnigent_agent.verifier_risk(7, "policy") is None
    assert "unrated" in capsys.readouterr().err


def test_no_model_id_is_a_literal_in_either_script() -> None:
    root = Path(__file__).resolve().parents[2]
    for script in SCRIPTS:
        found = re.findall(r"gpt-\d[\w.-]*", (root / script).read_text())
        assert found == [], f"{script} names a model id: {found}"
