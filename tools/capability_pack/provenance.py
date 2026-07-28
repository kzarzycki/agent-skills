from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

import yaml

from tools.capability_pack.model import FileHash, Provenance


def hash_files(root: Path, paths: Iterable[Path]) -> tuple[FileHash, ...]:
    return tuple(
        FileHash(
            path=path.relative_to(root).as_posix(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix())
    )


def _file_hashes(values: object) -> tuple[FileHash, ...]:
    if not isinstance(values, list):
        raise TypeError("provenance file manifest must be a list")
    return tuple(FileHash(path=item["path"], sha256=item["sha256"]) for item in values)


def load_provenance(path: Path) -> Provenance:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise TypeError("provenance must be a mapping")
    return Provenance(
        source_commit=data["source_commit"],
        included_skills=tuple(data.get("included_skills", ())),
        excluded_skills=tuple(data.get("excluded_skills", ())),
        source_files=_file_hashes(data.get("source_files", [])),
        patch_files=_file_hashes(data.get("patch_files", [])),
        license_files=_file_hashes(data.get("license_files", [])),
        output_files=_file_hashes(data.get("output_files", [])),
    )


def write_provenance(path: Path, provenance: Provenance) -> None:
    def manifest(items: tuple[FileHash, ...]) -> list[dict[str, str]]:
        return [{"path": item.path, "sha256": item.sha256} for item in items]

    data = {
        "source_commit": provenance.source_commit,
        "included_skills": list(provenance.included_skills),
        "excluded_skills": list(provenance.excluded_skills),
        "source_files": manifest(provenance.source_files),
        "patch_files": manifest(provenance.patch_files),
        "license_files": manifest(provenance.license_files),
        "output_files": manifest(provenance.output_files),
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
