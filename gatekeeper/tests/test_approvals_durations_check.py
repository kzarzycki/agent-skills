"""`durations --check`: a time budget per test file and per test, read from `timeouts` (#1400)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from approvals_harness import LOOP, add, approvals

BUDGETS = "file_budget: 2m\ntest_budget: 5s\n"


def policy(settings: str = BUDGETS) -> str:
    return add(LOOP, "timeouts", settings)


@pytest.fixture
def nightly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The nightly's two files in a directory of their own, and a policy with budgets; `record(files, tests)` writes them."""
    monkeypatch.setattr(approvals, "toplevel", lambda: tmp_path)
    monkeypatch.setattr(approvals, "tree_policy", lambda root: policy())

    def record(files: dict[str, float], tests: dict[str, float]) -> None:
        (tmp_path / "durations.json").write_text(json.dumps(files))
        (tmp_path / "durations-tests.json").write_text(json.dumps(tests))

    def check() -> int:
        return approvals.durations_verb(
            None,
            None,
            None,
            False,
            str(tmp_path / "durations.json"),
            str(tmp_path / "durations-tests.json"),
        )

    record.check = check  # type: ignore[attr-defined]
    return record


def test_the_budgets_are_read_from_timeouts_beside_test_and_run() -> None:
    assert approvals.timeouts(policy()) == {
        "test": 60,
        "run": 3600,
        "file_budget": 120,
        "test_budget": 5,
    }
    assert "file_budget" not in approvals.timeouts(LOOP)  # unset: nothing to check


def test_a_malformed_budget_is_refused_naming_the_key() -> None:
    with pytest.raises(approvals.Refused, match=r"`timeouts\.test_budget` is"):
        approvals.settings(policy("test_budget: fast\n"))


def test_a_run_within_its_budgets_passes(nightly, capsys: pytest.CaptureFixture[str]) -> None:
    nightly({"tests/test_a.py": 60.0}, {"tests/test_a.py::test_x": 3.0})
    assert nightly.check() == 0
    said = capsys.readouterr().out
    assert (
        "tests/test_a.py" in said and "within its budget" in said
    )  # the slowest are listed, then the verdict


def test_a_file_over_its_budget_fails_the_check_naming_file_time_and_budget(
    nightly, capsys: pytest.CaptureFixture[str]
) -> None:
    nightly({"tests/test_a.py": 130.5, "tests/test_b.py": 5.0}, {"tests/test_b.py::test_y": 1.0})
    assert nightly.check() == 1
    said = capsys.readouterr().out
    assert "file tests/test_a.py took 130.5s, over its budget of 120s" in said
    assert "test_b.py took" not in said


def test_a_test_over_its_budget_fails_the_check_naming_file_test_time_and_budget(
    nightly, capsys: pytest.CaptureFixture[str]
) -> None:
    nightly(
        {"tests/test_a.py": 20.0},
        {"tests/test_a.py::test_slow": 7.25, "tests/test_a.py::test_ok": 1.0},
    )
    assert nightly.check() == 1
    said = capsys.readouterr().out
    assert (
        "test tests/test_a.py::test_slow (file tests/test_a.py) took 7.2s, over its budget of 5s"
        in said
    )
    assert "test_ok" not in said.split("over its budget")[1]


def test_without_budgets_the_check_lists_the_slowest_and_passes(
    nightly, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(approvals, "tree_policy", lambda root: LOOP)
    nightly({"tests/test_a.py": 9999.0}, {})
    assert nightly.check() == 0
    assert "nothing to check" in capsys.readouterr().out


def test_recording_writes_each_tests_time_beside_each_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "toplevel", lambda: tmp_path)
    log = tmp_path / "durations.log"
    log.write_text(
        "0.500s setup tests/test_a.py::test_x\n2.000s call tests/test_a.py::test_x\n"
        "1.000s call tests/test_a.py::test_y\n0.250s call tests/test_b.py::test_z[p 1]\n"
    )
    assert (
        approvals.durations_verb(
            str(log), str(tmp_path / "f.json"), None, False, tests_out=str(tmp_path / "t.json")
        )
        == 0
    )
    assert json.loads((tmp_path / "f.json").read_text()) == {
        "tests/test_a.py": 3.5,
        "tests/test_b.py": 0.25,
    }
    assert (
        json.loads((tmp_path / "t.json").read_text())
        == {
            "tests/test_a.py::test_x": 2.5,
            "tests/test_a.py::test_y": 1.0,
            "tests/test_b.py::test_z[p 1]": 0.25,  # an id with a space, as the nightly's own log writes it
        }
    )
