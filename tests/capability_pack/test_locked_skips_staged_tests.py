from __future__ import annotations

from pathlib import Path

import pytest

from tools.capability_pack.qualify import QualificationError, qualify

NOT_RUN = (
    "Non-live test: NOT RUN (locked: the stage matches the committed package, "
    "which mise run test covers)"
)


def _failing_package_test(package: Path) -> None:
    tests = package / "tests"
    tests.mkdir()
    (tests / "test_contract.py").write_text("def test_contract():\n    assert False\n")


def test_locked_mode_reports_the_staged_tests_as_not_run(
    package: Path, fake_vendir: Path, tmp_path: Path
) -> None:
    """Catch a locked check that runs the package tests the test gate runs again."""
    _failing_package_test(package)
    summary = tmp_path / "summary.txt"

    result = qualify(package, "locked", summary)

    assert result.changed is False
    assert NOT_RUN in summary.read_text()


@pytest.mark.parametrize("mode", ["update", "regenerate"])
def test_update_and_regenerate_still_run_the_staged_tests(
    package: Path, fake_vendir: Path, mode: str
) -> None:
    """Catch skipping the staged tests where the stage differs from the checkout."""
    _failing_package_test(package)

    with pytest.raises(QualificationError, match="non-live package tests failed"):
        qualify(package, mode)


def test_locked_mode_validates_the_reproduction_before_anything_else(
    package: Path, fake_vendir: Path
) -> None:
    """Catch a drifted leaf passing because the staged tests no longer run."""
    _failing_package_test(package)
    leaf = package / "skills" / "alpha" / "SKILL.md"
    leaf.write_text(leaf.read_text() + "drift\n")

    with pytest.raises(
        QualificationError, match="reproduction differs from committed imported files"
    ):
        qualify(package, "locked")
