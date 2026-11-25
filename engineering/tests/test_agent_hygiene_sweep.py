"""agent-hygiene: once a day the round sweeps sessions idle over a day through omnigent_agent.py sweep, and hands
the owner card for those the owner talked to back to the round (#1580). Names are fake."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/agent-hygiene/scripts/agent-hygiene"
SKILL_MD = SCRIPT.parents[1] / "SKILL.md"
CARD = {
    "questions": [
        {"question": "Archive them?", "multiSelect": True, "options": [{"label": "Archive all"}]}
    ]
}


def load(name):
    loader = importlib.machinery.SourceFileLoader(name, str(SCRIPT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


@pytest.fixture
def hygiene(tmp_path, monkeypatch):
    """The script with its state, config and home skill install under tmp_path, and a fake omnigent_agent.py whose
    sweep prints ``out`` (written to its folder) and logs its argv."""
    module = load("agent_hygiene_sweep")
    skills = tmp_path / "skills"
    fake = skills / module.SWEEPER
    fake.parent.mkdir(parents=True)
    fake.write_text(
        "import json, sys, pathlib\n"
        "here = pathlib.Path(__file__).parent\n"
        "(here / 'argv').write_text(json.dumps(sys.argv[1:]))\n"
        "out = json.loads((here / 'out').read_text())\n"
        "print(out['stdout'], end='')\n"
        "sys.exit(out.get('code', 0))\n"
    )
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(module, "STATE", tmp_path / "state")
    monkeypatch.setattr(module, "KEEP_LIST", tmp_path / "config/keep-sessions")
    monkeypatch.setattr(module, "HOME_SKILLS", [tmp_path / "none", skills])
    monkeypatch.setattr(module, "configured_server", lambda: "http://omnigent.test")
    module.fake = fake.parent
    return module


def answer(hygiene, stdout, code=0):
    (hygiene.fake / "out").write_text(json.dumps({"stdout": stdout, "code": code}))


def run(hygiene, tmp_path, dry=False):
    r = hygiene.Run(dry, tmp_path / "run.log")
    return r, hygiene.sweep(r, dry)


def test_a_round_sweeps_through_omnigent_agent_with_the_keep_list_and_returns_the_card(
    hygiene, tmp_path, capsys
):
    answer(
        hygiene,
        json.dumps({"lines": ["s1 t: archived (idle)"], "owner": [{"id": "s2"}], "card": CARD}),
    )
    r, card = run(hygiene, tmp_path)
    assert card == CARD and not r.failed
    argv = json.loads((hygiene.fake / "argv").read_text())
    assert argv == [
        "--server",
        "http://omnigent.test",
        "sweep",
        "--json",
        "--keep-list",
        str(hygiene.KEEP_LIST),
    ]
    assert "sweep: s1 t: archived (idle)" in capsys.readouterr().out
    assert (hygiene.STATE / "swept").exists()


def test_the_sweep_runs_at_most_once_a_day(hygiene, tmp_path):
    answer(hygiene, json.dumps({"lines": [], "owner": [], "card": None}))
    run(hygiene, tmp_path)
    (hygiene.fake / "argv").unlink()
    assert (
        run(hygiene, tmp_path)[1] is None and not (hygiene.fake / "argv").exists()
    )  # the next round skips it
    day_ago = time.time() - 25 * 3600
    os.utime(hygiene.STATE / "swept", (day_ago, day_ago))
    run(hygiene, tmp_path)
    assert (hygiene.fake / "argv").exists()  # a day on, it sweeps again


def test_a_dry_run_passes_dry_run_and_leaves_the_day_unswept(hygiene, tmp_path):
    answer(hygiene, json.dumps({"lines": [], "owner": [], "card": None}))
    run(hygiene, tmp_path, dry=True)
    assert json.loads((hygiene.fake / "argv").read_text())[-1] == "--dry-run"
    assert not (hygiene.STATE / "swept").exists()


@pytest.mark.parametrize("stdout", ["", "Traceback: boom\n"])
def test_a_failed_sweep_fails_the_run_and_is_tried_again_next_round(
    hygiene, tmp_path, stdout, capsys
):
    answer(hygiene, stdout, code=1)
    r, card = run(hygiene, tmp_path)
    assert r.failed and card is None and "FAIL session sweep: exit 1" in capsys.readouterr().out
    assert not (hygiene.STATE / "swept").exists()


def test_a_refused_finish_is_logged_and_fails_the_run(hygiene, tmp_path, capsys):
    answer(
        hygiene,
        json.dumps({"lines": ["s1 t: finish failed: HTTP 503"], "owner": [], "card": None}),
        code=1,
    )
    r, _ = run(hygiene, tmp_path)
    out = capsys.readouterr().out
    assert (
        r.failed and "sweep: s1 t: finish failed" in out and not (hygiene.STATE / "swept").exists()
    )


def test_without_the_omnigent_agents_skill_the_sweep_is_skipped(
    hygiene, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(hygiene, "HOME_SKILLS", [tmp_path / "none"])
    r, card = run(hygiene, tmp_path)
    assert card is None and not r.failed and "session sweep skipped" in capsys.readouterr().out


def test_the_skill_documents_the_sweep_the_keep_list_and_the_card():
    text = SKILL_MD.read_text()
    for needle in (
        "## The session sweep",
        "~/.config/agent-hygiene/keep-sessions",
        "once a day",
        "CARD:",
        "omnigent.keep",
        "Archive all",
    ):
        assert needle in text, needle
