from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tools.capability_pack.model import FileHash, Provenance, SourceMapping
from tools.capability_pack.provenance import hash_files, load_provenance, write_provenance
from tools.capability_pack.summary import render_summary


def _provenance(commit: str, *, skills: tuple[str, ...] = ("alpha",)) -> Provenance:
    return Provenance(
        source_commit=commit,
        included_skills=skills,
        excluded_skills=("setup-matt-pocock-skills",),
        source_mappings=(
            SourceMapping(
                "https://example.invalid/upstream.git",
                commit,
                "skills/engineering/alpha",
                "skills/alpha",
            ),
        ),
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


def test_hash_files_normalizes_only_the_git_executable_bit(tmp_path: Path) -> None:
    """Catch platform permission noise while preserving Git's 0644/0755 distinction."""
    path = tmp_path / "tool"
    path.write_text("same bytes")

    path.chmod(0o600)
    non_executable = hash_files(tmp_path, [path])
    path.chmod(0o644)
    normal = hash_files(tmp_path, [path])
    path.chmod(0o755)
    executable = hash_files(tmp_path, [path])

    assert non_executable[0].mode == normal[0].mode == "100644"
    assert executable[0].mode == "100755"
    assert {item.sha256 for item in (*non_executable, *normal, *executable)} == {
        non_executable[0].sha256
    }


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


def test_summary_deduplicates_changed_license_paths() -> None:
    """Catch reporting one changed license twice because both hashes differ."""
    previous = _provenance("1" * 40)
    proposed = replace(
        _provenance("2" * 40),
        license_files=(FileHash("LICENSES/LICENSE", "e" * 64),),
    )

    summary = render_summary(
        previous,
        proposed,
        changed_skills=(),
        patch_failures=(),
        test_command="uv run pytest",
        test_result="PASS",
        setup_contract_changed=False,
    )

    line = next(line for line in summary.splitlines() if line.startswith("License changes:"))
    assert line == "License changes: LICENSES/LICENSE"
