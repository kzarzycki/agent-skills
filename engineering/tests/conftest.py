import os
import shutil
import sys
from collections.abc import Callable, Iterable, Iterator
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
    repo_template,
    required,
)


@pytest.fixture(autouse=True)
def _no_wait_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that mocks the rerun's execv leaves the wait's place in the environment; the next land would resume it."""
    monkeypatch.delenv("LOOP_LAND_WAIT", raising=False)


# os.environ as each phase of a test found it: before setup, before the call, after the call
_ENVIRON = pytest.StashKey[dict[str, dict[str, str]]]()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Iterator[None]:
    item.stash[_ENVIRON] = {"setup": dict(os.environ)}
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    seen = item.stash[_ENVIRON]
    seen["call"] = dict(os.environ)
    try:
        return (yield)
    finally:
        seen["called"] = dict(os.environ)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item) -> Iterator[None]:
    """A test that runs a script's cli() in this process lets it edit os.environ directly, which monkeypatch never
    undoes: approvals' leave_own_environment drops the venv from PATH, so a later subprocess's python3 loses its
    packages (a fake vendir's `import yaml`). After every fixture's teardown, a variable the call changed is put back
    to its value before the call when it is still as the call left it and not as it was before setup. That leaves
    alone:
    - a monkeypatch the call made, since its undo has already put the value back
    - an early `monkeypatch.undo()`, since it leaves the value as it was before setup
    - a session fixture's variable, which the call found set
    - pytest's PYTEST_CURRENT_TEST, which the call never changes
    A monkeypatch recorded after a direct edit brings the call's value back at its undo, which this then undoes.
    ponytail: a direct edit made in a fixture's setup is not undone; none leaks today."""
    try:
        return (yield)
    finally:
        seen = item.stash.get(_ENVIRON, {})
        if "called" in seen:
            setup, before, after = seen["setup"], seen["call"], seen["called"]
            for key in before.keys() | after.keys():
                now = os.environ.get(key)
                changed = before.get(key) != after.get(key)
                if changed and now == after.get(key) and now != setup.get(key):
                    if key in before:
                        os.environ[key] = before[key]
                    else:
                        del os.environ[key]


# The fixtures that run a tool beyond git and Python: pytest ignores a mark on a fixture, so each test that takes
# one gets its `needs_tool` mark at collection, as a test that runs the tool itself carries it.
FIXTURE_TOOLS = {"cloud_land": ("ssh-keygen",), "signing": ("ssh-keygen",)}


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Before `-m` deselects, so `-m "not needs_tool"` leaves out a test that needs a tool through a fixture."""
    for item in items:
        for name in getattr(item, "fixturenames", ()):
            if name in FIXTURE_TOOLS:
                item.add_marker(pytest.mark.needs_tool(*FIXTURE_TOOLS[name]))


def missing_tools(items: Iterable[pytest.Item]) -> list[str]:
    """The tools the `needs_tool` marks of `items` name that are not on PATH."""
    needed = {
        tool for item in items for mark in item.iter_markers("needs_tool") for tool in mark.args
    }
    return sorted(tool for tool in needed if shutil.which(tool) is None)


def pytest_collection_finish(session: pytest.Session) -> None:
    """A tool a selected test runs (its `needs_tool` mark) and PATH lacks stops the run before its first test, one
    line naming every such tool, rather than failing each test that runs it partway through; a test with no such
    mark runs, whatever its module's other tests need (#1022)."""
    missing = missing_tools(session.items)
    if missing:
        pytest.exit(
            f"missing tools the tests run: {', '.join(missing)}; put them on PATH",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )


@pytest.fixture(autouse=True)
def _fresh_viewer() -> None:
    """The login `gh` runs as is read once per process (github_adapter.viewer); a test stubs it per test."""
    from approvals_harness import approvals

    approvals.github.viewer_login.clear()


@pytest.fixture(autouse=True)
def _no_cold_start_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """`omnigent_agent start` polls up to 20 s for a first turn to time; a fake Omnigent never takes one, so each
    start a test lets succeed cost 20 s (#1420). A test of the wait passes its own `wait`."""
    module = sys.modules.get(
        "omnigent_agent"
    )  # loaded by test_omnigent_agent, which the other modules import from
    if module:
        monkeypatch.setattr(module, "COLD_START_SECONDS", 0)


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
        monkeypatch.setenv("GATE_SLOTS", "1")  # one slot, so a held slot 1 is a full host (#1138)


@pytest.fixture(autouse=True)
def _no_heavy_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Heavy steps run unwrapped, as under a wrapped run, so a host's own heavy wrapper file never wraps a test's
    step; test_approvals_heavy_wrapper.py clears it and fakes the host's config home."""
    monkeypatch.setenv("LOOP_HEAVY_WRAPPED", "1")


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


@pytest.fixture(autouse=True)
def _status_follows_the_pull(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """approvals.py reads a PR's state, base and head alone through pull_status (one REST call); most tests fake the
    whole PR with pull_request, so there it answers from that fake. A test of pull_status sets its own."""
    module = request.module
    if module.__name__.startswith("test_approvals") and hasattr(module, "approvals"):
        approvals = module.approvals
        monkeypatch.setattr(approvals, "pull_status", lambda n: approvals.pull_request(n))


@pytest.fixture(autouse=True)
def _brief_head_merges(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """approvals.py's brief checks the PR's head merges into its base with git, and lists the open PRs that change the
    same files: its other tests have no such repo, so the check reads clean there and no open PR is listed, which keeps
    them off the live `gh`. test_approvals_brief_conflict.py runs the real merge check, test_approvals_overlap.py its
    own list."""
    module = request.module
    if module.__name__ != "test_approvals_brief_conflict" and hasattr(module, "approvals"):
        monkeypatch.setattr(module.approvals, "conflicted", lambda _pr, _base, _head: [])
    if module.__name__ != "test_approvals_overlap" and hasattr(module, "approvals"):
        monkeypatch.setattr(module.approvals, "open_pull_files", lambda _limit: [])


@pytest.fixture(autouse=True)
def _host_has_room(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """A start reads this host's CPU and memory and waits up to 600 s while either is short, so a test's start on a
    host busy with the gate running it waits and fails. Every module that loads omnigent_agent gets a host with room,
    whether or not it imports test_omnigent_agent's fixtures; a test of the real check calls `monkeypatch.undo()`."""
    # the module is the one test_omnigent_agent registered, found by identity and not by the name a test binds it to
    # (`oa`, `omnigent_agent`), so a later alias is covered too
    agent = sys.modules.get("omnigent_agent")
    if agent is not None and any(v is agent for v in vars(request.module).values()):
        monkeypatch.setattr(agent, "capacity", lambda **_: (True, ""))


@pytest.fixture
def role_file(tmp_path: Path) -> Callable[[str], str]:
    """Write a role file under tmp_path and return its path: `--role` must name a readable file (#1313)."""

    def make(name: str) -> str:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("role")
        return str(path)

    return make
