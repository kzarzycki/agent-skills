"""cloud_verifier.py env-sync: is the cloud environment's copy of the setup script the base branch's (#989)?

Driven against a fake environment API (post_json) and a real git repo whose `main` holds the setup script.
"""

from __future__ import annotations

import json
import subprocess

import pytest
from test_cloud_verifier import cv

PATH = ".claude/claude-cloud-setup.sh"
NEW = "#!/bin/bash\necho new\n"
OLD = "#!/bin/bash\necho old\n"
CONFIG = {
    "init_script": OLD,
    "environment": {"KEEP": "1"},
    "network_config": {"allowed_hosts": ["example.com"]},
    "other": {"deep": [1, 2]},
}


@pytest.fixture
def synced(tmp_path, monkeypatch):
    """A repo whose main has NEW as its setup script, and a fake environment holding `state`; calls are recorded."""
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / PATH).write_text(NEW)
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["add", "."],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"],
    ):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True)
    monkeypatch.chdir(repo)
    state = {"name": "dev", "description": "d", "config": json.loads(json.dumps(CONFIG))}
    calls: list[tuple[str, dict | None]] = []

    def post_json(url: str, body: dict | None, headers: dict) -> dict:
        calls.append((url, body))
        if body is not None:
            state.update(name=body["name"], description=body["description"], config=body["config"])
        return json.loads(json.dumps(state))

    monkeypatch.setattr(cv, "post_json", post_json)
    monkeypatch.setattr(cv, "claude_headers", dict)
    return state, calls


def test_env_sync_reports_in_sync_when_the_environment_has_the_base_branchs_script(
    synced, capsys
) -> None:
    state, calls = synced
    state["config"]["init_script"] = NEW
    assert cv.main(["env-sync", "--env", "env_1"]) == 0
    assert capsys.readouterr().out.startswith("in sync")
    assert all(body is None for _, body in calls)  # a read, nothing posted


def test_env_sync_reports_stale_with_the_apply_command_and_exits_1(synced, capsys) -> None:
    state, calls = synced
    assert cv.main(["env-sync", "--env", "env_1"]) == 1
    out = capsys.readouterr().out
    assert "environment setup is stale" in out
    assert "env-sync --env env_1" in out and "--apply" in out
    assert state["config"]["init_script"] == OLD  # without --apply nothing is posted
    assert all(body is None for _, body in calls)


def test_env_sync_apply_changes_only_init_script_and_confirms_it(synced, capsys) -> None:
    _state, calls = synced
    assert cv.main(["env-sync", "--env", "env_1", "--apply"]) == 0
    posts = [body for _, body in calls if body is not None]
    assert len(posts) == 1
    assert posts[0]["config"] == {**CONFIG, "init_script": NEW}  # every other key as it was
    assert (posts[0]["name"], posts[0]["description"]) == ("dev", "d")
    assert capsys.readouterr().out.startswith("applied")
    assert calls[-1][1] is None  # read back after the post


def test_env_sync_apply_exits_1_when_the_environment_does_not_keep_the_script(
    synced, monkeypatch, capsys
) -> None:
    _state, _ = synced
    keep = cv.post_json

    def ignoring(url, body, headers):
        return keep(url, None, headers)  # a post the server drops

    monkeypatch.setattr(cv, "post_json", ignoring)
    assert cv.main(["env-sync", "--env", "env_1", "--apply"]) == 1
    assert "did not keep" in capsys.readouterr().err
