"""The affected-test selection (tools/affected_tests.py): a change runs the tests it touches, and anything it can't
judge runs nothing and says so, never the whole suite (#1872)."""

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
    picked = a.targets(["gatekeeper/skills/gatekeeper/scripts/gatekeeper.py"])
    assert "gatekeeper/tests/test_approvals.py" in picked
    assert set(a.CHEAP) <= set(picked)


def test_a_changed_test_file_runs() -> None:
    assert "tests/test_affected_tests.py" in a.targets(["tests/test_affected_tests.py"])


def test_no_base_cant_tell_and_runs_nothing(capsys) -> None:
    """#1872: the "can't tell" case runs no test at all, and says so."""
    assert a.targets(None, "origin/main") == []
    assert "affected-tests: nothing: no diff against origin/main" in capsys.readouterr().err


def test_test_setup_alone_runs_only_the_repo_wide_checks(capsys) -> None:
    """#1872: the map can't judge test setup, so it adds nothing, never the whole suite."""
    assert a.targets(["pyproject.toml"]) == a.CHEAP
    assert a.targets(["engineering/tests/conftest.py"]) == a.CHEAP
    assert "engineering/tests/conftest.py: nothing, it is test setup" in capsys.readouterr().err


def test_test_setup_beside_a_script_runs_what_the_script_selects() -> None:
    assert a.targets(["pyproject.toml", "tools/failed_tests.py"]) == a.targets(
        ["tools/failed_tests.py"]
    )
    assert "tests/test_failed_tests.py" in a.targets(["tools/failed_tests.py"])


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


def test_a_parametrized_id_with_a_space_runs_as_its_function(tmp_path, monkeypatch) -> None:
    """#1609: the gate splits targets on whitespace, so `test_p[a b]` runs as `test_p`, every parameter, not its file."""
    monkeypatch.chdir(tmp_path)
    Path("t.py").write_text("def test_p(): pass\n")
    assert a.node_files({"t.py::test_p[a b]", "t.py::test_p[a]"}) == {
        "t.py::test_p",
        "t.py::test_p[a]",
    }


def land_on_main(name: str, text: str) -> str:
    """A commit after the map's, standing for main moving on; returns it as the PR's base."""
    Path(name).write_text(text)
    git("add", name)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "main moves")
    return git("rev-parse", "HEAD")


def test_a_test_that_landed_after_the_map_runs_by_name(mapped) -> None:
    base = land_on_main("tests/test_new.py", "from pkg import mod\n\n\ndef test_new(): mod.two()\n")
    picked = a.targets(mapped("return 2", "return 22"), base)
    assert "tests/test_new.py" in picked
    assert "tests/test_both.py::test_both" in picked


def test_a_script_that_changed_on_main_after_the_map_runs_by_name(mapped) -> None:
    base = land_on_main("pkg/mod.py", SCRIPT + "\n\ndef three():\n    return 3\n")
    Path("pkg/mod.py").write_text(Path("pkg/mod.py").read_text().replace("return 3", "return 33"))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "pr")
    picked = a.targets(["pkg/mod.py"], base)
    assert {"tests/test_one.py", "tests/test_both.py"} <= set(picked)


def test_a_line_run_in_process_and_in_a_subprocess_falls_back_to_the_name_match(mapped) -> None:
    data = CoverageData(basename=str(a.MAP / "coverage"))
    data.read()
    data.set_context("")  # what a subprocess records
    data.add_lines({"pkg/mod.py": [7]})
    data.write()
    picked = a.targets(mapped("return 2", "return 22"))
    assert {"tests/test_one.py", "tests/test_both.py"} <= set(picked)


def test_a_corrupt_map_falls_back_to_the_name_match(mapped) -> None:
    (a.MAP / "coverage").write_text("garbage")
    assert a.load_map() is None
    assert {"tests/test_one.py", "tests/test_both.py"} <= set(a.targets(mapped("return 2", "x")))


def test_a_test_that_can_skip_runs_by_name_beside_the_map(mapped) -> None:
    Path("tests/test_skips.py").write_text(
        "import pytest\nfrom pkg import mod\n\n\n@pytest.mark.skipif(True, reason='x')\ndef test_s(): mod.two()\n"
    )
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "skips")
    picked = a.targets(mapped("return 2", "return 22"))
    assert "tests/test_skips.py" in picked


def test_a_changed_line_no_test_ran_selects_only_the_cheap_checks(mapped) -> None:
    assert a.targets(mapped("\n\n\ndef two", "\n# c\n\ndef two")) == a.CHEAP


def test_stderr_names_the_rule_behind_each_target(mapped, capsys) -> None:
    """#1609: a slow run's log says why: the map, a test, a name match and why, or everything and which file."""
    a.targets(mapped("return 1", "return 11") + ["tests/test_one.py", "notes.md"])
    said = capsys.readouterr().err
    assert "affected-tests: map of " in said
    assert "affected-tests: pkg/mod.py: 2 tests from the map" in said
    assert "affected-tests: tests/test_one.py: a changed test" in said
    a.targets(["pyproject.toml"])
    assert "affected-tests: pyproject.toml: nothing, it is test setup" in capsys.readouterr().err


def test_a_new_function_beside_a_def_line_selects_only_the_tests_around_it(mapped) -> None:
    """#1609: a function inserted after `one` borders `def two` (line 5), which only the import ran; that line is not
    changed, so it doesn't send the whole file to the name match."""
    picked = a.targets(mapped("\n\ndef two()", "\n\ndef new():\n    return 0\n\n\ndef two()"))
    assert "tests/test_one.py" not in picked and "tests/test_both.py" not in picked


def test_a_map_with_a_skip_list_adds_only_the_skipped_tests(mapped) -> None:
    """#1609: a test file that can skip no longer runs whole beside the map: only the tests the map's run skipped do."""
    Path("tests/test_skips.py").write_text(
        "import pytest\nfrom pkg import mod\n\n\n@pytest.mark.skipif(True, reason='x')\ndef test_s(): mod.two()\n\n\n"
        "def test_kept(): pass\n"
    )
    (a.MAP / "skipped").write_text("tests/test_skips.py::test_s\n")
    picked = a.targets(mapped("return 2", "return 22"))
    assert "tests/test_skips.py::test_s" in picked
    assert "tests/test_skips.py" not in picked


@pytest.mark.parametrize(
    "inserted",
    [
        "@staticmethod\n",
        "LIMIT = 0\n\n\n",
        "import os\n\n\n",
        "def new():\n    return 0\n\n\nLIMIT = 0\n\n\n",
    ],
    ids=["decorator", "constant", "import", "def then constant"],
)
def test_code_that_runs_at_import_beside_a_def_line_falls_back_to_the_name_match(
    mapped, inserted
) -> None:
    """Verifier F2 on #1617: only a whole new undecorated def or class leaves the import run of the line beside it out."""
    picked = a.targets(mapped("def two()", inserted + "def two()"))
    assert {"tests/test_one.py", "tests/test_both.py"} <= set(picked)


def test_a_class_test_id_with_a_space_runs_as_its_method(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("t.py").write_text("class TestK:\n    def test_m(self): pass\n")
    assert a.node_files({"t.py::TestK::test_m[a b]"}) == {"t.py::TestK::test_m"}


def suite(root, names: int, naming: int) -> None:
    """A suite of `names` test files, the first `naming` of them naming `tool`."""
    (root / "tests").mkdir(parents=True)
    for n in range(names):
        (root / "tests" / f"test_{n:02}.py").write_text(
            "# uses tool\n" if n < naming else "# other\n"
        )
    (root / "tool.py").write_text("")


def test_a_selection_of_over_half_the_test_files_runs_only_them(monkeypatch, tmp_path) -> None:
    """#1872: a near-whole selection runs as picked, never as the whole suite, which only the nightly runs."""
    suite(tmp_path, 20, 11)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "ALL", ["tests"])
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets(["tool.py"]) == [f"tests/test_{n:02}.py" for n in range(11)]


def test_the_cheap_checks_and_a_changed_e2e_file_are_picked_as_they_are(
    monkeypatch, tmp_path
) -> None:
    """Half the suite named, plus a cheap check and a changed e2e test, all picked as they are."""
    suite(tmp_path, 20, 10)
    (tmp_path / "tests" / "test_skill_x.py").write_text("# uses tool\n")
    (tmp_path / "tests" / "e2e").mkdir()
    (tmp_path / "tests" / "e2e" / "test_live.py").write_text("# other\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "ALL", ["tests"])
    monkeypatch.setattr(a, "CHEAP", ["tests/test_skill_x.py"])
    picked = a.targets(["tool.py", "tests/e2e/test_live.py"])
    named = [f"tests/test_{n:02}.py" for n in range(10)]
    assert picked == sorted([*named, "tests/test_skill_x.py", "tests/e2e/test_live.py"])
