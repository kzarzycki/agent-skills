"""Roles as agent files (#1067): each role is a Claude Code subagent file that names no model or harness."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLES = {
    "lead": (ROOT / "loop/agents/lead.md", ROOT / "loop/skills/engineering-loop/lead.md"),
    "worker": (ROOT / "loop/agents/worker.md", ROOT / "loop/skills/engineering-loop/worker.md"),
    "verifier": (
        ROOT / "loop/agents/verifier.md",
        ROOT / "loop/skills/engineering-loop/verifier.md",
    ),
    "chief-of-staff": (
        ROOT / "chief-of-staff/agents/chief-of-staff.md",
        ROOT / "chief-of-staff/skills/chief-of-staff/SKILL.md",
    ),
}
HARNESS_OR_MODEL = re.compile(
    r"claude|codex|gemini|omnigent|opus|sonnet|haiku|fable|gpt|antigravity|\bagy\b", re.IGNORECASE
)


def split(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    _, front, body = text.split("---\n", 2)
    fields = yaml.safe_load(front)
    assert isinstance(fields, dict)
    return fields, body


@pytest.mark.parametrize("role", ROLES)
def test_role_file_has_valid_frontmatter(role):
    fields, body = split(ROLES[role][0])
    assert fields["name"] == role
    assert isinstance(fields["description"], str) and fields["description"]
    assert fields["skills"]
    assert body.strip()


@pytest.mark.parametrize("role", ROLES)
def test_role_file_denies_no_command(role):
    # A command-specific entry such as Bash(gh pr merge *) removes all of Bash from a subagent.
    fields, _ = split(ROLES[role][0])
    denied = fields.get("disallowedTools") or ""
    assert "(" not in denied


@pytest.mark.parametrize("role", ROLES)
def test_role_file_names_no_model_or_harness(role):
    path = ROLES[role][0]
    fields, _ = split(path)
    assert "model" not in fields
    assert not HARNESS_OR_MODEL.search(path.read_text())


def test_verifier_cannot_edit():
    fields, _ = split(ROLES["verifier"][0])
    denied = {tool.strip() for tool in fields["disallowedTools"].split(",")}
    assert {"Edit", "Write", "NotebookEdit"} <= denied


@pytest.mark.parametrize("role", ROLES)
def test_role_prose_has_one_copy(role):
    agent, skill = ROLES[role]
    _, body = split(agent)
    assert skill.name in body
    skill_lines = {
        line.strip() for line in skill.read_text().splitlines() if len(line.strip()) > 40
    }
    copied = [line.strip() for line in body.splitlines() if line.strip() in skill_lines]
    assert not copied
    assert len(body.splitlines()) < 12
