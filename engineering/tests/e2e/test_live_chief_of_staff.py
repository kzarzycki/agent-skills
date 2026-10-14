"""A chief of staff in one harness has a lead in the other harness do a small ask.

Live: it needs a logged-in Omnigent with a local host for both native harnesses, and runs only
with OMNIGENT_E2E=1 (about five minutes and two agent sessions per direction):

    OMNIGENT_E2E=1 uv run pytest -q -m live_agent engineering/tests/e2e/test_live_chief_of_staff.py
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.live_agent

SKILLS = Path(__file__).resolve().parents[2] / "skills"
SCRIPT = SKILLS / "orchestrating-agents" / "scripts" / "omnigent_agent.py"
NATIVE = {"claude": "claude-native", "codex": "codex-native"}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


def _sessions(og, repo: Path) -> list[str]:
    """The top-level sessions working in ``repo``, archived ones too (the chief archives its lead)."""
    page = og.call("GET", "/v1/sessions?kind=default&include_archived=true&limit=100")
    return [s["id"] for s in page.get("data", []) if s.get("workspace") == str(repo)]


def _omnigent():
    spec = importlib.util.spec_from_file_location("omnigent_agent_live", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.Omnigent()


@pytest.mark.parametrize(("chief", "lead"), [("claude", "codex"), ("codex", "claude")])
def test_chief_of_staff_has_a_lead_of_the_other_family_do_an_ask(
    tmp_path: Path, chief: str, lead: str
) -> None:
    if os.environ.get("OMNIGENT_E2E") != "1":
        pytest.skip("OMNIGENT_E2E=1 is required for the live chief-of-staff test")
    repo = (tmp_path / "project").resolve()
    repo.mkdir()
    # A native child is prompted for a read outside its workspace, so the skills live inside it.
    for name in ("chief-of-staff", "orchestrating-agents"):
        for target in (".claude", ".agents"):
            shutil.copytree(SKILLS / name, repo / target / "skills" / name)
    (repo / ".gitignore").write_text(".claude/\n.agents/\ntmp/\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "init")
    skills = repo / ".claude" / "skills"
    line = f"hello from {lead}"
    report = repo / "tmp" / "loop" / "chief-report.md"
    brief = repo / "tmp" / "loop" / "chief-brief.md"
    brief.parent.mkdir(parents=True)
    brief.write_text(
        f"You are this project's chief of staff: read and follow "
        f"{skills / 'chief-of-staff' / 'SKILL.md'}. Its `<script>` is "
        f"{skills / 'orchestrating-agents' / 'scripts' / 'omnigent_agent.py'}.\n\n"
        "The owner, in the session that started you:\n\n"
        f"> Have a {lead.capitalize()} lead add a file NOTES.md to this repo containing exactly "
        f"the line `{line}`, committed on main. Tell me when it's done.\n\n"
        "This is a test project with no remote and no issue tracker. Start no detached "
        "supervisor job; follow the lead with a one-shot `supervise`. Once the lead has reported "
        "and you have checked NOTES.md and the commit, archive the lead and write your final "
        "report: the lead's session id and what it did.\n"
    )
    module, og = _omnigent()
    started = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "start",
            "--top-level",
            chief,
            "chief-e2e",
            str(brief),
            str(report),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "OMNIGENT_PROJECT": ""},
    )
    assert started.returncode == 0, started.stderr
    chief_id = started.stdout.split()[0]
    try:
        waited = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "wait", chief_id, str(report), "--timeout", "1800"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert waited.returncode == 0, waited.stdout + waited.stderr
        assert (repo / "NOTES.md").read_text() == line + "\n"
        assert "NOTES.md" in _git(repo, "log", "-1", "--name-only", "--format=")
        assert _git(repo, "status", "--porcelain") == ""
        leads = [og.info(sid) for sid in _sessions(og, repo) if sid != chief_id]
        assert [(s.get("harness"), s.get("parent_session_id")) for s in leads] == [
            (NATIVE[lead], None)
        ]
    finally:
        module.reap(og, _sessions(og, repo) or [chief_id])
