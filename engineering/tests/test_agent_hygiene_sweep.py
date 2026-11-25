"""agent-hygiene's daily session sweep (#1580): once a day, through omnigent-agents' `sweep`."""

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/agent-hygiene/scripts/agent-hygiene"
CARD = {
    "questions": [
        {
            "question": "Archive?",
            "multiSelect": True,
            "options": [{"label": "Archive all (Recommended)"}, {"label": "Keep x (s9)"}],
        }
    ]
}


def load(home, monkeypatch, name):
    monkeypatch.setenv("HOME", str(home))
    loader = importlib.machinery.SourceFileLoader(name, str(SCRIPT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    sys.dont_write_bytecode, saved = True, sys.dont_write_bytecode
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    module.STATE.mkdir(parents=True)
    return module


def fake_sweep(home, code=0):
    """A stand-in omnigent_agent.py in the home skill install: logs its argv, prints a line and the card."""
    script = home / ".agents/skills/omnigent-agents/scripts/omnigent_agent.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "import json, sys\n"
        f"open({str(home / 'calls')!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "print('s1 t: archived (idle)')\n"
        f"print('CARD: ' + json.dumps({CARD!r}))\n"
        f"sys.exit({code})\n"
    )


def calls(home):
    path = home / "calls"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_the_sweep_runs_once_a_day_with_the_keep_list_and_hands_back_the_card(
    tmp_path, monkeypatch
):
    hygiene = load(tmp_path, monkeypatch, "agent_hygiene_sweep")
    fake_sweep(tmp_path)
    run = hygiene.Run(False, tmp_path / "log")
    assert json.loads(hygiene.session_sweep(run)) == CARD
    assert calls(tmp_path) == [
        ["sweep", "--keep-file", str(tmp_path / ".config/agent-hygiene/keep")]
    ]
    log = (tmp_path / "log").read_text()
    assert "sweep: s1 t: archived (idle)\n" in log and "CARD: {" in log and not run.failed
    # the round's second run, or a later round the same day: no second sweep, the same card again
    assert json.loads(hygiene.session_sweep(run)) == CARD
    assert (tmp_path / "log").read_text().count("CARD: {") == 2
    assert (
        len(calls(tmp_path)) == 1
        and "already swept in the last 20 h" in (tmp_path / "log").read_text()
    )


def test_a_failed_sweep_fails_the_run_and_sweeps_again_next_round(tmp_path, monkeypatch):
    hygiene = load(tmp_path, monkeypatch, "agent_hygiene_sweep_fail")
    fake_sweep(tmp_path, code=1)
    run = hygiene.Run(False, tmp_path / "log")
    hygiene.session_sweep(run)
    assert run.failed and "FAIL session sweep: exit 1" in (tmp_path / "log").read_text()
    hygiene.session_sweep(hygiene.Run(False, tmp_path / "log"))
    assert len(calls(tmp_path)) == 2


def test_a_dry_run_sweeps_dry_and_leaves_the_day_open(tmp_path, monkeypatch):
    hygiene = load(tmp_path, monkeypatch, "agent_hygiene_sweep_dry")
    fake_sweep(tmp_path)
    hygiene.session_sweep(hygiene.Run(True, tmp_path / "log"), dry_run=True)
    assert calls(tmp_path)[0][-1] == "--dry-run" and not (hygiene.STATE / "swept").exists()


def test_without_omnigent_agents_the_sweep_is_skipped(tmp_path, monkeypatch):
    hygiene = load(tmp_path, monkeypatch, "agent_hygiene_sweep_none")
    run = hygiene.Run(False, tmp_path / "log")
    assert hygiene.session_sweep(run) is None and not run.failed
    assert "session sweep skipped" in (tmp_path / "log").read_text()


def test_the_skill_documents_the_sweep_and_the_keep_list():
    text = (SCRIPT.parents[1] / "SKILL.md").read_text()
    assert (
        "**Idle sessions**" in text
        and "~/.config/agent-hygiene/keep" in text
        and "at most once a day" in text
    )
