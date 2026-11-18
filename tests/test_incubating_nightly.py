"""The incubating nightly workflow: it reports, never blocks, runs only for an open epic, and runs only `mise run <task>` (#1288)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

FILE = Path(__file__).resolve().parents[1] / ".github/workflows/incubating-nightly.yml"


@pytest.fixture(scope="module")
def flow() -> dict[str, Any]:
    return yaml.safe_load(FILE.read_text())


def test_it_runs_on_a_schedule_and_by_hand_and_never_on_a_pull_request(flow: dict[str, Any]) -> None:
    triggers = flow[True]  # YAML 1.1 reads the key `on` as true
    assert set(triggers) == {"schedule", "workflow_dispatch"}


def test_it_may_only_comment_and_read(flow: dict[str, Any]) -> None:
    assert flow["permissions"] == {"contents": "read", "issues": "write"}


def test_every_step_after_the_listing_waits_for_an_epic(flow: dict[str, Any]) -> None:
    steps = flow["jobs"]["nightly"]["steps"]
    assert steps[0]["id"] == "epics"
    assert all("steps.epics.outputs.numbers != ''" in step["if"] for step in steps[1:])


def test_a_stale_reminder_is_counted_by_the_bot_only() -> None:
    text = FILE.read_text()
    assert 'github-actions[bot]' in text and 'startswith("Still incubating")' in text
    assert "| min //" in text  # the first label event: a label put back doesn't restart the clock


def test_the_body_parser_takes_only_a_flag_name_and_a_mise_task() -> None:
    """The shell loop of the workflow, run on bodies: an injected command is not a `Nightly:` line."""
    text = FILE.read_text()
    start = text.index("            flag=\"\" cmd=\"\"")
    end = text.index("            done <<< \"$body\"") + len("            done <<< \"$body\"")
    parser = "\n".join(line[12:] for line in text[start:end].splitlines())
    script = f"tick=$(printf '\\x60')\n{parser}\necho \"[$flag][$cmd]\"\n"

    def run(body: str) -> str:
        return subprocess.run(
            ["bash", "-c", script], input="", env={"body": body, "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    ok = run("Flag: `FEAT_X`\nNightly: `mise run nightly:feat`")
    assert ok == "[FEAT_X][mise run nightly:feat]"
    assert run("Nightly: mise run a:b; rm -rf /\nFlag: X1") == "[X1][]"
    assert run("Flag: none") == "[none][]"
