"""The engineering loop is method: a project's facts live in its own docs/agents/ files, never in the skill."""

from __future__ import annotations

import re
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop"
# Terms of the project the loop was ported from; `ta/` only as a path start, so `data/` is no hit.
PROJECT_TERMS = re.compile(r"(?<![\w.-])ta/|bin/dev|IBKR|trinity", re.IGNORECASE)


def hits(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root)}:{number}: {line.strip()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
        if PROJECT_TERMS.search(line)
    ]


def test_the_loop_names_no_project() -> None:
    assert LOOP.is_dir() and hits(LOOP) == []


def test_the_check_catches_each_term_but_not_a_lookalike(tmp_path: Path) -> None:
    lines = ["run ta/x", "bin/dev up", "IBKR fills", "Trinity's", "~/dev/trinity", "data/ meta/"]
    (tmp_path / "f.md").write_text("\n".join(lines))
    assert [hit.split(": ", 1)[1] for hit in hits(tmp_path)] == lines[:-1]


def loop_sections() -> list[str]:
    """Section names in SKILL.md's docs/agents/loop.md row, up to the sentence on optional lines."""
    row = next(
        line
        for line in (LOOP / "SKILL.md").read_text().splitlines()
        if line.startswith("| `docs/agents/loop.md` |")
    )
    cell = row.split("|")[2].split(". ")[0]
    return [re.sub(r"\(.*?\)", "", part).split(",")[0].strip() for part in cell.split(";")]


def test_every_cited_loop_section_is_listed() -> None:
    sections = loop_sections()
    assert "Approvals" in sections and "Settings" in sections
    unlisted = [
        f"{path.relative_to(LOOP)}: § {cited}"
        for path in sorted(LOOP.rglob("*.md"))
        for cited in re.findall(
            r"loop\.md`? § (\S+(?: \S+){0,3})", " ".join(path.read_text().split())
        )
        if not any(re.match(rf"{re.escape(name)}\b", cited) for name in sections)
    ]
    assert unlisted == []


# A bare CLI child (`codex exec -C <dir> "..."` in a code block, or inline with its prompt) runs
# outside any backend, so nothing lists, watches or closes it, and dotagents hosts deny it (#278).
BARE_CHILD = re.compile(
    r"^\s*(?:claude -p|codex exec|omp -p|gemini -p|agy -p)\s"
    r"|`(?:claude -p|codex exec|omp -p|gemini -p|agy -p) [^`]*[\"<]"
)


def bare_children(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root)}:{number}: {line.strip()}"
        for path in sorted(root.rglob("*.md"))
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
        if BARE_CHILD.search(line)
    ]


def test_no_skill_starts_a_bare_cli_child() -> None:
    assert bare_children(LOOP.parent) == []


def test_the_bare_child_check_catches_a_start_but_not_a_mention(tmp_path: Path) -> None:
    starts = ['codex exec -C <worktree> "Read b.md."', 'claude -p "Read b.md."', '`gemini -p "go"`']
    mentions = ["never start it with `claude -p` or `codex exec`", "one `claude -p --model"]
    (tmp_path / "f.md").write_text("\n".join(starts + mentions))
    assert [hit.split(": ", 1)[1] for hit in bare_children(tmp_path)] == starts


def test_the_cloud_split_is_reached_only_through_its_loop_md_line() -> None:
    """Without the line every role file reads as before: each adds one pointer line, no more."""
    skill = (LOOP / "SKILL.md").read_text()
    section = skill.split("\n## Cloud worker\n", 1)[1].split("\n## ", 1)[0]
    assert section.strip().startswith("With the loop.md line `Cloud worker: <agent>, gate <task>`")
    assert "Without the line nothing" in section
    assert "`Cloud worker: <agent>, gate <task>`" in next(
        line for line in skill.splitlines() if line.startswith("| `docs/agents/loop.md` |")
    )
    for role in ("lead.md", "worker.md", "verifier.md"):
        cloud = [line for line in (LOOP / role).read_text().splitlines() if "cloud" in line.lower()]
        assert len(cloud) == 1, (role, cloud)
        assert "`Cloud worker:`" in cloud[0] and "SKILL.md, Cloud worker" in cloud[0]


def test_the_verifier_waits_in_few_long_calls_and_reruns_repros_together() -> None:
    """A wait or a repro per short call re-reads the whole context each time."""
    verifier = " ".join((LOOP / "verifier.md").read_text().split())
    assert (
        "never short polls or a sleep loop of your own, since every call re-reads the whole context"
        in verifier
    )
    assert "wait-for --log <log> --pid <pid>" in verifier  # the one verb that blocks to the limit
    assert "waited on as a detached run is" in verifier  # the bare gate too
    assert "Rerun all of its repros from one script" in verifier
    assert "the diff since its head and the files it touches" in verifier


def test_owner_questions_end_the_turn_rather_than_wait_in_a_tool() -> None:
    """A tool that waits for the owner's answer holds the turn open, and Omnigent delivers input
    only at turn end, so every relay and supervisor event queues behind the question (#658)."""
    cos = " ".join((LOOP.parent / "chief-of-staff" / "SKILL.md").read_text().split())
    lead = " ".join((LOOP / "lead.md").read_text().split())
    assert "Ask as text at the end of your turn" in cos
    assert "as text that ends your turn `USER NEEDED`" in lead
    for text in (cos, lead):
        assert "never through a tool that waits for the answer" in text
        assert "(Claude Code's AskUserQuestion, Codex's requestUserInput)" in text


def test_a_held_approval_prompt_is_never_routed_around() -> None:
    """A lead read a call held for the owner's approval as a hang and made the change over REST (#696)."""
    skill = " ".join((LOOP / "SKILL.md").read_text().split())
    assert "A tool call held for approval is waiting for the owner, not hung" in skill
    assert "never make its change by another route (REST, another tool, a script)" in skill
    for role in ("lead.md", "worker.md", "verifier.md"):
        text = " ".join((LOOP / role).read_text().split())
        assert (
            "A tool call held for approval waits for the owner, not a hang: never make its change"
            " by another route, since the approval is theirs to give (SKILL.md, Owner steps park)."
        ) in text, role
