from __future__ import annotations

import difflib
import re
import shutil
from pathlib import Path, PurePosixPath

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
SKILL = PACKAGE / "skills" / "setup-engineering-workflow-for-apm"
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
        return f"{existing.rstrip()}\n\n{block}\n"

    assert existing.count(start_marker) == 1
    assert existing.count(end_marker) == 1
    before, marked = existing.split(start_marker)
    _, after = marked.split(end_marker)
    return f"{before}{block}{after}"


def _run_fixture_protocol(project: Path, *, approved: bool = True) -> dict:
    protocol = _load_protocol()
    start_marker = protocol["markers"]["start"]
    end_marker = protocol["markers"]["end"]
    proposals = []

    for source_file in protocol["source_files"]:
        destination = project / source_file["destination"]
        existing = destination.read_text() if destination.exists() else ""
        rendered = (SKILL / source_file["template"]).read_text()
        proposed = _replace_marked_section(existing, rendered, start_marker, end_marker)
        if proposed == existing:
            continue
        relative = destination.relative_to(project).as_posix()
        diff = "".join(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
        proposals.append((relative, diff, destination, proposed))

    directly_written_files: list[str] = []
    sync_commands: list[list[str]] = []
    if approved:
        for relative, _, destination, proposed in proposals:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(proposed)
            directly_written_files.append(relative)
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

    result = _run_fixture_protocol(project)

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

    result = _run_fixture_protocol(project, approved=False)

    assert result["directly_written_files"] == []
    assert result["sync_commands"] == []
    assert before == {
        path.relative_to(project).as_posix(): path.read_text()
        for path in project.rglob("*")
        if path.is_file()
    }
    for path, diff in result["proposals"]:
        assert diff.startswith(f"--- a/{path}\n+++ b/{path}\n")


def test_setup_is_idempotent_and_preserves_text_outside_markers(tmp_path: Path) -> None:
    project = _fixture_project(tmp_path)
    guidance = project / ".apm" / "instructions" / "engineering-workflow.md"
    issue_tracker = project / "docs" / "agents" / "issue-tracker.md"
    preserved = {
        guidance: ("Project preface.", "Project epilogue."),
        issue_tracker: ("Tracker preface.", "Tracker epilogue."),
    }

    _run_fixture_protocol(project)
    after_first_run = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    second_run = _run_fixture_protocol(project)
    after_second_run = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    assert second_run["proposals"] == []
    assert after_second_run == after_first_run
    for path, user_text in preserved.items():
        content = path.read_text()
        assert all(text in content for text in user_text)
