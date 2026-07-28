from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileHash:
    path: str
    sha256: str


@dataclass(frozen=True)
class Provenance:
    source_commit: str
    included_skills: tuple[str, ...]
    excluded_skills: tuple[str, ...]
    source_files: tuple[FileHash, ...]
    patch_files: tuple[FileHash, ...]
    license_files: tuple[FileHash, ...]
    output_files: tuple[FileHash, ...]


@dataclass(frozen=True)
class QualificationResult:
    changed: bool
    source_commit: str
    added_skills: tuple[str, ...]
    removed_skills: tuple[str, ...]
    summary: str
