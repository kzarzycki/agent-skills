from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tools.capability_pack.qualify import BreakingDriftError, QualificationError, qualify


def test_new_upstream_skill_is_reported_and_promoted(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch silently importing a new skill without update evidence."""
    beta = upstream / "skills" / "engineering" / "beta"
    beta.mkdir()
    (beta / "SKILL.md").write_text("# Beta\n")

    result = qualify(package, "update")

    assert result.added_skills == ("beta",)
    assert (package / "skills" / "beta" / "SKILL.md").read_text() == "# Beta\n"


def test_removed_upstream_skill_is_breaking_drift(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch treating an upstream removal or rename as an ordinary update."""
    shutil.rmtree(upstream / "skills" / "engineering" / "alpha")

    with pytest.raises(
        BreakingDriftError, match=r"alpha.*1111111111111111111111111111111111111111"
    ):
        qualify(package, "update")


def test_missing_recorded_legal_file_fails_qualification(package: Path, fake_vendir: Path) -> None:
    """Catch publishing a reconstructed payload without its required license."""
    (package / "LICENSES" / "mattpocock-skills-LICENSE").unlink()

    with pytest.raises(QualificationError, match="legal file"):
        qualify(package, "locked")


def test_owned_skill_collision_stops_promotion(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch an upstream skill replacing repository-owned behavior."""
    colliding = upstream / "skills" / "engineering" / "context-extractor"
    colliding.mkdir()
    (colliding / "SKILL.md").write_text("# Upstream collision\n")
    owned = (package / "skills" / "context-extractor" / "SKILL.md").read_bytes()

    with pytest.raises(QualificationError, match="context-extractor"):
        qualify(package, "update")

    assert (package / "skills" / "context-extractor" / "SKILL.md").read_bytes() == owned
