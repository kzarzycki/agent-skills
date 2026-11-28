"""The engineering pack's PreToolUse hook refuses a push to a held PR's branch and a PR created for a held issue,
and allows both once the `loop:hold` label is off (#2998). A fake `gh` on PATH answers from a JSON state file."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "engineering-hooks" / "hooks" / "hold_guard.py"
FAKE_GH = """#!/usr/bin/env python3
import json, os, re, sys
state = json.load(open(os.environ["FAKE_GH_STATE"]))
path = next((a for a in sys.argv[1:] if a.startswith("repos/")), "")
if re.search(r"/pulls$", path):
    print(json.dumps(state["pulls"]))
elif path.endswith("/events"):
    print(json.dumps(state["events"]))
else:
    n = path.rsplit("/", 1)[-1]
    print(json.dumps({"labels": [{"name": x} for x in state["labels"].get(n, [])]}))
"""


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs" / "agents").mkdir(parents=True)
    (repo / "docs" / "agents" / "loop.md").write_text("Cloud worker: claude\n")
    subprocess.run(["git", "init", "-q", "-b", "claude/work", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:acme/widgets.git"],
        check=True,
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    state = tmp_path / "state.json"

    def set_state(labels, pulls=None):
        state.write_text(
            json.dumps(
                {
                    "labels": labels,
                    "pulls": pulls if pulls is not None else [{"number": 7, "body": "Closes #5"}],
                    "events": [
                        {
                            "event": "labeled",
                            "label": {"name": "loop:hold"},
                            "actor": {"login": "boss"},
                        }
                    ],
                }
            )
        )

    def call(command):
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_GH_STATE": str(state)}
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)}
        done = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        return done.returncode, done.stderr

    return set_state, call


def test_a_push_to_a_held_prs_branch_is_refused_naming_the_hold_and_who_set_it(world):
    set_state, call = world
    set_state({"7": ["loop:hold"]})
    code, err = call("git push -u origin claude/work")
    assert code == 2
    assert "loop:hold" in err and "@boss" in err and "#7" in err


def test_a_push_is_refused_when_the_issue_the_pr_closes_is_held(world):
    set_state, call = world
    set_state({"5": ["loop:hold"]})
    assert call("git push origin claude/work")[0] == 2


def test_opening_a_pr_for_a_held_issue_is_refused_on_every_creation_path(world):
    set_state, call = world
    set_state({"5": ["loop:hold"]}, pulls=[])
    for command in (
        "gh pr create --draft --title t --body 'Closes #5'",
        (
            "curl -sS -X POST -H 'Content-Type: application/json' https://api.github.com/repos/acme/widgets/pulls"
            ' -d \'{"title":"t","head":"claude/work","base":"main","body":"Closes #5"}\''
        ),
    ):
        code, err = call(command)
        assert code == 2, command
        assert "loop:hold" in err and "#5" in err


def test_once_the_hold_is_cleared_the_push_and_the_pr_go_through(world):
    set_state, call = world
    set_state({"7": ["loop:hold"], "5": ["loop:hold"]})
    assert call("git push origin claude/work")[0] == 2
    set_state({"7": [], "5": []})
    assert call("git push origin claude/work")[0] == 0
    assert call("gh pr create --draft --body 'Closes #5'")[0] == 0


def test_an_unrelated_command_and_an_unreadable_label_are_allowed(world):
    set_state, call = world
    set_state({"7": ["loop:hold"]})
    assert call("git status")[0] == 0
    assert call("git push --delete origin claude/work")[0] == 0
