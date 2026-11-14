"""approvals_harness.py: every autouse fixture of test_approvals.py is exported and imported (#850)."""

from __future__ import annotations

import ast
from pathlib import Path

import approvals_harness

HERE = Path(__file__).parent


def autouse_fixtures(path: Path) -> set[str]:
    """The names of the functions a module decorates with `@pytest.fixture(autouse=True)`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and any(
                    k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value
                    for k in decorator.keywords
                ):
                    found.add(node.name)
    return found


def harness_imports(path: Path) -> set[str]:
    """The names a module imports from approvals_harness."""
    return {
        alias.name
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ImportFrom) and node.module == "approvals_harness"
        for alias in node.names
    }


def test_the_harness_exports_every_autouse_fixture_of_test_approvals() -> None:
    """A fixture test_approvals.py runs every test under, and the harness leaves out, leaks between a new
    module's tests; AUTOUSE lists them all, and the harness exports each."""
    assert set(approvals_harness.AUTOUSE) == autouse_fixtures(HERE / "test_approvals.py")
    assert set(approvals_harness.AUTOUSE) <= set(approvals_harness.__all__)
    for name in approvals_harness.AUTOUSE:
        assert callable(getattr(approvals_harness, name))


def test_each_module_of_approvals_tests_imports_every_autouse_fixture() -> None:
    modules = sorted(HERE.glob("test_approvals_*.py"))
    assert modules
    for module in modules:
        if module.name != Path(__file__).name:
            missing = set(approvals_harness.AUTOUSE) - harness_imports(module)
            assert not missing, f"{module.name} lacks {sorted(missing)}"
