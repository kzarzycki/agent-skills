from __future__ import annotations

from tools.capability_pack.model import FileHash, Provenance


def _names(items: tuple[str, ...]) -> str:
    return ", ".join(items) if items else "none"


def _hashes(items: tuple[FileHash, ...]) -> str:
    return ", ".join(f"{item.path}={item.sha256}" for item in items) if items else "none"


def render_summary(
    previous: Provenance | None,
    proposed: Provenance,
    *,
    changed_skills: tuple[str, ...],
    patch_failures: tuple[str, ...],
    test_command: str,
    test_result: str,
    setup_contract_changed: bool,
) -> str:
    previous_commit = previous.source_commit if previous else "none"
    old_skills = set(previous.included_skills if previous else ())
    new_skills = set(proposed.included_skills)
    added = tuple(sorted(new_skills - old_skills))
    removed = tuple(sorted(old_skills - new_skills))
    if removed or setup_contract_changed or patch_failures:
        version = "BLOCKED"
    elif added:
        version = "minor"
    else:
        version = "patch"
    lines = [
        f"Previous source commit: {previous_commit}",
        f"Proposed source commit: {proposed.source_commit}",
        f"Added skills: {_names(added)}",
        f"Removed skills: {_names(removed)}",
        f"Changed skills: {_names(tuple(sorted(changed_skills)))}",
        f"Patch hashes: {_hashes(proposed.patch_files)}",
        f"Patch failures: {_names(patch_failures)}",
        f"License hashes: {_hashes(proposed.license_files)}",
        f"License changes: {_license_changes(previous, proposed)}",
        f"Non-live test command: {test_command}",
        f"Non-live test: {test_result}",
        f"Proposed version: {version}",
    ]
    return "\n".join(lines) + "\n"


def _license_changes(previous: Provenance | None, proposed: Provenance) -> str:
    old = set(previous.license_files if previous else ())
    new = set(proposed.license_files)
    changed = sorted({item.path for item in old ^ new})
    return ", ".join(changed) if changed else "none"
