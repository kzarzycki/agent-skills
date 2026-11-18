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
