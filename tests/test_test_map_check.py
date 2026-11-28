"""tools/test_map_check.py (#1400): the nightly saves the map of the tests that passed, and refuses an empty one."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml
from coverage import CoverageData

from tools import affected_tests as a
from tools import test_map_check as check

ROOT = Path(__file__).resolve().parents[1]
MOD = "def good():\n    return 1\n\n\ndef bad():\n    return 2\n"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def nightly_core() -> str:
    """The `COVERAGE_CORE` the nightly's map run sets: a test here runs under the nightly's own tracer, not one it picks."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/engineering-ci.yml").read_text())
    steps = [s for job in workflow["jobs"].values() for s in job["steps"]]
    mapped = [
        s for s in steps if "--cov-context=test" in s.get("env", {}).get("PYTEST_ADDOPTS", "")
    ]
    return str(mapped[0]["env"].get("COVERAGE_CORE", "sysmon"))


def run_suite(project: Path, tests: dict[str, str], cover: tuple[str, ...] = ("pkg",)) -> Path:
    """Run `tests` under `project` the way the nightly does (one coverage context per test, the map plugin's failed,
    skipped and durations lists) and return the map directory."""
    (project / "pkg").mkdir()
    (project / "pkg/mod.py").write_text(MOD)
    (project / "tests").mkdir()
    for name, text in tests.items():
        (project / "tests" / name).write_text(text)
    (project / ".coveragerc").write_text("[run]\nparallel = true\nrelative_files = true\n")
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    root = project / ".test-map"
    root.mkdir()
    env = {
        **os.environ,
        "PYTHONPATH": f"{ROOT}{os.pathsep}{project}",
        "COVERAGE_CORE": nightly_core(),
        "COVERAGE_FILE": str(root / "coverage"),
        "TEST_MAP_FAILED": str(root / "failed"),
        "TEST_MAP_SKIPPED": str(root / "skipped"),
        "TEST_DURATIONS": str(root / "durations.log"),
    }
    env.pop("PYTEST_ADDOPTS", None)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "tools.test_map_plugin",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
            "-o",
            "addopts=",
            *(f"--cov={c}" for c in cover),
            "--cov-context=test",
            "--cov-report=",
            "tests",
        ],
        cwd=project,
        env=env,
        check=False,
        capture_output=True,
    )
    return root


def test_a_map_with_no_entries_fails_the_map_step(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".test-map"
    root.mkdir()
    CoverageData(basename=str(root / "coverage")).write()  # a run that measured nothing
    assert check.main(["test_map_check.py", str(root)]) == 1
    assert "map is empty" in capsys.readouterr().err


def test_a_map_with_no_coverage_file_fails_the_map_step(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert check.main(["test_map_check.py", str(tmp_path / "nothing")]) == 1
    assert "map is empty" in capsys.readouterr().err


def test_a_map_short_of_a_test_that_passed_fails_the_map_step(
    tmp_path, monkeypatch, capsys
) -> None:
    root = run_suite(
        tmp_path,
        {
            "test_one.py": "from pkg import mod\n\n\ndef test_one():\n    mod.good()\n",
            "test_two.py": "from pkg import mod\n\n\ndef test_two():\n    mod.good()\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    assert check.main(["test_map_check.py", str(root)]) == 0
    with sqlite3.connect(
        root / "coverage"
    ) as db:  # lose one test's contexts, as a run that recorded none would
        db.execute(
            "delete from line_bits where context_id in (select id from context where context like '%test_two%')"
        )
    assert check.main(["test_map_check.py", str(root)]) == 1
    said = capsys.readouterr().err
    assert "fewer tests than ran" in said and "tests/test_two.py::test_two" in said


def test_a_map_from_a_run_with_one_failing_test_still_selects_by_lines(
    tmp_path, monkeypatch, capsys
) -> None:
    root = run_suite(
        tmp_path,
        {
            "test_good.py": "from pkg import mod\n\n\ndef test_good():\n    assert mod.good() == 1\n",
            "test_fine.py": "from pkg import mod\n\n\ndef test_fine():\n    assert mod.bad() == 2\n",
            "test_red.py": "from pkg import mod\n\n\ndef test_red():\n    assert mod.bad() == 3\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    git("add", ".")
    git("commit", "-qm", "base")
    (root / "sha").write_text(git("rev-parse", "HEAD"))
    assert (root / "failed").read_text().split() == ["tests/test_red.py::test_red"]
    assert (
        check.main(["test_map_check.py", str(root)]) == 0
    )  # the failure no longer leaves the map unfit
    monkeypatch.setattr(a, "MAP", root)
    (tmp_path / "pkg/mod.py").write_text(MOD.replace("return 1", "return 11"))
    git("commit", "-qam", "edit good")
    picked = a.targets(["pkg/mod.py"])
    assert "tests/test_good.py::test_good" in picked
    assert not any("test_fine" in p for p in picked), picked
    assert "map of " in capsys.readouterr().err


def test_two_tests_sharing_a_line_both_keep_their_context_under_the_nightly_settings(
    tmp_path, monkeypatch
) -> None:
    root = run_suite(
        tmp_path,
        {
            "test_first.py": "from pkg import mod\n\n\ndef test_first():\n    assert mod.good() == 1\n",
            "test_second.py": "from pkg import mod\n\n\ndef test_second():\n    assert mod.good() == 1\n",
        },
    )
    with sqlite3.connect(root / "coverage") as db:
        who = {
            c.split("|")[0]
            for (c,) in db.execute(
                "select context from context where id in (select context_id from line_bits)"
            )
        }
    assert {"tests/test_first.py::test_first", "tests/test_second.py::test_second"} <= who


def test_a_failed_test_is_selected_by_name_for_the_script_it_names(tmp_path, monkeypatch) -> None:
    """The map holds no line of a failed test, so its fix would select nothing by lines (#1400)."""
    root = run_suite(
        tmp_path,
        {
            "test_good.py": "from pkg import mod\n\n\ndef test_good():\n    assert mod.good() == 1\n",
            "test_red.py": "from pkg import mod\n\n\ndef test_red():\n    assert mod.bad() == 3\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    git("add", ".")
    git("commit", "-qm", "base")
    (root / "sha").write_text(git("rev-parse", "HEAD"))
    assert check.main(["test_map_check.py", str(root)]) == 0
    monkeypatch.setattr(a, "MAP", root)
    (tmp_path / "pkg/mod.py").write_text(MOD.replace("return 2", "return 3"))
    git("commit", "-qam", "fix bad")
    assert "tests/test_red.py::test_red" in a.targets(["pkg/mod.py"])


def test_a_map_whose_source_files_ran_no_line_fails_the_map_step(
    tmp_path, monkeypatch, capsys
) -> None:
    """Coverage lists the unexecuted files of a measured package too: a run that touched none of them is an empty map."""
    root = run_suite(
        tmp_path,
        {"test_idle.py": "def test_idle():\n    assert True\n"},
        cover=("pkg", "tests"),  # the nightly measures the test files too
    )
    monkeypatch.chdir(tmp_path)
    assert check.main(["test_map_check.py", str(root)]) == 1
    assert "map is empty" in capsys.readouterr().err
