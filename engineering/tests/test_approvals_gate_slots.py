"""The host gate has `GATE_SLOTS` heavy slots, a third of the cores by default (#1138): a step or a mutation run takes
the first free one, waits only when every one is held, and a record is never torn when two gates write it."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import threading
import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    gatekeeper_md,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)
from test_approvals_gate_steps import steps  # noqa: F401
from test_mutate import clean, log, mutate, patch, policy, recording, repo, slots  # noqa: F401


def hold(number: int, seconds: float = 3.0) -> Callable[[], None]:
    """Hold heavy slot `number` the way a running gate does; the returned function frees it, and it frees itself after
    `seconds`, so a step that wrongly waits for it fails its assertion instead of hanging."""
    path = Path(approvals.slot_path(number))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    freed = threading.Lock()

    def release() -> None:
        if freed.acquire(blocking=False):
            os.close(fd)

    timer = threading.Timer(seconds, release)
    timer.daemon = True
    timer.start()
    return release


def test_a_second_step_takes_the_next_free_slot_without_waiting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GATE_SLOTS", "2")
    first = hold(1)
    try:
        with approvals.heavy_slot("unit") as (path, waited):
            assert path == approvals.slot_path(2) and waited == 0
    finally:
        first()
    assert "waiting" not in capsys.readouterr().err


def test_with_every_slot_held_a_step_waits_and_says_so_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GATE_SLOTS", "2")
    held = [hold(1, 3.0), hold(2, 1.0)]
    try:
        with approvals.heavy_slot("unit") as (path, waited):
            assert path == approvals.slot_path(2) and waited >= 1
    finally:
        held[0]()
    assert capsys.readouterr().err.count("local-ci: unit: waiting for the host gate slot") == 1


def test_gate_slots_1_keeps_one_gate_at_a_time(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GATE_SLOTS", "1")
    hold(1, 1.0)
    began = time.monotonic()
    with approvals.heavy_slot("unit") as (path, _):
        assert path == approvals.slot_path(1)
    assert time.monotonic() - began >= 1.0
    assert "waiting for the host gate slot" in capsys.readouterr().err


@pytest.mark.parametrize(("cores", "slots"), [(12, 4), (8, 2), (3, 1), (2, 1), (1, 1), (None, 1)])
def test_the_slot_count_defaults_to_a_third_of_the_cores_and_at_least_one(
    monkeypatch: pytest.MonkeyPatch, cores: int | None, slots: int
) -> None:
    monkeypatch.delenv("GATE_SLOTS")
    monkeypatch.setattr(os, "cpu_count", lambda: cores)
    assert approvals.gate_slots() == slots


@pytest.mark.parametrize("said", ["", "0", "-2", "many", "1.5"])
def test_a_gate_slots_that_is_not_a_whole_number_from_1_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, said: str
) -> None:
    monkeypatch.setenv("GATE_SLOTS", said)
    monkeypatch.setattr(os, "cpu_count", lambda: 12)
    assert approvals.gate_slots() == 4


def test_a_run_under_the_second_slot_takes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATE_SLOTS", "2")
    held = [hold(1), hold(2)]
    monkeypatch.setenv(approvals.SLOT_HELD, approvals.slot_path(2))
    try:
        began = time.monotonic()
        with approvals.heavy_slot("unit") as (path, waited):
            assert (path, waited) == (approvals.slot_path(2), 0)
        assert time.monotonic() - began < 1.0
    finally:
        for release in held:
            release()


def test_two_gates_on_one_tree_and_command_one_per_slot_leave_one_valid_record(
    steps: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each gate sleeps in its slot until the other has started, so the two overlap on slots 1 and 2."""
    monkeypatch.setenv("GATE_SLOTS", "2")
    seen, script = tmp_path / "seen", tmp_path / "gate.py"
    script.write_text(
        "import os, pathlib, sys, time\n"
        "seen = pathlib.Path(sys.argv[1])\n"
        "seen.open('a').write(os.environ['LOOP_GATE_SLOT_HELD'] + '\\n')\n"
        "for _ in range(200):\n"
        "    if len(seen.read_text().split()) >= 2:\n"
        "        break\n"
        "    time.sleep(0.05)\n"
    )
    command = f"{sys.executable} {script} {seen}"
    steps["set_policy"](gatekeeper_md(f"loop:\n  gate: {command}\n"))
    codes: list[int] = []
    runs = [
        threading.Thread(target=lambda: codes.append(approvals.main(["local-ci", "--record"])))
        for _ in range(2)
    ]
    for run in runs:
        run.start()
    for run in runs:
        run.join(60)
    assert codes == [0, 0]
    assert sorted(seen.read_text().split()) == [approvals.slot_path(1), approvals.slot_path(2)]
    files = sorted(approvals.local_ci_dir().iterdir())
    assert [f.name for f in files] == [approvals.recorded(steps["tree"], command).name]
    assert json.loads(files[0].read_text())["exit"] == 0


def test_a_record_is_replaced_whole_never_truncated_in_place(
    steps: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader meeting a record mid-write would find it empty: the write goes to a file of its own, which replaces the
    record in one step, so the old record is whole until then."""
    record = {"tree": steps["tree"], "command": "gate", "exit": 0}
    approvals.stored(record)
    where = approvals.recorded(record["tree"], record["command"])
    replaced: list[dict[str, Any]] = []
    real = os.replace

    def replace(source: Any, target: Any) -> None:
        replaced.append(json.loads(where.read_text()))
        assert json.loads(Path(source).read_text())["seconds"] == 2
        real(source, target)

    monkeypatch.setattr(approvals.os, "replace", replace)
    approvals.stored({**record, "seconds": 2})
    assert replaced == [record]
    assert json.loads(where.read_text())["seconds"] == 2
    assert [f.name for f in where.parent.iterdir()] == [where.name]


def test_mutate_takes_a_free_slot_when_the_first_is_held(repo: Path, tmp_path: Path) -> None:
    policy(repo, 0)
    first = patch(repo, "add.patch", "a + b", "a - b")
    record = tmp_path / "slots"
    held = hold(1, 8.0)
    try:
        # a run that took only slot 1 would wait for its holder to let go, and name that slot
        result = mutate(repo, first, test=recording(record), env={"GATE_SLOTS": "2"}, timeout=30)
    finally:
        held()
    assert result.returncode == 0, result.stderr
    assert slots(record) == [approvals.slot_path(2)]
    assert not any("waiting" in line for line in log(repo))
    assert clean(repo)


@pytest.mark.parametrize("slots", ["1", "2"])
def test_a_waiting_land_takes_the_next_free_slot_ahead_of_a_waiting_pr_gate(
    monkeypatch: pytest.MonkeyPatch, slots: str
) -> None:
    """A land holds the landing lock while its gate waits, so it takes a freed slot first though the PR gate waited
    longer. With one slot the land blocks in the kernel; with several it polls, and the slots free between two polls
    of the PR gate, so a plain race would give the PR gate the first."""
    monkeypatch.setenv("GATE_SLOTS", slots)
    for number in range(1, int(slots) + 1):
        hold(number, 1.52)
    order: list[str] = []

    def gate(name: str, land: bool) -> None:
        fd, _ = approvals.take_slot(land=land)
        order.append(name)
        time.sleep(0.4)
        assert fd is not None
        os.close(fd)

    pr = threading.Thread(target=gate, args=("pr", False), daemon=True)
    land = threading.Thread(target=gate, args=("land", True), daemon=True)
    pr.start()
    time.sleep(0.5)
    land.start()
    for thread in (pr, land):
        thread.join(20)
    assert order == ["land", "pr"]


def test_a_land_takes_a_free_slot_at_once_on_several_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    """A land yields to no one, its own mark included: with every slot free it holds one without waiting."""
    monkeypatch.setenv("GATE_SLOTS", "2")
    got: list[str] = []
    waited: list[bool] = []
    thread = threading.Thread(
        target=lambda: got.append(approvals.take_slot(lambda: waited.append(True), land=True)[1]),
        daemon=True,
    )
    thread.start()
    thread.join(5)
    assert got == [approvals.slot_path(1)] and not waited


def test_a_lands_batch_gate_runs_its_steps_as_a_land(
    steps: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the land's own gate steps take a slot ahead of PR gates: gate_batch hands run_steps `land`, and run_steps
    hands it to each step it runs."""
    seen: list[bool] = []
    real = approvals.run_steps

    def run_steps(*_args: Any, land: bool = False, **_kw: Any) -> dict[str, Any]:
        seen.append(land)
        return {"code": 0, "left": [], "ran": [], "records": [], "step": None}

    monkeypatch.setattr(approvals, "run_steps", run_steps)
    assert approvals.gate_batch(steps["repo"], []) == (steps["tree"], "reused")
    assert seen == [True]

    lands: list[bool] = []

    def ran_step(_step: Any, _cwd: Any, _out: Any, _load: Any, land: bool) -> tuple[int, int, int]:
        lands.append(land)
        return 0, 0, 0

    monkeypatch.setattr(approvals, "run_steps", real)
    monkeypatch.setattr(approvals, "ran_step", ran_step)
    monkeypatch.setattr(approvals, "step_pass", lambda *_a, **_k: None)
    approvals.run_steps(steps["head"], steps["tree"], lambda: "", steps["repo"], land=True)
    assert lands and all(lands)


def test_a_waiting_land_on_one_slot_beats_a_blocking_flock_that_started_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gate wrapper's own flock is woken by the kernel the moment the slot frees, so a polling land would lose every
    race to it; a land on one slot blocks in the kernel too, and the one that waited longer gets the slot."""
    monkeypatch.setenv("GATE_SLOTS", "1")
    hold(1, 1.5)
    order: list[str] = []

    def land() -> None:
        fd, _ = approvals.take_slot(land=True)
        order.append("land")
        time.sleep(0.3)
        assert fd is not None
        os.close(fd)

    def wrapper() -> None:
        fd = os.open(approvals.slot_path(1), os.O_WRONLY | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX)
        order.append("wrapper")
        os.close(fd)

    threads = [threading.Thread(target=land), threading.Thread(target=wrapper)]
    threads[0].start()
    time.sleep(0.3)
    threads[1].start()
    for thread in threads:
        thread.join(20)
    assert order == ["land", "wrapper"]


def test_a_run_under_any_slot_is_held_whatever_gate_slots_it_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parent took `gate.3.lock` under the default count; a child under a wrapper's `GATE_SLOTS=1` still runs under
    it. Only a `gate.<n>.lock` of the slot directory counts."""
    monkeypatch.setenv("GATE_SLOTS", "1")
    monkeypatch.setenv(approvals.SLOT_HELD, approvals.slot_path(3))
    assert approvals.held_slot() == approvals.slot_path(3)
    for other in (approvals.slot_file("gate.short.lock"), "/elsewhere/gate.1.lock", "gate.x.lock"):
        monkeypatch.setenv(approvals.SLOT_HELD, other)
        assert approvals.held_slot() is None


def test_this_repos_gate_wrapper_takes_no_slot_under_any_gate_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`mise run test` runs pytest behind tools/gate_slot.py: under a gate that holds `gate.2.lock` it takes none,
    though `gate.1.lock` is held, and a bare run takes the free slot 2 and tells its command."""
    wrapper = Path(__file__).resolve().parents[2] / "tools" / "gate_slot.py"
    hold(1, 30.0)
    env = {**os.environ, "GATE_SLOTS": "2"}
    # prints the slot it is told it runs under, and whether that lock is still held (a try at it fails) by the wrapper
    probe = (
        "import fcntl, os\n"
        "path = os.environ['LOOP_GATE_SLOT_HELD']\n"
        "fd = os.open(path, os.O_WRONLY)\n"
        "try:\n"
        "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
        "    print(path, 'free')\n"
        "except BlockingIOError:\n"
        "    print(path, 'held')\n"
    )
    show = [sys.executable, "-c", probe]
    bare = subprocess.run(
        [sys.executable, str(wrapper), *show],
        env={k: v for k, v in env.items() if k != approvals.SLOT_HELD},
        capture_output=True, text=True, timeout=10, check=False,
    )  # fmt: skip
    # the lock survives the exec: pytest under it holds the slot, not just the variable naming it
    assert bare.stdout.split() == [approvals.slot_path(2), "held"] and "waiting" not in bare.stderr
    # every slot held, one of them by this run's parent: a second slot would wait for good
    hold(2, 30.0)
    held = subprocess.run(
        [sys.executable, str(wrapper), *show],
        env={**env, approvals.SLOT_HELD: approvals.slot_path(2)},
        capture_output=True, text=True, timeout=10, check=False,
    )  # fmt: skip
    assert held.stdout.split()[0] == approvals.slot_path(2) and "waiting" not in held.stderr


def test_a_lands_gate_step_reaches_take_slot_as_a_land(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flag travels ran_step -> heavy_slot -> take_slot; a link dropping it would switch land priority off."""
    seen: list[bool] = []

    def take_slot(waiting: Any = None, land: bool = False) -> tuple[None, str]:
        seen.append(land)
        return None, approvals.slot_path()

    monkeypatch.setattr(approvals, "take_slot", take_slot)
    real = subprocess.run
    monkeypatch.setattr(
        approvals.subprocess,
        "run",
        lambda words, **kw: (
            subprocess.CompletedProcess(words, 0) if words == ["true"] else real(words, **kw)
        ),
    )
    step = {"name": "unit", "words": ["true"], "sets": {}, "legacy": False, "command": "true"}
    approvals.ran_step(step, land=True)
    approvals.ran_step(step)
    assert seen == [True, False]


def test_a_failed_record_write_leaves_no_partial_file(
    steps: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    record = {"tree": steps["tree"], "command": "gate", "exit": 0}
    approvals.stored(record)
    where = approvals.recorded(record["tree"], record["command"])

    def replace(*_args: Any) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(approvals.os, "replace", replace)
    with pytest.raises(OSError):
        approvals.stored({**record, "seconds": 2})
    assert json.loads(where.read_text()) == record
    assert [f.name for f in where.parent.iterdir()] == [where.name]


def test_mutate_under_the_second_slot_stays_in_it_and_hands_it_down(
    repo: Path, tmp_path: Path
) -> None:
    """A run under `gate.2.lock` runs every patch in that slot, not the short lane, so a heavy wrapper under it takes
    none."""
    first = patch(repo, "add.patch", "a + b", "a - b")
    record = tmp_path / "slots"
    held = approvals.slot_path(2)
    result = mutate(
        repo, first, test=recording(record),
        env={"GATE_SLOTS": "2", approvals.SLOT_HELD: held}, timeout=30,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert log(repo)[2] == "heavy: run under a holder of the heavy slot"
    assert slots(record) == [held]


def test_the_repos_test_task_runs_pytest_behind_the_slot_wrapper() -> None:
    """The wrapper above only counts if `mise run test` runs pytest behind it, not behind a lock of its own."""
    root = Path(__file__).resolve().parents[2]
    run = tomllib.loads((root / "mise.toml").read_text())["tasks"]["test"]["run"]
    assert run.startswith("uv run python tools/gate_slot.py pytest ")


# the slot count's shared table (#1232): the template's `gate-slot` tests the same file, so both count alike
TABLE = Path(__file__).resolve().parent / "fixtures" / "gate-slots.tsv"


def table() -> list[Any]:
    """The table's rows as pytest params, each named for its inputs and the limit it expects."""
    rows = []
    for line in TABLE.read_text().splitlines():
        if line and not line.startswith("#"):
            row = line.split("\t")
            assert len(row) == 8, line
            rows.append(pytest.param(*row, id="-".join(row)))
    return rows


def unset(value: str) -> int | None:
    return None if value == "-" else int(value)


@pytest.mark.parametrize(
    ("cores", "memory", "cost_cores", "cost_gb", "reserve", "said", "count", "limit"), table()
)
def test_the_slot_count_follows_the_shared_table(
    cores: str, memory: str, cost_cores: str, cost_gb: str, reserve: str, said: str,
    count: str, limit: str,
) -> None:  # fmt: skip
    cost = (
        approvals.COST_DEFAULT
        if cost_cores == "-"
        else (int(cost_cores), int(cost_gb), unset(reserve))
    )
    plan = approvals.slot_plan(int(cores), int(memory), cost, "" if said == "-" else said)
    assert (plan.count, plan.limit) == (int(count), limit)


def loop_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """A checkout whose docs/agents/loop.md holds `text`, as the process's working directory, in a subdirectory, so
    the line is read from the checkout's root."""
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(text)
    (tmp_path / "sub").mkdir()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path / "sub")


def host(monkeypatch: pytest.MonkeyPatch, cores: int, memory: int, said: str | None) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: cores)
    monkeypatch.setattr(approvals, "total_memory", lambda: memory)
    if said is None:
        monkeypatch.delenv("GATE_SLOTS")
    else:
        monkeypatch.setenv("GATE_SLOTS", said)


@pytest.mark.parametrize(
    ("cores", "memory", "cost_cores", "cost_gb", "reserve", "said", "count", "limit"), table()
)
def test_the_host_counts_the_table_from_its_gate_cost_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    cores: str, memory: str, cost_cores: str, cost_gb: str, reserve: str, said: str,
    count: str, limit: str,
) -> None:  # fmt: skip
    """The same rows read as a host does: loop.md's `Gate cost:` line, the host's cores and memory, `GATE_SLOTS`."""
    line = "" if cost_cores == "-" else f"Gate cost: {cost_cores} cores, {cost_gb} GB"
    line += "" if reserve == "-" else f", reserve {reserve} GB"
    loop_md(tmp_path, monkeypatch, f"# Loop\n\n{line}\n")
    host(monkeypatch, int(cores), int(memory), None if said == "-" else said)
    assert (approvals.gate_slots(), approvals.host_plan().limit) == (int(count), limit)


def test_cores_set_the_count_when_memory_holds_more_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_md(tmp_path, monkeypatch, "Gate cost: 4 cores, 4 GB\n")
    host(monkeypatch, 16, 64, None)
    assert approvals.host_plan().line() == (
        "slots 4: cores (16 cores, 64 GB, cost 4 cores 4 GB, reserve 16 GB)"
    )


def test_memory_sets_the_count_when_it_holds_fewer_runs_than_the_cores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate that starts a database container: 16 GB less the 4 GB reserve holds two 6 GB runs, the cores four."""
    loop_md(tmp_path, monkeypatch, "Gate cost: `4 cores, 6 GB`\n")
    host(monkeypatch, 16, 16, None)
    assert approvals.host_plan().line() == (
        "slots 2: memory (16 cores, 16 GB, cost 4 cores 6 GB, reserve 4 GB)"
    )


def test_a_reserve_on_the_line_replaces_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_md(tmp_path, monkeypatch, "Gate cost: 1 core, 2 GB, reserve 10 GB\n")
    host(monkeypatch, 16, 16, None)
    assert approvals.host_plan() == approvals.SlotPlan(3, "memory", 16, 16, 1, 2, 10)


@pytest.mark.parametrize("value", ["4 cores", "0 cores, 4 GB", "4 cores, 1.5 GB", "four"])
def test_a_gate_cost_line_that_does_not_parse_counts_a_third_of_the_cores_and_says_so_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    monkeypatch.setattr(approvals, "cost_said", set())
    loop_md(tmp_path, monkeypatch, f"Gate cost: {value}\n")
    host(monkeypatch, 12, 64, None)
    assert approvals.host_plan()[:2] == (4, "cores")
    approvals.host_plan()
    assert capsys.readouterr().err.count(f"loop.md's `Gate cost: {value}` is not") == 1


def test_outside_a_checkout_the_count_is_a_third_of_the_cores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loop.md with the line in a directory no `.git` marks is not a checkout's, so it counts for nothing."""
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text("Gate cost: 4 cores, 4 GB\n")
    monkeypatch.chdir(tmp_path)
    assert not any((d / ".git").exists() for d in (tmp_path, *tmp_path.parents))
    assert approvals.gate_cost() == approvals.COST_DEFAULT


def test_total_memory_is_meminfos_total_in_whole_gb(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16473764 kB\nMemAvailable:    1000000 kB\n")
    assert approvals.total_memory(str(meminfo)) == 15


def test_without_meminfo_total_memory_is_sysctls_hw_memsize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A macOS host: no meminfo, and `sysctl -n hw.memsize` prints bytes; with neither the memory is 0."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sysctl = bin_dir / "sysctl"
    sysctl.write_text('#!/bin/sh\n[ "$*" = "-n hw.memsize" ] && echo 34359738368\n')
    sysctl.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert approvals.total_memory(str(tmp_path / "none")) == 32
    sysctl.write_text("#!/bin/sh\necho 34359738368\nexit 1\n")
    assert approvals.total_memory(str(tmp_path / "none")) == 0


def test_heavy_plan_prints_the_plan_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loop_md(tmp_path, monkeypatch, "Gate cost: 4 cores, 4 GB\n")
    host(monkeypatch, 16, 16, None)
    assert approvals.main(["heavy", "--plan"]) == 0
    assert capsys.readouterr().out == (
        "slots 3: memory (16 cores, 16 GB, cost 4 cores 4 GB, reserve 4 GB)\n"
    )
    assert approvals.main(["heavy", "--plan", "true"]) == 1
    assert "takes no command" in capsys.readouterr().out


def test_a_wait_for_the_slot_names_the_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loop_md(tmp_path, monkeypatch, "Gate cost: 16 cores, 1 GB\n")
    host(monkeypatch, 16, 64, None)
    hold(1, 1.0)
    with approvals.heavy_slot("unit"):
        pass
    assert (
        "local-ci: unit: waiting for the host gate slot"
        " (slots 1: cores (16 cores, 64 GB, cost 16 cores 1 GB, reserve 16 GB))"
    ) in capsys.readouterr().err


def held_by_another_process(path: str) -> subprocess.Popen[str]:
    """A process holding `path`'s exclusive flock until its stdin closes; it says `held` once it holds it."""
    holder = subprocess.Popen(
        [
            sys.executable, "-c",
            (
                "import fcntl, os, sys\n"
                "fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT)\n"
                "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                "print('held', flush=True)\n"
                "sys.stdin.read()\n"
            ),
            path,
        ],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    assert holder.stdout is not None and holder.stdout.readline() == "held\n"
    return holder


def test_gate_slots_off_runs_a_command_while_another_process_holds_gate_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The off switch takes no lock: a step, this repo's gate wrapper and mutate.py's short lane each run at once
    though another process holds slot 1 (and the short lane), and a step's command is told it holds none."""
    Path(approvals.slot_path()).parent.mkdir(parents=True, exist_ok=True)
    holders = [held_by_another_process(approvals.slot_path(1))]
    holders.append(held_by_another_process(approvals.slot_file("gate.short.lock")))
    monkeypatch.setenv("GATE_SLOTS", "off")
    try:
        began = time.monotonic()
        assert approvals.take_slot() == (None, "")
        with approvals.heavy_slot("unit") as (path, waited):
            assert (path, waited) == ("", 0)
        step = {"name": "unit", "words": [sys.executable, "-c", "pass"], "sets": {}}
        step |= {"legacy": False, "command": "pass"}
        assert approvals.ran_step(step)[0] == 0
        wrapper = Path(__file__).resolve().parents[2] / "tools" / "gate_slot.py"
        probe = "import os; print(repr(os.environ['LOOP_GATE_SLOT_HELD']))"
        ran = subprocess.run(
            [sys.executable, str(wrapper), sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
        assert (ran.returncode, ran.stdout) == (0, "''\n"), ran.stderr
        sys.path.insert(0, str(Path(approvals.__file__).resolve().parent))
        import mutate

        assert mutate.take_short(mutate.slot_path(), lambda: None) is None
        assert time.monotonic() - began < 5.0
    finally:
        for holder in holders:
            holder.communicate("")
    assert "waiting" not in capsys.readouterr().err
