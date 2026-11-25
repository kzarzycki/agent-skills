"""The affected-test selection (tools/affected_tests.py): a change runs the tests it touches, and what it can't judge
exactly runs the narrowest set it can still name: zero only for a change of non-product paths (#2217)."""

import subprocess
import sys
from pathlib import Path

import pytest
from coverage import CoverageData

from tools import affected_tests as a


@pytest.fixture(autouse=True)
def no_map(tmp_path_factory, monkeypatch) -> None:
    """A map of the checkout's own nightly never decides these tests."""
    monkeypatch.setattr(a, "MAP", tmp_path_factory.mktemp("no-map"))


def test_a_skill_prose_change_no_test_reads_runs_only_the_repo_wide_checks(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_unit.py").write_text("def test_x(): pass\n")
    monkeypatch.chdir(tmp_path)
    assert a.targets(["content/skills/x/SKILL.md"]) == a.CHEAP


def test_a_loop_doc_change_runs_the_test_that_holds_its_old_path_copy() -> None:
    picked = a.targets(["loop/skills/engineering-loop/verifier.md"])
    assert {*a.CHEAP, "tests/test_old_paths.py"} <= set(picked)


def test_a_script_change_runs_the_tests_that_name_it() -> None:
    picked = a.targets(["loop/skills/engineering-loop/scripts/nightly.py"])
    assert "loop/tests/test_nightly.py" in picked
    assert set(a.CHEAP) <= set(picked)


def test_a_changed_test_file_runs() -> None:
    assert "tests/test_affected_tests.py" in a.targets(["tests/test_affected_tests.py"])


def clone_on_a_branch(tmp_path, monkeypatch) -> str:
    """A clone of an origin whose default branch `main` holds `app.py`, on a branch `work` that changes it; returns
    the merge base of the two."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    run = lambda *args, cwd=tmp_path: subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()
    run("init", "-q", "--bare", "-b", "main", str(origin))
    run("clone", "-q", str(origin), str(repo))
    for key, value in (("user.email", "loop@example.com"), ("user.name", "loop")):
        run("config", key, value, cwd=repo)
    run("checkout", "-q", "-b", "main", cwd=repo)
    (repo / "app.py").write_text("value = 1\n")
    run("add", "-A", cwd=repo)
    run("commit", "-qm", "base", cwd=repo)
    run("push", "-q", "-u", "origin", "main", cwd=repo)
    run("remote", "set-head", "origin", "main", cwd=repo)
    run("checkout", "-q", "-b", "work", cwd=repo)
    (repo / "app.py").write_text("value = 2\n")
    run("commit", "-qam", "change", cwd=repo)
    monkeypatch.chdir(repo)
    return run("merge-base", "origin/main", "HEAD", cwd=repo)


def test_a_base_git_cant_resolve_selects_against_the_merge_base(
    tmp_path, monkeypatch, capsys
) -> None:
    """#2217: a new branch's all-zeros base names no diff, so the selection diffs against the merge base with the
    default branch instead of running nothing."""
    merge_base = clone_on_a_branch(tmp_path, monkeypatch)
    assert a.resolve("0" * 40) == (merge_base, ["app.py"])
    assert f"the base {'0' * 40} is no commit here: the merge base {merge_base[:12]}" in (
        capsys.readouterr().err
    )
    assert a.resolve("origin/main") == ("origin/main", ["app.py"])  # a base that resolves is kept


def test_no_base_and_no_merge_base_fails_the_run(tmp_path, monkeypatch) -> None:
    """Not a repository: no diff and no merge base, so it can't name a set at all and the step fails."""
    monkeypatch.chdir(tmp_path)
    assert a.resolve("origin/main") is None
    done = subprocess.run(
        [sys.executable, str(Path(a.__file__).resolve()), "origin/main"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1 and done.stdout == ""
    assert "nor a merge base with the default branch" in done.stderr


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock", "mise.toml", "conftest.py"])
def test_a_build_input_runs_the_whole_suite(path, capsys) -> None:
    """#2217: the runner's config, the lock, the toolchain pins and the root conftest are read by every test."""
    assert a.targets(["docs/x.md", path]) == a.ALL
    assert f"affected-tests: {path}: a build input, which every test reads: the whole suite" in (
        capsys.readouterr().err
    )


def test_a_nested_conftest_runs_the_test_files_under_its_directory(
    tmp_path, monkeypatch, capsys
) -> None:
    """#1460: a conftest.py below the root sets up only the tests under its directory."""
    monkeypatch.chdir(tmp_path)
    for name in (
        "pkg/tests/unit/conftest.py",
        "pkg/tests/unit/test_a.py",
        "pkg/tests/unit/deep/test_b.py",
        "pkg/tests/test_beside.py",
        "tests/test_root.py",
    ):
        Path(name).parent.mkdir(parents=True, exist_ok=True)
        Path(name).write_text("def test_x(): pass\n")
    monkeypatch.setattr(a, "ALL", ["tests", "pkg/tests"])
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets(["pkg/tests/unit/conftest.py"]) == [
        "pkg/tests/unit/deep/test_b.py",
        "pkg/tests/unit/test_a.py",
    ]
    assert "pkg/tests/unit/conftest.py: test setup: the 2 test files under pkg/tests/unit" in (
        capsys.readouterr().err
    )


def test_a_test_named_plugin_outside_the_suites_runs_the_tests_that_name_it() -> None:
    """`tools/test_map_plugin.py` holds no tests: its own tests are found by the name match."""
    assert "tests/test_test_map_plugin.py" in a.targets(["tools/test_map_plugin.py"])


def test_a_non_python_file_runs_the_tests_that_name_its_file_name(tmp_path, monkeypatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_unit.py").write_text("calls run-it.sh")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets(["scripts/run-it.sh"]) == ["tests/test_unit.py"]
    (tmp_path / "pkg/tests").mkdir(parents=True)
    (tmp_path / "pkg/tests/test_pkg.py").write_text("calls other.sh")
    monkeypatch.setattr(a, "ALL", ["tests", "pkg/tests"])
    assert a.targets(["scripts/other.sh"]) == ["pkg/tests/test_pkg.py"]


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
    assert "affected-tests: pyproject.toml: a build input" in capsys.readouterr().err


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
    """#1872, kept by #2217: a near-whole selection runs as picked, never as the whole suite, which only the nightly runs."""
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


SCRIPT_UNDER_PACKAGE = "omnigent/skills/omnigent-agents/scripts/omnigent_agent.py"
WAKE_TEST = "omnigent/tests/test_omnigent_agent_wake.py"


def test_a_package_script_nothing_names_selects_the_packages_whole_test_dir(
    monkeypatch, tmp_path
) -> None:
    """#2157: a changed script under a package's `scripts/` that no test names or ran falls back to that package's tests."""
    monkeypatch.chdir(tmp_path)
    for name in (
        "omnigent/skills/s/scripts/lonely.py",
        "omnigent/tests/test_a.py",
        "omnigent/tests/test_b.py",
    ):
        Path(name).parent.mkdir(parents=True, exist_ok=True)
        Path(name).write_text("")
    monkeypatch.setattr(a, "ALL", ["omnigent/tests"])
    assert a.targets(["omnigent/skills/s/scripts/lonely.py"]) == sorted(
        [*a.CHEAP, "omnigent/tests/test_a.py", "omnigent/tests/test_b.py"]
    )


def test_a_file_no_test_names_runs_its_package_or_directory_tests(
    monkeypatch, tmp_path, capsys
) -> None:
    """#2217: a file nothing names, outside `scripts/` and `src/` too, runs the tests of its package, and a file in no
    package the tests of its nearest directory that has some, the root suite last."""
    monkeypatch.chdir(tmp_path)
    for name in (
        "omnigent/skills/s/lonely.yml",
        "omnigent/tests/test_a.py",
        "tests/fixtures/data/lonely.json",
        "tests/fixtures/test_fix.py",
        "tests/test_root.py",
        "tools/lonely.sh",
    ):
        Path(name).parent.mkdir(parents=True, exist_ok=True)
        Path(name).write_text("")
    monkeypatch.setattr(a, "ALL", ["tests", "omnigent/tests"])
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets(["omnigent/skills/s/lonely.yml"]) == ["omnigent/tests/test_a.py"]
    assert a.targets(["tests/fixtures/data/lonely.json"]) == ["tests/fixtures/test_fix.py"]
    assert a.targets(["tools/lonely.sh"]) == ["tests/fixtures/test_fix.py", "tests/test_root.py"]
    assert "tools/lonely.sh: no test names it: the 2 test files under tests" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize(
    "paths",
    [
        ["docs/notes.md"],
        ["gatekeeper/changelog.d/9999.md", "README.md", "loop/CHANGELOG.md"],
        [".claude/rules/x.md", ".agents/skills/s/SKILL.md", "apm.yml", "apm.lock.yaml"],
    ],
)
def test_a_change_of_only_non_product_paths_selects_zero_and_says_so(
    tmp_path, monkeypatch, capsys, paths
) -> None:
    """#2217: zero only when every changed path is non-product and no test reads it, with its one line."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_unit.py").write_text("def test_x(): pass\n")
    monkeypatch.chdir(tmp_path)
    assert a.targets(paths) == []
    assert "affected-tests: 0 selected: non-product" in capsys.readouterr().err


def test_a_non_product_path_beside_a_product_one_runs_the_product_ones_tests(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_unit.py").write_text("calls run-it.sh")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets(["docs/notes.md", "scripts/run-it.sh"]) == ["tests/test_unit.py"]


def test_a_non_product_path_a_test_reads_runs_that_test(tmp_path, monkeypatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_layers.py").write_text('LAYERS = ROOT / "docs" / "layers.md"\n')
    (tmp_path / "tests/test_other.py").write_text("def test_x(): pass\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets(["docs/layers.md"]) == ["tests/test_layers.py"]


def test_a_file_a_test_reads_by_path_runs_that_test(tmp_path, monkeypatch, capsys) -> None:
    """#2216: a test that opens a doc by its directory and file name, or by its whole path, is selected for it;
    one naming only the file name, or only the directory, is not."""
    (tmp_path / "pkg/tests").mkdir(parents=True)
    tests = {
        "pkg/tests/test_by_parts.py": 'LOOP = ROOT / "skills" / "engineering-loop"\n(LOOP / "verifier.md").read_text()\n',
        "pkg/tests/test_by_path.py": 'Path("pkg/skills/engineering-loop/verifier.md")\n',
        "pkg/tests/test_name_only.py": 'Path("other") / "verifier.md"\n',
        "pkg/tests/test_dir_only.py": 'ROOT / "engineering-loop" / "lead.md"\n',
        "pkg/tests/test_unquoted.py": "# a comment naming pkg/skills/engineering-loop/verifier.md as it reads it\n",
        "pkg/tests/test_not_segments.py": 'NOTE = "my-engineering-loop-x verifier.md.orig"\n',
    }
    for name, text in tests.items():
        (tmp_path / name).write_text(text)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "ALL", ["pkg/tests"])
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets(["pkg/skills/engineering-loop/verifier.md"]) == [
        "pkg/tests/test_by_parts.py",
        "pkg/tests/test_by_path.py",
        "pkg/tests/test_unquoted.py",
    ]
    assert "verifier.md: 3 test files read it by path" in capsys.readouterr().err


def test_a_verifier_md_change_selects_the_loop_test_that_reads_it() -> None:
    """#2216's miss, on this checkout: test_engineering_loop.py reads `(LOOP / "verifier.md")`."""
    assert "loop/tests/test_engineering_loop.py" in a.targets(
        ["loop/skills/engineering-loop/verifier.md"]
    )


def test_a_change_to_omnigent_agent_selects_the_wake_test() -> None:
    assert WAKE_TEST in a.targets([SCRIPT_UNDER_PACKAGE])


def test_a_mapped_package_script_whose_changed_lines_no_test_ran_selects_the_packages_tests(
    monkeypatch, tmp_path
) -> None:
    """The map measures the script but no test ran the changed line: the package's tests run, wake test included."""
    monkeypatch.setattr(a, "MAP", tmp_path / ".map")
    a.MAP.mkdir()
    (a.MAP / "sha").write_text(git("rev-parse", "HEAD"))
    (a.MAP / "skipped").write_text(
        ""
    )  # a map with a skip list: no test is picked by name beside it
    data = CoverageData(basename=str(a.MAP / "coverage"))
    data.set_context("omnigent/tests/test_other.py::test_x|run")
    data.add_lines({SCRIPT_UNDER_PACKAGE: [1]})
    data.write()
    monkeypatch.setattr(a, "load_map", lambda: (git("rev-parse", "HEAD"), data))
    monkeypatch.setattr(a, "executed_by", lambda *args: set())
    assert WAKE_TEST in a.targets([SCRIPT_UNDER_PACKAGE])


def package(tmp_path, monkeypatch, named: str = "") -> None:
    """A repo with one package: a script `scripts/unique_script.py`, `tests/test_ran.py` (names `named`) and
    `tests/test_other.py` (names nothing)."""
    monkeypatch.chdir(tmp_path)
    for name, text in {
        "omnigent/skills/s/scripts/unique_script.py": "def f(): pass\n",
        "omnigent/tests/test_ran.py": f"{named}\n\n\ndef test_x(): pass\n",
        "omnigent/tests/test_other.py": "def test_y(): pass\n",
    }.items():
        Path(name).parent.mkdir(parents=True, exist_ok=True)
        Path(name).write_text(text)
    monkeypatch.setattr(a, "ALL", ["omnigent/tests"])
    monkeypatch.setattr(a, "CHEAP", [])


def test_a_script_a_test_names_selects_only_that_test_never_the_package(
    tmp_path, monkeypatch
) -> None:
    package(tmp_path, monkeypatch, named="import unique_script")
    assert a.targets(["omnigent/skills/s/scripts/unique_script.py"]) == [
        "omnigent/tests/test_ran.py"
    ]


def test_a_mapped_script_a_test_ran_selects_only_that_test_never_the_package(
    tmp_path, monkeypatch
) -> None:
    package(tmp_path, monkeypatch)
    monkeypatch.setattr(a, "MAP", tmp_path / ".map")
    monkeypatch.setattr(a, "load_map", lambda: ("sha", object()))
    monkeypatch.setattr(a, "executed_by", lambda *args: {"omnigent/tests/test_ran.py::test_x"})
    assert a.targets(["omnigent/skills/s/scripts/unique_script.py"]) == [
        "omnigent/tests/test_ran.py::test_x"
    ]


def test_a_mapped_script_whose_test_the_map_skipped_selects_that_test_never_the_package(
    tmp_path, monkeypatch
) -> None:
    package(tmp_path, monkeypatch, named="import unique_script")
    monkeypatch.setattr(a, "MAP", tmp_path / ".map")
    a.MAP.mkdir()
    (a.MAP / "skipped").write_text("omnigent/tests/test_ran.py::test_x\n")
    monkeypatch.setattr(a, "load_map", lambda: ("sha", object()))
    monkeypatch.setattr(a, "executed_by", lambda *args: set())
    assert a.targets(["omnigent/skills/s/scripts/unique_script.py"]) == [
        "omnigent/tests/test_ran.py::test_x"
    ]


def test_a_non_product_file_a_test_names_by_its_file_name_runs_that_test(
    tmp_path, monkeypatch
) -> None:
    """A non-product path a test names (by file name, not its path) is no longer zero: that test runs."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_settings.py").write_text(
        "loads settings.json from the agent's folder\n"
    )
    (tmp_path / "tests/test_other.py").write_text("def test_x(): pass\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(a, "CHEAP", [])
    assert a.targets([".claude/settings.json"]) == ["tests/test_settings.py"]
