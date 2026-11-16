from __future__ import annotations

from pathlib import Path

import yaml

PACKAGE = Path(__file__).resolve().parents[1]


def _data() -> tuple[dict, dict, dict]:
    return (
        yaml.safe_load((PACKAGE / "upstream.yml").read_text()),
        yaml.safe_load((PACKAGE / "provenance.yml").read_text()),
        yaml.safe_load((PACKAGE / "vendir.lock.yml").read_text()),
    )


def _skill_inventory() -> set[str]:
    return {path.parent.name for path in (PACKAGE / "skills").glob("*/SKILL.md")}


def test_inventory_is_derived_from_provenance_and_policy() -> None:
    policy, provenance, _ = _data()
    assert set(policy) == {
        "schema_version",
        "repository",
        "tracked_ref",
        "stable_tag_pattern",
        "removal_policy",
        "substitutions",
        "exclusions",
        "aliases",
        "owned_skills",
        "owned_overlays",
    }
    overlays = {Path(item["destination"]).name for item in policy["owned_overlays"]}
    expected = set(provenance["included_skills"]) | set(policy["owned_skills"]) | overlays
    assert _skill_inventory() == expected
    assert not (set(policy["exclusions"]) & _skill_inventory())


def test_substitution_rules_leave_no_upstream_literal_behind() -> None:
    policy, provenance, _ = _data()
    shipped = "\n".join(
        path.read_text()
        for name in provenance["included_skills"]
        for path in sorted((PACKAGE / "skills" / name).rglob("*"))
        if path.is_file()
    )
    for rule in policy["substitutions"]:
        assert rule["find"] not in shipped
        assert rule["replace"] in shipped


def test_lock_provenance_and_mappings_share_one_source_identity() -> None:
    _, provenance, lock = _data()
    commits = {
        content["git"]["sha"]
        for directory in lock["directories"]
        for content in directory["contents"]
        if "git" in content
    }
    mapping_commits = {item["source_commit"] for item in provenance["source_mappings"]}
    destinations = {Path(item["destination_path"]).name for item in provenance["source_mappings"]}
    assert commits == mapping_commits == {provenance["source_commit"]}
    assert destinations == set(provenance["included_skills"])
    assert len(provenance["source_mappings"]) == len(
        {(item["source_repository"], item["source_path"]) for item in provenance["source_mappings"]}
    )


# The After merge list in the kept verifier, the epic handoff note and the Nightly section (#1158).


def _flat(name: str) -> str:
    return " ".join((PACKAGE / "skills" / "engineering-loop" / name).read_text().split())


def _step(name: str, number: int) -> str:
    text = _flat(name)
    start = text.index(f" {number}. **")
    end = text.index(f" {number + 1}. **", start)
    return text[start:end]


def test_lead_step_9_sends_the_after_merge_list_to_the_kept_verifier_with_reuse() -> None:
    accept = _step("lead.md", 9)
    assert "`Verifier session: reuse`" in accept
    assert "send the spec's After merge list to the kept verifier right after the merge" in accept
    assert "Otherwise, or once that verifier's session has ended, run the list as above." in accept


def test_lead_step_9_leaves_the_epic_handoff_note_at_the_last_sub_issue_merge() -> None:
    accept = _step("lead.md", 9)
    assert "**Epic handoff note.**" in accept
    for item in (
        "each story's PR and merge commit",
        "each spec's acceptance checks",
        "the After merge results",
        "what the next nightly must confirm",
    ):
        assert item in accept


def test_skill_has_a_nightly_section_naming_nightly_py_red() -> None:
    skill = _flat("SKILL.md")
    start = skill.index("**Nightly.**")
    nightly_section = skill[start : skill.index("**", start + len("**Nightly.**"))]
    assert "full suite" in nightly_section
    assert "scripts/acceptance.py --all" in nightly_section
    assert (
        "uv run <this skill's folder>/scripts/nightly.py red --last-green <sha> --red <sha> --run <url>"
        in nightly_section
    )


def test_owned_overlay_is_canonical_and_reproduced() -> None:
    policy, provenance, _ = _data()
    assert provenance["excluded_skills"] == policy["exclusions"]
    for overlay in policy["owned_overlays"]:
        source = PACKAGE / overlay["source"]
        destination = PACKAGE / overlay["destination"]
        source_files = {
            path.relative_to(source): path.read_bytes()
            for path in source.rglob("*")
            if path.is_file()
        }
        destination_files = {
            path.relative_to(destination): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file()
        }
        assert destination_files == source_files


def test_no_skill_sends_the_user_to_a_setup_skill() -> None:
    offenders = [
        path.relative_to(PACKAGE).as_posix()
        for path in (PACKAGE / "skills").rglob("*")
        if path.is_file()
        and any(
            name in path.read_text(errors="ignore")
            for name in ("/setup-matt-pocock-skills", "setup-engineering-workflow-for-apm")
        )
    ]
    assert offenders == []
