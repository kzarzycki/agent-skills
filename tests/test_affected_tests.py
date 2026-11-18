"""The landing gate's test selection (tools/affected_tests.py): a change runs the tests it touches, and anything the
map cannot judge runs everything."""

import subprocess
from pathlib import Path

import pytest
from coverage import CoverageData

from tools import affected_tests as a


@pytest.fixture(autouse=True)
def no_map(tmp_path_factory, monkeypatch) -> None:
    """A map of the checkout's own nightly never decides these tests."""
    monkeypatch.setattr(a, "MAP", tmp_path_factory.mktemp("no-map"))


def test_a_docs_only_change_runs_only_the_repo_wide_checks() -> None:
    assert a.targets(["docs/agents/loop.md", "content/skills/x/SKILL.md"]) == a.CHEAP


def test_a_script_change_runs_the_tests_that_name_it() -> None:
    picked = a.targets(["engineering/skills/engineering-loop/scripts/gatekeeper.py"])
    assert "engineering/tests/test_approvals.py" in picked
    assert set(a.CHEAP) <= set(picked)


def test_a_changed_test_file_runs() -> None:
    assert "tests/test_affected_tests.py" in a.targets(["tests/test_affected_tests.py"])


def test_test_setup_or_no_base_runs_everything() -> None:
    assert a.targets(["pyproject.toml"]) == a.ALL
    assert a.targets(["tools/gate_workers.py"]) == a.ALL
    assert a.targets(None) == a.ALL


def test_a_conftest_anywhere_runs_everything() -> None:
    assert a.targets(["engineering/tests/conftest.py"]) == a.ALL


def test_a_non_python_file_runs_the_tests_that_name_its_file_name(tmp_path, monkeypatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_unit.py").write_text("calls run-it.sh")
    monkeypatch.chdir(tmp_path)
    assert "tests/test_unit.py" in a.targets(["scripts/run-it.sh"])
    assert "tests/test_unit.py" not in a.targets(["scripts/other.sh"])


def test_a_deleted_test_file_is_not_picked() -> None:
    assert "tests/test_gone_for_good.py" not in a.targets(["tests/test_gone_for_good.py"])


def test_e2e_tests_are_never_selected_by_name(tmp_path, monkeypatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "engineering/tests/e2e").mkdir(parents=True)
    (tmp_path / "engineering/tests/e2e/test_live.py").write_text("foo")
    (tmp_path / "engineering/tests/test_unit.py").write_text("foo")
    monkeypatch.chdir(tmp_path)
    picked = a.targets(["scripts/foo.py"])
    assert "engineering/tests/test_unit.py" in picked
    assert "engineering/tests/e2e/test_live.py" not in picked


def test_changed_returns_none_when_git_cannot_diff(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # not a repository
    assert a.changed("origin/main") is None


def test_a_changed_test_file_runs_even_when_it_does_not_name_itself(tmp_path, monkeypatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_new.py").write_text("def test_x(): pass")
    monkeypatch.chdir(tmp_path)
    assert "tests/test_new.py" in a.targets(["tests/test_new.py"])


SCRIPT = "def one():\n    return 1\n\n\ndef two():\n    # note\n    return 2\n"  # one: lines 1-2, two: 5-7


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def mapped(tmp_path, monkeypatch):
    """A repo whose map says test_one ran `one` (and test_both ran both; line 6 is a comment), and whose map commit is its first."""
    monkeypatch.chdir(tmp_path)
    git("init", "-q")
    for name, text in {
        "pkg/mod.py": SCRIPT,
        "tests/test_one.py": "from pkg import mod\n\n\ndef test_one(): mod.one()\n",
        "tests/test_both.py": "from pkg import mod\n\n\ndef test_both(): mod.one(); mod.two()\n",
    }.items():
        Path(name).parent.mkdir(exist_ok=True)
        Path(name).write_text(text)
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    monkeypatch.setattr(a, "MAP", tmp_path / ".map")
    a.MAP.mkdir()
    (a.MAP / "sha").write_text(git("rev-parse", "HEAD"))
    data = CoverageData(basename=str(a.MAP / "coverage"))
    for context, lines in {
        "": [1, 5],  # the import ran the two `def` lines
        "tests/test_one.py::test_one|run": [2],
        "tests/test_both.py::test_both|run": [2, 7],
    }.items():
        data.set_context(context)
        data.add_lines({"pkg/mod.py": lines})
    data.write()

    def edit(old: str, new: str) -> list[str]:
        Path("pkg/mod.py").write_text(SCRIPT.replace(old, new))
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "edit")
        return ["pkg/mod.py"]

    return edit


def test_a_change_to_one_function_selects_only_the_tests_that_execute_it(mapped) -> None:
    picked = a.targets(mapped("return 2", "return 22"))
    assert "tests/test_both.py::test_both" in picked
    assert not any("test_one" in p for p in picked)


def test_a_change_to_a_shared_function_selects_every_test_that_executes_it(mapped) -> None:
    picked = a.targets(mapped("return 1", "return 11"))
    assert {"tests/test_one.py::test_one", "tests/test_both.py::test_both"} <= set(picked)


def test_a_new_line_in_a_function_selects_the_tests_around_it(mapped) -> None:
    picked = a.targets(mapped("    # note\n", "    # note\n    x = 2\n"))
    assert "tests/test_both.py::test_both" in picked


def test_a_line_that_only_the_import_ran_falls_back_to_the_name_match(mapped) -> None:
    picked = a.targets(mapped("def two()", "def two(a=0)"))
    assert {"tests/test_one.py", "tests/test_both.py"} <= set(picked)
    assert "tests/test_both.py::test_both" not in picked  # the file runs whole, not by node id


def test_a_script_missing_from_the_map_falls_back_to_the_name_match(mapped) -> None:
    Path("pkg/other.py").write_text("x = 1\n")
    Path("tests/test_other.py").write_text("import other  # names other\n")
    assert "tests/test_other.py" in a.targets(["pkg/other.py"])


def test_a_map_whose_commit_is_gone_falls_back_to_the_name_match(mapped) -> None:
    (a.MAP / "sha").write_text("0" * 40)
    assert a.load_map() is None
    assert {"tests/test_one.py", "tests/test_both.py"} <= set(
        a.targets(mapped("return 2", "return 3"))
    )


def test_a_test_the_file_no_longer_has_runs_as_its_file(mapped) -> None:
    Path("tests/test_both.py").write_text("def test_renamed(): pass\n")
    assert "tests/test_both.py" in a.targets(mapped("return 2", "return 22"))


def test_a_node_id_with_a_space_runs_as_its_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("t.py").write_text("def test_p(): pass\n")
    assert a.node_files({"t.py::test_p[a b]", "t.py::test_p[a]"}) == {"t.py", "t.py::test_p[a]"}
