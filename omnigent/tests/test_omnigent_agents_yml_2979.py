"""omnigent_agent.py: every start's model and effort come from agents.yml, never from code (#2979)."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from test_omnigent_agent import FakeOmnigent, agents_yml, omnigent_agent

SCRIPTS = Path(__file__).resolve().parents[2]


def config(text: str, project: str = "") -> dict:
    """The merged config of a setup file and a project's, as a start reads them."""
    base = omnigent_agent.tagged(omnigent_agent.parse_yaml(text, "setup"), "setup")
    over = omnigent_agent.tagged(omnigent_agent.parse_yaml(project, "project"), "project")
    return omnigent_agent.merged(base, over)


def pick(conf: dict, role: str, job: dict | None = None, flags: dict | None = None) -> dict:
    got = omnigent_agent.resolve(conf, role, lambda: job or {}, flags)
    return {key: got[key] for key in ("model", "effort")}


FILE = """\
effort: medium            # every agent
lead:
  model: lead-m
  by_size: {XS: {model: xs-m, effort: low}, S: {model: s-m}}
worker:
  model: worker-m
  effort: high
  by_risk:
    low: {model: low-m, effort: low}
verifier:
  route: codex
  model: verifier-m
  by_risk: {low: {model: cheap-m}}
helper: {model: helper-m, effort: low}
"""


def test_each_level_overrides_the_one_below() -> None:
    conf = config(FILE)
    assert pick(conf, "verifier") == {
        "model": ("verifier-m", "setup"),
        "effort": ("medium", "setup"),
    }
    assert pick(conf, "worker")["effort"] == (
        "high",
        "setup",
    )  # the role's own over the top level's
    assert pick(conf, "")["model"] == (None, "harness")  # no top-level model: the harness decides
    project = "worker:\n  model: project-m\n"
    assert pick(config(FILE, project), "worker")["model"] == ("project-m", "project")
    assert pick(config(FILE, project), "worker")["effort"] == ("high", "setup")  # key by key
    flagged = pick(config(FILE, project), "worker", flags={"model": "flag-m"})
    assert flagged["model"] == ("flag-m", "flag")


def test_by_size_and_by_risk_match_and_an_unmatched_job_falls_through_to_its_role() -> None:
    conf = config(FILE)
    assert pick(conf, "lead", {"size": "XS"}) == {
        "model": ("xs-m", "setup"),
        "effort": ("low", "setup"),
    }
    assert pick(conf, "lead", {"size": "S"})["model"] == ("s-m", "setup")
    assert pick(conf, "lead", {"size": "M"})["model"] == ("lead-m", "setup")
    assert pick(conf, "lead", {"size": None})["model"] == ("lead-m", "setup")
    assert pick(conf, "verifier", {"risk": "low"})["model"] == ("cheap-m", "setup")
    assert pick(conf, "verifier", {"risk": "high"})["model"] == ("verifier-m", "setup")
    assert pick(conf, "worker", {"risk": "low"})["effort"] == ("low", "setup")


def test_an_effort_set_at_a_deeper_level_wins() -> None:
    conf = config(FILE)
    assert pick(conf, "worker", {"risk": "low"})["effort"] == ("low", "setup")
    assert pick(conf, "worker", {"risk": "high"})["effort"] == ("high", "setup")
    assert pick(conf, "lead", {"size": "S"})["effort"] == ("medium", "setup")  # S sets none


def test_a_nested_project_entry_wins_over_a_setup_key_above_it() -> None:
    conf = config("lead:\n  model: a\n", "lead:\n  by_size: {XS: {model: b}}\n")
    assert pick(conf, "lead", {"size": "XS"})["model"] == ("b", "project")
    assert pick(conf, "lead", {"size": "L"})["model"] == ("a", "setup")


def test_the_reader_takes_block_and_flow_forms_comments_and_quotes() -> None:
    got = omnigent_agent.parse_yaml(
        "# a comment\nverifier:\n  route: 'gemini'  # why\n  fallback: [codex, claude]\n"
        "  by_risk:\n    low: {model: m}\n",
        "f",
    )
    assert got == {
        "verifier": {
            "route": "gemini",
            "fallback": ["codex", "claude"],
            "by_risk": {"low": {"model": "m"}},
        }
    }
    for bad in ("no colon here\n", "a:\n    b: 1\n  c: 2\n"):
        with pytest.raises(omnigent_agent.Fail):
            omnigent_agent.parse_yaml(bad, "f")


def start(
    tmp_path: Path, agent: str, *, brief: str = "do X", role: str | None = None, **kw: object
) -> tuple[FakeOmnigent, str]:
    og = FakeOmnigent()
    sid, _ = omnigent_agent.start(og, agent, "t", brief, tmp_path / "r.md", role, 0, **kw)
    return og, sid


def test_with_nothing_set_a_start_sends_no_model_or_effort_and_says_harness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og, sid = start(tmp_path, "codex")
    assert og.overrides[sid] is None and og.efforts[sid] is None
    assert "model: the harness default (from harness)" in capsys.readouterr().err


def test_a_start_prints_where_each_value_came_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    agents_yml("model: gpt-6.1-sol\neffort: low\n")
    repo = tmp_path / "repo"
    (repo / ".agents").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".agents" / "agents.yml").write_text("effort: high\n")
    og, sid = start(tmp_path, "codex", workspace=str(repo))
    assert (og.overrides[sid], og.efforts[sid]) == ("gpt-6.1-sol", "high")
    assert "model: gpt-6.1-sol (from setup), effort: high (from project)" in capsys.readouterr().err
    og, sid = start(tmp_path, "codex", workspace=str(repo), model="gpt-6.1-terra", effort="medium")
    assert (og.overrides[sid], og.efforts[sid]) == ("gpt-6.1-terra", "medium")
    assert "(from flag), effort: medium (from flag)" in capsys.readouterr().err


@pytest.fixture
def issues(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, list[str]]], None]:
    """`gh api repos/o/r/issues/<n>` answering each issue's labels."""
    monkeypatch.setattr(omnigent_agent, "repo_slug", lambda cwd=None: "o/r")

    def given(labels: dict[str, list[str]]) -> None:
        def gh(*args: str, **_kw: object) -> str:
            number = re.search(r"issues/(\d+)", args[1])[1]  # type: ignore[index]
            return "\n".join(labels.get(number, []))

        monkeypatch.setattr(omnigent_agent, "gh", gh)

    return given


def test_a_lead_start_for_an_xs_issue_runs_the_xs_entry_and_an_m_issue_the_leads_own(
    tmp_path: Path, issues: Callable[[dict[str, list[str]]], None]
) -> None:
    agents_yml("lead:\n  model: claude-sonnet-5-5\n  by_size: {XS: {model: opus}}\n")
    issues({"1": ["size:XS"], "2": ["size:M"]})
    og, sid = start(tmp_path, "claude", brief="Work on #1", top_level=True)
    assert og.overrides[sid] == "opus"
    og, sid = start(tmp_path, "claude", brief="Work on #2", top_level=True)
    assert og.overrides[sid] == "claude-sonnet-5-5"
    og, sid = start(tmp_path, "claude", brief="Work on #1 and #2", top_level=True)
    assert og.overrides[sid] == "claude-sonnet-5-5"  # the largest size on the brief's issues


def test_a_worker_start_reads_the_risk_label_of_the_issue(
    tmp_path: Path, issues: Callable[[dict[str, list[str]]], None], role_file: Callable[[str], str]
) -> None:
    agents_yml("worker:\n  model: claude-sonnet-5-5\n  by_risk: {low: {model: opus}}\n")
    issues({"1": ["risk:low"], "2": ["risk:high", "risk:low"]})
    og, sid = start(tmp_path, "claude", brief="Work on #1", role=role_file("worker.md"))
    assert og.overrides[sid] == "opus"
    og, sid = start(tmp_path, "claude", brief="Work on #2", role=role_file("worker.md"))
    assert og.overrides[sid] == "claude-sonnet-5-5"


def test_a_verifier_start_runs_by_risk_low_on_a_low_rated_pr_and_its_own_model_on_a_high_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role_file: Callable[[str], str]
) -> None:
    agents_yml("verifier:\n  model: claude-sonnet-5-5\n  by_risk: {low: {model: opus}}\n")
    monkeypatch.setattr(omnigent_agent, "installed", lambda skill, **_k: tmp_path)
    rated = {"level": "low"}
    asked: list[tuple[list[str], object]] = []
    real = subprocess.run

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess:
        if "check" not in cmd:
            return real(cmd, **kw)  # type: ignore[call-overload]
        asked.append((cmd[-3:], kw.get("cwd")))
        said = f"PR #7: rerun: not needed (off) (rated {rated['level']})\n"
        return subprocess.CompletedProcess(cmd, 0, said, "")

    monkeypatch.setattr(omnigent_agent.subprocess, "run", run)
    for level, model in (
        ("low", "opus"),
        ("high", "claude-sonnet-5-5"),
        ("medium", "claude-sonnet-5-5"),
    ):
        rated["level"] = level
        og, sid = start(tmp_path, "claude", role=role_file("verifier.md"), about=7)
        assert og.overrides[sid] == model, level
    # a read-only rating (`check rerun`, never `check merge`'s label writes) in the workspace's own repository
    assert {cmd[:2] == ["check", "rerun"] for cmd, _ in asked} == {True}
    assert {Path(str(cwd)).resolve() for _, cwd in asked} == {Path.cwd().resolve()}


def test_a_literal_model_id_in_a_skills_scripts_fails() -> None:
    ids = re.compile(r"gpt-[0-9]|claude-(opus|sonnet|haiku|fable)|OMNIGENT_(MODEL|EFFORT|SMALL)")
    found = [
        f"{path.relative_to(SCRIPTS)}:{n}"
        for path in SCRIPTS.glob("[!.]*/skills/*/scripts/*.py")
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if ids.search(line) and not line.lstrip().startswith("#")
    ]
    assert found == [], "model ids live in agents.yml, never in a skill's scripts"


def test_a_yaml_block_list_is_read_like_the_flow_form() -> None:
    block = omnigent_agent.parse_yaml(
        "verifier:\n  fallback:\n    - codex\n    - claude\n  route: x\n", "f"
    )
    assert block == {"verifier": {"fallback": ["codex", "claude"], "route": "x"}}
    flush = omnigent_agent.parse_yaml("verifier:\n  fallback:\n  - claude\n", "f")
    assert flush == {"verifier": {"fallback": ["claude"]}}


def test_a_model_the_file_names_for_one_route_is_not_sent_to_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role_file: Callable[[str], str]
) -> None:
    agents_yml("verifier:\n  route: codex\n  model: gpt-6.1-sol\n")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("review")
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    base = [
        "start",
        "codex",
        "t",
        "b.md",
        str(tmp_path / "r.md"),
        "--role",
        role_file("verifier.md"),
    ]
    assert omnigent_agent.main(base) == 0
    assert og.overrides["s0"] == "gpt-6.1-sol"
    og = FakeOmnigent()
    assert omnigent_agent.main([*base, "--verifier-route", "claude"]) == 0
    assert og.overrides["s0"] is None  # the Claude route runs its harness's own model
