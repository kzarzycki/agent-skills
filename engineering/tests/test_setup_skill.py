from __future__ import annotations

import difflib
import re
import shutil
from pathlib import Path, PurePosixPath

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
SKILL = PACKAGE / "skills" / "setup-engineering-workflow-for-apm"
OVERLAY = PACKAGE / "overlays" / "skills" / "setup-engineering-workflow-for-apm"
PROTOCOL_PATTERN = re.compile(
    r"<!-- setup-fixture-protocol\n(?P<protocol>.*?)\n-->",
    re.DOTALL,
)


def _load_protocol() -> dict:
    match = PROTOCOL_PATTERN.search((SKILL / "SKILL.md").read_text())
    assert match, "setup skill must declare its fixture protocol"
    protocol = yaml.safe_load(match.group("protocol"))
    assert protocol["version"] == 1
    return protocol


def _replace_marked_section(
    existing: str,
    rendered: str,
    start_marker: str,
    end_marker: str,
) -> str:
    block = f"{start_marker}\n{rendered.rstrip()}\n{end_marker}"
    if start_marker not in existing and end_marker not in existing:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        return f"{existing}{separator}{block}\n"

    assert existing.count(start_marker) == 1
    assert existing.count(end_marker) == 1
    before, marked = existing.split(start_marker)
    _, after = marked.split(end_marker)
    return f"{before}{block}{after}"


def _run_fixture_protocol(
    project: Path,
    *,
    source_changes_approved: bool = False,
    no_diff_recheck_approved: bool = False,
) -> dict:
    protocol = _load_protocol()
    start_marker = protocol["markers"]["start"]
    end_marker = protocol["markers"]["end"]
    proposals = []

    for source_file in protocol["source_files"]:
        destination = project / source_file["destination"]
        destination_exists = destination.exists()
        existing = destination.read_text() if destination_exists else ""
        rendered = (SKILL / source_file["template"]).read_text()
        proposed = _replace_marked_section(existing, rendered, start_marker, end_marker)
        if proposed == existing:
            continue
        relative = destination.relative_to(project).as_posix()
        diff = "".join(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile=f"a/{relative}" if destination_exists else "/dev/null",
                tofile=f"b/{relative}",
            )
        )
        proposals.append((relative, diff, destination, proposed))

    directly_written_files: list[str] = []
    sync_commands: list[list[str]] = []
    if proposals and source_changes_approved:
        for relative, _, destination, proposed in proposals:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(proposed)
            directly_written_files.append(relative)
        sync_commands.append(protocol["sync_command"])
    elif not proposals and no_diff_recheck_approved:
        sync_commands.append(protocol["sync_command"])

    changed_roots = {"/".join(PurePosixPath(path).parts[:2]) for path in directly_written_files}
    return {
        "changed_roots": changed_roots,
        "directly_written_files": directly_written_files,
        "proposals": [(path, diff) for path, diff, _, _ in proposals],
        "sync_commands": sync_commands,
    }


def _fixture_project(tmp_path: Path) -> Path:
    protocol = _load_protocol()
    project = tmp_path / "project"
    shutil.copytree(PACKAGE / protocol["fixture"], project)
    return project


def test_setup_owns_only_apm_sources_and_runs_the_single_compiler(tmp_path: Path) -> None:
    project = _fixture_project(tmp_path)

    result = _run_fixture_protocol(project, source_changes_approved=True)

    assert result["changed_roots"] <= {".apm/instructions", "docs/agents"}
    assert "AGENTS.md" not in result["directly_written_files"]
    assert "CLAUDE.md" not in result["directly_written_files"]
    assert result["sync_commands"] == [["mise", "run", "agent-sync"]]


def test_setup_proposes_exact_paths_and_unified_diffs_before_writing(
    tmp_path: Path,
) -> None:
    project = _fixture_project(tmp_path)
    before = {
        path.relative_to(project).as_posix(): path.read_text()
        for path in project.rglob("*")
        if path.is_file()
    }

    result = _run_fixture_protocol(project)

    assert result["directly_written_files"] == []
    assert result["sync_commands"] == []
    assert before == {
        path.relative_to(project).as_posix(): path.read_text()
        for path in project.rglob("*")
        if path.is_file()
    }
    for path, diff in result["proposals"]:
        assert diff.startswith(f"--- a/{path}\n+++ b/{path}\n")


def test_clean_first_run_proposes_and_creates_both_source_files(tmp_path: Path) -> None:
    project = tmp_path / "clean-project"
    project.mkdir()
    expected_paths = {
        ".apm/instructions/engineering-workflow.md",
        "docs/agents/issue-tracker.md",
    }

    proposal = _run_fixture_protocol(project)

    assert {path for path, _ in proposal["proposals"]} == expected_paths
    for path, diff in proposal["proposals"]:
        assert diff.startswith(f"--- /dev/null\n+++ b/{path}\n")
        assert not (project / path).exists()

    applied = _run_fixture_protocol(project, source_changes_approved=True)

    assert set(applied["directly_written_files"]) == expected_paths
    for path in expected_paths:
        content = (project / path).read_text()
        assert content.startswith("<!-- engineering-workflow:start -->\n")
        assert content.endswith("<!-- engineering-workflow:end -->\n")


def test_marker_absent_update_preserves_every_existing_byte(tmp_path: Path) -> None:
    project = _fixture_project(tmp_path)
    guidance = project / ".apm" / "instructions" / "engineering-workflow.md"
    user_bytes = b"User-authored line with trailing spaces.  \n\n\n"
    guidance.write_bytes(user_bytes)

    _run_fixture_protocol(project, source_changes_approved=True)

    result = guidance.read_bytes()
    assert result[: len(user_bytes)] == user_bytes
    assert result[len(user_bytes) :].startswith(b"<!-- engineering-workflow:start -->\n")
    assert result.endswith(b"<!-- engineering-workflow:end -->\n")


def test_setup_is_idempotent_and_preserves_text_outside_markers(tmp_path: Path) -> None:
    project = _fixture_project(tmp_path)
    guidance = project / ".apm" / "instructions" / "engineering-workflow.md"
    issue_tracker = project / "docs" / "agents" / "issue-tracker.md"
    preserved = {
        guidance: ("Project preface.", "Project epilogue."),
        issue_tracker: ("Tracker preface.", "Tracker epilogue."),
    }

    _run_fixture_protocol(project, source_changes_approved=True)
    after_first_run = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    second_run = _run_fixture_protocol(project, source_changes_approved=True)
    after_second_run = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    assert second_run["proposals"] == []
    assert second_run["sync_commands"] == []
    assert after_second_run == after_first_run
    for path, user_text in preserved.items():
        content = path.read_text()
        assert all(text in content for text in user_text)

    explicit_recheck = _run_fixture_protocol(
        project,
        no_diff_recheck_approved=True,
    )
    assert explicit_recheck["sync_commands"] == [["mise", "run", "agent-sync"]]


def test_setup_leaf_contains_only_the_active_workflow_payload() -> None:
    assert {path.relative_to(SKILL).as_posix() for path in SKILL.rglob("*") if path.is_file()} == {
        "SKILL.md",
        "agents/openai.yaml",
        "templates/issue-tracker-github.md",
        "templates/project-guidance.md",
    }
    assert {
        path.relative_to(OVERLAY).as_posix(): path.read_bytes()
        for path in OVERLAY.rglob("*")
        if path.is_file()
    } == {
        path.relative_to(SKILL).as_posix(): path.read_bytes()
        for path in SKILL.rglob("*")
        if path.is_file()
    }


def test_protocol_requires_separate_fresh_confirmation_for_no_diff_recheck() -> None:
    assert _load_protocol()["confirmations"] == {
        "source_changes": "required",
        "no_diff_recheck": "fresh",
    }
