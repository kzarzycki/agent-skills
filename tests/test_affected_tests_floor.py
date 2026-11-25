"""#2445: in the merge queue a build input selects a floor (`select.build_inputs_in_queue: floor`), not the whole suite."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import affected_tests as a


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


LOCK = 'version = 1\n\n[[package]]\nname = "{pkg}"\nversion = "{version}"\n\n[[package]]\nname = "other"\nversion = "1"\n'


@pytest.fixture
def lock_bump(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """A repo with `uv.lock` and `src/app.py` changed in one PR: `coverage` bumped, the app edited."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        a.importlib.metadata,
        "packages_distributions",
        lambda: {"fakepkgz": ["fakepkgz"], "yaml": ["PyYAML"]},
    )
    monkeypatch.setattr(a, "MAP", tmp_path / ".nomap")
    monkeypatch.setattr(a, "ALL", ["tests"])
    monkeypatch.setattr(a, "CHEAP", [])
    git("init", "-q")
    files = {
        "uv.lock": LOCK.format(pkg="fakepkgz", version="1"),
        "src/app.py": "x = 1\n",
        "tests/test_app.py": "import app\n\n\ndef test_a(): pass\n",
        "tests/test_pkg.py": "import fakepkgz\n\n\ndef test_p(): pass\n",
        "tests/test_other.py": "import other\n\n\ndef test_o(): pass\n",
    }
    for name, text in files.items():
        Path(name).parent.mkdir(exist_ok=True)
        Path(name).write_text(text)
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    Path("uv.lock").write_text(LOCK.format(pkg="fakepkgz", version="2"))
    Path("src/app.py").write_text("x = 2\n")
    git("commit", "-qam", "bump")
    return [base, "uv.lock", "src/app.py"]


def test_under_floor_a_lockfile_bump_selects_the_changed_files_tests_and_the_importers(
    lock_bump: list[str],
) -> None:
    base, *files = lock_bump
    picked = a.targets(files, base, build_inputs="floor")
    assert picked == [
        "tests/test_app.py",
        "tests/test_pkg.py",
    ]  # not test_other: its package didn't move


def test_under_full_a_lockfile_bump_selects_the_whole_suite(lock_bump: list[str]) -> None:
    base, *files = lock_bump
    assert a.targets(files, base, build_inputs="full") == a.ALL


def test_the_queue_reads_the_policy_and_runs_the_whole_suite_unless_a_project_opts_into_floor(
    lock_bump: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, *files = lock_bump
    assert a.targets(files, base) == a.ALL  # a PR head, not the queue: as before
    monkeypatch.setenv("GITHUB_HEAD_REF", "mergify/merge-queue/abc")
    assert (
        a.targets(files, base) == a.ALL
    )  # no policy: `full` until a project's nightly records durations
    Path("docs/agents").mkdir(parents=True)
    Path("docs/agents/gatekeeper.md").write_text("select:\n  build_inputs_in_queue: floor\n")
    assert a.targets(files, base) == ["tests/test_app.py", "tests/test_pkg.py"]
    Path("docs/agents/gatekeeper.md").write_text("select:\n  build_inputs_in_queue: full\n")
    assert a.targets(files, base) == a.ALL


def test_another_build_input_adds_nothing_in_the_queue(
    lock_bump: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, *_ = lock_bump
    monkeypatch.setenv("GATE_IN_QUEUE", "1")
    Path("docs/agents").mkdir(parents=True)
    Path("docs/agents/gatekeeper.md").write_text("select:\n  build_inputs_in_queue: floor\n")
    assert a.targets(["pyproject.toml", "src/app.py"], base) == ["tests/test_app.py"]


def test_an_import_name_that_differs_from_the_package_name_is_found(lock_bump: list[str]) -> None:
    assert a.import_names("pyyaml") == {"yaml"}


def test_a_moved_package_with_no_import_name_selects_the_whole_suite(
    lock_bump: list[str],
) -> None:
    base, *files = lock_bump
    Path("uv.lock").write_text(
        LOCK.format(pkg="fakepkgz", version="2")
        + '\n[[package]]\nname = "mystery"\nversion = "1"\n'
    )
    git("commit", "-qam", "add mystery")
    assert a.targets(files, base, build_inputs="floor") == a.ALL
