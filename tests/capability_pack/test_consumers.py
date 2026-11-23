from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.capability_pack.consumers import ConsumerListError, consumer_matrix

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "capability_pack" / "consumers.py"


@pytest.mark.parametrize("raw", [None, "", "  ", "[]"])
def test_without_a_list_only_this_repo_is_bumped(raw) -> None:
    assert consumer_matrix("o/self", raw) == [{"repository": "o/self", "queue": "mergify"}]


def test_entries_default_to_auto_merge_and_this_repo_comes_once_first() -> None:
    raw = json.dumps(["a/app", {"repository": "b/web", "queue": "none"}, "O/Self", "a/app"])
    assert consumer_matrix("o/self", raw) == [
        {"repository": "o/self", "queue": "mergify"},
        {"repository": "a/app", "queue": "auto-merge"},
        {"repository": "b/web", "queue": "none"},
    ]


@pytest.mark.parametrize(
    "raw",
    [
        "a/app",  # not JSON
        '{"repository": "a/app"}',  # not a list
        '["no-slash"]',
        '["a/b/c"]',
        '[{"repository": "a/app", "queue": "later"}]',
        '[{"repository": "a/app", "token": "x"}]',  # an unknown key is refused, never ignored
        "[1]",
    ],
)
def test_a_malformed_list_is_refused_whole(raw) -> None:
    with pytest.raises(ConsumerListError):
        consumer_matrix("o/self", raw)


def test_the_script_runs_on_a_bare_interpreter_without_pyyaml(tmp_path) -> None:
    """The plan job runs it on the runner's python3 before any tool is installed (#1629's trap)."""
    env = {**os.environ, "ENGINEERING_CONSUMERS": '["a/app"]'}
    done = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "o/self"],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)[1] == {"repository": "a/app", "queue": "auto-merge"}
    env["ENGINEERING_CONSUMERS"] = '["bad"]'
    refused = subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "o/self"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert refused.returncode == 4 and "owner/repo" in refused.stderr
