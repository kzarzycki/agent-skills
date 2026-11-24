import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

# The engineering loop's script tests load modules from a shipped skill folder;
# a bytecode cache written there would ship with the package. The variable carries
# the same to the scripts the tests run as subprocesses (#1022).
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import pytest

from tools.gh_trap import install_trap, without_trap

# the gatekeeper's test harness, whose fixtures every package's tests run under, and the Omnigent driver's tests
for package in (
    "gatekeeper",
    "omnigent",
    "loop",
):  # a test imports the fixtures of another package's tests by module name
    sys.path.insert(0, str(Path(__file__).resolve().parent / package / "tests"))

# The approvals.py fixtures, visible to every module here; _approvals_stubs turns them on.
from approvals_harness import (  # noqa: F401
    AUTOUSE,
    added,
    assigned,
    attached,
    board_risks,
    graphql_answers,
    hub,
    merging,
    others_open,
    pushed,
    refs,
    repo_template,
    required,
)

# No test reaches GitHub through the real `gh` (tools/gh_trap.py, #2035); the trap folder this process made is removed
# when its run ends, and an xdist worker reuses its controller's (inherited through GH_NO_GITHUB_TRAP)
_made_trap: list[Path] = []


def pytest_configure(config: pytest.Config) -> None:
    if made := install_trap(os.environ):
        _made_trap.append(made)


def pytest_unconfigure(config: pytest.Config) -> None:
    for made in _made_trap:
        shutil.rmtree(made, ignore_errors=True)


@pytest.fixture(autouse=True)
def _real_gh_for_live_agents(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `live_agent` test drives a real harness against the real forge: it gets PATH without the trap."""
    trap = os.environ.get("GH_NO_GITHUB_TRAP")
    if trap and request.node.get_closest_marker("live_agent"):
        monkeypatch.setenv("PATH", without_trap(os.environ["PATH"], trap))


@pytest.fixture
def no_origin(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """The checkout under test has no origin, as a fresh `git init` has: a `git fetch` or `git ls-remote` of origin, run
    with `subprocess.run` or started with `subprocess.Popen` (tree_of's), ends at once as git ends there (128; a Popen
    is a `false`), instead of spending 0.4 s on the real checkout's own remote. A test that takes it is not about a
    remote; one that is brings a bare repo of its own. The value is the argv of each refused call."""
    asked: list[list[str]] = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def refused(argv: Any) -> list[str] | None:
        words = [str(word) for word in argv] if isinstance(argv, list) else []
        if words[:1] == ["git"] and "origin" in words and {"fetch", "ls-remote"} & set(words):
            asked.append(words)
            return words
        return None

    def run(argv: Any, *args: Any, **kw: Any) -> Any:
        if words := refused(argv):
            error = "fatal: 'origin' does not appear to be a git repository"
            if kw.get("check"):
                raise subprocess.CalledProcessError(128, words, "", error)
            return subprocess.CompletedProcess(words, 128, "", error)
        return real_run(argv, *args, **kw)

    class Popen(real_popen):  # type: ignore[type-arg,misc]
        def __init__(self, argv: Any, *args: Any, **kw: Any) -> None:
            super().__init__(["false"] if refused(argv) else argv, *args, **kw)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", Popen)
    return asked


@pytest.fixture(autouse=True)
def _no_wait_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test that mocks the rerun's execv leaves the wait's place in the environment; the next land would resume it."""
    monkeypatch.delenv("LOOP_LAND_WAIT", raising=False)


_Environ = type(os.environ)
_SET, _DEL = _Environ.__setitem__, _Environ.__delitem__


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    """A test that runs a script's cli() in this process lets it edit os.environ directly, which monkeypatch never
    undoes: approvals' leave_own_environment drops the venv from PATH, so a later subprocess's python3 loses its
    packages (a fake vendir's `import yaml`). During the call, each such edit is made through the test's own
    monkeypatch instead, so its teardown undoes it in order with the test's patches, before any wider fixture's
    teardown. pytest's PYTEST_CURRENT_TEST is left to pytest, which sets it for every phase.
    ponytail: a direct edit made in a fixture's setup is not undone; none leaks today."""
    monkeypatch = getattr(item, "funcargs", {}).get("monkeypatch")
    if monkeypatch is None:  # every test here takes it through the autouse fixtures above
        return (yield)
    # per thread, so another thread's edit is never taken for monkeypatch's own write
    inside = threading.local()

    def through(edit: Callable[[], None], direct: Callable[[], None]) -> None:
        if getattr(inside, "now", False):  # monkeypatch's own write
            return direct()
        inside.now = True
        try:
            edit()
        finally:
            inside.now = False

    def setitem(environ: os._Environ[str], key: str, value: str) -> None:
        # os.environb shares the class, so its bytes key goes straight through before the name check reads it as str.
        # A name the OS refuses raises in the direct write, before monkeypatch records an undo whose deletion would
        # raise too; a refused value leaves an undo that teardown makes, so the one native write is the assignment's
        if (
            environ is not os.environ
            or key == "PYTEST_CURRENT_TEST"
            or not isinstance(value, str)
            or not key
            or "=" in key
            or "\0" in key
        ):
            return _SET(environ, key, value)
        through(lambda: monkeypatch.setenv(key, value), lambda: _SET(environ, key, value))

    def delitem(environ: os._Environ[str], key: str) -> None:
        if environ is not os.environ or key == "PYTEST_CURRENT_TEST" or key not in environ:
            return _DEL(environ, key)
        through(lambda: monkeypatch.delenv(key), lambda: _DEL(environ, key))

    _Environ.__setitem__, _Environ.__delitem__ = setitem, delitem  # type: ignore[method-assign]
    try:
        return (yield)
    finally:
        _Environ.__setitem__, _Environ.__delitem__ = _SET, _DEL  # type: ignore[method-assign]


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
    if not missing:
        return
    line = f"missing tools the tests run: {', '.join(missing)}; put them on PATH"
    if hasattr(session.config, "workerinput"):
        # An xdist worker that exits here leaves the tests the controller assigned it, which fails the run with an
        # INTERNALERROR naming whichever test came first; a stop the worker reports ends the run with this line.
        session.config.stash[_STOP] = line
        session.shouldstop = line
        return
    pytest.exit(line, returncode=pytest.ExitCode.USAGE_ERROR)


_STOP = pytest.StashKey[str]()


@pytest.hookimpl(tryfirst=True)
def pytest_runtestloop(session: pytest.Session) -> bool | None:
    """A worker stopped by `pytest_collection_finish` runs none of its tests."""
    return True if _STOP in session.config.stash else None


def pytest_testnodedown(node: object, error: object) -> None:
    """On the xdist controller: a worker's missing-tools stop ends the whole run as the serial run does."""
    stop = getattr(node, "workeroutput", {}).get("shouldstop")
    if isinstance(stop, str) and stop.startswith("missing tools the tests run: "):
        pytest.exit(stop, returncode=pytest.ExitCode.USAGE_ERROR)


@pytest.fixture(autouse=True)
def _fresh_viewer() -> None:
    """The login `gh` runs as is read once per process (github_adapter.viewer), and writer, required_checks and a
    settled head's check runs are kept for a while (#1771); a test stubs them per test, so each starts with none."""
    from approvals_harness import approvals

    approvals.github.forget()


@pytest.fixture(autouse=True)
def _fresh_commit_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """omnigent_agent keeps `git/commits/<sha>` answers for the process (a commit never changes); tests reuse shas
    with different dates, so each test starts with none (#1537)."""
    module = sys.modules.get("omnigent_agent")
    if module:
        monkeypatch.setattr(module, "COMMITS", {})


@pytest.fixture(autouse=True)
def _no_cold_start_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """`omnigent_agent start` polls up to 20 s for a first turn to time; a fake Omnigent never takes one, so each
    start a test lets succeed cost 20 s (#1420). A test of the wait passes its own `wait`."""
    module = sys.modules.get(
        "omnigent_agent"
    )  # loaded by test_omnigent_agent, which the other modules import from
    if module:
        monkeypatch.setattr(module, "COLD_START_SECONDS", 0)


# The modules that read loop events from a real bare remote on purpose; every other omnigent_agent test gets none.
READS_LOOP_EVENTS = {"test_omnigent_agent_events", "test_lead_event"}


@pytest.fixture(autouse=True)
def _no_loop_events_read(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """The supervisor's loop-event read is an `ls-remote origin` of the real checkout, one per poll: 0.5 s on a quiet
    host, a minute and a timeout where the proxy is slow (#1610). A module that imports its fixtures by name from
    test_omnigent_agent (as the traffic one does) misses that module's `no_loop_events`, so this applies it to all."""
    module = sys.modules.get("omnigent_agent")
    if module and request.module.__name__ not in READS_LOOP_EVENTS:
        monkeypatch.setattr(module, "read_loop_events", lambda cwd=None: None)


# The one module that runs land's `own-pr` start for real, against a fake script.
STARTS_OWN_PR = {"test_approvals_own_prs"}


@pytest.fixture(autouse=True)
def _no_own_pr_start(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """land starts omnigent_agent.py `own-pr` for each PR it names (#2161): a test of land starts none."""
    if request.module.__name__ in STARTS_OWN_PR:
        return
    from approvals_harness import approvals

    monkeypatch.setattr(approvals, "own_prs", lambda pulls: None)


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
def _land_heads_recorded(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """The local queue's land refuses a head with no pass record on origin (head_recorded, R6): its other tests have no
    origin holding one, so every head reads recorded there. test_approvals_land_record.py runs the real read."""
    module = request.module
    if module.__name__ != "test_approvals_land_record" and hasattr(module, "approvals"):
        monkeypatch.setattr(module.approvals, "head_recorded", lambda _pull: True)


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
