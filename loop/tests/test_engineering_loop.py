"""The engineering loop is method: a project's facts live in its own docs/agents/ files, never in the skill, nor in
the gatekeeper and GitHub skills that came out of it."""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
LOOP = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop"
METHOD = (
    LOOP,
    REPOSITORY / "gatekeeper" / "skills" / "gatekeeper",
    REPOSITORY / "github" / "skills" / "github-tracker",
)
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
    for root in METHOD:
        assert root.is_dir() and hits(root) == []


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
    assert "Approvals" in sections and "Owner" in sections
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


def section_of(text: str, heading: str) -> str:
    """The body of the `## <heading>` section, joined onto one line."""
    return " ".join(text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0].split())


def test_the_cloud_is_the_default_and_none_opts_out() -> None:
    """No line means claude-cloud with the policy's gate; `none` means host workers (#1119)."""
    skill = (LOOP / "SKILL.md").read_text()
    section = section_of(skill, "Cloud worker")
    assert section.startswith("With the loop.md line `Cloud worker: <agent>, gate <task>`")
    assert (
        "Without the line the same holds with `claude-cloud` as the agent and the policy's `gate`"
        " as the gate" in section
    )
    assert "Without the line nothing" not in section  # the opt-in it replaced
    assert (
        "A line that opens `Cloud worker: none`, with the project's reason after it, keeps workers on hosts"
        in section
    )
    assert "A project that has the line keeps its meaning" in section
    assert "`Cloud worker: <agent>, gate <task>, env <name>`" in section
    assert "`omnigent_agent.py cloud-env <checkout>`" in section
    row = next(line for line in skill.splitlines() if line.startswith("| `docs/agents/loop.md` |"))
    assert "`Cloud worker: <agent>, gate <task>`" in row and "`Cloud worker: none`" in row


def test_placement_is_stated_once_and_the_role_files_point_to_it() -> None:
    """Every heavy run by any role, in one order, with a lead's own run's recipe (#1119)."""
    rule = section_of((LOOP / "SKILL.md").read_text(), "Where heavy steps run")
    for run in (
        (
            "implementation, the gate, the verifier's test and mutation runs, proof runs, and a"
            " lead's own suite, build and e2e runs"
        ),
        "the only place placement is stated",
    ):
        assert run in rule
    order = [
        (
            "1. To a Claude cloud session: the agent the project's `docs/agents/loop.md` names on"
            " its `Cloud worker:` line, else `claude-cloud`"
        ),
        "2. Else to a host that offers the harness the step needs, under the start's capacity check",
        "3. A step that needs a particular machine",
    ]
    assert [rule.index(step) for step in order] == sorted(rule.index(step) for step in order)
    assert (
        "a cloud launch that is refused, whose setup fails twice, or that is out of quota goes to a host"
        in rule
    )
    assert "The lead's report says which run went where and why" in rule
    # a lead's own run is one call, made the default by the pack's hook (#1233)
    assert "`omnigent_agent.py claude-cloud-run [--checkout DIR] -- <command>`" in rule
    assert "exits with the command's own code" in rule
    assert "PreToolUse hook" in rule and "`LOOP_HOST_RUN=<reason>`" in rule
    assert "launch-dir" not in rule.split("A lead's own heavy run")[1].split("\n")[0]
    for role in ("lead.md", "worker.md", "verifier.md", "proof-run.md"):
        text = " ".join((LOOP / role).read_text().split())
        assert "SKILL.md, Where heavy steps run" in text, role
        assert (
            "else `claude-cloud`" not in text and "under the start's capacity check" not in text
        ), role
    lead = " ".join((LOOP / "lead.md").read_text().split())
    assert "each heavy run that did not go to the cloud with where it went and why" in lead
    assert (
        "Every heavy run, a worker's or your own (a suite to sort failures, a build, an e2e run),"
        " goes where SKILL.md, Where heavy steps run says, which also gives your own run's recipe"
        in lead
    )


def test_the_verifier_waits_with_one_wake_and_reruns_repros_together() -> None:
    """A wait or a repro per short call re-reads the whole context each time: a run is waited on
    by one tracked background wait as long as the run (waste audit, finding 1)."""
    verifier = " ".join((LOOP / "verifier.md").read_text().split())
    assert (
        "Never a short `wait-for`, an `until grep` or a `sleep` loop, since each return re-reads your whole context"
        in verifier
    )
    assert (
        "wait-for --log <log> --pid <pid> --budget <the run's expected length>` started as a background call"
        in verifier
    )
    worker = " ".join((LOOP / "worker.md").read_text().split())
    assert (
        "--budget <the run's expected length>`" in worker and "never a short `wait-for`" in worker
    )
    assert "blocks close to the tool limit and prints only the outcome" not in worker
    assert "waited on as a detached run is" in verifier  # the bare gate too
    assert "Rerun all of its repros from one script" in verifier
    assert "the diff since its head and the files it touches" in verifier


def test_owner_questions_end_the_turn_rather_than_wait_in_a_tool() -> None:
    """A tool that waits for the owner's answer holds the turn open, and Omnigent delivers input
    only at turn end, so every relay and supervisor event queues behind the question (#658)."""
    cos = " ".join(
        (REPOSITORY / "chief-of-staff" / "skills" / "chief-of-staff" / "SKILL.md")
        .read_text()
        .split()
    )
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


def test_the_verifier_keeps_real_data_out_of_the_report_it_posts() -> None:
    """The report is posted as the PR review, so real data goes in a local evidence file."""
    verifier = " ".join((LOOP / "verifier.md").read_text().split())
    assert "Real data you see may go in your report" not in verifier
    assert "The report is posted as the PR review, so it holds no real data" in verifier
    assert "local file next to the report (under `tmp/loop/`)" in verifier
    assert "cites that file by path and says what it shows, without the values" in verifier
