"""`.github/workflows/queue-failure.yml` (#2497): the job that writes a PR's `Queue failure` record runs only for a
Mergify comment on a PR, with the two permissions its reads and its record need, and runs the base's copy with no PR
code (the model is land-status.yml)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "queue-failure.yml"


def load() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_it_reads_a_mergify_comment_on_a_pr_and_no_one_elses() -> None:
    workflow = load()
    job = workflow["jobs"]["record"]
    assert list(workflow["on"]) == ["issue_comment"]
    assert workflow["on"]["issue_comment"]["types"] == ["created", "edited"]
    assert "github.event.issue.pull_request" in job["if"]
    assert "github.event.comment.user.login == 'mergify[bot]'" in job["if"]


def test_it_holds_the_permissions_it_needs_and_no_write_beyond_the_record() -> None:
    permissions = load()["permissions"]
    assert permissions["actions"] == "read"
    assert permissions["pull-requests"] == "write"
    assert {k for k, v in permissions.items() if v == "write"} == {"pull-requests"}


def test_it_runs_the_default_branch_and_no_pr_code() -> None:
    text = WORKFLOW.read_text()
    [checkout] = [s for s in load()["jobs"]["record"]["steps"] if "uses" in s]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert re.search(r"@[0-9a-f]{40}$", checkout["uses"])
    assert checkout["with"]["persist-credentials"] == "false"
    assert not re.search(r"head\.(sha|ref)|pull_request\.head|refs/pull", text.replace("\n#", "\n"))


def test_its_script_is_the_one_the_supervisor_loads() -> None:
    [step] = [s for s in load()["jobs"]["record"]["steps"] if "run" in s]
    script = ROOT / step["env"]["SCRIPT"]
    assert script.is_file()
    assert script.parent == ROOT / "omnigent" / "skills" / "omnigent-agents" / "scripts"
    assert step["run"] == 'python3 "$SCRIPT"'
