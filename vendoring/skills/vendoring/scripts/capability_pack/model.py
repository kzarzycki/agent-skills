from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileHash:
    path: str
    sha256: str
    mode: str = "100644"


@dataclass(frozen=True)
class SourceMapping:
    source_repository: str
    source_commit: str
    source_path: str
    destination_path: str


@dataclass(frozen=True)
class Provenance:
    source_commit: str
    included_skills: tuple[str, ...]
    excluded_skills: tuple[str, ...]
    source_mappings: tuple[SourceMapping, ...]
    source_files: tuple[FileHash, ...]
    patch_files: tuple[FileHash, ...]
    license_files: tuple[FileHash, ...]
    output_files: tuple[FileHash, ...]
    source_tag: str | None = None
    stable_baseline_tag: str | None = None
    owned_overlays: tuple[FileHash, ...] = ()


@dataclass(frozen=True)
class QualificationResult:
    changed: bool
    source_commit: str
    added_skills: tuple[str, ...]
    removed_skills: tuple[str, ...]
    summary: str
    proposed_version: str | None = None
    changed_skills: tuple[str, ...] = ()
