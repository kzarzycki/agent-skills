import os
import sys

# The engineering loop's script tests load modules from a shipped skill folder;
# a bytecode cache written there would ship with the package.
sys.dont_write_bytecode = True

import pytest


@pytest.fixture(autouse=True)
def _outside_omnigent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests run as if outside an Omnigent session; one that needs a session sets it."""
    for var in (
        "OMNIGENT_RUNNER_PRIMARY_SESSION_ID",
        "OMNIGENT_SESSION_ID",
        "OMNIGENT_TERMINAL_LAUNCH_SESSION_ID",
        "LOOP_HEAVY_LOCK",
        "OMNIGENT_PERMISSION_MODE",
        # a cloud session's marker: land refuses there without a landing key, so tests run as a host's
        "CLAUDE_CODE_REMOTE",
        # the host's defaults for a child's model and effort
        *(v for v in os.environ if v.startswith(("OMNIGENT_MODEL_", "OMNIGENT_EFFORT_"))),
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _own_gate_slot(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """approvals.py's gate steps take the host gate slot: its tests take one of their own, since the host's may be
    held by a gate running above this suite (#940)."""
    if request.module.__name__.startswith("test_approvals"):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
        monkeypatch.delenv("LOOP_GATE_SLOT_HELD", raising=False)


@pytest.fixture(autouse=True)
def _no_user_git_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Git reads no global or system config, so a host's signing program or identity can't change a test's outcome."""
    empty = tmp_path_factory.mktemp("git-config") / "gitconfig"
    empty.touch()
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture(autouse=True)
def _brief_head_merges(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """approvals.py's brief checks the PR's head merges into its base with git: its other tests have no such repo, so
    the check reads clean there. test_approvals_brief_conflict.py runs the real one."""
    module = request.module
    if module.__name__ != "test_approvals_brief_conflict" and hasattr(module, "approvals"):
        monkeypatch.setattr(module.approvals, "conflicted", lambda _pr, _base, _head: [])
