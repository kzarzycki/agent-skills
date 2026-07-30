from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import OWNED_SKILLS

from tools.capability_pack.qualify import QualificationError, qualify


def _owned_state(package: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(package).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o777)
        for name in OWNED_SKILLS
        for path in (package / "skills" / name).rglob("*")
        if path.is_file()
    }


def test_update_preserves_all_owned_skill_trees(package: Path, fake_vendir: Path) -> None:
    """Catch staging or promotion rewriting any repository-owned skill."""
    executable = package / "skills" / "audit-third-party-software" / "run.sh"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    before = _owned_state(package)

    qualify(package, "update")

    assert _owned_state(package) == before


def test_update_then_locked_repeat_converges(package: Path, fake_vendir: Path) -> None:
    """Catch one-lock reproduction changing payload, provenance, or source identity."""
    qualify(package, "update")
    before = _owned_state(package)

    result = qualify(package, "locked")

    assert result.changed is False
    assert _owned_state(package) == before


def test_staged_package_tests_receive_complete_provenance(package: Path, fake_vendir: Path) -> None:
    """Catch running package contracts before proposed provenance is generated."""
    tests = package / "tests"
    tests.mkdir()
    (tests / "test_provenance.py").write_text(
        "from pathlib import Path\n"
        "import yaml\n\n"
        "def test_complete_provenance():\n"
        "    package = Path(__file__).parents[1]\n"
        "    data = yaml.safe_load((package / 'provenance.yml').read_text())\n"
        "    assert data['source_commit'] == '" + "2" * 40 + "'\n"
        "    assert data['included_skills'] == [\n"
        "        'alpha', 'grilling', 'setup-engineering-workflow-for-apm'\n"
        "    ]\n"
        "    assert data['source_files']\n"
        "    assert data['license_files']\n"
        "    assert data['output_files']\n"
    )

    qualify(package, "update")


def test_staged_package_tests_receive_explicit_boundary_signal(
    package: Path, fake_vendir: Path
) -> None:
    """Catch package-only tests inferring their boundary from missing repository files."""
    tests = package / "tests"
    tests.mkdir()
    (tests / "test_stage_boundary.py").write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "def test_stage_boundary():\n"
        "    package = Path(__file__).parents[1].resolve()\n"
        "    assert Path(os.environ['CAPABILITY_PACK_QUALIFICATION_STAGE_ROOT']) == package\n"
    )

    qualify(package, "update")


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


@pytest.mark.parametrize(
    ("source_mode", "committed_mode"),
    [(0o644, 0o755), (0o755, 0o644)],
)
def test_check_detects_imported_executable_mode_drift(
    package: Path,
    upstream: Path,
    fake_vendir: Path,
    source_mode: int,
    committed_mode: int,
) -> None:
    """Catch accepting a 0644/0755 drift when imported bytes are unchanged."""
    source = upstream / "skills" / "engineering" / "alpha" / "SKILL.md"
    committed = package / "skills" / "alpha" / "SKILL.md"
    source.chmod(source_mode)
    committed.chmod(committed_mode)

    with pytest.raises(
        QualificationError, match="reproduction differs from committed imported files"
    ):
        qualify(package, "locked")

    assert committed.stat().st_mode & 0o777 == committed_mode


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


@pytest.mark.parametrize("mode", ["update", "locked"])
def test_summary_path_inside_package_is_rejected_without_mutation(
    package: Path, fake_vendir: Path, mode: str
) -> None:
    """Catch update replacement or check mode writing through an in-package summary."""
    before = (package / "skills" / "alpha" / "SKILL.md").read_bytes()
    summary = package / "qualification-summary.txt"

    with pytest.raises(QualificationError, match="summary path must be outside"):
        qualify(package, mode, summary)

    assert not summary.exists()
    assert (package / "skills" / "alpha" / "SKILL.md").read_bytes() == before


def test_external_summary_survives_update_swap(
    package: Path, fake_vendir: Path, tmp_path: Path
) -> None:
    """Catch placing update evidence in the staged tree that is lost during rename."""
    summary = tmp_path / "summary.txt"

    qualify(package, "update", summary)

    assert summary.is_file()
    assert "Proposed source commit: " + "2" * 40 in summary.read_text()


@pytest.mark.parametrize(
    "field", ["excluded_skills", "source_mappings", "source_files", "output_files"]
)
def test_locked_mode_compares_every_provenance_field(
    package: Path, fake_vendir: Path, field: str
) -> None:
    """Catch accepting committed provenance that does not match reconstruction."""
    path = package / "provenance.yml"
    data = yaml.safe_load(path.read_text())
    if field == "excluded_skills":
        data[field].append("ghost-skill")
    elif field == "source_mappings":
        data[field][0]["destination_path"] = "skills/ghost-skill"
    else:
        data[field][0]["sha256"] = "f" * 64
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(QualificationError, match="committed provenance"):
        qualify(package, "locked")
