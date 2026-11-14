import os
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

# The engineering loop's script tests load modules from a shipped skill folder;
# a bytecode cache written there would ship with the package. The variable carries
# the same to the scripts the tests run as subprocesses (#1022).
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import pytest

# The approvals.py fixtures, visible to every module here; _approvals_stubs turns them on.
from approvals_harness import (  # noqa: F401
    AUTOUSE,
    added,
    assigned,
    attached,
    board_risks,
    graphql_answers,
    hub,
    others_open,
    pushed,
    refs,
    required,
)

HERE = Path(__file__).parent

# The tools beyond git and Python each module's tests run, by its path from here (#1022).
TOOLS = {
    "e2e/test_static_discovery.py": ("apm",),
    "test_approvals.py": ("ssh-keygen",),
    "test_consumer_e2e.py": ("apm",),
    "test_omnigent_agent.py": ("perl",),
}


def missing_tools(paths: Iterable[Path]) -> list[str]:
    """The tools the modules at `paths` run that are not on PATH."""
    needed = {
        tool
        for path in paths
        if path.is_relative_to(HERE)
        for tool in TOOLS.get(path.relative_to(HERE).as_posix(), ())
    }
    return sorted(tool for tool in needed if shutil.which(tool) is None)


def pytest_collection_finish(session: pytest.Session) -> None:
    """A tool the selected tests run and PATH lacks stops the run before its first test, one line naming every
    such tool, rather than failing each test that runs it partway through."""
    missing = missing_tools({item.path for item in session.items})
    if missing:
        pytest.exit(
            f"missing tools the tests run: {', '.join(missing)}; put them on PATH",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )


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
def _approvals_stubs(request: pytest.FixtureRequest) -> None:
    """Every test of approvals.py runs under the harness's AUTOUSE fixtures, though its module imports none, so a
    module that main gains while a PR adds a fixture still gets it (#1015)."""
    if request.module.__name__.startswith("test_approvals"):
        for name in AUTOUSE:
            request.getfixturevalue(name)
