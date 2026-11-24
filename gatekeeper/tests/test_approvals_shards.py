"""approvals.py shards: `select.shards` splits a whole-suite selection into disjoint, balanced shards (#2229)."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import approvals, gatekeeper_md

SUITE = [f"t{n}" for n in range(1, 10)]


def policy_of(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    policy = approvals.Policy(gatekeeper_md(text))
    monkeypatch.setattr(approvals, "project", lambda: (None, policy))


def run(
    tmp_path: Path, *extra: str, selection: list[str] | None = None, durations: str | None = None
) -> None:
    (tmp_path / "suite").write_text("\n".join(SUITE))
    args = ["shards", "--suite", str(tmp_path / "suite"), *extra]
    if selection is not None:
        (tmp_path / "sel").write_text("\n".join(selection))
        args += ["--selection", str(tmp_path / "sel")]
    if durations is not None:
        (tmp_path / "dur").write_text(durations)
        args += ["--durations", str(tmp_path / "dur")]
    assert approvals.main(args) == 0


def printed(capsys: pytest.CaptureFixture[str]) -> list[list[str]]:
    shards: list[list[str]] = []
    for line in capsys.readouterr().out.splitlines():
        if line.startswith("# shard"):
            shards.append([])
        elif line:
            shards[-1].append(line)
    return shards


def test_shards_3_splits_the_whole_suite_into_three_disjoint_shards_balanced_by_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_of(monkeypatch, "select:\n  shards: 3\n")
    # t1 is as long as t2..t9 together; t9 has no recorded duration
    run(
        tmp_path,
        durations='{"t1": 8, "t2": 1, "t3": 1, "t4": 1, "t5": 1, "t6": 1, "t7": 1, "t8": 1}',
    )
    shards = printed(capsys)
    assert len(shards) == 3
    flat = [item for shard in shards for item in shard]
    assert sorted(flat) == sorted(SUITE) and len(flat) == len(
        set(flat)
    )  # disjoint, the union is the suite
    assert any(
        shard == ["t1"] for shard in shards
    )  # the long one is alone: balanced by time, not count
    assert (
        sum("t9" in shard for shard in shards) == 1
    )  # no recorded duration, still in exactly one shard


def test_shards_without_durations_split_evenly_by_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_of(monkeypatch, "select:\n  shards: 3\n")
    run(tmp_path)
    assert sorted(len(shard) for shard in printed(capsys)) == [3, 3, 3]


def test_nothing_set_or_one_shard_prints_the_one_selection_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for text in ("", "select:\n  shards: 1\n"):
        policy_of(monkeypatch, text)
        run(tmp_path)
        assert capsys.readouterr().out == "\n".join(SUITE) + "\n"


def test_a_narrow_selection_is_never_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_of(monkeypatch, "select:\n  shards: 3\n")
    run(tmp_path, selection=["t1", "t2", "t3", "t4"])  # not over half of nine
    assert capsys.readouterr().out == "t1\nt2\nt3\nt4\n"


def test_a_selection_over_half_the_suite_or_flagged_whole_is_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_of(monkeypatch, "select:\n  shards: 2\n")
    run(tmp_path, selection=SUITE[:5])
    assert len(printed(capsys)) == 2
    run(tmp_path, "--whole", selection=SUITE[:2])  # a build input changed: whole by rule
    assert len(printed(capsys)) == 2


@pytest.mark.parametrize("bad", ["0", "-1", "true", "two"])
def test_a_shards_value_below_one_or_not_a_number_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    policy_of(monkeypatch, f"select:\n  shards: {bad}\n")
    with pytest.raises(approvals.Refused):
        approvals.shard_count()


def test_the_run_passes_only_when_every_shard_has_a_record_keyed_by_its_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_of(monkeypatch, "select:\n  shards: 3\n")
    (tmp_path / "suite").write_text("\n".join(SUITE))
    shards = approvals.shard_selections(SUITE, SUITE, 3, None, True)
    keyed = [approvals.shard_command("run all", at, 3, items) for at, items in enumerate(shards, 1)]
    assert len(set(keyed)) == 3  # one record per shard: R1's key is the tree and this command
    assert len({approvals.record_name("tree", command) for command in keyed}) == 3
    held = set(keyed[:2])
    asked: list[str] = []

    def record(head: str, words: list[str]) -> int:
        asked.append(" ".join(words))
        return 0 if " ".join(words) in held else 1

    monkeypatch.setattr(approvals, "gate_record", record)
    args = ["shards", "--suite", str(tmp_path / "suite"), "--passed", "h", "--command", "run all"]
    assert approvals.main(args) == 1  # the third has no pass
    assert asked == keyed
    held.add(keyed[2])
    assert approvals.main(args) == 0
