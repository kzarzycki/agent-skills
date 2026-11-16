"""The host gate has `GATE_SLOTS` heavy slots, a third of the cores by default (#1138): a step or a mutation run takes
the first free one, waits only when every one is held, and a record is never torn when two gates write it."""

from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
import time
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


def test_a_waiting_land_takes_the_next_free_slot_ahead_of_a_waiting_pr_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A land holds the landing lock while its gate waits, so it takes a freed slot first though the PR gate waited
    longer. The slot frees between two polls of the PR gate, so a plain race would give it to the PR gate."""
    monkeypatch.setenv("GATE_SLOTS", "1")
    hold(1, 1.52)
    order: list[str] = []

    def gate(name: str, land: bool) -> None:
        fd, _ = approvals.take_slot(land=land)
        order.append(name)
        time.sleep(0.4)
        assert fd is not None
        os.close(fd)

    pr = threading.Thread(target=gate, args=("pr", False))
    land = threading.Thread(target=gate, args=("land", True))
    pr.start()
    time.sleep(0.5)
    land.start()
    for thread in (pr, land):
        thread.join(20)
    assert order == ["land", "pr"]


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
