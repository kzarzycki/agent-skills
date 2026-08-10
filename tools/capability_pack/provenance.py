from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

import yaml

from tools.capability_pack.model import FileHash, Provenance, SourceMapping


def _git_file_mode(path: Path) -> str:
    """Normalize a regular file to the only two modes Git tracks."""
    return "100755" if path.stat().st_mode & 0o111 else "100644"


def hash_files(root: Path, paths: Iterable[Path]) -> tuple[FileHash, ...]:
    return tuple(
        FileHash(
            path=path.relative_to(root).as_posix(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            mode=_git_file_mode(path),
        )
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix())
    )


def _file_hashes(values: object) -> tuple[FileHash, ...]:
    if not isinstance(values, list):
        raise TypeError("provenance file manifest must be a list")
    return tuple(
        FileHash(
            path=item["path"],
            sha256=item["sha256"],
            mode=item.get("mode", "100644"),
        )
        for item in values
    )


def _source_mappings(values: object) -> tuple[SourceMapping, ...]:
    if not isinstance(values, list):
        raise TypeError("provenance source mappings must be a list")
    return tuple(
        SourceMapping(
            source_repository=item["source_repository"],
            source_commit=item["source_commit"],
            source_path=item["source_path"],
            destination_path=item["destination_path"],
        )
        for item in values
    )


def load_provenance(path: Path) -> Provenance:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise TypeError("provenance must be a mapping")
    return Provenance(
        source_commit=data["source_commit"],
        source_tag=data.get("source_tag"),
        stable_baseline_tag=data.get("stable_baseline_tag"),
        included_skills=tuple(data.get("included_skills", ())),
        excluded_skills=tuple(data.get("excluded_skills", ())),
        owned_overlays=_file_hashes(data.get("owned_overlays", [])),
        source_mappings=_source_mappings(data.get("source_mappings", [])),
        source_files=_file_hashes(data.get("source_files", [])),
        patch_files=_file_hashes(data.get("patch_files", [])),
        license_files=_file_hashes(data.get("license_files", [])),
        output_files=_file_hashes(data.get("output_files", [])),
    )


def write_provenance(path: Path, provenance: Provenance) -> None:
    def manifest(items: tuple[FileHash, ...]) -> list[dict[str, str]]:
        return [{"path": item.path, "sha256": item.sha256, "mode": item.mode} for item in items]

    data = {
        "source_commit": provenance.source_commit,
        "source_tag": provenance.source_tag,
        "stable_baseline_tag": provenance.stable_baseline_tag,
        "included_skills": list(provenance.included_skills),
        "excluded_skills": list(provenance.excluded_skills),
        "owned_overlays": manifest(provenance.owned_overlays),
        "source_mappings": [
            {
                "source_repository": item.source_repository,
                "source_commit": item.source_commit,
                "source_path": item.source_path,
                "destination_path": item.destination_path,
            }
            for item in provenance.source_mappings
        ],
        "source_files": manifest(provenance.source_files),
        "patch_files": manifest(provenance.patch_files),
        "license_files": manifest(provenance.license_files),
        "output_files": manifest(provenance.output_files),
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
