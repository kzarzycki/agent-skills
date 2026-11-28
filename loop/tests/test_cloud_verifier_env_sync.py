"""cloud_verifier.py env-sync: is the cloud environment's copy of the setup script the base branch's (#989)?

Driven against a fake environment API (post_json) and a real git repo whose `main` holds the setup script.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

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


def commit(repo: Path, *files: str, branch: str | None = None) -> None:
    if branch:
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", branch], check=True)
    subprocess.run(["git", "-C", str(repo), "add", *files], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            "y",
        ],
        check=True,
    )


def test_a_script_the_base_lacks_is_never_read_from_the_working_tree(synced) -> None:
    """F2: the base holds only the legacy script; an untracked modern one in the checkout is not published."""
    _, calls = synced
    repo = Path.cwd()
    (repo / ".claude" / "cloud-setup.sh").write_text("#!/bin/bash\necho legacy\n")
    subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached", PATH], check=True)
    commit(repo, ".claude/cloud-setup.sh")
    (repo / PATH).write_text("#!/bin/bash\necho untracked\n")
    assert cv.main(["env-sync", "--env", "env_1", "--apply"]) == 0
    posted = next(body for _, body in calls if body is not None)
    assert posted["config"]["init_script"] == "#!/bin/bash\necho legacy\n"
    assert cv.main(["env-sync", "--env", "env_1", "--script", "ci/absent.sh", "--apply"]) == 2


def test_the_declared_setup_script_and_the_pinned_environment_are_resolved_without_arguments(
    synced, capsys
) -> None:
    """F3: loop.md's `Cloud setup script:` line picks the script, the checkout's pin picks the environment."""
    state, calls = synced
    repo = Path.cwd()
    (repo / "docs" / "agents").mkdir(parents=True)
    (repo / "docs" / "agents" / "loop.md").write_text("Cloud setup script: ci/setup.sh\n")
    (repo / "ci").mkdir()
    (repo / "ci" / "setup.sh").write_text("#!/bin/bash\necho declared\n")
    commit(repo, "docs", "ci")
    (repo / ".claude" / "settings.local.json").write_text(
        json.dumps({"remote": {"defaultEnvironmentId": "env_pin"}})
    )
    state["config"]["init_script"] = NEW  # matches the default script, not the declared one
    assert cv.main(["env-sync"]) == 1
    assert calls[0][0].endswith("/env_pin")
    assert "ci/setup.sh" in capsys.readouterr().out


def test_the_printed_apply_command_runs_the_script_by_its_real_path_with_arguments_intact(
    synced, capsys
) -> None:
    """F5: split as a shell would, the command names this script's absolute path and a path with a space as one argument."""
    repo = Path.cwd()
    (repo / "ci dir").mkdir()
    (repo / "ci dir" / "s.sh").write_text("#!/bin/bash\necho spaced\n")
    commit(repo, "ci dir")
    assert cv.main(["env-sync", "--env", "env_1", "--script", "ci dir/s.sh"]) == 1
    command = capsys.readouterr().out.split("apply it with: ", 1)[1].strip()
    argv = shlex.split(command)
    assert argv[0] == "python3" and Path(argv[1]).is_absolute() and Path(argv[1]).is_file()
    assert argv[argv.index("--script") + 1] == "ci dir/s.sh" and argv[-1] == "--apply"


def test_a_trailing_space_is_a_difference_but_a_trailing_newline_is_not(synced) -> None:
    """F7: only the final newline is normalised, so a change that alters a command's meaning is seen."""
    state, _ = synced
    state["config"]["init_script"] = NEW.rstrip("\n")
    assert cv.main(["env-sync", "--env", "env_1"]) == 0
    state["config"]["init_script"] = NEW.rstrip("\n") + " \n"
    assert cv.main(["env-sync", "--env", "env_1"]) == 1


def test_the_script_is_read_from_the_base_named_by_base(synced) -> None:
    """F1: --base picks the ref (a landing's freshly fetched one), not whatever local main holds."""
    state, _ = synced
    repo = Path.cwd()
    (repo / PATH).write_text("#!/bin/bash\necho later\n")
    commit(repo, PATH, branch="later")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    state["config"]["init_script"] = "#!/bin/bash\necho later\n"
    assert cv.main(["env-sync", "--env", "env_1"]) == 1  # main still has NEW
    assert cv.main(["env-sync", "--env", "env_1", "--base", "later"]) == 0
    assert cv.main(["env-sync", "--env", "env_1", "--base", "nope"]) == 2
