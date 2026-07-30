from __future__ import annotations

from pathlib import Path

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
PINNED_COMMIT = "2ab958093e83e0ec752e6c1c5932da465bf23e0c"
OWNED_SKILLS = {
    "audit-third-party-software",
    "context-extractor",
    "operating-omnigent",
}
IMPORTED_SKILLS = {
    "ask-matt",
    "code-review",
    "codebase-design",
    "diagnosing-bugs",
    "domain-modeling",
    "grill-with-docs",
    "grilling",
    "implement",
    "improve-codebase-architecture",
    "prototype",
    "research",
    "resolving-merge-conflicts",
    "setup-engineering-workflow-for-apm",
    "tdd",
    "to-spec",
    "to-tickets",
    "triage",
    "wayfinder",
}


def _skill_inventory() -> set[str]:
    return {path.parent.name for path in (PACKAGE / "skills").glob("*/SKILL.md") if path.is_file()}


def test_package_contains_the_pinned_upstream_inventory_and_owned_skills() -> None:
    assert _skill_inventory() == IMPORTED_SKILLS | OWNED_SKILLS


def test_provenance_records_the_pinned_import_boundary() -> None:
    provenance = yaml.safe_load((PACKAGE / "provenance.yml").read_text())

    assert provenance["source_commit"] == PINNED_COMMIT
    assert set(provenance["included_skills"]) == IMPORTED_SKILLS
    assert provenance["excluded_skills"] == ["setup-matt-pocock-skills"]


def test_imported_text_uses_the_owned_setup_command() -> None:
    offenders = [
        path.relative_to(PACKAGE).as_posix()
        for skill in sorted(IMPORTED_SKILLS)
        for path in (PACKAGE / "skills" / skill).rglob("*")
        if path.is_file() and "/setup-matt-pocock-skills" in path.read_text()
    ]

    assert offenders == []
