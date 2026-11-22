"""The split stage: a Practice row, a stage key the gatekeeper accepts, a skill that writes
the manifest and never tracker state, and an apply step that takes the manifest."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_practice_table_has_a_split_row_defaulting_to_to_tickets() -> None:
    rows = [
        line
        for line in _read("loop/skills/engineering-loop/SKILL.md").splitlines()
        if line.startswith("| Split")
    ]
    assert len(rows) == 1
    assert "manifest" in rows[0]
    assert rows[0].rstrip(" |").endswith("`to-tickets`")


def test_to_tickets_writes_a_manifest_and_no_tracker_state() -> None:
    text = _read("engineering/skills/to-tickets/SKILL.md")
    assert text == _read("engineering/overlays/skills/to-tickets/SKILL.md")
    assert "split-manifest.json" in text
    assert "Never create, edit or close an issue" in text
    assert "gh issue create" not in text


def test_apply_step_takes_the_manifest_as_its_batch() -> None:
    text = _read("github/skills/github-tracker/github.md")
    assert "### Input: the split manifest" in text
    assert "`blocked_by`" in text


def test_local_files_apply_step_is_named_where_github_tracker_is_read() -> None:
    skill = _read("github/skills/github-tracker/SKILL.md")
    assert "scripts/issue_batch.py" in skill
    assert "(local.md)" in skill
    assert "issue_batch.py local" in _read("github/skills/github-tracker/local.md")
    assert "issue_batch.py github" in _read("github/skills/github-tracker/github.md")
