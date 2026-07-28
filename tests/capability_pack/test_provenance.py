from __future__ import annotations

from pathlib import Path

from tools.capability_pack.model import FileHash, Provenance
from tools.capability_pack.provenance import hash_files, load_provenance, write_provenance
from tools.capability_pack.summary import render_summary


def _provenance(commit: str, *, skills: tuple[str, ...] = ("alpha",)) -> Provenance:
    return Provenance(
        source_commit=commit,
        included_skills=skills,
        excluded_skills=("setup-matt-pocock-skills",),
        source_files=(FileHash("source/a", "a" * 64),),
        patch_files=(FileHash("patches/a.patch", "b" * 64),),
        license_files=(FileHash("LICENSES/LICENSE", "c" * 64),),
        output_files=(FileHash("skills/alpha/SKILL.md", "d" * 64),),
    )


def test_provenance_round_trip_is_stable_and_has_no_timestamp(tmp_path: Path) -> None:
    """Catch nondeterministic provenance or loss of typed manifest fields."""
    path = tmp_path / "provenance.yml"
    expected = _provenance("1" * 40)

    write_provenance(path, expected)
    first = path.read_bytes()
    write_provenance(path, expected)

    assert path.read_bytes() == first
    assert b"timestamp" not in first
    assert b"imported_at" not in first
    assert load_provenance(path) == expected


def test_hash_files_uses_sorted_posix_paths_and_file_bytes(tmp_path: Path) -> None:
    """Catch platform-order or metadata-dependent file manifests."""
    (tmp_path / "z.txt").write_text("z")
    nested = tmp_path / "a"
    nested.mkdir()
    (nested / "b.txt").write_text("b")

    hashes = hash_files(tmp_path, [tmp_path / "z.txt", nested / "b.txt"])

    assert [item.path for item in hashes] == ["a/b.txt", "z.txt"]
    assert [item.sha256 for item in hashes] == [
        "3e23e8160039594a33894f6564e1b1348bbd7a0088d42c4acb73eeaed59c009d",
        "594e519ae499312b29433b7dd8a97ff068defcba9755b6d5d00e84c524d67b06",
    ]


def test_summary_is_deterministic_and_contains_release_evidence() -> None:
    """Catch update summaries omitting reviewer evidence or changing between runs."""
    previous = _provenance("1" * 40)
    proposed = _provenance("2" * 40, skills=("alpha", "beta"))

    first = render_summary(
        previous,
        proposed,
        changed_skills=("alpha",),
        patch_failures=(),
        test_command="uv run pytest -q -m 'not live_agent' engineering/tests",
        test_result="PASS",
        setup_contract_changed=False,
    )

    assert first == render_summary(
        previous,
        proposed,
        changed_skills=("alpha",),
        patch_failures=(),
        test_command="uv run pytest -q -m 'not live_agent' engineering/tests",
        test_result="PASS",
        setup_contract_changed=False,
    )
    assert "1111111111111111111111111111111111111111" in first
    assert "2222222222222222222222222222222222222222" in first
    assert "Added skills: beta" in first
    assert "Changed skills: alpha" in first
    assert "Patch hashes:" in first
    assert "License hashes:" in first
    assert "Non-live test: PASS" in first
    assert "Proposed version: minor" in first


def test_summary_blocks_removed_skill() -> None:
    """Catch proposing a releasable version for a removal or rename."""
    summary = render_summary(
        _provenance("1" * 40, skills=("alpha", "beta")),
        _provenance("2" * 40, skills=("alpha",)),
        changed_skills=(),
        patch_failures=("patches/broken.patch: rejected",),
        test_command="uv run pytest",
        test_result="FAIL",
        setup_contract_changed=False,
    )

    assert "Removed skills: beta" in summary
    assert "Patch failures: patches/broken.patch: rejected" in summary
    assert "Proposed version: BLOCKED" in summary
