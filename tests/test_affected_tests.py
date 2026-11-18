"""The landing gate's test selection (tools/affected_tests.py): a change runs the tests it touches, and anything the
map cannot judge runs everything."""

from tools import affected_tests as a


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
