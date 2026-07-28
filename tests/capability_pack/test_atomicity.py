from __future__ import annotations

from pathlib import Path

import yaml
from conftest import OWNED_SKILLS

from tools.capability_pack.qualify import QualificationError, qualify


def _owned_bytes(package: Path) -> dict[str, bytes]:
    return {
        path.relative_to(package).as_posix(): path.read_bytes()
        for name in OWNED_SKILLS
        for path in (package / "skills" / name).rglob("*")
        if path.is_file()
    }


def test_update_preserves_all_owned_skill_trees(package: Path, fake_vendir: Path) -> None:
    """Catch staging or promotion rewriting any repository-owned skill."""
    before = _owned_bytes(package)

    qualify(package, "update")

    assert _owned_bytes(package) == before


def test_check_detects_direct_edit_without_mutating_package(
    package: Path, fake_vendir: Path
) -> None:
    """Catch accepting a committed imported file that locked reproduction cannot produce."""
    edited = package / "skills" / "alpha" / "SKILL.md"
    edited.write_text("# Locally edited alpha\n")
    before = edited.read_bytes()

    try:
        qualify(package, "locked")
    except QualificationError as error:
        assert "reproduction differs" in str(error)
    else:
        raise AssertionError("check must reject direct edits")

    assert edited.read_bytes() == before


def test_check_ignores_legacy_import_timestamp(package: Path, fake_vendir: Path) -> None:
    """Catch volatile provenance metadata making identical content appear changed."""
    path = package / "provenance.yml"
    data = yaml.safe_load(path.read_text())
    data["imported_at"] = "2025-01-01T00:00:00Z"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = qualify(package, "locked")

    assert result.changed is False


def test_failed_non_live_package_test_leaves_package_unchanged(
    package: Path, fake_vendir: Path
) -> None:
    """Catch replacing the package before its staged contract tests pass."""
    tests = package / "tests"
    tests.mkdir()
    (tests / "test_contract.py").write_text("def test_contract():\n    assert False\n")
    before = (package / "skills" / "alpha" / "SKILL.md").read_bytes()

    try:
        qualify(package, "update")
    except QualificationError as error:
        assert "non-live package tests failed" in str(error)
    else:
        raise AssertionError("failed staged package tests must stop replacement")

    assert (package / "skills" / "alpha" / "SKILL.md").read_bytes() == before
