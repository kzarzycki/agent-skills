"""scripts/mutate.py: each patch alone against the tests, a log stamped with the head, and the tree as it started
after every run, a killed one included."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

MUTATE = (
    Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts" / "mutate.py"
)
MODULE = "def add(a, b):\n    return a + b\n\n\ndef double(x):\n    return x * 2\n"
TEST = "from calc import add\n\nassert add(2, 3) == 5\n"
TESTS = f"{sys.executable} test_calc.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with one module, its test, which covers add() but not double(), and a docs/ folder."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text(MODULE)
    (repo / "test_calc.py").write_text(TEST)
    (repo / ".gitignore").write_text("tmp/\n__pycache__/\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "README.md").write_text("calc\n")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "calc")
    (repo / "tmp" / "loop").mkdir(parents=True)
    return repo


def patch(repo: Path, name: str, old: str, new: str) -> Path:
    """A patch that changes `old` to `new` in calc.py, saved in the ignored tmp/loop/."""
    (repo / "calc.py").write_text(MODULE.replace(old, new))
    path = repo / "tmp" / "loop" / name
    path.write_text(git(repo, "diff", "--", "calc.py"))
    git(repo, "checkout", "--", "calc.py")
    return path


@pytest.fixture(autouse=True)
def own_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs with a gate slot of its own: a run that took the host's would wait on a gate running above this
    suite, or, started under a held slot, on its parent for good (#818)."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("LOOP_GATE_SLOT_HELD", raising=False)


def mutate(
    repo: Path,
    *patches: Path,
    test: str = TESTS,
    cwd: Path | None = None,
    to: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """Run mutate.py in its own session; past `timeout` its whole process group is stopped, so a hung run leaves
    nothing behind, and subprocess.TimeoutExpired is raised."""
    run = subprocess.Popen(
        [
            sys.executable,
            str(MUTATE),
            "--test",
            test,
            "--log",
            str(to or log_path(repo)),
            *map(str, patches),
        ],
        cwd=cwd or repo,
        # a mutate.py run over these tests passes its switch down, which would hide this one lacking it
        env={k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"} | (env or {}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = run.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # TERM first: mutate.py stops its test command's own group and restores the tree on it
        os.killpg(run.pid, signal.SIGTERM)
        try:
            run.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        with contextlib.suppress(ProcessLookupError):
            os.killpg(run.pid, signal.SIGKILL)
        run.communicate()
        raise
    return subprocess.CompletedProcess(run.args, run.returncode, out, err)


def stopped(repo: Path, tmp_path: Path, *signals: signal.Signals, first: str = "") -> int:
    """Send `signals` to a run while its patch is applied and its test command sleeps, after running `first`; its
    exit code."""
    killed = patch(repo, "add.patch", "a + b", "a - b")
    started = tmp_path / "started"
    command = [sys.executable, str(MUTATE), "--test", f"{first}touch {started} && sleep 60"]
    run = subprocess.Popen([*command, "--log", str(log_path(repo)), str(killed)], cwd=repo)
    deadline = time.monotonic() + 30
    while not started.exists():
        assert time.monotonic() < deadline and run.poll() is None
        time.sleep(0.05)
    assert "a - b" in (repo / "calc.py").read_text()
    for sent in signals:
        run.send_signal(sent)
    return run.wait(timeout=30)


def log_path(repo: Path) -> Path:
    return repo / "tmp" / "loop" / "m.log"


def log(repo: Path) -> list[str]:
    return log_path(repo).read_text().splitlines()


def clean(repo: Path) -> bool:
    return git(repo, "status", "--porcelain", "--untracked-files=all") == ""


def test_a_patch_the_tests_catch_is_killed_and_the_run_exits_0(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, killed)
    assert result.returncode == 0, result.stderr
    lines = log(repo)
    assert lines[0] == git(repo, "rev-parse", "HEAD").strip()
    assert "mutate.py --test" in lines[1]
    assert lines[2] == f"{killed}: exit 1 killed"
    assert f"== {killed} ==" in lines and "AssertionError" in "\n".join(lines)
    assert clean(repo) and (repo / "calc.py").read_text() == MODULE


def test_a_patch_no_test_catches_survives_and_the_log_names_it(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    survivor = patch(repo, "double.patch", "x * 2", "x * 3")
    result = mutate(repo, killed, survivor)
    assert result.returncode == 1, result.stderr
    assert log(repo)[2:4] == [f"{killed}: exit 1 killed", f"{survivor}: exit 0 survived"]
    assert clean(repo)


def test_a_tree_with_a_change_is_refused_before_any_test_runs(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    (repo / "notes.txt").write_text("not ignored\n")
    result = mutate(repo, killed)
    assert result.returncode == 2
    assert "the tree has changes" in result.stderr and "notes.txt" in result.stderr
    assert not any(line.startswith(str(killed)) for line in log(repo))
    (repo / "notes.txt").unlink()
    assert clean(repo)


def test_a_patch_that_does_not_apply_is_refused_before_any_test_runs(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    stale = repo / "tmp" / "loop" / "stale.patch"
    stale.write_text(killed.read_text().replace("a + b", "a * b"))
    result = mutate(repo, killed, stale)
    assert result.returncode == 2
    assert f"{stale} does not apply" in result.stderr
    assert log(repo)[-1].startswith(f"refused: {stale} does not apply")
    assert not any(line.startswith(str(killed)) for line in log(repo))
    assert clean(repo)


def test_sigterm_while_a_patch_is_applied_leaves_the_tree_as_it_started(
    repo: Path, tmp_path: Path
) -> None:
    before = (git(repo, "status", "--porcelain"), git(repo, "diff"))
    assert stopped(repo, tmp_path, signal.SIGTERM) == -signal.SIGTERM
    assert (git(repo, "status", "--porcelain"), git(repo, "diff")) == before
    assert clean(repo) and log(repo)[-1] == "stopped by SIGTERM"


def test_a_second_signal_during_the_restore_does_not_interrupt_it(
    repo: Path, tmp_path: Path
) -> None:
    code = stopped(repo, tmp_path, signal.SIGINT, signal.SIGTERM)
    assert code in (-signal.SIGINT, -signal.SIGTERM)
    assert clean(repo) and log(repo)[-1].startswith("stopped by SIG")


def test_a_run_from_a_subdirectory_patches_files_outside_it(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    test = f"{sys.executable} {repo / 'test_calc.py'}"
    result = mutate(repo, killed, test=test, cwd=repo / "docs")
    assert result.returncode == 0, result.stderr
    assert log(repo)[2] == f"{killed}: exit 1 killed"
    assert clean(repo)


def test_the_test_command_writes_no_bytecode_that_could_hide_the_next_patch(repo: Path) -> None:
    survivor = patch(repo, "double.patch", "x * 2", "x * 3")
    assert mutate(repo, survivor).returncode == 1
    assert not (repo / "__pycache__").exists()


def test_a_test_command_that_leaves_a_file_fails_the_restore_and_names_it(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, killed, test=f"touch stray.txt; {TESTS}")
    assert result.returncode == 2
    assert "could not be restored" in result.stderr and "stray.txt" in result.stderr
    assert (repo / "calc.py").read_text() == MODULE
    # the test had finished: its result and output stay in the log beside the refusal
    lines = log(repo)
    assert lines[2:4] == [
        f"{killed}: exit 1 killed",
        f"refused: the tree could not be restored after {killed}:",
    ]
    assert f"== {killed} ==" in lines
    (repo / "stray.txt").unlink()
    assert clean(repo)


def test_a_change_an_index_flag_hides_is_refused(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    git(repo, "update-index", "--assume-unchanged", "calc.py")
    (repo / "calc.py").write_text(MODULE + "# edited\n")
    result = mutate(repo, killed)
    assert result.returncode == 2
    assert "calc.py (index flag hides its changes)" in result.stderr
    assert log(repo)[-1].startswith("refused: the tree has changes")


def test_outside_a_git_checkout_it_refuses(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "x.patch").write_text("")
    result = subprocess.run(
        [sys.executable, str(MUTATE), "--test", "true", "--log", "m.log", "x.patch"],
        cwd=plain,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "not in a git checkout" in result.stderr


def test_a_signal_whose_restore_fails_is_refused_with_exit_2(repo: Path, tmp_path: Path) -> None:
    code = stopped(repo, tmp_path, signal.SIGTERM, first="echo edited >> docs/README.md; ")
    assert code == 2
    assert (repo / "calc.py").read_text() == MODULE
    assert log(repo)[-1].startswith("refused: the tree could not be restored")


def test_test_output_that_is_not_utf8_is_logged_and_the_tree_restored(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, killed, test=f"printf '\\377'; {TESTS}")
    assert result.returncode == 0, result.stderr
    assert clean(repo) and f"{killed}: exit 1 killed" in log(repo)


@pytest.mark.parametrize("target", ["tracked", "patch"])
def test_a_log_path_that_is_tracked_or_a_patch_is_refused_and_left_as_it_was(
    repo: Path, target: str
) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    path = repo / "docs" / "README.md" if target == "tracked" else killed
    before = path.read_text()
    result = mutate(repo, killed, to=path)
    assert result.returncode == 2 and "the log" in result.stderr
    assert path.read_text() == before and clean(repo)


def test_a_failure_while_a_patch_is_applied_still_restores_the_tree(repo: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    gone = repo / "tmp" / "gone"
    gone.mkdir()
    # the test deletes the log's folder, so writing its result fails while the patch is applied
    result = mutate(repo, killed, test=f"rm -rf {gone}; {TESTS}", to=gone / "m.log")
    assert result.returncode == 1 and "FileNotFoundError" in result.stderr
    assert clean(repo) and (repo / "calc.py").read_text() == MODULE


def seen_env(repo: Path, tmp_path: Path, **env: str) -> dict[str, str]:
    """The VIRTUAL_ENV and PATH the test command sees when mutate.py starts with `env` over its own."""
    seen = tmp_path / "seen.json"
    script = tmp_path / "dump.py"
    script.write_text(
        "import json, os, sys\n"
        "json.dump({k: os.environ.get(k) for k in ('VIRTUAL_ENV', 'PATH', 'UV_RUN_RECURSION_DEPTH')}, open(sys.argv[1], 'w'))\n"
    )
    killed = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, killed, test=f"{sys.executable} {script} {seen}; false", env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(seen.read_text())


def test_the_test_command_does_not_see_the_scripts_own_environment(
    repo: Path, tmp_path: Path
) -> None:
    own_bin = str(Path(sys.prefix) / "bin")
    seen = seen_env(
        repo, tmp_path, VIRTUAL_ENV=sys.prefix, PATH=os.pathsep.join([own_bin, "/usr/bin", "/bin"])
    )
    assert seen["VIRTUAL_ENV"] is None
    assert own_bin not in seen["PATH"].split(os.pathsep) and "/usr/bin" in seen["PATH"]


def test_a_virtual_env_the_caller_set_on_purpose_reaches_the_test_command(
    repo: Path, tmp_path: Path
) -> None:
    elsewhere = str(tmp_path / "project-venv")
    path = os.pathsep.join([str(Path(sys.prefix) / "bin"), "/usr/bin", "/bin"])
    seen = seen_env(repo, tmp_path, VIRTUAL_ENV=elsewhere, PATH=path)
    assert seen["VIRTUAL_ENV"] == elsewhere and seen["PATH"] == path


# the cases a path heuristic can't tell apart: uv replaces the caller's VIRTUAL_ENV before the script starts, so
# neither is reconstructed, whether or not the caller activated an environment
CALLERS = {
    "activated, another directory in front of its bin": lambda venv: (
        str(venv),
        ["/usr/bin", str(venv / "bin"), "/bin"],
    ),
    "not activated, its bin first on PATH": lambda venv: (
        None,
        [str(venv / "bin"), "/usr/bin", "/bin"],
    ),
}


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
@pytest.mark.parametrize("case", CALLERS)
def test_under_uv_run_the_test_command_gets_no_virtual_env_and_the_callers_path(
    repo: Path, tmp_path: Path, case: str
) -> None:
    """The test command gets no VIRTUAL_ENV, never a guessed one, and the caller's PATH without the script's bin."""
    venv = tmp_path / "caller-venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    # uv inspects an active environment's interpreter
    (venv / "bin" / "python3").symlink_to(sys.executable)
    virtual_env, entries = CALLERS[case](venv)
    path = os.pathsep.join(entries)
    seen = tmp_path / "seen.json"
    script = tmp_path / "dump.py"
    script.write_text(
        "import json, os, sys\n"
        "keys = ('VIRTUAL_ENV', 'PATH')\n"
        "json.dump({k: os.environ.get(k) for k in keys}, open(sys.argv[1], 'w'))\n"
    )
    killed = patch(repo, "add.patch", "a + b", "a - b")
    env = {
        k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_RUN_RECURSION_DEPTH")
    } | {"PATH": path}
    if virtual_env:
        env["VIRTUAL_ENV"] = virtual_env
    result = subprocess.run(
        [
            str(shutil.which("uv")),
            "run",
            "-q",
            "--script",
            str(MUTATE),
            "--test",
            f"{sys.executable} {script} {seen}; false",
            "--log",
            str(log_path(repo)),
            str(killed),
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    got = json.loads(seen.read_text())
    assert got["VIRTUAL_ENV"] is None and got["PATH"] == path


def test_a_run_nested_under_another_uv_run_sees_the_callers_environment_depth(
    repo: Path, tmp_path: Path
) -> None:
    """uv counts each nested run in UV_RUN_RECURSION_DEPTH; the test command gets the count minus this script's."""
    seen = seen_env(repo, tmp_path, VIRTUAL_ENV=sys.prefix, UV_RUN_RECURSION_DEPTH="2")
    assert seen["UV_RUN_RECURSION_DEPTH"] == "1"


# the host gate slot (#818)
TAKE_SLOT = """
import fcntl, os, sys, time
path = sys.argv[1]
if os.environ.get("LOOP_GATE_SLOT_HELD") != path:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT)
    end = time.monotonic() + 5
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() > end:
                sys.exit(3)
            time.sleep(0.05)
sys.exit(0)
"""


def slot(tmp_path: Path) -> Path:
    return tmp_path / "cache" / "engineering-loop" / "gate.1.lock"


def slot_env(tmp_path: Path) -> dict[str, str]:
    return {"XDG_CACHE_HOME": str(tmp_path / "cache")}


def hold(path: Path) -> subprocess.Popen[str]:
    """A process holding the slot until its stdin closes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "import fcntl, os, sys\n"
        f"fd = os.open({str(path)!r}, os.O_WRONLY | os.O_CREAT)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "print('held', flush=True)\n"
        "sys.stdin.read()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    assert proc.stdout is not None and proc.stdout.readline().strip() == "held"
    return proc


def test_the_test_command_waits_while_another_process_holds_the_slot(
    repo: Path, tmp_path: Path
) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    started = tmp_path / "started"
    holder = hold(slot(tmp_path))
    command = [sys.executable, str(MUTATE), "--test", f"touch {started} && exit 1"]
    run = subprocess.Popen(
        [*command, "--log", str(log_path(repo)), str(killed)],
        cwd=repo,
        env={**os.environ, **slot_env(tmp_path)},
    )
    try:
        deadline = time.monotonic() + 30
        while not (
            log_path(repo).exists() and "waiting for the host" in log_path(repo).read_text()
        ):
            assert time.monotonic() < deadline and run.poll() is None
            time.sleep(0.05)
        time.sleep(0.5)
        assert not started.exists()
        released = time.time()
        assert holder.stdin is not None
        holder.stdin.close()
        assert run.wait(timeout=30) == 0
    finally:
        holder.kill()
        run.kill()
    assert started.stat().st_mtime >= released - 0.05
    assert f"{killed}: waiting for the host gate slot" in log(repo)
    assert clean(repo)


def test_a_free_slot_is_taken_without_a_wait_line(repo: Path, tmp_path: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    assert mutate(repo, killed, env=slot_env(tmp_path)).returncode == 0
    assert not any("waiting" in line for line in log(repo))


def test_the_slot_is_held_around_each_patchs_test_run_only(repo: Path, tmp_path: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    # the test command fails when it can't take the slot itself while its parent holds it (no re-entry variable)
    probe = (
        f'{sys.executable} -c "import fcntl,os,sys; fd=os.open({str(slot(tmp_path))!r}, os.O_WRONLY);'
        ' fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)" && exit 0 || exit 1'
    )
    mutate(repo, killed, test=probe, env=slot_env(tmp_path))
    assert log(repo)[2] == f"{killed}: exit 1 killed"
    # between runs it is free
    free = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                f"import fcntl,os; fd=os.open({str(slot(tmp_path))!r}, os.O_WRONLY);"
                "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)"
            ),
        ],
        check=False,
    )
    assert free.returncode == 0


def test_a_test_command_that_takes_the_slot_by_the_reentry_rule_does_not_deadlock(
    repo: Path, tmp_path: Path
) -> None:
    (repo / "tmp" / "take_slot.py").write_text(TAKE_SLOT)
    killed = patch(repo, "add.patch", "a + b", "a - b")
    test = f"{sys.executable} {repo / 'tmp' / 'take_slot.py'} {slot(tmp_path)} && {TESTS}"
    result = mutate(repo, killed, test=test, env=slot_env(tmp_path))
    assert result.returncode == 0, result.stderr
    # exit 1 from the tests, not 3 from a wrapper that waited on its parent
    assert log(repo)[2] == f"{killed}: exit 1 killed"


def test_a_run_under_a_holder_of_the_slot_takes_no_lock(repo: Path, tmp_path: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    holder = hold(slot(tmp_path))
    run = subprocess.Popen(
        [sys.executable, str(MUTATE), "--test", TESTS, "--log", str(log_path(repo)), str(killed)],
        cwd=repo,
        env={**os.environ, **slot_env(tmp_path), "LOOP_GATE_SLOT_HELD": str(slot(tmp_path))},
    )
    try:
        # a run that took the lock anyway would wait on the holder for good
        assert run.wait(timeout=20) == 0
    finally:
        holder.kill()
        run.kill()
    assert not any("waiting" in line for line in log(repo))


def test_the_slot_is_released_after_each_patch_so_the_next_does_not_wait(
    repo: Path, tmp_path: Path
) -> None:
    first = patch(repo, "add.patch", "a + b", "a - b")
    second = patch(repo, "add2.patch", "a + b", "a * b")
    run = subprocess.Popen(
        [sys.executable, str(MUTATE), "--test", TESTS, "--log", str(log_path(repo))]
        + [str(first), str(second)],
        cwd=repo,
        env={**os.environ, **slot_env(tmp_path)},
    )
    try:
        # a slot kept after the first patch would block the second for good
        assert run.wait(timeout=20) == 0
    finally:
        run.kill()
    assert not any("waiting" in line for line in log(repo))


def test_a_run_that_hangs_is_stopped_with_everything_it_started(repo: Path, tmp_path: Path) -> None:
    killed = patch(repo, "add.patch", "a + b", "a - b")
    pidfile = tmp_path / "sleeper.pid"
    with pytest.raises(subprocess.TimeoutExpired):
        mutate(repo, killed, test=f"echo $$ > {pidfile} && exec sleep 300", timeout=3)
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(pid, signal.SIGKILL)
        pytest.fail("the test command of a timed-out run is still running")
    assert clean(repo)


def test_the_hosts_slot_held_by_another_process_is_not_waited_on(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a fake host: its cache is where a run without the fixture's XDG_CACHE_HOME would look for the slot
    host = tmp_path / "host"
    host_slot = host / ".cache" / "engineering-loop" / "gate.1.lock"
    monkeypatch.setenv("HOME", str(host))
    assert os.environ["XDG_CACHE_HOME"] == str(tmp_path / "cache")
    assert "LOOP_GATE_SLOT_HELD" not in os.environ
    holder = hold(host_slot)
    try:
        killed = patch(repo, "add.patch", "a + b", "a - b")
        # a run that waited on the host's slot would hit the timeout
        result = mutate(repo, killed, timeout=20)
        assert result.returncode == 0, result.stderr
        assert not any("waiting" in line for line in log(repo))
        # the helper's other runs, here a bare Popen, see the same slot
        assert stopped(repo, tmp_path, signal.SIGTERM) != 0
    finally:
        holder.kill()
        holder.wait()
    assert clean(repo)
